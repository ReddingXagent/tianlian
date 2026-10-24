"""
通知发送服务 - 模板渲染 + 配置查找 + 日志记录
集成到工单派单/催单、告警触发流程中
"""
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.notification_config import NotificationConfig, NotificationTemplate, NotificationLog
from app.models.alarm_notification import AlarmNotification
from app.models.user import User
from app.services.notification_dispatcher import notification_dispatcher
from app.services.channel_providers import dispatch_real_channel

logger = logging.getLogger(__name__)

# 卡 6259ac0d: 静默时间 HH:MM 白名单 (与 API 层同规则), 读侧兜底校验
_QUIET_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# 事件类型 → 默认渠道映射
EVENT_CHANNEL_MAP = {
    "workorder_dispatch": ["sms", "app_push"],
    "workorder_urge": ["sms", "app_push"],
    "workorder_complete": ["app_push"],
    "alarm_trigger": ["sms", "email", "app_push", "im"],
    "alarm_escalate": ["sms", "email", "im"],
    "maintenance_reminder": ["app_push"],
    "system_notice": ["app_push", "im"],
}


# 通知静默判定兜底时区 (卡 ac0a7aa7): 坏值/缺失的最后防线, 模块加载时构造一次。
_FALLBACK_NOTIFICATION_TZ = ZoneInfo("Asia/Shanghai")


def _global_notification_timezone_name() -> str:
    """读 settings.NOTIFICATION_TIMEZONE, 取不到回退上海。

    settings 懒导入 (函数内) 规避模块加载时序耦合 —— 静默判定路径在热循环外,
    每次 _is_quiet_time 调用一次 import 开销可忽略 (sys.modules 缓存命中)。
    """
    try:
        from app.core.config import settings
        name = getattr(settings, "NOTIFICATION_TIMEZONE", None)
        if isinstance(name, str) and name.strip():
            return name
    except Exception:
        pass
    return "Asia/Shanghai"


def _get_notification_tz(config) -> ZoneInfo:
    """解析通知静默判定用的目标时区 (卡 ac0a7aa7, 与电价卡 9912ba63 同根)。

    quiet_start/quiet_end 按用户本地时间定义; 三级优先:
      1. per-config NotificationConfig.timezone (模型 default='Asia/Shanghai',
         旧实现从未读, 是死字段 —— 现复活)
      2. settings.NOTIFICATION_TIMEZONE (全局兜底, 默认上海)
      3. 硬编码 Asia/Shanghai (上述都取不到时)
    坏值 (None/空串/非 str/非法 IANA 名) 逐级回退, 永不抛异常 —— 静默判定是
    best-effort, 时区解析失败不应让通知发送整体崩溃。
    """
    tz_name = getattr(config, "timezone", None)
    if not isinstance(tz_name, str) or not tz_name.strip():
        tz_name = _global_notification_timezone_name()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return _FALLBACK_NOTIFICATION_TZ


def _event_now() -> datetime:
    """通知事件时间戳用的本地时区当前时刻 (卡 a7bc9343, 与电价/静默判定时区族同根)。

    旧实现 3 处 datetime.now().strftime() 是 naive, UTC 容器部署时显示错误时间
    (上海 14:00 被当 UTC 14:00 = 上海 22:00)。按 settings.NOTIFICATION_TIMEZONE
    解析目标时区, 坏值回退 Asia/Shanghai, 与 _get_notification_tz 同模式, 永不抛异常。
    """
    try:
        return datetime.now(ZoneInfo(_global_notification_timezone_name()))
    except Exception:
        return datetime.now(_FALLBACK_NOTIFICATION_TZ)


class NotificationSender:
    """通知发送服务"""

    def __init__(self):
        self._dispatcher = notification_dispatcher

    def send(
        self,
        event_type: str,
        event_id: str,
        event_data: Dict[str, Any],
        db: Optional[Session] = None,
        override_channels: Optional[List[str]] = None,
        override_receivers: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        发送通知的主入口
        
        Args:
            event_type: 事件类型 (workorder_dispatch, workorder_urge, alarm_trigger, etc.)
            event_id: 事件ID (工单号/告警ID)
            event_data: 事件数据，用于模板渲染
            db: 数据库会话
            override_channels: 覆盖渠道列表
            override_receivers: 覆盖接收人 [{'type': 'user', 'id': '1', 'name': '张三', 'phone': '138...'}]
        
        Returns:
            {'status': 'ok', 'results': [...]} 或 {'status': 'blocked', 'reason': '...'}
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # 1. 查找匹配的配置
            configs = self._find_configs(db, event_type)
            if not configs:
                logger.info("No notification config found for event_type=%s", event_type)
                return {"status": "no_config", "results": []}

            # 2. 确定渠道
            channels = override_channels or self._resolve_channels(configs, event_type)
            if not channels:
                return {"status": "no_channels", "results": []}

            # 3. 确定接收人
            receivers = override_receivers or self._resolve_receivers(configs, event_data, db)

            # 4. 查找模板
            templates = self._find_templates(db, event_type, channels)

            # 卡 8d98ebe3: 团队级配置 (team_id 为真实 int) 时, _dispatch_channel 走真实发送路径
            # 读 ChannelConfig 凭证; team_id 缺省/非 int (全局配置/既有测试的 mock 配置) →
            # getattr 安全取值避免 _FakeConfig 无属性崩溃, 并保持 legacy mock 路径。
            team_id = getattr(configs[0], "team_id", None) if configs else None

            # 5. 发送通知并记录日志
            results = []
            for channel in channels:
                channel_configs = [c for c in configs if self._is_channel_enabled(c, channel)]
                if not channel_configs:
                    continue

                # 检查静默时间
                if self._is_quiet_time(channel_configs[0]):
                    logger.info("Channel %s is in quiet time for event %s", channel, event_type)
                    results.append({"channel": channel, "status": "quiet"})
                    continue

                # 渲染内容
                content = self._render_content(templates, channel, event_data)
                subject = self._render_subject(templates, channel, event_data)

                for receiver in receivers:
                    try:
                        # 调用底层分发器
                        self._dispatch_channel(
                            channel, receiver, content, subject, event_data,
                            db=db, team_id=team_id,
                        )

                        # 记录日志
                        self._log_notification(
                            db, configs[0].id if configs else None,
                            event_type, event_id, event_data,
                            channel, templates.get(channel),
                            receiver, subject, content, "sent"
                        )
                        results.append({
                            "channel": channel,
                            "receiver": receiver.get("id", "unknown"),
                            "status": "sent"
                        })
                    except Exception as e:
                        logger.error("Failed to send %s to %s: %s", channel, receiver.get("id"), e)
                        self._log_notification(
                            db, configs[0].id if configs else None,
                            event_type, event_id, event_data,
                            channel, templates.get(channel),
                            receiver, subject, content, "failed", "服务内部错误，请稍后重试"
                        )
                        results.append({
                            "channel": channel,
                            "receiver": receiver.get("id", "unknown"),
                            "status": "failed",
                            "error": "服务内部错误，请稍后重试"
                        })

            db.commit()
            return {"status": "ok", "results": results}

        except Exception as e:
            logger.exception("NotificationSender.send error: %s", e)
            if should_close:
                db.rollback()
            return {"status": "error", "error": "服务内部错误，请稍后重试"}
        finally:
            if should_close:
                db.close()

    def send_workorder_dispatch(
        self,
        workorder_id: str,
        engineer_name: str,
        engineer_phone: str,
        device_name: str,
        station_name: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """发送工单派单通知"""
        event_data = {
            "workorder_id": workorder_id,
            "engineer_name": engineer_name,
            "engineer_phone": engineer_phone,
            "device_name": device_name,
            "station_name": station_name,
            "time": _event_now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self.send(
            event_type="workorder_dispatch",
            event_id=workorder_id,
            event_data=event_data,
            db=db,
            override_receivers=[{
                "type": "user",
                "id": engineer_phone,
                "name": engineer_name,
                "phone": engineer_phone,
            }],
        )

    def send_workorder_urge(
        self,
        workorder_id: str,
        engineer_name: str,
        engineer_phone: str,
        device_name: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """发送工单催单通知"""
        event_data = {
            "workorder_id": workorder_id,
            "engineer_name": engineer_name,
            "engineer_phone": engineer_phone,
            "device_name": device_name,
            "time": _event_now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self.send(
            event_type="workorder_urge",
            event_id=workorder_id,
            event_data=event_data,
            db=db,
            override_receivers=[{
                "type": "user",
                "id": engineer_phone,
                "name": engineer_name,
                "phone": engineer_phone,
            }],
        )

    def send_alarm_notification(
        self,
        alarm_id: int,
        alarm_content: str,
        device_id: int,
        station_id: int,
        level: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """发送告警通知，并持久化发送记录到 alarm_notifications (maint-platform-spec §2.1)"""
        event_data = {
            "alarm_id": alarm_id,
            "alarm_content": alarm_content,
            "device_id": device_id,
            "station_id": station_id,
            "level": level,
            "time": _event_now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        result = self.send(
            event_type="alarm_trigger",
            event_id=str(alarm_id),
            event_data=event_data,
            db=db,
        )
        # 持久化每条渠道发送结果，便于按告警查询通知审计
        self._record_alarm_notifications(db, alarm_id, result)
        return result

    # ─── Private Helpers ───

    def _find_configs(self, db: Session, event_type: str) -> List[NotificationConfig]:
        """查找匹配的配置"""
        configs = db.query(NotificationConfig).filter(
            NotificationConfig.enabled == True,
            NotificationConfig.trigger_events.contains([event_type]),
        ).order_by(NotificationConfig.priority.desc()).all()

        if not configs:
            # Fallback: 查找全局配置（trigger_events 为空表示全部事件）
            configs = db.query(NotificationConfig).filter(
                NotificationConfig.enabled == True,
                NotificationConfig.scope_type == "tenant",
            ).order_by(NotificationConfig.priority.desc()).all()

        return configs

    def _resolve_channels(
        self, configs: List[NotificationConfig], event_type: str
    ) -> List[str]:
        """从配置中解析启用的渠道"""
        channels = set()
        for config in configs:
            if config.sms_enabled:
                channels.add("sms")
            if config.email_enabled:
                channels.add("email")
            if config.app_push_enabled:
                channels.add("app_push")
            if config.im_b_enabled:
                channels.add("im_b")
            if config.im_enabled:
                channels.add("im")

        # 如果没有配置任何渠道，使用默认渠道
        if not channels:
            channels = set(EVENT_CHANNEL_MAP.get(event_type, ["app_push"]))

        return list(channels)

    def _resolve_receivers(
        self, configs: List[NotificationConfig], event_data: Dict, db: Session
    ) -> List[Dict[str, str]]:
        """解析接收人列表

        所有 config 的 receiver_roles 收集去重后, 用单次 User.role.in_(...) 查询批量拉取
        活跃用户并按角色分组, 在内存里复用 —— 修复 N config × M role 次 User 查询 (N+1)。
        返回顺序/去重语义与原逐角色循环一致: 按 config 顺序, 每个 config 先固定接收人再角色用户,
        角色用户按 DB 返回序, 跨 config 按 f"user_{id}" 去重。
        """
        receivers = []
        seen = set()

        # 批量预取: 收集所有唯一角色 → 单次查询 → 按 role 分组
        all_roles: List[str] = []
        for config in configs:
            for role in (config.receiver_roles or []):
                if role not in all_roles:
                    all_roles.append(role)

        users_by_role: Dict[str, List[User]] = {}
        if all_roles:
            users = db.query(User).filter(
                User.role.in_(all_roles),
                User.status == "active",
            ).all()
            for user in users:
                users_by_role.setdefault(user.role, []).append(user)

        for config in configs:
            # 固定接收人
            for r in (config.receivers or []):
                key = r if isinstance(r, str) else r.get("id", str(r))
                if key not in seen:
                    seen.add(key)
                    if isinstance(r, dict):
                        receivers.append(r)
                    else:
                        receivers.append({"type": "phone", "id": str(r), "name": str(r)})

            # 按角色查找用户 (从批量结果中取, 不再逐角色查询)
            for role in (config.receiver_roles or []):
                for user in users_by_role.get(role, []):
                    key = f"user_{user.id}"
                    if key not in seen:
                        seen.add(key)
                        receivers.append({
                            "type": "user",
                            "id": str(user.id),
                            "name": user.name or user.username,
                            "phone": user.phone or "",
                            "email": user.email or "",
                        })

        return receivers

    def _find_templates(
        self, db: Session, event_type: str, channels: List[str]
    ) -> Dict[str, NotificationTemplate]:
        """查找模板，按渠道索引

        所有渠道合并成单次 NotificationTemplate.channel.in_(channels) 查询, 内存里按 channel
        分组取每个渠道的首条匹配 —— 修复原 N 渠道 N 次 .first() 查询 (N+1), 与逐渠道
        .first() 的 DB 默认序语义等价。返回结构不变: {channel: template}。
        """
        templates: Dict[str, NotificationTemplate] = {}
        if not channels:
            return templates

        found = db.query(NotificationTemplate).filter(
            NotificationTemplate.enabled == True,
            NotificationTemplate.event_type == event_type,
            NotificationTemplate.channel.in_(channels),
        ).all()

        # 按 channel 分组, 保留每个渠道首条 (与原 per-channel .first() 的 DB 默认序一致)
        first_by_channel: Dict[str, NotificationTemplate] = {}
        for tpl in found:
            if tpl.channel not in first_by_channel:
                first_by_channel[tpl.channel] = tpl

        for channel in channels:
            tpl = first_by_channel.get(channel)
            if tpl is not None:
                templates[channel] = tpl
        return templates

    def _is_channel_enabled(self, config: NotificationConfig, channel: str) -> bool:
        """检查配置中某渠道是否启用"""
        channel_map = {
            "sms": config.sms_enabled,
            "email": config.email_enabled,
            "app_push": config.app_push_enabled,
            "im_b": config.im_b_enabled,
            "im": config.im_enabled,
        }
        return channel_map.get(channel, False)

    def _is_quiet_time(
        self, config: NotificationConfig, *, now: Optional[datetime] = None
    ) -> bool:
        """检查是否在静默时间内 (卡 ac0a7aa7, 与电价卡 9912ba63 同根)。

        quiet_start/quiet_end (HH:MM) 按用户本地时间定义。旧实现用 datetime.now()
        取 naive 本地时间读 .hour, UTC 容器部署时窗口整体错位 8h (上海 22:00 静默
        被当 UTC 22:00 = 上海 06:00)。现按 _get_notification_tz 解析的 per-config
        时区取本地时分。

        Args:
            now: 可注入 datetime 供测试确定性。aware 时先 astimezone(tz) 转目标时区
                 再取本地时分 (注入 UTC 绝对时刻即可验证错位修复); naive 时按表面
                 时分判定; None 时取 datetime.now(tz) 目标时区当前真实时刻。
        """
        if not config.quiet_start or not config.quiet_end:
            return False
        try:
            # 卡 6259ac0d: "25:99" 等数值可解析的坏值不会在下方抛异常, 会静默按窗口
            # 比较返回 False 击穿免打扰 —— 读侧同样按 HH:MM 白名单校验, 坏值统一走
            # 本 except 分支 (fail-open + warning 留痕)。
            if not _QUIET_TIME_RE.match(config.quiet_start) or not _QUIET_TIME_RE.match(config.quiet_end):
                raise ValueError("quiet_start/quiet_end 非 HH:MM 格式")
            tz = _get_notification_tz(config)
            current = now if now is not None else datetime.now(tz)
            if current.tzinfo is not None:
                current = current.astimezone(tz)
            now_minutes = current.hour * 60 + current.minute

            start_h, start_m = map(int, config.quiet_start.split(":"))
            end_h, end_m = map(int, config.quiet_end.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= end_minutes:
                return start_minutes <= now_minutes <= end_minutes
            else:
                # 跨天 (e.g., 22:00 - 08:00)
                return now_minutes >= start_minutes or now_minutes <= end_minutes
        except Exception as e:
            # 卡 6259ac0d: 保留 fail-open (坏数据全渠道静默更糟), 但必须留痕 —— 坏值
            # 静默击穿免打扰不可接受, warning 带 config id 与坏值便于排查修数。
            logger.warning(
                "静默时间判定失败, 免打扰被跳过 [config %s, quiet_start=%r, quiet_end=%r]: %s",
                getattr(config, "id", None), config.quiet_start, config.quiet_end, e,
            )
            return False

    def _render_content(
        self, templates: Dict[str, NotificationTemplate], channel: str, event_data: Dict
    ) -> str:
        """渲染通知内容"""
        template = templates.get(channel)
        if template and template.content:
            return self._format_template(template.content, event_data)

        # 默认内容
        return self._default_content(channel, event_data)

    def _render_subject(
        self, templates: Dict[str, NotificationTemplate], channel: str, event_data: Dict
    ) -> Optional[str]:
        """渲染通知主题"""
        template = templates.get(channel)
        if template and template.subject:
            return self._format_template(template.subject, event_data)
        return None

    def _format_template(self, template_str: str, data: Dict) -> str:
        """简单的模板变量替换 {variable}"""
        result = template_str
        for key, value in data.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def _default_content(self, channel: str, event_data: Dict) -> str:
        """生成默认通知内容"""
        if "workorder_dispatch" in str(event_data.get("_event_type", "")) or "workorder" in str(event_data.get("workorder_id", "")):
            return (
                f"【天链运维】新工单 {event_data.get('workorder_id', '')} 已分配给您。"
                f"设备：{event_data.get('device_name', '')}，"
                f"站点：{event_data.get('station_name', '')}，"
                f"请及时处理。"
            )
        elif "alarm" in str(event_data.get("alarm_id", "")) or "alarm" in str(event_data.get("level", "")):
            return (
                f"【天链告警】{event_data.get('level', '')}级别告警："
                f"{event_data.get('alarm_content', '')}。"
                f"设备ID：{event_data.get('device_id', '')}。"
            )
        return f"【天链运维】通知：{event_data}"

    def _dispatch_channel(
        self, channel: str, receiver: Dict, content: str, subject: Optional[str],
        event_data: Dict, *, db: Optional[Session] = None, team_id: Optional[int] = None,
    ):
        """调用底层分发器发送。

        双路径 (卡 8d98ebe3):
        - 真实发送: 当 ``db`` 提供且 ``team_id`` 为真实 int (团队级配置) 时, 读
          ChannelConfig(team_id, channel) 凭证真实触达 (im/wecom/webhook HTTP +
          sms/voice provider)。渠道未配置/enabled=False/凭证缺失 → 跳过 (INFO);
          发送失败 → 抛异常, 由 send() 落 notification_logs(status=failed)。
        - legacy mock: db 缺省 或 team_id 非 int (含现有单元测试的 mock 配置与
          team_id=None 的全局配置) → 保持原 mock dispatcher 行为, 不破坏既有测试。
          ``isinstance(team_id, int)`` 守卫同时排除 None 与 MagicMock 自动子属性。"""
        if db is not None and isinstance(team_id, int):
            result = dispatch_real_channel(
                channel, team_id, db, receiver, content, subject
            )
            status = (result or {}).get("status")
            if status == "failed":
                # 最终失败 → 抛异常让 send() 记 failed 日志 (不泄露原始错误给调用方)
                raise RuntimeError(
                    (result or {}).get("error") or "渠道发送失败"
                )
            # sent / skipped: skipped 已在 dispatch_real_channel 内 INFO 日志
            return
        if channel == "sms":
            phone = receiver.get("phone", receiver.get("id", ""))
            self._dispatcher.notify_sms(message=content, phone=phone)
        elif channel == "email":
            email = receiver.get("email", receiver.get("id", ""))
            self._dispatcher.notify_email(message=content, to=email)
        elif channel == "im":
            self._dispatcher.notify_im(message=content)
        elif channel == "app_push":
            logger.info("[APP_PUSH MOCK] To: %s, Content: %s", receiver.get("name"), content[:80])
        elif channel == "im_b":
            logger.info("[WECHAT MOCK] To: %s, Content: %s", receiver.get("name"), content[:80])
        else:
            logger.info("[%s MOCK] To: %s, Content: %s", channel.upper(), receiver.get("name"), content[:80])

    def _log_notification(
        self, db: Session, config_id: Optional[int],
        event_type: str, event_id: str, event_data: Dict,
        channel: str, template: Optional[NotificationTemplate],
        receiver: Dict, subject: Optional[str], content: str,
        status: str, error_message: Optional[str] = None,
    ):
        """记录通知发送日志

        best-effort: 用 SAVEPOINT (db.begin_nested) 隔离单条日志写入, 仅 add+flush
        不 commit (事务边界由调用方 send 统一管理)。写日志失败只回滚 savepoint,
        不影响同一事务内已写入的其他日志记录 (卡 a7bc9343) —— 通知本身已由
        _dispatch_channel 发出, 单条日志缺失不应反过来让 send() 循环里整批日志丢失。
        """
        try:
            with db.begin_nested():
                log = NotificationLog(
                    config_id=config_id,
                    event_type=event_type,
                    event_id=event_id,
                    event_data=event_data,
                    channel=channel,
                    template_id=template.id if template else None,
                    template_code=template.code if template else None,
                    receiver_type=receiver.get("type", "phone"),
                    receiver_id=receiver.get("id", "unknown"),
                    receiver_name=receiver.get("name", ""),
                    subject=subject,
                    content=content,
                    status=status,
                    error_message=error_message,
                    sent_at=datetime.now(timezone.utc) if status == "sent" else None,
                )
                db.add(log)
                db.flush()  # 在 savepoint 内物化 INSERT, 失败只回滚本 savepoint
        except Exception as e:
            logger.error("记录通知日志失败(%s/%s): %s", event_type, channel, e)

    def _record_alarm_notifications(
        self, db: Optional[Session], alarm_id: int, send_result: Dict[str, Any]
    ) -> None:
        """将本次告警通知的发送结果持久化到 alarm_notifications 表。

        send() 返回的 results 每条形如 {channel, receiver, status[, error]}，
        逐条落库；写库失败不影响主流程（仅记日志），通知发送本身已由 send() 完成。
        每行独立 SAVEPOINT 隔离 (卡 a7bc9343): 单行毒记录只回滚自身, 不再让整批
        在一次 commit 里连坐丢失。
        """
        results = (send_result or {}).get("results") or []
        if not results:
            return

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            for r in results:
                status = r.get("status", "unknown")
                try:
                    with db.begin_nested():
                        db.add(AlarmNotification(
                            alarm_id=alarm_id,
                            channel=r.get("channel", "unknown"),
                            recipient=r.get("receiver") or "",
                            status=status,
                            result=r.get("error") if status == "failed" else None,
                            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
                        ))
                        db.flush()
                except Exception as row_err:
                    # 单行写库失败: 只回滚该行 savepoint, 继续其余行 (best-effort)
                    logger.warning(
                        "跳过 alarm_notifications 毒行 [alarm %s, ch %s]: %s",
                        alarm_id, r.get("channel"), row_err,
                    )
            db.commit()
        except Exception as e:
            logger.error("Failed to persist alarm_notifications [alarm %s]: %s", alarm_id, e)
            if should_close:
                db.rollback()
        finally:
            if should_close:
                db.close()


# 全局单例
notification_sender = NotificationSender()

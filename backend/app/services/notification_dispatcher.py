"""
消息推送服务 - 邮件/Webhook/IM/日志
Phase19: 集成IM告警通知
Phase35: 多级告警通道 + smtplib邮件增强
卡 6ca6092d: 告警链路凭证源统一 —— im_b/sms 优先读团队级 ChannelConfig
(站点→团队, 平台级回退; 经 dispatch_real_channel 自带 5xx/网络异常重试),
未配置回退 settings 全局值; legacy _send_im_b/_send_sms 补 5xx/网络异常
重试 (对齐 channel_providers._post_with_retry)。IM保持 im_notify_service。
"""
from app.services.im_notify import im_notify_service
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import List, Optional
import logging
import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.notification_rule import NotificationRule
from app.models.alarm import Alarm, AlarmLevel
from app.models.station import Station
from app.services.audit_service import audit_service
from app.services.channel_providers import dispatch_real_channel

logger = logging.getLogger(__name__)


# ============================
# 告警级别 → 通知通道映射
# ============================
LEVEL_CHANNEL_MAP = {
    AlarmLevel.INFO: ['im', 'logger'],
    AlarmLevel.WARNING: ['im', 'logger', 'email'],
    AlarmLevel.CRITICAL: ['im', 'email', 'logger'],
    AlarmLevel.FATAL: ['im', 'email', 'sms', 'logger'],
}

# 紧急告警强制通知通道
URGENT_LEVELS = {AlarmLevel.CRITICAL, AlarmLevel.FATAL}

# 卡 6ca6092d: legacy HTTP 发送重试参数 (对齐 channel_providers.DEFAULT_*)
_RETRY_MAX_RETRIES = 2
_RETRY_BACKOFF = 0.1

# 卡 6ca6092d: 告警链路读 ChannelConfig 真实凭证的渠道
# (dispatcher 渠道名 → channel_providers/ChannelType 渠道名)
_REAL_CREDENTIAL_CHANNELS = {"im_b": "wecom", "sms": "sms"}


def _mask_phone(phone):
    """Mask phone number: 13812345678 -> 138****5678"""
    if not phone or len(str(phone)) < 7:
        return '****'
    s = str(phone)
    return f"{s[:3]}****{s[-4:]}"


def _mask_email(email):
    """Mask email local part: user@example.com -> us***@example.com"""
    if not email or '@' not in str(email):
        return '****'
    s = str(email)
    local, domain = s.split('@', 1)
    if len(local) <= 2:
        masked_local = '***'
    else:
        masked_local = local[:2] + '***'
    return f"{masked_local}@{domain}"


def _post_with_retry_sync(url, payload, *, timeout=5):
    """requests.post 重试包装 (卡 6ca6092d, 对齐 channel_providers._post_with_retry):
    5xx 与网络异常重试 (指数退避 _RETRY_BACKOFF * 2^attempt, 共 _RETRY_MAX_RETRIES 次),
    2xx/4xx 立即返回由调用方判定业务结果; 重试耗尽抛最后一次异常。"""
    last_exc: Optional[Exception] = None
    attempts = _RETRY_MAX_RETRIES + 1
    for attempt in range(attempts):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code < 500:
                return resp  # 2xx/4xx: 不重试
            last_exc = RuntimeError(f"http {resp.status_code}")
        except Exception as e:
            last_exc = e
        if attempt < attempts - 1:
            time.sleep(_RETRY_BACKOFF * (2 ** attempt))
    raise last_exc if last_exc else RuntimeError("send failed")



class NotificationDispatcher:
    """通知分发器"""

    def __init__(self):
        self._email_config = {
            'smtp_host': getattr(settings, 'SMTP_HOST', None),
            'smtp_port': getattr(settings, 'SMTP_PORT', 587),
            'smtp_user': getattr(settings, 'SMTP_USER', None),
            'smtp_pass': getattr(settings, 'SMTP_PASS', None),
            'from_addr': getattr(settings, 'EMAIL_FROM', None),
            'to_addr': getattr(settings, 'EMAIL_TO', 'admin@tianlian.com'),
        }
        self._im_b_webhook = getattr(settings, 'WECHAT_WEBHOOK_URL', None)
        self._sms_api_url = getattr(settings, 'SMS_API_URL', None)
        # 管理员邮箱列表（可通过环境变量配置逗号分隔）
        self._admin_emails = getattr(settings, 'ADMIN_EMAILS', 'admin@tianlian.com')
        if isinstance(self._admin_emails, str):
            self._admin_emails = [e.strip() for e in self._admin_emails.split(',')]

    def dispatch(self, alarm=None, channels=None, alarm_id=None, level=None, message=None,
                 *, db: Optional[Session] = None, team_id: Optional[int] = None):
        """分发告警通知到指定渠道

        Supports both direct Alarm object and keyword-based calls for testing.

        卡 6ca6092d: db+team_id 提供时 (告警链路 dispatch_on_alarm 注入),
        im_b/sms 渠道优先读团队级 ChannelConfig 凭证真实发送 (自带重试),
        未配置回退 legacy settings 路径; 缺省保持原 legacy 行为。
        """
        # Keyword-based call (for tests)
        if alarm is None and alarm_id is not None:
            # Map string level to AlarmLevel enum
            level_map = {
                'info': AlarmLevel.INFO,
                'warning': AlarmLevel.WARNING,
                'critical': AlarmLevel.CRITICAL,
                'fatal': AlarmLevel.FATAL,
            }
            alarm_level = level_map.get((level or 'warning').lower(), AlarmLevel.WARNING)
            # Build a minimal alarm-like object for test dispatch
            class _TestAlarm:
                def __init__(self):
                    self.id = alarm_id
                    self.level = alarm_level
                    self.content = message or ''
                    self.device_id = 0
                    self.station_id = 0
                    self.fault_code = None
                    self.created_at = datetime.now(timezone.utc)
                    self.escalated_from = None
                    self.escalated_at = None
                    self.aggregation_count = 1
            alarm = _TestAlarm()
        
        if channels is None:
            channels = []
        
        if not channels:
            logger.info("No channels configured for alarm %s", getattr(alarm, 'id', 'unknown'))
            return {'status': 'no_channels', 'channels': []}

        results = []
        senders = {
            'email': self._send_email,
            'im_b': self._send_im_b,
            'sms': self._send_sms,
            'im': self._send_im,
            'logger': self._log_notification,
        }
        for channel in channels:
            try:
                # 卡 6ca6092d: im_b/sms 优先读 ChannelConfig 团队级凭证真实发送
                # (dispatch_real_channel 自带 5xx/网络异常重试); skipped (未配置/
                # 缺凭证) 回退 legacy settings 路径, 未配置团队保持原行为。
                if db is not None and channel in _REAL_CREDENTIAL_CHANNELS:
                    entry = self._send_real_channel(channel, team_id, db, alarm)
                    if entry is not None:
                        results.append(entry)
                        continue
                sender = senders.get(channel)
                if sender is None:
                    logger.warning("Unknown channel: %s", channel)
                    results.append({
                        'channel': channel,
                        'status': 'unknown',
                        'error': f"unknown channel: {channel}",
                    })
                    continue
                sent = sender(alarm)
                if sent is False:
                    results.append({'channel': channel, 'status': 'failed', 'error': 'send failed'})
                else:
                    results.append({'channel': channel, 'status': 'sent'})
            except Exception as e:
                logger.error("Failed to send %s notification: %s", channel, e)
                results.append({'channel': channel, 'status': 'failed', 'error': f"send failed: {e}"})
        return {'status': 'dispatched', 'channels': results}

    def dispatch_on_alarm(self, alarm: Alarm, db: Session = None,
                          override_channels: Optional[List[str]] = None):
        """
        告警触发时自动匹配规则并分发通知
        支持 override_channels 参数用于级别驱动的通道选择

        卡 6ca6092d: 解析告警归属团队 (站点→团队) 并注入 dispatch, 使 im_b/sms
        渠道读团队级 ChannelConfig 凭证 (平台级回退), 与事件通知健康路径统一。
        """
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False

        try:
            team_id = self._resolve_alarm_team_id(alarm, db)
            # 优先级1: 调用方指定通道（级别策略）
            if override_channels:
                self.dispatch(alarm, override_channels, db=db, team_id=team_id)
                audit_service.log_crud(
                    0, "system", "dispatch", "notification",
                    str(alarm.id),
                    f"level:{alarm.level.value} channels:{override_channels}"
                )
                return

            # 优先级2: 匹配通知规则
            rules = db.query(NotificationRule).filter(
                NotificationRule.enabled == True
            ).all()

            matched = False
            for rule in rules:
                if self._rule_matches(rule, alarm):
                    channels = self._get_rule_channels_with_level(rule, alarm)
                    self.dispatch(alarm, channels, db=db, team_id=team_id)
                    matched = True
                    audit_service.log_crud(
                        0, "system", "dispatch", "notification",
                        str(rule.id),
                        f"rule:{rule.name} → alarm:{alarm.id}"
                    )

            if not matched:
                # 优先级3: 默认渠道（按级别）
                default_channels = LEVEL_CHANNEL_MAP.get(
                    alarm.level, ['logger']
                )
                self.dispatch(alarm, default_channels, db=db, team_id=team_id)
        except Exception as e:
            logger.error("dispatch_on_alarm error: %s", e)
        finally:
            if should_close:
                db.close()

    def _resolve_alarm_team_id(self, alarm: Alarm, db: Optional[Session]) -> Optional[int]:
        """告警 → 站点 → 团队 (卡 6ca6092d): ChannelConfig 凭证按团队隔离。

        station 缺失/查询异常/team_id 非 int → None (平台级凭证回退, 与
        _lookup_channel_config 的 team_id NULL 回退对齐)。"""
        station_id = getattr(alarm, "station_id", None)
        if not station_id or db is None:
            return None
        try:
            station = db.query(Station).filter(Station.id == station_id).first()
            team_id = getattr(station, "team_id", None)
            return team_id if isinstance(team_id, int) else None
        except Exception as e:
            logger.warning(
                "告警团队归属解析失败 (station=%s), 回退平台级凭证: %s", station_id, e
            )
            return None

    def _rule_matches(self, rule: NotificationRule, alarm: Alarm) -> bool:
        """检查规则是否匹配告警"""
        if not rule.enabled:
            return False
        if rule.level and alarm.level.value != rule.level:
            return False
        return True

    def _get_rule_channels_with_level(self, rule: NotificationRule,
                                       alarm: Alarm) -> List[str]:
        """根据规则渠道 + 告警级别扩展渠道"""
        channels = rule.channels or []
        # 紧急级别增强渠道
        if alarm.level in URGENT_LEVELS:
            extra = LEVEL_CHANNEL_MAP.get(alarm.level, [])
            for ch in extra:
                if ch not in channels:
                    channels.append(ch)
        return channels

    def notify_sms(self, alarm=None, message=None, phone=None):
        """发送短信通知（便捷方法）"""
        if alarm:
            self._send_sms(alarm)
        else:
            logger.info("[SMS MOCK] To: %s, Msg: %s", _mask_phone(phone), (message or '')[:80])

    def send_sms(self, alarm=None, message=None, phone=None):
        """发送短信通知（别名）"""
        self.notify_sms(alarm=alarm, message=message, phone=phone)

    def notify_email(self, alarm=None, message=None, to=None):
        """发送邮件通知（便捷方法）"""
        if alarm:
            self._send_email(alarm)
        else:
            logger.info("[EMAIL MOCK] To: %s, Msg: %s", _mask_email(to), (message or '')[:80])

    def send_email(self, alarm=None, message=None, to=None):
        """发送邮件通知（别名）"""
        self.notify_email(alarm=alarm, message=message, to=to)

    def notify_im(self, alarm=None, message=None):
        """发送IM通知（便捷方法）"""
        if alarm:
            self._send_im(alarm)
        else:
            logger.info("[IM MOCK] Msg: %s", message or '')

    def send_im(self, alarm=None, message=None):
        """发送IM通知（别名）"""
        self.notify_im(alarm=alarm, message=message)

    def notify_webhook(self, alarm=None, url=None, payload=None):
        """发送Webhook通知（便捷方法）"""
        logger.info("[WEBHOOK MOCK] URL: %s, Payload: %s", url or 'unknown', payload or '')

    def send_webhook(self, alarm=None, url=None, payload=None):
        """发送Webhook通知（别名）"""
        self.notify_webhook(alarm=alarm, url=url, payload=payload)

    def get_history(self, page: int = 1, page_size: int = 10) -> list:
        """获取通知历史"""
        return []

    def _send_email(self, alarm: Alarm) -> bool:
        """发送邮件通知（内置 smtplib，无额外依赖）。返回是否成功。"""
        subject = self._build_email_subject(alarm)
        body = self._build_email_body(alarm)
        to_addrs = self._admin_emails

        # 如果 smtp 未配置，走 mock 日志
        if not self._email_config['smtp_host']:
            logger.info(
                "[EMAIL MOCK] To: %s, Subject: %s",
                ', '.join(to_addrs), subject
            )
            return True

        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = self._email_config['from_addr'] or 'noreply@tianlian.com'
        msg['To'] = ', '.join(to_addrs)

        # 纯文本版本
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # HTML 版本（紧急告警用富文本）
        if alarm.level in URGENT_LEVELS:
            html_body = self._build_email_html_body(alarm)
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        try:
            with smtplib.SMTP(
                self._email_config['smtp_host'],
                self._email_config['smtp_port'],
                timeout=10
            ) as server:
                server.starttls()
                if self._email_config['smtp_user'] and self._email_config['smtp_pass']:
                    server.login(
                        self._email_config['smtp_user'],
                        self._email_config['smtp_pass']
                    )
                server.sendmail(
                    self._email_config['from_addr'] or 'noreply@tianlian.com',
                    to_addrs,
                    msg.as_string()
                )
            logger.info("[EMAIL] Sent to %s: %s", ', '.join(_mask_email(a) for a in to_addrs), subject)
            return True
        except Exception as e:
            logger.warning("Email send failed: %s", e)
            return False

    def _build_email_subject(self, alarm: Alarm) -> str:
        """构建邮件主题"""
        level_labels = {
            AlarmLevel.INFO: '提示',
            AlarmLevel.WARNING: '预警',
            AlarmLevel.CRITICAL: '严重',
            AlarmLevel.FATAL: '紧急',
        }
        label = level_labels.get(alarm.level, alarm.level.value)
        escalation_tag = ""
        if alarm.escalated_from:
            escalation_tag = f" [已升级]"
        return f"[{label}]{escalation_tag} 天链告警: {alarm.content[:80]}"

    def _build_email_body(self, alarm: Alarm) -> str:
        """构建邮件纯文本正文"""
        lines = [
            f"告警级别: {alarm.level.value}",
            f"告警内容: {alarm.content}",
            f"设备ID: {alarm.device_id}",
            f"站点ID: {alarm.station_id or 'N/A'}",
            f"故障码: {alarm.fault_code or 'N/A'}",
            f"时间: {alarm.created_at or datetime.now(timezone.utc)}",
        ]
        if alarm.escalated_from:
            lines.append(f"升级来源: {alarm.escalated_from}")
            lines.append(f"升级时间: {alarm.escalated_at or 'N/A'}")
        if alarm.aggregation_count and alarm.aggregation_count > 1:
            lines.append(f"聚合计数: 共 {alarm.aggregation_count} 次触发")
        return "\n".join(lines)

    def _build_email_html_body(self, alarm: Alarm) -> str:
        """构建邮件 HTML 正文（紧急告警用）"""
        level_color = {
            AlarmLevel.INFO: '#3498db',
            AlarmLevel.WARNING: '#f39c12',
            AlarmLevel.CRITICAL: '#e74c3c',
            AlarmLevel.FATAL: '#c0392b',
        }.get(alarm.level, '#95a5a6')

        time_str = alarm.created_at.strftime('%Y-%m-%d %H:%M:%S') if alarm.created_at else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
<div style="border-left: 6px solid {level_color}; padding: 12px; background: #f8f9fa;">
<h2 style="color: {level_color};">🚨 天链告警通知</h2>
<table style="border-collapse: collapse; width: 100%;">
<tr><td style="padding: 6px; font-weight: bold;">级别</td><td style="padding: 6px;">{alarm.level.value}</td></tr>
<tr><td style="padding: 6px; font-weight: bold;">内容</td><td style="padding: 6px;">{alarm.content}</td></tr>
<tr><td style="padding: 6px; font-weight: bold;">设备ID</td><td style="padding: 6px;">{alarm.device_id}</td></tr>
<tr><td style="padding: 6px; font-weight: bold;">时间</td><td style="padding: 6px;">{time_str}</td></tr>
{"<tr><td style='padding: 6px; font-weight: bold;'>升级来源</td><td style='padding: 6px; color: red;'>" + alarm.escalated_from + "</td></tr>" if alarm.escalated_from else ""}
{"<tr><td style='padding: 6px; font-weight: bold;'>聚合次数</td><td style='padding: 6px;'>" + str(alarm.aggregation_count) + "</td></tr>" if alarm.aggregation_count and alarm.aggregation_count > 1 else ""}
</table>
<p style="color: #666; font-size: 12px; margin-top: 16px;">天链运维 v3 | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</p>
</div></body></html>"""

    # ========== 企业IM-B ==========

    def _send_real_channel(self, channel: str, team_id: Optional[int],
                           db: Session, alarm: Alarm) -> Optional[dict]:
        """告警链路真实凭证发送 (卡 6ca6092d): im_b→wecom / sms 读 ChannelConfig
        (团队级 + 平台级回退) 经 channel_providers.dispatch_real_channel, 自带
        5xx/网络异常重试。

        skipped (渠道未配置/缺凭证) → None, 调用方回退 legacy settings 路径;
        sent/failed → dispatch results 条目 (failed 不回退, 避免同一告警双发)。"""
        real_channel = _REAL_CREDENTIAL_CHANNELS[channel]
        if real_channel == "wecom":
            content = self._build_im_b_markdown(alarm)
            receiver = {"type": "group", "id": "wecom_group", "name": "wecom_group"}
        else:
            content = f"[天链告警]{alarm.level.value}:{alarm.content[:60]}"
            phone = getattr(settings, 'SMS_PHONE', '157****3673')
            receiver = {"type": "phone", "id": phone, "phone": phone}
        try:
            result = dispatch_real_channel(real_channel, team_id, db, receiver, content)
        except Exception as e:
            logger.error("告警 %s 渠道真实发送异常 (team=%s): %s", real_channel, team_id, e)
            return {'channel': channel, 'status': 'failed', 'error': f"send failed: {e}"}
        status = (result or {}).get("status")
        if status == "sent":
            return {'channel': channel, 'status': "sent"}
        if status == "failed":
            return {'channel': channel, 'status': "failed",
                    'error': (result or {}).get("error") or "send failed"}
        logger.info(
            "告警 %s 渠道未配置/缺凭证 (team=%s), 回退 legacy 路径", real_channel, team_id
        )
        return None

    def _build_im_b_markdown(self, alarm: Alarm) -> str:
        """企微 markdown 消息体 (legacy _send_im_b 与 ChannelConfig wecom 真实路径共用)。"""
        return (
            f"## 天链告警通知\n"
            f"> **级别**: {alarm.level.value}\n"
            f"> **内容**: {alarm.content}\n"
            f"> **设备**: #{alarm.device_id}\n"
            f"> **时间**: {alarm.created_at or datetime.now(timezone.utc)}\n"
            + (f"> **升级**: {alarm.escalated_from}\n" if alarm.escalated_from else "")
            + (f"> **聚合**: 共{alarm.aggregation_count}次\n" if alarm.aggregation_count and alarm.aggregation_count > 1 else "")
        )

    def _send_im_b(self, alarm: Alarm) -> bool:
        """发送企业IM-B通知 (settings 全局 webhook)。返回是否成功。

        校验 HTTP 状态码 + 企业IM-B响应体 errcode==0；5xx/网络异常重试
        (_post_with_retry_sync, 卡 6ca6092d)；4xx/业务拒绝不重试；
        webhook 失效/内容超限/网关拒绝时返回 False，避免告警静默丢失。
        """
        if not self._im_b_webhook:
            logger.info("[WECHAT MOCK] %s", alarm.content[:80])
            return True

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": self._build_im_b_markdown(alarm)},
        }
        try:
            resp = _post_with_retry_sync(self._im_b_webhook, payload, timeout=5)
            if resp.status_code != 200:
                logger.error("IMB webhook HTTP %d: %s", resp.status_code, resp.text[:200])
                return False
            # 企业IM-B webhook 返回 JSON: {"errcode":0,"errmsg":"ok"} 或错误码
            body = resp.json()
            if body.get("errcode", 0) != 0:
                logger.error("IMB webhook errcode %d: %s", body.get("errcode"), body.get("errmsg", ""))
                return False
            return True
        except Exception as e:
            logger.error("IMB webhook failed (重试耗尽): %s", e)
            return False

    # ========== 短信 ==========

    def _send_sms(self, alarm: Alarm) -> bool:
        """发送短信通知（settings 全局 API 网关）。返回是否成功。

        校验 HTTP 状态码；5xx/网络异常重试 (_post_with_retry_sync, 卡 6ca6092d)；
        4xx 不重试；网关拒绝/重试耗尽时返回 False，避免告警静默丢失。
        """
        if not self._sms_api_url:
            logger.info("[SMS MOCK] To: 157****3673, Msg: [%s] %s", alarm.level.value, alarm.content[:40])
            return True

        try:
            payload = {
                "phone": getattr(settings, 'SMS_PHONE', '157****3673'),
                "content": f"[天链告警]{alarm.level.value}:{alarm.content[:60]}",
            }
            resp = _post_with_retry_sync(self._sms_api_url, payload, timeout=5)
            if resp.status_code >= 400:
                logger.error("SMS API HTTP %d: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as e:
            logger.error("SMS API failed (重试耗尽): %s", e)
            return False

    # ========== IM ==========

    def _send_im(self, alarm: Alarm) -> bool:
        """发送IM通知（Phase19）。返回是否成功。

        卡 9fbc00ce (a7bc9343 漏改): 协程执行交由 im_notify_service.
        _run_coro_sync。旧实现 new_event_loop+set_event_loop+run_until_complete
        有两处问题: close 后线程 loop policy 悬垂指向 closed loop; async 上下文
        (FastAPI async worker) 调用直接 RuntimeError → except 吞掉 → 告警IM
        通知静默丢弃。
        """
        try:
            return im_notify_service._run_coro_sync(
                im_notify_service.notify_system_alarm(alarm)
            )
        except Exception as e:
            logger.error("IM通知失败: %s", e)
            return False

    # ========== 直接通知（非告警） ==========

    def send_sms_to_user(self, phone: str, content: str) -> bool:
        """直接给指定手机号发短信（非告警场景，如 API 端点调用）。

        卡 9fbc00ce (6ca6092d 遗留): 5xx/网络异常重试
        (_post_with_retry_sync, 对齐 _send_sms legacy 路径); 4xx 不重试。
        Returns True 如果发送成功（含 mock 模式），False 如果发送失败。
        """
        if not phone:
            logger.warning("send_sms_to_user: phone is empty")
            return False
        if not self._sms_api_url:
            logger.info("[SMS MOCK] To: %s, Msg: %s", _mask_phone(phone), content[:80])
            return True
        try:
            payload = {
                "phone": phone,
                "content": content[:200],
            }
            resp = _post_with_retry_sync(self._sms_api_url, payload, timeout=5)
            if resp.status_code >= 400:
                logger.error("SMS API HTTP %d: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as e:
            logger.error("SMS API failed (重试耗尽): %s", e)
            return False

    def send_email_to_user(self, to_addr: str, subject: str, body: str) -> bool:
        """直接给指定邮箱发邮件（非告警场景，如 API 端点调用）。

        Returns True 如果发送成功（含 mock 模式），False 如果发送失败。
        """
        if not to_addr:
            logger.warning("send_email_to_user: to_addr is empty")
            return False
        if not self._email_config['smtp_host']:
            logger.info("[EMAIL MOCK] To: %s, Subject: %s", _mask_email(to_addr), subject)
            return True
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = self._email_config['from_addr'] or 'noreply@tianlian.com'
        msg['To'] = to_addr
        try:
            with smtplib.SMTP(
                self._email_config['smtp_host'],
                self._email_config['smtp_port'],
                timeout=10
            ) as server:
                server.starttls()
                if self._email_config['smtp_user'] and self._email_config['smtp_pass']:
                    server.login(
                        self._email_config['smtp_user'],
                        self._email_config['smtp_pass']
                    )
                server.sendmail(
                    self._email_config['from_addr'] or 'noreply@tianlian.com',
                    [to_addr],
                    msg.as_string()
                )
            logger.info("[EMAIL] Sent to %s: %s", _mask_email(to_addr), subject)
            return True
        except Exception as e:
            logger.warning("Email send failed: %s", e)
            return False

    # ========== 日志 ==========

    def _log_notification(self, alarm: Alarm):
        """记录通知到日志"""
        extra = ""
        if alarm.escalated_from:
            extra += f" [升级:{alarm.escalated_from}]"
        if alarm.aggregation_count and alarm.aggregation_count > 1:
            extra += f" [聚合x{alarm.aggregation_count}]"
        logger.info(
            "[NOTIFY] alarm#%s level=%s device=%s%s: %s",
            alarm.id, alarm.level.value, alarm.device_id,
            extra, alarm.content[:100]
        )


notification_dispatcher = NotificationDispatcher()
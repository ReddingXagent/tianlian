"""
IM告警通知服务
Phase19: 将 Prometheus/Alertmanager 告警推送至IM
卡 9fbc00ce: 平台级 webhook 签名 (IM_SECRET 可选, 开启「签名校验」的机器人
body 必须带 timestamp+sign, 算法复用 channel_providers.im_sign; 未配置不
签名保持兼容) + HTTP 5xx 纳入重试 (对齐 channel_providers._post_with_retry)。
"""
import logging
import time
import httpx
from typing import Dict, Any, List
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.alarm import Alarm, AlarmLevel
from app.services.audit_service import audit_service
from app.services.channel_providers import im_sign

logger = logging.getLogger(__name__)

# IM卡片时间戳用的本地时区 (卡 a7bc9343): 旧 datetime.now().strftime() 是 naive,
# UTC 容器部署显示错误时间, 与通知静默/电价时区族同根。
_IM_TZ = ZoneInfo("Asia/Shanghai")

# 防御性加固 (卡 3bcec6d5): HTTP 请求超时 / 重试参数
_REQUEST_TIMEOUT = 10          # 单次请求超时 (秒)
_MAX_RETRIES = 3              # 最大尝试次数 (含首次)
_RETRY_BACKOFF_BASE = 0.5     # 指数退避基数 (秒): 0.5, 1, 2 ...

# 可重试的网络/传输类异常 (业务码错误 / HTTP 4xx 不重试)
_RETRYABLE_EXC = (httpx.TimeoutException, httpx.TransportError)


async def _retry_sleep(attempt: int) -> None:
    """重试退避: 指数退避 (attempt 从 1 起)。独立函数便于测试 patch, 不真睡。"""
    import asyncio
    await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))


def _now_ts() -> int:
    """当前秒级时间戳 (卡 9fbc00ce)。独立函数便于测试 patch 控制签名 ts。"""
    return int(time.time())


class IMNotifyService:
    """IM告警通知服务"""

    def __init__(self):
        # 从配置读取IM Webhook URL
        self.webhook_url = getattr(settings, 'IM_WEBHOOK_URL', None)
        # IM开放平台应用凭证（可选，用于高级功能）
        self.app_id = getattr(settings, 'IM_APP_ID', None)
        self.app_secret = getattr(settings, 'IM_APP_SECRET', None)
        # 告警通知用户 Open ID（可选）
        self.notify_user_id = getattr(settings, 'IM_NOTIFY_USER_ID', None)
        # 自定义机器人签名密钥 (可选, 卡 9fbc00ce): 机器人开启「签名校验」后
        # body 必须带 timestamp+sign; None = 不签名 (历史行为完全兼容)
        self.secret = getattr(settings, 'IM_SECRET', None)

    def _build_signed_payload(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """构造发送 body (卡 9fbc00ce): 拷贝 content 后按需附加IM签名字段。

        配置 self.secret (IM_SECRET) 时附加 timestamp+sign, 算法复用
        channel_providers.im_sign (base64(hmac_sha256(key=f"{ts}\\n{secret}")))
        对齐官方自定义机器人签名校验; 未配置原样返回。不 mutate 调用方 content。"""
        payload = dict(content or {})
        secret = getattr(self, "secret", None)
        if secret:
            ts = _now_ts()
            payload["timestamp"] = str(ts)
            payload["sign"] = im_sign(ts, secret)
        return payload

    async def send_webhook_message(self, content: Dict[str, Any]) -> bool:
        """
        通过IM自定义机器人 Webhook 发送消息
        文档: https://open.im.cn/document/client-docs/bot-v3/add-custom-bot

        防御性加固 (卡 3bcec6d5):
          - 每次请求显式 timeout (10s)
          - 网络/超时/SSL 异常重试 (max 3, 指数退避); 业务码错误与 HTTP 4xx 不重试
          - 区分超时 / 连接错误 / SSL, 分类记录日志
          - IM返回非 JSON 时安全降级 (网关错误页等)
          - code/StatusCode != 0 显式记录错误码, 不静默忽略

        卡 9fbc00ce:
          - 配置 IM_SECRET 时 body 附加 timestamp+sign (每 attempt 重算,
            重试不携带冻结 ts; 未配置不附加保持完全兼容)
          - HTTP 5xx 纳入重试 (对齐 channel_providers._post_with_retry;
            4xx/业务码错误仍不重试)
        """
        if not self.webhook_url:
            logger.warning("IM_WEBHOOK_URL 未配置，跳过IM通知")
            return False

        last_exc: Exception = None
        for attempt in range(1, _MAX_RETRIES + 1):
            payload = self._build_signed_payload(content)  # 每 attempt 重算签名
            try:
                async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=_REQUEST_TIMEOUT,
                    )
                if response.status_code < 500:
                    return self._interpret_response(response)
                # 5xx 纳入重试 (卡 9fbc00ce, 对齐 _post_with_retry 语义)
                last_exc = RuntimeError(f"http {response.status_code}")
                logger.warning(
                    "IM通知 HTTP 5xx (第 %d/%d 次): HTTP %d",
                    attempt, _MAX_RETRIES, response.status_code,
                )
                if attempt < _MAX_RETRIES:
                    await _retry_sleep(attempt)
                continue
            except httpx.TimeoutException as e:
                last_exc = e
                logger.warning("IM通知请求超时 (第 %d/%d 次): %s", attempt, _MAX_RETRIES, e)
            except httpx.ConnectError as e:
                last_exc = e
                # SSL 握手失败在 httpx 0.28 被包装进 ConnectError, 单独标记
                msg = str(e)
                if "ssl" in msg.lower() or "certificate" in msg.lower():
                    logger.warning("IM通知 SSL 错误 (第 %d/%d 次): %s", attempt, _MAX_RETRIES, msg)
                else:
                    logger.warning("IM通知连接错误 (第 %d/%d 次): %s", attempt, _MAX_RETRIES, msg)
            except httpx.HTTPError as e:
                # 其他 HTTP 协议级异常: 与可重试集合取交集, 命中则重试
                last_exc = e
                logger.warning("IM通知 HTTP 异常 (第 %d/%d 次): %s", attempt, _MAX_RETRIES, e)
                if not isinstance(e, _RETRYABLE_EXC):
                    logger.error("IM通知不可重试异常, 终止: %s", e)
                    return False

            # 未耗尽重试次数 → 退避后重试
            if attempt < _MAX_RETRIES and isinstance(last_exc, _RETRYABLE_EXC):
                await _retry_sleep(attempt)

        logger.error("IM通知重试耗尽, 放弃: %s", last_exc)
        return False

    @staticmethod
    def _interpret_response(response) -> bool:
        """解析IM响应: HTTP 状态码 + 业务 code/StatusCode + JSON 反序列化防护。"""
        if response.status_code != 200:
            logger.error("IM Webhook 请求失败: HTTP %d", response.status_code)
            return False

        # JSON 反序列化防护: 网关错误页等非 JSON body 不能让通知进程崩溃
        try:
            result = response.json()
        except (ValueError, TypeError) as e:
            logger.error("IM响应非 JSON, 解析失败: %s", e)
            return False

        if not isinstance(result, dict):
            logger.error("IM响应结构异常 (非对象): %r", result)
            return False

        code = result.get("code")
        status_code = result.get("StatusCode")
        # code==0 (新版) 或 StatusCode==0 (旧版) 视为成功; 显式 None 也按失败处理
        if code == 0 or status_code == 0:
            logger.info("IM消息发送成功")
            return True

        # 业务码错误 (含限流/鉴权失败): 显式记录错误码, 不静默
        logger.error(
            "IM消息发送失败 code=%s StatusCode=%s msg=%s",
            code, status_code, result.get("msg"),
        )
        return False

    @staticmethod
    def _safe_format(template: str, *args, **kwargs) -> str:
        """模板渲染防护 (卡 3bcec6d5): 变量缺失/类型异常时降级为字符串,
        不让单条非字符串字段 (None/int) 抛 TypeError 中断整张卡片构建。"""
        try:
            return template.format(*args, **kwargs)
        except (KeyError, IndexError, ValueError, TypeError):
            # 渲染失败 → 回退到原始模板, 不崩
            logger.warning("模板渲染失败, 回退原文: %r", template)
            return template

    @staticmethod
    def _empty_card(title: str = "通知") -> Dict[str, Any]:
        """降级空卡片 (卡 28655f6c): format_* / _build_summary_card 异常时返回
        结构合法的IM卡片, 保证 send_webhook_message 能正常发送一条降级提示,
        而非因空 dict 让通知管线彻底失败。"""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "grey",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "⚠️ 告警内容格式化失败, 请检查原始数据"}},
                    {"tag": "note", "elements": [
                        {"tag": "plain_text",
                         "content": f"天链运维 v3 | {datetime.now(_IM_TZ).strftime('%Y-%m-%d %H:%M:%S')}"}
                    ]},
                ],
            },
        }

    def format_prometheus_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化 Prometheus/Alertmanager 告警为IM卡片消息

        异常加固 (卡 28655f6c): 畸形 alert (labels 非 dict / 不可迭代字段)
        让整张卡片构建失败 → 上层 notify 静默丢消息。整个函数体 try/except 兜底,
        异常时 logger.exception 并降级返回结构合法的空卡片, 不阻塞通知管线。
        """
        try:
            return self._format_prometheus_alert_impl(alert)
        except Exception:
            logger.exception("格式化 Prometheus 告警失败, 降级空卡片: %r", alert)
            return self._empty_card("告警格式化失败")

    def _format_prometheus_alert_impl(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """format_prometheus_alert 的实际实现 (无防御层, 由调用方兜底)。"""
        # 防御 (卡 3bcec6d5): alert 可能非 dict / labels 显式 None → 安全降级, 不抛
        alert = alert or {}
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        status = alert.get("status") or "firing"
        starts_at = alert.get("startsAt") or ""

        alertname = labels.get("alertname", "未知告警")
        severity = labels.get("severity", "info")
        instance = labels.get("instance", "N/A")
        job = labels.get("job", "")
        summary = annotations.get("summary", "")
        description = annotations.get("description", "")

        # 状态和级别映射
        is_firing = status == "firing"
        status_text = "🔥 告警触发" if is_firing else "✅ 已恢复"
        status_color = "red" if is_firing else "green"

        severity_emoji = {
            "critical": "🔴",
            "warning": "🟡",
            "info": "🔵"
        }.get(severity, "⚪")

        severity_text = {
            "critical": "严重",
            "warning": "警告",
            "info": "提示"
        }.get(severity, "未知")

        # 构建IM卡片消息
        card_content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{status_text}: {alertname}"
                    },
                    "template": status_color
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**级别**\n{severity_emoji} {severity_text}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**实例**\n{instance}"
                                }
                            }
                        ]
                    },
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**任务**\n{job or 'N/A'}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**时间**\n{starts_at[:19] if starts_at else 'N/A'}"
                                }
                            }
                        ]
                    }
                ]
            }
        }

        # 添加摘要和详情
        elements = card_content["card"]["elements"]
        if summary:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**摘要**\n{summary}"
                }
            })
        if description:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**详情**\n{description}"
                }
            })

        # 添加时间戳
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"天链运维 v3 | {datetime.now(_IM_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })

        return card_content

    def format_alarm_message(self, alarm: Alarm) -> Dict[str, Any]:
        """
        格式化系统内部告警为IM卡片消息

        异常加固 (卡 28655f6c): 残缺 alarm 对象 (属性缺失 / content 不可切片)
        会让卡片构建抛异常 → 上层 notify 静默失败。整个函数体 try/except 兜底,
        异常时 logger.exception 并降级返回空卡片, 不阻塞通知管线。
        """
        try:
            return self._format_alarm_message_impl(alarm)
        except Exception:
            logger.exception("格式化系统告警失败, 降级空卡片: %r", alarm)
            return self._empty_card("告警格式化失败")

    def _format_alarm_message_impl(self, alarm: Alarm) -> Dict[str, Any]:
        """format_alarm_message 的实际实现 (无防御层, 由调用方兜底)。"""
        level_emoji = {
            AlarmLevel.FATAL: "💀",
            AlarmLevel.CRITICAL: "🔴",
            AlarmLevel.WARNING: "🟡",
            AlarmLevel.INFO: "🔵"
        }.get(alarm.level, "⚪")

        level_text = {
            AlarmLevel.FATAL: "致命",
            AlarmLevel.CRITICAL: "严重",
            AlarmLevel.WARNING: "警告",
            AlarmLevel.INFO: "提示"
        }.get(alarm.level, "未知")

        level_color = {
            AlarmLevel.FATAL: "red",
            AlarmLevel.CRITICAL: "red",
            AlarmLevel.WARNING: "yellow",
            AlarmLevel.INFO: "blue"
        }.get(alarm.level, "grey")

        card_content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🚨 天链告警: {alarm.content[:50]}"
                    },
                    "template": level_color
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**级别**\n{level_emoji} {level_text}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**设备ID**\n{alarm.device_id or 'N/A'}"
                                }
                            }
                        ]
                    }
                ]
            }
        }

        elements = card_content["card"]["elements"]

        # 添加详细内容
        detail_lines = [f"**内容**: {alarm.content}"]
        if alarm.fault_code:
            detail_lines.append(f"**故障码**: {alarm.fault_code}")
        if alarm.station_id:
            detail_lines.append(f"**站点ID**: {alarm.station_id}")

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(detail_lines)
            }
        })

        # 添加时间
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"时间: {alarm.created_at or datetime.now(timezone.utc)} | 天链运维 v3"
                }
            ]
        })

        return card_content

    async def notify_prometheus_alerts(
        self,
        status: str,
        alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        发送 Prometheus/Alertmanager 告警通知
        返回发送统计

        异常加固 (卡 28655f6c): format/send 任一抛非预期异常 (非 HTTP 类) 会中断
        循环, 后续告警丢失且审计日志缺失。每条 try/except 兜底, 单条失败计入
        failed, 审计日志放 finally 保证一定记录, 顶层再兜一次防异常逃逸。
        """
        if not self.webhook_url:
            return {"success": False, "error": "IM_WEBHOOK_URL 未配置"}

        results = {
            "total": len(alerts),
            "sent": 0,
            "failed": 0,
            "errors": []
        }

        # 按严重级别分组发送 (a.get 可能抛 → 整体兜底)
        try:
            critical_alerts = [a for a in alerts if a.get("labels", {}).get("severity") == "critical"]
            warning_alerts = [a for a in alerts if a.get("labels", {}).get("severity") == "warning"]
            info_alerts = [a for a in alerts if a.get("labels", {}).get("severity") not in ["critical", "warning"]]

            # 严重告警 - 立即逐条发送
            for alert in critical_alerts:
                try:
                    card = self.format_prometheus_alert(alert)
                    if await self.send_webhook_message(card):
                        results["sent"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"Failed to send critical alert: {alert.get('labels', {}).get('alertname')}")
                except Exception:
                    logger.exception("发送 critical 告警异常, 跳过: %r", alert)
                    results["failed"] += 1
                    results["errors"].append("Exception sending critical alert")

            # 警告/提示 - 合并为一条消息发送（避免刷屏）
            if warning_alerts or info_alerts:
                try:
                    summary_card = self._build_summary_card(status, warning_alerts, info_alerts)
                    if await self.send_webhook_message(summary_card):
                        results["sent"] += len(warning_alerts) + len(info_alerts)
                    else:
                        results["failed"] += len(warning_alerts) + len(info_alerts)
                        results["errors"].append("Failed to send summary message")
                except Exception:
                    logger.exception("发送告警汇总消息异常, 跳过")
                    results["failed"] += len(warning_alerts) + len(info_alerts)
                    results["errors"].append("Exception sending summary message")
        except Exception:
            # 分组阶段 (a.get 抛等) 兜底, 不让异常逃逸
            logger.exception("Prometheus 告警分组/处理异常, 降级返回统计")

        # 记录审计日志 (finally 语义: 无论上面成败都记录, 不丢审计)
        try:
            audit_service.log_crud(
                0, "system", "notify", "im",
                "prometheus_alerts",
                f"sent={results['sent']}, failed={results['failed']}"
            )
        except Exception:
            logger.exception("记录IM通知审计日志失败")

        return results

    def _build_summary_card(
        self,
        status: str,
        warning_alerts: List[Dict[str, Any]],
        info_alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建告警汇总卡片

        异常加固 (卡 28655f6c): 畸形 alert 元素 (非 dict / __bool__ 抛) 让循环体
        抛异常 → 汇总卡片构建中断。整个函数体 try/except 兜底, 异常时
        logger.exception 并降级返回空卡片, 不阻塞通知管线。
        """
        try:
            return self._build_summary_card_impl(status, warning_alerts, info_alerts)
        except Exception:
            logger.exception("构建告警汇总卡片失败, 降级空卡片")
            return self._empty_card("告警汇总格式化失败")

    def _build_summary_card_impl(
        self,
        status: str,
        warning_alerts: List[Dict[str, Any]],
        info_alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """_build_summary_card 的实际实现 (无防御层, 由调用方兜底)。"""
        status_text = "🔥 告警触发" if status == "firing" else "✅ 已恢复"

        elements = []

        # 警告列表
        if warning_alerts:
            warning_lines = []
            for a in warning_alerts[:5]:  # 最多5条
                labels = (a or {}).get("labels") or {}
                name = labels.get("alertname", "未知")
                instance = labels.get("instance", "")
                warning_lines.append(f"🟡 {name} ({instance})")
            if len(warning_alerts) > 5:
                warning_lines.append(f"_... 还有 {len(warning_alerts) - 5} 条_")
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**警告 ({len(warning_alerts)}条)**\n" + "\n".join(warning_lines)
                }
            })

        # 提示列表
        if info_alerts:
            info_lines = []
            for a in info_alerts[:3]:  # 最多3条
                labels = (a or {}).get("labels") or {}
                name = labels.get("alertname", "未知")
                info_lines.append(f"🔵 {name}")
            if len(info_alerts) > 3:
                info_lines.append(f"_... 还有 {len(info_alerts) - 3} 条_")
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**提示 ({len(info_alerts)}条)**\n" + "\n".join(info_lines)
                }
            })

        # 时间戳
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"天链运维 v3 | {datetime.now(_IM_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{status_text}: 告警汇总"
                    },
                    "template": "blue" if status == "resolved" else "yellow"
                },
                "elements": elements
            }
        }

    async def notify_system_alarm(self, alarm: Alarm) -> bool:
        """
        发送系统内部告警通知
        """
        if not self.webhook_url:
            logger.warning("IM_WEBHOOK_URL 未配置，跳过IM通知")
            return False

        card = self.format_alarm_message(alarm)
        return await self.send_webhook_message(card)

    def dispatch_alarm_notification(self, alarm: Alarm, db: Session = None) -> bool:
        """
        同步分发告警通知（用于后台任务）
        """
        if db is None:
            db = SessionLocal()
            should_close = True
        else:
            should_close = False

        try:
            # 只通知严重及以上级别
            if alarm.level in [AlarmLevel.FATAL, AlarmLevel.CRITICAL, AlarmLevel.WARNING]:
                return self._run_coro_sync(self.notify_system_alarm(alarm))
            return True
        except Exception as e:
            logger.error("IM告警通知失败: %s", e)
            return False
        finally:
            if should_close:
                db.close()

    @staticmethod
    def _run_coro_sync(coro):
        """同步执行协程, 不污染线程全局事件循环 (卡 a7bc9343)。

        旧实现 asyncio.new_event_loop()+asyncio.set_event_loop()+run_until_complete 有两处问题:
          1. set_event_loop 把线程当前 loop 覆盖成新建 loop, close 后留指向已关闭 loop
             的悬垂引用 (后续 asyncio.get_event_loop() 取到 closed loop);
          2. 在已有运行循环的线程里 (FastAPI async worker) run_until_complete 直接抛
             "Cannot run the event loop while another loop is running" → 通知静默失败。

        - 无运行循环 (后台任务线程): asyncio.run 自动建/清理, 收尾 set_event_loop(None),
          不留悬垂 closed loop;
        - 已有运行循环 (async worker): 本线程既不能 run_until_complete 也不能 asyncio.run,
          放到独立线程跑 (该线程无运行循环, asyncio.run 安全), 主线程 loop 不受影响。
        """
        import asyncio
        import concurrent.futures
        try:
            asyncio.get_running_loop()
            in_running_loop = True
        except RuntimeError:
            in_running_loop = False
        if in_running_loop:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, coro).result()
        return asyncio.run(coro)


# 单例
im_notify_service = IMNotifyService()
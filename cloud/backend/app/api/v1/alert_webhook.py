"""
Alertmanager webhook 接收端点
Phase19: 将 Prometheus 告警转发至IM
"""
from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any
import hmac
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.services.im_notify import im_notify_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_webhook_secret(request: Request) -> None:
    """校验 Alertmanager webhook 共享密钥 (da16d511 安全加固)。

    优先读请求头 ``X-Webhook-Secret``，其次 query ``?secret=``。
    - secret 未配置(None/空)：拒绝所有请求并 warning，强制生产配置，
      杜绝任何人 POST 伪造 critical 告警刷屏IM（通知通道 DoS）。
    - 用 hmac.compare_digest 做常数时间比较，抗时序侧信道。
    """
    expected = (settings.ALERT_WEBHOOK_SECRET or "").strip()
    if not expected:
        logger.warning(
            "ALERT_WEBHOOK_SECRET 未配置，/alert-webhook 拒绝所有请求 "
            "（防止伪造告警刷屏IM）。请在 .env 配置 ALERT_WEBHOOK_SECRET。"
        )
        raise HTTPException(status_code=403, detail="Webhook secret not configured")
    provided = request.headers.get("X-Webhook-Secret") or request.query_params.get("secret") or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


class AlertManagerWebhook:
    """Alertmanager webhook payload 结构"""

    @staticmethod
    def format_alert(alert: Dict[str, Any]) -> str:
        """格式化单条告警为消息文本"""
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        status = alert.get("status", "firing")

        alertname = labels.get("alertname", "未知告警")
        severity = labels.get("severity", "unknown")
        instance = labels.get("instance", "N/A")
        summary = annotations.get("summary", "")
        description = annotations.get("description", "")

        emoji_map = {
            "critical": "🔴",
            "warning": "🟡",
            "info": "🔵",
        }
        status_emoji = "🔥" if status == "firing" else "✅"
        severity_emoji = emoji_map.get(severity, "⚪")

        lines = [
            f"{status_emoji} {severity_emoji} **{alertname}** (severity={severity})",
            f"📌 实例: {instance}",
        ]
        if summary:
            lines.append(f"📋 摘要: {summary}")
        if description:
            lines.append(f"📝 详情: {description}")

        return "\n".join(lines)

    @staticmethod
    def format_resolved(alert: Dict[str, Any]) -> str:
        """格式化已恢复告警"""
        labels = alert.get("labels", {})
        alertname = labels.get("alertname", "未知告警")
        severity = labels.get("severity", "unknown")
        return f"✅ 已恢复: [{severity}] {alertname}"


@router.post("/alert-webhook")
async def alertmanager_webhook(request: Request):
    """
    Alertmanager webhook 接收端点
    Prometheus → Alertmanager → 此端点 → IM/日志
    """
    # 安全门：先校验共享密钥，未授权请求不进入任何业务处理
    _verify_webhook_secret(request)

    try:
        body = await request.json()
    except Exception as e:
        logger.error("解析 Alertmanager webhook 失败: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    alerts = body.get("alerts", [])
    status = body.get("status", "unknown")
    num_alerts = len(alerts)

    logger.info("收到 Alertmanager webhook: status=%s, alerts=%d", status, num_alerts)

    if not alerts:
        return {"ok": True, "message": "无告警"}

    # 按严重级别分组
    critical_alerts = []
    warning_alerts = []
    info_alerts = []

    for alert in alerts:
        severity = alert.get("labels", {}).get("severity", "info")
        target = (
            critical_alerts if severity == "critical"
            else warning_alerts if severity == "warning"
            else info_alerts
        )
        target.append(alert)

    messages = []

    # 严重告警
    if critical_alerts:
        msg_parts = [f"🔴 **{len(critical_alerts)} 条严重告警**"]
        for a in critical_alerts:
            msg_parts.append(AlertManagerWebhook.format_alert(a))
        messages.append("\n\n".join(msg_parts))

    # 警告
    if warning_alerts:
        msg_parts = [f"🟡 **{len(warning_alerts)} 条警告**"]
        for a in warning_alerts:
            msg_parts.append(AlertManagerWebhook.format_alert(a))
        messages.append("\n\n".join(msg_parts))

    # 提示
    if info_alerts:
        msg_parts = [f"🔵 **{len(info_alerts)} 条提示**"]
        for a in info_alerts:
            msg_parts.append(AlertManagerWebhook.format_alert(a))
        messages.append("\n\n".join(msg_parts))

    # Phase19: 通过IM服务发送告警通知
    notify_result = await im_notify_service.notify_prometheus_alerts(status, alerts)

    # 同时写入日志（保留历史记录）
    for msg in messages:
        logger.info("[AlertNotify] %s", msg)

    return {
        "ok": True,
        "message": f"已接收 {len(alerts)} 条告警",
        "groups": {
            "critical": len(critical_alerts),
            "warning": len(warning_alerts),
            "info": len(info_alerts),
        },
        "im_notify": notify_result,
    }


@router.get("/alert-webhook/health")
async def webhook_health():
    """Webhook 健康检查"""
    return {
        "status": "running",
        "version": "1.0",
        "capabilities": ["alertmanager", "prometheus"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

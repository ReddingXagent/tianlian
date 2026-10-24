# -*- coding: utf-8 -*-
"""
IM通知服务异常路径加固测试 (卡 28655f6c)

被测: app/services/im_notify.py 的 4 个关键函数在异常下不抛、降级返回:
  - format_prometheus_alert  → 降级返回空安全卡片 (msg_type=interactive 结构)
  - format_alarm_message     → 降级返回空安全卡片
  - notify_prometheus_alerts → 降级返回统计 dict (含 errors), 不抛、不丢审计
  - _build_summary_card      → 降级返回空安全卡片

设计原则:
  - 用抛异常的 property / 非 dict labels 模拟畸形输入, 强制被测函数抛
  - patch logger.exception 验证异常被记录 (任务卡硬性要求 logger.exception)
  - 不改动既有 test_im_notify*.py, 仅新增本文件
  - audit_service mock 避免写库
"""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.services import im_notify as im_mod
from app.services.im_notify import IMNotifyService
from app.models.alarm import Alarm, AlarmLevel


# ═══════════════════════════════════════════════════════════════
# Fixture / 辅助
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def mock_audit():
    with patch("app.services.im_notify.audit_service") as m:
        yield m


def _configured_service():
    svc = IMNotifyService()
    svc.webhook_url = "https://open.im.cn/open-apis/bot/v2/hook/fake"
    return svc


class _ExplodingAlarm:
    """模拟残缺/损坏的 Alarm 对象: 任意属性访问抛异常 (DB 反序列化损坏等场景)。"""

    level = AlarmLevel.WARNING

    def __getattr__(self, item):
        raise AttributeError(f"corrupted alarm: missing {item}")


# ═══════════════════════════════════════════════════════════════
# 1. format_prometheus_alert: 异常 → 降级空卡片 + logger.exception
# ═══════════════════════════════════════════════════════════════
def test_format_prometheus_alert_degrades_on_exception():
    svc = IMNotifyService()

    # labels 是非 dict (list) → 内部 .get 抛 AttributeError, 触发降级
    bomb = {"labels": ["not", "a", "dict"], "annotations": {}, "startsAt": ""}

    with patch.object(im_mod.logger, "exception") as mock_exc:
        card = svc.format_prometheus_alert(bomb)

    # 降级: 返回结构合法的空卡片, 不抛
    assert isinstance(card, dict)
    assert card.get("msg_type") == "interactive"
    # 异常必须被 logger.exception 记录 (任务卡硬性要求)
    assert mock_exc.called


# ═══════════════════════════════════════════════════════════════
# 2. format_alarm_message: 异常 → 降级空卡片 + logger.exception
# ═══════════════════════════════════════════════════════════════
def test_format_alarm_message_degrades_on_exception():
    svc = IMNotifyService()

    with patch.object(im_mod.logger, "exception") as mock_exc:
        # 残缺 alarm: content 访问即抛
        card = svc.format_alarm_message(_ExplodingAlarm())

    assert isinstance(card, dict)
    assert card.get("msg_type") == "interactive"
    assert mock_exc.called


# ═══════════════════════════════════════════════════════════════
# 3. notify_prometheus_alerts: 内部 format 抛 → 不中断, 降级返回统计
# ═══════════════════════════════════════════════════════════════
async def test_notify_prometheus_alerts_degrades_on_format_exception(mock_audit):
    svc = _configured_service()

    # format_prometheus_alert 抛异常 → notify 须降级, 不让异常逃逸
    with patch.object(svc, "format_prometheus_alert", side_effect=RuntimeError("format boom")), \
         patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=True)):
        with patch.object(im_mod.logger, "exception") as mock_exc:
            result = await svc.notify_prometheus_alerts("firing", [
                {"labels": {"severity": "critical", "alertname": "A"}},
            ])

    assert isinstance(result, dict)
    assert "total" in result
    # 异常被记录, 审计仍执行 (不丢日志)
    assert mock_exc.called
    mock_audit.log_crud.assert_called_once()


async def test_notify_prometheus_alerts_degrades_on_send_exception(mock_audit):
    """send_webhook_message 自身已吞 HTTP 异常返回 False, 但若它抛非 HTTP 异常
    (如 RuntimeError), notify 顶层兜底, 单条失败计数, 不中断后续。"""
    svc = _configured_service()

    with patch.object(svc, "send_webhook_message",
                      new=AsyncMock(side_effect=RuntimeError("unexpected"))):
        with patch.object(im_mod.logger, "exception"):
            result = await svc.notify_prometheus_alerts("firing", [
                {"labels": {"severity": "critical", "alertname": "A"}},
            ])

    # 降级返回统计, 该条计入 failed
    assert isinstance(result, dict)
    assert result["failed"] >= 1


# ═══════════════════════════════════════════════════════════════
# 4. _build_summary_card: 畸形 alert 元素 → 降级空卡片 + logger.exception
# ═══════════════════════════════════════════════════════════════
def test_build_summary_card_degrades_on_exception():
    svc = IMNotifyService()

    # 构造能让循环体抛异常的输入: warning_alerts 含一个 .get 会抛的对象
    # (a or {}).get 在 a 为自定义抛异常 __bool__ 时触发)
    class _TruthyBomb:
        def __bool__(self):
            raise RuntimeError("bool bomb")

    with patch.object(im_mod.logger, "exception") as mock_exc:
        card = svc._build_summary_card("firing", [_TruthyBomb()], [])

    assert isinstance(card, dict)
    assert card.get("msg_type") == "interactive"
    assert mock_exc.called

# -*- coding: utf-8 -*-
"""
IM告警通知服务测试 - 覆盖率补强 ≥70%

被测: app/services/im_notify.py (IMNotifyService + 全局单例 im_notify_service)
设计:
  - 外部 HTTP 全部 mock: patch httpx.AsyncClient, 隔离真实网络请求
  - audit_service.log_crud mock, 避免写库依赖
  - send_webhook_message / notify_prometheus_alerts / notify_system_alarm 内部调用
    用 patch.object 替换为 AsyncMock 精确控制成功/失败/异常
  - format_* / _build_summary_card 为纯函数, 直接断言产物结构
  - dispatch_alarm_notification 同步入口走新 event loop, 用轻量 MagicMock 替换
    模块 SessionLocal 覆盖 db=None 路径 (不依赖 test_db, 避免按值绑定坑)

覆盖:
- __init__                  读取4项IM配置
- send_webhook_message      未配置 / 200+code=0 / 200+StatusCode=0 / 业务失败 /
                            HTTP错误码 / 网络异常
- format_prometheus_alert   firing critical(含summary+description) / resolved / info /
                            unknown severity / 空字段(N/A)
- format_alarm_message      warning(含fault_code+station_id) / 各级别颜色映射 /
                            长内容截断title / 无fault无station / created_at=None回退
- notify_prometheus_alerts  未配置 / 全critical逐条 / warning+info合并 / 发送失败 /
                            混合+审计日志
- _build_summary_card       warning>5截断 / info>3截断 / firing黄 / resolved蓝 / 空
- notify_system_alarm       未配置 / 成功
- dispatch_alarm_notification warning通知 / fatal+critical通知 / info跳过 /
                            db=None关闭session / 异常返回False / 传入db不关闭
"""
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

import httpx
import pytest

from app.services import im_notify as im_mod
from app.services.im_notify import IMNotifyService, im_notify_service
from app.models.alarm import Alarm, AlarmLevel


# ═══════════════════════════════════════════════════════════════
# Fixture / 辅助
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def mock_httpx():
    """patch httpx.AsyncClient; 测试内通过 client.post.return_value / .side_effect 配置响应。"""
    client = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.services.im_notify.httpx.AsyncClient", return_value=cm):
        yield client


@pytest.fixture
def mock_audit():
    """patch audit_service, 避免写库。"""
    with patch("app.services.im_notify.audit_service") as m:
        yield m


def _resp(status_code=200, payload=None):
    """构造 httpx 响应 mock。"""
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = payload if payload is not None else {"code": 0}
    return r


def _configured_service():
    """返回一个已配置 webhook_url 的服务实例。"""
    svc = IMNotifyService()
    svc.webhook_url = "https://open.im.cn/open-apis/bot/v2/hook/fake"
    return svc


def _alarm(**overrides):
    """构造内存 Alarm 对象 (不落库, 避免 FK 约束)。"""
    defaults = dict(
        device_id=1,
        station_id=10,
        level=AlarmLevel.WARNING,
        content="测试告警内容",
        fault_code="0x0102",
        created_at=datetime(2026, 8, 2, 10, 0, 0),
    )
    defaults.update(overrides)
    return Alarm(**defaults)


# ═══════════════════════════════════════════════════════════════
# __init__ smoke
# ═══════════════════════════════════════════════════════════════
def test_init_reads_config_attributes():
    svc = IMNotifyService()
    # 4 项配置属性均被读取 (值由 settings 决定, 此处仅验证属性存在)
    for attr in ("webhook_url", "app_id", "app_secret", "notify_user_id"):
        assert hasattr(svc, attr)


def test_singleton_instance():
    assert isinstance(im_notify_service, IMNotifyService)


# ═══════════════════════════════════════════════════════════════
# send_webhook_message
# ═══════════════════════════════════════════════════════════════
async def test_send_webhook_unconfigured_returns_false():
    svc = IMNotifyService()
    svc.webhook_url = None
    assert await svc.send_webhook_message({"msg_type": "text"}) is False


async def test_send_webhook_success_code_zero(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(200, {"code": 0, "msg": "ok"})
    assert await svc.send_webhook_message({"msg_type": "text"}) is True
    mock_httpx.post.assert_awaited_once()


async def test_send_webhook_success_legacy_status_code_field(mock_httpx):
    # 旧版IM返回 StatusCode
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(200, {"StatusCode": 0})
    assert await svc.send_webhook_message({"msg_type": "text"}) is True


async def test_send_webhook_business_failure_returns_false(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(200, {"code": 19021, "msg": "rate limited"})
    assert await svc.send_webhook_message({"msg_type": "text"}) is False


async def test_send_webhook_http_error_status_returns_false(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(500, {})
    assert await svc.send_webhook_message({"msg_type": "text"}) is False


async def test_send_webhook_network_exception_returns_false(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.side_effect = httpx.ConnectError("connection refused")
    assert await svc.send_webhook_message({"msg_type": "text"}) is False


# ═══════════════════════════════════════════════════════════════
# format_prometheus_alert
# ═══════════════════════════════════════════════════════════════
def test_format_prometheus_alert_firing_critical_with_summary_desc():
    svc = IMNotifyService()
    alert = {
        "status": "firing",
        "labels": {"alertname": "HighCPU", "severity": "critical",
                   "instance": "node1:9100", "job": "node"},
        "annotations": {"summary": "CPU > 90%", "description": "CPU sustained high"},
        "startsAt": "2026-08-02T10:00:00Z",
    }
    card = svc.format_prometheus_alert(alert)
    assert card["msg_type"] == "interactive"
    header = card["card"]["header"]
    assert "告警触发" in header["title"]["content"]
    assert "HighCPU" in header["title"]["content"]
    assert header["template"] == "red"  # firing → red
    elements_str = str(card["card"]["elements"])
    assert "摘要" in elements_str
    assert "详情" in elements_str
    assert "node1:9100" in elements_str


def test_format_prometheus_alert_resolved_green():
    svc = IMNotifyService()
    alert = {"status": "resolved",
             "labels": {"alertname": "DiskFull", "severity": "warning"},
             "annotations": {}, "startsAt": ""}
    card = svc.format_prometheus_alert(alert)
    header = card["card"]["header"]
    assert "已恢复" in header["title"]["content"]
    assert header["template"] == "green"  # resolved → green
    # startsAt 空 → 时间显示 N/A; 无 summary/description 不追加对应 div
    elements_str = str(card["card"]["elements"])
    assert "N/A" in elements_str
    assert "摘要" not in elements_str


def test_format_prometheus_alert_info_and_unknown_severity():
    svc = IMNotifyService()
    # info severity → 蓝色 emoji
    card_info = svc.format_prometheus_alert(
        {"status": "firing", "labels": {"severity": "info"}, "annotations": {}, "startsAt": ""})
    assert "🔵" in str(card_info["card"]["elements"])
    # 未知 severity → 默认 emoji/text
    card_unk = svc.format_prometheus_alert(
        {"status": "firing", "labels": {"severity": "weird"}, "annotations": {}, "startsAt": ""})
    assert "未知" in str(card_unk["card"]["elements"])


# ═══════════════════════════════════════════════════════════════
# format_alarm_message
# ═══════════════════════════════════════════════════════════════
def test_format_alarm_message_warning_with_fault_and_station():
    svc = IMNotifyService()
    alarm = _alarm(level=AlarmLevel.WARNING, content="电池温度过高",
                   fault_code="0x0102", station_id=5, device_id=42)
    card = svc.format_alarm_message(alarm)
    assert card["msg_type"] == "interactive"
    header = card["card"]["header"]
    assert "天链告警" in header["title"]["content"]
    assert header["template"] == "yellow"  # warning → yellow
    elements_str = str(card["card"]["elements"])
    assert "故障码" in elements_str
    assert "站点ID" in elements_str
    assert "电池温度过高" in elements_str
    assert "42" in elements_str  # device_id


@pytest.mark.parametrize("level,color", [
    (AlarmLevel.FATAL, "red"),
    (AlarmLevel.CRITICAL, "red"),
    (AlarmLevel.WARNING, "yellow"),
    (AlarmLevel.INFO, "blue"),
])
def test_format_alarm_message_level_color_mapping(level, color):
    svc = IMNotifyService()
    card = svc.format_alarm_message(_alarm(level=level, content="x"))
    assert card["card"]["header"]["template"] == color


def test_format_alarm_message_long_content_truncated_in_title():
    svc = IMNotifyService()
    long_content = "A" * 200
    card = svc.format_alarm_message(_alarm(content=long_content))
    title = card["card"]["header"]["title"]["content"]
    # title = "🚨 天链告警: " + content[:50]
    assert len(title) <= 60
    # 详情区保留完整内容
    assert long_content in str(card["card"]["elements"])


def test_format_alarm_message_no_fault_no_station_and_null_created_at():
    svc = IMNotifyService()
    alarm = _alarm(content="简单告警", fault_code=None, station_id=None,
                   device_id=7, created_at=None)
    card = svc.format_alarm_message(alarm)
    elements_str = str(card["card"]["elements"])
    assert "故障码" not in elements_str
    assert "站点ID" not in elements_str
    # created_at None → 回退 datetime.now() 不报错, note 元素仍生成
    assert "天链运维 v3" in elements_str


# ═══════════════════════════════════════════════════════════════
# notify_prometheus_alerts
# ═══════════════════════════════════════════════════════════════
async def test_notify_prometheus_unconfigured_returns_error():
    svc = IMNotifyService()
    svc.webhook_url = None
    result = await svc.notify_prometheus_alerts("firing", [])
    assert result == {"success": False, "error": "IM_WEBHOOK_URL 未配置"}


async def test_notify_prometheus_all_critical_sent_individually(mock_audit):
    svc = _configured_service()
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=True)) as m:
        alerts = [
            {"labels": {"severity": "critical", "alertname": "A"}},
            {"labels": {"severity": "critical", "alertname": "B"}},
        ]
        result = await svc.notify_prometheus_alerts("firing", alerts)
    assert result["total"] == 2
    assert result["sent"] == 2
    assert result["failed"] == 0
    assert m.await_count == 2  # critical 逐条发送


async def test_notify_prometheus_warning_info_merged_into_one(mock_audit):
    svc = _configured_service()
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=True)) as m:
        alerts = [
            {"labels": {"severity": "warning", "alertname": "W1"}},
            {"labels": {"severity": "info", "alertname": "I1"}},
        ]
        result = await svc.notify_prometheus_alerts("firing", alerts)
    assert result["sent"] == 2
    assert result["failed"] == 0
    # warning + info 合并为一条汇总消息
    assert m.await_count == 1


async def test_notify_prometheus_send_failure_counted(mock_audit):
    svc = _configured_service()
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=False)):
        alerts = [{"labels": {"severity": "critical", "alertname": "A"}}]
        result = await svc.notify_prometheus_alerts("firing", alerts)
    assert result["sent"] == 0
    assert result["failed"] == 1
    assert result["errors"]  # 记录错误详情


async def test_notify_prometheus_summary_send_failure(mock_audit):
    svc = _configured_service()
    # warning+info 合并为一条汇总消息, 发送失败 → failed 累加 + 记录 summary 错误
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=False)):
        alerts = [
            {"labels": {"severity": "warning", "alertname": "W"}},
            {"labels": {"severity": "info", "alertname": "I"}},
        ]
        result = await svc.notify_prometheus_alerts("firing", alerts)
    assert result["sent"] == 0
    assert result["failed"] == 2  # warning + info
    assert "Failed to send summary message" in result["errors"]


async def test_notify_prometheus_mixed_and_audit_logged(mock_audit):
    svc = _configured_service()
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=True)):
        alerts = [
            {"labels": {"severity": "critical", "alertname": "C"}},
            {"labels": {"severity": "warning", "alertname": "W"}},
            {"labels": {"severity": "info", "alertname": "I"}},
        ]
        result = await svc.notify_prometheus_alerts("firing", alerts)
    assert result["sent"] == 3
    # critical 1 条 + 汇总 1 条 = 2 次发送
    mock_audit.log_crud.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# _build_summary_card
# ═══════════════════════════════════════════════════════════════
def test_build_summary_card_truncates_overflow():
    svc = IMNotifyService()
    warnings = [{"labels": {"alertname": f"W{i}", "instance": f"n{i}"}} for i in range(7)]
    infos = [{"labels": {"alertname": f"I{i}"}} for i in range(5)]
    card = svc._build_summary_card("firing", warnings, infos)
    elements_str = str(card["card"]["elements"])
    assert "还有 2 条" in elements_str  # warning 7-5=2, info 5-3=2
    assert "警告 (7条)" in elements_str
    assert "提示 (5条)" in elements_str


def test_build_summary_card_resolved_blue_and_empty():
    svc = IMNotifyService()
    card = svc._build_summary_card("resolved", [], [])
    assert card["card"]["header"]["template"] == "blue"
    # 无 warning/info, 仅时间戳 note
    assert len(card["card"]["elements"]) == 1


def test_build_summary_card_firing_yellow():
    svc = IMNotifyService()
    card = svc._build_summary_card("firing", [], [])
    assert card["card"]["header"]["template"] == "yellow"


# ═══════════════════════════════════════════════════════════════
# notify_system_alarm
# ═══════════════════════════════════════════════════════════════
async def test_notify_system_alarm_unconfigured_returns_false():
    svc = IMNotifyService()
    svc.webhook_url = None
    assert await svc.notify_system_alarm(_alarm()) is False


async def test_notify_system_alarm_success():
    svc = _configured_service()
    with patch.object(svc, "send_webhook_message", new=AsyncMock(return_value=True)) as m:
        assert await svc.notify_system_alarm(_alarm()) is True
    m.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# dispatch_alarm_notification
# ═══════════════════════════════════════════════════════════════
def test_dispatch_warning_notifies():
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)) as m:
        result = svc.dispatch_alarm_notification(_alarm(level=AlarmLevel.WARNING), db=MagicMock())
    assert result is True
    m.assert_awaited_once()


@pytest.mark.parametrize("level", [AlarmLevel.FATAL, AlarmLevel.CRITICAL])
def test_dispatch_fatal_critical_notifies(level):
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)) as m:
        result = svc.dispatch_alarm_notification(_alarm(level=level), db=MagicMock())
    assert result is True
    m.assert_awaited_once()


def test_dispatch_info_level_skips_notification():
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)) as m:
        result = svc.dispatch_alarm_notification(_alarm(level=AlarmLevel.INFO), db=MagicMock())
    assert result is True  # 低于 WARNING 直接返回 True
    m.assert_not_called()


def test_dispatch_default_db_path_closes_session(monkeypatch):
    # db=None → 内部 SessionLocal() 创建 session, finally should_close 关闭
    mock_session = MagicMock()
    fake_local = MagicMock(return_value=mock_session)
    monkeypatch.setattr(im_mod, "SessionLocal", fake_local)
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)):
        result = svc.dispatch_alarm_notification(_alarm(level=AlarmLevel.WARNING))
    assert result is True
    fake_local.assert_called_once()
    mock_session.close.assert_called_once()  # finally 关闭


def test_dispatch_passed_db_not_closed():
    svc = _configured_service()
    db = MagicMock()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)):
        svc.dispatch_alarm_notification(_alarm(level=AlarmLevel.WARNING), db=db)
    db.close.assert_not_called()  # should_close=False


def test_dispatch_exception_returns_false():
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = svc.dispatch_alarm_notification(_alarm(level=AlarmLevel.WARNING), db=MagicMock())
    assert result is False


# ═══════════════════════════════════════════════════════════════
# 卡 a7bc9343: naive 时区 + 事件循环竞态修复
# ═══════════════════════════════════════════════════════════════
def test_format_timestamps_are_shanghai_aware(monkeypatch):
    """Bug2: format_prometheus_alert / _build_summary_card 末尾时间戳原为 naive
    datetime.now(), UTC 容器显示错时。注入固定 UTC 时刻, 验证按 +08:00 渲染。"""
    fixed_utc = datetime(2026, 8, 8, 6, 30, 0, tzinfo=timezone.utc)  # → 上海 14:30:00

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)

    monkeypatch.setattr(im_mod, "datetime", FakeDateTime)

    svc = IMNotifyService()
    # format_prometheus_alert 末尾 note 时间戳
    card = svc.format_prometheus_alert(
        {"status": "firing", "labels": {}, "annotations": {}, "startsAt": ""})
    assert "2026-08-08 14:30:00" in str(card["card"]["elements"])  # 非 UTC 06:30:00

    # _build_summary_card 末尾 note 时间戳
    card2 = svc._build_summary_card("firing", [], [])
    assert "2026-08-08 14:30:00" in str(card2["card"]["elements"])


async def test_dispatch_in_running_loop_still_notifies():
    """Bug3: 在已有运行循环中 (FastAPI async worker) 调用同步 dispatch 入口,
    旧实现 loop.run_until_complete 抛 'Cannot run the event loop while another
    loop is running' → 通知静默失败 (返回 False)。修复后须正常发出通知,
    且不污染主线程运行循环。"""
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)) as m:
        result = svc.dispatch_alarm_notification(
            _alarm(level=AlarmLevel.WARNING), db=MagicMock())
    assert result is True
    m.assert_awaited_once()
    # 主线程运行循环仍健康, 可继续调度 (未被新建/关闭的 loop 污染)
    await asyncio.sleep(0)


def test_dispatch_no_running_loop_leaves_clean_loop_state():
    """Bug3: 无运行循环 (后台任务线程) 走 asyncio.run, 收尾 set_event_loop(None),
    不残留指向已关闭 loop 的悬垂引用 (旧 new_event_loop+set_event_loop+close 会把
    线程当前 loop 污染成 closed loop)。"""
    svc = _configured_service()
    with patch.object(svc, "notify_system_alarm", new=AsyncMock(return_value=True)) as m:
        result = svc.dispatch_alarm_notification(
            _alarm(level=AlarmLevel.WARNING), db=MagicMock())
    assert result is True
    m.assert_awaited_once()
    # 旧实现遗留 closed loop 作为线程当前 loop → 取出后须未关闭
    policy = asyncio.get_event_loop_policy()
    try:
        loop = policy.get_event_loop()
    except RuntimeError:
        return  # 无当前 loop (asyncio.run 收尾 set(None)) → 干净, 通过
    assert not loop.is_closed(), "线程残留已关闭的事件循环 (污染)"

# -*- coding: utf-8 -*-
"""
IM通知服务防御性加固边界测试 (卡 3bcec6d5)

被测: app/services/im_notify.py
聚焦加固项:
  - HTTP 请求重试 (max 3, 指数退避) + timeout
  - IM业务错误码 (code/errno != 0) 显式失败, 不静默
  - 限流响应处理
  - 网络异常分类 (超时 / 连接错误 / SSL)
  - JSON 反序列化防护 (非 JSON 响应)
  - 消息模板渲染变量缺失安全降级

设计原则:
  - 复用 test_im_notify.py 的 mock_httpx 模式 (patch httpx.AsyncClient)
  - retry 的指数退避 sleep 全部 patch 为 no-op, 测试不真睡
  - 不改动 test_im_notify.py 既有断言, 仅新增本文件
"""
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
import pytest

from app.services import im_notify as im_mod
from app.services.im_notify import IMNotifyService


# ═══════════════════════════════════════════════════════════════
# Fixture / 辅助 (与 test_im_notify.py 一致)
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def mock_httpx():
    """patch httpx.AsyncClient; 测试内通过 client.post.return_value / .side_effect 配置。"""
    client = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.services.im_notify.httpx.AsyncClient", return_value=cm):
        yield client


@pytest.fixture(autouse=True)
def no_retry_sleep():
    """把重试退避 sleep patch 成 no-op, 避免测试真睡。"""
    with patch.object(im_mod, "_retry_sleep", new=AsyncMock(return_value=None)):
        yield


def _resp(status_code=200, payload=None, *, json_raises=False):
    """构造 httpx 响应 mock; json_raises=True 模拟非 JSON 响应。"""
    r = MagicMock()
    r.status_code = status_code
    if json_raises:
        r.json.side_effect = ValueError("not json")
        r.text = "<html>502 Bad Gateway</html>"
    else:
        r.json.return_value = payload if payload is not None else {"code": 0}
    return r


def _configured_service():
    svc = IMNotifyService()
    svc.webhook_url = "https://open.im.cn/open-apis/bot/v2/hook/fake"
    return svc


# ═══════════════════════════════════════════════════════════════
# 1. 超时重试: 前两次超时, 第三次成功 → 最终 True, 共调用 3 次
# ═══════════════════════════════════════════════════════════════
async def test_send_message_timeout_retry(mock_httpx):
    svc = _configured_service()
    ok = _resp(200, {"code": 0, "msg": "ok"})
    mock_httpx.post.side_effect = [
        httpx.ReadTimeout("read timeout"),
        httpx.ConnectTimeout("connect timeout"),
        ok,
    ]
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is True
    assert mock_httpx.post.await_count == 3  # 重试到第 3 次成功


# 超时: 3 次全部超时 → 最终 False, 不再重试
async def test_send_message_timeout_exhausts_retries(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.side_effect = httpx.ReadTimeout("always timeout")
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False
    assert mock_httpx.post.await_count == 3  # max retries = 3


# ═══════════════════════════════════════════════════════════════
# 2. IM业务错误码 (无效 token) → 记录错误并返回 False, 不重试
# ═══════════════════════════════════════════════════════════════
async def test_send_message_auth_error(mock_httpx):
    svc = _configured_service()
    # IM开放平台: code=99991663 token 无效; code!=0 即业务失败
    mock_httpx.post.return_value = _resp(200, {"code": 99991663, "msg": "invalid access token"})
    with patch.object(im_mod.logger, "error") as mock_err:
        result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False
    assert mock_httpx.post.await_count == 1  # 业务错误不重试
    # 错误日志须包含错误码, 不能静默
    logged = " ".join(str(c) for c in mock_err.call_args[0])
    assert "99991663" in logged


# ═══════════════════════════════════════════════════════════════
# 3. 限流响应: IM 429/限流码 → 返回 False, 业务码错误不重试
# ═══════════════════════════════════════════════════════════════
async def test_send_message_rate_limit(mock_httpx):
    svc = _configured_service()
    # IM自定义机器人限流: code=11236 或 HTTP 429
    mock_httpx.post.return_value = _resp(429, {"code": 11236, "msg": "reach rate limit"})
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False
    assert mock_httpx.post.await_count == 1  # 限流不重试 (避免加剧限流)


# ═══════════════════════════════════════════════════════════════
# 4. 连接错误: ConnectionError 重试耗尽 → False
# ═══════════════════════════════════════════════════════════════
async def test_send_message_network_error(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.side_effect = httpx.ConnectError("connection refused")
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False
    assert mock_httpx.post.await_count == 3


# 连接错误后重试成功 → True
async def test_send_message_network_error_retry_then_success(mock_httpx):
    svc = _configured_service()
    ok = _resp(200, {"code": 0})
    mock_httpx.post.side_effect = [httpx.ConnectError("refused"), ok]
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is True
    assert mock_httpx.post.await_count == 2


# ═══════════════════════════════════════════════════════════════
# 5. JSON 序列化/反序列化防护: IM返回非 JSON (如 502 html) → False, 不抛
# ═══════════════════════════════════════════════════════════════
async def test_json_serialize_error(mock_httpx):
    svc = _configured_service()
    # HTTP 200 但 body 是网关错误页 (非 JSON) → json() 抛 → 须捕获返回 False
    mock_httpx.post.return_value = _resp(200, json_raises=True)
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False


# 非法响应体 (None / 缺 code 字段) 不应崩, 按"非成功"处理
async def test_send_message_missing_code_field(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(200, {"msg": "no code field"})
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False


# ═══════════════════════════════════════════════════════════════
# 6. SSL 错误: httpx 把 ssl.SSLError 包装进 ConnectError → 重试耗尽 False
# ═══════════════════════════════════════════════════════════════
async def test_send_message_ssl_error(mock_httpx):
    svc = _configured_service()
    # httpx 0.28: SSL 握手失败表现为 ConnectError (内含 ssl 上下文)
    mock_httpx.post.side_effect = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")
    result = await svc.send_webhook_message({"msg_type": "text"})
    assert result is False
    assert mock_httpx.post.await_count == 3


# ═══════════════════════════════════════════════════════════════
# 7. 模板渲染: 变量缺失时安全降级而非崩溃
# ═══════════════════════════════════════════════════════════════
def test_template_missing_variable_prometheus():
    """format_prometheus_alert: 空 dict / 缺所有键 → 用默认值, 不抛 KeyError。"""
    svc = IMNotifyService()
    # 极端输入: 完全空, 无 labels/annotations/startsAt
    card = svc.format_prometheus_alert({})
    assert card["msg_type"] == "interactive"
    # 默认 alertname="未知告警", status="firing" → 触发态红色
    assert "未知告警" in card["card"]["header"]["title"]["content"]
    elements_str = str(card["card"]["elements"])
    assert "N/A" in elements_str  # instance/job/时间默认 N/A


def test_template_missing_variable_labels_none():
    """labels 显式 None (而非缺键) → 不抛 AttributeError。"""
    svc = IMNotifyService()
    card = svc.format_prometheus_alert({"labels": None, "annotations": None})
    assert card["msg_type"] == "interactive"
    assert "未知告警" in str(card["card"])


def test_safe_format_handles_non_string():
    """_safe_format helper: 非字符串变量 (None/int) 安全转字符串, 不抛。"""
    svc = IMNotifyService()
    # 模板变量为 None / 数字 → 降级为字符串占位, 不抛 TypeError
    out = svc._safe_format("val={}", None)
    assert out == "val=None"
    out2 = svc._safe_format("n={}", 42)
    assert out2 == "n=42"


# ═══════════════════════════════════════════════════════════════
# 8. timeout 参数显式传递 (加固契约: 每次请求必须带 timeout)
# ═══════════════════════════════════════════════════════════════
async def test_request_timeout_passed_to_client(mock_httpx):
    svc = _configured_service()
    mock_httpx.post.return_value = _resp(200, {"code": 0})
    await svc.send_webhook_message({"msg_type": "text"})
    # client.post 调用时须显式带 timeout 参数 (不能依赖全局默认)
    _, kwargs = mock_httpx.post.call_args
    assert "timeout" in kwargs
    assert kwargs["timeout"] is not None

"""安全测试: API catch-all 异常不得泄露内部错误信息 (信息泄露修复)

catch-all except 块必须向客户端返回通用错误消息, 严禁把 str(e) 直接放入
响应体——否则数据库连接串、文件路径、堆栈片段等会经由 500 响应外泄。

每个用例 monkeypatch 端点内首个被调函数令其抛出携带敏感「哨兵」字符串的
RuntimeError; 若该哨兵出现在响应体中即判定信息泄露。
"""
import pytest

import app.api.v1.on_call as on_call_module
import app.api.v1.order_fees as order_fees_module
import app.api.v1.protocol_instances as protocol_module

# 模拟内部异常携带的敏感信息; 修复后绝不可出现在响应体中
LEAK_MARKER = "INTERNAL_SECRET_TRACE_a1b2c3d4"
GENERIC_500 = "服务器内部错误，请稍后重试"


def _boom(*args, **kwargs):
    """抛出携带哨兵字符串的 RuntimeError, 模拟底层内部异常。"""
    raise RuntimeError(LEAK_MARKER)


@pytest.mark.parametrize("module, target, url", [
    (on_call_module, "team_scope", "/api/v1/on-call/rules"),
    (order_fees_module, "assert_order_team_access", "/api/v1/orders/1/fee-items"),
    (protocol_module, "is_platform_admin", "/api/v1/protocol-instances"),
])
def test_api_exception_does_not_leak_internal_error(client, monkeypatch, module, target, url):
    """端点内部异常时, 响应体不得包含异常原文, 应返回通用 500 消息。"""
    monkeypatch.setattr(module, target, _boom)

    resp = client.get(url)

    assert resp.status_code == 500, f"期望 500, 实际 {resp.status_code}: {resp.text}"
    # 核心: 敏感哨兵不得外泄
    assert LEAK_MARKER not in resp.text, "内部异常信息泄露到响应体"
    # 通用消息应出现在 detail
    assert resp.json().get("detail") == GENERIC_500

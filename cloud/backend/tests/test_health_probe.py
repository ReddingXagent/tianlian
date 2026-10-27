"""
Phase33-Task3 数据管道监控与告警 测试

覆盖 4 条验收标准:
  1. 网关健康检查探针 API (/api/v1/gateway/health)
  2. 数据管道吞吐量统计 (消息数/秒 + 延迟 avg_latency_ms + 错误率)
  3. 断连自动重试 + 告警通知集成 (reconnect_adapter / monitor_and_reconnect + on_alert 回调)
  4. pytest 覆盖 (本文件)

说明: gateway 层保持轻量, 告警通过 on_alert 回调注入解耦, 由 API/服务层注入真实告警实现。
"""
import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.gateway import health_probe
from app.gateway.health_probe import (
    record_request,
    get_throughput_stats,
    check_gateway_health,
    reconnect_adapter,
    monitor_and_reconnect,
)


# ========== 测试桩 ==========

class _FakeAdapter:
    """模拟协议适配器 (实现 connect/disconnect/is_connected)"""

    def __init__(self, connect_ok=True, connected=False):
        self._connect_ok = connect_ok
        self._connected = connected
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self._connected = self._connect_ok
        return self._connect_ok

    async def disconnect(self):
        self.disconnect_calls += 1
        return True

    def is_connected(self):
        return self._connected


class _FakeRegistry:
    def __init__(self, adapter):
        self._adapter = adapter

    def get_adapter(self, device_type, config):
        return self._adapter


async def _no_sleep(*_a, **_k):
    """抹平指数退避的 sleep, 加速测试"""
    return None


def _patch_registry(monkeypatch, adapter):
    monkeypatch.setattr(health_probe, "get_registry", lambda: _FakeRegistry(adapter))
    monkeypatch.setattr(health_probe.asyncio, "sleep", _no_sleep)


# ========== 标准2: 吞吐量统计含延迟 ==========

class TestThroughputLatency:
    """验收标准2: 吞吐量统计接口必须返回消息数/秒、延迟、错误率"""

    def test_record_request_tracks_latency(self):
        """record_request 记录延迟, 统计返回平均延迟"""
        health_probe._reset_metrics()
        record_request(bytes_count=100, error=False, latency_ms=12.0)
        record_request(bytes_count=200, error=False, latency_ms=24.0)
        stats = get_throughput_stats()
        assert stats["total_requests"] == 2
        assert stats["avg_latency_ms"] == pytest.approx(18.0)
        assert "requests_per_sec" in stats
        assert "error_rate_pct" in stats

    def test_record_request_backward_compat(self):
        """旧调用 (不传 latency_ms) 不报错, avg_latency_ms=0"""
        health_probe._reset_metrics()
        record_request(bytes_count=50)
        record_request(bytes_count=50, error=True)
        stats = get_throughput_stats()
        assert stats["total_requests"] == 2
        assert stats["total_errors"] == 1
        assert stats["avg_latency_ms"] == 0

    def test_check_gateway_health_returns_latency(self):
        """check_gateway_health 的 throughput 含 avg_latency_ms"""
        health_probe._reset_metrics()
        record_request(bytes_count=10, latency_ms=5.0)
        health = asyncio.run(check_gateway_health())
        assert "avg_latency_ms" in health["throughput"]
        assert health["throughput"]["avg_latency_ms"] == pytest.approx(5.0)
        assert health["throughput"]["total_requests"] == 1


# ========== 标准3: 断连自动重试 + 告警通知集成 ==========

class TestReconnectAdapter:
    """验收标准3: reconnect_adapter 重试 + on_alert 告警回调"""

    def test_reconnect_success_no_alert(self, monkeypatch):
        """重连成功 → 不触发告警"""
        adapter = _FakeAdapter(connect_ok=True)
        _patch_registry(monkeypatch, adapter)
        alert_cb = MagicMock()
        ok = asyncio.run(reconnect_adapter(
            "modbus_rtu", {"port": "/dev/x"}, max_retries=3, on_alert=alert_cb))
        assert ok is True
        alert_cb.assert_not_called()

    def test_reconnect_fail_triggers_alert(self, monkeypatch):
        """重连耗尽 → 触发告警, 消息含设备类型"""
        adapter = _FakeAdapter(connect_ok=False)
        _patch_registry(monkeypatch, adapter)
        alert_cb = MagicMock()
        ok = asyncio.run(reconnect_adapter(
            "modbus_rtu", {"port": "/dev/x"}, max_retries=2, on_alert=alert_cb))
        assert ok is False
        alert_cb.assert_called_once()
        message = alert_cb.call_args.args[1]
        assert "modbus_rtu" in message

    def test_reconnect_no_adapter_triggers_alert(self, monkeypatch):
        """无适配器 → 告警"""
        monkeypatch.setattr(health_probe, "get_registry",
                            lambda: _FakeRegistry(None))
        alert_cb = MagicMock()
        ok = asyncio.run(reconnect_adapter("unknown", {}, on_alert=alert_cb))
        assert ok is False
        alert_cb.assert_called_once()


class TestMonitorAndReconnect:
    """验收标准3: monitor_and_reconnect 自动重连编排 (断连感知 → 自动重连 → 失败告警)"""

    def test_connected_skips_reconnect(self, monkeypatch):
        """设备已连接 → 不重连, 不告警"""
        adapter = _FakeAdapter(connect_ok=True, connected=True)
        _patch_registry(monkeypatch, adapter)
        alert_cb = MagicMock()
        result = asyncio.run(monitor_and_reconnect(
            "modbus_rtu", {}, on_alert=alert_cb))
        assert result["reconnected"] is True
        assert result["attempted"] is False
        alert_cb.assert_not_called()
        assert adapter.connect_calls == 0

    def test_disconnected_reconnect_fail_alerts(self, monkeypatch):
        """断连 → 自动重连 → 失败 → 告警"""
        adapter = _FakeAdapter(connect_ok=False, connected=False)
        _patch_registry(monkeypatch, adapter)
        alert_cb = MagicMock()
        result = asyncio.run(monitor_and_reconnect(
            "mqtt", {"host": "x"}, on_alert=alert_cb, max_retries=2))
        assert result["reconnected"] is False
        assert result["attempted"] is True
        alert_cb.assert_called_once()

    def test_disconnected_reconnect_success(self, monkeypatch):
        """断连 → 自动重连 → 成功 → 不告警"""
        adapter = _FakeAdapter(connect_ok=True, connected=False)
        _patch_registry(monkeypatch, adapter)
        alert_cb = MagicMock()
        result = asyncio.run(monitor_and_reconnect(
            "modbus_rtu", {}, on_alert=alert_cb, max_retries=2))
        assert result["reconnected"] is True
        assert result["attempted"] is True
        alert_cb.assert_not_called()


# ========== 标准1: /api/v1/gateway/health 网关健康探针 ==========

class TestGatewayHealthRoute:
    """验收标准1: GET /api/v1/gateway/health 返回网关健康+吞吐量"""

    def test_gateway_health_endpoint(self, client: TestClient):
        resp = client.get("/api/v1/gateway/health")
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        assert "throughput" in data
        assert "protocols" in data
        assert "avg_latency_ms" in data["throughput"]

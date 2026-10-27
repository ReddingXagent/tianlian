"""
Pod 健康检查与注册 API 测试

覆盖: /api/v1/pod/*
- 健康信息 / 场站路由 / Pod 列表 / Pod 详情
- 单Pod模式下的 register / heartbeat 行为
- 场站聚合统计
"""

import ipaddress
import socket

import pytest

# D2 (卡69acc93c): /pod 写端点强制 X-Pod-Secret 共享密钥。本文件合法用例注入
# 密钥配置 + 默认请求头; 反向 403 路径由 test_auth_gaps_d2.py 覆盖。
_POD_SECRET = "test-pod-comm-secret"


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    """mock DNS 解析保证确定性(卡 bab27c02 起 register 校验 endpoint)。

    IP 字面量原样返回; 域名一律解析为公网 1.1.1.1。
    """
    from app.core import url_safety

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            ip = "1.1.1.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.fixture(autouse=True)
def _inject_pod_secret(monkeypatch, client):
    from app.core.config import settings
    monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", _POD_SECRET)
    client.headers["X-Pod-Secret"] = _POD_SECRET
    yield


def test_pod_health(client):
    """GET /pod/health 返回健康信息"""
    resp = client.get("/api/v1/pod/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["pod_id"]
    assert body["region_id"]
    assert body["endpoint"]
    assert "version" in body
    # load 结构
    load = body["load"]
    for key in ("stations", "devices", "memory_usage_pct"):
        assert key in load
    assert isinstance(body["uptime_seconds"], int)


def test_pod_register_local_only(client):
    """单Pod模式不支持注册(合法公网 endpoint 通过字段校验后到 local_only 分支)"""
    resp = client.post("/api/v1/pod/register", json={
        "pod_id": "pod-99",
        "region_id": "region-x",
        "endpoint": "https://api.pod.example.com",
        "version": "3.0.0",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "单Pod" in body["message"]


# ===== 卡 bab27c02: register endpoint SSRF 校验 =====

@pytest.mark.parametrize("bad_endpoint", [
    "http://127.0.0.1:8000",             # 环回 IP
    "http://169.254.169.254/latest/meta-data",  # 云元数据链路本地
    "http://localhost:8000",             # localhost 字面量
    "http://10.1.2.3:8000",              # 内网段(多Pod内网部署会被拒,见取舍注释)
    "http://192.168.1.10:8000",          # 内网段
    "file:///etc/passwd",                # 非 http/https scheme
    "ftp://pod.example.com",             # 非 http/https scheme
    "not-a-url",                         # 非法格式
])
def test_pod_register_rejects_unsafe_endpoint(client, bad_endpoint):
    """不安全 endpoint 在字段校验层即被拒(422), 不进入注册逻辑"""
    resp = client.post("/api/v1/pod/register", json={
        "pod_id": "pod-evil",
        "region_id": "region-x",
        "endpoint": bad_endpoint,
    })
    assert resp.status_code == 422


def test_pod_register_accepts_public_https_endpoint(client):
    """合法公网 https endpoint 放行(单Pod模式仍返回不支持注册,但通过校验)"""
    resp = client.post("/api/v1/pod/register", json={
        "pod_id": "pod-ok",
        "region_id": "region-x",
        "endpoint": "https://api.pod.example.com",
    })
    assert resp.status_code == 200
    assert "单Pod" in resp.json()["message"]


def test_pod_heartbeat_local_only(client):
    """单Pod模式心跳直接成功"""
    resp = client.post("/api/v1/pod/heartbeat", json={"pod_id": "pod-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True


def test_pod_heartbeat_emits_timing_log(client, caplog):
    """卡 f78a8e44: heartbeat 请求结束输出含固定键的 timing 分段日志"""
    import logging
    caplog.set_level(logging.INFO, logger="app.core.timing_log")
    resp = client.post("/api/v1/pod/heartbeat", json={"pod_id": "pod-01"})
    assert resp.status_code == 200
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "endpoint=pod/heartbeat" in msgs
    assert "batch_size=1" in msgs
    for key in ("total_ms", "auth_ms", "parse_ms", "insert_ms", "commit_ms"):
        assert f"{key}=" in msgs, f"timing 日志缺固定键: {key}"


def test_pod_routes(client):
    """GET /pod/routes 返回本Pod场站路由"""
    resp = client.get("/api/v1/pod/routes")
    assert resp.status_code == 200
    body = resp.json()
    assert "station_count" in body
    assert isinstance(body["stations"], list)
    assert body["station_count"] == len(body["stations"])


def test_pod_list(client):
    """GET /pod/list 返回已注册 Pod 列表"""
    resp = client.get("/api/v1/pod/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert isinstance(body["pods"], list)
    assert body["pods"][0]["pod_id"]


def test_pod_info_found_and_not_found(client):
    """本Pod可查，未知Pod返回404"""
    # 先从 list 拿到真实 pod_id
    pod_id = client.get("/api/v1/pod/list").json()["pods"][0]["pod_id"]

    ok = client.get(f"/api/v1/pod/info/{pod_id}")
    assert ok.status_code == 200
    assert ok.json()["pod_id"] == pod_id

    miss = client.get("/api/v1/pod/info/nonexistent-pod-xyz")
    assert miss.status_code == 404


def test_pod_stations_stats(client, seed_stations, seed_devices):
    """GET /pod/stations 返回场站/设备聚合统计"""
    resp = client.get("/api/v1/pod/stations")
    assert resp.status_code == 200
    body = resp.json()
    assert "stations" in body and "devices" in body
    for key in ("total", "normal", "maintenance", "closed"):
        assert key in body["stations"]
    for key in ("total", "online", "offline", "fault"):
        assert key in body["devices"]
    # 已 seed 2 站点 + 4 设备
    assert body["stations"]["total"] >= 2
    assert body["devices"]["total"] >= 4

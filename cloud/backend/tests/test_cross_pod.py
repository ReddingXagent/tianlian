"""
跨 Pod 查询 API 测试

覆盖: /api/v1/cross/*
- POST /cross/query        跨Pod聚合查询（单Pod模式走本地）
- POST /cross/internal/query  内部查询（仅本地）
- POST /cross/routes       批量路由查询
"""

import pytest

# D2 (卡69acc93c): /cross 写端点强制 X-Pod-Secret 共享密钥。本文件合法用例注入
# 密钥配置 + 默认请求头; 反向 403 路径由 test_auth_gaps_d2.py 覆盖。
_POD_SECRET = "test-pod-comm-secret"


@pytest.fixture(autouse=True)
def _inject_pod_secret(monkeypatch, client):
    from app.core.config import settings
    monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", _POD_SECRET)
    client.headers["X-Pod-Secret"] = _POD_SECRET
    yield


def test_cross_query_overview(client, seed_stations, seed_devices):
    """overview 查询返回场站概览 + 设备数"""
    sid = seed_stations["station_a"].id
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid],
        "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_type"] == "overview"
    assert body["total_stations"] == 1
    assert body["pods_involved"]  # 至少一个Pod
    assert len(body["results"]) == 1
    r = body["results"][0]
    assert r["station_id"] == sid
    assert r["station_name"]
    # station_a seed 了 2 个设备
    assert r["device_count"] == 2


def test_cross_query_unknown_station_skipped(client, seed_stations):
    """不存在的场站被跳过，结果为空"""
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [999999],
        "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []


def test_cross_query_devices_type(client, seed_stations, seed_devices):
    """devices 查询返回设备明细列表"""
    sid = seed_stations["station_a"].id
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid],
        "query_type": "devices",
    })
    assert resp.status_code == 200
    r = resp.json()["results"][0]
    assert r["device_count"] == 2
    assert isinstance(r["devices"], list)
    assert len(r["devices"]) == 2
    dev = r["devices"][0]
    assert "name" in dev and "sn" in dev and "type" in dev


def test_cross_query_include_details(client, seed_stations, seed_devices):
    """overview + include_details 带出设备明细"""
    sid = seed_stations["station_a"].id
    resp = client.post("/api/v1/cross/query", json={
        "station_ids": [sid],
        "query_type": "overview",
        "include_details": True,
    })
    r = resp.json()["results"][0]
    assert "devices" in r
    assert len(r["devices"]) == 2


def test_cross_routes(client, seed_stations):
    """批量路由查询返回每个场站归属的Pod"""
    sids = [seed_stations["station_a"].id, seed_stations["station_b"].id]
    resp = client.post("/api/v1/cross/routes", json={"station_ids": sids})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for sid in sids:
        route = body["routes"][str(sid)]
        assert "pod_id" in route
        assert "region_id" in route


def test_cross_internal_query(client, seed_stations, seed_devices):
    """内部查询仅返回本地数据"""
    sid = seed_stations["station_a"].id
    resp = client.post("/api/v1/cross/internal/query", json={
        "station_ids": [sid],
        "query_type": "overview",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["pod_id"]
    assert len(body["results"]) == 1
    assert body["results"][0]["station_id"] == sid

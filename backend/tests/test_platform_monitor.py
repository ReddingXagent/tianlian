"""
平台监控扩展 API 测试

覆盖:
  - GET /api/v1/platform/topology
  - GET /api/v1/platform/device-access-stats
"""


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


# ──────────────────────────────────────────────
# Topology 端点
# ──────────────────────────────────────────────


def test_topology_structure(client, seed_users):
    """空数据下返回完整结构骨架"""
    headers = _auth(client)
    resp = client.get("/api/v1/platform/topology", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("nodes", "status_summary", "type_summary", "device_online_rate", "timestamp"):
        assert key in body, f"缺字段 {key}"

    # 至少有9个节点
    assert len(body["nodes"]) >= 9

    # status_summary 三档
    for key in ("healthy", "degraded", "down"):
        assert key in body["status_summary"]

    # 每个节点结构
    node = body["nodes"][0]
    for key in ("id", "name", "type", "status", "response_time_ms", "dependencies"):
        assert key in node, f"节点缺字段 {key}"


def test_topology_node_types(client, seed_users):
    """节点类型覆盖 gateway/backend/db/cache/mq"""
    headers = _auth(client)
    resp = client.get("/api/v1/platform/topology", headers=headers)
    types = {n["type"] for n in resp.json()["nodes"]}
    assert "gateway" in types
    assert "backend" in types
    assert "db" in types
    assert "cache" in types
    assert "mq" in types


def test_topology_healthy_with_devices(client, seed_users, seed_stations, seed_devices):
    """seed 4 设备(2 online) → 在线率 50% → 仍可能 healthy/degraded，但端点正常"""
    headers = _auth(client)
    resp = client.get("/api/v1/platform/topology", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_online_rate"] == 50.0
    # 节点状态只有 healthy/degraded/down
    for n in body["nodes"]:
        assert n["status"] in ("healthy", "degraded", "down")


def test_topology_requires_auth(anon_client):
    """未认证 → 401"""
    resp = anon_client.get("/api/v1/platform/topology")
    assert resp.status_code in (401, 403)


# ──────────────────────────────────────────────
# Device Access Stats 端点
# ──────────────────────────────────────────────


def test_device_access_stats_empty(client, seed_users):
    """空数据下返回零值结构"""
    headers = _auth(client)
    resp = client.get("/api/v1/platform/device-access-stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total_devices", "total_online", "total_offline", "total_fault",
                "online_rate", "device_categories", "protocol_distribution", "timestamp"):
        assert key in body, f"缺字段 {key}"
    assert body["total_devices"] == 0
    assert body["online_rate"] == 0


def test_device_access_stats_with_data(client, seed_users, seed_stations, seed_devices):
    """seed 4 设备 → 分类统计正确"""
    headers = _auth(client)
    resp = client.get("/api/v1/platform/device-access-stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    # 4 台设备
    assert body["total_devices"] == 4
    assert body["total_online"] == 2
    assert body["total_fault"] == 1
    assert body["total_offline"] == 1
    assert body["online_rate"] == 50.0

    # 分类应包含光伏、充电桩、储能
    categories = {c["category"] for c in body["device_categories"]}
    assert "光伏" in categories
    assert "充电桩" in categories
    assert "储能" in categories

    # 每个分类条目结构
    for cat in body["device_categories"]:
        for key in ("category", "total", "online", "offline", "fault", "online_rate"):
            assert key in cat, f"分类缺字段 {key}"


def test_device_access_stats_requires_auth(anon_client):
    """未认证 → 401"""
    resp = anon_client.get("/api/v1/platform/device-access-stats")
    assert resp.status_code in (401, 403)

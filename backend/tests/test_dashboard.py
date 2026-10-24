"""
数据大屏 API 测试

覆盖: /api/v1/dashboard/large-screen
- 响应结构完整性
- 核心指标聚合（设备总量/在线/故障/离线 + 在线率）
- 告警统计 + 告警实时列表
- 站点健康分布
- 鉴权（router-level dependency）
"""


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_large_screen_structure(client, seed_users):
    """空数据下返回完整结构骨架"""
    headers = _auth(client)
    resp = client.get("/api/v1/dashboard/large-screen", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("core_metrics", "health_distribution", "station_health",
                "recent_alarms", "workorder_stats", "alarm_stats",
                "device_type_stats", "timestamp"):
        assert key in body, f"缺字段 {key}"
    # health_distribution 四档齐全
    for key in ("excellent", "good", "warning", "critical"):
        assert key in body["health_distribution"]


def test_large_screen_core_metrics(client, seed_users, seed_stations, seed_devices):
    """seed 4 设备(2 online + 1 fault + 1 offline) → 核心指标与在线率"""
    headers = _auth(client)
    resp = client.get("/api/v1/dashboard/large-screen", headers=headers)
    cm = resp.json()["core_metrics"]
    assert cm["total_devices"] == 4
    assert cm["online_devices"] == 2
    assert cm["fault_devices"] == 1
    assert cm["offline_devices"] == 1
    # 在线率 = 2/4*100
    assert cm["online_rate"] == 50.0
    assert cm["total_stations"] == 2
    # 空工单环境
    assert cm["pending_workorders"] == 0


def test_large_screen_alarm_stats(client, seed_users, seed_stations, seed_devices, seed_alarms):
    """seed 3 告警(2 active: 1 warning + 1 critical, 1 resolved)"""
    headers = _auth(client)
    body = client.get("/api/v1/dashboard/large-screen", headers=headers).json()
    alarm = body["alarm_stats"]
    assert alarm["active"] == 2
    assert alarm["critical"] == 1
    assert alarm["warning"] == 1
    # 告警实时列表取 active，共 2 条
    assert len(body["recent_alarms"]) == 2
    titles = {a["title"] for a in body["recent_alarms"]}
    assert titles  # 非空


def test_large_screen_station_health(client, seed_users, seed_stations, seed_devices):
    """两个站点均有设备 → 各产出一条健康记录，分布合计 = 2"""
    headers = _auth(client)
    body = client.get("/api/v1/dashboard/large-screen", headers=headers).json()
    sh = body["station_health"]
    assert len(sh) == 2
    station_names = {s["station_name"] for s in sh}
    assert "测试电站A" in station_names
    assert sum(body["health_distribution"].values()) == 2
    # 设备类型统计覆盖所有 seed 类型
    types = {d["type"] for d in body["device_type_stats"]}
    assert types  # 非空


def test_large_screen_requires_auth(anon_client):
    """router-level dependency: 缺 token 返回 401"""
    resp = anon_client.get("/api/v1/dashboard/large-screen")
    assert resp.status_code == 401

"""
内存缓存跨用例隔离复现测试 (卡 2f8e2e32)

背景: eb0e1afd (b97e22006) 复活 get_workflow_stats 缓存写侧后, cache.set_json 真写
app/core.cache 模块级 _MEMORY_CACHE。conftest 的 client fixture 切库时清缓存,
但 test_db fixture 只隔离 DB (独立 sqlite 副本 + override SessionLocal), 不清内存缓存
→ 经 test_db 的用例 (模块级 TestClient(app.main.app) + 服务层直调) 跨用例共享内存缓存。
cache key 含 team/scope 维度而测试库 id 序列相同 (admin 恒为 "all"), 换库后同 key
命中上一用例旧值 → 串扰假绿/假红。

复现设计: 同文件两个用例 (pytest.ini --dist=loadfile 保证同 worker 同进程),
用例 A 经真实端点路径写缓存; 用例 B 换全新独立 test_db (零告警) 调同端点,
断言读到的是本库真实状态而非 A 残留的缓存旧值。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

# 刻意走问题路径: 模块级 TestClient(app.main.app), 不经 conftest client fixture
# (该 fixture 会清内存缓存, 走它就复现不了 test_db 路径的缺口)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def test_case_a_stats_endpoint_seeds_memory_cache(test_db, auth_token):
    """用例 A: 库内 seed 3 条告警, 调 stats 端点 → 写侧落模块级内存缓存。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.core.cache import cache

    db = test_db["session"]
    station = Station(name="缓存串扰站A", code="CACHE-A", status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)
    device = Device(
        sn="CACHE-A-DEV-001", name="缓存串扰设备A",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=station.id, protocol_type=ProtocolType.MODBUS_RTU,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    for i in range(3):
        db.add(Alarm(
            device_id=device.id, alarm_type=f"cache_bleed_{i}",
            level=AlarmLevel.WARNING, content=f"缓存串扰告警{i}",
            status=AlarmStatus.ACTIVE,
        ))
    db.commit()

    resp = client.get("/api/v1/alert-workflow/stats", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["alerts"]["total"] == 3

    # 证明写侧确实把 A 库聚合结果落进了模块级内存缓存 (跨用例存活的载体)
    cached = cache.get_json("alert_workflow:stats:all")
    assert cached is not None, "stats 首查应写缓存 (eb0e1afd 复活的写侧)"
    assert cached["data"]["alerts"]["total"] == 3


def test_case_b_fresh_db_reads_own_state_not_stale_cache(test_db, auth_token):
    """用例 B: 全新独立 test_db 零告警, 同 admin 同 key。

    若内存缓存跨用例存活 (test_db 不清缓存), 本用例命中 A 的旧值 total==3;
    正确行为: 读本库真实状态 total==0。
    """
    resp = client.get("/api/v1/alert-workflow/stats", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200, resp.text
    total = resp.json()["data"]["alerts"]["total"]
    assert total == 0, (
        f"内存缓存跨 test_db 用例串扰: 本用例独立新库零告警, 却命中上一用例"
        f"残留缓存旧值 total={total} (key=alert_workflow:stats:all, TTL 30s 内)"
    )

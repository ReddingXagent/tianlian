"""
车辆维保/保险档案管理测试 - fleet-platform-spec §4.3

覆盖:
- 维保 CRUD: 创建/列表(类型+状态筛选)/详情/更新/删除 + 车辆404 + 无效类型 + 跨车隔离
- 保险 CRUD: 创建/列表/更新/删除 + 起止日期校验 + 无效类型
- 聚合档案: 维保统计 + 保险统计 + 到期提醒(即将到期/已过期/正常不计) + 空档案 + 车辆404
"""
from datetime import datetime, timedelta, timezone

import pytest


# ─── Helpers ───

def _seed_enterprise(db_session, code="VP_TEST"):
    """建企业, 返回 enterprise_id。"""
    from app.models.enterprise import Enterprise
    ent = Enterprise(name="档案测试企业", code=code, balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent.id


def _seed_vehicle(db_session, enterprise_id, idx=0):
    """建企业车辆, 返回 vehicle_id。"""
    from app.models.enterprise_vehicle import EnterpriseVehicle
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=f"豫A-VP-{enterprise_id}-{idx:03d}",
        vin=f"LSVAUVP{enterprise_id:06d}{idx:02d}",
    )
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v.id


def _iso(dt):
    return dt.isoformat()


_MAINT = {
    "type": "maintenance",
    "start_at": "2026-06-01T09:00:00",
    "end_at": "2026-06-01T11:00:00",
    "cost": 350.0,
    "mileage": 52000.0,
    "description": "常规保养-更换机油机滤",
}

_INS = {
    "insurance_type": "commercial",
    "company": "人保财险",
    "policy_no": "POL-2026-0001",
    "start_date": "2026-01-01T00:00:00",
    "end_date": "2026-12-31T23:59:59",
    "premium": 4500.0,
    "attachment_url": "https://cdn.example.com/pol-0001.pdf",
}


# ======================================================================
# 维保 CRUD
# ======================================================================

def test_create_maintenance(client, db_session):
    """POST 创建维保, 字段落库且回显正确, 默认状态 pending。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json=_MAINT)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["vehicle_id"] == vid
    assert data["type"] == "maintenance"
    assert data["cost"] == 350.0
    assert data["mileage"] == 52000.0
    assert data["status"] == "pending"
    assert data["description"] == "常规保养-更换机油机滤"


def test_create_maintenance_vehicle_not_found(client, db_session):
    """车辆不存在时创建维保返回 404。"""
    resp = client.post("/api/v1/fleet/vehicles/99999/maintenance", json=_MAINT)
    assert resp.status_code == 404


def test_create_maintenance_invalid_type(client, db_session):
    """无效维保类型返回 400。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(
        f"/api/v1/fleet/vehicles/{vid}/maintenance",
        json={**_MAINT, "type": "wash"},
    )
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


def test_list_maintenance_with_filter(client, db_session):
    """GET 维保列表支持按 type 过滤。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json=_MAINT)
    client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json={
        **_MAINT, "type": "repair", "description": "更换刹车片",
    })
    resp = client.get(f"/api/v1/fleet/vehicles/{vid}/maintenance?type=repair")
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["type"] == "repair"


def test_update_maintenance(client, db_session):
    """PUT 更新维保状态与费用, 回显新值。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    mid = client.post(
        f"/api/v1/fleet/vehicles/{vid}/maintenance", json=_MAINT
    ).json()["data"]["id"]
    resp = client.put(f"/api/v1/fleet/vehicles/{vid}/maintenance/{mid}", json={
        "status": "completed", "cost": 380.0,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["cost"] == 380.0


def test_delete_maintenance(client, db_session):
    """DELETE 删除维保后列表归零。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    mid = client.post(
        f"/api/v1/fleet/vehicles/{vid}/maintenance", json=_MAINT
    ).json()["data"]["id"]
    resp = client.delete(f"/api/v1/fleet/vehicles/{vid}/maintenance/{mid}")
    assert resp.status_code == 200
    listing = client.get(f"/api/v1/fleet/vehicles/{vid}/maintenance").json()["data"]
    assert listing["total"] == 0


def test_maintenance_cross_vehicle_isolation(client, db_session):
    """车辆A的维保记录不能被车辆B访问(返回404)。"""
    ent = _seed_enterprise(db_session)
    vid_a = _seed_vehicle(db_session, ent, idx=1)
    vid_b = _seed_vehicle(db_session, ent, idx=2)
    mid_a = client.post(
        f"/api/v1/fleet/vehicles/{vid_a}/maintenance", json=_MAINT
    ).json()["data"]["id"]
    resp = client.get(f"/api/v1/fleet/vehicles/{vid_b}/maintenance/{mid_a}")
    assert resp.status_code == 404


# ======================================================================
# 保险 CRUD
# ======================================================================

def test_create_insurance(client, db_session):
    """POST 创建保险, 字段落库且回显正确。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json=_INS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["vehicle_id"] == vid
    assert data["insurance_type"] == "commercial"
    assert data["company"] == "人保财险"
    assert data["policy_no"] == "POL-2026-0001"
    assert data["premium"] == 4500.0
    assert data["attachment_url"].endswith("pol-0001.pdf")


def test_create_insurance_invalid_dates(client, db_session):
    """到期日期早于起保日期返回 400。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    payload = {
        **_INS,
        "start_date": "2026-12-01T00:00:00",
        "end_date": "2026-01-01T00:00:00",
    }
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json=payload)
    assert resp.status_code == 400


def test_create_insurance_invalid_type(client, db_session):
    """无效保险类型返回 400。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(
        f"/api/v1/fleet/vehicles/{vid}/insurance",
        json={**_INS, "insurance_type": "theft"},
    )
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


def test_list_insurance(client, db_session):
    """GET 保险列表支持按 insurance_type 过滤。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json=_INS)
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json={
        **_INS, "policy_no": "POL-2026-0002", "insurance_type": "compulsory",
    })
    resp = client.get(f"/api/v1/fleet/vehicles/{vid}/insurance")
    assert resp.json()["data"]["total"] == 2
    resp2 = client.get(f"/api/v1/fleet/vehicles/{vid}/insurance?insurance_type=compulsory")
    assert resp2.json()["data"]["total"] == 1


def test_update_insurance(client, db_session):
    """PUT 更新保险保费与公司, 回显新值。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    iid = client.post(
        f"/api/v1/fleet/vehicles/{vid}/insurance", json=_INS
    ).json()["data"]["id"]
    resp = client.put(f"/api/v1/fleet/vehicles/{vid}/insurance/{iid}", json={
        "premium": 4800.0, "company": "平安产险",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["premium"] == 4800.0
    assert data["company"] == "平安产险"


def test_delete_insurance(client, db_session):
    """DELETE 删除保险后列表归零。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    iid = client.post(
        f"/api/v1/fleet/vehicles/{vid}/insurance", json=_INS
    ).json()["data"]["id"]
    resp = client.delete(f"/api/v1/fleet/vehicles/{vid}/insurance/{iid}")
    assert resp.status_code == 200
    assert client.get(f"/api/v1/fleet/vehicles/{vid}/insurance").json()["data"]["total"] == 0


# ======================================================================
# 聚合档案 + 到期提醒
# ======================================================================

def test_profile_aggregation(client, db_session):
    """GET /profile 聚合维保统计+保险统计。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    m1 = client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json={
        **_MAINT, "cost": 100.0,
    }).json()["data"]
    client.put(f"/api/v1/fleet/vehicles/{vid}/maintenance/{m1['id']}", json={"status": "completed"})
    m2 = client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json={
        **_MAINT, "type": "repair", "cost": 200.0,
    }).json()["data"]
    client.put(f"/api/v1/fleet/vehicles/{vid}/maintenance/{m2['id']}", json={"status": "completed"})
    # 1 条生效保险(远未到期)
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json={
        **_INS, "policy_no": "AGG-001",
        "end_date": _iso(datetime.now(timezone.utc) + timedelta(days=365)),
        "premium": 5000.0,
    })

    resp = client.get(f"/api/v1/fleet/vehicles/{vid}/profile")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["vehicle_id"] == vid
    assert data["maintenance"]["total_count"] == 2
    assert data["maintenance"]["total_cost"] == 300.0
    assert data["maintenance"]["by_status"] == {"completed": 2}
    assert data["insurance"]["total_count"] == 1
    assert data["insurance"]["active_count"] == 1
    assert data["insurance"]["total_premium"] == 5000.0


def test_profile_expiry_reminder(client, db_session):
    """到期提醒: 即将到期/已过期入提醒, 远未到期不入提醒。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    now = datetime.now(timezone.utc)
    # 即将到期(10天后)
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json={
        **_INS, "policy_no": "SOON",
        "end_date": _iso(now + timedelta(days=10)),
    })
    # 已过期(1天前)
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json={
        **_INS, "policy_no": "EXPIRED",
        "start_date": _iso(now - timedelta(days=400)),
        "end_date": _iso(now - timedelta(days=1)),
    })
    # 正常(100天后, 不应提醒)
    client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json={
        **_INS, "policy_no": "OK",
        "end_date": _iso(now + timedelta(days=100)),
    })

    resp = client.get(f"/api/v1/fleet/vehicles/{vid}/profile?reminder_days=30")
    data = resp.json()["data"]
    reminders = data["expiry_reminders"]
    policies = {r["policy_no"]: r for r in reminders}
    assert "SOON" in policies
    assert policies["SOON"]["status"] == "expiring_soon"
    assert "EXPIRED" in policies
    assert policies["EXPIRED"]["status"] == "expired"
    assert "OK" not in policies
    # 按剩余天数升序: 已过期(负) 排在 即将到期(正) 之前
    assert reminders[0]["days_remaining"] < reminders[-1]["days_remaining"]


def test_profile_vehicle_not_found(client, db_session):
    """聚合档案: 车辆不存在返回 404。"""
    resp = client.get("/api/v1/fleet/vehicles/99999/profile")
    assert resp.status_code == 404


def test_profile_empty(client, db_session):
    """空档案聚合返回零值。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.get(f"/api/v1/fleet/vehicles/{vid}/profile")
    data = resp.json()["data"]
    assert data["maintenance"]["total_count"] == 0
    assert data["insurance"]["total_count"] == 0
    assert data["expiry_reminders"] == []


# ======================================================================
# 卡 c4cbcbf1: _parse_dt ISO8601 Z后缀 (py3.9 误拒, 维保/保险共用 helper)
# 旧 _parse_dt: datetime.fromisoformat 有 try/except→400, 但 py3.9 不识 'Z'
# → 合法 Z 被误拒 400 (UX 缺口)。接入共享 parse_iso8601 归一后接受 (保留剥 tz 语义)。
# ======================================================================

_DT_STATES = [
    pytest.param("2026-06-01T09:00:00Z", "2026-06-01T09:00:00", id="z"),
    pytest.param("2026-06-01T09:00:00+08:00", "2026-06-01T09:00:00", id="offset"),
    pytest.param("2026-06-01T09:00:00", "2026-06-01T09:00:00", id="naive"),
]


@pytest.mark.parametrize("value,stored", _DT_STATES)
def test_create_maintenance_start_at_valid_formats(client, db_session, value, stored):
    """维保 start_at: Z/offset/naive → 200, 剥 tz 后墙钟回显一致。

    py3.9 旧 _parse_dt 拒 Z (UX 缺口); offset/naive 本就通过。
    """
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    payload = dict(_MAINT, start_at=value, end_at="2026-06-01T11:00:00")
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json=payload)
    assert resp.status_code == 200, f"合法 start_at={value} 应200, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"]["start_at"] == stored


def test_create_maintenance_start_at_bad_400(client, db_session):
    """维保 start_at 坏值 → 400。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/maintenance", json=dict(_MAINT, start_at="not-a-date"))
    assert resp.status_code == 400, f"坏值应400, 实际 {resp.status_code}: {resp.text}"


def test_create_insurance_start_date_z_suffix(client, db_session):
    """保险 start_date Z后缀 → 200, 剥 tz 墙钟回显 (同 _parse_dt, 另一调用路径)。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json=dict(
        _INS, start_date="2026-01-01T00:00:00Z", end_date="2026-12-31T23:59:59",
    ))
    assert resp.status_code == 200, f"Z后缀应200, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"]["start_date"] == "2026-01-01T00:00:00"


def test_create_insurance_start_date_bad_400(client, db_session):
    """保险 start_date 坏值 → 400 (同 _parse_dt, 另一调用路径)。"""
    vid = _seed_vehicle(db_session, _seed_enterprise(db_session))
    resp = client.post(f"/api/v1/fleet/vehicles/{vid}/insurance", json=dict(_INS, start_date="not-a-date"))
    assert resp.status_code == 400, f"坏值应400, 实际 {resp.status_code}: {resp.text}"

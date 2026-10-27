"""
企业充电策略管理测试 - fleet-platform-spec §4.3

覆盖:
- CRUD: 创建 / 列表(企业筛选) / 更新 / 删除 + 404
- check 校验逻辑: 无策略放行 / 站点白名单 / 时段白名单 / 日限额 / 禁用策略被忽略 / 全满足放行
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.charging_order import ChargingOrder, OrderStatus


# ─── Helpers ───

def _seed_enterprise(db_session, code="POL_TEST"):
    """建企业, 返回 enterprise_id。"""
    ent = Enterprise(name="策略测试企业", code=code, balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent.id


def _seed_vehicle(db_session, enterprise_id, idx=0):
    """建企业车辆, 返回 vehicle_id。"""
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=f"豫A-POL-{enterprise_id}-{idx:03d}",
        vin=f"LSVAUPOL{enterprise_id:06d}{idx:02d}",
    )
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v.id


def _seed_order(db_session, vehicle_id, station_id, device_id, kwh, days_ago=0):
    """建充电订单(默认已完成), 返回订单。"""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    order = ChargingOrder(
        order_no=f"NO-POL-{vehicle_id}-{station_id}-{device_id}-{int(created.timestamp())}",
        station_id=station_id,
        device_id=device_id,
        vehicle_id=vehicle_id,
        charged_kwh=Decimal(str(kwh)),
        order_status=OrderStatus.COMPLETED,
        created_at=created,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


_PAYLOAD = {
    "daily_kwh_limit": 500.0,
    "allowed_time_slots": ["谷", "平"],
    "allowed_station_ids": [1, 2, 3],
    "enable": True,
}


# ======================================================================
# 创建
# ======================================================================

def test_create_policy(client, db_session):
    """POST /fleet/policies 创建策略, 字段落库且回显正确。"""
    ent_id = _seed_enterprise(db_session)
    resp = client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id, **_PAYLOAD,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["enterprise_id"] == ent_id
    assert data["daily_kwh_limit"] == 500.0
    assert data["allowed_time_slots"] == ["谷", "平"]
    assert data["allowed_station_ids"] == [1, 2, 3]
    assert data["enable"] is True
    assert data["created_at"]


def test_create_policy_enterprise_not_found(client, db_session):
    """企业不存在时返回 404。"""
    resp = client.post("/api/v1/fleet/policies", json={
        "enterprise_id": 999999, **_PAYLOAD,
    })
    assert resp.status_code == 404


# ======================================================================
# 列表
# ======================================================================

def test_list_policies_filter_by_enterprise(client, db_session):
    """GET /fleet/policies 按 enterprise_id 筛选, 分页结构正确。"""
    ent_a = _seed_enterprise(db_session, code="POL_A")
    ent_b = _seed_enterprise(db_session, code="POL_B")

    for _ in range(2):
        client.post("/api/v1/fleet/policies", json={"enterprise_id": ent_a, **_PAYLOAD})
    client.post("/api/v1/fleet/policies", json={"enterprise_id": ent_b, **_PAYLOAD})

    resp = client.get(f"/api/v1/fleet/policies?enterprise_id={ent_a}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert all(it["enterprise_id"] == ent_a for it in data["items"])


# ======================================================================
# 更新
# ======================================================================

def test_update_policy(client, db_session):
    """PUT /fleet/policies/{id} 更新字段, 回显新值。"""
    ent_id = _seed_enterprise(db_session)
    pid = client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id, **_PAYLOAD,
    }).json()["data"]["id"]

    resp = client.put(f"/api/v1/fleet/policies/{pid}", json={
        "daily_kwh_limit": 800.0,
        "allowed_time_slots": ["谷"],
        "allowed_station_ids": [5, 6],
        "enable": False,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["daily_kwh_limit"] == 800.0
    assert data["allowed_time_slots"] == ["谷"]
    assert data["allowed_station_ids"] == [5, 6]
    assert data["enable"] is False


def test_update_policy_not_found(client, db_session):
    """更新不存在的策略返回 404。"""
    resp = client.put("/api/v1/fleet/policies/99999", json={"enable": False})
    assert resp.status_code == 404


# ======================================================================
# 删除
# ======================================================================

def test_delete_policy(client, db_session):
    """DELETE /fleet/policies/{id} 删除后列表减少。"""
    ent_id = _seed_enterprise(db_session)
    pid = client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id, **_PAYLOAD,
    }).json()["data"]["id"]

    resp = client.delete(f"/api/v1/fleet/policies/{pid}")
    assert resp.status_code == 200

    listing = client.get(f"/api/v1/fleet/policies?enterprise_id={ent_id}").json()["data"]
    assert listing["total"] == 0


def test_delete_policy_not_found(client, db_session):
    """删除不存在的策略返回 404。"""
    resp = client.delete("/api/v1/fleet/policies/99999")
    assert resp.status_code == 404


# ======================================================================
# check 校验逻辑
# ======================================================================

def test_check_no_policy_allowed(client, db_session):
    """企业无启用策略 -> 允许充电。"""
    ent_id = _seed_enterprise(db_session)
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=10&time_slot=峰"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["allowed"] is True
    assert data["policy_id"] is None


def test_check_station_not_allowed(client, db_session):
    """站点不在白名单 -> 拒绝并给出原因。"""
    ent_id = _seed_enterprise(db_session)
    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 0,
        "allowed_time_slots": [],
        "allowed_station_ids": [1, 2, 3],
        "enable": True,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=999&time_slot=谷"
    )
    data = resp.json()["data"]
    assert data["allowed"] is False
    assert "站点" in data["reason"]
    assert data["policy_id"] is not None


def test_check_time_slot_not_allowed(client, db_session):
    """时段不在白名单 -> 拒绝并给出原因。"""
    ent_id = _seed_enterprise(db_session)
    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 0,
        "allowed_time_slots": ["谷", "平"],
        "allowed_station_ids": [],
        "enable": True,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=1&time_slot=峰"
    )
    data = resp.json()["data"]
    assert data["allowed"] is False
    assert "时段" in data["reason"]


def test_check_disabled_policy_ignored(client, db_session):
    """策略 enable=False 时被忽略, 视同无策略放行。"""
    ent_id = _seed_enterprise(db_session)
    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 0,
        "allowed_time_slots": ["谷"],
        "allowed_station_ids": [1],
        "enable": False,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=999&time_slot=峰"
    )
    data = resp.json()["data"]
    assert data["allowed"] is True
    assert data["policy_id"] is None


def test_check_all_allowed(client, db_session):
    """站点+时段均在白名单且未达日限额 -> 允许。"""
    ent_id = _seed_enterprise(db_session)
    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 500.0,
        "allowed_time_slots": ["谷", "平"],
        "allowed_station_ids": [1, 2],
        "enable": True,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=2&time_slot=平"
    )
    data = resp.json()["data"]
    assert data["allowed"] is True
    assert data["policy_id"] is not None
    assert data["used_today_kwh"] == 0.0


def test_check_daily_limit_exceeded(client, db_session):
    """当日累计已达日限额 -> 拒绝。"""
    ent_id = _seed_enterprise(db_session)
    vid = _seed_vehicle(db_session, ent_id)
    # 当日已充 520 kWh(超 500 限额)
    _seed_order(db_session, vid, station_id=1, device_id=1, kwh=520.0, days_ago=0)

    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 500.0,
        "allowed_time_slots": ["谷", "平"],
        "allowed_station_ids": [1, 2],
        "enable": True,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=1&time_slot=谷"
    )
    data = resp.json()["data"]
    assert data["allowed"] is False
    assert "限额" in data["reason"]
    assert data["used_today_kwh"] == 520.0


def test_check_daily_limit_ignores_old_orders(client, db_session):
    """昨日订单不计入当日累计, 未达限额放行。"""
    ent_id = _seed_enterprise(db_session)
    vid = _seed_vehicle(db_session, ent_id)
    # 昨日订单不应计入
    _seed_order(db_session, vid, station_id=1, device_id=1, kwh=1000.0, days_ago=1)

    client.post("/api/v1/fleet/policies", json={
        "enterprise_id": ent_id,
        "daily_kwh_limit": 500.0,
        "allowed_time_slots": ["谷"],
        "allowed_station_ids": [1],
        "enable": True,
    })
    resp = client.get(
        f"/api/v1/fleet/policies/check?enterprise_id={ent_id}&station_id=1&time_slot=谷"
    )
    data = resp.json()["data"]
    assert data["allowed"] is True
    assert data["used_today_kwh"] == 0.0


# ======================================================================
# 异常路径加固 (卡 416f2bb4)
# ======================================================================

def test_create_policy_integrity_conflict(client, db_session, monkeypatch):
    """创建策略遇唯一约束冲突 → 409。"""
    from sqlalchemy.exc import IntegrityError

    ent_id = _seed_enterprise(db_session)

    def _boom(*a, **kw):
        raise IntegrityError("simulated", {}, Exception("UNIQUE"))

    monkeypatch.setattr(db_session, "commit", _boom)

    resp = client.post(
        "/api/v1/fleet/policies",
        json={"enterprise_id": ent_id, **_PAYLOAD},
    )
    assert resp.status_code == 409

# 卡18885b82: 路由补盲 — 零散 19 端点
# alarms/rules/{id}/evaluate; alarm-rules/{id}/toggle+evaluate; work-orders dispatch/transfer;
# spare-parts inbound/outbound; stats/perf; gateways/status; api-keys/{id}/usage; security/stats;
# runbook templates/{name}+stats; admin/registrations approve/reject; business vehicles/favorites
import uuid
from datetime import datetime, timezone

import bcrypt

from app.models.alarm import AlarmRule, AlarmLevel
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.gateway import Gateway
from app.models.registration import RegistrationApplication, RegistrationStatus
from app.models.spare_part import SparePartInventory
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderStatus
from tests.api._helpers import create_wo


def _seed_alarm_rule(s):
    rule = AlarmRule(name=f"规则{uuid.uuid4().hex[:6]}", metric="battery_temperature",
                     operator=">", threshold=60.0, duration=0,
                     level=AlarmLevel.WARNING, alarm_template="温度超限", enabled=True)
    s.add(rule)
    s.commit()
    s.refresh(rule)
    return rule


# ─── 告警规则 evaluate / toggle ───

def test_alarm_rules_evaluate_and_toggle(client):
    s = client._sesh
    rule = _seed_alarm_rule(s)
    # alarm-rules 前缀
    r = client.post(f"/api/v1/alarm-rules/{rule.id}/evaluate")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["rule_id"] == rule.id
    assert data["success"] is True

    r = client.put(f"/api/v1/alarm-rules/{rule.id}/toggle")
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is False

    # alarms 前缀 (同语义别名)
    r = client.post(f"/api/v1/alarms/rules/{rule.id}/evaluate")
    assert r.status_code == 200
    assert r.json()["data"]["success"] is True


# ─── 工单 dispatch / transfer ───

def _seed_engineer(s, username):
    u = User(username=username,
             password_hash=bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode(),
             real_name=username, role=UserRole.ENGINEER, status="active")
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def test_workorder_dispatch(client):
    wo_id = create_wo(client)
    _seed_engineer(client._sesh, f"eng_{uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/work-orders/{wo_id}/dispatch", json={"auto": True})
    assert r.status_code == 200, r.text
    assert "engineer" in r.json()["data"]
    # 非 pending → 400; 不存在 → 404
    r2 = client.post(f"/api/v1/work-orders/{wo_id}/dispatch", json={"auto": True})
    assert r2.status_code == 400
    assert client.post("/api/v1/work-orders/NO-SUCH/dispatch",
                       json={"auto": True}).status_code == 404


def test_workorder_transfer(client):
    s = client._sesh
    e1 = _seed_engineer(s, f"eng1_{uuid.uuid4().hex[:8]}")
    e2 = _seed_engineer(s, f"eng2_{uuid.uuid4().hex[:8]}")
    wo = WorkOrder(id=f"WO-TR-{uuid.uuid4().hex[:10]}", fault_desc="转单测试", type="repair",
                   level="warning", status=WorkOrderStatus.ACCEPTED, assignee_id=e1.id)
    s.add(wo)
    s.commit()
    r = client.post(f"/api/v1/work-orders/{wo.id}/transfer",
                    json={"target_engineer_id": e2.id, "reason": "技能不匹配"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "pending"
    # 转给自己 → 400; 目标不存在 → 404; 工单不存在 → 404
    assert client.post(f"/api/v1/work-orders/{wo.id}/transfer",
                       json={"target_engineer_id": e2.id, "reason": "x"}).status_code == 400
    assert client.post(f"/api/v1/work-orders/{wo.id}/transfer",
                       json={"target_engineer_id": 99999, "reason": "x"}).status_code == 404
    assert client.post("/api/v1/work-orders/NO-SUCH/transfer",
                       json={"target_engineer_id": e2.id, "reason": "x"}).status_code == 404


# ─── spare-parts 入库/出库 ───

def test_spare_parts_inbound_outbound(client):
    s = client._sesh
    part = SparePartInventory(part_name="熔断器", part_model="FU-100",
                              total_quantity=10, available_quantity=10)
    s.add(part)
    s.commit()
    s.refresh(part)

    r = client.post(f"/api/v1/spare-parts/{part.id}/inbound", json={"quantity": 5})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_quantity"] == 15
    assert data["available_quantity"] == 15

    r = client.post(f"/api/v1/spare-parts/{part.id}/outbound", json={"quantity": 3})
    assert r.status_code == 200
    assert r.json()["data"]["available_quantity"] == 12

    # 库存不足 → 409; 不存在 → 404
    assert client.post(f"/api/v1/spare-parts/{part.id}/outbound",
                       json={"quantity": 999}).status_code == 409
    assert client.post(f"/api/v1/spare-parts/99999/outbound",
                       json={"quantity": 1}).status_code == 404


# ─── stats/perf, gateways/status, security/stats ───

def test_stats_perf(client):
    r = client.get("/api/v1/stats/perf")
    assert r.status_code == 200
    data = r.json()["data"]
    for k in ("cpu_percent", "memory_total", "memory_percent", "db_connections"):
        assert k in data


def test_gateways_status(client):
    s = client._sesh
    sta = Station(name="网关站", code=f"GW{uuid.uuid4().hex[:6]}", address="x",
                  status=StationStatus.NORMAL)
    s.add(sta)
    s.commit()
    s.refresh(sta)
    s.add_all([
        Gateway(name="G1", sn=f"gw-{uuid.uuid4().hex[:8]}", station_id=sta.id, status="online"),
        Gateway(name="G2", sn=f"gw-{uuid.uuid4().hex[:8]}", station_id=sta.id, status="offline"),
    ])
    s.commit()
    r = client.get("/api/v1/gateways/status")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["online_count"] == 1
    assert data["offline_count"] == 1


def test_security_stats(client):
    r = client.get("/api/v1/security/stats")
    assert r.status_code == 200
    assert "total_logins" in r.json()["data"]


# ─── api-keys/{id}/usage ───

def test_api_key_usage(client):
    s = client._sesh
    admin = s.query(User).filter(User.username == "admin").first()
    key = ApiKey(key_hash=uuid.uuid4().hex, key_prefix="tlk", user_id=admin.id,
                 name="usage测试", is_active=True, is_revoked=False)
    s.add(key)
    s.commit()
    s.refresh(key)
    r = client.get(f"/api/v1/api-keys/{key.id}/usage")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["key_id"] == key.id
    assert data["total_requests"] == 0
    assert client.get("/api/v1/api-keys/99999/usage").status_code == 404


# ─── runbook templates/{name} + stats ───

def test_runbook_templates_and_stats(client):
    r = client.get("/api/v1/runbook/templates")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["data"]]
    assert len(names) > 0
    r = client.get(f"/api/v1/runbook/templates/{names[0]}")
    assert r.status_code == 200
    assert r.json()["data"]["name"] == names[0]
    # 不存在模板: error_response 404 code (HTTP 200 语义见实现, 断言业务码)
    r = client.get("/api/v1/runbook/templates/__no_such__")
    assert r.json()["code"] != 0 or r.status_code == 404

    r = client.get("/api/v1/runbook/stats")
    assert r.status_code == 200
    assert "total_executions" in r.json()["data"]


# ─── admin/registrations approve / reject ───

def _seed_registration(s, company):
    app = RegistrationApplication(
        company_name=company, credit_code=f"91330100{abs(hash(company)) % 10**10:010d}"[:18],
        contact_name="联系人", contact_phone="13900000000",
        password_hash=bcrypt.hashpw(b"pw123456", bcrypt.gensalt()).decode(),
        agreed_to_terms=True)
    s.add(app)
    s.commit()
    s.refresh(app)
    return app


def test_admin_registration_approve_and_idempotent(client):
    s = client._sesh
    app = _seed_registration(s, f"审批公司{uuid.uuid4().hex[:6]}")
    r = client.post(f"/api/v1/admin/registrations/{app.id}/approve")
    assert r.status_code == 200, r.text
    # 幂等
    r2 = client.post(f"/api/v1/admin/registrations/{app.id}/approve")
    assert r2.status_code == 200
    # 已通过 → 拒绝 400
    assert client.post(f"/api/v1/admin/registrations/{app.id}/reject",
                       json={"review_remark": "太晚了"}).status_code == 400
    assert client.post("/api/v1/admin/registrations/99999/approve").status_code == 404


def test_admin_registration_reject(client):
    s = client._sesh
    app = _seed_registration(s, f"拒绝公司{uuid.uuid4().hex[:6]}")
    r = client.post(f"/api/v1/admin/registrations/{app.id}/reject",
                    json={"review_remark": "资质不符"})
    assert r.status_code == 200
    # 已拒绝 → 再 approve 400
    assert client.post(f"/api/v1/admin/registrations/{app.id}/approve").status_code == 400
    # 已 REJECTED 再 reject → 400 (卡7bdc63e2 补守卫, 与 approve 双向守卫对齐)
    assert client.post(f"/api/v1/admin/registrations/{app.id}/reject",
                       json={"review_remark": "再拒"}).status_code == 400
    assert client.post("/api/v1/admin/registrations/99999/reject",
                       json={"review_remark": "x"}).status_code == 404


def test_admin_registration_reject_rejected_guard_no_overwrite(client):
    """卡7bdc63e2: 重复驳回被 400 拒绝, 且首次驳回的 reviewer/reviewed_at 不被覆写。"""
    s = client._sesh
    app = _seed_registration(s, f"重复拒绝公司{uuid.uuid4().hex[:6]}")
    assert client.post(f"/api/v1/admin/registrations/{app.id}/reject",
                       json={"review_remark": "首次理由"}).status_code == 200
    s.expire_all()
    first = s.query(RegistrationApplication).get(app.id)
    first_remark, first_at = first.review_remark, first.reviewed_at
    assert client.post(f"/api/v1/admin/registrations/{app.id}/reject",
                       json={"review_remark": "二次理由"}).status_code == 400
    s.expire_all()
    again = s.query(RegistrationApplication).get(app.id)
    assert again.status == RegistrationStatus.REJECTED
    assert again.review_remark == first_remark == "首次理由"
    assert again.reviewed_at == first_at


# ─── business vehicles delete / default; favorites delete ───

def _end_user_login(client, code):
    r = client.post("/api/v1/business/auth/wx-login", json={"code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_business_vehicle_delete_and_default(client):
    h = _end_user_login(client, f"gap-{uuid.uuid4().hex[:8]}")
    base = "/api/v1/business/vehicles"
    r1 = client.post(base, json={"plate_number": "京A11111"}, headers=h)
    assert r1.status_code == 200, r1.text
    r2 = client.post(base, json={"plate_number": "京B22222"}, headers=h)
    assert r2.status_code == 200
    v1, v2 = r1.json()["data"], r2.json()["data"]

    r = client.patch(f"{base}/{v2['vehicle_id']}/default", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["is_default"] is True
    r = client.delete(f"{base}/{v1['vehicle_id']}", headers=h)
    assert r.status_code == 200
    # 再删 → 404
    assert client.delete(f"{base}/{v1['vehicle_id']}", headers=h).status_code == 404


def test_business_favorite_delete(client):
    h = _end_user_login(client, f"fav-{uuid.uuid4().hex[:8]}")
    s = client._sesh
    sta = Station(name=f"收藏站{uuid.uuid4().hex[:6]}",
                  code=f"FV{uuid.uuid4().hex[:6]}", address="x",
                  status=StationStatus.NORMAL)
    s.add(sta)
    s.commit()
    s.refresh(sta)
    base = "/api/v1/business/favorites"
    r = client.post(base, json={"station_id": sta.id}, headers=h)
    assert r.status_code == 200, r.text
    r = client.delete(f"{base}/{sta.id}", headers=h)
    assert r.status_code == 200
    # 幂等: 再删 deleted=false
    r = client.delete(f"{base}/{sta.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] is False

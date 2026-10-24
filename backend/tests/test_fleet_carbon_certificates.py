"""
碳减排核证/交易测试 - fleet-platform-spec §4.3

覆盖:
- 申请核证: 成功 / 汇总不存在(404) / 汇总未审核(400) / 重复申请(400)
- 列表: 企业+状态筛选
- 核证确认: pending->verified / 非法状态(400) / 不存在(404)
- 交易登记: verified->traded / 未核证直接交易(400)
- 状态流转: 撤销 pending->cancelled, 撤销后同汇总可重新申请
"""
from datetime import datetime
from decimal import Decimal

from app.models.enterprise import Enterprise
from app.models.carbon_emission import CarbonReductionSummary


# ─── Helpers ───

def _seed_enterprise(db_session, code="CC_TEST"):
    """建企业, 返回 enterprise_id。"""
    ent = Enterprise(name="碳核证测试企业", code=code, balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)
    return ent.id


def _seed_summary(db_session, enterprise_id, year=2026, month=6, verified=True,
                  reduction_kg=100000.0):
    """建碳减排月度汇总, 返回 summary_id。"""
    s = CarbonReductionSummary(
        enterprise_id=enterprise_id,
        report_year=year,
        report_month=month,
        total_charge_kwh=Decimal("12000.00"),
        total_reduction_kg=Decimal(str(reduction_kg)),
        total_fuel_saved_liters=Decimal("6720.00"),
        vehicle_count=8,
        verified=verified,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s.id


_BASE = "/api/v1/fleet/carbon/certificates"


def _apply(client, summary_id):
    return client.post(f"{_BASE}/apply", json={"summary_id": summary_id})


# ======================================================================
# 申请核证
# ======================================================================

def test_apply_certificate(client, db_session):
    """POST /apply 从已审核汇总申请核证, 状态pending, 编号回显。"""
    ent_id = _seed_enterprise(db_session)
    sid = _seed_summary(db_session, ent_id)

    resp = _apply(client, sid)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] > 0
    assert data["enterprise_id"] == ent_id
    assert data["summary_id"] == sid
    assert data["certificate_no"].startswith("CC-")
    assert data["status"] == "pending"
    assert data["verified_at"] is None
    assert data["trade_volume"] == 0.0
    assert data["trade_price"] == 0.0
    assert data["created_at"]


def test_apply_summary_not_found(client, db_session):
    """汇总不存在 -> 404。"""
    resp = _apply(client, 999999)
    assert resp.status_code == 404


def test_apply_summary_not_verified(client, db_session):
    """汇总未审核(verified=False) -> 400。"""
    ent_id = _seed_enterprise(db_session, code="CC_NV")
    sid = _seed_summary(db_session, ent_id, verified=False)

    resp = _apply(client, sid)
    assert resp.status_code == 400
    assert "审核" in resp.json()["detail"]


def test_apply_duplicate_summary(client, db_session):
    """同一汇总已有有效证书(pending) -> 400。"""
    ent_id = _seed_enterprise(db_session, code="CC_DUP")
    sid = _seed_summary(db_session, ent_id)

    assert _apply(client, sid).status_code == 200
    resp = _apply(client, sid)
    assert resp.status_code == 400
    assert "重复" in resp.json()["detail"] or "已存在" in resp.json()["detail"]


# ======================================================================
# 列表
# ======================================================================

def test_list_filter_by_enterprise_and_status(client, db_session):
    """GET /certificates 按企业+状态筛选, 分页结构正确。"""
    ent_a = _seed_enterprise(db_session, code="CC_LA")
    ent_b = _seed_enterprise(db_session, code="CC_LB")
    sid_a1 = _seed_summary(db_session, ent_a, month=4)
    sid_a2 = _seed_summary(db_session, ent_a, month=5)
    sid_b = _seed_summary(db_session, ent_b, month=4)

    # ent_a: 一张pending, 一张verified
    cid_a1 = _apply(client, sid_a1).json()["data"]["id"]
    cid_a2 = _apply(client, sid_a2).json()["data"]["id"]
    client.patch(f"{_BASE}/{cid_a2}/verify")
    _apply(client, sid_b)  # ent_b 一张pending

    # 按企业筛选
    resp = client.get(f"{_BASE}?enterprise_id={ent_a}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert all(it["enterprise_id"] == ent_a for it in data["items"])

    # 按企业+状态筛选
    resp = client.get(f"{_BASE}?enterprise_id={ent_a}&status=verified")
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["status"] == "verified"
    assert data["items"][0]["id"] == cid_a2


# ======================================================================
# 核证确认
# ======================================================================

def test_verify_certificate(client, db_session):
    """PATCH /{id}/verify pending->verified, verified_at 被记录。"""
    ent_id = _seed_enterprise(db_session, code="CC_V")
    sid = _seed_summary(db_session, ent_id)
    cid = _apply(client, sid).json()["data"]["id"]

    resp = client.patch(f"{_BASE}/{cid}/verify")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "verified"
    assert data["verified_at"] is not None


def test_verify_wrong_status(client, db_session):
    """已traded再核证 -> 400。"""
    ent_id = _seed_enterprise(db_session, code="CC_VS")
    sid = _seed_summary(db_session, ent_id)
    cid = _apply(client, sid).json()["data"]["id"]
    client.patch(f"{_BASE}/{cid}/verify")
    client.patch(f"{_BASE}/{cid}/trade", json={"trade_volume": 50.0, "trade_price": 60.0})

    resp = client.patch(f"{_BASE}/{cid}/verify")
    assert resp.status_code == 400


def test_verify_not_found(client, db_session):
    """核证不存在的证书 -> 404。"""
    resp = client.patch(f"{_BASE}/99999/verify")
    assert resp.status_code == 404


# ======================================================================
# 交易登记
# ======================================================================

def test_trade_certificate(client, db_session):
    """PATCH /{id}/trade verified->traded, 交易量/价落库。"""
    ent_id = _seed_enterprise(db_session, code="CC_T")
    sid = _seed_summary(db_session, ent_id)
    cid = _apply(client, sid).json()["data"]["id"]
    client.patch(f"{_BASE}/{cid}/verify")

    resp = client.patch(f"{_BASE}/{cid}/trade", json={
        "trade_volume": 100.0,
        "trade_price": 65.5,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "traded"
    assert data["trade_volume"] == 100.0
    assert data["trade_price"] == 65.5


def test_trade_without_verify(client, db_session):
    """未核证(pending)直接交易 -> 400。"""
    ent_id = _seed_enterprise(db_session, code="CC_TV")
    sid = _seed_summary(db_session, ent_id)
    cid = _apply(client, sid).json()["data"]["id"]

    resp = client.patch(f"{_BASE}/{cid}/trade", json={
        "trade_volume": 100.0, "trade_price": 65.5,
    })
    assert resp.status_code == 400


# ======================================================================
# 状态流转: 撤销 + 撤销后重新申请
# ======================================================================

def test_cancel_and_reapply(client, db_session):
    """PATCH /{id}/cancel pending->cancelled; 撤销后同汇总可重新申请。"""
    ent_id = _seed_enterprise(db_session, code="CC_CAN")
    sid = _seed_summary(db_session, ent_id)

    cid = _apply(client, sid).json()["data"]["id"]
    resp = client.patch(f"{_BASE}/{cid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"

    # 撤销后该汇总可重新申请
    resp2 = _apply(client, sid)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["id"] != cid
    assert resp2.json()["data"]["status"] == "pending"


# ======================================================================
# 异常路径加固 (卡 f3e5633d)
# ======================================================================

def test_apply_certificate_integrity_conflict(client, db_session, monkeypatch):
    """申请核证遇唯一约束冲突 → 409, 不冒泡 500。"""
    from sqlalchemy.exc import IntegrityError

    ent_id = _seed_enterprise(db_session, code="CC_DUP")
    sid = _seed_summary(db_session, ent_id)

    def _boom(*a, **kw):
        raise IntegrityError("simulated", {}, Exception("UNIQUE"))

    monkeypatch.setattr(db_session, "commit", _boom)

    resp = _apply(client, sid)
    assert resp.status_code == 409


def test_verify_certificate_db_error(client, db_session, monkeypatch):
    """核证确认遇非约束类 DB 异常 → 500, 不泄露原始异常。"""
    ent_id = _seed_enterprise(db_session, code="CC_500")
    sid = _seed_summary(db_session, ent_id)
    cid = client.post(f"{_BASE}/apply", json={"summary_id": sid}).json()["data"]["id"]

    def _boom(*a, **kw):
        raise RuntimeError("DB 连接断开")

    monkeypatch.setattr(db_session, "commit", _boom)

    resp = client.patch(f"{_BASE}/{cid}/verify")
    assert resp.status_code == 500
    assert "DB 连接断开" not in str(resp.json().get("detail", ""))

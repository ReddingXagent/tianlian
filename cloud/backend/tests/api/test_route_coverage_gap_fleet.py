# 卡18885b82: 路由补盲 — /fleet/* 10 端点
# fleet/enterprises/{id}/stations GET/PUT, available-stations;
# fleet/drivers/{id}/account GET, account/recharge POST, transactions GET/POST;
# fleet/carbon/certificates/{id}/verify|trade|cancel PATCH
from datetime import datetime, timezone
from decimal import Decimal

from app.models.carbon_emission import CarbonReductionSummary
from app.models.enterprise import Enterprise
from app.models.fleet_carbon_certificate import (
    FleetCarbonCertificate, CertificateStatus,
)
from app.models.fleet_driver import (
    FleetDriver, FleetDriverAccount, DriverStatus, LicenseType,
    AccountStatus, DriverTransactionType,
)
from app.models.station import Station, StationStatus

DRV = "/api/v1/fleet/drivers"
CERT = "/api/v1/fleet/carbon/certificates"
ENT = "/api/v1/fleet/enterprises"


def _seed_enterprise(s, name="测试企业"):
    ent = Enterprise(name=name, code=f"ENT{abs(hash(name)) % 10**8}")
    s.add(ent)
    s.commit()
    s.refresh(ent)
    return ent


def _seed_driver(s, enterprise_id, name="张三"):
    d = FleetDriver(enterprise_id=enterprise_id, name=name, phone="13800000000",
                    license_no=f"DL{abs(hash(name)) % 10**10}", license_type=LicenseType.C1,
                    status=DriverStatus.ACTIVE)
    s.add(d)
    s.commit()
    s.refresh(d)
    acc = FleetDriverAccount(driver_id=d.id, balance=Decimal("0.00"), status=AccountStatus.ACTIVE)
    s.add(acc)
    s.commit()
    s.refresh(d)
    return d


def _seed_cert(s, enterprise_id, status=CertificateStatus.PENDING):
    summ = CarbonReductionSummary(enterprise_id=enterprise_id, report_year=2026,
                                  report_month=7, verified=True)
    s.add(summ)
    s.flush()
    cert = FleetCarbonCertificate(enterprise_id=enterprise_id, summary_id=summ.id,
                                  certificate_no=f"CC-{summ.id}", status=status)
    s.add(cert)
    s.commit()
    s.refresh(cert)
    return cert


# ─── fleet/enterprises/{id}/stations ───

def test_enterprise_stations_get_put_available(client):
    s = client._sesh
    ent = _seed_enterprise(s)
    sta = Station(name="企业绑定站", code=f"BS{abs(hash('bs')) % 10**8}",
                  address="测试", status=StationStatus.NORMAL)
    s.add(sta)
    s.commit()
    s.refresh(sta)

    r = client.get(f"{ENT}/{ent.id}/stations")
    assert r.status_code == 200
    assert r.json()["data"] == []

    r = client.put(f"{ENT}/{ent.id}/stations", json={"station_ids": [sta.id]})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["data"]] == [sta.id]

    r = client.get(f"{ENT}/{ent.id}/stations")
    assert [x["id"] for x in r.json()["data"]] == [sta.id]

    r = client.get(f"{ENT}/{ent.id}/available-stations")
    assert r.status_code == 200
    assert sta.id in [x["id"] for x in r.json()["data"]]

    assert client.get(f"{ENT}/99999/stations").status_code == 404
    assert client.put(f"{ENT}/99999/stations", json={"station_ids": []}).status_code == 404
    # 绑定不存在的场站 → 422
    assert client.put(f"{ENT}/{ent.id}/stations", json={"station_ids": [99999]}).status_code == 422


# ─── fleet/drivers 账户与交易 ───

def test_driver_account_get_and_recharge(client):
    s = client._sesh
    ent = _seed_enterprise(s)
    d = _seed_driver(s, ent.id)
    r = client.get(f"{DRV}/{d.id}/account")
    assert r.status_code == 200
    assert float(r.json()["data"]["balance"]) == 0.0

    r = client.post(f"{DRV}/{d.id}/account/recharge", json={"amount": 100.5})
    assert r.status_code == 200
    assert float(r.json()["data"]["balance_after"]) == 100.5

    # 错误路径: 金额=0 → 400(端点 amount<=0 校验, ge=0 放行零); 负数 → 422(ge=0 Pydantic前置); 不存在司机 → 404
    assert client.post(f"{DRV}/{d.id}/account/recharge", json={"amount": 0}).status_code == 400
    assert client.post(f"{DRV}/{d.id}/account/recharge", json={"amount": -5}).status_code == 422
    assert client.get(f"{DRV}/99999/account").status_code == 404
    assert client.post(f"{DRV}/99999/account/recharge", json={"amount": 10}).status_code == 404


def test_driver_transactions_list_and_create(client):
    s = client._sesh
    ent = _seed_enterprise(s)
    d = _seed_driver(s, ent.id, name="李四")
    # 先充值供消费
    assert client.post(f"{DRV}/{d.id}/account/recharge", json={"amount": 50}).status_code == 200

    r = client.get(f"{DRV}/{d.id}/transactions")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 1

    r = client.post(f"{DRV}/{d.id}/transactions",
                    json={"type": "consume", "amount": 20, "remark": "充电消费"})
    assert r.status_code == 200
    assert float(r.json()["data"]["balance_after"]) == 30.0
    assert r.json()["data"]["type"] == "consume"

    # 退款
    r = client.post(f"{DRV}/{d.id}/transactions",
                    json={"type": "refund", "amount": 5})
    assert r.status_code == 200
    assert float(r.json()["data"]["balance_after"]) == 35.0

    # 错误路径 (非法type 19664eed9 后由 Literal 前置拦截 → 422)
    assert client.post(f"{DRV}/{d.id}/transactions", json={"type": "bad", "amount": 1}).status_code == 422
    assert client.post(f"{DRV}/{d.id}/transactions", json={"type": "consume", "amount": 9999}).status_code == 400
    assert client.get(f"{DRV}/99999/transactions").status_code == 404


# ─── fleet/carbon/certificates 状态机 ───

def test_certificate_verify_trade_cancel_flow(client):
    s = client._sesh
    ent = _seed_enterprise(s)
    cert = _seed_cert(s, ent.id, CertificateStatus.PENDING)

    # pending → verified
    r = client.patch(f"{CERT}/{cert.id}/verify")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "verified"
    # 重复 verify → 400
    assert client.patch(f"{CERT}/{cert.id}/verify").status_code == 400

    # verified → traded
    r = client.patch(f"{CERT}/{cert.id}/trade",
                     json={"trade_volume": 12.5, "trade_price": 60.0})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "traded"
    assert data["trade_volume"] == 12.5
    # 非 verified → 400
    assert client.patch(f"{CERT}/{cert.id}/trade",
                        json={"trade_volume": 1.0, "trade_price": 10.0}).status_code == 400

    # 已 traded 不可撤销 → 400
    assert client.patch(f"{CERT}/{cert.id}/cancel").status_code == 400

    # 404
    assert client.patch(f"{CERT}/99999/verify").status_code == 404
    assert client.patch(f"{CERT}/99999/trade",
                        json={"trade_volume": 1, "trade_price": 1}).status_code == 404
    assert client.patch(f"{CERT}/99999/cancel").status_code == 404


def test_certificate_cancel_pending_then_reapply_ok(client):
    s = client._sesh
    ent = _seed_enterprise(s, name="碳取消企业")
    cert = _seed_cert(s, ent.id, CertificateStatus.PENDING)
    r = client.patch(f"{CERT}/{cert.id}/cancel")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "cancelled"

"""余额不足/企业删除分支不得丢失 settle 费用 (卡 8772b963)

缺陷: charging_sessions 停止结算流中, settle_charging_session 写费用但
不内部 commit; 企业扣款 InsufficientBalanceError 分支 db.rollback() 把
pending 费用一并回滚 → completed 订单零费用, 设备重试上报走幂等返回
既有单, 费用永不重算, 永久营收漏损。

修复语义 (对齐 business_orders L529-549):
- InsufficientBalanceError: 订单 completed + 费用>0 持久化 + unpaid + 200
  (不再 402 — 现有测试无强 402 断言, 大圣许可切换契约)
- EnterpriseDeletedError: 同款; charging_orders.update_order_status 对应
  路径费用在创建时已 commit (b8895972), 断言 completed+unpaid+费用保留。

持久化验证用 expire_all + 独立会话双保险, 防 identity map 假绿。
"""
import uuid
from decimal import Decimal

import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
)
from app.services.enterprise_balance_service import EnterpriseDeletedError


# ─── helpers ───

def _seed_station_device(s):
    from app.models.device import Device, DeviceStatus, DeviceType
    from app.models.station import Station, StationStatus
    st = Station(
        name=f"余额不足站{uuid.uuid4().hex[:4]}",
        code=f"STIB{uuid.uuid4().hex[:6].upper()}",
        address="测试地址", status=StationStatus.NORMAL,
    )
    s.add(st); s.commit(); s.refresh(st)
    dev = Device(
        sn=f"SNIB{uuid.uuid4().hex[:10]}", name="充电桩",
        code=f"CHIB{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id,
    )
    s.add(dev); s.commit(); s.refresh(dev)
    return st, dev


def _seed_enterprise(s, balance):
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.enterprise_vehicle import EnterpriseVehicle
    vin = f"VINIB{uuid.uuid4().hex[:8].upper()}"
    ent = Enterprise(
        name=f"余额不足企业{uuid.uuid4().hex[:4]}",
        code=f"ENTIB-{uuid.uuid4().hex[:6].upper()}",
        balance=Decimal(str(balance)), credit_limit=Decimal("0"),
        status=EnterpriseStatus.ACTIVE,
    )
    s.add(ent); s.commit(); s.refresh(ent)
    plate = f"京C{uuid.uuid4().hex[:5].upper()}"
    s.add(EnterpriseVehicle(enterprise_id=ent.id, plate_number=plate, vin=vin))
    s.commit()
    return ent, vin, plate


def _post_session(dev_sn, vin, tx=None):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/auth/login",
               data={"username": "admin", "password": "admin123"})
    token = r.json()["data"]["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c.post("/api/v1/charging-sessions", json={
        "charge_point_id": dev_sn,
        "transaction_id": tx or f"TX-IB-{uuid.uuid4().hex[:8]}",
        "id_tag": vin,
        "meter_start": 0,
        "meter_stop": 10000,   # 默认费率: 电费 8 + 服务费 5 = 13
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    })


def _assert_fees_persisted(db_module, order_no):
    """新会话直查, 绕开 identity map (持久化金标准)。"""
    fresh = db_module.SessionLocal()
    try:
        row = fresh.query(ChargingOrder).filter(
            ChargingOrder.order_no == order_no).first()
        assert row is not None, "订单不存在"
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID
        assert row.total_amount and row.total_amount > 0, \
            f"费用被 rollback 抹掉: total_amount={row.total_amount}"
        assert (row.paid_amount or Decimal("0")) > 0, \
            f"settle 费用未持久化: paid_amount={row.paid_amount}"
        return row
    finally:
        fresh.close()


# =====================================================================
# ① charging_sessions 余额不足 → 200 + completed + unpaid + 费用落库
# =====================================================================

class TestChargingSessionsInsufficientBalance:
    def test_insufficient_balance_keeps_fees(self, client, monkeypatch):
        s = client._sesh
        st, dev = _seed_station_device(s)
        ent, vin, plate = _seed_enterprise(s, balance=1)  # 余额 1 < 费用 13

        r = _post_session(dev.sn, vin)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 200, body
        data = body["data"]
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "unpaid"
        assert data["total_amount"] == 13.0

        s.expire_all()
        row = s.query(ChargingOrder).filter(
            ChargingOrder.order_no == data["order_no"]).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID
        assert row.total_amount == Decimal("13.00")
        # 明细同样持久化
        from app.models.order_fee_item import OrderFeeItem, FeeType
        items = s.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == row.id).all()
        assert any(i.fee_type == FeeType.ELECTRICITY for i in items), \
            "费用明细被 rollback 抹掉"
        assert sum(float(i.amount) for i in items
                   if i.fee_type == FeeType.ELECTRICITY) == 8.0

        # 独立会话验证持久化 (防 identity map 假绿)
        import app.core.database as db_module
        _assert_fees_persisted(db_module, data["order_no"])

        # 余额未被扣
        s.refresh(ent)
        assert ent.balance == Decimal("1.00")


# =====================================================================
# ② charging_sessions 企业删除竞态 → 同款断言
# =====================================================================

class TestChargingSessionsEnterpriseDeletedFees:
    def test_deleted_enterprise_keeps_fees(self, client, monkeypatch):
        import app.api.v1.charging_sessions as cs
        s = client._sesh
        st, dev = _seed_station_device(s)
        ent, vin, plate = _seed_enterprise(s, balance=1000)

        def _raise(db, order, enterprise):
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)

        monkeypatch.setattr(cs, "deduct_on_order_complete", _raise)

        r = _post_session(dev.sn, vin)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 200, body
        data = body["data"]
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "unpaid"
        assert data["total_amount"] == 13.0

        s.expire_all()
        row = s.query(ChargingOrder).filter(
            ChargingOrder.order_no == data["order_no"]).first()
        assert row.total_amount == Decimal("13.00"), \
            "企业删除分支 rollback 把 pending 费用抹掉"
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID

        import app.core.database as db_module
        _assert_fees_persisted(db_module, data["order_no"])


# =====================================================================
# ③ charging_orders.update_order_status 余额不足 → completed + unpaid
#    + 创建时已落库的费用保留 (b8895972 语义不破坏)
# =====================================================================

class TestChargingOrdersInsufficientBalance:
    def test_insufficient_balance_status_update_keeps_fees(
        self, client
    ):
        s = client._sesh
        st, dev = _seed_station_device(s)
        ent, vin, plate = _seed_enterprise(s, balance=1)

        # 创建订单: 默认费率 total 13, 创建时已 commit (b8895972)
        r = client.post("/api/v1/charging-orders", json={
            "station_id": st.id, "device_id": dev.id,
            "charged_kwh": 10.0, "duration_minutes": 60,
            "plate_number": plate, "payment_method": "enterprise",
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total_amount"] == 13.0
        oid = data["id"]

        r = client.put(f"/api/v1/charging-orders/{oid}/status",
                       json={"status": "completed"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 200, body
        d = body["data"]
        assert d["order_status"] == "completed"
        assert d["payment_status"] == "unpaid", \
            "余额不足应保持 unpaid 而非 402"
        assert d["total_amount"] == 13.0

        s.expire_all()
        row = s.query(ChargingOrder).filter(ChargingOrder.id == oid).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID
        assert row.total_amount == Decimal("13.00")
        assert row.end_time is not None

        s.refresh(ent)
        assert ent.balance == Decimal("1.00")  # 未扣款

    def test_deleted_enterprise_status_update_keeps_fees(
        self, client, monkeypatch
    ):
        import app.api.v1.charging_orders as co
        s = client._sesh
        st, dev = _seed_station_device(s)
        ent, vin, plate = _seed_enterprise(s, balance=1000)

        def _raise(db, order, enterprise):
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)

        monkeypatch.setattr(co, "deduct_on_order_complete", _raise)

        r = client.post("/api/v1/charging-orders", json={
            "station_id": st.id, "device_id": dev.id,
            "charged_kwh": 10.0, "duration_minutes": 60,
            "plate_number": plate, "payment_method": "enterprise",
        })
        assert r.status_code == 200, r.text
        oid = r.json()["data"]["id"]

        r = client.put(f"/api/v1/charging-orders/{oid}/status",
                       json={"status": "completed"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["order_status"] == "completed"
        assert d["payment_status"] == "unpaid"
        assert d["total_amount"] == 13.0

        s.expire_all()
        row = s.query(ChargingOrder).filter(ChargingOrder.id == oid).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID
        assert row.total_amount == Decimal("13.00")

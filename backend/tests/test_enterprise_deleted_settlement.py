"""企业删除竞态下三结算端点不得 500 (卡 84439ed8)

deduct_on_order_complete 刻意抛 EnterpriseDeletedError (结算前企业行被并发
删除 → with_for_update 锁查 None → 中断防白嫖)。三个 API 调用点原先只
catch InsufficientBalanceError → 异常穿透全局 handler → 500。

修复语义 (与 InsufficientBalanceError 对齐):
- stop_order: rollback 后重放 completed 状态变更 → 订单 completed+unpaid
  (OCPP stop 已 accepted, 不能卡 charging; 用户可IM-B支付)
- charging_sessions / charging_orders: 订单 completed+unpaid + 200 正常响应

模式: monkeypatch 各路由模块的 deduct_on_order_complete 抛
EnterpriseDeletedError, 模拟锁查 None 的删除竞态。
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.station import Station, StationStatus
from app.services.enterprise_balance_service import EnterpriseDeletedError

BASE = "/api/v1/business/orders"


# ─── helpers ───

def _seed_enterprise_with_plate(session, plate):
    """企业车按 VIN 关联 (charging_sessions 经 id_tag=VIN 匹配)。"""
    vin = f"VIN{uuid.uuid4().hex[:10].upper()}"
    ent = Enterprise(
        name=f"删除竞态企业{uuid.uuid4().hex[:4]}",
        code=f"ENT-DEL-{uuid.uuid4().hex[:6].upper()}",
        balance=Decimal("1000"),
        credit_limit=Decimal("0"),
        status=EnterpriseStatus.ACTIVE,
    )
    session.add(ent)
    session.commit()
    session.refresh(ent)
    session.add(EnterpriseVehicle(
        enterprise_id=ent.id, plate_number=plate, vin=vin,
    ))
    session.commit()
    return ent, vin


def _seed_station_device(session):
    st = Station(
        name="删除竞态测试站", code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址", status=StationStatus.NORMAL,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    dev = Device(
        sn=f"SN{uuid.uuid4().hex[:10]}", name="充电桩",
        code=f"CHG{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id, rated_power=120.0, gun_count=2,
    )
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return st, dev


# =====================================================================
# ① business_orders.stop_order — 最重路径: OCPP 已 accepted 不得卡 charging
# =====================================================================

class TestStopOrderEnterpriseDeleted:
    def test_deleted_enterprise_order_completes_unpaid(
        self, client, monkeypatch
    ):
        """企业删除竞态: completed+unpaid + code=0, 绝不 500/卡 charging。"""
        import app.api.v1.business_orders as bo

        s = client._sesh
        from app.models.user import User, UserRole
        import bcrypt
        uname = f"deluser_{uuid.uuid4().hex[:6]}"
        u = User(
            username=uname, real_name=uname, role=UserRole.VIEWER,
            status="active",
            password_hash=bcrypt.hashpw(
                b"pw123456", bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        r = client.post("/api/v1/auth/login",
                        data={"username": uname, "password": "pw123456"})
        token = r.json()["data"]["token"]

        st, dev = _seed_station_device(s)
        plate = f"京B{uuid.uuid4().hex[:5].upper()}"
        _, vin = _seed_enterprise_with_plate(s, plate)
        o = ChargingOrder(
            order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            station_id=st.id, device_id=dev.id, user_id=u.id,
            user_type=UserType.APP, connector_id=1,
            order_status=OrderStatus.CHARGING,
            payment_status=OrderPaymentStatus.UNPAID,
            charged_kwh=Decimal("23.50"),
            total_amount=Decimal("35.25"),
            paid_amount=Decimal("35.25"),
            plate_number=plate,
            start_time=datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),
        )
        s.add(o)
        s.commit()

        def _raise(db, order, enterprise):
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)

        monkeypatch.setattr(bo, "deduct_on_order_complete", _raise)

        r = client.post(
            f"{BASE}/{o.order_no}/stop",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"现状穿透全局 handler → {r.status_code}"
        body = r.json()
        assert body["code"] == 0, body
        data = body["data"]
        assert data["order_status"] == "completed"
        assert data["stop_reason"] == "user_manual"
        assert data["duration_minutes"] is not None

        s.expire_all()
        row = s.query(ChargingOrder).filter(
            ChargingOrder.id == o.id).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID
        assert row.end_time is not None
        assert row.duration_minutes is not None


# =====================================================================
# ② charging_sessions ingestion — 会话照常 completed+unpaid, 200
# =====================================================================

class TestChargingSessionsEnterpriseDeleted:
    def test_deleted_enterprise_session_completes_unpaid(
        self, client, monkeypatch
    ):
        import app.api.v1.charging_sessions as cs

        s = client._sesh
        st, dev = _seed_station_device(s)
        plate = f"京B{uuid.uuid4().hex[:5].upper()}"
        _, vin = _seed_enterprise_with_plate(s, plate)

        def _raise(db, order, enterprise):
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)

        monkeypatch.setattr(cs, "deduct_on_order_complete", _raise)

        r = client.post(
            "/api/v1/charging-sessions",
            json={
                "charge_point_id": dev.sn,
                "transaction_id": f"TX-DEL-{uuid.uuid4().hex[:6]}",
                "id_tag": vin,
                "meter_start": 0,
                "meter_stop": 10000,
                "timestamp_start": "2026-07-28T10:00:00",
                "timestamp_stop": "2026-07-28T11:00:00",
            },
        )
        assert r.status_code == 200, f"现状穿透全局 handler → {r.status_code}"
        body = r.json()
        assert body["code"] == 200, body  # success_response 口径: code=200 表成功
        data = body["data"]
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "unpaid"

        row = s.query(ChargingOrder).filter(
            ChargingOrder.order_no == data["order_no"]).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID


# =====================================================================
# ③ charging_orders.update_order_status — 订单照常完成, 200
# =====================================================================

class TestChargingOrdersEnterpriseDeleted:
    def test_deleted_enterprise_status_update_completes_unpaid(
        self, client, monkeypatch
    ):
        import app.api.v1.charging_orders as co

        s = client._sesh
        st, dev = _seed_station_device(s)
        plate = f"京B{uuid.uuid4().hex[:5].upper()}"
        _, vin = _seed_enterprise_with_plate(s, plate)
        o = ChargingOrder(
            order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            station_id=st.id, device_id=dev.id,
            user_type=UserType.APP, connector_id=1,
            order_status=OrderStatus.CHARGING,
            payment_method="enterprise",
            payment_status=OrderPaymentStatus.UNPAID,
            charged_kwh=Decimal("10"),
            total_amount=Decimal("13"),
            paid_amount=Decimal("13"),
            plate_number=plate,
        )
        s.add(o)
        s.commit()
        s.refresh(o)

        def _raise(db, order, enterprise):
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)

        monkeypatch.setattr(co, "deduct_on_order_complete", _raise)

        r = client.put(
            f"/api/v1/charging-orders/{o.id}/status",
            json={"status": "completed"},
        )
        assert r.status_code == 200, f"现状穿透全局 handler → {r.status_code}"
        body = r.json()
        assert body["code"] == 200, body  # success_response 口径: code=200 表成功
        data = body["data"]
        assert data["order_status"] == "completed"

        s.expire_all()
        row = s.query(ChargingOrder).filter(
            ChargingOrder.id == o.id).first()
        assert row.order_status == OrderStatus.COMPLETED
        assert row.payment_status == OrderPaymentStatus.UNPAID

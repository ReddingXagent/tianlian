"""订单详情 API 测试 — 契约 §7.7 GET /business/orders/{order_id}?detail=full (卡 4b4a502a)

覆盖 app/api/v1/business.py get_order 的 full 分支 (明细构造复用
business_orders.order_full_detail):
- 正常详情: 契约 §7.7 全字段集 + 金额分 + 时间 +08:00
- 他人订单: 200 + biz_error ORDER_NOT_FOUND (卡 418a675a 统一口径, 不泄露存在性)
- 不存在:   同上
- 支付字段口径: transaction_id/paid_at 与 §2.3 同语义 (IM-B交易号/支付完成时间),
  真相源是 PaymentOrder —— ChargingOrder 无 paid_at 列 (payment.py 同步是 no-op),
  transaction_id 列是 OCPP 事务号 (遥测幂等键), 不能进 C 端契约响应。

契约: docs/contracts/user-client-contract.md §7.7 (v1.2), 错误码参照 §7.1-§7.6。
金额: 模型存元(Decimal), 响应是分(整数)。
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    PaymentMethod,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.payment_order import PayScene, PaymentOrder, PaymentStatus
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

BASE = "/api/v1/business/orders"

_CN_TZ = timezone(timedelta(hours=8))


# ─── helpers ───

def _add_user(session, username, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=UserRole.VIEWER,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def c_user(client):
    """C 端用户 (VIEWER) + 登录 token。"""
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    return u, _login_token(client, u.username)


@pytest.fixture
def station_and_device(client):
    st = Station(
        name="甘天地光储充示范站",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
    )
    client._sesh.add(st)
    client._sesh.commit()
    client._sesh.refresh(st)
    dev = Device(
        sn=f"SN{uuid.uuid4().hex[:10]}",
        name="充电桩",
        code=f"CHG{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC,
        status=DeviceStatus.ONLINE,
        station_id=st.id,
        rated_power=120.0,
        gun_count=2,
    )
    client._sesh.add(dev)
    client._sesh.commit()
    client._sesh.refresh(dev)
    return st, dev


def _seed_completed_order(session, *, user_id, station_id, device_id,
                          order_no=None, plate_number="京A12345"):
    """契约 §7.7 示例形态的已完成已支付订单 (费用/时长/SOC 全非默认)。"""
    o = ChargingOrder(
        order_no=order_no or f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=UserType.APP,
        connector_id=1,
        plate_number=plate_number,
        order_status=OrderStatus.COMPLETED,
        payment_status=OrderPaymentStatus.PAID,
        charged_kwh=Decimal("23.50"),
        electricity_fee=Decimal("21.00"),
        service_fee=Decimal("12.00"),
        parking_fee=Decimal("0.00"),
        idle_penalty=Decimal("2.25"),
        total_amount=Decimal("35.25"),
        discount_amount=Decimal("0.00"),
        paid_amount=Decimal("35.25"),
        payment_method=PaymentMethod.WECHAT,
        start_soc=Decimal("35.0"),
        end_soc=Decimal("100.0"),
        duration_minutes=45,
        stop_reason="full",
        start_time=datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),  # 14:31 +08:00
        end_time=datetime(2026, 8, 8, 7, 16, tzinfo=timezone.utc),    # 15:16 +08:00
        transaction_id="OCPP-TX-888",  # OCPP 事务号 (遥测幂等键, 非 C 端契约字段)
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _seed_payment(session, *, order_no, paid=True):
    """订单对应IM-B支付单 (paid_at / wx_transaction_id 真相源)。"""
    po = PaymentOrder(
        out_trade_no=f"TL_{uuid.uuid4().hex[:12]}",
        business_order_no=order_no,
        openid=f"o{uuid.uuid4().hex[:16]}",
        scene=PayScene.MINIPROGRAM,
        sub_mchid="1900000109",
        amount_fen=3525,
        payment_status=PaymentStatus.PAID if paid else PaymentStatus.UNPAID,
        wx_transaction_id="4200001234202608081234567890" if paid else None,
        paid_at=datetime(2026, 8, 8, 7, 18, tzinfo=timezone.utc) if paid else None,  # 15:18 +08:00
    )
    session.add(po)
    session.commit()
    session.refresh(po)
    return po


# =====================================================================
# 契约 §7.7 字段完整性
# =====================================================================

class TestOrderDetailContract:
    def test_detail_full_contract_fields(self, client, c_user, station_and_device):
        """正常详情: 契约 §7.7 响应字段逐项核对 (含 paid_at, 金额分, 时间 +08:00)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_completed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id
        )
        _seed_payment(client._sesh, order_no=o.order_no, paid=True)

        r = client.get(f"{BASE}/{o.order_no}?detail=full", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]

        # 契约 §7.7 字段全集 (一个不少)
        expected_keys = {
            "order_id", "order_status", "payment_status", "station_id",
            "station_name", "device_id", "connector_id", "user_type",
            "plate_number", "charged_kwh", "electricity_fee", "service_fee",
            "parking_fee", "idle_penalty", "total_amount", "discount_amount",
            "paid_amount", "payment_method", "start_time", "end_time",
            "duration_minutes", "start_soc", "end_soc", "stop_reason",
            "transaction_id", "paid_at", "created_at",
        }
        assert expected_keys <= set(data.keys()), (
            f"缺失字段: {expected_keys - set(data.keys())}"
        )

        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "paid"
        assert data["station_id"] == st.id
        assert data["station_name"] == st.name
        assert data["device_id"] == dev.id
        assert data["connector_id"] == 1
        assert data["user_type"] == "app"
        assert data["plate_number"] == "京A12345"
        assert data["charged_kwh"] == 23.50
        # 金额为分 (整数)
        assert data["electricity_fee"] == 2100
        assert data["service_fee"] == 1200
        assert data["parking_fee"] == 0
        assert data["idle_penalty"] == 225
        assert data["total_amount"] == 3525
        assert data["discount_amount"] == 0
        assert data["paid_amount"] == 3525
        assert data["payment_method"] == "im_b"
        assert data["duration_minutes"] == 45
        assert data["start_soc"] == 35.0
        assert data["end_soc"] == 100.0
        assert data["stop_reason"] == "full"
        # 时间 ISO8601 +08:00
        assert data["start_time"] == "2026-08-08T14:31:00+08:00"
        assert data["end_time"] == "2026-08-08T15:16:00+08:00"
        assert data["created_at"].endswith("+08:00")

        # 支付字段与 §2.3 同语义: IM-B交易号 + 支付完成时间 (真相源 PaymentOrder)
        assert data["transaction_id"] == "4200001234202608081234567890"
        assert data["paid_at"] == "2026-08-08T15:18:00+08:00"

    def test_detail_no_payment_record(self, client, c_user, station_and_device):
        """无IM-B支付单 (如企业余额自动扣款): paid_at/transaction_id 为 null, 不崩。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_completed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id
        )
        r = client.get(f"{BASE}/{o.order_no}?detail=full", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["order_id"] == o.order_no
        assert data["paid_at"] is None
        assert data["transaction_id"] is None


# =====================================================================
# 归属校验 (参照 §7.4 user scoping)
# =====================================================================

class TestOrderDetailOwnership:
    def test_other_user_order_not_found(self, client, station_and_device):
        """他人订单 → 200 + code!=0 ORDER_NOT_FOUND (卡 418a675a 统一口径,
        与 403/404 HTTP 语义等价的防枚举实现, 不泄露订单存在性)。"""
        st, dev = station_and_device
        owner = _add_user(client._sesh, f"owner_{uuid.uuid4().hex[:6]}")
        intruder = _add_user(client._sesh, f"intruder_{uuid.uuid4().hex[:6]}")
        token_intruder = _login_token(client, intruder.username)
        o = _seed_completed_order(
            client._sesh, user_id=owner.id, station_id=st.id, device_id=dev.id
        )
        _seed_payment(client._sesh, order_no=o.order_no, paid=True)

        r = client.get(f"{BASE}/{o.order_no}?detail=full",
                       headers=_auth(token_intruder))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_order_not_exist(self, client, c_user):
        """订单不存在 → 同 ORDER_NOT_FOUND (与他人订单响应无差别)。"""
        _, token = c_user
        r = client.get(f"{BASE}/TL00000000000000NOPE?detail=full",
                       headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_no_auth_rejected(self, anon_client, client, c_user, station_and_device):
        """未认证 → 401 (不落入业务错误)。注意须用 anon_client:
        conftest autouse 会给 client 注入 token, 匿名场景不能用。"""
        u, _ = c_user
        st, dev = station_and_device
        o = _seed_completed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id
        )
        r = anon_client.get(f"{BASE}/{o.order_no}?detail=full")
        assert r.status_code == 401

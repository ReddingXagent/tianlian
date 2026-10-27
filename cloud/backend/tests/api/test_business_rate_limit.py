"""C 端 /business/* 限流 + 输入校验加固测试 (卡 d6e415b7)

覆盖 app/api/v1/business_orders.py / business_invoices.py / business.py:
  限流 (conftest 默认关闭, 本文件 monkeypatch 开启 limiter):
    ① POST /business/orders          超 30/min → 429
    ② GET  /business/orders/{id}/status 超 60/min → 429
    ③ POST /business/invoices        超 30/min → 429
  输入校验 (Pydantic, 限流无关):
    ④ 无效 user_type ('hack')         → 422
    ⑤ station_id=0 / device_id=-1    → 422
    ⑥ order_ids 超过 50 个            → 422
"""
import uuid

import bcrypt
import pytest
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

ORDERS = "/api/v1/business/orders"
INVOICES = "/api/v1/business/invoices"


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
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station_and_device(session):
    st = Station(
        name=f"限流站{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
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
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return st, dev


def _seed_order(session, *, user_id, station_id, device_id, connector_id=1,
                order_status=OrderStatus.PENDING, order_no=None):
    o = ChargingOrder(
        order_no=order_no or f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=UserType.APP,
        connector_id=connector_id,
        order_status=order_status,
        payment_status=OrderPaymentStatus.UNPAID,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


@pytest.fixture
def enable_rate_limit(client: TestClient, monkeypatch):
    """开启 limiter 并为 conftest app 补齐 SlowAPI handler (RateLimitExceeded → 429)。

    复用 test_auth_rate_limit.py 的既定模式。每用例前 reset 清内存计数残留。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    yield
    limiter.reset()


@pytest.fixture
def c_user(client):
    """C 端 VIEWER 用户 + token。"""
    u = _add_user(client._sesh, f"rl_user_{uuid.uuid4().hex[:6]}")
    token = _login_token(client, u.username)
    return u, token


# =====================================================================
# ① POST /business/orders 超 30/min → 429
# =====================================================================

def test_create_order_rate_limit_429(client, enable_rate_limit, c_user):
    """创建订单限流 30/min per real IP: 第 31 次返回 429。

    端点参数校验通过后才会落库 (此处 body 有效, 前 30 次因 EXISTING_ORDER / CONNECTOR_BUSY
    等业务码返回非 429; 不关心业务结果, 只断言前 30 次未限流、第 31 次 429)。
    """
    _, token = c_user
    st, dev = _seed_station_and_device(client._sesh)
    payload = {
        "station_id": st.id,
        "device_id": dev.id,
        "connector_id": 1,
        "user_type": "app",
    }
    headers = _auth(token)
    codes = []
    for _ in range(31):
        r = client.post(ORDERS, json=payload, headers=headers)
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


# =====================================================================
# ② GET /business/orders/{id}/status 超 60/min → 429
# =====================================================================

def test_order_status_rate_limit_429(client, enable_rate_limit, c_user):
    """订单实时状态限流 60/min: 第 61 次返回 429 (高频轮询端点)。"""
    u, token = c_user
    st, dev = _seed_station_and_device(client._sesh)
    order = _seed_order(
        client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
        order_status=OrderStatus.CHARGING,
    )
    headers = _auth(token)
    codes = []
    for _ in range(61):
        r = client.get(f"{ORDERS}/{order.order_no}/status", headers=headers)
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


# =====================================================================
# ③ POST /business/invoices 超 30/min → 429
# =====================================================================

def test_invoices_rate_limit_429(client, enable_rate_limit, c_user):
    """开票申请限流 30/min: 第 31 次返回 429。

    用非法 order_id 触发 422 (限流装饰器在端点执行前消耗配额, 422 也计数),
    避免污染真实 InvoiceRequest 状态机。
    """
    _, token = c_user
    headers = _auth(token)
    payload = {
        "order_ids": ["NON_EXISTENT_ORDER"],
        "title_type": "personal",
        "title_name": "测试抬头",
    }
    codes = []
    for _ in range(31):
        r = client.post(INVOICES, json=payload, headers=headers)
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


# =====================================================================
# ③-b POST /business/invoices/{id}/send-email 限 9/hour 按用户 (卡 71062d84)
# =====================================================================

def test_send_email_rate_limit_9_per_hour_per_user(client, enable_rate_limit, monkeypatch):
    """补发邮件限流收紧: 9/hour 按用户维度 (原 30/min=1800封/小时可刷爆 SMTP)。

    key_func 在端点体前执行, 靠解 Authorization token 的 sub 识别用户 →
    同 IP 不同用户配额独立; 第 10 次 429。用 404 invoice_id 触发业务
    异常 (限流装饰器先于端点执行, 404 也计数), 不污染真实状态机。
    """
    u = _add_user(client._sesh, f"rl_inv_{uuid.uuid4().hex[:6]}")
    token = _login_token(client, u.username)
    headers = _auth(token)
    codes = []
    for _ in range(10):
        r = client.post(
            f"{INVOICES}/999999/send-email",
            json={"email": "a@b.com"},
            headers=headers,
        )
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:9]), f"前 9 次不应限流, 实际: {codes}"
    assert codes[9] == 429, f"第 10 次应 429, 实际: {codes}"

    # 用户维度: 同 IP 另一用户配额独立, 不被前者挤占
    other = _add_user(client._sesh, f"rl_inv2_{uuid.uuid4().hex[:6]}")
    other_token = _login_token(client, other.username)
    r = client.post(
        f"{INVOICES}/999999/send-email",
        json={"email": "a@b.com"},
        headers=_auth(other_token),
    )
    assert r.status_code != 429, "同 IP 另一用户不应共享 9/hour 配额"

def test_invalid_user_type_rejected_422(client, c_user):
    """user_type 改为 Literal['app','card']: 'hack' 等 非 enum 值 → 422。"""
    _, token = c_user
    st, dev = _seed_station_and_device(client._sesh)
    payload = {
        "station_id": st.id,
        "device_id": dev.id,
        "connector_id": 1,
        "user_type": "hack",
    }
    r = client.post(ORDERS, json=payload, headers=_auth(token))
    assert r.status_code == 422, f"非法 user_type 应 422, 实际 {r.status_code}: {r.text[:200]}"


# =====================================================================
# ⑤ station_id=0 / device_id=-1 → 422
# =====================================================================

def test_station_id_zero_rejected_422(client, c_user):
    """station_id 加 ge=1: 0 → 422。"""
    _, token = c_user
    payload = {
        "station_id": 0,
        "device_id": 1,
        "connector_id": 1,
        "user_type": "app",
    }
    r = client.post(ORDERS, json=payload, headers=_auth(token))
    assert r.status_code == 422, f"station_id=0 应 422, 实际 {r.status_code}"


def test_device_id_negative_rejected_422(client, c_user):
    """device_id 加 ge=1: -1 → 422。"""
    _, token = c_user
    payload = {
        "station_id": 1,
        "device_id": -1,
        "connector_id": 1,
        "user_type": "app",
    }
    r = client.post(ORDERS, json=payload, headers=_auth(token))
    assert r.status_code == 422, f"device_id=-1 应 422, 实际 {r.status_code}"


# =====================================================================
# ⑥ order_ids 超过 50 个 → 422
# =====================================================================

def test_invoice_order_ids_over_50_rejected_422(client, c_user):
    """InvoiceApplyRequest.order_ids 加 max_length=50: 51 个 → 422。"""
    _, token = c_user
    payload = {
        "order_ids": [f"TL{i:050d}" for i in range(51)],
        "title_type": "personal",
        "title_name": "测试抬头",
    }
    r = client.post(INVOICES, json=payload, headers=_auth(token))
    assert r.status_code == 422, f"order_ids 超 50 应 422, 实际 {r.status_code}: {r.text[:200]}"

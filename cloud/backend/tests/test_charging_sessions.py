"""
充电交易 ingestion 端点测试 (d018e3dc)

覆盖 POST /api/v1/charging-sessions (app/api/v1/charging_sessions.py):
① 跨尖峰平谷时段会话 → 订单 + 电费 TOU 拆分明细正确
② 幂等: 同 transaction_id 二次上报不重建
③ 无定价 → 默认费率兜底不崩
④ VIN 匹配企业车辆 → 企业余额扣减
⑤ 无 token → 401

认证/DB 模式参考 test_charging_orders.py (module-level client + test_db autouse)。
计费全程 Decimal; 断言落在真实费用数值与明细行, 禁弱断言。
"""
import pytest
from decimal import Decimal
from datetime import date, time

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


def _auth_headers():
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


# ─── 种子 helpers ───

def _seed_station_device(session, sn="CP-TEST-001"):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    st = Station(name="ingestion测试站", code="STCS001", address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    dev = Device(sn=sn, name="测试桩", code="CP001", type=DeviceType.CHARGER_DC,
                 status=DeviceStatus.ONLINE, station_id=st.id)
    session.add(dev); session.commit(); session.refresh(dev)
    return st, dev


def _seed_tou_pricing(session, station_id):
    """尖峰平谷定价: flat 08-12 @0.6, peak 12-16 @1.0; 服务费 app 0.5/kWh"""
    from app.models.pricing_v2 import (
        TimeSlotDefinition, EnergyPrice, ServiceFeePrice,
        PeriodType, UserType as PUserType, FeeType as PFeeType,
    )
    flat_slot = TimeSlotDefinition(name="平", period_type=PeriodType.FLAT,
                                   start_time=time(8, 0), end_time=time(12, 0),
                                   is_active=True)
    peak_slot = TimeSlotDefinition(name="峰", period_type=PeriodType.PEAK,
                                   start_time=time(12, 0), end_time=time(16, 0),
                                   is_active=True)
    session.add_all([flat_slot, peak_slot]); session.commit()
    session.refresh(flat_slot); session.refresh(peak_slot)
    session.add_all([
        EnergyPrice(station_id=station_id, slot_id=flat_slot.id,
                    price_per_kwh=Decimal("0.6"), effective_date=date(2026, 1, 1),
                    is_active=True),
        EnergyPrice(station_id=station_id, slot_id=peak_slot.id,
                    price_per_kwh=Decimal("1.0"), effective_date=date(2026, 1, 1),
                    is_active=True),
        ServiceFeePrice(station_id=station_id, user_type=PUserType.APP,
                        fee_type=PFeeType.PERCENT, fee_value=Decimal("0.5"),
                        effective_date=date(2026, 1, 1), is_active=True),
    ])
    session.commit()
    return flat_slot, peak_slot


# ═══════════════════════════════════════════════════════════════
# ① 跨尖峰平谷时段 → TOU 电费拆分
# ═══════════════════════════════════════════════════════════════

def test_tou_split_across_periods(test_db):
    """10:00-14:00 = 4h, 40kWh: flat 10-12(2h→20kWh@0.6=12) + peak 12-14(2h→20kWh@1.0=20) = 32"""
    s = test_db["session"]
    st, dev = _seed_station_device(s)
    _seed_tou_pricing(s, st.id)

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-TOU-001",
        "meter_start": 0,
        "meter_stop": 40000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T14:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["charged_kwh"] == 40.0
    assert data["electricity_fee"] == 32.0          # 12 + 20
    assert data["service_fee"] == 20.0              # 40 * 0.5
    assert data["total_amount"] == 52.0
    assert data["order_status"] == "completed"

    # 明细: 2 条分时电费(flat/peak) + 1 条服务费
    from app.models.order_fee_item import OrderFeeItem, FeeType
    items = s.query(OrderFeeItem).filter(OrderFeeItem.order_id == data["id"]).all()
    elec = [i for i in items if i.fee_type == FeeType.ELECTRICITY]
    assert len(elec) == 2
    names = {i.fee_name for i in elec}
    assert any("flat" in n for n in names)
    assert any("peak" in n for n in names)
    assert sum(float(i.amount) for i in elec) == 32.0
    assert any(i.fee_type == FeeType.SERVICE for i in items)


# ═══════════════════════════════════════════════════════════════
# ② 幂等: 同 transaction_id 二次上报不重建
# ═══════════════════════════════════════════════════════════════

def test_idempotent_duplicate_report(test_db):
    s = test_db["session"]
    _seed_station_device(s)
    payload = {
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-IDEM-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }
    r1 = client.post("/api/v1/charging-sessions", json=payload, headers=_auth_headers())
    assert r1.status_code == 200, r1.text
    order_no_1 = r1.json()["data"]["order_no"]

    r2 = client.post("/api/v1/charging-sessions", json=payload, headers=_auth_headers())
    assert r2.status_code == 200
    assert r2.json()["data"]["order_no"] == order_no_1  # 同一单

    from app.models.charging_order import ChargingOrder
    count = s.query(ChargingOrder).filter(
        ChargingOrder.transaction_id == "TX-IDEM-001"
    ).count()
    assert count == 1


# ═══════════════════════════════════════════════════════════════
# ③ 无定价 → 默认费率兜底不崩
# ═══════════════════════════════════════════════════════════════

def test_default_pricing_fallback(test_db):
    """无 pricing_v2 数据: 电费 10*0.8=8, 服务费 10*0.5=5, total 13"""
    s = test_db["session"]
    _seed_station_device(s)  # 不 seed 任何定价

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-DEF-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["electricity_fee"] == 8.0
    assert data["service_fee"] == 5.0
    assert data["total_amount"] == 13.0
    assert data["order_status"] == "completed"


# ═══════════════════════════════════════════════════════════════
# ④ VIN 匹配企业车辆 → 企业余额扣减
# ═══════════════════════════════════════════════════════════════

def test_vin_match_enterprise_deduction(test_db):
    s = test_db["session"]
    _seed_station_device(s)
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.enterprise_vehicle import EnterpriseVehicle
    ent = Enterprise(name="ingestion测试企业", code="ENT-CS-001",
                     balance=Decimal("1000"), credit_limit=Decimal("0"),
                     status=EnterpriseStatus.ACTIVE)
    s.add(ent); s.commit(); s.refresh(ent)
    s.add(EnterpriseVehicle(enterprise_id=ent.id, plate_number="京A99999",
                            vin="VINENT001"))
    s.commit()

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-ENT-001",
        "id_tag": "VINENT001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # 默认费率: paid 13; 企业扣款 → payment_method=enterprise, paid
    assert data["payment_method"] == "enterprise"
    assert data["payment_status"] == "paid"
    assert data["paid_amount"] == 13.0

    s.refresh(ent)
    assert ent.balance == Decimal("987.00")          # 1000 - 13


# ═══════════════════════════════════════════════════════════════
# ⑤ 无 token → 401
# ═══════════════════════════════════════════════════════════════

def test_unauthorized_rejected(test_db):
    _seed_station_device(test_db["session"])
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token
    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-AUTH-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    })
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# ⑥ 并发竞态: INSERT 撞 UNIQUE(IntegrityError) + 既有单存在 → 200 复用
# ═══════════════════════════════════════════════════════════════

def _patch_commit_to_raise_once(monkeypatch, before_raise=None):
    """让 Session.commit 首次抛 IntegrityError(模拟撞 idx_co_tx_device UNIQUE), 之后恢复原行为。

    并发下两请求同时过前置查询(都 None) → 都 INSERT → 第二个撞唯一索引 → IntegrityError。
    单线程复现该时序: before_raise 在"抛错前"把对手单真实落库, 使前置查询仍为 None(走到 INSERT),
    而 except 内回查时对手单已可见。与真实唯一索引冲突语义一致。
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    real_commit = Session.commit
    raised = {"v": False}

    def fake_commit(self):
        if not raised["v"]:
            raised["v"] = True  # 先置位, 防止 before_raise 内 s.commit() 递归再抛
            if before_raise is not None:
                before_raise()
            raise IntegrityError(
                "INSERT INTO charging_orders ... UNIQUE(idx_co_tx_device)",
                {},
                Exception("UNIQUE constraint failed: idx_co_tx_device"),
            )
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", fake_commit)


def test_concurrent_integrity_returns_existing(test_db, monkeypatch):
    """并发下第二个 INSERT 撞唯一索引, 回查到既有单 → 200 复用, 调用方无感。"""
    headers = _auth_headers()  # patch 前取 token, 避免 login commit 被拦截
    s = test_db["session"]
    st, dev = _seed_station_device(s)

    from datetime import datetime
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus,
    )
    opponent = {"order": None}

    def opponent_wins():
        # 竞态对手在"前置查询之后、本请求 commit 之前"抢先落库同 transaction_id+device 单
        opp = ChargingOrder(
            order_no="RACE-WINNER",
            station_id=st.id,
            device_id=dev.id,
            transaction_id="TX-RACE-001",
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.UNPAID,
            start_time=datetime(2026, 7, 28, 10, 0, 0),
            end_time=datetime(2026, 7, 28, 11, 0, 0),
            charged_kwh=Decimal("10.00"),
        )
        s.add(opp)
        s.commit()      # raised 已置位 → 走 real_commit, 对手单真实落库
        s.refresh(opp)
        opponent["order"] = opp

    _patch_commit_to_raise_once(monkeypatch, before_raise=opponent_wins)

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-RACE-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=headers)

    assert resp.status_code == 200, resp.text
    assert opponent["order"] is not None
    assert resp.json()["data"]["order_no"] == opponent["order"].order_no  # 复用对手单
    # 未重建: 全库仅对手那一单(本请求 INSERT 被 IntegrityError 拦下)
    count = s.query(ChargingOrder).filter(
        ChargingOrder.transaction_id == "TX-RACE-001"
    ).count()
    assert count == 1


# ═══════════════════════════════════════════════════════════════
# ⑦ 并发竞态: IntegrityError + 回查不到既有单 → 409(非 500)
# ═══════════════════════════════════════════════════════════════

def test_concurrent_integrity_no_existing_returns_409(test_db, monkeypatch):
    """INSERT 撞 UNIQUE 但回查不到既有单(如被删) → 409 明确 detail, 禁裸 500。"""
    headers = _auth_headers()
    s = test_db["session"]
    _seed_station_device(s)
    # 不预置任何同 transaction_id 的单 → 回查必然落空

    _patch_commit_to_raise_once(monkeypatch)

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-RACE-404",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=headers)

    assert resp.status_code != 500, "并发冲突不得裸抛 500"
    assert resp.status_code == 409, resp.text
    body = resp.json()
    msg = body.get("message") or body.get("detail") or ""
    assert "conflict" in msg.lower() or "existing" in msg.lower(), resp.text


# ═══════════════════════════════════════════════════════════════
# ⑧ naive/aware 混传时长计算不崩 (缺陷3)
# ═══════════════════════════════════════════════════════════════

def test_mixed_naive_aware_timestamps_no_crash(test_db):
    """timestamp_start/stop 混传 aware/naive → (stop-start).total_seconds() 旧实现 TypeError → 500。

    归一为 aware biz-tz 后正常计时长返回 200。校验时长: naive 上海 10:00 ~
    aware UTC 03:00(= 上海 11:00) = 1h = 60min(naive 按 biz 时区解释, aware 转 biz 时区)。
    """
    s = test_db["session"]
    _seed_station_device(s)
    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-TEST-001",
        "transaction_id": "TX-TZ-MIX-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",       # naive → 按上海解释
        "timestamp_stop": "2026-07-28T03:00:00+00:00",  # aware UTC → 上海 11:00
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text  # 旧实现此处 500(TypeError)

    from app.models.charging_order import ChargingOrder
    order = s.query(ChargingOrder).filter(
        ChargingOrder.transaction_id == "TX-TZ-MIX-001"
    ).first()
    assert order is not None
    # naive(上海10:00) 与 aware(UTC03:00=上海11:00) 归一后差 1h = 60min
    assert order.duration_minutes == 60


# ═══════════════════════════════════════════════════════════════
# ⑨ 卡 e18ce31e: 订单已 cancelled → StartTransaction 上报丢弃 + 审计
# ═══════════════════════════════════════════════════════════════

def test_starttransaction_discarded_when_order_cancelled(test_db, caplog):
    """d) 桩物理启动后的 StartTransaction 上报, 该桩枪上已有 cancelled 的 pending 单
    (取消时 RemoteStop 未及时撤销桩侧启动) → 丢弃 session 不建 completed 单,
    warning 审计 (订单号/充电桩/remote_stop_pending_cancel), 不转 charging。"""
    import logging
    from datetime import datetime, timezone, timedelta
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus,
    )

    s = test_db["session"]
    st, dev = _seed_station_device(s, sn="CP-CANCEL-001")
    now = datetime.now(timezone.utc)
    cancelled = ChargingOrder(
        order_no="TL-CANCEL-001",
        station_id=st.id, device_id=dev.id, connector_id=1,
        order_status=OrderStatus.CANCELLED,
        payment_status=OrderPaymentStatus.UNPAID,
        created_at=now - timedelta(minutes=2),
        end_time=now - timedelta(minutes=1),
    )
    s.add(cancelled)
    s.commit()

    ts_start = (now - timedelta(seconds=30)).isoformat()
    ts_stop = (now + timedelta(minutes=30)).isoformat()
    with caplog.at_level(logging.WARNING, logger="app.api.v1.charging_sessions"):
        resp = client.post("/api/v1/charging-sessions", json={
            "charge_point_id": "CP-CANCEL-001",
            "transaction_id": "TX-CANCEL-001",
            "connector_id": 1,
            "meter_start": 0,
            "meter_stop": 5000,
            "timestamp_start": ts_start,
            "timestamp_stop": ts_stop,
        }, headers=_auth_headers())

    assert resp.status_code == 200, resp.text
    # 不建 completed 单 (归属不悬空)
    count = s.query(ChargingOrder).filter(
        ChargingOrder.transaction_id == "TX-CANCEL-001"
    ).count()
    assert count == 0
    # warning 审计日志含订单号 / 充电桩 / 原因
    msgs = [r.message for r in caplog.records]
    assert any(
        "remote_stop_pending_cancel" in m
        and "TL-CANCEL-001" in m
        and "CP-CANCEL-001" in m
        for m in msgs
    ), msgs


def test_starttransaction_accepted_when_no_cancelled_sibling(test_db):
    """无 cancelled 单时 session 照常建 completed 单 (识别逻辑不误伤正常流程)。"""
    from app.models.charging_order import ChargingOrder

    s = test_db["session"]
    _seed_station_device(s, sn="CP-OK-001")
    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-OK-001",
        "transaction_id": "TX-OK-001",
        "meter_start": 0,
        "meter_stop": 10000,
        "timestamp_start": "2026-07-28T10:00:00",
        "timestamp_stop": "2026-07-28T11:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["order_status"] == "completed"
    assert s.query(ChargingOrder).filter(
        ChargingOrder.transaction_id == "TX-OK-001"
    ).count() == 1

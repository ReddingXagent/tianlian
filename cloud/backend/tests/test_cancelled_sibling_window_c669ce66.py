"""
卡 c669ce66 回归: _find_cancelled_pending_sibling 时间窗 SQL 下推

原实现 (卡 e18ce31e 引入) 查询无 created_at 下界, order_by(...).all() 把该设备
全部历史 CANCELLED 单拉入内存逐条 Python 比较 600s 窗口 —— StartTransaction
ingest 每次上报都调用, 历史取消单无界累积时 O(历史取消单数) 劣化。

修复后时间窗下推 SQL: created_at ∈ [ts_naive_utc-600s, ts_naive_utc] (闭区间,
naive-UTC 绑定), order_by(created_at.desc()).first() 取最近一条。

本文件锁定窗口边界/排序/connector 过滤/tz 归一语义, 证明行为与原 Python 循环
严格等价 —— 尤其"远早于窗口的历史取消单不命中"(原实现也如此, 但靠全量扫描)。
fixture/风格参考 tests/test_charging_sessions.py 中 e18ce31e 相关测试。
"""
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


# 固定基准时刻 (aware UTC), 测试不依赖 now(), 完全确定性
TS = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
# 同一物理时刻的上海(+8)墙钟 — 验证 aware 非 UTC 入参的 naive-UTC 归一口径
TS_SH = datetime(2026, 8, 27, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))


# ─── 种子 helpers ───

def _seed_device(session, sn):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    st = Station(name="c669ce66测试站", code=f"ST{sn[-6:]}", address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    dev = Device(sn=sn, name="测试桩", code=sn[-4:], type=DeviceType.CHARGER_DC,
                 status=DeviceStatus.ONLINE, station_id=st.id)
    session.add(dev); session.commit(); session.refresh(dev)
    return st, dev


def _cancelled_order(session, station_id, device_id, order_no,
                     created_at_naive, connector_id=1):
    """种一条 CANCELLED 订单, created_at 显式传 naive-UTC (SQLite 落库口径)。"""
    from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
    o = ChargingOrder(
        order_no=order_no,
        station_id=station_id, device_id=device_id, connector_id=connector_id,
        order_status=OrderStatus.CANCELLED,
        payment_status=OrderPaymentStatus.UNPAID,
        created_at=created_at_naive,
        end_time=created_at_naive + timedelta(minutes=1),
    )
    session.add(o); session.commit()
    return o


def _find(session, device, connector_id, ts_start):
    from app.api.v1.charging_sessions import _find_cancelled_pending_sibling
    return _find_cancelled_pending_sibling(session, device.id, connector_id, ts_start)


def _naive_utc(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _auth_headers():
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# 窗口内/外 命中语义
# ═══════════════════════════════════════════════════════════════

def test_hit_inside_window(test_db):
    """窗口内命中: created_at = ts-120s (< 600s) → 返回该单。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-HIT-001")
    _cancelled_order(s, st.id, dev.id, "TL-C669-HIT",
                     _naive_utc(TS - timedelta(seconds=120)))
    found = _find(s, dev, 1, TS)
    assert found is not None and found.order_no == "TL-C669-HIT"


def test_miss_created_far_before_window(test_db):
    """关键用例: 历史取消单远早于 ts-600s → 不命中。

    含 30 天前(远期)与 ts-601s(刚出窗 1s)两级, 证明 SQL 下界过滤后不再扫
    历史全量, 且窗口边界语义与原 Python 循环一致。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-OLD-001")
    _cancelled_order(s, st.id, dev.id, "TL-C669-OLD-30D",
                     _naive_utc(TS - timedelta(days=30)))
    _cancelled_order(s, st.id, dev.id, "TL-C669-OLD-601",
                     _naive_utc(TS - timedelta(seconds=601)))
    assert _find(s, dev, 1, TS) is None


def test_miss_created_after_ts(test_db):
    """窗口外不命中: created_at 晚于 ts_start (取消单后于 session 开始存在)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-FUT-001")
    _cancelled_order(s, st.id, dev.id, "TL-C669-FUT",
                     _naive_utc(TS + timedelta(seconds=30)))
    assert _find(s, dev, 1, TS) is None


def test_multiple_in_window_picks_latest(test_db):
    """多候选都在窗口内 → 取 created_at 最近一条 (原循环 desc 首个命中者)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-MULTI01")
    _cancelled_order(s, st.id, dev.id, "TL-C669-M1",
                     _naive_utc(TS - timedelta(seconds=500)))
    _cancelled_order(s, st.id, dev.id, "TL-C669-M2",
                     _naive_utc(TS - timedelta(seconds=100)))
    _cancelled_order(s, st.id, dev.id, "TL-C669-M3",
                     _naive_utc(TS - timedelta(seconds=300)))
    found = _find(s, dev, 1, TS)
    assert found is not None and found.order_no == "TL-C669-M2"


def test_window_boundary_lower_edge_hits(test_db):
    """闭区间下边界: created_at == ts-600s → 命中 (原实现 ts==created+600s 亦命中)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-EDGE-LO")
    _cancelled_order(s, st.id, dev.id, "TL-C669-EDGE-LO",
                     _naive_utc(TS - timedelta(seconds=600)))
    found = _find(s, dev, 1, TS)
    assert found is not None and found.order_no == "TL-C669-EDGE-LO"


def test_window_boundary_upper_edge_hits(test_db):
    """闭区间上边界: created_at == ts → 命中 (原实现 created<=ts 亦命中)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-EDGE-HI")
    _cancelled_order(s, st.id, dev.id, "TL-C669-EDGE-HI",
                     _naive_utc(TS))
    found = _find(s, dev, 1, TS)
    assert found is not None and found.order_no == "TL-C669-EDGE-HI"


# ═══════════════════════════════════════════════════════════════
# tz 口径: aware 非 UTC 入参必须先归一 naive-UTC 再绑 SQL
# ═══════════════════════════════════════════════════════════════

def test_aware_non_utc_ts_normalized(test_db):
    """aware 上海(+8)时刻 = TS 同一物理时刻: 以 TS_SH 查询必须命中 TS 时刻建的取消单。

    若 aware datetime 未归一直接绑 SQL, +8 偏移会造成 8h 窗口错位 → 漏命中。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-TZSH-01")
    _cancelled_order(s, st.id, dev.id, "TL-C669-TZSH",
                     _naive_utc(TS - timedelta(seconds=60)))
    found = _find(s, dev, 1, TS_SH)
    assert found is not None and found.order_no == "TL-C669-TZSH"


# ═══════════════════════════════════════════════════════════════
# connector_id 过滤行为不变
# ═══════════════════════════════════════════════════════════════

def test_connector_filter_excludes_other_connector(test_db):
    """不同 connector 的取消单不命中 (connector_id=2 的单, 按 connector 1 查 → None)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-CONN-01")
    _cancelled_order(s, st.id, dev.id, "TL-C669-CONN2",
                     _naive_utc(TS - timedelta(seconds=60)), connector_id=2)
    assert _find(s, dev, 1, TS) is None


def test_connector_none_matches_any_connector(test_db):
    """connector_id=None 时不过滤 connector (任意枪的窗口内取消单均可命中)。"""
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-CONN-02")
    _cancelled_order(s, st.id, dev.id, "TL-C669-CONN-ANY",
                     _naive_utc(TS - timedelta(seconds=60)), connector_id=2)
    found = _find(s, dev, None, TS)
    assert found is not None and found.order_no == "TL-C669-CONN-ANY"


# ═══════════════════════════════════════════════════════════════
# 端到端等价性: 历史取消单不误伤正常 ingest
# ═══════════════════════════════════════════════════════════════

def test_api_far_past_cancelled_still_accepted(test_db):
    """端到端: 30 天前的取消单不影响新 session 建 completed 单。

    旧实现全量扫描后逐条比较也会跳过远期单; SQL 下推后行为等价, 不误伤。"""
    from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
    s = test_db["session"]
    st, dev = _seed_device(s, "CP-C669-API-001")
    now = datetime.now(timezone.utc)
    s.add(ChargingOrder(
        order_no="TL-C669-API-OLD",
        station_id=st.id, device_id=dev.id, connector_id=1,
        order_status=OrderStatus.CANCELLED,
        payment_status=OrderPaymentStatus.UNPAID,
        created_at=_naive_utc(now - timedelta(days=30)),
        end_time=_naive_utc(now - timedelta(days=29)),
    ))
    s.commit()

    resp = client.post("/api/v1/charging-sessions", json={
        "charge_point_id": "CP-C669-API-001",
        "transaction_id": "TX-C669-API-001",
        "connector_id": 1,
        "meter_start": 0,
        "meter_stop": 5000,
        "timestamp_start": (now - timedelta(minutes=30)).isoformat(),
        "timestamp_stop": now.isoformat(),
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["order_status"] == "completed"

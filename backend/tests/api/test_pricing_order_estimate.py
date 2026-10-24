"""订单费用估算 API 测试 (app/api/v1/pricing_management/order_estimate.py, 卡 96f676b3)

覆盖端点 (挂 /api/v1 前缀, 无额外 prefix):
- POST /pricing/mgmt/order-estimate  按当前生效定价估算订单费用

估算分项: 充电费(电价加权平均) + 服务费(按用户类型/fixed) + 停车费(含免费时长/日封顶)
        + 占桩费(含免罚/封顶) = 总费用

覆盖维度:
(a) 各分项计算正确: 电费/服务费/停车费/占桩费 + total 求和
(b) 服务费 fixed vs percent (按 kWh) 分支
(c) 停车费: free_minutes 扣除 + daily_cap 封顶
(d) 占桩费: grace_minutes 扣除 + max_fee 封顶
(e) 无定价配置 → 各分项为 0, total 为 0
(f) 生效期过滤: 过期/未生效定价不计入
(g) 参数校验: energy_kwh < 0 → 422
(h) 权限门: router-level require_role("admin") — 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models.pricing_v2 import (
    EnergyPrice, ServiceFeePrice, ParkingPrice, OccupancyFeePrice,
    TimeSlotDefinition, PeriodType, UserType, FeeType,
)
from app.models.station import Station

URL = "/api/v1/pricing/mgmt/order-estimate"


# ─── helpers ───

def _seed_station(session):
    sx = uuid.uuid4().hex[:6]
    st = Station(name=f"估站{sx}", code=f"EST{sx}")
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _slot(session, period=PeriodType.FLAT):
    """建一个 TimeSlotDefinition 行 (period_type unique, 但每 test 独立库无冲突)。"""
    tsd = TimeSlotDefinition(
        name=f"slot-{period.value}", period_type=period,
        start_time=time(0, 0), end_time=time(23, 59), is_active=True,
    )
    session.add(tsd)
    session.flush()
    return tsd


def _today():
    return date.today()


def _estimate(client, station_id, **over):
    body = {"station_id": station_id, "energy_kwh": 10.0}
    body.update(over)
    r = client.post(URL, json=body)
    assert r.status_code == 200, f"估算失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


# ═══════════════════════════════════════════════════════════════
# 1. 电费 + 服务费
# ═══════════════════════════════════════════════════════════════

class TestEnergyAndServiceFee:
    def test_energy_cost_weighted_average(self, client):
        """两条生效电价取平均 × kWh。"""
        s = client._sesh
        st = _seed_station(s)
        slot = _slot(s)
        today = _today()
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=Decimal("0.6"),
                          effective_date=today, is_active=True))
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=Decimal("0.8"),
                          effective_date=today, is_active=True))
        s.commit()
        # 平均 (0.6+0.8)/2 = 0.7 × 10 kWh = 7.0
        d = _estimate(client, st.id, energy_kwh=10.0)
        assert d["energy_cost"] == 7.0
        assert d["service_fee"] == 0.0

    def test_service_fee_percent_by_kwh(self, client):
        """服务费 fee_type=percent → fee_value × kWh。"""
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP,
                              fee_type=FeeType.PERCENT, fee_value=Decimal("0.5"),
                              effective_date=today, is_active=True))
        s.commit()
        # 0.5 × 10 = 5.0
        d = _estimate(client, st.id, energy_kwh=10.0, user_type="app")
        assert d["service_fee"] == 5.0

    def test_service_fee_fixed(self, client):
        """服务费 fee_type=fixed → 固定金额, 与 kWh 无关。"""
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP,
                              fee_type=FeeType.FIXED, fee_value=Decimal("3.0"),
                              effective_date=today, is_active=True))
        s.commit()
        d = _estimate(client, st.id, energy_kwh=100.0, user_type="app")
        assert d["service_fee"] == 3.0

    def test_service_fee_fallback_to_first(self, client):
        """无匹配用户类型 → 取第一条生效服务费。"""
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.CARD,
                              fee_type=FeeType.FIXED, fee_value=Decimal("7.0"),
                              effective_date=today, is_active=True))
        s.commit()
        # 请求 user_type=app 但只有 card → fallback 7.0
        d = _estimate(client, st.id, energy_kwh=10.0, user_type="app")
        assert d["service_fee"] == 7.0


# ═══════════════════════════════════════════════════════════════
# 2. 停车费 (free_minutes + daily_cap)
# ═══════════════════════════════════════════════════════════════

class TestParkingFee:
    def test_parking_free_minutes_deducted(self, client):
        """前 30 分钟免费, 之后按小时计。"""
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ParkingPrice(station_id=st.id, free_minutes=30, hourly_rate=Decimal("6.0"),
                           effective_date=today, is_active=True))
        s.commit()
        # 90 分钟 - 30 免费 = 60 分钟 = 1h × 6 = 6.0
        d = _estimate(client, st.id, parking_minutes=90)
        assert d["parking_fee"] == 6.0

    def test_parking_below_free_minutes_is_zero(self, client):
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ParkingPrice(station_id=st.id, free_minutes=60, hourly_rate=Decimal("6.0"),
                           effective_date=today, is_active=True))
        s.commit()
        d = _estimate(client, st.id, parking_minutes=30)
        assert d["parking_fee"] == 0.0

    def test_parking_daily_cap(self, client):
        """超出 daily_cap → 封顶。"""
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(ParkingPrice(station_id=st.id, free_minutes=0, hourly_rate=Decimal("10.0"),
                           daily_cap=Decimal("25.0"),
                           effective_date=today, is_active=True))
        s.commit()
        # 10h × 10 = 100 → 封顶 25
        d = _estimate(client, st.id, parking_minutes=600)
        assert d["parking_fee"] == 25.0


# ═══════════════════════════════════════════════════════════════
# 3. 占桩费 (grace_minutes + max_fee)
# ═══════════════════════════════════════════════════════════════

class TestOccupancyFee:
    def test_occupancy_grace_deducted(self, client):
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=15,
                                rate_per_minute=Decimal("0.5"),
                                effective_date=today, is_active=True))
        s.commit()
        # 65 - 15 = 50 × 0.5 = 25
        d = _estimate(client, st.id, occupancy_minutes=65)
        assert d["occupancy_fee"] == 25.0

    def test_occupancy_max_fee_cap(self, client):
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=0,
                                rate_per_minute=Decimal("2.0"), max_fee=Decimal("30.0"),
                                effective_date=today, is_active=True))
        s.commit()
        # 100 × 2 = 200 → 封顶 30
        d = _estimate(client, st.id, occupancy_minutes=100)
        assert d["occupancy_fee"] == 30.0

    def test_occupancy_zero_when_no_minutes(self, client):
        s = client._sesh
        st = _seed_station(s)
        today = _today()
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=0,
                                rate_per_minute=Decimal("2.0"),
                                effective_date=today, is_active=True))
        s.commit()
        d = _estimate(client, st.id, occupancy_minutes=0)
        assert d["occupancy_fee"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 4. total 求和 + 空配置 + 生效期
# ═══════════════════════════════════════════════════════════════

class TestTotalAndEffective:
    def test_total_sum_of_breakdown(self, client):
        s = client._sesh
        st = _seed_station(s)
        slot = _slot(s)
        today = _today()
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=Decimal("1.0"),
                          effective_date=today, is_active=True))            # 10
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP, fee_type=FeeType.FIXED,
                              fee_value=Decimal("2.0"), effective_date=today, is_active=True))  # 2
        s.add(ParkingPrice(station_id=st.id, free_minutes=0, hourly_rate=Decimal("6.0"),
                           effective_date=today, is_active=True))           # 60min=6
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=0, rate_per_minute=Decimal("0.5"),
                                effective_date=today, is_active=True))      # 30min=15
        s.commit()
        d = _estimate(client, st.id, energy_kwh=10.0, parking_minutes=60, occupancy_minutes=30)
        assert d["energy_cost"] == 10.0
        assert d["service_fee"] == 2.0
        assert d["parking_fee"] == 6.0
        assert d["occupancy_fee"] == 15.0
        assert d["total"] == 33.0

    def test_no_pricing_all_zero(self, client):
        """站点无任何定价 → 全 0。"""
        s = client._sesh
        st = _seed_station(s)
        d = _estimate(client, st.id, energy_kwh=50.0, parking_minutes=100, occupancy_minutes=100)
        assert d["total"] == 0.0
        assert d["energy_cost"] == 0.0

    def test_expired_pricing_excluded(self, client):
        """已过期定价不计入。"""
        s = client._sesh
        st = _seed_station(s)
        slot = _slot(s)
        today = _today()
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=Decimal("1.0"),
                          effective_date=today - timedelta(days=10),
                          expire_date=today - timedelta(days=1),  # 已过期
                          is_active=True))
        s.commit()
        d = _estimate(client, st.id, energy_kwh=10.0)
        assert d["energy_cost"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 5. 参数校验 + 权限门
# ═══════════════════════════════════════════════════════════════

class TestValidationAndPermission:
    def test_negative_energy_422(self, client):
        r = client.post(URL, json={"station_id": 1, "energy_kwh": -1.0})
        assert r.status_code == 422

    def test_missing_station_id_422(self, client):
        r = client.post(URL, json={"energy_kwh": 10.0})
        assert r.status_code == 422

    def test_anonymous_401(self, anon_client):
        r = anon_client.post(URL, json={"station_id": 1, "energy_kwh": 10.0})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════
# 6. 夜间费率 (卡 c13ac16b: 试算端点补 start_time)
# ═══════════════════════════════════════════════════════════════

class TestNightRate:
    def _seed_night_parking(self, session, station_id):
        """夜间价启用: 白天 10 元/h, 夜间 0.5 元/h, 22:00-06:00, 无免费/封顶。"""
        session.add(ParkingPrice(
            station_id=station_id,
            free_minutes=0,
            hourly_rate=Decimal("10.00"),
            daily_cap=None,
            enable_night_rate=True,
            night_rate=Decimal("0.50"),
            night_start=time(22, 0),
            night_end=time(6, 0),
            effective_date=_today(),
            is_active=True,
        ))
        session.commit()

    def test_night_start_lowers_fee(self, client):
        """RED-1: parking_start 落夜间窗 → 夜间价分摊生效, 低于全白天价。

        23:00 起停 120 分钟(全夜间) → 0.5×2=1.0; 若 start_time 缺失走白天价
        → 10×2=20。修复前恒返回 20 (start_time=None 短路)。
        """
        from zoneinfo import ZoneInfo
        s = client._sesh
        st = _seed_station(s)
        self._seed_night_parking(s, st.id)
        parking_start = datetime(
            _today().year, _today().month, _today().day, 23, 0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
        d = _estimate(client, st.id, parking_minutes=120, parking_start=parking_start.isoformat())
        assert d["parking_fee"] == 1.0

    def test_day_start_keeps_day_rate(self, client):
        """对照: parking_start 落白天(12:00) → 全白天价 20。"""
        from zoneinfo import ZoneInfo
        s = client._sesh
        st = _seed_station(s)
        self._seed_night_parking(s, st.id)
        parking_start = datetime(
            _today().year, _today().month, _today().day, 12, 0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
        d = _estimate(client, st.id, parking_minutes=120, parking_start=parking_start.isoformat())
        assert d["parking_fee"] == 20.0

    def test_parking_start_default_no_500(self, client):
        """RED-2: 不传 parking_start → 不 500, 走 now 路径。"""
        s = client._sesh
        st = _seed_station(s)
        self._seed_night_parking(s, st.id)
        d = _estimate(client, st.id, parking_minutes=60)
        assert 0.5 <= d["parking_fee"] <= 10.0

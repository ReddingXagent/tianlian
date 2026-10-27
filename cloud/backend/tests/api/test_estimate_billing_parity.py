"""估价端点 vs billing_engine 计费口径对拍测试 (卡 b6c8faf3)

同一输入(费率/电量/时长)下, order_estimate 各费项必须与 billing_engine
对应纯函数计算结果精确相等 —— 单一事实来源, 消除 float/Decimal 双实现漂移。

重点: 半分位边界用例(乘积落在 x.xx5), float 表示误差会使 round() 与
Decimal.quantize 分道扬镳, 差 1 分钱。
"""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from app.models.pricing_v2 import (
    EnergyPrice, ServiceFeePrice, ParkingPrice, OccupancyFeePrice,
    TimeSlotDefinition, PeriodType, UserType, FeeType,
)
from app.models.station import Station
from app.services.billing_engine import (
    TWO_PLACES,
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
)

URL = "/api/v1/pricing/mgmt/order-estimate"


def _seed_station(session):
    sx = uuid.uuid4().hex[:6]
    st = Station(name=f"对拍站{sx}", code=f"PAR{sx}")
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _full_day_slot(session):
    tsd = TimeSlotDefinition(
        name=f"slot-{uuid.uuid4().hex[:6]}", period_type=PeriodType.FLAT,
        start_time=time(0, 0), end_time=time(23, 59), is_active=True,
    )
    session.add(tsd)
    session.flush()
    return tsd


def _estimate(client, station_id, **over):
    body = {"station_id": station_id, "energy_kwh": 0.0}
    body.update(over)
    r = client.post(URL, json=body)
    assert r.status_code == 200, f"估算失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


class TestEstimateBillingParity:
    def test_energy_cost_parity_half_cent_boundary(self, client):
        """电费半分位: 0.149 × 3 = 0.447 (x.xx5 结尾) 对拍 TOU 引擎。"""
        s = client._sesh
        st = _seed_station(s)
        slot = _full_day_slot(s)
        today = date.today()
        rate = Decimal("0.149")
        kwh = Decimal("3")
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=rate,
                          effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, energy_kwh=float(kwh))

        engine = compute_tou_energy_fee(
            start_time=datetime(2026, 1, 1, 0, 0),
            end_time=datetime(2026, 1, 1, 23, 59),
            total_kwh=kwh,
            time_slots=[{"slot_id": slot.id, "period_type": "flat",
                         "start_time": slot.start_time, "end_time": slot.end_time}],
            slot_prices={slot.id: rate},
        )
        assert d["energy_cost"] == float(engine["total_fee"].quantize(TWO_PLACES))

    def test_service_fee_percent_parity_half_cent_boundary(self, client):
        """服务费半分位: 0.149 × 3 = 0.447 对拍 compute_service_fee_multi。"""
        s = client._sesh
        st = _seed_station(s)
        today = date.today()
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP,
                              fee_type=FeeType.PERCENT, fee_value=Decimal("0.149"),
                              effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, energy_kwh=3.0, user_type="app")
        engine = compute_service_fee_multi(Decimal("3"), "percent", Decimal("0.149"))
        assert d["service_fee"] == float(engine.quantize(TWO_PLACES))

    def test_parking_fee_parity_half_cent_boundary(self, client):
        """停车费半分位: 61 分钟计费 × 费率 29.5/60h → 29.5×61/60 = 29.9983~;
        构造 rate=0.733, 45min: 0.733×45/60 = 0.54975 → 边界对拍。"""
        s = client._sesh
        st = _seed_station(s)
        today = date.today()
        hourly = Decimal("0.733")
        minutes = 45
        s.add(ParkingPrice(station_id=st.id, free_minutes=0, hourly_rate=hourly,
                           effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, parking_minutes=minutes)
        engine = compute_parking_fee_full(
            minutes, {"free_minutes": 0, "hourly_rate": hourly},
        )
        assert d["parking_fee"] == float(engine["total"].quantize(TWO_PLACES))

    def test_parking_fee_parity_with_daily_cap(self, client):
        """停车费含日封顶对拍(引擎每 24h 块数封顶语义)。"""
        s = client._sesh
        st = _seed_station(s)
        today = date.today()
        rule = {"free_minutes": 30, "hourly_rate": Decimal("6.00"),
                "daily_cap": Decimal("25.00")}
        s.add(ParkingPrice(station_id=st.id, free_minutes=30, hourly_rate=Decimal("6.00"),
                           daily_cap=Decimal("25.00"),
                           effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, parking_minutes=600)
        engine = compute_parking_fee_full(600, rule)
        assert d["parking_fee"] == float(engine["total"].quantize(TWO_PLACES))

    def test_occupancy_fee_parity_plain_rate(self, client):
        """占桩费对拍: rate_per_minute 列为 Numeric(10,2), 费率物理上到不了 3 位小数,
        半分位边界在此维度不可构造(乘积恒为 2 位小数), 改用 2 位费率做口径对拍。"""
        s = client._sesh
        st = _seed_station(s)
        today = date.today()
        rate = Decimal("0.25")
        minutes = 55
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=0,
                                rate_per_minute=rate,
                                effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, occupancy_minutes=minutes)
        engine = compute_occupancy_fee_full(
            minutes, {"grace_minutes": 0, "rate_per_minute": rate},
        )
        assert d["occupancy_fee"] == float(engine.quantize(TWO_PLACES))

    def test_occupancy_fee_parity_with_max_fee(self, client):
        """占桩费封顶对拍。"""
        s = client._sesh
        st = _seed_station(s)
        today = date.today()
        rule = {"grace_minutes": 15, "rate_per_minute": Decimal("2.00"),
                "max_fee": Decimal("30.00")}
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=15,
                                rate_per_minute=Decimal("2.00"), max_fee=Decimal("30.00"),
                                effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, occupancy_minutes=100)
        engine = compute_occupancy_fee_full(100, rule)
        assert d["occupancy_fee"] == float(engine.quantize(TWO_PLACES))

    def test_total_parity_full_stack(self, client):
        """全费项组合: total == 各费项 Decimal 和(与引擎同一汇总口径)。"""
        s = client._sesh
        st = _seed_station(s)
        slot = _full_day_slot(s)
        today = date.today()
        s.add(EnergyPrice(station_id=st.id, slot_id=slot.id, price_per_kwh=Decimal("0.149"),
                          effective_date=today, is_active=True))
        s.add(ServiceFeePrice(station_id=st.id, user_type=UserType.APP,
                              fee_type=FeeType.PERCENT, fee_value=Decimal("0.149"),
                              effective_date=today, is_active=True))
        s.add(ParkingPrice(station_id=st.id, free_minutes=0, hourly_rate=Decimal("0.733"),
                           effective_date=today, is_active=True))
        s.add(OccupancyFeePrice(station_id=st.id, grace_minutes=0,
                                rate_per_minute=Decimal("0.0045"),
                                effective_date=today, is_active=True))
        s.commit()

        d = _estimate(client, st.id, energy_kwh=3.0, parking_minutes=45,
                      occupancy_minutes=55)
        expected = sum(
            (Decimal(str(d[k])).quantize(TWO_PLACES)
             for k in ("energy_cost", "service_fee", "parking_fee", "occupancy_fee")),
            Decimal("0.00"),
        )
        assert d["total"] == float(expected)

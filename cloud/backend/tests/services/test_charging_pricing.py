"""
充电计费接线服务(charging_pricing)测试 - 覆盖率补强 ≥70%

被测: app/services/charging_pricing.py (310 行)
设计: 用 test_db 真 SQLite 走 pricing_v2 → billing_engine 全链路。
覆盖:
- _today / _effective_filter       日期助手 / 生效期过滤(生效/未来/过期)
- _load_tou_energy                 时段定义+电价加载 → TOU 拆分; 缺 slot/电价 → None
- _load_service_fee                fixed/percent; 无效 user_type→APP; 缺定价→None
- _load_parking_fee                minutes≤0→0; 免费时长/小时费率/封顶/夜间
- _load_occupancy_fee              minutes≤0→0; 宽限/费率/单次封顶
- settle_charging_session          全定价写 5 项 + order_fee_items;
                                   兜底 DEFAULT_ENERGY_PRICE/SERVICE_FEE(used_default);
                                   Decimal 全程禁 float
"""
from datetime import datetime, date, time, timedelta
from decimal import Decimal

import pytest

from app.services.charging_pricing import (
    DEFAULT_ENERGY_PRICE,
    DEFAULT_SERVICE_FEE,
    TWO_PLACES,
    _today,
    _effective_filter,
    _load_tou_energy,
    _load_service_fee,
    _load_parking_fee,
    _load_occupancy_fee,
    settle_charging_session,
)
from app.models.pricing_v2 import (
    TimeSlotDefinition,
    PeriodType,
    EnergyPrice,
    ServiceFeePrice,
    ParkingPrice,
    OccupancyFeePrice,
    UserType as PricingUserType,
    FeeType as PricingFeeType,
)
from app.models.charging_order import ChargingOrder
from app.models.order_fee_item import OrderFeeItem
from app.models.pricing_v2 import ServiceFeePrice as _SFP  # noqa: F401 (覆盖性引用)


STATION = 9001


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

def _slot(db, name, period_type, start, end, is_active=True):
    s = TimeSlotDefinition(
        name=name, period_type=period_type,
        start_time=start, end_time=end, is_active=is_active,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _energy(db, station_id, slot_id, price, *, is_active=True,
            effective=None, expire=None):
    ep = EnergyPrice(
        station_id=station_id, slot_id=slot_id, price_per_kwh=price,
        is_active=is_active,
        effective_date=effective or (date.today() - timedelta(days=1)),
        expire_date=expire,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return ep


def _order(db, *, station_id=STATION, device_id=1, order_no="CP-TEST-1"):
    o = ChargingOrder(
        order_no=order_no, station_id=station_id, device_id=device_id,
        charged_kwh=Decimal("10.00"),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


# ═══════════════════════════════════════════════════════════════
# 1. 日期助手 / 生效期过滤
# ═══════════════════════════════════════════════════════════════

class TestDateHelpers:

    def test_today_returns_biz_tz_date(self):
        # _today() 走业务时区 today_in_biz_tz(), 非容器本地 date.today() (缺陷2)
        from app.tasks.tz_utils import today_in_biz_tz
        assert isinstance(_today(), date)
        assert _today() == today_in_biz_tz()

    def test_effective_filter_returns_expression(self):
        # 返回的是 SQLAlchemy 布尔表达式(非 None), 真正的过滤语义由下方 DB 测试覆盖
        expr = _effective_filter(ServiceFeePrice, date.today())
        assert expr is not None


# ═══════════════════════════════════════════════════════════════
# 2. _load_tou_energy
# ═══════════════════════════════════════════════════════════════

class TestLoadTouEnergy:

    def test_no_slots_returns_none(self, test_db):
        db = test_db["session"]
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_slots_but_no_energy_price_returns_none(self, test_db):
        db = test_db["session"]
        _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0))
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_slot_without_matching_price_filtered(self, test_db):
        # slot A 有电价, slot B 无电价 → time_slots 仅含 A
        db = test_db["session"]
        sa = _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0))
        _slot(db, "平", PeriodType.FLAT, time(6, 0), time(10, 0))  # 无电价
        _energy(db, STATION, sa.id, Decimal("1.0"))
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 12, 0)
        fee, breakdown = _load_tou_energy(db, STATION, Decimal("12"), start, end)
        assert fee > Decimal("0")
        # 仅峰段命中
        assert len(breakdown) == 1
        assert breakdown[0]["period_name"] == "peak段电费"
        # breakdown 字段完整
        assert set(breakdown[0].keys()) == {"period_name", "kwh", "price", "fee", "unit"}
        assert breakdown[0]["unit"] == "kWh"

    def test_multi_period_split(self, test_db):
        db = test_db["session"]
        sp = _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(14, 0))
        sf = _slot(db, "平", PeriodType.FLAT, time(6, 0), time(10, 0))
        _energy(db, STATION, sp.id, Decimal("1.0"))
        _energy(db, STATION, sf.id, Decimal("0.5"))
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 14, 0)  # 8 小时, 峰平各 4 小时
        fee, breakdown = _load_tou_energy(db, STATION, Decimal("16"), start, end)
        # 两段
        assert len(breakdown) == 2
        # total_fee == 各段 fee 之和(Decimal 精度一致)
        assert fee == sum((seg["fee"] for seg in breakdown), Decimal("0"))
        # 全程 Decimal
        assert isinstance(fee, Decimal)

    def test_breakdown_sum_equals_fee_invariant(self, test_db, monkeypatch):
        """_load_tou_energy 生成明细后核对: 明细金额之和 == 总电费(electricity_fee)。

        回归 4671e993 配套核对: time_slot_definitions.period_type 有 UNIQUE 约束,
        真实链路无法入库双 PEAK, 故 monkeypatch compute_tou_energy_fee 注入"双峰已合并"
        result, 验证 _load_tou_energy 明细和==total_fee 核对通过(修复后恒成立)。
        """
        from app.services import charging_pricing as cp
        monkeypatch.setattr(cp, "compute_tou_energy_fee", lambda *a, **kw: {
            "period_breakdown": {
                "peak": {"energy": Decimal("70.00"), "price": Decimal("1.000000"),
                         "fee": Decimal("70.00"), "minutes": 420.0},
            },
            "total_fee": Decimal("70.00"),
        })
        db = test_db["session"]
        sp = _slot(db, "峰", PeriodType.PEAK, time(8, 0), time(12, 0))
        _energy(db, STATION, sp.id, Decimal("1.0"))
        start = datetime(2026, 8, 2, 8, 0)
        end = datetime(2026, 8, 2, 21, 0)
        fee, breakdown = _load_tou_energy(db, STATION, Decimal("130"), start, end)
        assert fee == Decimal("70.00")
        assert len(breakdown) == 1
        # 明细行金额之和 == 总电费(electricity_fee)
        assert sum((seg["fee"] for seg in breakdown), Decimal("0")) == fee

    def test_breakdown_sum_mismatch_falls_back_to_none(self, test_db, monkeypatch):
        """billing_engine 返回明细和 != total_fee(不变式被破坏, 如旧覆盖 bug) →
        _load_tou_energy 核对抛错, 外层 except 兜底返回 None, 调用方走默认电价, 不出错误明细。"""
        from app.services import charging_pricing as cp
        monkeypatch.setattr(cp, "compute_tou_energy_fee", lambda *a, **kw: {
            "period_breakdown": {  # 旧覆盖 bug 形态: peak 只剩第二窗 30
                "peak": {"energy": Decimal("30.00"), "price": Decimal("1.000000"),
                         "fee": Decimal("30.00"), "minutes": 180.0},
            },
            "total_fee": Decimal("70.00"),  # 但 total_fee 累加了 70 → 明细和 30 != 70
        })
        db = test_db["session"]
        sp = _slot(db, "峰", PeriodType.PEAK, time(8, 0), time(12, 0))
        _energy(db, STATION, sp.id, Decimal("1.0"))
        start = datetime(2026, 8, 2, 8, 0)
        end = datetime(2026, 8, 2, 21, 0)
        assert _load_tou_energy(db, STATION, Decimal("130"), start, end) is None

    def test_inactive_slot_excluded(self, test_db):
        db = test_db["session"]
        _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0), is_active=False)
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_all_slots_filtered_returns_none(self, test_db):
        # slot 存在但都不在 slot_prices 中(无电价) → time_slots 空 → None
        db = test_db["session"]
        _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0))
        _slot(db, "平", PeriodType.FLAT, time(6, 0), time(10, 0))
        start = datetime(2026, 8, 2, 6, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_energy_price_for_unknown_slot_returns_none(self, test_db):
        # slot 定义存在, 电价也存在, 但电价绑定的 slot_id 不在任何 slot 定义中
        # → slot_prices 有值但 time_slots 仍空 → None
        db = test_db["session"]
        _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0))  # id=1
        _energy(db, STATION, slot_id=99999, price=Decimal("1.0"))   # 不匹配任何 slot
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_expired_energy_price_excluded(self, test_db):
        db = test_db["session"]
        sp = _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(12, 0))
        # 已过期电价 → 不命中 → 该 slot 无电价 → None
        _energy(db, STATION, sp.id, Decimal("1.0"),
                expire=date.today() - timedelta(days=1))
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 12, 0)
        assert _load_tou_energy(db, STATION, Decimal("10"), start, end) is None

    def test_overlap_picks_latest_effective_energy(self, test_db):
        """同 slot 两条重叠生效期电价 → 须确定性取最新生效(缺陷1)。

        构造: 新价 1.0(eff 2026-02-01) 先插, 旧价 0.6(eff 2026-01-01) 后插, 均 open-ended。
        旧实现 slot_prices dict 推导 last-wins 按"行序"而非生效日 → 取到旧价 0.6。
        修复: 查询 order_by(effective_date.desc(), id.desc()) + first-wins dict → 取新价 1.0。
        """
        db = test_db["session"]
        sp = _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(14, 0))
        _energy(db, STATION, sp.id, Decimal("1.0"), effective=date(2026, 2, 1))  # 新
        _energy(db, STATION, sp.id, Decimal("0.6"), effective=date(2026, 1, 1))  # 旧
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)
        fee, _bd = _load_tou_energy(db, STATION, Decimal("10"), start, end,
                                    charging_date=date(2026, 8, 2))
        # 10 kWh × 1.0(最新生效) = 10.00, 非 0.6 的 6.00
        assert fee == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 3. _load_service_fee
# ═══════════════════════════════════════════════════════════════

class TestLoadServiceFee:

    def _row(self, db, user_type, fee_type, fee_value, **kw):
        r = ServiceFeePrice(
            station_id=STATION, user_type=user_type,
            fee_type=fee_type, fee_value=fee_value,
            effective_date=kw.get("effective", date.today() - timedelta(days=1)),
            expire_date=kw.get("expire"),
            is_active=kw.get("is_active", True),
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def test_percent_fee(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.3"))
        fee = _load_service_fee(db, STATION, "app", Decimal("10"))
        assert fee == Decimal("3.00")

    def test_fixed_fee(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.FIXED, Decimal("2.0"))
        fee = _load_service_fee(db, STATION, "app", Decimal("10"))
        # fixed 与电量无关
        assert fee == Decimal("2.00")

    def test_invalid_user_type_falls_back_to_app(self, test_db):
        db = test_db["session"]
        # 仅 APP 行, 传非法 user_type → 命中 APP
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.5"))
        fee = _load_service_fee(db, STATION, "bogus_type", Decimal("10"))
        assert fee == Decimal("5.00")

    def test_enterprise_user_type(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.ENTERPRISE, PricingFeeType.PERCENT, Decimal("0.4"))
        fee = _load_service_fee(db, STATION, "enterprise", Decimal("10"))
        assert fee == Decimal("4.00")

    def test_no_pricing_returns_none(self, test_db):
        db = test_db["session"]
        assert _load_service_fee(db, STATION, "app", Decimal("10")) is None

    def test_expired_row_excluded(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.3"),
                  expire=date.today() - timedelta(days=1))
        assert _load_service_fee(db, STATION, "app", Decimal("10")) is None

    def test_future_row_excluded(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.3"),
                  effective=date.today() + timedelta(days=1))
        assert _load_service_fee(db, STATION, "app", Decimal("10")) is None

    def test_returns_decimal(self, test_db):
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.3"))
        fee = _load_service_fee(db, STATION, "app", Decimal("10"))
        assert isinstance(fee, Decimal)

    def test_charging_date_controls_effective_filter(self, test_db):
        """定价基准日 = 充电日(非结算日 today): charging_date 早于生效日 → 未生效 None;
        晚于/等于生效日 → 生效。跨午夜/延迟结算按充电日价格计费。"""
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.4"),
                  effective=date(2026, 8, 5))
        # 充电日 2026-08-02 早于生效日 2026-08-05 → 未生效 → None
        assert _load_service_fee(db, STATION, "app", Decimal("10"),
                                 charging_date=date(2026, 8, 2)) is None
        # 充电日 2026-08-06 晚于生效日 → 生效 → 10 × 0.4 = 4.00
        assert _load_service_fee(db, STATION, "app", Decimal("10"),
                                 charging_date=date(2026, 8, 6)) == Decimal("4.00")

    def test_overlap_picks_latest_effective_service_fee(self, test_db):
        """同维度(app)两条重叠生效期 → .first() 须确定性取最新生效(缺陷1)。

        旧价 0.3(eff 2026-01-01) 先插, 新价 0.5(eff 2026-02-01) 后插, 均 open-ended。
        旧实现无 order_by 的 .first() 取插入序首条(旧价 0.3)。
        修复: order_by(effective_date.desc(), id.desc()) → first 取新价 0.5。
        """
        db = test_db["session"]
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.3"),
                  effective=date(2026, 1, 1))
        self._row(db, PricingUserType.APP, PricingFeeType.PERCENT, Decimal("0.5"),
                  effective=date(2026, 2, 1))
        fee = _load_service_fee(db, STATION, "app", Decimal("10"),
                                charging_date=date(2026, 8, 2))
        # 10 kWh × 0.5(最新生效) = 5.00, 非 0.3 的 3.00
        assert fee == Decimal("5.00")


# ═══════════════════════════════════════════════════════════════
# 4. _load_parking_fee
# ═══════════════════════════════════════════════════════════════

class TestLoadParkingFee:

    def _row(self, db, **kw):
        r = ParkingPrice(
            station_id=STATION,
            free_minutes=kw.get("free_minutes", 0),
            hourly_rate=kw.get("hourly_rate", Decimal("2.0")),
            daily_cap=kw.get("daily_cap"),
            enable_night_rate=kw.get("enable_night_rate", False),
            night_rate=kw.get("night_rate"),
            night_start=kw.get("night_start"),
            night_end=kw.get("night_end"),
            effective_date=kw.get("effective", date.today() - timedelta(days=1)),
            expire_date=kw.get("expire"),
            is_active=True,
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def test_zero_minutes_returns_zero(self, test_db):
        db = test_db["session"]
        self._row(db, free_minutes=30, hourly_rate=Decimal("2.0"))
        assert _load_parking_fee(db, STATION, 0, None) == Decimal("0.00")

    def test_negative_minutes_returns_zero(self, test_db):
        db = test_db["session"]
        self._row(db)
        assert _load_parking_fee(db, STATION, -5, None) == Decimal("0.00")

    def test_no_pricing_returns_zero(self, test_db):
        db = test_db["session"]
        assert _load_parking_fee(db, STATION, 90, None) == Decimal("0.00")

    def test_free_minutes_absorbed(self, test_db):
        db = test_db["session"]
        # 免费 60 分钟, 停 30 分钟 → billable=0 → 0
        self._row(db, free_minutes=60, hourly_rate=Decimal("2.0"))
        start = datetime(2026, 8, 2, 10, 0)
        assert _load_parking_fee(db, STATION, 30, start) == Decimal("0.00")

    def test_hourly_rate(self, test_db):
        db = test_db["session"]
        # 免费 30, 停 90 → billable 60min = 1h × 2.0 = 2.00
        self._row(db, free_minutes=30, hourly_rate=Decimal("2.0"))
        start = datetime(2026, 8, 2, 10, 0)
        assert _load_parking_fee(db, STATION, 90, start) == Decimal("2.00")

    def test_daily_cap(self, test_db):
        db = test_db["session"]
        # 停 600min=10h × 2.0 = 20, 封顶 15 → 15.00
        self._row(db, free_minutes=0, hourly_rate=Decimal("2.0"), daily_cap=Decimal("15"))
        start = datetime(2026, 8, 2, 10, 0)
        assert _load_parking_fee(db, STATION, 600, start) == Decimal("15.00")

    def test_night_rate(self, test_db):
        db = test_db["session"]
        # 夜间费率: 60min 全在夜间窗口 22:00-06:00, night_rate 1.0 → 1.00
        self._row(db, free_minutes=0, hourly_rate=Decimal("5.0"),
                  enable_night_rate=True, night_rate=Decimal("1.0"),
                  night_start=time(22, 0), night_end=time(6, 0))
        start = datetime(2026, 8, 2, 23, 0)
        assert _load_parking_fee(db, STATION, 60, start) == Decimal("1.00")

    def test_overlap_picks_latest_effective_parking(self, test_db):
        """同站点两条重叠生效期 → .first() 须确定性取最新生效(缺陷1)。

        旧 hourly 2.0(eff 2026-01-01) 先插, 新 hourly 5.0(eff 2026-02-01) 后插, 均 open-ended。
        修复: order_by(effective_date.desc(), id.desc()) → first 取新价 5.0。
        """
        db = test_db["session"]
        self._row(db, free_minutes=0, hourly_rate=Decimal("2.0"),
                  effective=date(2026, 1, 1))
        self._row(db, free_minutes=0, hourly_rate=Decimal("5.0"),
                  effective=date(2026, 2, 1))
        start = datetime(2026, 8, 2, 10, 0)
        # 60min × 5.0(最新生效) = 5.00, 非 2.0 的 2.00
        assert _load_parking_fee(db, STATION, 60, start,
                                 charging_date=date(2026, 8, 2)) == Decimal("5.00")

    def test_returns_decimal(self, test_db):
        db = test_db["session"]
        self._row(db, free_minutes=0, hourly_rate=Decimal("2.0"))
        fee = _load_parking_fee(db, STATION, 60, datetime(2026, 8, 2, 10, 0))
        assert isinstance(fee, Decimal)


# ═══════════════════════════════════════════════════════════════
# 5. _load_occupancy_fee
# ═══════════════════════════════════════════════════════════════

class TestLoadOccupancyFee:

    def _row(self, db, **kw):
        r = OccupancyFeePrice(
            station_id=STATION,
            grace_minutes=kw.get("grace_minutes", 15),
            rate_per_minute=kw.get("rate_per_minute", Decimal("0.5")),
            max_fee=kw.get("max_fee"),
            effective_date=kw.get("effective", date.today() - timedelta(days=1)),
            expire_date=kw.get("expire"),
            is_active=True,
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def test_zero_minutes_returns_zero(self, test_db):
        db = test_db["session"]
        self._row(db)
        assert _load_occupancy_fee(db, STATION, 0) == Decimal("0.00")

    def test_negative_returns_zero(self, test_db):
        db = test_db["session"]
        self._row(db)
        assert _load_occupancy_fee(db, STATION, -1) == Decimal("0.00")

    def test_no_pricing_returns_zero(self, test_db):
        db = test_db["session"]
        assert _load_occupancy_fee(db, STATION, 60) == Decimal("0.00")

    def test_grace_minutes_absorbed(self, test_db):
        db = test_db["session"]
        # 宽限 30, 占 20 → billable 0 → 0
        self._row(db, grace_minutes=30, rate_per_minute=Decimal("0.5"))
        assert _load_occupancy_fee(db, STATION, 20) == Decimal("0.00")

    def test_rate_per_minute(self, test_db):
        db = test_db["session"]
        # 宽限 15, 占 45 → billable 30 × 0.5 = 15.00
        self._row(db, grace_minutes=15, rate_per_minute=Decimal("0.5"))
        assert _load_occupancy_fee(db, STATION, 45) == Decimal("15.00")

    def test_max_fee_cap(self, test_db):
        db = test_db["session"]
        # 占 300 → billable 285 × 0.5 = 142.5, 封顶 20 → 20.00
        self._row(db, grace_minutes=15, rate_per_minute=Decimal("0.5"), max_fee=Decimal("20"))
        assert _load_occupancy_fee(db, STATION, 300) == Decimal("20.00")

    def test_overlap_picks_latest_effective_occupancy(self, test_db):
        """同站点两条重叠生效期 → .first() 须确定性取最新生效(缺陷1)。

        旧 rate 0.5(eff 2026-01-01) 先插, 新 rate 1.0(eff 2026-02-01) 后插, 均 open-ended。
        修复: order_by(effective_date.desc(), id.desc()) → first 取新价 1.0。
        """
        db = test_db["session"]
        self._row(db, grace_minutes=0, rate_per_minute=Decimal("0.5"),
                  effective=date(2026, 1, 1))
        self._row(db, grace_minutes=0, rate_per_minute=Decimal("1.0"),
                  effective=date(2026, 2, 1))
        # 60min × 1.0(最新生效) = 60.00, 非 0.5 的 30.00
        assert _load_occupancy_fee(db, STATION, 60,
                                   charging_date=date(2026, 8, 2)) == Decimal("60.00")

    def test_returns_decimal(self, test_db):
        db = test_db["session"]
        self._row(db, grace_minutes=0, rate_per_minute=Decimal("0.5"))
        fee = _load_occupancy_fee(db, STATION, 10)
        assert isinstance(fee, Decimal)


# ═══════════════════════════════════════════════════════════════
# 6. settle_charging_session
# ═══════════════════════════════════════════════════════════════

class TestSettleChargingSession:

    def test_full_pricing_writes_five_fees_and_items(self, test_db):
        db = test_db["session"]
        # 电费(TOU) — 定价生效日早于充电日 2026-08-02(定价基准日=充电日语义)
        sp = _slot(db, "峰", PeriodType.PEAK, time(10, 0), time(14, 0))
        _energy(db, STATION, sp.id, Decimal("1.0"), effective=date(2026, 8, 1))
        # 服务费
        db.add(ServiceFeePrice(
            station_id=STATION, user_type=PricingUserType.APP,
            fee_type=PricingFeeType.PERCENT, fee_value=Decimal("0.3"),
            effective_date=date(2026, 8, 1), is_active=True,
        ))
        # 停车费
        db.add(ParkingPrice(
            station_id=STATION, free_minutes=0, hourly_rate=Decimal("2.0"),
            effective_date=date(2026, 8, 1), is_active=True,
        ))
        # 占桩费
        db.add(OccupancyFeePrice(
            station_id=STATION, grace_minutes=0, rate_per_minute=Decimal("0.5"),
            effective_date=date(2026, 8, 1), is_active=True,
        ))
        db.commit()

        order = _order(db)
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)

        fees = settle_charging_session(
            db, order, start, end, Decimal("10"),
            user_type_str="app", parking_minutes=60, occupancy_minutes=30,
        )

        # 全定价 → 不兜底
        assert fees["used_default"] is False
        # 5 项费用齐全且为 Decimal
        for k in ("energy_fee", "service_fee", "parking_fee", "occupancy_fee", "reservation_fee"):
            assert isinstance(fees[k], Decimal), f"{k} 应为 Decimal"
        # 预约费恒 0(ingestion 无预约语义)
        assert fees["reservation_fee"] == Decimal("0.00")
        # 服务费 10 × 0.3 = 3.00
        assert fees["service_fee"] == Decimal("3.00")
        # 占桩费 30 × 0.5 = 15.00
        assert fees["occupancy_fee"] == Decimal("15.00")
        # 停车费 60min = 1h × 2.0 = 2.00
        assert fees["parking_fee"] == Decimal("2.00")
        # 电费 breakdown 非空(TOU 拆分写入多条明细)
        assert fees["energy_fee"] > Decimal("0")

        # 验证 ChargingOrder 5 项字段被写入
        db.refresh(order)
        assert order.electricity_fee == fees["energy_fee"]
        assert order.service_fee == Decimal("3.00")
        assert order.parking_fee == Decimal("2.00")
        assert order.occupancy_fee == Decimal("15.00")
        assert order.reservation_fee == Decimal("0.00")
        assert order.total_amount == (
            fees["energy_fee"] + Decimal("3.00") + Decimal("2.00")
            + Decimal("15.00") + Decimal("0.00")
        )

        # 验证 order_fee_items 明细行(电费分时多行 + 服务费 + 停车 + 占桩)
        items = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        assert len(items) >= 4
        item_types = {i.fee_type for i in items}
        # 至少含 电费/服务费/停车费/占桩费 四类(枚举值来自 order_fee_item.FeeType)
        assert len(item_types) >= 4

    def test_default_fallback_when_no_pricing(self, test_db):
        db = test_db["session"]
        # 完全无 pricing_v2 数据
        order = _order(db, order_no="CP-DEFAULT-1")
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)

        # 无定价 → 兜底(记 warning, 不抛)
        fees = settle_charging_session(db, order, start, end, Decimal("10"))

        assert fees["used_default"] is True
        # 电费 = 10 × 0.8 = 8.00
        assert fees["energy_fee"] == (Decimal("10") * DEFAULT_ENERGY_PRICE).quantize(TWO_PLACES)
        assert fees["energy_fee"] == Decimal("8.00")
        # 服务费 = 10 × 0.5 = 5.00
        assert fees["service_fee"] == (Decimal("10") * DEFAULT_SERVICE_FEE).quantize(TWO_PLACES)
        assert fees["service_fee"] == Decimal("5.00")
        # 停车/占桩无定价 → 0(不兜底)
        assert fees["parking_fee"] == Decimal("0.00")
        assert fees["occupancy_fee"] == Decimal("0.00")
        # 预约费恒 0
        assert fees["reservation_fee"] == Decimal("0.00")
        # 优惠三项为 0
        assert fees["discount_amount"] == Decimal("0")
        assert fees["coupon_amount"] == Decimal("0")
        assert fees["points_amount"] == Decimal("0")

        # order 写入兜底值
        db.refresh(order)
        assert order.electricity_fee == Decimal("8.00")
        assert order.service_fee == Decimal("5.00")

        # 兜底时 energy_breakdown=None → 电费汇总单行明细
        items = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        assert len(items) >= 1

    def test_partial_pricing_mixed_fallback(self, test_db):
        db = test_db["session"]
        # 仅服务费有定价, 电费/停车/占桩无 — 生效日早于充电日 2026-08-02(充电日语义)
        db.add(ServiceFeePrice(
            station_id=STATION, user_type=PricingUserType.APP,
            fee_type=PricingFeeType.PERCENT, fee_value=Decimal("0.4"),
            effective_date=date(2026, 8, 1), is_active=True,
        ))
        db.commit()
        order = _order(db, order_no="CP-MIX-1")
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)

        fees = settle_charging_session(db, order, start, end, Decimal("10"))

        # 电费兜底(无 TOU), 服务费走定价 → used_default=True(电费触发)
        assert fees["used_default"] is True
        assert fees["energy_fee"] == Decimal("8.00")  # 兜底
        assert fees["service_fee"] == Decimal("4.00")  # 10 × 0.4 定价
        assert fees["parking_fee"] == Decimal("0.00")
        assert fees["occupancy_fee"] == Decimal("0.00")

    def test_idempotent_resettle_overwrites(self, test_db):
        db = test_db["session"]
        order = _order(db, order_no="CP-IDEM-1")
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)

        settle_charging_session(db, order, start, end, Decimal("10"))
        items_after_first = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).count()

        # 再次结算: 旧明细应被清除后重写, 不累积
        settle_charging_session(db, order, start, end, Decimal("10"))
        items_after_second = db.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).count()

        assert items_after_first == items_after_second
        assert items_after_first >= 1


# ═══════════════════════════════════════════════════════════════
# 7. 定价基准日业务时区 (缺陷2): aware UTC 跨午夜 → 定价基准日按上海业务日
# ═══════════════════════════════════════════════════════════════

class TestSettleBizDate:

    def test_charging_date_is_shanghai_biz_date_for_aware_utc(self, test_db):
        """跨午夜: start_time 为 aware UTC 16:00(= 上海次日 00:00) → 定价基准日取上海业务日。

        服务费仅在 2026-08-03(上海业务日) 生效。旧实现 charging_date=start_time.date()
        对 aware UTC 取 .date() = 2026-08-02(UTC 当日) → 命中不到定价走兜底 5.00。
        修复: aware 转 biz tz 取 date → 2026-08-03 → 命中定价 0.4 → 4.00。容器 UTC 回归。
        """
        from datetime import timezone
        db = test_db["session"]
        db.add(ServiceFeePrice(
            station_id=STATION, user_type=PricingUserType.APP,
            fee_type=PricingFeeType.PERCENT, fee_value=Decimal("0.4"),
            effective_date=date(2026, 8, 3), is_active=True,
        ))
        db.commit()
        order = _order(db, order_no="CP-TZ-BIZ-1")
        # UTC 2026-08-02 16:00 = 上海 2026-08-03 00:00
        start = datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, 17, 0, tzinfo=timezone.utc)
        fees = settle_charging_session(db, order, start, end, Decimal("10"))
        # 基准日=上海 08-03 → 命中服务费 0.4 → 4.00(旧实现会取兜底 5.00)
        assert fees["service_fee"] == Decimal("4.00")

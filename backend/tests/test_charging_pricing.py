#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
充电计费接线服务 - 隔离单元测试 (MagicMock 隔离 DB)

被测: app/services/charging_pricing.py
设计: pricing_v2 定价加载逻辑用 MagicMock 模拟 Session 查询链;
       billing_engine 纯计算函数保持真实运行 (无 DB 耦合, 更有价值);
       settle_order_fees 在 settle_charging_session 测试中 patch 掉避免写库。
覆盖:
- _today                          返回 date
- _load_tou_energy                无 slot / 无电价 / slot 不匹配 / 全数据
- _load_service_fee               无行 / fixed / percent / 非法 user_type 回落 APP
- _load_parking_fee               minutes<=0 / 无行 / 全规则
- _load_occupancy_fee             minutes<=0 / 无行 / 全规则
- settle_charging_session         无定价兜底 used_default / 全定价 / 调用 settle_order_fees
"""
from datetime import datetime, date, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import charging_pricing as cp
from app.services.charging_pricing import (
    DEFAULT_ENERGY_PRICE,
    DEFAULT_SERVICE_FEE,
    _today,
    _load_tou_energy,
    _load_service_fee,
    _load_parking_fee,
    _load_occupancy_fee,
    settle_charging_session,
)
from app.models.pricing_v2 import PeriodType, FeeType


# ─────────────────────────────────────────────────────────
# 辅助: 自链式 query mock
# ─────────────────────────────────────────────────────────

def _self_query():
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q  # 缺陷1: 查询链新增 order_by, mock 须续链
    return q


# ═══════════════════════════════════════════════════════════
# 1. 日期助手
# ═══════════════════════════════════════════════════════════

def test_today_returns_date_instance():
    assert isinstance(_today(), date)


# ═══════════════════════════════════════════════════════════
# 2. _load_tou_energy
# ═══════════════════════════════════════════════════════════

class TestLoadTouEnergy:
    def test_no_slots_returns_none(self):
        db = MagicMock()
        slots_q = _self_query()
        slots_q.all.return_value = []
        db.query.side_effect = [slots_q]
        assert _load_tou_energy(db, 1, Decimal("10"),
                                datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10)) is None

    def test_no_energy_prices_returns_none(self):
        db = MagicMock()
        slot = SimpleNamespace(id=1, period_type=PeriodType.FLAT,
                               start_time=time(0, 0), end_time=time(23, 59))
        slots_q = _self_query()
        slots_q.all.return_value = [slot]
        ep_q = _self_query()
        ep_q.all.return_value = []
        db.query.side_effect = [slots_q, ep_q]
        assert _load_tou_energy(db, 1, Decimal("10"),
                                datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10)) is None

    def test_slot_id_not_in_prices_returns_none(self):
        db = MagicMock()
        slot = SimpleNamespace(id=1, period_type=PeriodType.FLAT,
                               start_time=time(0, 0), end_time=time(23, 59))
        slots_q = _self_query()
        slots_q.all.return_value = [slot]
        # 电价挂在 slot_id=99, 与 slot.id=1 不匹配 -> time_slots 为空
        ep = SimpleNamespace(slot_id=99, price_per_kwh=Decimal("0.8"))
        ep_q = _self_query()
        ep_q.all.return_value = [ep]
        db.query.side_effect = [slots_q, ep_q]
        assert _load_tou_energy(db, 1, Decimal("10"),
                                datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10)) is None

    def test_full_data_returns_fee_and_breakdown(self):
        db = MagicMock()
        slot = SimpleNamespace(id=1, period_type=PeriodType.FLAT,
                               start_time=time(0, 0), end_time=time(23, 59))
        slots_q = _self_query()
        slots_q.all.return_value = [slot]
        ep = SimpleNamespace(slot_id=1, price_per_kwh=Decimal("0.8"))
        ep_q = _self_query()
        ep_q.all.return_value = [ep]
        db.query.side_effect = [slots_q, ep_q]

        result = _load_tou_energy(db, 1, Decimal("10"),
                                  datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10))
        assert result is not None
        fee, breakdown = result
        # 10 kWh * 0.8 元/kWh, 全落 flat 段
        assert fee == Decimal("8.00")
        assert isinstance(breakdown, list)
        assert len(breakdown) == 1
        assert breakdown[0]["period_name"] == "flat段电费"
        assert breakdown[0]["fee"] == Decimal("8.00")


# ═══════════════════════════════════════════════════════════
# 3. _load_service_fee
# ═══════════════════════════════════════════════════════════

class TestLoadServiceFee:
    def _db_with_first(self, row):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = row
        db.query.return_value = q
        return db

    def test_no_row_returns_none(self):
        db = self._db_with_first(None)
        assert _load_service_fee(db, 1, "app", Decimal("10")) is None

    def test_fixed_fee_type(self):
        row = SimpleNamespace(fee_type=FeeType.FIXED, fee_value=Decimal("2.50"))
        db = self._db_with_first(row)
        assert _load_service_fee(db, 1, "app", Decimal("10")) == Decimal("2.50")

    def test_percent_fee_type(self):
        row = SimpleNamespace(fee_type=FeeType.PERCENT, fee_value=Decimal("0.50"))
        db = self._db_with_first(row)
        # 10 kWh * 0.5 元/kWh
        assert _load_service_fee(db, 1, "app", Decimal("10")) == Decimal("5.00")

    def test_invalid_user_type_falls_back_to_app(self):
        # 非法 user_type 触发 except -> 回落 APP, 不应抛异常
        row = SimpleNamespace(fee_type=FeeType.FIXED, fee_value=Decimal("1.00"))
        db = self._db_with_first(row)
        assert _load_service_fee(db, 1, "bogus_type", Decimal("10")) == Decimal("1.00")


# ═══════════════════════════════════════════════════════════
# 4. _load_parking_fee
# ═══════════════════════════════════════════════════════════

class TestLoadParkingFee:
    def test_zero_minutes_returns_zero(self):
        db = MagicMock()
        assert _load_parking_fee(db, 1, 0, None) == Decimal("0.00")
        assert _load_parking_fee(db, 1, -5, None) == Decimal("0.00")
        db.query.assert_not_called()

    def test_no_row_returns_zero(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = None
        db.query.return_value = q
        assert _load_parking_fee(db, 1, 90, datetime(2026, 1, 1, 9)) == Decimal("0.00")

    def test_full_rule_computes_fee(self):
        db = MagicMock()
        row = SimpleNamespace(
            free_minutes=30, hourly_rate=Decimal("5.00"), daily_cap=None,
            enable_night_rate=False, night_rate=None, night_start=None, night_end=None,
        )
        q = _self_query()
        q.first.return_value = row
        db.query.return_value = q
        # 90 分钟 - 30 免费时长 = 60 计费分钟, 60/60 * 5 = 5.00
        assert _load_parking_fee(db, 1, 90, datetime(2026, 1, 1, 9)) == Decimal("5.00")


# ═══════════════════════════════════════════════════════════
# 5. _load_occupancy_fee
# ═══════════════════════════════════════════════════════════

class TestLoadOccupancyFee:
    def test_zero_minutes_returns_zero(self):
        db = MagicMock()
        assert _load_occupancy_fee(db, 1, 0) == Decimal("0.00")
        assert _load_occupancy_fee(db, 1, -3) == Decimal("0.00")
        db.query.assert_not_called()

    def test_no_row_returns_zero(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = None
        db.query.return_value = q
        assert _load_occupancy_fee(db, 1, 45) == Decimal("0.00")

    def test_full_rule_computes_fee(self):
        db = MagicMock()
        row = SimpleNamespace(
            grace_minutes=15, rate_per_minute=Decimal("0.50"), max_fee=None,
        )
        q = _self_query()
        q.first.return_value = row
        db.query.return_value = q
        # 45 - 15 宽限 = 30 计费分钟 * 0.5 = 15.00
        assert _load_occupancy_fee(db, 1, 45) == Decimal("15.00")

    def test_full_rule_respects_max_fee_cap(self):
        db = MagicMock()
        row = SimpleNamespace(
            grace_minutes=0, rate_per_minute=Decimal("1.00"), max_fee=Decimal("20.00"),
        )
        q = _self_query()
        q.first.return_value = row
        db.query.return_value = q
        # 60 分钟 * 1.0 = 60.00, 但封顶 20.00
        assert _load_occupancy_fee(db, 1, 60) == Decimal("20.00")


# ═══════════════════════════════════════════════════════════
# 6. settle_charging_session
# ═══════════════════════════════════════════════════════════

class TestSettleChargingSession:
    def _order(self):
        order = MagicMock()
        order.station_id = 9001
        order.order_no = "ON-TEST-1"
        return order

    @patch("app.services.charging_pricing.settle_order_fees")
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=None)
    @patch("app.services.charging_pricing._load_tou_energy", return_value=None)
    def test_default_fallback_when_no_pricing(self, _tou, _sf, _park, _occ, _settle):
        db = MagicMock()
        order = self._order()
        fees = settle_charging_session(
            db, order, datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            Decimal("10"),
        )
        # 无定价 -> 默认兜底 0.8/kWh 电费 + 0.5/kWh 服务费
        assert fees["used_default"] is True
        assert fees["energy_fee"] == Decimal("10") * DEFAULT_ENERGY_PRICE
        assert fees["service_fee"] == Decimal("10") * DEFAULT_SERVICE_FEE
        assert fees["parking_fee"] == Decimal("0.00")
        assert fees["reservation_fee"] == Decimal("0.00")
        assert isinstance(fees["energy_fee"], Decimal)
        # settle_order_fees 被调用一次, 传入同一 order
        _settle.assert_called_once()
        assert _settle.call_args[0][0] is order

    @patch("app.services.charging_pricing.settle_order_fees")
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("3.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("5.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=Decimal("2.00"))
    @patch("app.services.charging_pricing._load_tou_energy")
    def test_full_pricing_no_default(self, _tou, _sf, _park, _occ, _settle):
        _tou.return_value = (Decimal("8.00"), [{"period_name": "flat段电费"}])
        db = MagicMock()
        order = self._order()
        fees = settle_charging_session(
            db, order, datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            Decimal("10"), parking_minutes=90, occupancy_minutes=45,
        )
        assert fees["used_default"] is False
        assert fees["energy_fee"] == Decimal("8.00")
        assert fees["service_fee"] == Decimal("2.00")
        assert fees["parking_fee"] == Decimal("5.00")
        assert fees["occupancy_fee"] == Decimal("3.00")
        # energy_breakdown 透传给 settle_order_fees
        _, kwargs = _settle.call_args
        assert kwargs.get("energy_breakdown") == [{"period_name": "flat段电费"}]

    @patch("app.services.charging_pricing.settle_order_fees")
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=Decimal("2.00"))
    @patch("app.services.charging_pricing._load_tou_energy", return_value=None)
    def test_mixed_pricing_partial_default(self, _tou, _sf, _park, _occ, _settle):
        # 电费缺失(兜底) + 服务费有定价 -> 仍标 used_default
        db = MagicMock()
        order = self._order()
        fees = settle_charging_session(
            db, order, datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            Decimal("10"),
        )
        assert fees["used_default"] is True
        assert fees["energy_fee"] == Decimal("8.00")  # 兜底
        assert fees["service_fee"] == Decimal("2.00")  # 真实定价


# ═══════════════════════════════════════════════════════════
# 7. 异常保护加固 (卡 01b3880b)
#    DB异常 / Decimal脏数据 / billing_engine异常 → 兜底不崩整个结算流程
# ═══════════════════════════════════════════════════════════

class TestExceptionProtection:

    def _order(self):
        order = MagicMock()
        order.station_id = 9001
        order.order_no = "ON-ERR-1"
        return order

    # ── _load_* DB 异常 → 各自兜底值(等价"无定价") ──

    def test_load_tou_energy_db_error_returns_none(self):
        db = MagicMock()
        db.query.side_effect = SQLAlchemyError("db down")
        assert _load_tou_energy(db, 1, Decimal("10"),
                                datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10)) is None

    def test_load_service_fee_db_error_returns_none(self):
        db = MagicMock()
        db.query.side_effect = SQLAlchemyError("db down")
        assert _load_service_fee(db, 1, "app", Decimal("10")) is None

    def test_load_parking_fee_db_error_returns_zero(self):
        db = MagicMock()
        db.query.side_effect = SQLAlchemyError("db down")
        assert _load_parking_fee(db, 1, 90, datetime(2026, 1, 1, 9)) == Decimal("0.00")

    def test_load_occupancy_fee_db_error_returns_zero(self):
        db = MagicMock()
        db.query.side_effect = SQLAlchemyError("db down")
        assert _load_occupancy_fee(db, 1, 45) == Decimal("0.00")

    # ── Decimal 脏数据 → 兜底(InvalidOperation 等价于无可用定价) ──

    def test_load_tou_energy_invalid_price_returns_none(self):
        db = MagicMock()
        slot = SimpleNamespace(id=1, period_type=PeriodType.FLAT,
                               start_time=time(0, 0), end_time=time(23, 59))
        slots_q = _self_query()
        slots_q.all.return_value = [slot]
        ep = SimpleNamespace(slot_id=1, price_per_kwh="!!not_a_number!!")
        ep_q = _self_query()
        ep_q.all.return_value = [ep]
        db.query.side_effect = [slots_q, ep_q]
        # Decimal("!!not_a_number!!") 抛 InvalidOperation → 兜底 None
        assert _load_tou_energy(db, 1, Decimal("10"),
                                datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10)) is None

    # ── billing_engine 计算异常 → 兜底 ──

    @patch("app.services.charging_pricing.compute_service_fee_multi",
           side_effect=ValueError("compute boom"))
    def test_load_service_fee_compute_error_returns_none(self, _compute):
        db = MagicMock()
        row = SimpleNamespace(fee_type=FeeType.FIXED, fee_value=Decimal("2.50"))
        q = _self_query()
        q.first.return_value = row
        db.query.return_value = q
        assert _load_service_fee(db, 1, "app", Decimal("10")) is None

    # ── settle 主体异常保护: 不抛, rollback + 返回错误 dict ──

    @patch("app.services.charging_pricing.settle_order_fees")
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=None)
    @patch("app.services.charging_pricing._load_tou_energy", return_value=None)
    def test_settle_commit_error_rolls_back_and_returns_error(
        self, _tou, _sf, _park, _occ, _settle):
        db = MagicMock()
        db.commit.side_effect = SQLAlchemyError("commit failed")
        result = settle_charging_session(
            db, self._order(), datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            Decimal("10"),
        )
        # commit 失败不抛, 返回错误标记 dict, 并 rollback
        assert "error" in result
        db.rollback.assert_called_once()
        _settle.assert_called_once()  # settle_order_fees 已执行, 失败发生在其后的 commit

    @patch("app.services.charging_pricing.settle_order_fees",
           side_effect=SQLAlchemyError("write failed"))
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=Decimal("2.00"))
    @patch("app.services.charging_pricing._load_tou_energy", return_value=None)
    def test_settle_write_error_returns_error(self, _tou, _sf, _park, _occ, _settle):
        db = MagicMock()
        result = settle_charging_session(
            db, self._order(), datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10),
            Decimal("10"),
        )
        assert "error" in result
        db.rollback.assert_called_once()
        db.commit.assert_not_called()  # 写明细失败, 未推进到 commit


# ═══════════════════════════════════════════════════════════════
# 8. 定价日期语义: settle 以充电日(start_time.date())为定价基准日, 非结算执行日 today
#    跨午夜充电或延迟结算(次日结算前一天订单)时, 应按"充电日"价格而非"结算日"价格计费。
# ═══════════════════════════════════════════════════════════════

class TestSettleUsesChargingDate:
    """settle_charging_session 把 start_time.date() 作为 charging_date 透传给所有 _load_*,
    使生效期过滤基于充电日(而非结算执行日 today)。"""

    def _order(self):
        order = MagicMock()
        order.station_id = 9001
        order.order_no = "ON-DATE-1"
        return order

    @patch("app.services.charging_pricing.settle_order_fees")
    @patch("app.services.charging_pricing._load_occupancy_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_parking_fee", return_value=Decimal("0.00"))
    @patch("app.services.charging_pricing._load_service_fee", return_value=Decimal("2.00"))
    @patch("app.services.charging_pricing._load_tou_energy", return_value=None)
    def test_settle_passes_charging_date_to_all_loaders(
        self, _tou, _sf, _park, _occ, _settle,
    ):
        db = MagicMock()
        order = self._order()
        # 充电日 2026-08-02(可能早于结算执行日 today)
        start = datetime(2026, 8, 2, 10, 0)
        end = datetime(2026, 8, 2, 14, 0)
        settle_charging_session(db, order, start, end, Decimal("10"))

        expected = date(2026, 8, 2)
        # 4 个 _load_* 都应收到 charging_date=start.date()
        for loader in (_tou, _sf, _park, _occ):
            assert loader.call_args.kwargs.get("charging_date") == expected


# ═══════════════════════════════════════════════════════════════
# 9. 定价基准日业务时区 (缺陷2): _today/_biz_date 走业务时区, 非容器本地
# ═══════════════════════════════════════════════════════════════

class TestBizTzDate:
    """_today() 委托业务时区 today_in_biz_tz()(非容器 date.today());
    _biz_date(): aware→astimezone(biz)取date, naive→按biz时区表面解释取date。"""

    def test_today_delegates_to_biz_tz(self, monkeypatch):
        # _today 不再读 date.today(), 而委托 today_in_biz_tz
        from app.services import charging_pricing as cp
        monkeypatch.setattr(cp, "today_in_biz_tz", lambda: date(2026, 8, 7))
        assert cp._today() == date(2026, 8, 7)

    def test_biz_date_aware_utc_crosses_midnight_to_shanghai(self):
        # aware UTC 2026-08-02 16:00 = 上海 2026-08-03 00:00
        from app.services.charging_pricing import _biz_date
        start = datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc)
        assert _biz_date(start) == date(2026, 8, 3)

    def test_biz_date_naive_interpreted_as_biz_tz(self):
        # naive 按业务时区表面解释(仅贴 tz, 不偏移), date 不变
        from app.services.charging_pricing import _biz_date
        naive = datetime(2026, 8, 2, 23, 30)
        assert _biz_date(naive) == date(2026, 8, 2)

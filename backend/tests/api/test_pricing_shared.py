"""定价管理共享模块单元测试 — app/api/v1/pricing_management/_shared.py

_shared.py 无路由端点，仅含：日期/时间解析与格式化 helper + 6 类定价 Pydantic schema
+ router 级鉴权依赖。本测试为纯单元测试（helper + schema 校验），不依赖 DB/client。
"""
from datetime import date, datetime, time as dt_time

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.pricing_management._shared import (
    _parse_time, _parse_date, _fmt_time, _fmt_date, _fmt_dt,
    TimeSlotCreate, EnergyPriceCreate, OrderEstimateRequest,
    ParkingPriceCreate, OccupancyFeeCreate, ServiceFeeCreate, ReservationFeeCreate,
    _ROUTER_DEPENDENCIES,
)


# ─── _parse_time ───

class TestParseTime:
    def test_normal(self):
        assert _parse_time("09:30") == dt_time(9, 30)

    def test_zero_padded(self):
        assert _parse_time("00:00") == dt_time(0, 0)

    def test_single_digit(self):
        assert _parse_time("9:5") == dt_time(9, 5)

    def test_none(self):
        assert _parse_time(None) is None

    def test_empty_string(self):
        assert _parse_time("") is None

    def test_invalid_format_raises_400(self):
        """非法时间格式 → HTTPException 400 (卡 f3e5633d 加固, 不裸奔 500)。"""
        with pytest.raises(HTTPException) as ei:
            _parse_time("25时")
        assert ei.value.status_code == 400


# ─── _parse_date ───

class TestParseDate:
    def test_normal(self):
        assert _parse_date("2026-01-15") == date(2026, 1, 15)

    def test_invalid_format_raises_400(self):
        """非法日期格式 → HTTPException 400 (卡 f3e5633d 加固, 不裸奔 500)。"""
        with pytest.raises(HTTPException) as ei:
            _parse_date("2026/01/15")
        assert ei.value.status_code == 400


# ─── _fmt_time ───

class TestFmtTime:
    def test_normal(self):
        assert _fmt_time(dt_time(9, 30)) == "09:30"

    def test_zero_padded(self):
        assert _fmt_time(dt_time(9, 5)) == "09:05"

    def test_none(self):
        assert _fmt_time(None) is None


# ─── _fmt_date ───

class TestFmtDate:
    def test_normal(self):
        assert _fmt_date(date(2026, 1, 15)) == "2026-01-15"

    def test_none(self):
        assert _fmt_date(None) is None


# ─── _fmt_dt ───

class TestFmtDt:
    def test_normal(self):
        dt = datetime(2026, 1, 15, 9, 30, 0)
        assert _fmt_dt(dt) == dt.isoformat()

    def test_none(self):
        assert _fmt_dt(None) is None


# ─── Schema 校验 ───

class TestTimeSlotCreateSchema:
    def test_ok(self):
        s = TimeSlotCreate(name="峰时", period_type="peak", start_time="08:00", end_time="12:00")
        assert s.name == "峰时"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            TimeSlotCreate(name="", period_type="peak", start_time="08:00", end_time="12:00")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            TimeSlotCreate(name="x" * 51, period_type="peak", start_time="08:00", end_time="12:00")

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            TimeSlotCreate(period_type="peak", start_time="08:00", end_time="12:00")


class TestEnergyPriceCreateSchema:
    def test_ok(self):
        s = EnergyPriceCreate(station_id=1, slot_id=2, price_per_kwh=1.2,
                              effective_date="2026-01-01")
        assert s.price_per_kwh == 1.2

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            EnergyPriceCreate(station_id=1, slot_id=2, price_per_kwh=-1,
                              effective_date="2026-01-01")


class TestServiceFeeCreateSchema:
    def test_negative_fee_rejected(self):
        with pytest.raises(ValidationError):
            ServiceFeeCreate(station_id=1, user_type="app", fee_type="fixed",
                             fee_value=-5, effective_date="2026-01-01")


class TestParkingPriceCreateSchema:
    def test_negative_free_minutes_rejected(self):
        with pytest.raises(ValidationError):
            ParkingPriceCreate(station_id=1, free_minutes=-1, hourly_rate=2.0,
                               effective_date="2026-01-01")

    def test_negative_hourly_rate_rejected(self):
        with pytest.raises(ValidationError):
            ParkingPriceCreate(station_id=1, hourly_rate=-1, effective_date="2026-01-01")


class TestOccupancyFeeCreateSchema:
    def test_negative_rate_rejected(self):
        with pytest.raises(ValidationError):
            OccupancyFeeCreate(station_id=1, rate_per_minute=-0.5, effective_date="2026-01-01")


class TestReservationFeeCreateSchema:
    def test_negative_deposit_rejected(self):
        with pytest.raises(ValidationError):
            ReservationFeeCreate(station_id=1, reservation_policy="flat",
                                 deposit_amount=-10, effective_date="2026-01-01")


class TestOrderEstimateRequestSchema:
    def test_ok(self):
        s = OrderEstimateRequest(station_id=1, energy_kwh=10.5)
        assert s.energy_kwh == 10.5
        assert s.user_type == "app"  # 默认值
        assert s.charging_minutes == 0  # 默认值

    def test_negative_energy_rejected(self):
        with pytest.raises(ValidationError):
            OrderEstimateRequest(station_id=1, energy_kwh=-1)

    def test_negative_charging_minutes_rejected(self):
        with pytest.raises(ValidationError):
            OrderEstimateRequest(station_id=1, energy_kwh=1, charging_minutes=-5)


# ─── router 级鉴权依赖 ───

class TestRouterDependencies:
    def test_dependencies_non_empty(self):
        """_ROUTER_DEPENDENCIES 必须携带 admin 角色鉴权依赖"""
        assert len(_ROUTER_DEPENDENCIES) >= 1

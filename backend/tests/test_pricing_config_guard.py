"""
定价配置面资金字段负值守卫测试 (卡7fef5042)

覆盖:
- pricing_management/_shared.py Update 模型 11 字段负值 → ValidationError
- pricing.py PricingCreate/PricingUpdate idle_penalty_per_min 负值 → ValidationError
- order_fees.py SettleRequest 三费率负值 → ValidationError
- 正常值通过, None(不更新) 通过

背景: Update 模型此前无 ge=0, 可绕过 Create 守卫写负费率, 污染计费资金边界。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.order_fees import SettleRequest
from app.api.v1.pricing import PricingCreate, PricingUpdate
from app.api.v1.pricing_management._shared import (
    EnergyPriceUpdate,
    OccupancyFeeUpdate,
    ParkingPriceUpdate,
    ReservationFeeUpdate,
    ServiceFeeUpdate,
)


class TestEnergyPriceUpdateGuard:
    def test_negative_price_per_kwh_rejected(self):
        with pytest.raises(ValidationError):
            EnergyPriceUpdate(price_per_kwh=-0.1)

    def test_normal_accepted(self):
        req = EnergyPriceUpdate(price_per_kwh=1.5)
        assert req.price_per_kwh == 1.5
        assert EnergyPriceUpdate().price_per_kwh is None


class TestServiceFeeUpdateGuard:
    def test_negative_fee_value_rejected(self):
        with pytest.raises(ValidationError):
            ServiceFeeUpdate(fee_value=-0.5)

    def test_normal_accepted(self):
        assert ServiceFeeUpdate(fee_value=0.8).fee_value == 0.8


class TestParkingPriceUpdateGuard:
    def test_negative_hourly_rate_rejected(self):
        with pytest.raises(ValidationError):
            ParkingPriceUpdate(hourly_rate=-1.0)

    def test_negative_night_rate_rejected(self):
        with pytest.raises(ValidationError):
            ParkingPriceUpdate(night_rate=-0.01)

    def test_normal_accepted(self):
        req = ParkingPriceUpdate(hourly_rate=2.0, night_rate=1.0)
        assert req.hourly_rate == 2.0
        assert req.night_rate == 1.0


class TestOccupancyFeeUpdateGuard:
    def test_negative_rate_per_minute_rejected(self):
        with pytest.raises(ValidationError):
            OccupancyFeeUpdate(rate_per_minute=-0.1)

    def test_negative_max_fee_rejected(self):
        with pytest.raises(ValidationError):
            OccupancyFeeUpdate(max_fee=-1.0)

    def test_normal_accepted(self):
        req = OccupancyFeeUpdate(rate_per_minute=0.5, max_fee=30.0)
        assert req.rate_per_minute == 0.5
        assert req.max_fee == 30.0


class TestReservationFeeUpdateGuard:
    def test_negative_deposit_amount_rejected(self):
        with pytest.raises(ValidationError):
            ReservationFeeUpdate(deposit_amount=-1.0)

    def test_negative_fee_amount_rejected(self):
        with pytest.raises(ValidationError):
            ReservationFeeUpdate(fee_amount=-0.01)

    def test_negative_no_show_penalty_rejected(self):
        with pytest.raises(ValidationError):
            ReservationFeeUpdate(no_show_penalty=-5.0)

    def test_normal_accepted(self):
        req = ReservationFeeUpdate(deposit_amount=10.0, fee_amount=1.0, no_show_penalty=0.0)
        assert req.deposit_amount == 10.0
        assert req.fee_amount == 1.0
        assert req.no_show_penalty == 0.0


class TestPricingIdlePenaltyGuard:
    def test_create_negative_rejected(self):
        with pytest.raises(ValidationError):
            PricingCreate(
                name="p",
                period_type="flat",
                start_time="00:00",
                end_time="23:59",
                idle_penalty_per_min=-0.1,
            )

    def test_update_negative_rejected(self):
        with pytest.raises(ValidationError):
            PricingUpdate(idle_penalty_per_min=-0.1)

    def test_normal_accepted(self):
        req = PricingCreate(
            name="p", period_type="flat", start_time="00:00", end_time="23:59", idle_penalty_per_min=0.2
        )
        assert req.idle_penalty_per_min == 0.2
        assert PricingUpdate(idle_penalty_per_min=0.0).idle_penalty_per_min == 0.0
        assert PricingUpdate().idle_penalty_per_min is None


class TestSettleRequestRateGuard:
    def test_negative_parking_rate_rejected(self):
        with pytest.raises(ValidationError):
            SettleRequest(parking_rate=-1.0)

    def test_negative_occupancy_rate_rejected(self):
        with pytest.raises(ValidationError):
            SettleRequest(occupancy_rate=-0.1)

    def test_negative_reservation_rate_rejected(self):
        with pytest.raises(ValidationError):
            SettleRequest(reservation_rate=-0.01)

    def test_normal_accepted(self):
        req = SettleRequest(parking_rate=1.0, occupancy_rate=0.5, reservation_rate=0.2)
        assert req.parking_rate == 1.0
        assert req.occupancy_rate == 0.5
        assert req.reservation_rate == 0.2

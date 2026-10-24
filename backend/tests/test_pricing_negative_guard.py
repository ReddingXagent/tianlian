"""
资金边界负值守卫测试 (卡26696f22)

覆盖:
- PricingCreate.electricity_price 负值 → 422 (ValidationError)
- PricingCreate.service_fee_rate 负值 → 422
- PricingCreate.parking_fee_per_hour 负值 → 422
- PricingUpdate 同字段负值 → 422
- SettleRequest.peak_price 负值 → 422
- 合法正常值 → 通过, 不回归

背景: 负电价/负费率写入定价规则或结算快照会污染资金计算。
前置核查: 仓库无现货负电价支持(EnergyPriceSpot 仅建结构 P3 用),
故 electricity_price 不豁免, 统一 ge=0。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.order_fees import SettleRequest
from app.api.v1.pricing import PricingCreate, PricingUpdate


class TestPricingCreateGuard:
    """PricingCreate 三费率必须 >=0。"""

    def test_negative_electricity_price_rejected(self):
        with pytest.raises(ValidationError):
            PricingCreate(electricity_price=-0.01)

    def test_negative_service_fee_rate_rejected(self):
        with pytest.raises(ValidationError):
            PricingCreate(service_fee_rate=-1.0)

    def test_negative_parking_fee_rejected(self):
        with pytest.raises(ValidationError):
            PricingCreate(parking_fee_per_hour=-0.5)

    def test_normal_values_accepted(self):
        req = PricingCreate(
            name="测试规则",
            period_type="peak",
            start_time="08:00",
            end_time="12:00",
            electricity_price=1.0,
            service_fee_rate=0.4,
            parking_fee_per_hour=2.0,
        )
        assert req.electricity_price == 1.0
        assert req.service_fee_rate == 0.4
        assert req.parking_fee_per_hour == 2.0

    def test_zero_accepted(self):
        """零值合法 (ge=0 含边界)。"""
        req = PricingCreate(
            name="零费率", period_type="flat", start_time="00:00", end_time="23:59",
            electricity_price=0.0, service_fee_rate=0.0, parking_fee_per_hour=0.0,
        )
        assert req.electricity_price == 0.0


class TestPricingUpdateGuard:
    """PricingUpdate 三费率负值同样拒绝 (None 表示不更新)。"""

    def test_negative_electricity_price_rejected(self):
        with pytest.raises(ValidationError):
            PricingUpdate(electricity_price=-0.01)

    def test_negative_service_fee_rate_rejected(self):
        with pytest.raises(ValidationError):
            PricingUpdate(service_fee_rate=-0.1)

    def test_negative_parking_fee_rejected(self):
        with pytest.raises(ValidationError):
            PricingUpdate(parking_fee_per_hour=-1)

    def test_none_and_normal_accepted(self):
        assert PricingUpdate().electricity_price is None
        req = PricingUpdate(electricity_price=0.8, service_fee_rate=0.3, parking_fee_per_hour=0.0)
        assert req.electricity_price == 0.8


class TestSettlePriceSnapshotGuard:
    """SettleRequest 电价快照 5 字段必须 >=0。"""

    def test_negative_peak_price_rejected(self):
        with pytest.raises(ValidationError):
            SettleRequest(peak_price=-0.01)

    def test_negative_prices_and_rate_rejected(self):
        for kw in (
            {"flat_price": -1}, {"valley_price": -1}, {"trough_price": -1},
            {"service_fee_rate": -0.1},
        ):
            with pytest.raises(ValidationError):
                SettleRequest(**kw)

    def test_normal_prices_accepted(self):
        req = SettleRequest(
            peak_price=1.2, flat_price=0.7, valley_price=0.3, trough_price=0.2,
            service_fee_rate=0.4,
        )
        assert req.peak_price == 1.2
        assert req.service_fee_rate == 0.4

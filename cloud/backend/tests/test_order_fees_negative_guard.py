"""
资金边界负值守卫测试 (卡0ffbd29e)

覆盖:
- SettleRequest.coupon_amount 负值 → 422 (ValidationError)
- SettleRequest.points_amount 负值 → 422
- ParkingDiscountCreate.discount_percent 负值 → 422
- 合法正常值 → 通过, 不回归

背景: 负抵扣会导致 paid_amount = total - (负值) 膨胀高于总额(用户多付),
且费用明细静默缺失。Pydantic ValidationError 是 FastAPI 422 的来源。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.order_fees import SettleRequest
from app.api.v1.parking import ParkingDiscountCreate


class TestSettleCouponPointsGuard:
    """coupon_amount/points_amount 必须 >=0 且 <=100000 (对齐 discount_amount 风格)。"""

    def test_negative_coupon_rejected(self):
        """负优惠券抵扣 → 422。"""
        with pytest.raises(ValidationError):
            SettleRequest(coupon_amount=-0.01)

    def test_negative_points_rejected(self):
        """负积分抵扣 → 422。"""
        with pytest.raises(ValidationError):
            SettleRequest(points_amount=-1.0)

    def test_normal_coupon_points_accepted(self):
        """合法正常值通过。"""
        req = SettleRequest(coupon_amount=5.0, points_amount=2.5, discount_amount=3.0)
        assert req.coupon_amount == 5.0
        assert req.points_amount == 2.5

    def test_zero_coupon_points_accepted(self):
        """零值合法 (ge=0 含边界)。"""
        req = SettleRequest()
        assert req.coupon_amount == 0.0
        assert req.points_amount == 0.0


class TestParkingDiscountGuard:
    """free_minutes/discount_percent/fixed_amount 必须 >=0, percent 另有 le=100。"""

    def test_negative_discount_percent_rejected(self):
        """负折扣比例 → 422。"""
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, discount_percent=-1.0)

    def test_negative_free_minutes_rejected(self):
        """负免费时长 → 422。"""
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, free_minutes=-5)

    def test_negative_fixed_amount_rejected(self):
        """负固定减免 → 422。"""
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, fixed_amount=-0.01)

    def test_percent_over_100_rejected(self):
        """折扣比例 >100 → 422。"""
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, discount_percent=100.5)

    def test_normal_values_accepted(self):
        """合法正常值通过。"""
        req = ParkingDiscountCreate(station_id=1, free_minutes=30,
                                    discount_percent=80.0, fixed_amount=2.0)
        assert req.free_minutes == 30
        assert req.discount_percent == 80.0
        assert req.fixed_amount == 2.0

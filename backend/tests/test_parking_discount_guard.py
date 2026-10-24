"""
停车折扣资金边界负值守卫测试 (卡c98f486a)

覆盖:
- ParkingDiscountCreate: free_minutes/discount_percent/fixed_amount/max_discount 负值 → 422
- ParkingDiscountCreate: discount_percent > 100 → 422
- ParkingDiscountUpdate: 同字段负值/超界 → 422 (None 表示不更新)
- 合法正常值 → 通过, 不回归

背景: PUT 此前可绕过 Create 守卫写负折扣/负减免, 污染停车计费资金边界。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.parking import ParkingDiscountCreate, ParkingDiscountUpdate


class TestParkingDiscountCreateGuard:
    """ParkingDiscountCreate 四资金字段必须 >=0, percent <=100。"""

    def test_negative_free_minutes_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, free_minutes=-10)

    def test_negative_discount_percent_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, discount_percent=-5.0)

    def test_discount_percent_over_100_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, discount_percent=100.5)

    def test_negative_fixed_amount_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, fixed_amount=-1.0)

    def test_negative_max_discount_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountCreate(station_id=1, max_discount=-0.01)

    def test_normal_values_accepted(self):
        req = ParkingDiscountCreate(
            station_id=1,
            free_minutes=30,
            discount_percent=80.0,
            fixed_amount=2.0,
            max_discount=5.0,
        )
        assert req.free_minutes == 30
        assert req.discount_percent == 80.0
        assert req.fixed_amount == 2.0
        assert req.max_discount == 5.0


class TestParkingDiscountUpdateGuard:
    """ParkingDiscountUpdate 同守卫 (None 表示不更新)。"""

    def test_negative_free_minutes_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountUpdate(free_minutes=-1)

    def test_negative_discount_percent_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountUpdate(discount_percent=-0.1)

    def test_discount_percent_over_100_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountUpdate(discount_percent=101)

    def test_negative_fixed_amount_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountUpdate(fixed_amount=-1.0)

    def test_negative_max_discount_rejected(self):
        with pytest.raises(ValidationError):
            ParkingDiscountUpdate(max_discount=-0.01)

    def test_none_and_normal_accepted(self):
        assert ParkingDiscountUpdate().fixed_amount is None
        req = ParkingDiscountUpdate(
            free_minutes=0, discount_percent=100.0, fixed_amount=0.0, max_discount=0.0
        )
        assert req.discount_percent == 100.0

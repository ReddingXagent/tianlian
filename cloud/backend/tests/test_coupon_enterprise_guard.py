"""
资金边界守卫测试 · 第8弹 优惠与企业账户面 (卡f4323e17)

覆盖:
- CouponCreate/CouponUpdate min_order_amount / max_discount_amount / per_user_limit 负值 → ValidationError
- DiscountCreate/DiscountUpdate max_discount_amount 负值 → ValidationError
- EnterpriseCreate/EnterpriseUpdate balance / credit_limit 负值 → ValidationError
- 正常值通过, None(不更新) 通过

背景: 负门槛/负面额券污染优惠计算, per_user_limit 负值等同无限领;
企业余额/信用额度负值绕过资金边界, 余额调减应走专用调整接口(留痕)。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.enterprises import EnterpriseCreate, EnterpriseUpdate
from app.api.v1.operate.coupon_api import CouponCreate, CouponUpdate
from app.api.v1.operate.discount import DiscountCreate, DiscountUpdate


def _coupon_kwargs(**overrides):
    kwargs = dict(
        name="测试券",
        face_value=10.0,
        total_stock=100,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-12-31T23:59:59Z",
    )
    kwargs.update(overrides)
    return kwargs


class TestCouponCreateGuard:
    def test_negative_min_order_amount_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(**_coupon_kwargs(min_order_amount=-0.1))

    def test_negative_max_discount_amount_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(**_coupon_kwargs(max_discount_amount=-1.0))

    def test_negative_per_user_limit_rejected(self):
        with pytest.raises(ValidationError):
            CouponCreate(**_coupon_kwargs(per_user_limit=-1))

    def test_normal_accepted(self):
        req = CouponCreate(
            **_coupon_kwargs(min_order_amount=50.0, max_discount_amount=20.0, per_user_limit=3)
        )
        assert req.min_order_amount == 50.0
        assert req.max_discount_amount == 20.0
        assert req.per_user_limit == 3


class TestCouponUpdateGuard:
    def test_negative_min_order_amount_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(min_order_amount=-0.01)

    def test_negative_max_discount_amount_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(max_discount_amount=-5.0)

    def test_negative_per_user_limit_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(per_user_limit=-2)

    def test_normal_and_none_accepted(self):
        req = CouponUpdate(min_order_amount=30.0, max_discount_amount=10.0, per_user_limit=0)
        assert req.min_order_amount == 30.0
        assert req.max_discount_amount == 10.0
        assert req.per_user_limit == 0
        assert CouponUpdate().min_order_amount is None
        assert CouponUpdate().max_discount_amount is None
        assert CouponUpdate().per_user_limit is None


def _discount_kwargs(**overrides):
    kwargs = dict(
        name="测试折扣",
        discount_rate=0.8,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-12-31T23:59:59Z",
    )
    kwargs.update(overrides)
    return kwargs


class TestDiscountCreateGuard:
    def test_negative_max_discount_amount_rejected(self):
        with pytest.raises(ValidationError):
            DiscountCreate(**_discount_kwargs(max_discount_amount=-1.0))

    def test_normal_accepted(self):
        assert DiscountCreate(**_discount_kwargs(max_discount_amount=15.0)).max_discount_amount == 15.0


class TestDiscountUpdateGuard:
    def test_negative_max_discount_amount_rejected(self):
        with pytest.raises(ValidationError):
            DiscountUpdate(max_discount_amount=-0.5)

    def test_normal_and_none_accepted(self):
        assert DiscountUpdate(max_discount_amount=8.0).max_discount_amount == 8.0
        assert DiscountUpdate().max_discount_amount is None


def _enterprise_kwargs(**overrides):
    kwargs = dict(name="测试企业", code="ENT001")
    kwargs.update(overrides)
    return kwargs


class TestEnterpriseCreateGuard:
    def test_negative_balance_rejected(self):
        with pytest.raises(ValidationError):
            EnterpriseCreate(**_enterprise_kwargs(balance=-100.0))

    def test_negative_credit_limit_rejected(self):
        with pytest.raises(ValidationError):
            EnterpriseCreate(**_enterprise_kwargs(credit_limit=-0.01))

    def test_normal_accepted(self):
        req = EnterpriseCreate(**_enterprise_kwargs(balance=1000.0, credit_limit=500.0))
        assert req.balance == 1000.0
        assert req.credit_limit == 500.0


class TestEnterpriseUpdateGuard:
    def test_negative_balance_rejected(self):
        with pytest.raises(ValidationError):
            EnterpriseUpdate(balance=-1.0)

    def test_negative_credit_limit_rejected(self):
        with pytest.raises(ValidationError):
            EnterpriseUpdate(credit_limit=-50.0)

    def test_normal_and_none_accepted(self):
        req = EnterpriseUpdate(balance=2000.0, credit_limit=0.0)
        assert req.balance == 2000.0
        assert req.credit_limit == 0.0
        assert EnterpriseUpdate().balance is None
        assert EnterpriseUpdate().credit_limit is None

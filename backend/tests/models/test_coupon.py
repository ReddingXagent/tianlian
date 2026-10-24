#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coupon / CouponBatch / CouponUsage 模型测试
"""
import pytest
from datetime import datetime
from decimal import Decimal
from app.models.coupon import Coupon, CouponBatch, CouponUsage, CouponType, CouponStatus


class TestCouponModel:
    def test_coupon_type_enum_values(self):
        assert CouponType.FIXED.value == "fixed"
        assert CouponType.PERCENTAGE.value == "percentage"
        assert CouponType.FREE_CHARGE.value == "free_charge"
        assert CouponType.SERVICE_FREE.value == "service_free"

    def test_coupon_status_enum_values(self):
        assert CouponStatus.ACTIVE.value == "active"
        assert CouponStatus.USED.value == "used"
        assert CouponStatus.EXPIRED.value == "expired"
        assert CouponStatus.DISABLED.value == "disabled"

    def test_coupon_columns(self):
        cols = [c.name for c in Coupon.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "coupon_type" in cols
        assert "face_value" in cols
        assert "min_order_amount" in cols
        assert "max_discount_amount" in cols
        assert "applicable_user_types" in cols
        assert "applicable_stations" in cols
        assert "total_stock" in cols
        assert "remaining_stock" in cols
        assert "per_user_limit" in cols
        assert "valid_days" in cols
        assert "start_time" in cols
        assert "end_time" in cols
        assert "is_active" in cols
        assert "description" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_coupon_batch_columns(self):
        cols = [c.name for c in CouponBatch.__table__.columns]
        assert "id" in cols
        assert "coupon_id" in cols
        assert "batch_name" in cols
        assert "quantity" in cols
        assert "user_type" in cols
        assert "user_ids" in cols
        assert "distributed_at" in cols
        assert "created_at" in cols

    def test_coupon_usage_columns(self):
        cols = [c.name for c in CouponUsage.__table__.columns]
        assert "id" in cols
        assert "coupon_id" in cols
        assert "batch_id" in cols
        assert "user_id" in cols
        assert "user_type" in cols
        assert "coupon_code" in cols
        assert "order_id" in cols
        assert "status" in cols
        assert "discount_amount" in cols
        assert "used_at" in cols
        assert "expires_at" in cols
        assert "received_at" in cols
        assert "created_at" in cols


class TestCouponModelCreation:
    def test_create_coupon_fixed(self, db_session):
        coupon = Coupon(
            name="新用户立减10元",
            coupon_type=CouponType.FIXED,
            face_value=Decimal("10.00"),
            min_order_amount=Decimal("20.00"),
            max_discount_amount=Decimal("10.00"),
            applicable_user_types="app",
            applicable_stations="1,2",
            total_stock=100,
            remaining_stock=100,
            per_user_limit=1,
            valid_days=30,
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
            is_active=True,
            description="新用户首单立减10元",
        )
        db_session.add(coupon)
        db_session.commit()
        db_session.refresh(coupon)

        assert coupon.id is not None
        assert coupon.name == "新用户立减10元"
        assert coupon.coupon_type == CouponType.FIXED
        assert float(coupon.face_value) == 10.00
        assert float(coupon.min_order_amount) == 20.00
        assert float(coupon.max_discount_amount) == 10.00
        assert coupon.total_stock == 100
        assert coupon.remaining_stock == 100

    def test_create_coupon_percentage(self, db_session):
        coupon = Coupon(
            name="全场9折券",
            coupon_type=CouponType.PERCENTAGE,
            face_value=Decimal("0.90"),
            min_order_amount=Decimal("0.00"),
            total_stock=500,
            remaining_stock=500,
            per_user_limit=2,
            valid_days=7,
            start_time=datetime(2026, 6, 1, 0, 0, 0),
            end_time=datetime(2026, 6, 30, 23, 59, 59),
            is_active=True,
        )
        db_session.add(coupon)
        db_session.commit()
        db_session.refresh(coupon)

        assert coupon.id is not None
        assert coupon.coupon_type == CouponType.PERCENTAGE
        assert float(coupon.face_value) == 0.90

    def test_create_coupon_batch(self, db_session):
        coupon = Coupon(
            name="测试券",
            coupon_type=CouponType.FIXED,
            face_value=Decimal("5.00"),
            total_stock=100,
            remaining_stock=100,
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
        )
        db_session.add(coupon)
        db_session.commit()
        db_session.refresh(coupon)

        batch = CouponBatch(
            coupon_id=coupon.id,
            batch_name="首发批次",
            quantity=50,
            user_type="app",
            user_ids="1,2,3,4,5",
        )
        db_session.add(batch)
        db_session.commit()
        db_session.refresh(batch)

        assert batch.id is not None
        assert batch.coupon_id == coupon.id
        assert batch.batch_name == "首发批次"
        assert batch.quantity == 50

    def test_create_coupon_usage(self, db_session):
        coupon = Coupon(
            name="使用测试券",
            coupon_type=CouponType.FIXED,
            face_value=Decimal("8.00"),
            total_stock=100,
            remaining_stock=100,
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
        )
        db_session.add(coupon)
        db_session.commit()
        db_session.refresh(coupon)

        usage = CouponUsage(
            coupon_id=coupon.id,
            batch_id=None,
            user_id=1,
            user_type="app",
            coupon_code="CPN-TEST123456",
            status=CouponStatus.ACTIVE,
            expires_at=datetime(2026, 2, 1, 0, 0, 0),
        )
        db_session.add(usage)
        db_session.commit()
        db_session.refresh(usage)

        assert usage.id is not None
        assert usage.coupon_code == "CPN-TEST123456"
        assert usage.status == CouponStatus.ACTIVE
        assert usage.user_id == 1
        assert usage.user_type == "app"
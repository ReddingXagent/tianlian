#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PriceDiscount / DiscountGroup 模型测试
"""
import pytest
from datetime import datetime
from decimal import Decimal
from app.models.price_discount import PriceDiscount, DiscountGroup, DiscountType


class TestPriceDiscountModel:
    def test_discount_type_enum_values(self):
        assert DiscountType.PERCENTAGE.value == "percentage"
        assert DiscountType.FIXED.value == "fixed"
        assert DiscountType.TIERED.value == "tiered"

    def test_price_discount_columns(self):
        cols = [c.name for c in PriceDiscount.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "discount_type" in cols
        assert "discount_rate" in cols
        assert "applicable_user_types" in cols
        assert "min_consumption" in cols
        assert "max_discount_amount" in cols
        assert "start_time" in cols
        assert "end_time" in cols
        assert "priority" in cols
        assert "is_active" in cols
        assert "description" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


class TestDiscountGroupModel:
    def test_discount_group_columns(self):
        cols = [c.name for c in DiscountGroup.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "discount_id" in cols
        assert "user_type" in cols
        assert "user_ids" in cols
        assert "station_ids" in cols
        assert "priority" in cols
        assert "is_active" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_discount_group_indexes(self):
        indexes = [idx.name for idx in DiscountGroup.__table__.indexes]
        assert "idx_dg_user_type" in indexes
        assert "idx_dg_active" in indexes
        assert "idx_dg_discount_id" in indexes


class TestDiscountModelCreation:
    def test_create_price_discount(self, db_session):
        discount = PriceDiscount(
            name="测试折扣",
            discount_type=DiscountType.PERCENTAGE,
            discount_rate=Decimal("0.90"),
            applicable_user_types="app,card",
            min_consumption=Decimal("10.00"),
            max_discount_amount=Decimal("50.00"),
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
            priority=10,
            is_active=True,
            description="新用户9折优惠",
        )
        db_session.add(discount)
        db_session.commit()
        db_session.refresh(discount)

        assert discount.id is not None
        assert discount.name == "测试折扣"
        assert discount.discount_type == DiscountType.PERCENTAGE
        assert float(discount.discount_rate) == 0.90
        assert discount.applicable_user_types == "app,card"
        assert float(discount.min_consumption) == 10.00
        assert float(discount.max_discount_amount) == 50.00
        assert discount.priority == 10
        assert discount.is_active is True
        assert discount.description == "新用户9折优惠"

    def test_create_discount_group(self, db_session):
        # 先创建折扣
        discount = PriceDiscount(
            name="基础折扣",
            discount_type=DiscountType.FIXED,
            discount_rate=Decimal("5.00"),
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 12, 31, 23, 59, 59),
        )
        db_session.add(discount)
        db_session.commit()
        db_session.refresh(discount)

        group = DiscountGroup(
            name="APP用户组",
            discount_id=discount.id,
            user_type="app",
            user_ids="1,2,3",
            station_ids="10,20",
            priority=5,
            is_active=True,
        )
        db_session.add(group)
        db_session.commit()
        db_session.refresh(group)

        assert group.id is not None
        assert group.name == "APP用户组"
        assert group.discount_id == discount.id
        assert group.user_type == "app"
        assert group.user_ids == "1,2,3"
        assert group.station_ids == "10,20"
        assert group.priority == 5
        assert group.is_active is True
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PointsRule / PointsRecord 模型测试
"""
import pytest
from datetime import datetime
from decimal import Decimal
from app.models.points import PointsRule, PointsRecord, PointsRuleType, PointsRecordType


class TestPointsRuleModel:
    def test_points_rule_type_enum_values(self):
        assert PointsRuleType.CHARGE.value == "charge"
        assert PointsRuleType.RECHARGE.value == "recharge"
        assert PointsRuleType.SIGN_IN.value == "sign_in"
        assert PointsRuleType.INVITE.value == "invite"
        assert PointsRuleType.BIRTHDAY.value == "birthday"
        assert PointsRuleType.ACTIVITY.value == "activity"
        assert PointsRuleType.SYSTEM.value == "system"

    def test_points_record_type_enum_values(self):
        assert PointsRecordType.EARN.value == "earn"
        assert PointsRecordType.REDEEM.value == "redeem"
        assert PointsRecordType.EXPIRE.value == "expire"
        assert PointsRecordType.ADJUST.value == "adjust"

    def test_points_rule_columns(self):
        cols = [c.name for c in PointsRule.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "rule_type" in cols
        assert "points" in cols
        assert "unit" in cols
        assert "daily_limit" in cols
        assert "weekly_limit" in cols
        assert "total_limit" in cols
        assert "applicable_user_types" in cols
        assert "min_amount" in cols
        assert "points_expire_days" in cols
        assert "is_active" in cols
        assert "start_time" in cols
        assert "end_time" in cols
        assert "description" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_points_record_columns(self):
        cols = [c.name for c in PointsRecord.__table__.columns]
        assert "id" in cols
        assert "user_id" in cols
        assert "user_type" in cols
        assert "rule_id" in cols
        assert "record_type" in cols
        assert "points" in cols
        assert "balance_before" in cols
        assert "balance_after" in cols
        assert "description" in cols
        assert "order_id" in cols
        assert "expires_at" in cols
        assert "created_at" in cols


class TestPointsRuleModelCreation:
    def test_create_charge_points_rule(self, db_session):
        rule = PointsRule(
            name="充电送积分",
            rule_type=PointsRuleType.CHARGE,
            points=10,
            unit="每充电1度电",
            daily_limit=100,
            weekly_limit=500,
            total_limit=None,
            applicable_user_types="app,card,vin",
            min_amount=Decimal("5.00"),
            points_expire_days=365,
            is_active=True,
            description="充电满5元送10积分，每度电10积分",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.name == "充电送积分"
        assert rule.rule_type == PointsRuleType.CHARGE
        assert rule.points == 10
        assert rule.unit == "每充电1度电"
        assert rule.daily_limit == 100
        assert rule.weekly_limit == 500
        assert rule.total_limit is None
        assert rule.applicable_user_types == "app,card,vin"
        assert float(rule.min_amount) == 5.00
        assert rule.points_expire_days == 365
        assert rule.is_active is True

    def test_create_sign_in_points_rule(self, db_session):
        rule = PointsRule(
            name="每日签到",
            rule_type=PointsRuleType.SIGN_IN,
            points=5,
            unit="每日签到",
            daily_limit=5,
            weekly_limit=None,
            total_limit=None,
            applicable_user_types=None,
            min_amount=None,
            points_expire_days=None,
            is_active=True,
            description="每日签到送5积分",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.rule_type == PointsRuleType.SIGN_IN
        assert rule.points == 5
        assert rule.daily_limit == 5

    def test_create_points_record(self, db_session):
        # 先创建规则
        rule = PointsRule(
            name="测试规则",
            rule_type=PointsRuleType.CHARGE,
            points=10,
            is_active=True,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        record = PointsRecord(
            user_id=1,
            user_type="app",
            rule_id=rule.id,
            record_type=PointsRecordType.EARN,
            points=10,
            balance_before=100,
            balance_after=110,
            description="充电订单积分",
            order_id=123,
            expires_at=datetime(2027, 1, 1, 0, 0, 0),
        )
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert record.id is not None
        assert record.user_id == 1
        assert record.user_type == "app"
        assert record.rule_id == rule.id
        assert record.record_type == PointsRecordType.EARN
        assert record.points == 10
        assert record.balance_before == 100
        assert record.balance_after == 110
        assert record.order_id == 123

    def test_create_points_record_redeem(self, db_session):
        record = PointsRecord(
            user_id=1,
            user_type="app",
            rule_id=None,
            record_type=PointsRecordType.REDEEM,
            points=-50,
            balance_before=200,
            balance_after=150,
            description="兑换充电抵扣券",
            order_id=None,
        )
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert record.id is not None
        assert record.record_type == PointsRecordType.REDEEM
        assert record.points == -50
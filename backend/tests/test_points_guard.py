"""
积分模块数值边界守卫测试 (卡b10e33d8)

覆盖:
- PointsRuleCreate/Update: min_amount / *_limit / points_expire_days ge 边界
- start_time/end_time 交叉校验 (end < start → 422; 相等 → 通过)
- PointsRecordCreate: EARN 必须 points>0; 扣减后余额>=0; ADJUST 双向放行
"""
import pytest
from pydantic import ValidationError

from app.api.v1.operate.points_api import (
    PointsRuleCreate,
    PointsRuleUpdate,
    PointsRecordCreate,
)
from app.models.points import PointsRecordType


# ==================== PointsRuleCreate 数值边界 ====================

class TestRuleCreateBounds:
    @pytest.mark.parametrize("field", ["min_amount", "daily_limit", "weekly_limit", "total_limit"])
    def test_negative_rejected(self, field):
        with pytest.raises(ValidationError):
            PointsRuleCreate(name="R", points=1, **{field: -1})

    @pytest.mark.parametrize("field", ["min_amount", "daily_limit", "weekly_limit", "total_limit"])
    def test_zero_allowed(self, field):
        obj = PointsRuleCreate(name="R", points=1, **{field: 0})
        assert getattr(obj, field) == 0

    def test_expire_days_zero_rejected(self):
        with pytest.raises(ValidationError):
            PointsRuleCreate(name="R", points=1, points_expire_days=0)

    def test_expire_days_one_allowed(self):
        assert PointsRuleCreate(name="R", points=1, points_expire_days=1).points_expire_days == 1

    def test_none_still_allowed(self):
        obj = PointsRuleCreate(name="R", points=1)
        assert obj.min_amount is None and obj.points_expire_days is None


class TestRuleCreateTimeWindow:
    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            PointsRuleCreate(name="R", points=1,
                             start_time="2026-01-02T00:00:00",
                             end_time="2026-01-01T00:00:00")

    def test_end_equal_start_allowed(self):
        obj = PointsRuleCreate(name="R", points=1,
                               start_time="2026-01-01T00:00:00",
                               end_time="2026-01-01T00:00:00")
        assert obj.end_time == obj.start_time

    def test_single_side_allowed(self):
        obj = PointsRuleCreate(name="R", points=1, start_time="2026-01-01T00:00:00")
        assert obj.end_time is None


# ==================== PointsRuleUpdate ====================

class TestRuleUpdateBounds:
    @pytest.mark.parametrize("field", ["min_amount", "daily_limit", "weekly_limit", "total_limit"])
    def test_negative_rejected(self, field):
        with pytest.raises(ValidationError):
            PointsRuleUpdate(**{field: -1})

    def test_expire_days_zero_rejected(self):
        with pytest.raises(ValidationError):
            PointsRuleUpdate(points_expire_days=0)

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            PointsRuleUpdate(start_time="2026-01-02T00:00:00", end_time="2026-01-01T00:00:00")

    def test_partial_update_single_side_allowed(self):
        obj = PointsRuleUpdate(end_time="2026-01-01T00:00:00")
        assert obj.start_time is None


# ==================== PointsRecordCreate 语义守卫 ====================

class TestRecordPointsSemantics:
    def test_earn_positive_allowed(self):
        obj = PointsRecordCreate(user_id=1, record_type=PointsRecordType.EARN,
                                 points=10, balance_before=0)
        assert obj.points == 10

    @pytest.mark.parametrize("bad", [0, -5])
    def test_earn_non_positive_rejected(self, bad):
        with pytest.raises(ValidationError):
            PointsRecordCreate(user_id=1, record_type=PointsRecordType.EARN,
                               points=bad, balance_before=0)

    def test_redeem_negative_allowed_within_balance(self):
        obj = PointsRecordCreate(user_id=1, record_type=PointsRecordType.REDEEM,
                                 points=-10, balance_before=10)
        assert obj.points == -10

    def test_redeem_overdraw_rejected(self):
        with pytest.raises(ValidationError):
            PointsRecordCreate(user_id=1, record_type=PointsRecordType.REDEEM,
                               points=-11, balance_before=10)

    def test_explicit_balance_after_overdraw_rejected(self):
        with pytest.raises(ValidationError):
            PointsRecordCreate(user_id=1, record_type=PointsRecordType.REDEEM,
                               points=-10, balance_before=5, balance_after=-5)

    def test_adjust_both_signs_allowed(self):
        PointsRecordCreate(user_id=1, record_type=PointsRecordType.ADJUST,
                           points=-3, balance_before=10)
        PointsRecordCreate(user_id=1, record_type=PointsRecordType.ADJUST,
                           points=3, balance_before=0)

    def test_adjust_to_negative_rejected(self):
        with pytest.raises(ValidationError):
            PointsRecordCreate(user_id=1, record_type=PointsRecordType.ADJUST,
                               points=-100, balance_before=10)


# ==================== 端到端 422 语义 ====================

class TestEndpoints422:
    def test_create_rule_bad_window_422(self, client):
        r = client.post("/api/v1/operate/points", json={
            "name": "R", "points": 1,
            "start_time": "2026-01-02T00:00:00", "end_time": "2026-01-01T00:00:00",
        })
        assert r.status_code == 422

    def test_create_rule_negative_min_amount_422(self, client):
        r = client.post("/api/v1/operate/points", json={"name": "R", "points": 1, "min_amount": -1})
        assert r.status_code == 422

    def test_create_record_earn_zero_422(self, client):
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 1, "record_type": "earn", "points": 0,
        })
        assert r.status_code == 422

    def test_create_record_overdraw_422(self, client):
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 1, "record_type": "redeem", "points": -100, "balance_before": 10,
        })
        assert r.status_code == 422

    def test_create_record_valid_redeem_ok(self, client):
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 1, "record_type": "redeem", "points": -10, "balance_before": 10,
        })
        assert r.status_code == 200

"""test_dispatch_engine.py — 智能派单引擎单元测试

覆盖: WEIGHTS 校验, dispatch 入口(空/成功), calculate_best_engineer (跳过inactive/评分/排序),
_score_distance (同位/远距离/空), _score_skill (匹配/不匹配/未知设备),
_score_load (0单/高负载), _score_performance (满分/空/快慢),
_score_parts (无需/全匹配/部分/无备件), 单例。
"""
import math
import pytest

from app.services.dispatch_engine import DispatchEngine, dispatch_engine


# ─── WEIGHTS ───

class TestWeights:
    def test_weights_sum_to_one(self):
        engine = DispatchEngine()
        total = sum(engine.WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_weight_keys(self):
        engine = DispatchEngine()
        assert set(engine.WEIGHTS.keys()) == {"distance", "skill", "load", "performance", "parts"}

    def test_distance_weight_highest(self):
        engine = DispatchEngine()
        assert engine.WEIGHTS["distance"] == 0.30
        assert engine.WEIGHTS["skill"] == 0.25


# ─── _score_distance ───

class TestScoreDistance:
    def setup_method(self):
        self.engine = DispatchEngine()

    def test_same_location(self):
        loc = {"lat": 30.0, "lon": 120.0}
        score = self.engine._score_distance(loc, loc)
        assert score == 100.0

    def test_far_distance(self):
        score = self.engine._score_distance(
            {"lat": 30.0, "lon": 120.0},
            {"lat": 31.0, "lon": 121.0},
        )
        # ~130km → score should be 0
        assert score == 0.0

    def test_empty_engineer_loc(self):
        score = self.engine._score_distance({}, {"lat": 30, "lon": 120})
        assert score == 50

    def test_empty_station_loc(self):
        score = self.engine._score_distance({"lat": 30, "lon": 120}, {})
        assert score == 50

    def test_both_empty(self):
        score = self.engine._score_distance({}, {})
        assert score == 50

    def test_moderate_distance(self):
        # ~5km → score = 100 - 5*2 = 90
        score = self.engine._score_distance(
            {"lat": 30.0, "lon": 120.0},
            {"lat": 30.045, "lon": 120.0},
        )
        assert 80 < score <= 100


# ─── _score_skill ───

class TestScoreSkill:
    def setup_method(self):
        self.engine = DispatchEngine()

    def test_exact_match_charger_dc(self):
        skills = ["充电桩", "直流充电", "高压电工"]
        score = self.engine._score_skill(skills, "charger_dc")
        assert score == 100.0

    def test_no_match(self):
        score = self.engine._score_skill(["厨师"], "charger_dc")
        assert score == 20.0  # 0 matched → 0*80 + 20

    def test_partial_match(self):
        skills = ["充电桩"]
        score = self.engine._score_skill(skills, "charger_dc")
        # 1/3 matched → 1/3 * 80 + 20 = 46.67
        assert 40 < score < 60

    def test_unknown_device_type(self):
        score = self.engine._score_skill(["something"], "unknown_device")
        assert score == 70

    def test_empty_skills(self):
        score = self.engine._score_skill([], "charger_dc")
        assert score == 50

    def test_empty_device_type(self):
        score = self.engine._score_skill(["充电桩"], None)
        assert score == 50


# ─── _score_load ───

class TestScoreLoad:
    def setup_method(self):
        self.engine = DispatchEngine()

    def test_zero_load(self):
        assert self.engine._score_load(0) == 100.0

    def test_high_load(self):
        assert self.engine._score_load(15) == 0.0

    def test_moderate_load(self):
        assert self.engine._score_load(5) == 50.0

    def test_exactly_10(self):
        assert self.engine._score_load(10) == 0.0


# ─── _score_performance ───

class TestScorePerformance:
    def setup_method(self):
        self.engine = DispatchEngine()

    def test_full_performance(self):
        perf = {"completion_rate": 100, "satisfaction": 5.0, "avg_hours": 1}
        score = self.engine._score_performance(perf)
        # 40 + 40 + 19 = 99 (hours: max(0, 20-1)=19)
        assert score == 99.0

    def test_empty_performance(self):
        score = self.engine._score_performance({})
        assert score == 60.0

    def test_slow_engineer(self):
        perf = {"completion_rate": 80, "satisfaction": 3.0, "avg_hours": 30}
        score = self.engine._score_performance(perf)
        # completion: 80*0.4=32, satisfaction: 3/5*40=24, hours: max(0,20-30)=0 → 56
        assert score == 56.0

    def test_capped_at_100(self):
        perf = {"completion_rate": 100, "satisfaction": 5.0, "avg_hours": 0}
        score = self.engine._score_performance(perf)
        # 40 + 40 + 20 = 100
        assert score == 100.0


# ─── _score_parts ───

class TestScoreParts:
    def setup_method(self):
        self.engine = DispatchEngine()

    def test_no_required_parts(self):
        assert self.engine._score_parts(["anything"], []) == 100.0

    def test_all_parts_matched(self):
        score = self.engine._score_parts(["fuse", "cable"], ["fuse", "cable"])
        assert score == 100.0

    def test_no_parts_carried(self):
        score = self.engine._score_parts([], ["fuse"])
        assert score == 30.0

    def test_partial_match(self):
        score = self.engine._score_parts(["fuse"], ["fuse", "cable", "plug"])
        # 1/3 matched → 30 + 1/3*70 = 53.33
        assert 50 < score < 60


# ─── calculate_best_engineer ───

class TestCalculateBestEngineer:
    def setup_method(self):
        self.engine = DispatchEngine()
        self.workorder = {"device_type": "charger_dc", "level": "P1", "required_parts": ["fuse"]}
        self.station = {"lat": 30.0, "lon": 120.0}

    def test_no_engineers(self):
        result = self.engine.calculate_best_engineer(self.workorder, [], self.station)
        assert result is None

    def test_skip_inactive(self):
        engs = [{"id": 1, "name": "A", "status": "offline"}]
        result = self.engine.calculate_best_engineer(self.workorder, engs, self.station)
        assert result is None

    def test_single_active_engineer(self):
        engs = [{
            "id": 1, "name": "A", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "skills": ["充电桩", "直流充电", "高压电工"],
            "current_load": 0,
            "performance": {"completion_rate": 100, "satisfaction": 5.0, "avg_hours": 1},
            "parts": ["fuse"],
        }]
        result = self.engine.calculate_best_engineer(self.workorder, engs, self.station)
        assert result is not None
        assert result["engineer"]["id"] == 1
        assert "score_details" in result
        assert "total_score" in result

    def test_best_engineer_selected(self):
        good = {
            "id": 1, "name": "Good", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "skills": ["充电桩", "直流充电", "高压电工"],
            "current_load": 0,
            "performance": {"completion_rate": 100, "satisfaction": 5.0, "avg_hours": 1},
            "parts": ["fuse"],
        }
        bad = {
            "id": 2, "name": "Bad", "status": "active",
            "location": {"lat": 31.0, "lon": 121.0},
            "skills": [],
            "current_load": 10,
            "performance": {},
            "parts": [],
        }
        result = self.engine.calculate_best_engineer(self.workorder, [bad, good], self.station)
        assert result["engineer"]["id"] == 1
        assert result["total_score"] > bad_score(bad, self.engine, self.workorder, self.station)


def bad_score(bad, engine, wo, station):
    """Helper to compute bad engineer's score"""
    details = {
        "distance": engine._score_distance(bad["location"], station),
        "skill": engine._score_skill(bad["skills"], wo["device_type"]),
        "load": engine._score_load(bad["current_load"]),
        "performance": engine._score_performance(bad["performance"]),
        "parts": engine._score_parts(bad["parts"], wo["required_parts"]),
    }
    return sum(details[k] * engine.WEIGHTS[k] for k in details)


# ─── dispatch ───

class TestDispatch:
    def setup_method(self):
        self.engine = DispatchEngine()
        self.workorder = {"device_type": "charger_dc", "level": "P1", "required_parts": []}
        self.station = {"lat": 30.0, "lon": 120.0}

    def test_no_available_engineers(self):
        result = self.engine.dispatch(self.workorder, [], self.station)
        assert result["success"] is False
        assert result["engineer"] is None

    def test_successful_dispatch(self):
        eng = {
            "id": 1, "name": "Best", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "skills": ["充电桩", "直流充电", "高压电工"],
            "current_load": 0,
            "performance": {"completion_rate": 100, "satisfaction": 5.0, "avg_hours": 1},
            "parts": [],
        }
        result = self.engine.dispatch(self.workorder, [eng], self.station)
        assert result["success"] is True
        assert result["engineer"]["id"] == 1
        assert "score" in result
        assert "score_details" in result


# ─── 脏数据守卫 (卡67caf9bf) ───

class TestDirtyDataGuards:
    """lat/lon 缺失 / None 字段 / haversine 浮点边界 / 负耗时溢出"""

    def setup_method(self):
        self.engine = DispatchEngine()

    # --- 缺陷1: lat/lon 缺失/None → 中性分 50 ---
    def test_lat_missing_returns_neutral(self):
        # lon 存在但 lat 缺失,不应把缺省当作 0(否则落点(0,0)几内亚湾)
        score = self.engine._score_distance({"lon": 120.0}, {"lat": 30.0, "lon": 120.0})
        assert score == 50

    def test_lon_missing_returns_neutral(self):
        score = self.engine._score_distance({"lat": 30.0}, {"lat": 30.0, "lon": 120.0})
        assert score == 50

    def test_lat_none_returns_neutral(self):
        score = self.engine._score_distance(
            {"lat": None, "lon": 120.0}, {"lat": 30.0, "lon": 120.0}
        )
        assert score == 50

    def test_station_lat_missing_returns_neutral(self):
        score = self.engine._score_distance({"lat": 30.0, "lon": 120.0}, {"lon": 120.0})
        assert score == 50

    def test_station_lat_none_returns_neutral(self):
        score = self.engine._score_distance(
            {"lat": 30.0, "lon": 120.0}, {"lat": None, "lon": 120.0}
        )
        assert score == 50

    # --- 缺陷3: haversine 浮点边界/同点不抛 ---
    def test_haversine_same_point_no_raise(self):
        # 同点: a 可能为极小负值导致 sqrt(1-a) 误判,必须 clamp
        loc = {"lat": 30.0, "lon": 120.0}
        score = self.engine._score_distance(loc, loc)
        assert math.isfinite(score)

    def test_haversine_extreme_coords_no_raise(self):
        # 对跖点附近,浮点误差可能令 a>1 → sqrt(1-a)<0 → ValueError,必须 clamp
        score = self.engine._score_distance(
            {"lat": 89.9999999, "lon": 0.0}, {"lat": -89.9999999, "lon": 180.0}
        )
        assert math.isfinite(score)

    # --- 缺陷2: _score_load None/str 不崩 ---
    def test_load_none_returns_neutral(self):
        # current_load=None 不应 TypeError;返回中性分 50
        score = self.engine._score_load(None)
        assert score == 50

    def test_load_str_returns_neutral(self):
        score = self.engine._score_load("5")
        assert score == 50

    def test_load_invalid_type_in_engineer_still_pooled(self):
        # 工程师 current_load=None(key 存在但值脏),必须在结果池中而非被吞
        engs = [{
            "id": 1, "name": "A", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "current_load": None,
        }]
        result = self.engine.calculate_best_engineer(
            {"device_type": "charger_dc"}, engs, {"lat": 30.0, "lon": 120.0}
        )
        assert result is not None
        assert result["engineer"]["id"] == 1

    def test_load_str_in_engineer_still_pooled(self):
        engs = [{
            "id": 2, "name": "B", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "current_load": "busy",
        }]
        result = self.engine.calculate_best_engineer(
            {"device_type": "charger_dc"}, engs, {"lat": 30.0, "lon": 120.0}
        )
        assert result is not None
        assert result["engineer"]["id"] == 2

    # --- 缺陷2: _score_performance None 字段不崩 ---
    def test_performance_completion_none_no_crash(self):
        score = self.engine._score_performance({"completion_rate": None})
        assert isinstance(score, (int, float))

    def test_performance_satisfaction_none_no_crash(self):
        score = self.engine._score_performance({"satisfaction": None})
        assert isinstance(score, (int, float))

    def test_performance_avg_hours_none_no_crash(self):
        score = self.engine._score_performance({"avg_hours": None})
        assert isinstance(score, (int, float))

    def test_performance_str_fields_no_crash(self):
        score = self.engine._score_performance({
            "completion_rate": "90", "satisfaction": "4", "avg_hours": "3",
        })
        assert isinstance(score, (int, float))

    def test_performance_none_fields_in_engineer_still_pooled(self):
        engs = [{
            "id": 3, "name": "C", "status": "active",
            "location": {"lat": 30.0, "lon": 120.0},
            "performance": {"completion_rate": None, "satisfaction": None, "avg_hours": None},
        }]
        result = self.engine.calculate_best_engineer(
            {"device_type": "charger_dc"}, engs, {"lat": 30.0, "lon": 120.0}
        )
        assert result is not None
        assert result["engineer"]["id"] == 3

    # --- 缺陷5: avg_hours 为负, score3 不超 20 上限 ---
    def test_performance_negative_avg_hours_capped(self):
        # avg_hours=-5 → 原逻辑 score3=max(0,20-(-5))=25 超 20 上限
        score = self.engine._score_performance({"avg_hours": -5})
        # score3 应被 clamp 到 20; 其余字段默认(completion=80→32, satisfaction=4→32) → 32+32+20=84
        assert score == 84.0

    def test_score3_clamp_upper_bound(self):
        # 直接验证耗时项 ≤20: avg_hours 越负 score3 越接近 20 但不超过
        for neg in (-5, -100, -1):
            score = self.engine._score_performance({"avg_hours": neg})
            # score3 = min(20, ...) → 总分含耗时项不超过 20
            # 其余(80→32, 4→32) 固定 64, 故总分 ≤ 64+20=84
            assert score <= 84.0 + 1e-9


# ─── calculate_best_engineer 边界消息 (卡67caf9bf) ───

class TestDispatchBoundaryMessages:
    def setup_method(self):
        self.engine = DispatchEngine()
        self.workorder = {"device_type": "charger_dc", "level": "P1", "required_parts": []}
        self.station = {"lat": 30.0, "lon": 120.0}

    def test_empty_engineers_dispatch(self):
        result = self.engine.dispatch(self.workorder, [], self.station)
        assert result["success"] is False
        assert result["message"] == "没有可用的工程师"

    def test_all_inactive_dispatch(self):
        engs = [
            {"id": 1, "name": "A", "status": "offline"},
            {"id": 2, "name": "B", "status": "busy"},
        ]
        result = self.engine.dispatch(self.workorder, engs, self.station)
        assert result["success"] is False
        assert result["message"] == "没有可用的工程师"


# ─── 单例 ───

class TestSingleton:
    def test_singleton_exists(self):
        assert dispatch_engine is not None
        assert isinstance(dispatch_engine, DispatchEngine)

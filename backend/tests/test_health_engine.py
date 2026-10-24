"""
健康度评估引擎单元测试 - app/services/health_engine.py

HealthEngine 是纯计算引擎(无 DB 依赖), 直接测 5 维度评分模型 /
温度阈值表 / 趋势分析 / 告警生成 / 剩余寿命预测的正常路径 + 边界 + 异常。
"""
import pytest

from app.services.health_engine import HealthEngine, health_engine


# ─── fixtures ───

@pytest.fixture
def engine():
    return HealthEngine()


def _perfect_data():
    """所有维度满分的设备数据。"""
    return {
        "insulation_resistance": 10,   # >=5 不扣分
        "leakage_current": 0,          # <=10 不扣分
        "ground_fault": False,
        "temperature": 40,             # < 任何 warn 阈值
        "temp_rise_rate": 0,
        "comm_success_rate": 100,
        "voltage": 220,                # 0 偏差
        "current_thd": 0,
        "plug_count": 0,
    }


# ======================================================================
# 权重 & 阈值常量
# ======================================================================

def test_weights_sum_to_one(engine):
    """5 维度权重之和必须为 1.0, 否则总分失真。"""
    assert sum(engine.WEIGHTS.values()) == pytest.approx(1.0)


def test_thresholds_ordering(engine):
    """健康阈值应 healthy > warning > critical。"""
    assert engine.THRESHOLDS["healthy"] > engine.THRESHOLDS["warning"]
    assert engine.THRESHOLDS["warning"] > engine.THRESHOLDS["critical"]


# ======================================================================
# 温度阈值表查找
# ======================================================================

def test_get_thermal_thresholds_known_type(engine):
    """已知设备类型返回专用阈值(battery 最严格: warn=45)。"""
    warn, crit, severe, rise = engine._get_thermal_thresholds("battery")
    assert (warn, crit, severe, rise) == (45, 55, 65, 3.0)


def test_get_thermal_thresholds_none_returns_default(engine):
    """device_type=None 回落默认阈值。"""
    assert engine._get_thermal_thresholds(None) == engine.DEFAULT_THERMAL_THRESHOLDS


def test_get_thermal_thresholds_unknown_returns_default(engine):
    """未知设备类型回落默认阈值。"""
    assert engine._get_thermal_thresholds("unicorn_device") == engine.DEFAULT_THERMAL_THRESHOLDS


def test_get_thermal_thresholds_case_insensitive(engine):
    """设备类型大小写不敏感。"""
    assert engine._get_thermal_thresholds("PV_INVERTER") == (60, 70, 80, 5.0)
    assert engine._get_thermal_thresholds("Battery") == (45, 55, 65, 3.0)


def test_get_thermal_thresholds_non_string(engine):
    """非字符串类型先 str() 再查表, 命不中走默认。"""
    assert engine._get_thermal_thresholds(12345) == engine.DEFAULT_THERMAL_THRESHOLDS


def test_get_gun_temp_threshold_charger(engine):
    """充电桩类设备返回枪头温度阈值 60。"""
    assert engine._get_gun_temp_threshold("charger_dc") == 60
    assert engine._get_gun_temp_threshold("charger_ac") == 60


def test_get_gun_temp_threshold_non_charger_is_none(engine):
    """非充电桩设备(含 None)返回 None, 不计枪头温度。"""
    assert engine._get_gun_temp_threshold("battery") is None
    assert engine._get_gun_temp_threshold("meter") is None
    assert engine._get_gun_temp_threshold(None) is None


# ======================================================================
# 电气安全评分
# ======================================================================

def test_score_electrical_perfect(engine):
    assert engine._score_electrical_safe(_perfect_data()) == 100


@pytest.mark.parametrize("insulation,expected", [
    (0.4, 50),   # <0.5 扣 50
    (0.5, 70),   # [0.5,1) 扣 30
    (1.0, 90),   # [1,5) 扣 10
    (5.0, 100),  # >=5 不扣
])
def test_score_electrical_insulation_tiers(engine, insulation, expected):
    s = engine._score_electrical_safe({**_perfect_data(), "insulation_resistance": insulation})
    assert s == expected


@pytest.mark.parametrize("leakage,expected", [
    (10, 100),   # <=10 不扣
    (11, 90),    # (10,20] 扣 10
    (21, 75),    # (20,30] 扣 25
    (31, 60),    # >30 扣 40
])
def test_score_electrical_leakage_tiers(engine, leakage, expected):
    s = engine._score_electrical_safe({**_perfect_data(), "leakage_current": leakage})
    assert s == expected


def test_score_electrical_ground_fault_deducts_50(engine):
    s = engine._score_electrical_safe({**_perfect_data(), "ground_fault": True})
    assert s == 50


def test_score_electrical_clamps_to_zero(engine):
    """多重严重问题叠加不得低于 0。"""
    bad = {"insulation_resistance": 0.1, "leakage_current": 50, "ground_fault": True}
    assert engine._score_electrical_safe(bad) == 0


# ======================================================================
# 热稳定性评分
# ======================================================================

def test_score_thermal_default_thresholds(engine):
    """默认设备类型温度阈值: 60/70/80。"""
    assert engine._score_thermal({"temperature": 50}, None) == 100
    assert engine._score_thermal({"temperature": 61}, None) == 85    # >warn 扣15
    assert engine._score_thermal({"temperature": 71}, None) == 70    # >crit 扣30
    assert engine._score_thermal({"temperature": 81}, None) == 50    # >severe 扣50


def test_score_thermal_battery_specific_threshold(engine):
    """battery 阈值更严(45/55/65): 同样 50°C 默认不扣, battery 扣 15。"""
    assert engine._score_thermal({"temperature": 50}, None) == 100
    assert engine._score_thermal({"temperature": 50}, "battery") == 85


def test_score_thermal_rise_rate(engine):
    """温升速率超阈值扣 20。"""
    s = engine._score_thermal({"temperature": 40, "temp_rise_rate": 6.0}, None)
    assert s == 80


def test_score_thermal_max_deduction_floor(engine):
    """severe 温度(-50) + 高温升(-20) = 最大扣 70, 最低 30(max(0,…)兜底防更低)。"""
    s = engine._score_thermal({"temperature": 200, "temp_rise_rate": 100}, "battery")
    assert s == 30


# ======================================================================
# 通信可靠性评分
# ======================================================================

def test_score_communication_returns_rate(engine):
    """通信维度直接返回成功率(满分/零分/中间值)。"""
    assert engine._score_communication({"comm_success_rate": 100}) == 100
    assert engine._score_communication({"comm_success_rate": 0}) == 0
    assert engine._score_communication({"comm_success_rate": 85}) == 85


def test_score_communication_default_100(engine):
    """缺省 comm_success_rate 视为 100。"""
    assert engine._score_communication({}) == 100


# ======================================================================
# 电能质量评分
# ======================================================================

def test_score_power_quality_perfect(engine):
    assert engine._score_power_quality(_perfect_data()) == 100


@pytest.mark.parametrize("voltage,expected", [
    (220, 100),   # 0 偏差
    (250, 80),    # 偏差 >10% 扣 20  (|250-220|/220≈13.6%)
    (260, 60),    # 偏差 >15% 扣 40  (≈18.2%)
    (190, 80),    # 低压 >10% 扣 20  (≈13.6%)
])
def test_score_power_quality_voltage_deviation(engine, voltage, expected):
    s = engine._score_power_quality({**_perfect_data(), "voltage": voltage})
    assert s == expected


@pytest.mark.parametrize("thd,expected", [
    (10, 100),   # <=10 不扣
    (11, 85),    # (10,20] 扣 15
    (21, 70),    # >20 扣 30
])
def test_score_power_quality_thd(engine, thd, expected):
    s = engine._score_power_quality({**_perfect_data(), "current_thd": thd})
    assert s == expected


# ======================================================================
# 机械寿命评分
# ======================================================================

def test_score_mechanical_wear_by_plug_count(engine):
    """插拔 5000 次(半寿命)扣 25 分。"""
    s = engine._score_mechanical({"plug_count": 5000}, None)
    assert s == 75


def test_score_mechanical_full_wear_clamps_zero(engine):
    """插拔超设计寿命不得低于 0。"""
    s = engine._score_mechanical({"plug_count": 999999}, None)
    assert s == 0


def test_score_mechanical_gun_temp_only_for_charger(engine):
    """枪头温度仅充电桩扣分: charger_dc 超 60 扣 20, battery 不扣。"""
    data = {"plug_count": 0, "gun_temperature": 70}
    assert engine._score_mechanical(data, "charger_dc") == 80
    assert engine._score_mechanical(data, "battery") == 100   # 非充电桩忽略枪头
    assert engine._score_mechanical(data, None) == 100


# ======================================================================
# 总分计算 + 趋势调整 + 区间裁剪
# ======================================================================

def test_calculate_health_score_perfect(engine):
    total, scores = engine.calculate_health_score(_perfect_data())
    assert total == 100
    assert set(scores.keys()) == set(engine.WEIGHTS.keys())


def test_calculate_health_score_clamps_high(engine):
    """通信成功率>100 时总分被裁剪到 100。"""
    data = {**_perfect_data(), "comm_success_rate": 200}
    total, _ = engine.calculate_health_score(data)
    assert total == 100


def test_calculate_health_score_low_but_non_negative(engine):
    """所有维度极差时总分受各维度 floor 约束, 仍 >= 0 且等于加权和。

    electrical/mechanical→0, thermal/power_quality→30, communication→0:
    total = 0*.30 + 30*.25 + 0*.20 + 30*.15 + 0*.10 = 12.0
    """
    bad = {
        "insulation_resistance": 0.1, "leakage_current": 50, "ground_fault": True,
        "temperature": 200, "temp_rise_rate": 100,
        "comm_success_rate": 0,
        "voltage": 999, "current_thd": 50,
        "plug_count": 999999,
    }
    total, scores = engine.calculate_health_score(bad, device_type="battery")
    assert total == 12.0
    assert total >= 0
    assert all(0 <= v <= 100 for v in scores.values())


def test_calculate_health_score_trend_adjustment_applied(engine):
    """历史持续恶化(trend<-5)对总分额外扣分。"""
    # 基础满分 100; 历史 total_score [100,100,85] → trend -10 → 总分 90
    hist = [{"total_score": v} for v in (100, 100, 85)]
    total, _ = engine.calculate_health_score(_perfect_data(), historical_data=hist)
    assert total == 90


def test_calculate_health_score_trend_not_applied_when_short(engine):
    """历史不足 3 条不触发趋势调整。"""
    hist = [{"total_score": v} for v in (100, 10)]
    total, _ = engine.calculate_health_score(_perfect_data(), historical_data=hist)
    assert total == 100


def test_calculate_health_score_trend_not_applied_when_mild(engine):
    """恶化幅度未达阈值(trend in (-5,0])不调整。"""
    # [100,100,93]: trend_per_day≈-2.33 → _analyze 返回 -4.67 → 不 < -5, 不调整
    hist = [{"total_score": v} for v in (100, 100, 93)]
    total, _ = engine.calculate_health_score(_perfect_data(), historical_data=hist)
    assert total == 100


# ======================================================================
# 趋势分析 helper
# ======================================================================

def test_analyze_trend_too_few_points(engine):
    assert engine._analyze_trend([{"total_score": 100}, {"total_score": 50}]) == 0


def test_analyze_trend_stable(engine):
    assert engine._analyze_trend([{"total_score": 100}] * 3) == 0


def test_analyze_trend_improving(engine):
    hist = [{"total_score": v} for v in (80, 90, 100)]
    assert engine._analyze_trend(hist) == 0


def test_analyze_trend_declining_doubles(engine):
    """持续恶化返回 trend_per_day*2(负值)。"""
    hist = [{"total_score": v} for v in (100, 100, 85)]
    # delta=-15, days=3, per_day=-5 → -5 < -2 → return -10
    assert engine._analyze_trend(hist) == -10


# ======================================================================
# 告警生成
# ======================================================================

def test_generate_alarm_healthy_returns_none(engine):
    """score>=80 不生成告警。"""
    dims = {k: 100 for k in engine.WEIGHTS}
    assert engine.generate_alarm(1, 80, dims) is None
    assert engine.generate_alarm(1, 95, dims) is None


def test_generate_alarm_warning_level(engine):
    """60<=score<80 为 warning 级别。"""
    dims = {"electrical": 70, "thermal": 90, "communication": 100, "power_quality": 100, "mechanical": 100}
    alarm = engine.generate_alarm(2, 70, dims)
    assert alarm is not None
    assert alarm["level"] == "warning"
    assert alarm["device_id"] == 2
    assert alarm["alarm_type"] == "电气安全异常"   # 最差维度 electrical


def test_generate_alarm_critical_level(engine):
    """score<60 为 critical 级别。"""
    dims = {"electrical": 100, "thermal": 100, "communication": 30, "power_quality": 100, "mechanical": 100}
    alarm = engine.generate_alarm(3, 50, dims)
    assert alarm["level"] == "critical"
    assert alarm["alarm_type"] == "通信故障"        # 最差维度 communication


def test_generate_alarm_content_format(engine):
    """告警内容含分数与最差维度得分。"""
    dims = {"electrical": 100, "thermal": 40, "communication": 100, "power_quality": 100, "mechanical": 100}
    alarm = engine.generate_alarm(4, 55, dims)
    assert "健康度55.0分" in alarm["content"]
    assert "温度异常" in alarm["content"]
    assert "得分40.0" in alarm["content"]


# ======================================================================
# 剩余寿命预测
# ======================================================================

def test_predict_remaining_life_empty(engine):
    assert engine.predict_remaining_life(_perfect_data(), []) == 365


def test_predict_remaining_life_too_few(engine):
    """历史不足 7 条返回默认 365。"""
    hist = [{"total_score": v} for v in range(5)]
    assert engine.predict_remaining_life(_perfect_data(), hist) == 365


def test_predict_remaining_life_stable(engine):
    """健康稳定/改善返回 365。"""
    hist = [{"total_score": v} for v in (80, 85, 90, 95, 100, 100, 100)]
    assert engine.predict_remaining_life(_perfect_data(), hist) == 365


def test_predict_remaining_life_declining(engine):
    """按衰退速率推算剩余天数。"""
    hist = [{"total_score": v} for v in (100, 100, 100, 100, 100, 100, 50)]
    # delta=-50, days=7, decline=50/7≈7.14, current=50 → int(50/7.14)=7
    assert engine.predict_remaining_life(_perfect_data(), hist) == 7


def test_predict_remaining_life_slow_decline_capped(engine):
    """慢衰退推算超 1 年, 上限 365。"""
    hist = [{"total_score": v} for v in (100, 100, 100, 100, 100, 100, 99)]
    assert engine.predict_remaining_life(_perfect_data(), hist) == 365


# ======================================================================
# 单例
# ======================================================================

def test_singleton_instance():
    """模块级 health_engine 是 HealthEngine 实例。"""
    assert isinstance(health_engine, HealthEngine)


# ======================================================================
# 异常 / 边界 兜底分支 (卡 a4f06843 安全加固)
# ======================================================================

class _BoomGetDict(dict):
    """get() 必抛, 用于触发各评分方法的 except 分支。"""
    def get(self, *args, **kwargs):
        raise RuntimeError("get boom")


@pytest.mark.parametrize("method,needs_device_type", [
    ("_score_electrical_safe", False),
    ("_score_thermal", True),
    ("_score_communication", False),
    ("_score_power_quality", False),
    ("_score_mechanical", True),
])
def test_score_method_exception_returns_safe_default(engine, method, needs_device_type):
    """5 个评分方法: data.get 抛 → except → 返回安全默认分 80。"""
    fn = getattr(engine, method)
    result = fn(_BoomGetDict(), None) if needs_device_type else fn(_BoomGetDict())
    assert result == 80.0


def test_calculate_health_score_non_dict_returns_safe_default(engine):
    """device_data 非字典 → 守卫返回 (安全默认分, 各维度默认分)。"""
    total, scores = engine.calculate_health_score("not-a-dict")
    assert total == 80.0
    assert set(scores.keys()) == set(engine.WEIGHTS.keys())
    assert all(v == 80.0 for v in scores.values())


def test_calculate_health_score_total_typeerror_falls_back(engine, monkeypatch):
    """某维度返回非数值 → 加权求和 TypeError → 兜底安全默认分。"""
    monkeypatch.setattr(engine, "_score_electrical_safe", lambda data: "not-a-number")
    total, _ = engine.calculate_health_score(_perfect_data())
    assert total == 80.0


def test_safe_float_invalid_returns_default(engine):
    """_safe_float: 非法字符串 → ValueError → 返回 default。"""
    assert engine._safe_float("abc") == 0.0
    assert engine._safe_float("abc", default=7.0) == 7.0


def test_analyze_trend_exception_returns_zero(engine):
    """_analyze_trend: historical 元素 get 抛 → except → 返回 0 (不扣分)。"""
    hist = [_BoomGetDict(), _BoomGetDict(), _BoomGetDict()]
    assert engine._analyze_trend(hist) == 0


def test_generate_alarm_empty_dimensions(engine):
    """generate_alarm: 空 dimensions + score<80 → 走空维度分支。"""
    alarm = engine.generate_alarm(1, 50, {})
    assert alarm is not None
    assert alarm["level"] == "critical"  # 50 < 60
    assert alarm["alarm_type"] == "健康度异常"
    assert "健康度50.0分" in alarm["content"]


def test_generate_alarm_exception_returns_none(engine):
    """generate_alarm: dimensions.get 抛 (min key) → except → 返回 None。"""
    dims = _BoomGetDict()
    dims["electrical"] = 70  # 非空, 绕过空维度守卫
    assert engine.generate_alarm(1, 50, dims) is None


def test_predict_remaining_life_exception_returns_365(engine):
    """predict_remaining_life: historical 元素 get 抛 → except → 返回 365。"""
    hist = [_BoomGetDict() for _ in range(7)]  # >=7 通过首道守卫
    assert engine.predict_remaining_life(_perfect_data(), hist) == 365

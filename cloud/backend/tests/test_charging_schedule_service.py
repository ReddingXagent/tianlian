"""
智能充电调度服务单元测试 - app/services/charging_schedule_service.py

用 MagicMock db 隔离持久化(plan.id/entry.id 留空不影响算法), 聚焦测调度算法:
时段归类 / SOC 优先级 / 变压器容量约束 / V2G 反向放电 / 动态调整错误路径。
(端到端持久化已由 tests/test_charging_schedule.py 集成测试覆盖。)
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.charging_schedule import (
    ChargingEntryMode,
    ChargingPeriodType,
    ChargingSchedulePlanStatus,
)
from app.services.charging_schedule_service import (
    classify_period,
    window_period,
    generate_schedule,
    adjust_schedule,
)


_VALLEY_START = datetime(2026, 7, 22, 2, 0)
_VALLEY_END = datetime(2026, 7, 22, 6, 0)
_PEAK_START = datetime(2026, 7, 22, 12, 0)
_PEAK_END = datetime(2026, 7, 22, 15, 0)
_FLAT_START = datetime(2026, 7, 22, 16, 0)
_FLAT_END = datetime(2026, 7, 22, 18, 0)


def _mock_db():
    """MagicMock db: add/flush/add_all/commit/refresh 均为 no-op, plan.id 留空。"""
    return MagicMock()


def _by_vid(result):
    return {e["vehicle_id"]: e for e in result["entries"]}


# ======================================================================
# 时段归类工具
# ======================================================================

@pytest.mark.parametrize("hour,expected", [
    (0, ChargingPeriodType.VALLEY), (6, ChargingPeriodType.VALLEY), (23, ChargingPeriodType.VALLEY),
    (10, ChargingPeriodType.PEAK), (12, ChargingPeriodType.PEAK), (14, ChargingPeriodType.PEAK),
    (18, ChargingPeriodType.PEAK), (20, ChargingPeriodType.PEAK),
    (7, ChargingPeriodType.FLAT), (9, ChargingPeriodType.FLAT), (15, ChargingPeriodType.FLAT),
    (17, ChargingPeriodType.FLAT), (21, ChargingPeriodType.FLAT), (22, ChargingPeriodType.FLAT),
])
def test_classify_period_all_hours(hour, expected):
    """24 小时逐段归类: 谷{23,0..6}/峰{10..14,18..20}/平其余。"""
    assert classify_period(hour) == expected


def test_classify_period_boundaries():
    """边界: 6 点仍谷, 7 点起平; 21 点起平, 22 平, 23 谷。"""
    assert classify_period(6) == ChargingPeriodType.VALLEY
    assert classify_period(7) == ChargingPeriodType.FLAT
    assert classify_period(20) == ChargingPeriodType.PEAK
    assert classify_period(21) == ChargingPeriodType.FLAT


def test_window_period_uses_start_hour():
    """window_period 按窗口起始小时归类。"""
    assert window_period(_VALLEY_START) == ChargingPeriodType.VALLEY
    assert window_period(_PEAK_START) == ChargingPeriodType.PEAK
    assert window_period(_FLAT_START) == ChargingPeriodType.FLAT


# ======================================================================
# generate_schedule 错误路径
# ======================================================================

def test_generate_negative_power_error():
    db = _mock_db()
    result = generate_schedule(db, 1, [{"vehicle_id": 1, "current_soc": 0.2}], -1.0, _VALLEY_START, _VALLEY_END)
    assert result == {"error": "可用功率不能为负"}
    db.add.assert_not_called()


def test_generate_empty_vehicle_states_error():
    db = _mock_db()
    result = generate_schedule(db, 1, [], 10.0, _VALLEY_START, _VALLEY_END)
    assert result == {"error": "车辆状态列表为空"}
    db.add.assert_not_called()


def test_generate_missing_vehicle_id_error():
    db = _mock_db()
    result = generate_schedule(db, 1, [{"current_soc": 0.2}], 10.0, _VALLEY_START, _VALLEY_END)
    assert result == {"error": "vehicle_states 缺少 vehicle_id"}


def test_generate_vehicle_id_null_error():
    """vehicle_id 显式为 None 也应报错。"""
    db = _mock_db()
    result = generate_schedule(db, 1, [{"vehicle_id": None, "current_soc": 0.2}], 10.0, _VALLEY_START, _VALLEY_END)
    assert result["error"] == "vehicle_states 缺少 vehicle_id"


# ======================================================================
# SOC 优先级排序
# ======================================================================

def test_generate_priority_sorted_by_soc():
    """低 SOC 优先级更高(priority 更小)。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.8, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": 2, "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": 3, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    result = generate_schedule(db, 1, states, 30.0, _VALLEY_START, _VALLEY_END)
    by_priority = sorted(result["entries"], key=lambda e: e["priority"])
    assert [e["vehicle_id"] for e in by_priority] == [3, 2, 1]
    assert by_priority[0]["priority"] == 1
    assert by_priority[0]["soc_start"] == 0.2


def test_generate_all_charge_when_power_sufficient():
    """功率充足时全部车辆进入充电。"""
    db = _mock_db()
    states = [
        {"vehicle_id": i, "current_soc": 0.1 * i, "target_soc": 0.9, "max_power_kw": 7.0}
        for i in range(1, 4)
    ]
    result = generate_schedule(db, 1, states, 30.0, _VALLEY_START, _VALLEY_END)
    assert result["summary"]["charging_vehicles"] == 3
    assert result["summary"]["idle_vehicles"] == 0
    assert all(e["charge_mode"] == "charge" for e in result["entries"])


# ======================================================================
# 变压器容量约束
# ======================================================================

def test_generate_power_constraint_greedy():
    """功率不足按优先级贪心, 不超总量, 单车不超 max_power_per_vehicle。"""
    db = _mock_db()
    states = [
        {"vehicle_id": i, "current_soc": 0.1 + 0.1 * i, "target_soc": 0.9, "max_power_kw": 10.0}
        for i in range(3)   # soc 0.1(p1)/0.2(p2)/0.3(p3)
    ]
    result = generate_schedule(db, 1, states, 15.0, _VALLEY_START, _VALLEY_END,
                               rule_spec={"max_power_per_vehicle": 7.0})
    # p1:7(rem8) p2:7(rem1) p3:1(rem0) => 合计 15
    assert result["summary"]["allocated_power_kw"] == 15.0
    assert result["summary"]["remaining_power_kw"] == 0.0
    by_vid = _by_vid(result)
    assert all(e["assigned_power_kw"] <= 7.0 for e in by_vid.values())
    assert by_vid[2]["assigned_power_kw"] == 1.0   # 最低优先级拿残余


def test_generate_idle_when_power_exhausted():
    """功率耗尽后, 低优先级车辆进入待机(0 功率)。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.1, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": 2, "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    result = generate_schedule(db, 1, states, 5.0, _VALLEY_START, _VALLEY_END)
    by_vid = _by_vid(result)
    assert by_vid[1]["charge_mode"] == "charge"
    assert by_vid[1]["assigned_power_kw"] == 5.0
    assert by_vid[2]["charge_mode"] == "idle"
    assert by_vid[2]["assigned_power_kw"] == 0.0
    assert result["summary"]["idle_vehicles"] == 1


def test_generate_default_max_power_when_missing():
    """vehicle_state 缺 max_power_kw 时用默认 max_power_per_vehicle(7.0)。"""
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9}]   # 无 max_power_kw
    result = generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END)
    assert _by_vid(result)[1]["assigned_power_kw"] == 7.0


def test_generate_default_target_soc_when_missing():
    """vehicle_state 缺 target_soc 时用默认 0.90。"""
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.2, "max_power_kw": 7.0}]   # 无 target_soc
    result = generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END)
    assert _by_vid(result)[1]["soc_target"] == 0.9


# ======================================================================
# 峰谷时段偏好
# ======================================================================

def test_generate_valley_period_marking():
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.3, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END)
    assert result["period_type"] == "valley"
    assert result["valley_preferred"] is True
    assert result["entries"][0]["period_type"] == "valley"


def test_generate_peak_period_marking():
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.3, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _PEAK_START, _PEAK_END)
    assert result["period_type"] == "peak"
    assert result["valley_preferred"] is False
    assert result["entries"][0]["period_type"] == "peak"


def test_generate_flat_period_marking():
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.3, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _FLAT_START, _FLAT_END)
    assert result["period_type"] == "flat"
    assert result["valley_preferred"] is False


# ======================================================================
# V2G 反向放电
# ======================================================================

def test_generate_v2g_discharge_in_peak():
    """峰时段: 高 SOC 且达标车辆进入 V2G 放电, 低 SOC 正常充电。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.95, "target_soc": 0.9, "max_power_kw": 7.0},  # 可放电
        {"vehicle_id": 2, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},   # 需充电
    ]
    result = generate_schedule(db, 1, states, 10.0, _PEAK_START, _PEAK_END,
                               rule_spec={"v2g_enabled": True, "v2g_discharge_kw": 5.0})
    by_vid = _by_vid(result)
    assert by_vid[1]["charge_mode"] == "discharge"
    assert by_vid[1]["assigned_power_kw"] == 5.0
    assert by_vid[2]["charge_mode"] == "charge"
    assert result["summary"]["v2g_discharge_vehicles"] == 1


def test_generate_v2g_idle_off_peak():
    """非峰时段(谷): 即便启用 V2G, 高 SOC 车也只待机不放电。"""
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.95, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END,
                               rule_spec={"v2g_enabled": True})
    by_vid = _by_vid(result)
    assert by_vid[1]["charge_mode"] == "idle"
    assert by_vid[1]["assigned_power_kw"] == 0.0
    assert result["summary"]["v2g_discharge_vehicles"] == 0


def test_generate_v2g_disabled_high_soc_not_participating():
    """V2G 未启用: 高 SOC 且已达标车辆不参与(不产生条目)。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.95, "target_soc": 0.9, "max_power_kw": 7.0},  # 达标, v2g 关
        {"vehicle_id": 2, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},   # 需充电
    ]
    result = generate_schedule(db, 1, states, 10.0, _PEAK_START, _PEAK_END)   # v2g 默认关
    vids = {e["vehicle_id"] for e in result["entries"]}
    assert 2 in vids          # 充电车有条目
    assert 1 not in vids      # 高 SOC 车无条目


def test_generate_v2g_threshold_boundary():
    """cur == v2g_discharge_threshold(默认 0.80) 且 tgt<=cur -> 可放电(>= 含等号)。"""
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.80, "target_soc": 0.80, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _PEAK_START, _PEAK_END,
                               rule_spec={"v2g_enabled": True})
    by_vid = _by_vid(result)
    assert by_vid[1]["charge_mode"] == "discharge"


def test_generate_v2g_custom_threshold():
    """自定义 v2g_discharge_threshold 生效。"""
    db = _mock_db()
    # soc=0.6 < 自定义阈值 0.7 -> 不达 V2G, 且 0.6<0.9(target) -> 走充电
    states = [{"vehicle_id": 1, "current_soc": 0.6, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(db, 1, states, 10.0, _PEAK_START, _PEAK_END,
                               rule_spec={"v2g_enabled": True, "v2g_discharge_threshold": 0.7})
    assert _by_vid(result)[1]["charge_mode"] == "charge"


# ======================================================================
# 持久化调用 & summary
# ======================================================================

def test_generate_invokes_persistence():
    """生成计划调用 add(plan)/flush/add_all/commit/refresh。"""
    db = _mock_db()
    states = [{"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0}]
    generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END)
    db.add.assert_called_once()       # add(plan)
    db.flush.assert_called_once()
    db.add_all.assert_called_once()
    db.commit.assert_called_once()
    assert db.refresh.call_count >= 2   # entries + plan


def test_generate_summary_fields():
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": 2, "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    result = generate_schedule(db, 1, states, 10.0, _VALLEY_START, _VALLEY_END)
    summary = result["summary"]
    assert summary["available_power_kw"] == 10.0
    assert summary["allocated_power_kw"] == 10.0   # 7+3
    assert summary["remaining_power_kw"] == 0.0
    assert summary["charging_vehicles"] == 2
    assert result["enterprise_id"] == 1


# ======================================================================
# adjust_schedule
# ======================================================================

def _adjust_db(entries, plan_status=ChargingSchedulePlanStatus.PLANNED, total_power=1000.0):
    """构造 adjust 用的 mock db: get 返回 plan(含 total_available_power_kw), query 链返回 entries。

    total_available_power_kw 默认给大值(1000), 不干扰现有调整成功用例的总功率校验;
    需测超限场景时显式传小值。
    """
    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        status=plan_status, total_available_power_kw=total_power,
    )
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = entries
    return db


def _entry(eid, vid, power, priority=1, mode=ChargingEntryMode.CHARGE):
    return SimpleNamespace(id=eid, vehicle_id=vid, assigned_power_kw=power,
                           priority=priority, charge_mode=mode)


def test_adjust_plan_not_found():
    db = MagicMock()
    db.get.return_value = None
    result = adjust_schedule(db, 9999, [{"entry_id": 1, "new_power_kw": 5.0}])
    assert "error" in result


def test_adjust_plan_status_not_adjustable():
    """已完成/已取消的计划不可调整。"""
    db = _adjust_db([], plan_status=ChargingSchedulePlanStatus.COMPLETED)
    result = adjust_schedule(db, 1, [{"entry_id": 1, "new_power_kw": 5.0}])
    assert "不可调整" in result["error"]


def test_adjust_entry_not_in_plan():
    """条目不属于该计划 -> error。"""
    db = _adjust_db([_entry(1, 10, 7.0)])
    result = adjust_schedule(db, 1, [{"entry_id": 999, "new_power_kw": 5.0}])
    assert "不属于计划" in result["error"]


def test_adjust_negative_power_error():
    db = _adjust_db([_entry(1, 10, 7.0)])
    result = adjust_schedule(db, 1, [{"entry_id": 1, "new_power_kw": -5.0}])
    assert result["error"] == "功率不能为负"


def test_adjust_success_updates_power():
    db = _adjust_db([_entry(1, 10, 7.0, priority=1), _entry(2, 11, 7.0, priority=2)])
    result = adjust_schedule(db, 1, [
        {"entry_id": 1, "new_power_kw": 3.0},
        {"entry_id": 2, "new_power_kw": 11.0},
    ])
    assert "error" not in result
    assert result["status"] == "planned"
    db.commit.assert_called_once()
    by_vid = {e["vehicle_id"]: e for e in result["entries"]}
    assert by_vid[10]["assigned_power_kw"] == 3.0
    assert by_vid[11]["assigned_power_kw"] == 11.0


def test_adjust_active_status_allowed():
    """ACTIVE 状态计划也可调整(PLANNED/ACTIVE 均可)。"""
    db = _adjust_db([_entry(1, 10, 7.0)], plan_status=ChargingSchedulePlanStatus.ACTIVE)
    result = adjust_schedule(db, 1, [{"entry_id": 1, "new_power_kw": 4.0}])
    assert "error" not in result
    assert result["status"] == "active"


# ======================================================================
# BUG 1 (卡2814e91a): adjust 校验失败必须 db.rollback, 防 dirty write
# 现有路径先改 ORM 对象后校验, 校验失败直接 return 会留脏对象,
# 后续任意 commit 会把超容量/非法分配持久化 -> 数据完整性破坏。
# mock 环境 rollback 不还原 detached 对象属性, 故以 rollback 被调用 +
# commit 未被调用作为"脏写被回滚、未持久化"的契约证据。
# ======================================================================

def test_adjust_over_power_no_dirty_write():
    """总功率超限必须 rollback, 否则超容量分配被后续 commit 持久化。"""
    db = _adjust_db([_entry(1, 10, 7.0), _entry(2, 11, 7.0)], total_power=10.0)
    result = adjust_schedule(db, 1, [
        {"entry_id": 1, "new_power_kw": 5.0},
        {"entry_id": 2, "new_power_kw": 6.0},   # 合计 11 > 10 超限
    ])
    assert "超过可用容量" in result["error"]
    db.rollback.assert_called_once()    # 脏改回滚
    db.commit.assert_not_called()       # 未持久化


def test_adjust_entry_not_found_no_dirty_write():
    """循环中第 N 条 entry 不存在, 前 N-1 条脏改必须 rollback 不持久化。"""
    db = _adjust_db([_entry(1, 10, 7.0)])   # 仅 entry 1 存在
    result = adjust_schedule(db, 1, [
        {"entry_id": 1, "new_power_kw": 5.0},     # 合法, entry1 已被改
        {"entry_id": 999, "new_power_kw": 3.0},   # 不存在 -> 中断
    ])
    assert "不属于计划" in result["error"]
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_adjust_negative_power_no_dirty_write():
    """循环中第 N 条功率为负, 前 N-1 条脏改必须 rollback 不持久化。"""
    db = _adjust_db([_entry(1, 10, 7.0), _entry(2, 11, 7.0)])
    result = adjust_schedule(db, 1, [
        {"entry_id": 1, "new_power_kw": 5.0},    # 合法, entry1 已被改
        {"entry_id": 2, "new_power_kw": -3.0},   # 负 -> 中断
    ])
    assert result["error"] == "功率不能为负"
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


# ======================================================================
# BUG 2/3 (卡2814e91a): generate 重复 vehicle_id 去重 + 非正功率跳过
# 单条脏数据不应阻断整个企业调度, 与"SOC 已达标则静默不参与"同哲学:
# 跳过该条 + log warning, 保留可观测性。
# ======================================================================

def test_generate_schedule_duplicate_vehicle_dedup():
    """同一 vehicle_id 出现多次只产生一条 entry(首条为准, 后续跳过)。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": 1, "current_soc": 0.3, "target_soc": 0.9, "max_power_kw": 7.0},  # 重复
        {"vehicle_id": 2, "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    result = generate_schedule(db, 1, states, 30.0, _VALLEY_START, _VALLEY_END)
    assert "error" not in result
    vids = [e["vehicle_id"] for e in result["entries"]]
    assert vids.count(1) == 1   # 去重, 只一条
    assert vids.count(2) == 1


def test_generate_schedule_negative_max_power():
    """max_power_kw <= 0 的车辆跳过(不产生 entry), 不阻断整体调度。"""
    db = _mock_db()
    states = [
        {"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": -5.0},  # 负, 跳过
        {"vehicle_id": 2, "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 0.0},   # 零, 跳过
        {"vehicle_id": 3, "current_soc": 0.4, "target_soc": 0.9, "max_power_kw": 7.0},   # 正常
    ]
    result = generate_schedule(db, 1, states, 30.0, _VALLEY_START, _VALLEY_END)
    assert "error" not in result
    vids = [e["vehicle_id"] for e in result["entries"]]
    assert 1 not in vids
    assert 2 not in vids
    assert 3 in vids


# ======================================================================
# 卡 bd1d57a4: new_power_kw 非有限值(NaN/±Inf, 数字或字符串)穿透
# float('nan')/float('inf') 不抛异常, nan<0=False 绕过负值检查,
# round(nan,2)=nan 直接写库; sum 混入 nan 后 nan>x=False 容量校验被
# 静默绕过。统一用 math.isfinite 拦截 NaN/±Inf 三态。
# ======================================================================

@pytest.mark.parametrize("bad_power", [
    float("nan"), float("inf"), float("-inf"),
    "nan", "NaN", "infinity", "Infinity", "-Infinity",
])
def test_adjust_non_finite_power_rejected(bad_power):
    """非有限功率 -> error, rollback, 不 commit, 不落库。"""
    entry = _entry(1, 10, 7.0)
    db = _adjust_db([entry])
    result = adjust_schedule(db, 1, [{"entry_id": 1, "new_power_kw": bad_power}])
    assert "error" in result
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    # mock 环境下 rollback 不还原属性, 但穿透时会被改成 nan/inf —
    # 修复后应在赋值前拦截, 属性保持原值。
    assert entry.assigned_power_kw == 7.0


def test_adjust_non_finite_power_no_bypass_capacity_check():
    """混合载荷: 第 1 条 NaN 不应静默绕过第 2 条的容量校验语义。"""
    db = _adjust_db([_entry(1, 10, 7.0), _entry(2, 11, 7.0)], total_power=10.0)
    result = adjust_schedule(db, 1, [
        {"entry_id": 1, "new_power_kw": float("nan")},
        {"entry_id": 2, "new_power_kw": 6.0},
    ])
    assert "error" in result
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_adjust_valid_string_number_still_works():
    """合法数字字符串不受影响, 正常调整成功(回归保护)。"""
    db = _adjust_db([_entry(1, 10, 7.0)])
    result = adjust_schedule(db, 1, [{"entry_id": 1, "new_power_kw": "4.5"}])
    assert "error" not in result
    assert result["entries"][0]["assigned_power_kw"] == 4.5

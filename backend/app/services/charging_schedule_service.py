"""
智能充电调度服务 - Phase45

调度策略(有序充电 + 负荷均衡):
1. SOC 优先级排序  — 低 SOC 车辆优先获得充电功率
2. 变压器容量约束  — 分配总功率不超过变压器可用容量, 单车不超过 max_power_per_vehicle
3. 峰谷时段偏好    — 充电窗口尽量落在谷时段(电价低), V2G 放电窗口落在峰时段(电价高)
4. V2G 反向放电    — 高 SOC 车辆在峰时段反向放电, 起到削峰作用

服务层只返回纯数据 dict(成功) 或 {"error": ...}(失败), 由 API 层做统一响应包装。
"""
import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.charging_schedule import (
    ChargingSchedulePlan,
    ChargingScheduleEntry,
    ChargingSchedulePlanStatus,
    ChargingEntryMode,
    ChargingPeriodType,
)

logger = logging.getLogger(__name__)


# ─── 电价时段定义(典型工商业峰谷, 可经 rule_spec 覆盖) ───
# 谷时 23:00-07:00 — 充电黄金时段
# 峰时 10:00-15:00, 18:00-21:00 — V2G 放电黄金时段
# 平时 其余
_VALLEY_HOURS = set(list(range(23, 24)) + list(range(0, 7)))   # {23, 0..6}
_PEAK_HOURS = set(list(range(10, 15)) + list(range(18, 21)))    # {10..14, 18..20}

# 默认规则参数
_DEFAULT_MAX_POWER_PER_VEHICLE = 7.0     # 单车最大功率(kW, 交流慢充典型值)
_DEFAULT_V2G_DISCHARGE_THRESHOLD = 0.80  # SOC >= 80% 可参与 V2G 放电
_DEFAULT_V2G_DISCHARGE_KW = 5.0          # V2G 单车放电功率(kW)
_DEFAULT_TARGET_SOC = 0.90


def classify_period(hour: int) -> ChargingPeriodType:
    """按小时归类电价时段(峰/平/谷)。

    输入边界校验: hour 必须是 [0, 23] 内的整数。
    None/越界/非数字统一抛 ValueError(便于调用方捕获, 不暴露 AttributeError 细节),
    而非静默归类为 FLAT —— 越界小时通常是上游数据错误, 静默处理会掩盖 bug。
    """
    # bool 是 int 子类(True/False 会通过 isinstance(int) 检查), 显式排除避免 True 被当成 1
    if isinstance(hour, bool) or not isinstance(hour, int):
        raise ValueError(f"hour 必须为整数, 得到 {type(hour).__name__}: {hour!r}")
    if hour < 0 or hour > 23:
        raise ValueError(f"hour 必须在 0-23 范围, 得到 {hour}")
    if hour in _VALLEY_HOURS:
        return ChargingPeriodType.VALLEY
    if hour in _PEAK_HOURS:
        return ChargingPeriodType.PEAK
    return ChargingPeriodType.FLAT


def window_period(time_window_start: datetime) -> ChargingPeriodType:
    """按调度窗口起始小时归类时段。

    None/非 datetime 输入抛 ValueError(非 AttributeError), 由调用方决策。
    """
    if not isinstance(time_window_start, datetime):
        raise ValueError(
            f"time_window_start 必须为 datetime, 得到 {type(time_window_start).__name__}"
        )
    return classify_period(time_window_start.hour)


def generate_schedule(
    db: Session,
    enterprise_id: int,
    vehicle_states: List[Dict[str, Any]],
    available_power_kw: float,
    time_window_start: datetime,
    time_window_end: datetime,
    rule_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成智能充电调度计划。

    Args:
        db: 数据库会话(依赖注入)
        enterprise_id: 企业 ID
        vehicle_states: 车辆实时状态列表, 每项含
            {vehicle_id, current_soc(0-1), target_soc(0-1), max_power_kw}
        available_power_kw: 变压器当前可用总功率(kW)
        time_window_start/end: 调度时段
        rule_spec: 规则参数(均可选):
            max_power_per_vehicle, v2g_enabled,
            v2g_discharge_threshold, v2g_discharge_kw, target_soc

    Returns:
        成功: {plan_id, period_type, valley_preferred, summary, entries}
        失败: {"error": "..."}
    """
    if available_power_kw < 0:
        return {"error": "可用功率不能为负"}
    if time_window_end <= time_window_start:
        return {"error": "结束时间必须晚于开始时间"}
    if not vehicle_states:
        return {"error": "车辆状态列表为空"}

    rule_spec = rule_spec or {}
    # 计算阶段(rule_spec 解析 / 时段归类 / 车辆分类 / 功率分配)统一兜底:
    # 脏数据(float 转换失败)/ 非法时间窗口会在此抛 ValueError/TypeError,
    # 不应冒泡成未捕获 500。降级为 error + rollback(保持 session 干净) + 记日志。
    # 注: 体内显式 return {"error": ...} 是业务校验, 正常退出不被 except 捕获。
    try:
        max_power_per_vehicle = float(
            rule_spec.get("max_power_per_vehicle", _DEFAULT_MAX_POWER_PER_VEHICLE)
        )
        if max_power_per_vehicle <= 0:
            return {"error": "单车最大功率必须大于0"}
        v2g_enabled = bool(rule_spec.get("v2g_enabled", False))
        v2g_threshold = float(rule_spec.get("v2g_discharge_threshold", _DEFAULT_V2G_DISCHARGE_THRESHOLD))
        v2g_discharge_kw = float(rule_spec.get("v2g_discharge_kw", _DEFAULT_V2G_DISCHARGE_KW))
        default_target_soc = float(rule_spec.get("target_soc", _DEFAULT_TARGET_SOC))

        period = window_period(time_window_start)

        # ─── 1. 车辆分类: 充电候选 / V2G放电候选 ───
        charge_candidates: List[Dict[str, Any]] = []
        v2g_candidates: List[Dict[str, Any]] = []
        seen_vids: set = set()
        for vs in vehicle_states:
            vid = vs.get("vehicle_id")
            if vid is None:
                return {"error": "vehicle_states 缺少 vehicle_id"}
            # 重复 vehicle_id 去重: 同一辆车出现多次只保留首条, 避免双倍分配功率
            if vid in seen_vids:
                logger.warning("generate_schedule 重复 vehicle_id=%s 跳过去重, enterprise_id=%s", vid, enterprise_id)
                continue
            seen_vids.add(vid)
            cur = float(vs.get("current_soc", 0.0))
            tgt = float(vs.get("target_soc", default_target_soc))
            if cur < 0 or cur > 1 or tgt < 0 or tgt > 1:
                return {"error": "SOC必须在0-1范围"}
            cap = float(vs.get("max_power_kw", max_power_per_vehicle))
            # 非正最大功率为脏数据, 跳过该车不阻断整体调度
            if cap <= 0:
                logger.warning("generate_schedule vehicle_id=%s max_power_kw=%s 非正, 跳过, enterprise_id=%s", vid, cap, enterprise_id)
                continue
            state = {
                "vehicle_id": vid,
                "current_soc": cur,
                "target_soc": tgt,
                "max_power_kw": cap,
            }
            # V2G: 启用且 SOC 达到放电阈值且无需再充(目标<=当前)
            if v2g_enabled and cur >= v2g_threshold and tgt <= cur:
                v2g_candidates.append(state)
            elif cur < tgt:
                charge_candidates.append(state)
            # 否则: SOC 已达标且不放电 -> 不参与(不产生条目)

        # ─── 2. SOC 优先级排序: 低 SOC 优先(priority 数字越小越优先) ───
        charge_candidates.sort(key=lambda s: s["current_soc"])
        for idx, s in enumerate(charge_candidates, start=1):
            s["priority"] = idx

        # ─── 3. 变压器容量约束下功率分配(按优先级贪心) ───
        remaining = available_power_kw
        for s in charge_candidates:
            cap = min(s["max_power_kw"], max_power_per_vehicle)
            if remaining > 0:
                alloc = min(cap, remaining)
            else:
                alloc = 0.0
            s["assigned_power_kw"] = round(alloc, 2)
            s["mode"] = ChargingEntryMode.CHARGE if alloc > 0 else ChargingEntryMode.IDLE
            remaining -= alloc

        # ─── 4. V2G 反向放电窗口(仅峰时段放电, 否则待机) ───
        discharge_in_window = v2g_enabled and period == ChargingPeriodType.PEAK
        for s in v2g_candidates:
            if discharge_in_window:
                s["assigned_power_kw"] = round(v2g_discharge_kw, 2)
                s["mode"] = ChargingEntryMode.DISCHARGE
                # 放电优先级排到充电之后: 100 + (1-soc)*100, SOC 越高越先放
                s["priority"] = 100 + int((1 - s["current_soc"]) * 100)
            else:
                s["assigned_power_kw"] = 0.0
                s["mode"] = ChargingEntryMode.IDLE
                s["priority"] = 200
    except Exception as e:
        db.rollback()
        logger.exception("generate_schedule 计算阶段失败 enterprise_id=%s: %s", enterprise_id, e)
        return {"error": "调度服务暂时不可用"}

    # ─── 5. 持久化计划与条目 ───
    try:
        plan = ChargingSchedulePlan(
            enterprise_id=enterprise_id,
            plan_date=datetime.now(timezone.utc),
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            total_available_power_kw=available_power_kw,
            status=ChargingSchedulePlanStatus.PLANNED,
            rule_json={
                "max_power_per_vehicle": max_power_per_vehicle,
                "v2g_enabled": v2g_enabled,
                "v2g_discharge_threshold": v2g_threshold,
                "period_type": period.value,
            },
        )
        db.add(plan)
        db.flush()  # 拿到 plan.id

        entry_objs: List[ChargingScheduleEntry] = []
        for s in charge_candidates + v2g_candidates:
            mode: ChargingEntryMode = s["mode"]
            e = ChargingScheduleEntry(
                plan_id=plan.id,
                vehicle_id=s["vehicle_id"],
                assigned_power_kw=s["assigned_power_kw"],
                start_time=time_window_start,
                end_time=time_window_end,
                priority=s["priority"],
                soc_start=s["current_soc"],
                soc_target=s["target_soc"],
                charge_mode=mode,
                # 充电/放电条目标注时段, 待机不标
                period_type=period if mode != ChargingEntryMode.IDLE else None,
            )
            entry_objs.append(e)
        db.add_all(entry_objs)
        db.commit()
        for e in entry_objs:
            db.refresh(e)
        db.refresh(plan)
    except Exception as e:
        db.rollback()
        logger.exception("generate_schedule 持久化失败 enterprise_id=%s: %s", enterprise_id, e)
        return {"error": "调度服务暂时不可用"}

    allocated = round(sum(s["assigned_power_kw"] for s in charge_candidates), 2)
    return {
        "plan_id": plan.id,
        "enterprise_id": enterprise_id,
        "period_type": period.value,
        "valley_preferred": period == ChargingPeriodType.VALLEY,
        "summary": {
            "available_power_kw": available_power_kw,
            "allocated_power_kw": allocated,
            "remaining_power_kw": round(max(0.0, remaining), 2),
            "charging_vehicles": sum(1 for s in charge_candidates if s["mode"] == ChargingEntryMode.CHARGE),
            "idle_vehicles": sum(1 for s in charge_candidates if s["mode"] == ChargingEntryMode.IDLE),
            "v2g_discharge_vehicles": sum(1 for s in v2g_candidates if s["mode"] == ChargingEntryMode.DISCHARGE),
        },
        "entries": [
            {
                "id": e.id,
                "vehicle_id": e.vehicle_id,
                "assigned_power_kw": e.assigned_power_kw,
                "priority": e.priority,
                "soc_start": e.soc_start,
                "soc_target": e.soc_target,
                "charge_mode": e.charge_mode.value,
                "period_type": e.period_type.value if e.period_type else None,
            }
            for e in entry_objs
        ],
    }


def adjust_schedule(
    db: Session,
    plan_id: int,
    new_distribution: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    动态调整调度功率分配。

    Args:
        db: 数据库会话
        plan_id: 计划 ID
        new_distribution: [{"entry_id": 1, "new_power_kw": 5.0}, ...]

    Returns:
        成功: {plan_id, status, entries}
        失败: {"error": "..."}
    """
    # 查询 + 转换阶段(db.get / db.query / float 转换)统一兜底:
    # 连接异常 / 脏功率值(float('oops'))会在此抛, 不应冒泡成未捕获 500。
    # 体内显式 return {"error": ...} 是业务校验, 正常退出不被 except 捕获。
    try:
        plan = db.get(ChargingSchedulePlan, plan_id)
        if not plan:
            return {"error": f"调度计划 {plan_id} 不存在"}
        if plan.status.value not in (ChargingSchedulePlanStatus.PLANNED.value,
                                     ChargingSchedulePlanStatus.ACTIVE.value):
            return {"error": f"计划状态 {plan.status.value} 不可调整"}

        entries = {
            e.id: e
            for e in db.query(ChargingScheduleEntry)
            .filter(ChargingScheduleEntry.plan_id == plan_id)
            .all()
        }

        for adj in new_distribution:
            eid = adj.get("entry_id")
            if eid not in entries:
                db.rollback()
                return {"error": f"条目 {eid} 不属于计划 {plan_id}"}
            new_power = float(adj.get("new_power_kw", 0))
            # NaN/±Inf(float('nan')/float('inf') 不抛异常, 且 nan<0=False)
            # 会绕过负值检查并污染容量校验(sum 混入 nan 后恒 False), 统一拦截。
            if not math.isfinite(new_power):
                db.rollback()
                return {"error": "功率必须为有限数值"}
            if new_power < 0:
                db.rollback()
                return {"error": "功率不能为负"}
            entries[eid].assigned_power_kw = round(new_power, 2)

        # 校验调整后总功率不超过计划可用容量
        total_power = round(sum(e.assigned_power_kw for e in entries.values()), 2)
        if total_power > plan.total_available_power_kw:
            db.rollback()
            return {"error": "调整后总功率超过可用容量"}
    except Exception as e:
        db.rollback()
        logger.exception("adjust_schedule 查询/转换失败 plan_id=%s: %s", plan_id, e)
        return {"error": "调度服务暂时不可用"}

    try:
        db.commit()
        result_entries = (
            db.query(ChargingScheduleEntry)
            .filter(ChargingScheduleEntry.plan_id == plan_id)
            .order_by(ChargingScheduleEntry.priority)
            .all()
        )
    except Exception as e:
        db.rollback()
        logger.exception("adjust_schedule 持久化失败 plan_id=%s: %s", plan_id, e)
        return {"error": "调度服务暂时不可用"}

    return {
        "plan_id": plan_id,
        "status": plan.status.value,
        "entries": [
            {
                "id": e.id,
                "vehicle_id": e.vehicle_id,
                "assigned_power_kw": e.assigned_power_kw,
                "priority": e.priority,
                "charge_mode": e.charge_mode.value,
            }
            for e in result_entries
        ],
    }

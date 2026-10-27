"""celery beat 15min 能量调度任务 + 能量流水落库 — P1-3 (卡片 a76fac6b)

每 15min 周期 (SPEC §7 调度引擎接入, 预研 §4):
1. 读所有启用策略场站 (StationEnergyStrategy.is_active=True)
2. 每站读当前生效 EnergyPriceTemplate + 最新 telemetry (PV/Battery/Charger)
3. 组装 ChargingContext (对齐 strategy_base.py:28 字段, 作为统一上下文载体)
4. 由 ctx 构造各业务策略 StrategyAdvice → EnergyArbitrator.arbitrate() → ArbitrationResult
5. 本层变压器容量约束校验 (仲裁层未做, P1-2 commit 注说明) → 钳位储能充电 + 算需求侧预算
6. 写 EnergyDispatchPlan (决策日志存 winning_strategies JSON + decision_reason Text)
7. 聚合 telemetry 写 EnergyFlowLog (瞬时功率 → 15min 能量值)
8. available_power_budget_kw 写入 plan, 下发给需求侧 (charging_schedule_service.generate_schedule
   的 available_power_kw 入参, 预研 §4.3 协同接口)

不修改 P1-1/P1-2 已交付文件 (models/energy_strategy.py / arbitrator.py / energy_flow.py)。
时区 Asia/Shanghai (celery_app 已配); now 缺省走 UTC, beat 触发时由 celery 时区换算。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.models.energy_strategy import (
    EnergyDispatchPlan,
    EnergyFlowLog,
    EnergyPricePeriod,
    EnergyPriceTemplate,
    StationEnergyStrategy,
)
from app.models.telemetry_v2 import TelemetryBattery, TelemetryCharger, TelemetryPV
from app.services.charging.arbitrator import (
    AdviceDirection,
    ArbitrationMode,
    EnergyArbitrator,
    HardConstraints,
    StrategyAdvice,
    StrategyType,
)
from app.services.charging.strategy_base import ChargingContext
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df
from app.tasks.tz_utils import to_aware_biz_tz

logger = logging.getLogger(__name__)

# ─── 常量 ───
WINDOW_MINUTES = 15                       # 15min 调度窗口
POWER_FACTOR_DEFAULT = 0.9                # 变压器 kVA → 有功 kW 默认功率因数
DEFAULT_CHARGE_KW = 50.0                  # 套利/消纳默认充电功率建议 (对齐 StorageOptimizer.DEFAULT_CHARGE_KW)
DEFAULT_DISCHARGE_KW = 50.0               # 增容默认放电功率建议
DEFAULT_VALLEY_PRICE = 0.40               # 低谷充电电价阈值 (元/kWh)
DEFAULT_PEAK_PRICE = 0.90                 # 高峰放电电价阈值 (元/kWh)
DEFAULT_SOC_CEILING = 0.90                # SOC 上限 (energy_strategy 表无此列, 走默认/配置)


# ═══════════════════════════════════════════════════════════════
# 时间窗口
# ═══════════════════════════════════════════════════════════════

def _floor_window(dt: datetime) -> datetime:
    """向下降采样到 15min 窗口起点"""
    return dt.replace(
        minute=(dt.minute // WINDOW_MINUTES) * WINDOW_MINUTES,
        second=0, microsecond=0,
    )


# ═══════════════════════════════════════════════════════════════
# 遥测读取
# ═══════════════════════════════════════════════════════════════

def _latest_pv(db: Session, station_id: int) -> Optional[TelemetryPV]:
    return (
        db.query(TelemetryPV)
        .filter(TelemetryPV.station_id == station_id)
        .order_by(TelemetryPV.timestamp.desc())
        .first()
    )


def _latest_battery(db: Session, station_id: int) -> Optional[TelemetryBattery]:
    return (
        db.query(TelemetryBattery)
        .filter(TelemetryBattery.station_id == station_id)
        .order_by(TelemetryBattery.timestamp.desc())
        .first()
    )


def _charger_load_kw(db: Session, station_id: int) -> float:
    """站级充电桩负荷: 取该站最新批次所有桩功率之和 (一站多桩)。

    最新 timestamp 用 SQL 标量子查询匹配 (sqlite 下 DateTime 列与 Python datetime
    直接 == 比较不可靠, 必须在 SQL 层比较)。
    """
    latest_ts_subq = (
        db.query(func.max(TelemetryCharger.timestamp))
        .filter(TelemetryCharger.station_id == station_id)
        .scalar_subquery()
    )
    rows = (
        db.query(TelemetryCharger.charger_power)
        .filter(
            TelemetryCharger.station_id == station_id,
            TelemetryCharger.timestamp == latest_ts_subq,
        )
        .all()
    )
    return float(sum((r[0] or 0.0) for r in rows))


# ═══════════════════════════════════════════════════════════════
# 电价
# ═══════════════════════════════════════════════════════════════

def _current_grid_price(db: Session, template_id: Optional[int], now: datetime) -> Optional[float]:
    """读模板当前生效时段的购电单价 (元/kWh)。无模板/未生效/无匹配时段 → None"""
    if template_id is None:
        return None
    tpl = (
        db.query(EnergyPriceTemplate)
        .filter(
            EnergyPriceTemplate.id == template_id,
            EnergyPriceTemplate.is_active.is_(True),
        )
        .first()
    )
    if tpl is None:
        return None
    # 卡 fd59ac1c: now 可能是 aware UTC (生产 dispatch_cycle 缺省) — 必须先归一到业务时区
    # 墙钟再取 date/time, 否则峰谷判定整体错位 8h; effective_from/until 与时段列的
    # 语义均为业务墙钟 (上海)。
    wall = to_aware_biz_tz(now)
    today = wall.date()
    if tpl.effective_from is not None and today < tpl.effective_from:
        return None
    if tpl.effective_until is not None and today > tpl.effective_until:
        return None
    now_time = wall.time()
    # 跨午夜时段 (start > end, 如 valley 22:00-08:00) 无法用区间比较命中, 全量读回逐段判断
    periods = (
        db.query(EnergyPricePeriod)
        .filter(EnergyPricePeriod.template_id == template_id)
        .all()
    )
    for period in periods:
        if period.start_time <= period.end_time:
            hit = period.start_time <= now_time <= period.end_time
        else:
            hit = now_time >= period.start_time or now_time <= period.end_time
        if hit:
            if period.purchase_price is None:
                return None
            return float(period.purchase_price)
    return None


# ═══════════════════════════════════════════════════════════════
# Advice 构造 (ctx → 各业务策略建议)
# ═══════════════════════════════════════════════════════════════

def _build_advices(ctx: ChargingContext, strategy_config: Optional[dict]) -> List[StrategyAdvice]:
    """由 ChargingContext + 策略开关构造各业务策略的功率建议。

    SAFETY/BACKUP 由仲裁层硬约束体现, 此处只产业务策略 advice:
    - ARBITRAGE 套利: 低谷电网充电 / 高峰放电
    - SOLAR_ABSORB 消纳: 光伏余电(扣直供后)充入储能
    - BOOSTING 增容: 有充电负荷时储能放电补供
    """
    cfg = strategy_config or {}
    strats = cfg.get("strategies") or {}
    valley_th = cfg.get("valley_price_threshold", DEFAULT_VALLEY_PRICE)
    peak_th = cfg.get("peak_price_threshold", DEFAULT_PEAK_PRICE)

    pv_surplus_kw = max(0.0, ctx.pv_output_kw - ctx.demand_power_kw)  # 光伏直供后的余电
    advices: List[StrategyAdvice] = []

    # 套利: 低谷充 / 高峰放
    if strats.get("arbitrage", {}).get("enabled", True) and ctx.grid_price is not None:
        if ctx.grid_price <= valley_th:
            advices.append(StrategyAdvice(
                StrategyType.ARBITRAGE, AdviceDirection.CHARGE, DEFAULT_CHARGE_KW,
                reason=f"低谷电价{ctx.grid_price:.2f}元/kWh, 电网充电套利",
            ))
        elif ctx.grid_price >= peak_th:
            advices.append(StrategyAdvice(
                StrategyType.ARBITRAGE, AdviceDirection.DISCHARGE, DEFAULT_DISCHARGE_KW,
                reason=f"高峰电价{ctx.grid_price:.2f}元/kWh, 放电套利",
            ))

    # 消纳: 光伏余电 → 储能
    if strats.get("solar_absorb", {}).get("enabled", True) and pv_surplus_kw > 1e-9:
        advices.append(StrategyAdvice(
            StrategyType.SOLAR_ABSORB, AdviceDirection.CHARGE,
            min(pv_surplus_kw, DEFAULT_CHARGE_KW),
            reason=f"光伏余电{pv_surplus_kw:.1f}kW消纳充储",
        ))

    # 增容: 充电负荷 → 储能放电补供
    if strats.get("boosting", {}).get("enabled", True) and ctx.demand_power_kw > 1e-9:
        advices.append(StrategyAdvice(
            StrategyType.BOOSTING, AdviceDirection.DISCHARGE,
            min(ctx.demand_power_kw, DEFAULT_DISCHARGE_KW),
            reason=f"充电负荷{ctx.demand_power_kw:.1f}kW, 储能放电增容",
        ))

    return advices


# ═══════════════════════════════════════════════════════════════
# 单站调度
# ═══════════════════════════════════════════════════════════════

def _build_arbitrator(strategy_config: Optional[dict]) -> EnergyArbitrator:
    cfg = strategy_config or {}
    priority_override = None
    priorities_cfg = cfg.get("priorities")
    if isinstance(priorities_cfg, dict):
        priority_override = {
            StrategyType[k]: int(v) for k, v in priorities_cfg.items()
            if k in StrategyType.__members__
        }
    mode_str = cfg.get("arbitration_mode", ArbitrationMode.MAX.value)
    mode = ArbitrationMode(mode_str) if mode_str in ArbitrationMode.__members__ else ArbitrationMode.MAX
    stack_cap = cfg.get("stack_cap_kw")
    return EnergyArbitrator(
        priority_override=priority_override,
        default_mode=mode,
        stack_cap_kw=float(stack_cap) if stack_cap is not None else None,
    )


def _dispatch_one_station(
    db: Session,
    strategy: StationEnergyStrategy,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
) -> None:
    """单站: 组装 ctx → 仲裁 → 变压器约束 → 写 plan + flow log"""
    station_id = strategy.station_id
    cfg = strategy.strategy_config or {}

    # 1. 读遥测
    pv = _latest_pv(db, station_id)
    bat = _latest_battery(db, station_id)
    pv_kw = float(pv.pv_power_total or 0.0) if pv else 0.0
    charger_load_kw = _charger_load_kw(db, station_id)
    soc = (float(bat.battery_soc) / 100.0) if (bat and bat.battery_soc is not None) else 0.0
    bat_power = float(bat.battery_power or 0.0) if bat else 0.0  # 正=充电 负=放电
    bat_temp = float(bat.battery_temperature) if (bat and bat.battery_temperature is not None) else None
    grid_power_total = float(pv.grid_power_total or 0.0) if pv else 0.0  # 正=取电 负=上网

    # 2. 读电价
    grid_price = _current_grid_price(db, strategy.price_template_id, now)
    valley_th = cfg.get("valley_price_threshold", DEFAULT_VALLEY_PRICE)

    # 3. 组装 ChargingContext (对齐 strategy_base.py:28)
    ctx = ChargingContext(
        station_id=str(station_id),
        charger_id="STATION_LEVEL",           # 站级调度, 非单桩
        rated_power_kw=charger_load_kw,
        demand_power_kw=charger_load_kw,
        pv_output_kw=pv_kw,
        battery_soc=soc,
        battery_capacity_kwh=float(strategy.ess_capacity_kwh or 0.0),
        battery_available_kw=DEFAULT_DISCHARGE_KW,
        battery_temp_c=bat_temp,
        grid_price=grid_price,
        in_valley_period=(grid_price is not None and grid_price <= valley_th),
        timestamp=now,
    )

    # 4. 构造 advice → 仲裁
    advices = _build_advices(ctx, cfg)
    constraints = HardConstraints(
        soc=soc,
        soc_floor=float(strategy.soc_floor) if strategy.soc_floor is not None else 0.10,
        soc_ceiling=float(cfg.get("soc_ceiling", DEFAULT_SOC_CEILING)),
        bms_max_charge_kw=cfg.get("bms_max_charge_kw"),
        bms_max_discharge_kw=cfg.get("bms_max_discharge_kw"),
        cycles_today=0,                      # P1 无当日循环计数数据源, 留 P2
        max_daily_cycles=strategy.max_daily_cycles,
    )
    arbitrator = _build_arbitrator(cfg)
    result = arbitrator.arbitrate(advices, constraints)

    # 5. 仲裁结果 → 储能指令功率
    ess_charge_kw = result.power_kw if result.direction == AdviceDirection.CHARGE else 0.0
    ess_discharge_kw = result.power_kw if result.direction == AdviceDirection.DISCHARGE else 0.0

    # 6. 本层变压器容量约束 (仲裁层未做): 从电网抽取 ≤ 变压器有功容量, 超则钳位储能充电
    transformer_kw = float(strategy.transformer_capacity_kva or 0.0) * POWER_FACTOR_DEFAULT
    pv_direct_kw = min(pv_kw, charger_load_kw)  # 光伏直供负荷部分
    grid_draw_kw = ess_charge_kw + charger_load_kw - pv_direct_kw - ess_discharge_kw
    clip_note = ""
    if transformer_kw > 0 and grid_draw_kw > transformer_kw:
        overflow = grid_draw_kw - transformer_kw
        ess_charge_kw = max(0.0, ess_charge_kw - overflow)
        grid_draw_kw = transformer_kw
        clip_note = (
            f"变压器容量{transformer_kw:.1f}kW约束, 储能充电钳位{overflow:.1f}kW"
        )

    # 7. 下发需求侧功率预算 = 变压器 + 光伏 + 储能放电 − 储能充电占用
    available_budget = max(
        0.0, transformer_kw + pv_kw + ess_discharge_kw - ess_charge_kw
    )

    # 8. 决策日志
    reason_parts: List[str] = []
    if result.reason:
        reason_parts.append(result.reason)
    if clip_note:
        reason_parts.append(clip_note)

    # 9. 写 EnergyDispatchPlan (卡 97c83af9: 同窗口唯一约束 uq_edp_station_window,
    #    beat 重叠/acks_late 重投递时覆盖已有 plan 而非重复插入)
    plan = (
        db.query(EnergyDispatchPlan)
        .filter(
            EnergyDispatchPlan.station_id == station_id,
            EnergyDispatchPlan.window_start == window_start,
        )
        .first()
    )
    if plan is None:
        plan = EnergyDispatchPlan(
            station_id=station_id,
            team_id=strategy.team_id,
            window_start=window_start,
            window_end=window_end,
            price_template_id=strategy.price_template_id,
            pv_setpoint_kw=round(pv_kw, 4),
            ess_charge_kw=round(ess_charge_kw, 4),
            ess_discharge_kw=round(ess_discharge_kw, 4),
            grid_purchase_kw=round(max(0.0, grid_draw_kw), 4),
            grid_export_kw=0.0,               # P1 防逆流默认关 (energy_flow.allow_export=False), 不上网
            available_power_budget_kw=round(available_budget, 4),
            winning_strategies={
                "winning_strategy": result.winning_strategy.value if result.winning_strategy else None,
                "direction": result.direction.value,
                "power_kw": result.power_kw,
                "mode": result.mode.value,
                "decision_log": result.decision_log,
            },
            decision_reason="; ".join(reason_parts) if reason_parts else None,
        )
        db.add(plan)

    # 10. 聚合 telemetry 写 EnergyFlowLog (瞬时功率 → 15min 能量值)
    # 卡 113e313b: 同窗口查重防重插 (与上方 plan 同模式)。DB 级唯一约束留待决策,
    # 当前模型仅普通索引 ix_efl_station_window, 代码层先挡 acks_late 重投递双插
    flow = (
        db.query(EnergyFlowLog)
        .filter(
            EnergyFlowLog.station_id == station_id,
            EnergyFlowLog.window_start == window_start,
        )
        .first()
    )
    if flow is not None:
        return

    kw_to_kwh = WINDOW_MINUTES / 60.0
    flow = EnergyFlowLog(
        station_id=station_id,
        team_id=strategy.team_id,
        window_start=window_start,
        pv_generation_kwh=round(pv_kw * kw_to_kwh, 4),
        pv_self_consumed_kwh=None,            # P1 不拆分光伏自用/上网
        ess_charge_kwh=round(max(0.0, bat_power) * kw_to_kwh, 4),
        ess_discharge_kwh=round(max(0.0, -bat_power) * kw_to_kwh, 4),
        grid_purchase_kwh=round(max(0.0, grid_power_total) * kw_to_kwh, 4),
        grid_export_kwh=round(max(0.0, -grid_power_total) * kw_to_kwh, 4),
        charger_load_kwh=round(charger_load_kw * kw_to_kwh, 4),
        soc_snapshot=round(soc, 4),
        cost_saving_yuan=None,                # P2 套利收益统计
    )
    db.add(flow)


# ═══════════════════════════════════════════════════════════════
# 周期入口 (纯函数, 可测)
# ═══════════════════════════════════════════════════════════════

def run_dispatch_cycle(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    """读启用策略场站 → 逐站调度 → 落 plan + flow log。

    单站异常不阻塞其他站。调用方负责 commit/rollback。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = _floor_window(now)
    window_end = window_start + timedelta(minutes=WINDOW_MINUTES)

    strategies = (
        db.query(StationEnergyStrategy)
        .filter(StationEnergyStrategy.is_active.is_(True))
        .all()
    )
    plans = flow_logs = 0
    for strategy in strategies:
        try:
            _dispatch_one_station(db, strategy, window_start, window_end, now)
            plans += 1
            flow_logs += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.exception("[energy] 场站 %s 调度失败, 跳过", strategy.station_id)

    db.flush()
    logger.info(
        "[energy] 调度周期完成: stations=%d plans=%d window=%s",
        len(strategies), plans, window_start.isoformat(),
    )
    return {
        "stations": len(strategies),
        "plans": plans,
        "flow_logs": flow_logs,
        "window_start": window_start.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 协同桥接 (预研 §4.3): 供给侧功率预算 → 需求侧排车
# ═══════════════════════════════════════════════════════════════

def apply_power_budget_to_charging(
    db: Session,
    station_id: int,
    enterprise_id: int,
    vehicle_states: List[Dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
    rule_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """功率预算协同桥接 (预研 §4.3 协同接口)。

    读站级最新 EnergyDispatchPlan.available_power_budget_kw, 作为需求侧排车的
    功率上限下发给 charging_schedule_service.generate_schedule, 使排车计划严格
    落在供给侧算出的功率预算内 (不超发)。

    供给侧 (本模块 run_dispatch_cycle) 按站算预算, 需求侧 (generate_schedule) 按
    企业+车辆排车, 两者通过本函数以数值预算为契约桥接; enterprise_id / vehicle_states
    由需求侧调用方提供 (车桩绑定关系属需求侧职责, 不在本模块数据域内)。

    Args:
        station_id: 取该站最新 plan.available_power_budget_kw 作为预算
        enterprise_id / vehicle_states / window / rule_spec: 透传给 generate_schedule
    Returns:
        generate_schedule 返回 dict (成功), 额外附 ``power_budget_source`` 溯源; 或
        ``{"error": ...}`` (该站无可用预算)
    """
    # 局部 import: 惰性拉需求侧服务链, 隔离协同依赖, 不扩大本模块加载面
    from app.services.charging_schedule_service import generate_schedule

    plan = (
        db.query(EnergyDispatchPlan)
        .filter(EnergyDispatchPlan.station_id == station_id)
        .order_by(EnergyDispatchPlan.window_start.desc())
        .first()
    )
    if plan is None or plan.available_power_budget_kw is None:
        return {"error": f"场站 {station_id} 无可用功率预算(无 EnergyDispatchPlan 记录)"}

    budget = float(plan.available_power_budget_kw)
    schedule = generate_schedule(
        db,
        enterprise_id=enterprise_id,
        vehicle_states=vehicle_states,
        available_power_kw=budget,
        time_window_start=window_start,
        time_window_end=window_end,
        rule_spec=rule_spec,
    )
    if isinstance(schedule, dict) and "error" not in schedule:
        schedule["power_budget_source"] = {
            "plan_id": plan.id,
            "station_id": station_id,
            "available_power_budget_kw": budget,
        }
    return schedule


# ═══════════════════════════════════════════════════════════════
# celery task
# ═══════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="energy.dispatch_cycle", max_retries=2, default_retry_delay=60)
def dispatch_cycle(self) -> Dict[str, Any]:
    """15min 能量调度周期任务 (celery beat 触发)"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        result = run_dispatch_cycle(db)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("[energy] 调度周期失败: %s", e, exc_info=True)
        raise self.retry(exc=e)
    finally:
        db.close()

"""
VPP 调度优化器 — 核心算法

原 app/services/vpp/dispatch_optimizer.py(1138行) 拆分而来(卡 61109a8a)。
混合整数线性规划(简化版) + 启发式规则: 经济调度/削峰填谷/需求响应/多站点协同。
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
import uuid

from .models import (
    ResourceType,
    DispatchMode,
    GridSignal,
    StationStatus,
    ResourceCapability,
    DispatchCommand,
    DispatchPlan,
)

logger = logging.getLogger("vpp")


def _make_plan_id(prefix: str) -> str:
    """生成调度计划ID: 前缀 + 秒级时间戳 + uuid4 hex 后缀。

    旧实现 f"{prefix}_{strftime('%Y%m%d%H%M%S')}" 仅秒级粒度, 同一秒内生成两个
    同前缀计划(降级链背靠背 / 削峰与需求响应同秒 / coordinator 与 optimizer 的
    safe_ 异常降级双入口)会产生完全相同的 plan_id, 污染日志与上报 payload 追踪。
    追加 uuid4().hex[:6] 后缀消除同秒碰撞, 保留秒级时间戳的可读性。

    prefix 须含尾分隔符(如 'safe_'/'eco_'), 输出形如 'safe_20260806070500_ab12cd'。
    """
    return f"{prefix}{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _get_pricing_tz() -> ZoneInfo:
    """电价时区 (从 settings.PRICING_TIMEZONE 读取, 默认 Asia/Shanghai)。

    懒导入 settings 规避循环依赖; 配置缺失/坏值兜底为 Asia/Shanghai, 保证电价窗口
    判定永不因配置问题崩溃。ZoneInfo 对同一 key 内部缓存, 重复构造零额外开销。
    """
    try:
        from app.core.config import settings
        return ZoneInfo(settings.PRICING_TIMEZONE)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _pricing_hour(now: Optional[datetime] = None) -> float:
    """当前电价时段的小时浮点值 (电价时区)。

    修复 (卡 9912ba63) 两个缺陷:
    1. 显式电价时区 — 电价窗口 (尖峰10-12 / 高峰8-10,18-21 / 低谷23-6) 按工商业分时
       电价的本地时间定义。旧 datetime.now() 返回 naive 本地时间, 容器默认 UTC 部署时
       窗口整体错位 8h。现统一按 settings.PRICING_TIMEZONE (默认 Asia/Shanghai) 判定,
       跨时区部署仍选中同一电价窗口。
    2. 单次 now 取值 — 旧 datetime.now().hour + datetime.now().minute/60.0 两次独立
       now() 之间可能跨整点 (10:59:59.999→11:00:00.001), 使 hour 与 minute 来自不同
       分钟, 峰谷切换边界产生毛刺 (hour=10.0 而非 10.983)。现单次 now(tz) 取值同源。

    now: 测试注入固定 aware 时刻; None 取当前电价时区时间。
    """
    tz = _get_pricing_tz()
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    return current.hour + current.minute / 60.0


# ─── 调度优化算法 ───

class VPPOptimizer:
    """
    VPP调度优化器
    核心算法：混合整数线性规划(简化版) + 启发式规则
    """

    # 电价时段定义 (示例: 工商业分时电价)
    PRICE_SCHEDULE = {
        'peak': (10.0, 1.2),       # 尖峰: 10:00-12:00, 1.2元/kWh
        'high': [(8.0, 10.0), (18.0, 21.0)],  # 高峰
        'flat': [(6.0, 8.0), (12.0, 18.0), (21.0, 23.0)],  # 平段
        'valley': [(23.0, 6.0)],   # 低谷
    }
    PEAK_PRICE = 1.2      # 尖峰电价
    HIGH_PRICE = 0.9      # 高峰电价
    FLAT_PRICE = 0.6      # 平段电价
    VALLEY_PRICE = 0.3    # 低谷电价

    # SOC约束
    BATTERY_SOC_MIN = 0.10   # 最低SOC
    BATTERY_SOC_MAX = 0.95   # 最高SOC
    BATTERY_SOC_OPTIMAL = 0.50  # 最优SOC(调频备用)
    BATTERY_DISCHARGE_SOC_FLOOR = 0.20  # 放电SOC下限(放电需 soc 高于此值, 绝对不低于 BATTERY_SOC_MIN)

    # EV 削减
    EV_CURTAILMENT_RATIO = 0.5  # 高峰时段 EV 充电功率削减比例(原硬编码 0.5)

    # 需量响应参数
    DEMAND_RESPONSE_MIN_KW = 50.0    # 最小响应容量
    DEMAND_RESPONSE_MAX_DURATION = 240  # 最大响应时长(分钟)

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.price_multiplier = self.config.get('price_multiplier', 1.0)
        self.dr_reward_rate = self.config.get('dr_reward_rate', 0.5)  # 需求响应奖励率
        self.frequency_reg_reward = self.config.get('frequency_reg_reward', 0.15)  # 调频收益

    @property
    def _battery_discharge_soc_floor(self) -> float:
        """放电SOC下限: config 可覆盖, 兜底不低于 BATTERY_SOC_MIN(0.10)"""
        return max(
            self.config.get('battery_discharge_soc_floor', self.BATTERY_DISCHARGE_SOC_FLOOR),
            self.BATTERY_SOC_MIN,
        )

    @property
    def _ev_curtail_ratio(self) -> float:
        """EV 充电功率削减比例: config 可覆盖, 默认 0.5"""
        return self.config.get('ev_curtailment_ratio', self.EV_CURTAILMENT_RATIO)

    def _safe_default_plan(self, mode: DispatchMode, trigger: str,
                           stations: Optional[List[StationStatus]] = None) -> DispatchPlan:
        """异常降级: 返回安全空计划(0功率, 无指令), 保证调用方不崩溃"""
        logger.exception("调度优化异常降级[%s]: %s", mode.value, trigger)
        try:
            stations_involved = [
                s.station_id for s in (stations or [])
                if s and getattr(s, 'online', False)
            ]
        except Exception:
            stations_involved = []
        return DispatchPlan(
            plan_id=_make_plan_id("safe_"),
            mode=mode,
            trigger=f"异常降级: {trigger}",
            stations_involved=stations_involved,
            commands=[],
            total_dispatch_kw=0,
            estimated_revenue=0,
            estimated_cost=0,
            net_profit=0,
        )

    def get_current_price(self, hour: Optional[float] = None, *,
                          now: Optional[datetime] = None) -> float:
        """获取当前电价。

        hour: 显式小时浮点 (电价时区); 缺省时由 _pricing_hour(now) 按电价时区取当前时刻。
        now: 测试注入 aware 时刻; 仅在 hour 缺省时生效, 显式 hour 优先 (向后兼容现有调用)。
        """
        try:
            if hour is None:
                hour = _pricing_hour(now)

            # 尖峰
            if 10.0 <= hour < 12.0:
                return self.PEAK_PRICE * self.price_multiplier
            # 高峰
            if (8.0 <= hour < 10.0) or (18.0 <= hour < 21.0):
                return self.HIGH_PRICE * self.price_multiplier
            # 低谷
            if 23.0 <= hour or hour < 6.0:
                return self.VALLEY_PRICE * self.price_multiplier
            # 平段
            return self.FLAT_PRICE * self.price_multiplier
        except Exception:
            logger.exception("获取电价异常, 降级返回平段电价")
            return self.FLAT_PRICE

    def optimize_economic_dispatch(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        forecast_pv_kw: Optional[Dict[str, float]] = None,
    ) -> DispatchPlan:
        """经济调度优化 - 峰谷套利 (含异常降级)"""
        try:
            return self._optimize_economic_dispatch_impl(stations, resources, forecast_pv_kw)
        except Exception:
            return self._safe_default_plan(DispatchMode.ECONOMIC, "经济调度", stations)

    def _optimize_economic_dispatch_impl(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        forecast_pv_kw: Optional[Dict[str, float]] = None,
    ) -> DispatchPlan:
        """
        经济调度优化 - 峰谷套利
        目标: 最大化峰谷价差收益
        """
        hour = _pricing_hour()
        current_price = self.get_current_price(hour)

        commands = []
        total_dispatch_kw = 0.0
        total_revenue = 0.0
        total_cost = 0.0

        # 按站点聚合资源
        station_resources = {}
        for r in resources:
            if r.station_id not in station_resources:
                station_resources[r.station_id] = []
            station_resources[r.station_id].append(r)

        for station_id, st_resources in station_resources.items():
            for r in st_resources:
                cmd = self._optimize_single_resource(r, current_price, hour)
                if cmd and abs(cmd.target_power_kw) > 0.1:
                    commands.append(cmd)
                    total_dispatch_kw += cmd.target_power_kw
                    total_revenue += cmd.estimated_revenue
                    total_cost += cmd.estimated_cost

        # 按优先级排序
        commands.sort(key=lambda c: c.priority)

        return DispatchPlan(
            plan_id=_make_plan_id("eco_"),
            mode=DispatchMode.ECONOMIC,
            trigger=f"峰谷套利(当前电价: {current_price:.2f}元/kWh)",
            stations_involved=list(station_resources.keys()),
            commands=commands,
            total_dispatch_kw=total_dispatch_kw,
            estimated_revenue=total_revenue,
            estimated_cost=total_cost,
            net_profit=total_revenue - total_cost,
        )

    def optimize_peak_shaving(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        peak_threshold_kw: float,
    ) -> DispatchPlan:
        """削峰填谷优化 (含异常降级)"""
        try:
            return self._optimize_peak_shaving_impl(stations, resources, peak_threshold_kw)
        except Exception:
            return self._safe_default_plan(DispatchMode.PEAK_SHAVING, "削峰填谷", stations)

    def _optimize_peak_shaving_impl(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        peak_threshold_kw: float,
    ) -> DispatchPlan:
        """
        削峰填谷优化
        目标: 将总负荷控制在峰值阈值以下
        """
        # BUG2修复(卡c7b966cd): peak_threshold_kw≤0 时 overload=load-threshold 会把全部
        # 负荷判定为过载, 触发大规模储能放电+负荷削减。入口校验非法阈值, 返回安全空计划。
        if not peak_threshold_kw or peak_threshold_kw <= 0:
            return DispatchPlan(
                plan_id=_make_plan_id("ps_"),
                mode=DispatchMode.PEAK_SHAVING,
                trigger=f"峰值阈值无效({peak_threshold_kw}), 跳过削峰",
                stations_involved=[s.station_id for s in stations if s.online],
                commands=[],
                total_dispatch_kw=0,
                estimated_revenue=0,
                estimated_cost=0,
                net_profit=0,
            )

        commands = []
        total_current_load = sum(s.current_load_kw for s in stations if s.online)
        overload_kw = total_current_load - peak_threshold_kw

        if overload_kw <= 0:
            return DispatchPlan(
                plan_id=_make_plan_id("ps_"),
                mode=DispatchMode.PEAK_SHAVING,
                trigger=f"负荷正常({total_current_load:.0f}kW < {peak_threshold_kw:.0f}kW)",
                stations_involved=[s.station_id for s in stations if s.online],
                commands=[],
                total_dispatch_kw=0,
                estimated_revenue=0,
                estimated_cost=0,
                net_profit=0,
            )

        # 优先调度储能放电
        battery_resources = [r for r in resources if r.resource_type == ResourceType.BATTERY]
        battery_resources.sort(key=lambda r: (r.priority, -r.available_power_kw))

        remaining_overload = overload_kw

        for bat in battery_resources:
            if remaining_overload <= 0:
                break

            # 计算可放电功率
            max_discharge = min(
                bat.available_power_kw,
                bat.rated_power_kw,
                remaining_overload * 1.1  # 留10%余量
            )

            # SOC约束
            if bat.soc is not None and bat.soc < self.BATTERY_SOC_MIN + 0.1:
                continue

            discharge_kw = max(0, max_discharge)
            if discharge_kw > 0.1:
                revenue = discharge_kw * self.get_current_price() / 60 * 15  # 15分钟收益
                commands.append(DispatchCommand(
                    resource_id=bat.resource_id,
                    station_id=bat.station_id,
                    resource_type=ResourceType.BATTERY,
                    target_power_kw=discharge_kw,
                    duration_min=15,
                    priority=bat.priority,
                    estimated_revenue=revenue,
                    estimated_cost=0,
                    dispatch_mode=DispatchMode.PEAK_SHAVING,
                ))
                remaining_overload -= discharge_kw

        # 储能不足时，削减可调负荷
        if remaining_overload > 0:
            load_resources = [r for r in resources if r.resource_type == ResourceType.LOAD]
            load_resources.sort(key=lambda r: (r.priority, -r.available_power_kw))

            for load in load_resources:
                if remaining_overload <= 0:
                    break
                curtail_kw = min(load.available_power_kw, remaining_overload)
                if curtail_kw > 0.1:
                    commands.append(DispatchCommand(
                        resource_id=load.resource_id,
                        station_id=load.station_id,
                        resource_type=ResourceType.LOAD,
                        target_power_kw=-curtail_kw,  # 负=削减
                        duration_min=15,
                        priority=load.priority,
                        estimated_revenue=0,
                        estimated_cost=curtail_kw * 0.1,  # 削减补偿成本
                        dispatch_mode=DispatchMode.PEAK_SHAVING,
                    ))
                    remaining_overload -= curtail_kw

        total_dispatch = sum(c.target_power_kw for c in commands)
        total_revenue = sum(c.estimated_revenue for c in commands)
        total_cost = sum(c.estimated_cost for c in commands)

        return DispatchPlan(
            plan_id=_make_plan_id("ps_"),
            mode=DispatchMode.PEAK_SHAVING,
            trigger=f"削峰(负荷{total_current_load:.0f}kW超阈值{peak_threshold_kw:.0f}kW, 需削减{overload_kw:.0f}kW)",
            stations_involved=[s.station_id for s in stations if s.online],
            commands=commands,
            total_dispatch_kw=total_dispatch,
            estimated_revenue=total_revenue,
            estimated_cost=total_cost,
            net_profit=total_revenue - total_cost,
        )

    def handle_demand_response(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        signal: GridSignal,
    ) -> DispatchPlan:
        """需求响应 - 响应电网调度信号 (含异常降级)"""
        try:
            return self._handle_demand_response_impl(stations, resources, signal)
        except Exception:
            return self._safe_default_plan(DispatchMode.DEMAND_RESPONSE, "需求响应", stations)

    def _handle_demand_response_impl(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        signal: GridSignal,
    ) -> DispatchPlan:
        """
        需求响应 - 响应电网调度信号
        """
        target_kw = signal.target_power_kw or 0
        duration = signal.duration_min or 30
        reward = signal.reward_per_kwh or self.dr_reward_rate

        commands = []
        remaining_kw = target_kw

        # 1. 优先储能放电(最高价值)
        batteries = [r for r in resources if r.resource_type == ResourceType.BATTERY]
        batteries.sort(key=lambda r: (r.priority, -r.soc if r.soc else 0))

        for bat in batteries:
            if remaining_kw <= 0:
                break
            if bat.soc is not None and bat.soc < self.BATTERY_SOC_MIN + 0.15:
                continue

            discharge_kw = min(
                bat.available_power_kw,
                bat.rated_power_kw,
                remaining_kw
            )
            if discharge_kw > 0.1:
                revenue = discharge_kw * reward * duration / 60
                commands.append(DispatchCommand(
                    resource_id=bat.resource_id,
                    station_id=bat.station_id,
                    resource_type=ResourceType.BATTERY,
                    target_power_kw=discharge_kw,
                    duration_min=duration,
                    priority=1,
                    estimated_revenue=revenue,
                    estimated_cost=0,
                    dispatch_mode=DispatchMode.DEMAND_RESPONSE,
                ))
                remaining_kw -= discharge_kw

        # 2. 调整充电桩功率(降低充电)
        ev_chargers = [r for r in resources if r.resource_type == ResourceType.EV_CHARGER]
        ev_chargers.sort(key=lambda r: r.priority)

        for ev in ev_chargers:
            if remaining_kw <= 0:
                break
            curtail_kw = min(ev.current_power_kw, remaining_kw)
            if curtail_kw > 0.1:
                revenue = curtail_kw * reward * duration / 60
                commands.append(DispatchCommand(
                    resource_id=ev.resource_id,
                    station_id=ev.station_id,
                    resource_type=ResourceType.EV_CHARGER,
                    target_power_kw=-curtail_kw,
                    duration_min=duration,
                    priority=2,
                    estimated_revenue=revenue,
                    estimated_cost=0,
                    dispatch_mode=DispatchMode.DEMAND_RESPONSE,
                ))
                remaining_kw -= curtail_kw

        # 3. 可调负荷
        loads = [r for r in resources if r.resource_type == ResourceType.LOAD]
        for load in loads:
            if remaining_kw <= 0:
                break
            curtail_kw = min(load.available_power_kw, remaining_kw)
            if curtail_kw > 0.1:
                revenue = curtail_kw * reward * duration / 60
                commands.append(DispatchCommand(
                    resource_id=load.resource_id,
                    station_id=load.station_id,
                    resource_type=ResourceType.LOAD,
                    target_power_kw=-curtail_kw,
                    duration_min=duration,
                    priority=3,
                    estimated_revenue=revenue,
                    estimated_cost=curtail_kw * 0.1,
                    dispatch_mode=DispatchMode.DEMAND_RESPONSE,
                ))
                remaining_kw -= curtail_kw

        total_dispatch = sum(abs(c.target_power_kw) for c in commands)
        total_revenue = sum(c.estimated_revenue for c in commands)
        total_cost = sum(c.estimated_cost for c in commands)

        response_rate = (target_kw - remaining_kw) / target_kw if target_kw > 0 else 0

        return DispatchPlan(
            plan_id=_make_plan_id("dr_"),
            mode=DispatchMode.DEMAND_RESPONSE,
            trigger=f"需求响应(目标{target_kw:.0f}kW, 响应率{response_rate:.1%}, 时长{duration}min)",
            stations_involved=[s.station_id for s in stations if s.online],
            commands=commands,
            total_dispatch_kw=total_dispatch,
            estimated_revenue=total_revenue,
            estimated_cost=total_cost,
            net_profit=total_revenue - total_cost,
        )

    def optimize_multi_station_coordination(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        grid_signal: Optional[GridSignal] = None,
    ) -> DispatchPlan:
        """多站点协同调度优化 (含异常降级)"""
        try:
            return self._optimize_multi_station_coordination_impl(stations, resources, grid_signal)
        except Exception:
            return self._safe_default_plan(DispatchMode.GRID_SUPPORT, "多站点协同", stations)

    def _optimize_multi_station_coordination_impl(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        grid_signal: Optional[GridSignal] = None,
    ) -> DispatchPlan:
        """
        多站点协同调度优化
        综合考虑: 站点间功率互济 + 电网需求 + 经济性
        """
        hour = _pricing_hour()
        current_price = self.get_current_price(hour)

        # 1. 分析各站点供需平衡
        station_balance = {}
        for s in stations:
            if not s.online:
                continue
            surplus = s.current_pv_output_kw - s.current_load_kw + s.available_dispatch_kw
            station_balance[s.station_id] = {
                'surplus_kw': surplus,
                'need_import': surplus < 0,
                'can_export': surplus > 0,
                'station': s,
            }

        # 2. 站点间功率互济
        export_stations = [(sid, b) for sid, b in station_balance.items() if b['can_export']]
        import_stations = [(sid, b) for sid, b in station_balance.items() if b['need_import']]

        commands = []
        total_dispatch_kw = 0.0
        total_revenue = 0.0
        total_cost = 0.0

        # 缺电站点优先从余电站点调度
        for imp_sid, imp_balance in sorted(import_stations, key=lambda x: x[1]['surplus_kw']):
            deficit = abs(imp_balance['surplus_kw'])

            for exp_sid, exp_balance in sorted(export_stations, key=lambda x: -x[1]['surplus_kw']):
                if deficit <= 0 or exp_balance['surplus_kw'] <= 0:
                    continue

                transfer_kw = min(deficit, exp_balance['surplus_kw'])

                # 从导出站点的储能放电
                exp_resources = [r for r in resources if r.station_id == exp_sid
                                and r.resource_type == ResourceType.BATTERY]
                for bat in sorted(exp_resources, key=lambda r: (r.priority, -r.soc if r.soc else 0)):
                    if transfer_kw <= 0:
                        break
                    actual_kw = min(bat.available_power_kw, transfer_kw)
                    if actual_kw > 0.1:
                        revenue = actual_kw * current_price / 60 * 15
                        commands.append(DispatchCommand(
                            resource_id=bat.resource_id,
                            station_id=exp_sid,
                            resource_type=ResourceType.BATTERY,
                            target_power_kw=actual_kw,
                            duration_min=15,
                            priority=1,
                            estimated_revenue=revenue,
                            estimated_cost=0,
                            dispatch_mode=DispatchMode.GRID_SUPPORT,
                        ))
                        transfer_kw -= actual_kw
                        exp_balance['surplus_kw'] -= actual_kw
                        total_revenue += revenue
                        # BUG1修复(卡c7b966cd): deficit 须按本轮实际互济量(actual_kw)扣减。
                        # 旧公式 `deficit -= abs(imp_balance['surplus_kw']) - transfer_kw`
                        # 把常量缺口(abs(imp_surplus))当作扣减基准, 在余电不足(单余电站
                        # surplus<缺口)或多余电站场景下 deficit 被错误归零/变负, 后续余电站
                        # 因 deficit<=0 提前跳过, 缺电站需求无法满足。改为逐次实际扣减,
                        # 语义清晰且所有场景正确。
                        deficit -= actual_kw

        # 3. 处理电网调度信号
        if grid_signal:
            dr_plan = self.handle_demand_response(stations, resources, grid_signal)
            commands.extend(dr_plan.commands)
            total_revenue += dr_plan.estimated_revenue
            total_cost += dr_plan.estimated_cost

        # 4. 经济调度(峰谷套利)
        remaining_batteries = [r for r in resources if r.resource_type == ResourceType.BATTERY
                              and r.resource_id not in {c.resource_id for c in commands}]

        if current_price >= self.FLAT_PRICE:
            # 高电价时段 - 储能放电
            for bat in sorted(remaining_batteries, key=lambda r: (r.priority, -r.soc if r.soc else 0)):
                if bat.soc is not None and bat.soc < self.BATTERY_SOC_MIN + 0.1:
                    continue
                discharge_kw = min(bat.available_power_kw, bat.rated_power_kw)
                if discharge_kw > 0.1:
                    revenue = discharge_kw * (current_price - self.VALLEY_PRICE) / 60 * 15
                    commands.append(DispatchCommand(
                        resource_id=bat.resource_id,
                        station_id=bat.station_id,
                        resource_type=ResourceType.BATTERY,
                        target_power_kw=discharge_kw,
                        duration_min=15,
                        priority=3,
                        estimated_revenue=revenue,
                        estimated_cost=0,
                        dispatch_mode=DispatchMode.ECONOMIC,
                    ))
                    total_revenue += revenue
        else:
            # 低电价时段 - 储能充电
            for bat in sorted(remaining_batteries, key=lambda r: (r.priority, r.soc if r.soc else 0)):
                if bat.soc is not None and bat.soc >= self.BATTERY_SOC_MAX:
                    continue
                charge_kw = min(bat.rated_power_kw, bat.available_power_kw)
                if charge_kw > 0.1:
                    cost = charge_kw * current_price / 60 * 15
                    commands.append(DispatchCommand(
                        resource_id=bat.resource_id,
                        station_id=bat.station_id,
                        resource_type=ResourceType.BATTERY,
                        target_power_kw=-charge_kw,
                        duration_min=15,
                        priority=4,
                        estimated_revenue=0,
                        estimated_cost=cost,
                        dispatch_mode=DispatchMode.ECONOMIC,
                    ))
                    total_cost += cost

        total_dispatch_kw = sum(abs(c.target_power_kw) for c in commands)

        return DispatchPlan(
            plan_id=_make_plan_id("coord_"),
            mode=DispatchMode.GRID_SUPPORT,
            trigger=f"多站点协同调度(参与站点{len(station_balance)}个, 互济+经济调度)",
            stations_involved=[s.station_id for s in stations if s.online],
            commands=commands,
            total_dispatch_kw=total_dispatch_kw,
            estimated_revenue=total_revenue,
            estimated_cost=total_cost,
            net_profit=total_revenue - total_cost,
        )

    def _optimize_single_resource(
        self,
        resource: ResourceCapability,
        current_price: float,
        hour: float,
    ) -> Optional[DispatchCommand]:
        """优化单个资源的调度"""

        if resource.resource_type == ResourceType.BATTERY:
            return self._optimize_battery(resource, current_price, hour)
        elif resource.resource_type == ResourceType.EV_CHARGER:
            return self._optimize_ev_charger(resource, current_price, hour)
        elif resource.resource_type == ResourceType.LOAD:
            return self._optimize_load(resource, current_price, hour)
        elif resource.resource_type == ResourceType.PV:
            # 光伏不调度, 尽量满发
            return None
        return None

    def _optimize_battery(
        self,
        bat: ResourceCapability,
        current_price: float,
        hour: float,
    ) -> Optional[DispatchCommand]:
        """储能调度策略"""
        soc = bat.soc
        # BUG3修复(卡c7b966cd): SOC 未知(None)时不再默认 0.5 贸然放电(未知残余电量下
        # 放电有过放风险)。仅允许低谷充电(充电不会过放), 并打 warning 提示补齐 SOC 采集。
        if soc is None:
            logger.warning(
                "电池 %s SOC未知, 跳过放电决策, 仅允许低谷充电", bat.resource_id,
            )
            if current_price <= self.VALLEY_PRICE * 1.1:
                charge_kw = min(bat.rated_power_kw, bat.available_power_kw)
                cost = charge_kw * current_price / 60 * 15
                return DispatchCommand(
                    resource_id=bat.resource_id,
                    station_id=bat.station_id,
                    resource_type=ResourceType.BATTERY,
                    target_power_kw=-charge_kw,
                    duration_min=15,
                    priority=bat.priority,
                    estimated_revenue=0,
                    estimated_cost=cost,
                    dispatch_mode=DispatchMode.ECONOMIC,
                )
            return None

        # 低谷充电
        if current_price <= self.VALLEY_PRICE * 1.1 and soc < self.BATTERY_SOC_MAX:
            charge_kw = min(bat.rated_power_kw, bat.available_power_kw)
            cost = charge_kw * current_price / 60 * 15
            return DispatchCommand(
                resource_id=bat.resource_id,
                station_id=bat.station_id,
                resource_type=ResourceType.BATTERY,
                target_power_kw=-charge_kw,
                duration_min=15,
                priority=bat.priority,
                estimated_revenue=0,
                estimated_cost=cost,
                dispatch_mode=DispatchMode.ECONOMIC,
            )

        # 高价放电 (放电SOC下限动态校验, 不低于 BATTERY_SOC_MIN)
        if current_price >= self.HIGH_PRICE and soc > self._battery_discharge_soc_floor:
            discharge_kw = min(bat.available_power_kw, bat.rated_power_kw)
            revenue = discharge_kw * (current_price - self.VALLEY_PRICE) / 60 * 15
            return DispatchCommand(
                resource_id=bat.resource_id,
                station_id=bat.station_id,
                resource_type=ResourceType.BATTERY,
                target_power_kw=discharge_kw,
                duration_min=15,
                priority=bat.priority,
                estimated_revenue=revenue,
                estimated_cost=0,
                dispatch_mode=DispatchMode.ECONOMIC,
            )

        return None

    def _optimize_ev_charger(
        self,
        ev: ResourceCapability,
        current_price: float,
        hour: float,
    ) -> Optional[DispatchCommand]:
        """充电桩调度策略 - 低谷集中充电, 高峰降功率"""
        # BUG4修复(卡c7b966cd): current_power_kw 可能为 None, 直接 `> 0` 比较抛 TypeError。
        current_power = ev.current_power_kw or 0
        if current_price >= self.HIGH_PRICE and current_power > 0:
            # 高峰降低充电功率(默认50%, 可经 config ev_curtailment_ratio 覆盖)
            curtail_kw = current_power * self._ev_curtail_ratio
            saved = curtail_kw * current_price / 60 * 15
            return DispatchCommand(
                resource_id=ev.resource_id,
                station_id=ev.station_id,
                resource_type=ResourceType.EV_CHARGER,
                target_power_kw=-curtail_kw,
                duration_min=15,
                priority=ev.priority,
                estimated_revenue=saved,
                estimated_cost=0,
                dispatch_mode=DispatchMode.ECONOMIC,
            )
        return None

    def _optimize_load(
        self,
        load: ResourceCapability,
        current_price: float,
        hour: float,
    ) -> Optional[DispatchCommand]:
        """可调负荷调度"""
        if current_price >= self.PEAK_PRICE and load.available_power_kw > 0:
            # 尖峰削减负荷
            curtail_kw = load.available_power_kw * 0.3
            saved = curtail_kw * current_price / 60 * 15
            return DispatchCommand(
                resource_id=load.resource_id,
                station_id=load.station_id,
                resource_type=ResourceType.LOAD,
                target_power_kw=-curtail_kw,
                duration_min=15,
                priority=load.priority,
                estimated_revenue=saved,
                estimated_cost=curtail_kw * 0.1,
                dispatch_mode=DispatchMode.ECONOMIC,
            )
        return None

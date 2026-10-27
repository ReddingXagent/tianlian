"""
VPP 多站点协同调度器

原 app/services/vpp/dispatch_optimizer.py(1138行) 拆分而来(卡 61109a8a)。
管理多个站点的 VPP 聚合调度: 站点/资源注册、聚合容量、各模式派发与历史记录。
"""
from typing import Dict, List
from datetime import datetime, timezone
import threading
import logging

from .models import (
    ResourceType,
    DispatchMode,
    GridSignalType,
    GridSignal,
    StationStatus,
    ResourceCapability,
    DispatchPlan,
)
from .optimizer import VPPOptimizer, _make_plan_id

logger = logging.getLogger("vpp")


# ─── 多站点协同调度器 ───

class MultiStationCoordinator:
    """
    多站点协同调度器
    管理多个站点的VPP聚合调度
    """

    def __init__(self, optimizer: VPPOptimizer = None):
        self.optimizer = optimizer or VPPOptimizer()
        self.stations: Dict[str, StationStatus] = {}
        self.resources: Dict[str, ResourceCapability] = {}
        self.dispatch_history: List[DispatchPlan] = []
        self.peak_threshold_kw: float = 500.0  # 默认峰值阈值
        self._plan_counter = 0
        # 并发保护: stations/resources/dispatch_history 经单例被多端点并发访问
        self._lock = threading.RLock()

        logger.info("VPP多站点协同调度器初始化完成")

    def _safe_plan(self, mode: DispatchMode, trigger: str) -> DispatchPlan:
        """异常降级: 返回安全空计划(0功率), 保证调用方不崩溃"""
        logger.exception("调度执行异常降级[%s]: %s", mode.value, trigger)
        return DispatchPlan(
            plan_id=_make_plan_id("safe_"),
            mode=mode,
            trigger=f"异常降级: {trigger}",
            stations_involved=[],
            commands=[],
            total_dispatch_kw=0,
            estimated_revenue=0,
            estimated_cost=0,
            net_profit=0,
        )

    def register_station(self, station: StationStatus):
        """注册站点"""
        try:
            with self._lock:
                self.stations[station.station_id] = station
            logger.info("站点注册: %s (%s)", station.station_name, station.station_id)
        except Exception:
            logger.exception("站点注册异常: %s", station)

    def unregister_station(self, station_id: str):
        """注销站点"""
        try:
            with self._lock:
                if station_id in self.stations:
                    del self.stations[station_id]
                    logger.info("站点注销: %s", station_id)
        except Exception:
            logger.exception("站点注销异常: %s", station_id)

    def register_resource(self, resource: ResourceCapability):
        """注册资源"""
        try:
            with self._lock:
                self.resources[resource.resource_id] = resource
        except Exception:
            logger.exception("资源注册异常: %s", resource)

    def unregister_resource(self, resource_id: str):
        """注销资源"""
        try:
            with self._lock:
                if resource_id in self.resources:
                    del self.resources[resource_id]
        except Exception:
            logger.exception("资源注销异常: %s", resource_id)

    def clear_all(self):
        """持锁原子清空全部站点与资源

        供 /vpp/simulate 重载模拟数据使用: 避免调用方在锁外
        裸调 stations.clear()/resources.clear() 与调度循环并发
        (dict-changed-size / 半清空调度) 的竞态。
        """
        with self._lock:
            self.stations.clear()
            self.resources.clear()

    def update_station_status(self, station_id: str, **kwargs):
        """更新站点状态"""
        try:
            with self._lock:
                if station_id in self.stations:
                    station = self.stations[station_id]
                    for k, v in kwargs.items():
                        if hasattr(station, k):
                            setattr(station, k, v)
        except Exception:
            logger.exception("站点状态更新异常: %s", station_id)

    def update_resource_status(self, resource_id: str, **kwargs):
        """更新资源状态"""
        try:
            with self._lock:
                if resource_id in self.resources:
                    resource = self.resources[resource_id]
                    for k, v in kwargs.items():
                        if hasattr(resource, k):
                            setattr(resource, k, v)
        except Exception:
            logger.exception("资源状态更新异常: %s", resource_id)

    def get_aggregate_capacity(self) -> Dict:
        """获取VPP聚合容量"""
        try:
            with self._lock:
                online_stations = [s for s in self.stations.values() if s.online]
                all_resources = list(self.resources.values())
                total_stations = len(self.stations)

            total_pv_kw = sum(s.total_pv_kw for s in online_stations)
            total_battery_kwh = sum(s.total_battery_kwh for s in online_stations)
            total_ev_chargers = sum(s.total_ev_chargers for s in online_stations)
            total_load_kw = sum(s.current_load_kw for s in online_stations)
            total_pv_output = sum(s.current_pv_output_kw for s in online_stations)
            total_available = sum(s.available_dispatch_kw for s in online_stations)

            avg_soc = 0
            battery_resources = [r for r in all_resources
                                 if r.resource_type == ResourceType.BATTERY and r.soc is not None]
            if battery_resources:
                avg_soc = sum(r.soc for r in battery_resources) / len(battery_resources)

            return {
                'online_stations': len(online_stations),
                'total_stations': total_stations,
                'total_pv_kw': total_pv_kw,
                'total_battery_kwh': total_battery_kwh,
                'total_ev_chargers': total_ev_chargers,
                'current_load_kw': total_load_kw,
                'current_pv_output_kw': total_pv_output,
                'available_dispatch_kw': total_available,
                'avg_battery_soc': round(avg_soc, 3),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("聚合容量计算异常, 降级返回空容量")
            return {
                'online_stations': 0,
                'total_stations': 0,
                'total_pv_kw': 0,
                'total_battery_kwh': 0,
                'total_ev_chargers': 0,
                'current_load_kw': 0,
                'current_pv_output_kw': 0,
                'available_dispatch_kw': 0,
                'avg_battery_soc': 0,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

    def dispatch_economic(self) -> DispatchPlan:
        """执行经济调度"""
        try:
            with self._lock:
                stations = list(self.stations.values())
                resources = list(self.resources.values())
            plan = self.optimizer.optimize_economic_dispatch(stations, resources)
            self._record_plan(plan)
            return plan
        except Exception:
            return self._safe_plan(DispatchMode.ECONOMIC, "经济调度")

    def dispatch_peak_shaving(self, threshold_kw: float = None) -> DispatchPlan:
        """执行削峰填谷"""
        try:
            with self._lock:
                if threshold_kw:
                    self.peak_threshold_kw = threshold_kw
                stations = list(self.stations.values())
                resources = list(self.resources.values())
                threshold = self.peak_threshold_kw
            plan = self.optimizer.optimize_peak_shaving(stations, resources, threshold)
            self._record_plan(plan)
            return plan
        except Exception:
            return self._safe_plan(DispatchMode.PEAK_SHAVING, "削峰填谷")

    def dispatch_demand_response(self, signal: GridSignal) -> DispatchPlan:
        """执行需求响应"""
        try:
            with self._lock:
                stations = list(self.stations.values())
                resources = list(self.resources.values())
            plan = self.optimizer.handle_demand_response(stations, resources, signal)
            self._record_plan(plan)
            return plan
        except Exception:
            return self._safe_plan(DispatchMode.DEMAND_RESPONSE, "需求响应")

    def dispatch_multi_station(self, grid_signal: GridSignal = None) -> DispatchPlan:
        """执行多站点协同调度"""
        try:
            with self._lock:
                stations = list(self.stations.values())
                resources = list(self.resources.values())
            plan = self.optimizer.optimize_multi_station_coordination(stations, resources, grid_signal)
            self._record_plan(plan)
            return plan
        except Exception:
            return self._safe_plan(DispatchMode.GRID_SUPPORT, "多站点协同")

    def auto_dispatch(self, grid_signal: GridSignal = None) -> DispatchPlan:
        """
        自动调度决策
        根据当前状态自动选择最优调度模式
        """
        try:
            aggregate = self.get_aggregate_capacity()

            # 1. 有电网信号 → 需求响应
            if grid_signal and grid_signal.signal_type in (
                GridSignalType.DEMAND_RESPONSE,
                GridSignalType.EMERGENCY
            ):
                logger.info("⚡ 自动调度: 需求响应模式")
                return self.dispatch_demand_response(grid_signal)

            # 2. 负荷超阈值 → 削峰
            if aggregate['current_load_kw'] > self.peak_threshold_kw:
                logger.info("⚡ 自动调度: 削峰填谷模式")
                return self.dispatch_peak_shaving()

            # 3. 有电网调频信号 → 电网支撑
            if grid_signal and grid_signal.signal_type == GridSignalType.FREQUENCY_REGULATION:
                logger.info("⚡ 自动调度: 电网支撑模式")
                return self.dispatch_multi_station(grid_signal)

            # 4. 多站点 → 协同调度(含经济优化)
            if aggregate['online_stations'] > 1:
                logger.info("⚡ 自动调度: 多站点协同模式")
                return self.dispatch_multi_station(grid_signal)

            # 5. 单站点 → 经济调度
            logger.info("⚡ 自动调度: 经济调度模式")
            return self.dispatch_economic()
        except Exception:
            return self._safe_plan(DispatchMode.ECONOMIC, "自动调度")

    def _record_plan(self, plan: DispatchPlan):
        """记录调度计划"""
        with self._lock:
            self._plan_counter += 1
            self.dispatch_history.append(plan)

            # 只保留最近100条
            if len(self.dispatch_history) > 100:
                self.dispatch_history = self.dispatch_history[-100:]

        logger.info(
            f"调度计划: {plan.plan_id} | 模式: {plan.mode.value} | "
            f"调度功率: {plan.total_dispatch_kw:.1f}kW | "
            f"净利润: {plan.net_profit:.2f}元"
        )

    def get_dispatch_history(self, limit: int = 20) -> List[Dict]:
        """获取调度历史"""
        try:
            with self._lock:
                # limit<=0 不取记录: history[-0:] 会返回全部, history[-n:] 会错位,
                # 统一规整为空列表, 仅 limit>0 时返回最后 limit 条。
                if limit <= 0:
                    history = []
                else:
                    history = list(self.dispatch_history[-limit:])
            return [
                {
                    'plan_id': p.plan_id,
                    'mode': p.mode.value,
                    'trigger': p.trigger,
                    'stations_involved': p.stations_involved,
                    'total_dispatch_kw': round(p.total_dispatch_kw, 2),
                    'estimated_revenue': round(p.estimated_revenue, 2),
                    'estimated_cost': round(p.estimated_cost, 2),
                    'net_profit': round(p.net_profit, 2),
                    'commands_count': len(p.commands),
                    'created_at': p.created_at.isoformat(),
                    'executed': p.executed,
                }
                for p in reversed(history)
            ]
        except Exception:
            logger.exception("调度历史读取异常, 降级返回空列表")
            return []

    def simulate_station_data(self, count: int = 3) -> None:
        """模拟站点数据(用于演示和测试)"""
        import random

        station_configs = [
            {"name": "华东-上海虹桥站", "pv": 200, "battery": 500, "ev": 20},
            {"name": "华东-杭州西站", "pv": 150, "battery": 400, "ev": 16},
            {"name": "华东-南京南站", "pv": 180, "battery": 450, "ev": 18},
            {"name": "华南-深圳北站", "pv": 250, "battery": 600, "ev": 24},
            {"name": "华南-广州南站", "pv": 220, "battery": 550, "ev": 22},
        ]

        for i in range(min(count, len(station_configs))):
            cfg = station_configs[i]
            sid = f"ST-{i+1:03d}"

            pv_output = cfg["pv"] * random.uniform(0.3, 0.9)
            battery_soc = random.uniform(0.2, 0.9)
            load = random.uniform(50, 300)
            available = cfg["battery"] * battery_soc * 0.8

            station = StationStatus(
                station_id=sid,
                station_name=cfg["name"],
                total_pv_kw=cfg["pv"],
                total_battery_kwh=cfg["battery"],
                total_ev_chargers=cfg["ev"],
                current_load_kw=round(load, 1),
                current_pv_output_kw=round(pv_output, 1),
                current_battery_soc=round(battery_soc, 3),
                available_dispatch_kw=round(available, 1),
                online=True,
            )
            self.register_station(station)

            # 注册光伏资源
            self.register_resource(ResourceCapability(
                resource_id=f"{sid}-PV",
                resource_type=ResourceType.PV,
                station_id=sid,
                rated_power_kw=cfg["pv"],
                current_power_kw=round(pv_output, 1),
                available_power_kw=round(pv_output, 1),
                priority=5,
            ))

            # 注册储能资源
            self.register_resource(ResourceCapability(
                resource_id=f"{sid}-BAT",
                resource_type=ResourceType.BATTERY,
                station_id=sid,
                rated_power_kw=cfg["battery"] * 0.5,
                current_power_kw=0,
                available_power_kw=round(cfg["battery"] * 0.5 * battery_soc * 0.8, 1),
                soc=round(battery_soc, 3),
                efficiency=0.95,
                priority=2,
            ))

            # 注册充电桩
            ev_power = random.uniform(30, 120)
            self.register_resource(ResourceCapability(
                resource_id=f"{sid}-EV",
                resource_type=ResourceType.EV_CHARGER,
                station_id=sid,
                rated_power_kw=cfg["ev"] * 7,  # 7kW每桩
                current_power_kw=round(ev_power, 1),
                available_power_kw=round(ev_power * 0.5, 1),
                priority=3,
            ))

            # 注册可调负荷
            self.register_resource(ResourceCapability(
                resource_id=f"{sid}-LOAD",
                resource_type=ResourceType.LOAD,
                station_id=sid,
                rated_power_kw=50,
                current_power_kw=round(load * 0.3, 1),
                available_power_kw=round(load * 0.15, 1),
                priority=4,
            ))

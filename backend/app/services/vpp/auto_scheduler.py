"""
VPP自动调度后台任务
- 定时经济调度(峰谷套利)
- SOC监控告警
- 调度计划执行跟踪
- 日统计汇总
"""
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from .dispatch_optimizer import (
    get_vpp_coordinator, MultiStationCoordinator,
    DispatchMode,
)
from .lp_optimizer import get_vpp_lp_optimizer

logger = logging.getLogger("vpp.scheduler")


class VPPAutoScheduler:
    """VPP自动调度器"""

    def __init__(self, coordinator: Optional[MultiStationCoordinator] = None):
        self.coordinator = coordinator or get_vpp_coordinator()
        self.lp_optimizer = get_vpp_lp_optimizer()
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # 调度参数
        self.economic_dispatch_interval_sec = 900  # 经济调度间隔(15分钟)
        self.health_check_interval_sec = 60        # 健康检查间隔(1分钟)
        self.stats_interval_sec = 3600             # 统计间隔(1小时)
        self.soc_alert_threshold = 0.15            # SOC告警阈值
        self.peak_threshold_kw = 500               # 削峰阈值

        # 运行状态
        self.last_economic_dispatch: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None
        self.dispatch_count_today = 0
        self.total_revenue_today = 0.0
        self.total_cost_today = 0.0

    async def start(self):
        """启动自动调度"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("VPP自动调度器已启动")

    async def stop(self):
        """停止自动调度"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("VPP自动调度器已停止")

    async def _run_loop(self):
        """主循环"""
        while self._running:
            try:
                now = datetime.now(timezone.utc)

                # 1. 健康检查
                if (not self.last_health_check or
                    (now - self.last_health_check).total_seconds() >= self.health_check_interval_sec):
                    await self._health_check()
                    self.last_health_check = now

                # 2. 自动经济调度
                if (not self.last_economic_dispatch or
                    (now - self.last_economic_dispatch).total_seconds() >= self.economic_dispatch_interval_sec):
                    await self._auto_economic_dispatch()
                    self.last_economic_dispatch = now

                # 3. 日统计重置(零点)
                if now.hour == 0 and now.minute < 2 and self.dispatch_count_today > 0:
                    logger.info("日统计: 调度%d次, 收益%.2f元, 成本%.2f元",
                                self.dispatch_count_today, self.total_revenue_today, self.total_cost_today)
                    self.dispatch_count_today = 0
                    self.total_revenue_today = 0.0
                    self.total_cost_today = 0.0

            except Exception as e:
                logger.error("自动调度循环异常: %s", e, exc_info=True)

            await asyncio.sleep(30)  # 30秒检查一次

    async def _health_check(self):
        """健康检查 - SOC告警"""
        for station_id, station in self.coordinator.stations.items():
            if not station.online:
                continue
            if station.current_battery_soc < self.soc_alert_threshold:
                logger.warning(
                    f"⚠️ 站点 {station.station_name}({station_id}) "
                    f"SOC过低: {station.current_battery_soc:.1%}"
                )
            if station.current_battery_soc > 0.95:
                logger.warning(
                    f"⚠️ 站点 {station.station_name}({station_id}) "
                    f"SOC过高: {station.current_battery_soc:.1%}"
                )

    async def _auto_economic_dispatch(self):
        """自动经济调度"""
        stations = list(self.coordinator.stations.values())
        resources = list(self.coordinator.resources.values())

        if not stations or not resources:
            return

        # 检查是否需要削峰
        total_load = sum(s.current_load_kw for s in stations if s.online)
        if total_load > self.peak_threshold_kw:
            logger.info("⚡ 检测到负荷超阈值(%.0fkW > %dkW), 执行削峰调度", total_load, self.peak_threshold_kw)
            plan = self.lp_optimizer.optimize_dispatch(
                stations=stations,
                resources=resources,
                target_power_kw=total_load - self.peak_threshold_kw,
                duration_min=15,
                mode=DispatchMode.PEAK_SHAVING,
                peak_threshold_kw=self.peak_threshold_kw,
            )
        else:
            # 经济调度
            plan = self.lp_optimizer.optimize_dispatch(
                stations=stations,
                resources=resources,
                target_power_kw=0,  # 自动
                duration_min=15,
                mode=DispatchMode.ECONOMIC,
            )

        if plan and plan.commands:
            self.coordinator._record_plan(plan)
            self.dispatch_count_today += 1
            self.total_revenue_today += plan.estimated_revenue
            self.total_cost_today += plan.estimated_cost
            logger.info(
                f"✅ 自动调度完成: {plan.plan_id} | "
                f"模式={plan.mode.value} | "
                f"功率={plan.total_dispatch_kw:.0f}kW | "
                f"净利润={plan.net_profit:.2f}元"
            )

    def get_status(self) -> dict:
        """获取自动调度器状态"""
        return {
            "running": self._running,
            "last_economic_dispatch": self.last_economic_dispatch.isoformat() if self.last_economic_dispatch else None,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "dispatch_count_today": self.dispatch_count_today,
            "total_revenue_today": round(self.total_revenue_today, 2),
            "total_cost_today": round(self.total_cost_today, 2),
            "net_profit_today": round(self.total_revenue_today - self.total_cost_today, 2),
            "config": {
                "economic_dispatch_interval_sec": self.economic_dispatch_interval_sec,
                "health_check_interval_sec": self.health_check_interval_sec,
                "soc_alert_threshold": self.soc_alert_threshold,
                "peak_threshold_kw": self.peak_threshold_kw,
            },
        }


# ─── 单例 ───

_auto_scheduler: Optional[VPPAutoScheduler] = None
_lock = threading.Lock()


def get_vpp_auto_scheduler() -> VPPAutoScheduler:
    """获取VPP自动调度器单例(双重检查锁,线程安全)

    无锁的 check-then-set 在并发下会各自构造实例覆盖单例;
    双重检查锁保证全局只构造一次。
    """
    global _auto_scheduler
    if _auto_scheduler is None:
        with _lock:
            if _auto_scheduler is None:
                _auto_scheduler = VPPAutoScheduler()
    return _auto_scheduler

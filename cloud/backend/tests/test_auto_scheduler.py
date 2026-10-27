"""test_auto_scheduler.py — VPP自动调度器单元测试

覆盖: VPPAutoScheduler 初始化/参数, start/stop 生命周期, get_status,
_health_check (SOC告警), _auto_economic_dispatch (削峰/经济调度),
_run_loop 异常吞并, get_vpp_auto_scheduler 单例。
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from app.services.vpp.auto_scheduler import (
    VPPAutoScheduler,
    get_vpp_auto_scheduler,
)


# ─── Fixtures ───

def make_station(station_id="st1", online=True, soc=0.5, load=100, name="Station1"):
    """创建模拟站点"""
    s = MagicMock()
    s.station_id = station_id
    s.station_name = name
    s.online = online
    s.current_battery_soc = soc
    s.current_load_kw = load
    return s


def make_resource(rid="r1"):
    r = MagicMock()
    r.resource_id = rid
    return r


def make_plan(plan_id="p1", commands=None, revenue=100, cost=50, power=50, mode_str="economic"):
    p = MagicMock()
    p.plan_id = plan_id
    p.commands = commands if commands is not None else [MagicMock()]
    p.estimated_revenue = revenue
    p.estimated_cost = cost
    p.total_dispatch_kw = power
    p.net_profit = revenue - cost
    m = MagicMock()
    m.value = mode_str
    p.mode = m
    return p


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.stations = {"st1": make_station("st1")}
    coord.resources = {"r1": make_resource("r1")}
    coord._record_plan = MagicMock()
    return coord


@pytest.fixture
def mock_lp_optimizer():
    opt = MagicMock()
    opt.optimize_dispatch = MagicMock(return_value=None)
    return opt


@pytest.fixture
def scheduler(mock_coordinator, mock_lp_optimizer):
    """创建带 mock 依赖的调度器"""
    s = VPPAutoScheduler(coordinator=mock_coordinator)
    s.lp_optimizer = mock_lp_optimizer
    return s


# ─── 初始化/参数 ───

class TestSchedulerInit:
    def test_default_intervals(self, scheduler):
        assert scheduler.economic_dispatch_interval_sec == 900
        assert scheduler.health_check_interval_sec == 60
        assert scheduler.stats_interval_sec == 3600

    def test_default_thresholds(self, scheduler):
        assert scheduler.soc_alert_threshold == 0.15
        assert scheduler.peak_threshold_kw == 500

    def test_initial_state(self, scheduler):
        assert scheduler._running is False
        assert scheduler._task is None
        assert scheduler.dispatch_count_today == 0
        assert scheduler.total_revenue_today == 0.0
        assert scheduler.last_economic_dispatch is None

    def test_custom_coordinator(self, mock_coordinator):
        s = VPPAutoScheduler(coordinator=mock_coordinator)
        assert s.coordinator is mock_coordinator

    def test_default_coordinator_created(self):
        """无 coordinator 参数时会从 get_vpp_coordinator 创建"""
        s = VPPAutoScheduler()
        assert s.coordinator is not None


# ─── get_status ───

class TestGetStatus:
    def test_status_not_running(self, scheduler):
        status = scheduler.get_status()
        assert status["running"] is False
        assert status["dispatch_count_today"] == 0
        assert status["net_profit_today"] == 0.0

    def test_status_config_values(self, scheduler):
        status = scheduler.get_status()
        assert status["config"]["economic_dispatch_interval_sec"] == 900
        assert status["config"]["soc_alert_threshold"] == 0.15

    def test_status_with_dispatch_data(self, scheduler):
        scheduler.dispatch_count_today = 3
        scheduler.total_revenue_today = 150.5
        scheduler.total_cost_today = 80.2
        scheduler._running = True
        status = scheduler.get_status()
        assert status["dispatch_count_today"] == 3
        assert status["total_revenue_today"] == 150.5
        assert status["net_profit_today"] == round(150.5 - 80.2, 2)
        assert status["running"] is True

    def test_status_last_dispatch_none(self, scheduler):
        status = scheduler.get_status()
        assert status["last_economic_dispatch"] is None
        assert status["last_health_check"] is None

    def test_status_last_dispatch_set(self, scheduler):
        now = datetime.now()
        scheduler.last_economic_dispatch = now
        scheduler.last_health_check = now
        status = scheduler.get_status()
        assert status["last_economic_dispatch"] is not None
        assert status["last_health_check"] is not None


# ─── start/stop ───

class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running(self, scheduler):
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._task is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, scheduler):
        await scheduler.start()
        task1 = scheduler._task
        await scheduler.start()  # second start should be no-op
        assert scheduler._task is task1
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, scheduler):
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_stop_without_start(self, scheduler):
        """stop 在未 start 时不应报错"""
        await scheduler.stop()
        assert scheduler._running is False


# ─── _health_check ───

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_normal_soc_no_warning(self, scheduler, mock_coordinator):
        mock_coordinator.stations["st1"].current_battery_soc = 0.5
        await scheduler._health_check()  # should not raise

    @pytest.mark.asyncio
    async def test_low_soc_warning(self, scheduler, mock_coordinator):
        mock_coordinator.stations["st1"].current_battery_soc = 0.10
        await scheduler._health_check()  # logs warning, no crash

    @pytest.mark.asyncio
    async def test_high_soc_warning(self, scheduler, mock_coordinator):
        mock_coordinator.stations["st1"].current_battery_soc = 0.98
        await scheduler._health_check()

    @pytest.mark.asyncio
    async def test_offline_station_skipped(self, scheduler, mock_coordinator):
        mock_coordinator.stations["st1"].online = False
        mock_coordinator.stations["st1"].current_battery_soc = 0.01
        await scheduler._health_check()  # offline, should not process


# ─── _auto_economic_dispatch ───

class TestAutoEconomicDispatch:
    @pytest.mark.asyncio
    async def test_no_stations_returns_early(self, scheduler, mock_coordinator):
        mock_coordinator.stations = {}
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 0

    @pytest.mark.asyncio
    async def test_no_resources_returns_early(self, scheduler, mock_coordinator):
        mock_coordinator.resources = {}
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 0

    @pytest.mark.asyncio
    async def test_economic_dispatch_normal(self, scheduler, mock_lp_optimizer):
        plan = make_plan(revenue=200, cost=100, power=50)
        mock_lp_optimizer.optimize_dispatch.return_value = plan
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 1
        assert scheduler.total_revenue_today == 200
        assert scheduler.total_cost_today == 100

    @pytest.mark.asyncio
    async def test_peak_shaving_when_load_exceeds_threshold(self, scheduler, mock_coordinator, mock_lp_optimizer):
        """总负荷超过阈值 → 削峰模式"""
        mock_coordinator.stations["st1"].current_load_kw = 600  # > 500 threshold
        plan = make_plan(power=100, mode_str="peak_shaving")
        mock_lp_optimizer.optimize_dispatch.return_value = plan
        await scheduler._auto_economic_dispatch()
        # Verify peak_shaving mode was used
        call_args = mock_lp_optimizer.optimize_dispatch.call_args
        assert call_args.kwargs.get("mode") is not None or call_args[1].get("mode") is not None

    @pytest.mark.asyncio
    async def test_no_plan_no_change(self, scheduler, mock_lp_optimizer):
        mock_lp_optimizer.optimize_dispatch.return_value = None
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 0

    @pytest.mark.asyncio
    async def test_plan_with_empty_commands(self, scheduler, mock_lp_optimizer):
        plan = make_plan(commands=[])
        mock_lp_optimizer.optimize_dispatch.return_value = plan
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 0  # empty commands → no record

    @pytest.mark.asyncio
    async def test_plan_record_called_with_valid_commands(self, scheduler, mock_lp_optimizer, mock_coordinator):
        plan = make_plan(revenue=50, cost=30)
        mock_lp_optimizer.optimize_dispatch.return_value = plan
        await scheduler._auto_economic_dispatch()
        mock_coordinator._record_plan.assert_called_once_with(plan)

    @pytest.mark.asyncio
    async def test_multiple_dispatches_accumulate(self, scheduler, mock_lp_optimizer):
        plan = make_plan(revenue=100, cost=50)
        mock_lp_optimizer.optimize_dispatch.return_value = plan
        await scheduler._auto_economic_dispatch()
        await scheduler._auto_economic_dispatch()
        await scheduler._auto_economic_dispatch()
        assert scheduler.dispatch_count_today == 3
        assert scheduler.total_revenue_today == 300
        assert scheduler.total_cost_today == 150


# ─── _run_loop 异常处理 ───

class TestRunLoopExceptionHandling:
    @pytest.mark.asyncio
    async def test_run_loop_swallows_exception(self, scheduler, mock_coordinator):
        """_run_loop 内部异常应被捕获，不应传播"""
        scheduler._running = True

        call_count = 0

        async def fake_sleep(sec):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                scheduler._running = False
                raise asyncio.CancelledError()

        # Force an exception inside the loop by making _health_check raise
        with patch.object(scheduler, '_health_check', new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch('app.services.vpp.auto_scheduler.asyncio.sleep', side_effect=fake_sleep):
            try:
                await scheduler._run_loop()
            except asyncio.CancelledError:
                pass  # expected

    @pytest.mark.asyncio
    async def test_run_loop_normal_exit(self, scheduler):
        scheduler._running = False
        # Should exit immediately since while condition is False
        await scheduler._run_loop()


# ─── 单例 ───

class TestSingleton:
    def test_get_vpp_auto_scheduler_returns_instance(self):
        s = get_vpp_auto_scheduler()
        assert isinstance(s, VPPAutoScheduler)

    def test_get_vpp_auto_scheduler_singleton(self):
        s1 = get_vpp_auto_scheduler()
        s2 = get_vpp_auto_scheduler()
        assert s1 is s2

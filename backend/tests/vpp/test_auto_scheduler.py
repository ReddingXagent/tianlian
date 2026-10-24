"""
VPPAutoScheduler 单元测试 (tests/vpp/test_auto_scheduler.py)

被测文件: app/services/vpp/auto_scheduler.py (190行, 原零测试)
聚焦:
- start/stop 生命周期 (重复 start 不重建 task)
- _run_loop 主循环 (间隔控制 + 三段检查按序执行 + 异常容错不崩溃)
- _health_check SOC 低/高告警 (阈值边界 + offline 跳过)
- _auto_economic_dispatch 经济调度路径 / 削峰路径 / 空资源跳过
- 调度统计累加 (dispatch_count_today / total_revenue_today / total_cost_today)
- get_status 返回结构
- get_vpp_auto_scheduler 线程安全单例 (双重检查锁)

设计要点:
- coordinator 与 lp_optimizer 用 MagicMock 注入构造函数, 避开真实 DB / 算法依赖
- 站点 / 资源 / plan 用真实 dataclass (StationStatus / ResourceCapability / DispatchPlan)
  作为 mock 数据, 比纯 Mock 更贴近真实属性访问语义
- _run_loop 是无限循环, 测试通过缩短 interval + patch asyncio.sleep 控制迭代次数
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.vpp.auto_scheduler import (
    VPPAutoScheduler,
    get_vpp_auto_scheduler,
)
from app.services.vpp.dispatch_optimizer import (
    DispatchMode,
    DispatchPlan,
    ResourceCapability,
    ResourceType,
    StationStatus,
)


# ─── 工厂 ───

def _station(sid="ST-1", *, name=None, soc=0.6, load=100.0, online=True):
    """真实 StationStatus, 字段与 auto_scheduler 访问的属性一一对应。"""
    return StationStatus(
        station_id=sid,
        station_name=name or f"N-{sid}",
        total_pv_kw=200.0,
        total_battery_kwh=500.0,
        total_ev_chargers=20,
        current_load_kw=load,
        current_pv_output_kw=80.0,
        current_battery_soc=soc,
        available_dispatch_kw=200.0,
        online=online,
    )


def _resource(rid="R-1"):
    return ResourceCapability(
        resource_id=rid,
        resource_type=ResourceType.BATTERY,
        station_id="ST-1",
        rated_power_kw=100.0,
        current_power_kw=0.0,
        available_power_kw=100.0,
        soc=0.6,
    )


def _plan(pid="plan-1", mode=DispatchMode.ECONOMIC, *, revenue=200.0, cost=80.0,
          dispatch=50.0, with_commands=True):
    """最小可用 DispatchPlan。with_commands=False 模拟空指令被跳过。"""
    from app.services.vpp.dispatch_optimizer import DispatchCommand
    commands = []
    if with_commands:
        commands.append(DispatchCommand(
            resource_id="R-1", station_id="ST-1",
            resource_type=ResourceType.BATTERY,
            target_power_kw=dispatch, duration_min=15, priority=2,
            estimated_revenue=revenue, estimated_cost=cost,
        ))
    return DispatchPlan(
        plan_id=pid, mode=mode, trigger="auto",
        stations_involved=["ST-1"], commands=commands,
        total_dispatch_kw=dispatch,
        estimated_revenue=revenue, estimated_cost=cost,
        net_profit=round(revenue - cost, 2),
    )


def _make_scheduler(*, stations=None, resources=None, plan=None, peak_kw=500):
    """构造一个注入了 mock 依赖的 VPPAutoScheduler。

    绕过 __init__ 里的工厂函数, 直接 patch 实例属性, 隔离单例与真实 coordinator。
    """
    coordinator = MagicMock()
    coordinator.stations = {s.station_id: s for s in (stations or [])}
    coordinator.resources = {r.resource_id: r for r in (resources or [])}
    coordinator._record_plan = MagicMock()

    lp_optimizer = MagicMock()
    # 默认返回非空 plan; 调用方可覆盖 side_effect / return_value
    lp_optimizer.optimize_dispatch.return_value = plan if plan is not None else _plan()

    sched = VPPAutoScheduler.__new__(VPPAutoScheduler)  # 跳过 __init__ 的工厂调用
    sched.coordinator = coordinator
    sched.lp_optimizer = lp_optimizer
    sched._task = None
    sched._running = False
    sched.economic_dispatch_interval_sec = 900
    sched.health_check_interval_sec = 60
    sched.stats_interval_sec = 3600
    sched.soc_alert_threshold = 0.15
    sched.peak_threshold_kw = peak_kw
    sched.last_economic_dispatch = None
    sched.last_health_check = None
    sched.dispatch_count_today = 0
    sched.total_revenue_today = 0.0
    sched.total_cost_today = 0.0
    return sched


# ─── 生命周期: start / stop ───

class TestLifecycle:
    """start/stop 与 task 管理。"""

    async def test_start_sets_running_and_creates_task(self):
        sched = _make_scheduler()
        with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=AsyncMockSleep()):
            await sched.start()

        assert sched._running is True
        assert sched._task is not None
        assert not sched._task.done()

        await sched.stop()

    async def test_start_idempotent_no_second_task(self):
        """重复 start 不创建第二个 task (铁律: _running 守卫)。"""
        sched = _make_scheduler()
        with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=AsyncMockSleep()):
            await sched.start()
            first_task = sched._task
            await sched.start()  # 重复启动

        assert sched._task is first_task  # 同一对象, 未重建

        await sched.stop()

    async def test_stop_resets_running_and_cancels_task(self):
        sched = _make_scheduler()
        with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=AsyncMockSleep()):
            await sched.start()
            task = sched._task
            await sched.stop()

        assert sched._running is False
        assert task.cancelled() or task.done()

    async def test_stop_without_start_is_noop(self):
        """未启动直接 stop 不报错。"""
        sched = _make_scheduler()
        await sched.stop()  # _task is None
        assert sched._running is False


# ─── _health_check: SOC 告警 ───

class TestHealthCheck:
    async def test_low_soc_triggers_warning(self, caplog):
        """SOC < 0.15 触发低告警。"""
        sched = _make_scheduler(stations=[_station("ST-1", soc=0.10)])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        assert any("SOC过低" in r.message for r in caplog.records)

    async def test_high_soc_triggers_warning(self, caplog):
        """SOC > 0.95 触发高告警。"""
        sched = _make_scheduler(stations=[_station("ST-1", soc=0.98)])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        assert any("SOC过高" in r.message for r in caplog.records)

    async def test_normal_soc_no_warning(self, caplog):
        sched = _make_scheduler(stations=[_station("ST-1", soc=0.50)])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        assert not any("SOC" in r.message for r in caplog.records)

    async def test_offline_station_skipped(self, caplog):
        """offline 站点不参与检查 (即使 SOC 极端)。"""
        sched = _make_scheduler(stations=[_station("ST-1", soc=0.01, online=False)])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        assert not any("SOC" in r.message for r in caplog.records)

    async def test_low_soc_threshold_boundary_excluded(self, caplog):
        """阈值边界 SOC==0.15 不告警 (严格 <)。"""
        sched = _make_scheduler(stations=[_station("ST-1", soc=0.15)])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        assert not any("SOC过低" in r.message for r in caplog.records)

    async def test_empty_stations_no_error(self):
        """空站点字典不抛错。"""
        sched = _make_scheduler(stations=[])
        await sched._health_check()  # 不抛即通过

    async def test_multiple_stations_independent(self, caplog):
        sched = _make_scheduler(stations=[
            _station("ST-A", soc=0.10),   # 低告警
            _station("ST-B", soc=0.50),   # 正常
            _station("ST-C", soc=0.98),   # 高告警
        ])
        with caplog.at_level("WARNING", logger="vpp.scheduler"):
            await sched._health_check()

        msgs = " ".join(r.message for r in caplog.records)
        assert "ST-A" in msgs
        assert "ST-C" in msgs
        assert "ST-B" not in msgs


# ─── _auto_economic_dispatch: 经济调度 / 削峰 / 空资源 ───

class TestEconomicDispatch:
    async def test_economic_path_when_load_below_peak(self):
        """负荷 < peak_threshold 走经济调度 (target=0, ECONOMIC)。"""
        sched = _make_scheduler(
            stations=[_station("ST-1", load=100.0)],
            resources=[_resource()],
            plan=_plan(mode=DispatchMode.ECONOMIC, revenue=200.0, cost=80.0),
            peak_kw=500,
        )

        await sched._auto_economic_dispatch()

        call = sched.lp_optimizer.optimize_dispatch.call_args
        assert call.kwargs["mode"] == DispatchMode.ECONOMIC
        assert call.kwargs["target_power_kw"] == 0
        sched.coordinator._record_plan.assert_called_once()
        assert sched.dispatch_count_today == 1
        assert sched.total_revenue_today == pytest.approx(200.0)
        assert sched.total_cost_today == pytest.approx(80.0)

    async def test_peak_shaving_path_when_load_exceeds_threshold(self):
        """负荷 > peak_threshold 走削峰 (target=load-peak, PEAK_SHAVING)。"""
        sched = _make_scheduler(
            stations=[_station("ST-1", load=700.0)],
            resources=[_resource()],
            plan=_plan(mode=DispatchMode.PEAK_SHAVING, revenue=300.0, cost=50.0),
            peak_kw=500,
        )

        await sched._auto_economic_dispatch()

        call = sched.lp_optimizer.optimize_dispatch.call_args
        assert call.kwargs["mode"] == DispatchMode.PEAK_SHAVING
        assert call.kwargs["target_power_kw"] == pytest.approx(200.0)  # 700 - 500
        assert call.kwargs["peak_threshold_kw"] == 500
        sched.coordinator._record_plan.assert_called_once()
        assert sched.dispatch_count_today == 1

    async def test_peak_boundary_not_triggered(self):
        """负荷 == peak_threshold 不削峰 (严格 >), 走经济调度。"""
        sched = _make_scheduler(
            stations=[_station("ST-1", load=500.0)],
            resources=[_resource()],
            peak_kw=500,
        )
        await sched._auto_economic_dispatch()

        assert sched.lp_optimizer.optimize_dispatch.call_args.kwargs["mode"] == DispatchMode.ECONOMIC

    async def test_skip_when_no_resources(self):
        """空资源跳过, 不调用 optimizer。"""
        sched = _make_scheduler(stations=[_station()], resources=[])
        await sched._auto_economic_dispatch()
        sched.lp_optimizer.optimize_dispatch.assert_not_called()
        assert sched.dispatch_count_today == 0

    async def test_skip_when_no_stations(self):
        """空站点跳过。"""
        sched = _make_scheduler(stations=[], resources=[_resource()])
        await sched._auto_economic_dispatch()
        sched.lp_optimizer.optimize_dispatch.assert_not_called()

    async def test_skip_when_both_empty(self):
        sched = _make_scheduler(stations=[], resources=[])
        await sched._auto_economic_dispatch()
        sched.lp_optimizer.optimize_dispatch.assert_not_called()

    async def test_empty_commands_not_recorded(self):
        """plan 返回但 commands 为空 → 不记录、不累加统计。"""
        sched = _make_scheduler(
            stations=[_station()],
            resources=[_resource()],
            plan=_plan(with_commands=False),
        )
        await sched._auto_economic_dispatch()

        sched.coordinator._record_plan.assert_not_called()
        assert sched.dispatch_count_today == 0
        assert sched.total_revenue_today == 0.0

    async def test_none_plan_not_recorded(self):
        """optimizer 返回 None → 不记录。"""
        sched = _make_scheduler(stations=[_station()], resources=[_resource()])
        sched.lp_optimizer.optimize_dispatch.return_value = None
        await sched._auto_economic_dispatch()

        sched.coordinator._record_plan.assert_not_called()
        assert sched.dispatch_count_today == 0

    async def test_stats_accumulate_across_dispatches(self):
        """多次调度统计累加 (dispatch_count / revenue / cost)。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
            plan=_plan(revenue=100.0, cost=40.0),
        )
        await sched._auto_economic_dispatch()
        await sched._auto_economic_dispatch()
        await sched._auto_economic_dispatch()

        assert sched.dispatch_count_today == 3
        assert sched.total_revenue_today == pytest.approx(300.0)
        assert sched.total_cost_today == pytest.approx(120.0)

    async def test_total_load_excludes_offline(self):
        """total_load 仅累加 online 站点 (offline 负荷不计入削峰判断)。"""
        sched = _make_scheduler(
            stations=[
                _station("ST-1", load=300.0, online=True),
                _station("ST-2", load=300.0, online=False),  # offline 不算
            ],
            resources=[_resource()],
            peak_kw=500,
        )
        await sched._auto_economic_dispatch()

        # online 总负荷 = 300 < 500 → 经济调度
        assert sched.lp_optimizer.optimize_dispatch.call_args.kwargs["mode"] == DispatchMode.ECONOMIC


# ─── get_status ───

class TestGetStatus:
    def test_structure_and_defaults(self):
        sched = _make_scheduler()
        status = sched.get_status()

        assert set(status.keys()) == {
            "running", "last_economic_dispatch", "last_health_check",
            "dispatch_count_today", "total_revenue_today", "total_cost_today",
            "net_profit_today", "config",
        }
        assert status["running"] is False
        assert status["last_economic_dispatch"] is None
        assert status["last_health_check"] is None
        assert status["dispatch_count_today"] == 0
        assert status["total_revenue_today"] == 0.0
        assert status["total_cost_today"] == 0.0
        assert status["net_profit_today"] == 0.0

    def test_config_block(self):
        sched = _make_scheduler()
        cfg = sched.get_status()["config"]
        assert cfg["economic_dispatch_interval_sec"] == 900
        assert cfg["health_check_interval_sec"] == 60
        assert cfg["soc_alert_threshold"] == 0.15
        assert cfg["peak_threshold_kw"] == 500

    def test_net_profit_reflects_revenue_minus_cost(self):
        sched = _make_scheduler()
        sched.dispatch_count_today = 2
        sched.total_revenue_today = 250.0
        sched.total_cost_today = 90.0
        status = sched.get_status()

        assert status["dispatch_count_today"] == 2
        assert status["net_profit_today"] == pytest.approx(160.0)

    def test_last_dispatch_isoformat(self):
        sched = _make_scheduler()
        ts = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
        sched.last_economic_dispatch = ts
        sched.last_health_check = ts
        status = sched.get_status()

        assert status["last_economic_dispatch"] == ts.isoformat()
        assert status["last_health_check"] == ts.isoformat()


# ─── _run_loop: 主循环 ───

class TestRunLoop:
    async def test_loop_executes_checks_in_order_then_sleeps(self):
        """首轮循环: health_check → economic_dispatch 按序执行, 然后 sleep。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        call_order = []

        async def spy_health():
            call_order.append("health")
        async def spy_dispatch():
            call_order.append("dispatch")

        sched._health_check = spy_health
        sched._auto_economic_dispatch = spy_dispatch
        sched._running = True  # _run_loop 守卫: 进入循环体需先置 True

        # 首轮后立刻置 _running=False, sleep 让出一次即停
        async def fake_sleep(seconds):
            call_order.append(f"sleep:{seconds}")
            sched._running = False
        with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
            await sched._run_loop()

        assert call_order == ["health", "dispatch", "sleep:30"]

    async def test_loop_respects_health_interval_skips_second_health(self):
        """第二轮: health 间隔未到跳过 health_check, dispatch 间隔未到也跳过。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        sched.health_check_interval_sec = 60
        sched.economic_dispatch_interval_sec = 900

        call_count = {"health": 0, "dispatch": 0}
        orig_health = sched._health_check
        orig_dispatch = sched._auto_economic_dispatch

        async def counting_health():
            call_count["health"] += 1
        async def counting_dispatch():
            call_count["dispatch"] += 1

        sched._health_check = counting_health
        sched._auto_economic_dispatch = counting_dispatch
        sched._running = True  # 进入循环体

        iterations = {"n": 0}

        async def fake_sleep(seconds):
            iterations["n"] += 1
            if iterations["n"] >= 2:
                sched._running = False
        with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
            await sched._run_loop()

        # 两轮循环: 首轮各执行一次, 第二轮因间隔未到都不执行
        assert call_count["health"] == 1
        assert call_count["dispatch"] == 1

    async def test_loop_tolerates_coordinator_exception(self, caplog):
        """health_check 抛异常不崩溃, 循环继续。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        ran_after_error = {"v": False}

        async def boom_health():
            raise RuntimeError("coordinator exploded")
        async def ok_dispatch():
            ran_after_error["v"] = True

        sched._health_check = boom_health
        sched._auto_economic_dispatch = ok_dispatch
        sched._running = True  # 进入循环体

        async def fake_sleep(seconds):
            sched._running = False
        with caplog.at_level("ERROR", logger="vpp.scheduler"):
            with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
                await sched._run_loop()

        # 异常被 catch, 错误日志记录, 且 _running 仍允许循环结构正常退出
        assert any("自动调度循环异常" in r.message for r in caplog.records)
        # 注: health 先抛, dispatch 在同一 try 块内本次未执行; 关键是循环未崩溃退出

    async def test_loop_runs_dispatch_after_health_recovers(self, caplog):
        """首轮 health 抛错被吞, 第二轮 health 恢复后 dispatch 正常执行。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        state = {"health_calls": 0}
        dispatch_called = {"v": False}

        async def flaky_health():
            state["health_calls"] += 1
            if state["health_calls"] == 1:
                raise RuntimeError("first boom")
        async def ok_dispatch():
            dispatch_called["v"] = True

        sched._health_check = flaky_health
        sched._auto_economic_dispatch = ok_dispatch
        sched._running = True  # 进入循环体
        # 让两轮间隔都满足 (重置 last_* 让第二轮重新触发)
        sched.health_check_interval_sec = 0
        sched.economic_dispatch_interval_sec = 0

        iterations = {"n": 0}

        async def fake_sleep(seconds):
            iterations["n"] += 1
            if iterations["n"] >= 2:
                sched._running = False
        with caplog.at_level("ERROR", logger="vpp.scheduler"):
            with patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
                await sched._run_loop()

        # 首轮 health 抛 → dispatch 未跑; 第二轮 health 成功 → dispatch 跑
        assert state["health_calls"] == 2
        assert dispatch_called["v"] is True

    async def test_loop_daily_reset_at_midnight(self, caplog):
        """零点窗口 (hour==0 and minute<2) 且当日有调度 → 统计重置。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        sched.dispatch_count_today = 5
        sched.total_revenue_today = 1000.0
        sched.total_cost_today = 300.0

        midnight = datetime(2026, 8, 10, 0, 1, tzinfo=timezone.utc)

        async def fake_health():
            pass
        async def fake_dispatch():
            pass
        sched._health_check = fake_health
        sched._auto_economic_dispatch = fake_dispatch
        sched._running = True  # 进入循环体

        async def fake_sleep(seconds):
            sched._running = False
        with patch("app.services.vpp.auto_scheduler.datetime") as dt_mock, \
             patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
            dt_mock.now.return_value = midnight
            dt_mock.side_effect = lambda *a, **k: datetime(*a, **k)
            with caplog.at_level("INFO", logger="vpp.scheduler"):
                await sched._run_loop()

        assert sched.dispatch_count_today == 0
        assert sched.total_revenue_today == 0.0
        assert sched.total_cost_today == 0.0
        assert any("日统计" in r.message for r in caplog.records)

    async def test_loop_no_reset_when_no_dispatch_today(self):
        """零点但当日无调度 (dispatch_count==0) → 不重置日志, 数值本就为 0。"""
        sched = _make_scheduler(
            stations=[_station(load=100.0)],
            resources=[_resource()],
        )
        midnight = datetime(2026, 8, 10, 0, 1, tzinfo=timezone.utc)

        async def fake_health():
            pass
        async def fake_dispatch():
            pass
        sched._health_check = fake_health
        sched._auto_economic_dispatch = fake_dispatch
        sched._running = True  # 进入循环体

        async def fake_sleep(seconds):
            sched._running = False
        with patch("app.services.vpp.auto_scheduler.datetime") as dt_mock, \
             patch("app.services.vpp.auto_scheduler.asyncio.sleep", new=fake_sleep):
            dt_mock.now.return_value = midnight
            dt_mock.side_effect = lambda *a, **k: datetime(*a, **k)
            await sched._run_loop()

        assert sched.dispatch_count_today == 0  # 未触发重置分支, 数值保持


# ─── 单例: get_vpp_auto_scheduler ───

class TestSingleton:
    def test_returns_same_instance(self):
        """连续调用返回同一实例。"""
        with patch("app.services.vpp.auto_scheduler.get_vpp_coordinator") as gc, \
             patch("app.services.vpp.auto_scheduler.get_vpp_lp_optimizer") as gl:
            gc.return_value = MagicMock()
            gl.return_value = MagicMock()
            a = get_vpp_auto_scheduler()
            b = get_vpp_auto_scheduler()
        assert a is b

    def test_double_checked_lock_constructs_once(self):
        """双重检查锁: 并发下只构造一次 (全局单例)。"""
        import threading
        constructed = {"n": 0}
        original_init = VPPAutoScheduler.__init__

        def counting_init(self, *a, **k):
            constructed["n"] += 1
            original_init(self, *a, **k)

        # 重置模块级单例, 隔离测试
        with patch("app.services.vpp.auto_scheduler._auto_scheduler", None), \
             patch("app.services.vpp.auto_scheduler.get_vpp_coordinator") as gc, \
             patch("app.services.vpp.auto_scheduler.get_vpp_lp_optimizer") as gl, \
             patch.object(VPPAutoScheduler, "__init__", counting_init):
            gc.return_value = MagicMock()
            gl.return_value = MagicMock()

            results = []
            def worker():
                results.append(get_vpp_auto_scheduler())

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert constructed["n"] == 1  # 仅构造一次
        assert all(r is results[0] for r in results)  # 全部同一实例


# ─── 辅助 ───

class AsyncMockSleep:
    """可复用的 noop async sleep (避免循环真实挂起)。"""
    async def __call__(self, seconds):
        return None

"""
VPPOptimizer 单元测试 (tests/vpp/dispatch_optimizer/test_optimizer.py)

被测文件: app/services/vpp/dispatch_optimizer/optimizer.py (768行, 原零测试)
聚焦:
- 模块工具函数: _make_plan_id / _get_pricing_tz / _pricing_hour
- get_current_price 四时段映射 + price_multiplier + 异常降级
- 经济调度 optimize_economic_dispatch: 峰谷套利分支(充/放/不动作) + 异常降级
- 削峰 optimize_peak_shaving: 阈值非法/负荷正常/储能放电优先/负荷削减/SOC太低跳过
- 需求响应 handle_demand_response: target/duration/reward 兜底 + 三级资源 + 响应率
- 多站协调 optimize_multi_station_coordination: 站间互济(BUG1实际扣减) + grid_signal + 高低价时段
- 单资源优化 _optimize_single_resource/_optimize_battery/_optimize_ev_charger/_optimize_load
- 配置覆盖 _battery_discharge_soc_floor / _ev_curtail_ratio
- 异常降级 _safe_default_plan 路径

设计要点:
- VPPOptimizer 是纯算法类, 构造无 DB/网络依赖, 直接实例化, 无需 mock 外部 IO
- 峰谷判断依赖系统时钟(_pricing_hour 取 datetime.now(tz)), 测试通过:
  (a) 显式 hour 参数驱动 get_current_price / _optimize_single_resource 等纯函数分支;
  (b) patch optimizer._pricing_hour 固定时段, 驱动依赖当前时段的整链路(经济/多站协调);
  (c) aware datetime 注入 _pricing_hour(now=...) 验证时区换算。
- 不修改 optimizer.py 本身, 仅验证既有行为(含 BUG1-4 已修复的契约)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.vpp.dispatch_optimizer import optimizer as opt_mod
from app.services.vpp.dispatch_optimizer.models import (
    DispatchCommand,
    DispatchMode,
    DispatchPlan,
    GridSignal,
    GridSignalType,
    ResourceCapability,
    ResourceType,
    StationStatus,
)
from app.services.vpp.dispatch_optimizer.optimizer import (
    VPPOptimizer,
    _get_pricing_tz,
    _make_plan_id,
    _pricing_hour,
)


# ─── 工厂 ───

def _station(
    sid: str = "ST-1",
    *,
    name: Optional[str] = None,
    load: float = 100.0,
    pv_output: float = 80.0,
    dispatch_kw: float = 200.0,
    soc: float = 0.6,
    online: bool = True,
) -> StationStatus:
    return StationStatus(
        station_id=sid,
        station_name=name or f"N-{sid}",
        total_pv_kw=200.0,
        total_battery_kwh=500.0,
        total_ev_chargers=20,
        current_load_kw=load,
        current_pv_output_kw=pv_output,
        current_battery_soc=soc,
        available_dispatch_kw=dispatch_kw,
        online=online,
    )


def _battery(
    rid: str = "BAT-1",
    *,
    station_id: str = "ST-1",
    rated: float = 100.0,
    available: float = 100.0,
    soc: Optional[float] = 0.6,
    priority: int = 5,
) -> ResourceCapability:
    return ResourceCapability(
        resource_id=rid,
        resource_type=ResourceType.BATTERY,
        station_id=station_id,
        rated_power_kw=rated,
        current_power_kw=0.0,
        available_power_kw=available,
        soc=soc,
        priority=priority,
    )


def _ev(
    rid: str = "EV-1",
    *,
    station_id: str = "ST-1",
    current_power: float = 50.0,
    available: float = 50.0,
    priority: int = 5,
) -> ResourceCapability:
    return ResourceCapability(
        resource_id=rid,
        resource_type=ResourceType.EV_CHARGER,
        station_id=station_id,
        rated_power_kw=120.0,
        current_power_kw=current_power,
        available_power_kw=available,
        priority=priority,
    )


def _load(
    rid: str = "LOAD-1",
    *,
    station_id: str = "ST-1",
    available: float = 100.0,
    priority: int = 5,
) -> ResourceCapability:
    return ResourceCapability(
        resource_id=rid,
        resource_type=ResourceType.LOAD,
        station_id=station_id,
        rated_power_kw=100.0,
        current_power_kw=available,
        available_power_kw=available,
        priority=priority,
    )


def _pv(rid: str = "PV-1", *, station_id: str = "ST-1") -> ResourceCapability:
    return ResourceCapability(
        resource_id=rid,
        resource_type=ResourceType.PV,
        station_id=station_id,
        rated_power_kw=200.0,
        current_power_kw=120.0,
        available_power_kw=120.0,
    )


def _grid_signal(
    *,
    target_kw: Optional[float] = 100.0,
    duration: Optional[int] = 30,
    reward: Optional[float] = None,
    stype: GridSignalType = GridSignalType.DEMAND_RESPONSE,
) -> GridSignal:
    return GridSignal(
        signal_type=stype,
        timestamp=datetime.now(timezone.utc),
        target_power_kw=target_kw,
        duration_min=duration,
        reward_per_kwh=reward,
    )


# ─── 时段工具: 用固定 aware 时刻锁定电价时段 ───

def _at(hour: float, tz: ZoneInfo = ZoneInfo("Asia/Shanghai")) -> datetime:
    """构造电价时区下某时:分的 aware 时刻, hour 为浮点(如 11.0=11:00, 9.5=09:30)。"""
    h = int(hour)
    m = int(round((hour - h) * 60))
    return datetime(2026, 1, 15, h, m, tzinfo=tz)


# ═══════════════════════════════════════════════════════════
# 模块级工具函数
# ═══════════════════════════════════════════════════════════

class TestMakePlanId:
    def test_前缀与秒级时间戳格式(self):
        pid = _make_plan_id("safe_")
        assert pid.startswith("safe_")
        # safe_YYYYMMDDhhmmss_xxxxxx (6位hex后缀)
        rest = pid[len("safe_"):]
        ts_part, hex_part = rest.split("_", 1)
        assert len(ts_part) == 14 and ts_part.isdigit()
        assert len(hex_part) == 6 and all(c in "0123456789abcdef" for c in hex_part)

    def test_同秒多次调用不碰撞(self):
        # uuid4 hex 后缀保证唯一
        ids = {_make_plan_id("eco_") for _ in range(50)}
        assert len(ids) == 50

    def test_不同前缀区分(self):
        assert _make_plan_id("ps_").startswith("ps_")
        assert _make_plan_id("dr_").startswith("dr_")
        assert _make_plan_id("coord_").startswith("coord_")


class TestGetPricingTz:
    def test_默认AsiaShanghai(self, monkeypatch):
        # settings.PRICING_TIMEZONE 缺失 → import 失败 → 兜底 Shanghai
        monkeypatch.setattr(opt_mod, "_get_pricing_tz", _get_pricing_tz)
        with patch("app.core.config.settings") as mock_settings:
            type(mock_settings).PRICING_TIMEZONE = property(
                lambda self: (_ for _ in ()).throw(RuntimeError("no attr"))
            )
            tz = _get_pricing_tz()
            assert str(tz) == "Asia/Shanghai"

    def test_配置生效(self, monkeypatch):
        fake = MagicMock()
        fake.PRICING_TIMEZONE = "America/New_York"
        with patch("app.core.config.settings", fake):
            tz = _get_pricing_tz()
            assert str(tz) == "America/New_York"

    def test_坏值兜底Shanghai(self):
        fake = MagicMock()
        fake.PRICING_TIMEZONE = "not/a/zone"
        with patch("app.core.config.settings", fake):
            tz = _get_pricing_tz()
            assert str(tz) == "Asia/Shanghai"


class TestPricingHour:
    def test_显式aware时刻换算到电价时区(self):
        # UTC 02:00 = Shanghai 10:00 → 10.0 (尖峰边界)
        moment = datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc)
        assert _pricing_hour(moment) == 10.0

    def test_含分钟浮点(self):
        # Shanghai 09:30 → 9.5
        assert _pricing_hour(_at(9.5)) == pytest.approx(9.5)

    def test_None取当前时刻(self):
        h = _pricing_hour(None)
        assert 0.0 <= h < 24.0

    def test_naive输入按Shanghai解释(self):
        # naive 直接 astimezone 当作本地(Shanghai) → hour 不变
        assert _pricing_hour(datetime(2026, 1, 15, 11, 0)) == 11.0


# ═══════════════════════════════════════════════════════════
# get_current_price
# ═══════════════════════════════════════════════════════════

class TestGetCurrentPrice:
    @pytest.fixture
    def opt(self):
        return VPPOptimizer()

    @pytest.mark.parametrize("hour,expected_price,tag", [
        (10.0, 1.2, "尖峰左闭"),
        (11.0, 1.2, "尖峰中"),
        (11.99, 1.2, "尖峰右开前"),
        (8.0, 0.9, "高峰左闭"),
        (9.5, 0.9, "高峰中"),
        (9.99, 0.9, "高峰右开前"),
        (18.0, 0.9, "晚高峰左闭"),
        (20.5, 0.9, "晚高峰中"),
        (20.99, 0.9, "晚高峰右开前"),
        (23.0, 0.3, "低谷跨日起点"),
        (2.0, 0.3, "低谷深夜"),
        (5.99, 0.3, "低谷右开前"),
        (6.0, 0.6, "平段早"),
        (12.0, 0.6, "尖峰右开=平段"),
        (15.0, 0.6, "平段午"),
        (21.0, 0.6, "晚高峰右开=平段"),
    ])
    def test_四时段映射(self, opt, hour, expected_price, tag):
        assert opt.get_current_price(hour) == pytest.approx(expected_price)

    def test_price_multiplier放大(self):
        opt = VPPOptimizer({"price_multiplier": 2.0})
        assert opt.get_current_price(11.0) == pytest.approx(2.4)  # 尖峰 1.2*2

    def test_None时由_pricing_hour计算(self, opt):
        # 注入 aware 时刻, 走 _pricing_hour(now) 路径
        price = opt.get_current_price(now=_at(11.0))
        assert price == pytest.approx(1.2)

    def test_显式hour优先于now(self, opt):
        # now=尖峰 但 hour=低谷, 显式 hour 胜出
        assert opt.get_current_price(hour=2.0, now=_at(11.0)) == pytest.approx(0.3)

    def test_内部异常降级平段(self, opt, monkeypatch):
        # _pricing_hour 抛错 → 降级 FLAT_PRICE(0.6)
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: (_ for _ in ()).throw(ValueError("boom")))
        assert opt.get_current_price() == pytest.approx(0.6)


# ═══════════════════════════════════════════════════════════
# 单资源优化
# ═══════════════════════════════════════════════════════════

class TestOptimizeBattery:
    def test_低谷充电(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_battery(_battery(soc=0.3), current_price=0.3, hour=2.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0  # 负=充电
        assert cmd.estimated_revenue == 0
        assert cmd.estimated_cost > 0
        assert cmd.dispatch_mode == DispatchMode.ECONOMIC

    def test_低谷充电含边界VALLEY乘1_1(self):
        opt = VPPOptimizer()
        # 价格恰等于 VALLEY*1.1 → 仍触发充电
        price = opt.VALLEY_PRICE * 1.1
        cmd = opt._optimize_battery(_battery(soc=0.3), current_price=price, hour=2.0)
        assert cmd is not None and cmd.target_power_kw < 0

    def test_低谷但SOC已满不充电(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_battery(_battery(soc=opt.BATTERY_SOC_MAX), current_price=0.3, hour=2.0)
        assert cmd is None

    def test_高价放电(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_battery(_battery(soc=0.8), current_price=1.0, hour=9.0)
        assert cmd is not None
        assert cmd.target_power_kw > 0  # 正=放电
        assert cmd.estimated_revenue > 0
        assert cmd.estimated_cost == 0

    def test_高价但SOC低于放电下限不放电(self):
        opt = VPPOptimizer()
        # soc 恰等于放电下限 0.20, 条件是 soc > floor → 不放电
        cmd = opt._optimize_battery(
            _battery(soc=opt.BATTERY_DISCHARGE_SOC_FLOOR),
            current_price=1.0, hour=9.0,
        )
        assert cmd is None

    def test_config覆盖放电SOC下限但不低于MIN(self):
        # config 设 0.05, 实际取 max(0.05, 0.10)=0.10
        opt = VPPOptimizer({"battery_discharge_soc_floor": 0.05})
        assert opt._battery_discharge_soc_floor == 0.10
        # soc=0.15 高于 floor 0.10, 高价可放电
        cmd = opt._optimize_battery(_battery(soc=0.15), current_price=1.0, hour=9.0)
        assert cmd is not None and cmd.target_power_kw > 0

    def test_config抬高放电SOC下限生效(self):
        opt = VPPOptimizer({"battery_discharge_soc_floor": 0.5})
        assert opt._battery_discharge_soc_floor == 0.5
        # soc=0.3 低于抬高的 floor 0.5 → 不放电
        cmd = opt._optimize_battery(_battery(soc=0.3), current_price=1.0, hour=9.0)
        assert cmd is None

    def test_SOC未知仅低谷充电不放(self):
        opt = VPPOptimizer()
        # 低谷 + soc=None → 充电
        cmd = opt._optimize_battery(_battery(soc=None), current_price=0.3, hour=2.0)
        assert cmd is not None and cmd.target_power_kw < 0
        # 高价 + soc=None → 不放电(防过放)
        cmd2 = opt._optimize_battery(_battery(soc=None), current_price=1.0, hour=9.0)
        assert cmd2 is None

    def test_平段无动作(self):
        opt = VPPOptimizer()
        # 价格介于低谷*1.1 和 HIGH 之间 → 平段无动作
        cmd = opt._optimize_battery(_battery(soc=0.6), current_price=0.6, hour=15.0)
        assert cmd is None


class TestOptimizeEvCharger:
    def test_高峰削减功率(self):
        opt = VPPOptimizer()
        ev = _ev(current_power=60.0)
        cmd = opt._optimize_ev_charger(ev, current_price=1.0, hour=9.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0
        assert cmd.target_power_kw == pytest.approx(-30.0)  # 60 * 0.5
        assert cmd.dispatch_mode == DispatchMode.ECONOMIC

    def test_current_power_None不崩溃(self):
        # BUG4契约: None 经 `or 0` 兜底, 不抛 TypeError
        opt = VPPOptimizer()
        ev = _ev(current_power=0.0)
        ev.current_power_kw = None
        cmd = opt._optimize_ev_charger(ev, current_price=1.0, hour=9.0)
        assert cmd is None  # 功率0 → 无削减

    def test_非高峰无动作(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_ev_charger(_ev(current_power=60.0), current_price=0.3, hour=2.0)
        assert cmd is None

    def test_config覆盖削减比例(self):
        opt = VPPOptimizer({"ev_curtailment_ratio": 0.25})
        assert opt._ev_curtail_ratio == 0.25
        cmd = opt._optimize_ev_charger(_ev(current_power=60.0), current_price=1.0, hour=9.0)
        assert cmd.target_power_kw == pytest.approx(-15.0)  # 60 * 0.25


class TestOptimizeLoad:
    def test_尖峰削减负荷(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_load(_load(available=100.0), current_price=1.2, hour=11.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0
        assert cmd.target_power_kw == pytest.approx(-30.0)  # 100 * 0.3
        assert cmd.estimated_cost == pytest.approx(30.0 * 0.1)
        assert cmd.dispatch_mode == DispatchMode.ECONOMIC

    def test_高峰非尖峰不削减(self):
        opt = VPPOptimizer()
        # HIGH_PRICE=0.9 < PEAK_PRICE=1.2, 高峰但不尖峰 → 不削
        cmd = opt._optimize_load(_load(available=100.0), current_price=1.0, hour=9.0)
        assert cmd is None

    def test_无可用功率不削减(self):
        opt = VPPOptimizer()
        cmd = opt._optimize_load(_load(available=0.0), current_price=1.2, hour=11.0)
        assert cmd is None


class TestOptimizeSingleResource:
    def test_PV不调度返回None(self):
        opt = VPPOptimizer()
        assert opt._optimize_single_resource(_pv(), current_price=1.0, hour=11.0) is None

    def test_按类型分发到对应优化器(self):
        opt = VPPOptimizer()
        # battery 低价充电
        c1 = opt._optimize_single_resource(_battery(soc=0.3), 0.3, 2.0)
        assert c1 is not None and c1.resource_type == ResourceType.BATTERY
        # ev 高峰削减
        c2 = opt._optimize_single_resource(_ev(current_power=60.0), 1.0, 9.0)
        assert c2 is not None and c2.resource_type == ResourceType.EV_CHARGER
        # load 尖峰削减
        c3 = opt._optimize_single_resource(_load(available=100.0), 1.2, 11.0)
        assert c3 is not None and c3.resource_type == ResourceType.LOAD

    def test_平段所有资源无动作(self):
        opt = VPPOptimizer()
        for r in [_battery(soc=0.6), _ev(current_power=60.0), _load(available=100.0), _pv()]:
            assert opt._optimize_single_resource(r, current_price=0.6, hour=15.0) is None

    def test_未知资源类型返回None(self):
        # L654: 四类之外的 resource_type 走末尾 return None
        opt = VPPOptimizer()
        r = ResourceCapability(
            resource_id="X-1", resource_type=ResourceType.PV, station_id="ST-1",
            rated_power_kw=100.0, current_power_kw=0.0, available_power_kw=100.0,
        )
        # 篡改为非枚举值, 模拟未知类型
        r.resource_type = "unknown_type"
        assert opt._optimize_single_resource(r, current_price=1.0, hour=11.0) is None


# ═══════════════════════════════════════════════════════════
# 经济调度 optimize_economic_dispatch
# ═══════════════════════════════════════════════════════════

class TestEconomicDispatch:
    @pytest.fixture
    def opt(self):
        return VPPOptimizer()

    def test_低谷时段储能充电(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)
        stations = [_station("ST-1")]
        resources = [_battery("BAT-1", soc=0.3)]
        plan = opt.optimize_economic_dispatch(stations, resources)
        assert plan.mode == DispatchMode.ECONOMIC
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw < 0  # 充电
        assert "峰谷套利" in plan.trigger
        assert plan.stations_involved == ["ST-1"]

    def test_高价时段储能放电(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)
        plan = opt.optimize_economic_dispatch([_station()], [_battery("BAT-1", soc=0.8)])
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw > 0  # 放电

    def test_平段无指令(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        plan = opt.optimize_economic_dispatch([_station()], [_battery("BAT-1", soc=0.6)])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_多站点多资源聚合并按优先级排序(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)  # 高价放电
        stations = [_station("ST-1"), _station("ST-2")]
        # priority 升序: BAT-p2 先于 BAT-p1? priority 越小越优先, sort 升序 → p1 在前
        resources = [
            _battery("BAT-A", station_id="ST-1", soc=0.8, priority=3),
            _battery("BAT-B", station_id="ST-2", soc=0.8, priority=1),
        ]
        plan = opt.optimize_economic_dispatch(stations, resources)
        assert len(plan.commands) == 2
        # 排序后 priority=1(BAT-B) 在前
        assert plan.commands[0].resource_id == "BAT-B"
        assert plan.commands[1].resource_id == "BAT-A"
        assert set(plan.stations_involved) == {"ST-1", "ST-2"}

    def test_净收益等于收入减成本(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)
        plan = opt.optimize_economic_dispatch([_station()], [_battery("BAT-1", soc=0.8)])
        assert plan.net_profit == pytest.approx(plan.estimated_revenue - plan.estimated_cost)

    def test_空资源列表返回空计划(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)
        plan = opt.optimize_economic_dispatch([_station()], [])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_极小功率指令被过滤(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)
        # available=0.05 → 放电功率 0.05 < 0.1 阈值, abs(power)<=0.1 不入列
        bat = _battery("BAT-1", soc=0.8, available=0.05)
        plan = opt.optimize_economic_dispatch([_station()], [bat])
        assert plan.commands == []

    def test_impl抛异常走安全降级(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)
        monkeypatch.setattr(
            VPPOptimizer, "_optimize_single_resource",
            lambda self, r, p, h: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        stations = [_station("ST-1", online=True)]
        plan = opt.optimize_economic_dispatch(stations, [_battery()])
        assert plan.mode == DispatchMode.ECONOMIC
        assert plan.plan_id.startswith("safe_")
        assert "异常降级" in plan.trigger
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        # 在线站点仍透传
        assert plan.stations_involved == ["ST-1"]


# ═══════════════════════════════════════════════════════════
# 削峰 optimize_peak_shaving
# ═══════════════════════════════════════════════════════════

class TestPeakShaving:
    @pytest.fixture
    def opt(self):
        return VPPOptimizer()

    def test_阈值零或负安全跳过(self, opt):
        for thr in (0, -1.0, -100):
            plan = opt.optimize_peak_shaving([_station("ST-1", online=True)], [], thr)
            assert plan.mode == DispatchMode.PEAK_SHAVING
            assert plan.commands == []
            assert plan.total_dispatch_kw == 0
            assert "无效" in plan.trigger

    def test_负荷正常无过载不调度(self, opt):
        # load=100 < threshold=500 → 无过载
        plan = opt.optimize_peak_shaving([_station(load=100.0)], [], peak_threshold_kw=500.0)
        assert plan.commands == []
        assert "正常" in plan.trigger

    def test_过载优先储能放电(self, opt):
        stations = [_station("ST-1", load=600.0)]  # overload = 600-500 = 100
        resources = [_battery("BAT-1", available=200.0, rated=200.0, soc=0.8)]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert cmd.target_power_kw > 0  # 放电为正
        assert cmd.resource_type == ResourceType.BATTERY
        assert cmd.dispatch_mode == DispatchMode.PEAK_SHAVING
        # 100*1.1=110 余量, 受 available/rated 上限 200 → 取 110
        assert cmd.target_power_kw == pytest.approx(110.0)

    def test_储能SOC过低跳过改削减负荷(self, opt):
        stations = [_station(load=600.0)]
        # SOC 0.10 < SOC_MIN+0.1=0.20 → 跳过储能
        low_bat = _battery("BAT-1", available=200.0, rated=200.0, soc=0.10)
        load_r = _load("LOAD-1", available=100.0)
        plan = opt.optimize_peak_shaving(stations, [low_bat, load_r], peak_threshold_kw=500.0)
        # 无储能指令, 仅负荷削减
        assert all(c.resource_type != ResourceType.BATTERY for c in plan.commands)
        assert any(c.resource_type == ResourceType.LOAD for c in plan.commands)
        # 削减指令功率为负
        load_cmd = next(c for c in plan.commands if c.resource_type == ResourceType.LOAD)
        assert load_cmd.target_power_kw < 0

    def test_储能不足时叠加负荷削减(self, opt):
        # overload=200, 储能只能给 50, 剩 150 由负荷削减
        stations = [_station(load=700.0)]
        resources = [
            _battery("BAT-1", available=50.0, rated=50.0, soc=0.8),
            _load("LOAD-1", available=200.0),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)
        types = [c.resource_type for c in plan.commands]
        assert ResourceType.BATTERY in types
        assert ResourceType.LOAD in types

    def test_离线站点不计入负荷(self, opt):
        stations = [
            _station("ST-ON", load=600.0, online=True),
            _station("ST-OFF", load=1000.0, online=False),
        ]
        # 仅在线站点 load=600 → overload=100
        plan = opt.optimize_peak_shaving(stations, [], peak_threshold_kw=500.0)
        assert "ST-ON" in plan.stations_involved
        assert "ST-OFF" not in plan.stations_involved

    def test_净收益计算(self, opt):
        stations = [_station(load=600.0)]
        plan = opt.optimize_peak_shaving(
            stations, [_battery("BAT-1", available=200.0, soc=0.8)], 500.0,
        )
        assert plan.net_profit == pytest.approx(plan.estimated_revenue - plan.estimated_cost)

    def test_储能满足过载后提前break(self, opt):
        # L295: 多储能, 第一个就满足全部过载, 循环中段 break, 第二个不调度
        stations = [_station(load=600.0)]  # overload=100
        resources = [
            _battery("BAT-1", available=200.0, rated=200.0, soc=0.8, priority=1),
            _battery("BAT-2", available=200.0, rated=200.0, soc=0.8, priority=2),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)
        assert {c.resource_id for c in plan.commands} == {"BAT-1"}

    def test_负荷满足剩余过载后提前break(self, opt):
        # L331: 储能不可用(低SOC) → 走负荷削减, 第一个负荷满足后 break
        stations = [_station(load=650.0)]  # overload=150
        resources = [
            _battery("BAT-1", available=200.0, rated=200.0, soc=0.10),  # SOC 太低跳过
            _load("LOAD-1", available=200.0, priority=1),
            _load("LOAD-2", available=200.0, priority=2),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)
        # LOAD-1 削减 150 满足过载, LOAD-2 不调度
        assert {c.resource_id for c in plan.commands} == {"LOAD-1"}

    def test_impl异常走安全降级(self, opt, monkeypatch):
        monkeypatch.setattr(
            VPPOptimizer, "_optimize_peak_shaving_impl",
            lambda self, s, r, t: (_ for _ in ()).throw(ValueError("x")),
        )
        plan = opt.optimize_peak_shaving([_station("ST-1", online=True)], [], 500.0)
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert plan.commands == []


# ═══════════════════════════════════════════════════════════
# 需求响应 handle_demand_response
# ═══════════════════════════════════════════════════════════

class TestDemandResponse:
    @pytest.fixture
    def opt(self):
        return VPPOptimizer()

    def test_优先储能放电满足目标(self, opt):
        stations = [_station()]
        resources = [
            _battery("BAT-1", available=60.0, rated=60.0, soc=0.8),
            _ev("EV-1", current_power=60.0),
            _load("LOAD-1", available=100.0),
        ]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=50.0))
        # 储能 priority=1 优先, 满足 50 目标后 remaining=0, 后续资源不调度
        bat_cmd = next((c for c in plan.commands if c.resource_type == ResourceType.BATTERY), None)
        assert bat_cmd is not None
        assert bat_cmd.priority == 1
        assert bat_cmd.target_power_kw == pytest.approx(50.0)
        # 目标已满足, EV/Load 无指令
        assert not any(c.resource_type == ResourceType.EV_CHARGER for c in plan.commands)
        assert not any(c.resource_type == ResourceType.LOAD for c in plan.commands)

    def test_储能不足转EV削减(self, opt):
        stations = [_station()]
        resources = [
            _battery("BAT-1", available=20.0, rated=20.0, soc=0.8),
            _ev("EV-1", current_power=60.0),
        ]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=50.0))
        # 储能给 20, 剩 30 由 EV 削减
        bat_kw = next(c.target_power_kw for c in plan.commands if c.resource_type == ResourceType.BATTERY)
        ev_cmd = next(c for c in plan.commands if c.resource_type == ResourceType.EV_CHARGER)
        assert bat_kw == pytest.approx(20.0)
        assert ev_cmd.target_power_kw == pytest.approx(-30.0)
        assert ev_cmd.priority == 2

    def test_EV不足转负荷削减(self, opt):
        stations = [_station()]
        resources = [
            _battery("BAT-1", available=10.0, rated=10.0, soc=0.8),
            _ev("EV-1", current_power=10.0),
            _load("LOAD-1", available=100.0),
        ]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=50.0))
        load_cmd = next(c for c in plan.commands if c.resource_type == ResourceType.LOAD)
        assert load_cmd.priority == 3
        # 10(bat)+10(ev)+30(load)=50
        assert load_cmd.target_power_kw == pytest.approx(-30.0)

    def test_储能SOC过低跳过(self, opt):
        # SOC < SOC_MIN+0.15=0.25 → 跳过储能, 直接 EV 削减
        stations = [_station()]
        resources = [
            _battery("BAT-1", available=60.0, rated=60.0, soc=0.20),
            _ev("EV-1", current_power=50.0),
        ]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=40.0))
        assert not any(c.resource_type == ResourceType.BATTERY for c in plan.commands)
        assert any(c.resource_type == ResourceType.EV_CHARGER for c in plan.commands)

    def test_target_kw为None兜底零响应率(self, opt):
        stations = [_station()]
        plan = opt.handle_demand_response(stations, [_battery(soc=0.8)], _grid_signal(target_kw=None))
        assert plan.commands == []
        assert "响应率0.0%" in plan.trigger

    def test_duration_None兜底30(self, opt):
        stations = [_station()]
        resources = [_battery("BAT-1", available=60.0, rated=60.0, soc=0.8)]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=50.0, duration=None))
        cmd = plan.commands[0]
        assert cmd.duration_min == 30

    def test_reward_None用配置dr_reward_rate(self, opt):
        opt = VPPOptimizer({"dr_reward_rate": 0.42})
        stations = [_station()]
        resources = [_battery("BAT-1", available=60.0, rated=60.0, soc=0.8)]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=50.0, reward=None))
        # revenue = discharge * reward * duration / 60 = 50 * 0.42 * 30 / 60 = 10.5
        assert plan.commands[0].estimated_revenue == pytest.approx(10.5)

    def test_response_rate计算(self, opt):
        stations = [_station()]
        # 目标 100, 储能仅能给 60 → 响应率 60%
        resources = [_battery("BAT-1", available=60.0, rated=60.0, soc=0.8)]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=100.0))
        assert "响应率60.0%" in plan.trigger

    def test_total_dispatch取绝对值(self, opt):
        stations = [_station()]
        resources = [
            _battery("BAT-1", available=30.0, rated=30.0, soc=0.8),
            _ev("EV-1", current_power=30.0),
        ]
        plan = opt.handle_demand_response(stations, resources, _grid_signal(target_kw=60.0))
        # bat +30(放电), ev -30(削减) → abs 之和 60
        assert plan.total_dispatch_kw == pytest.approx(60.0)

    def test_impl异常走安全降级(self, opt, monkeypatch):
        monkeypatch.setattr(
            VPPOptimizer, "_handle_demand_response_impl",
            lambda self, s, r, sig: (_ for _ in ()).throw(RuntimeError("x")),
        )
        plan = opt.handle_demand_response([_station("ST-1", online=True)], [], _grid_signal())
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert plan.commands == []


# ═══════════════════════════════════════════════════════════
# 多站协调 optimize_multi_station_coordination
# ═══════════════════════════════════════════════════════════

class TestMultiStationCoordination:
    @pytest.fixture
    def opt(self):
        return VPPOptimizer()

    def test_缺电站点从余电站点储能互济(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)  # 平段(不触发经济充放)
        # ST-IMP: surplus = pv_output - load + dispatch = 0 - 100 + 0 = -100 (缺电)
        # ST-EXP: surplus = 200 - 0 + 0 = 200 (余电)
        stations = [
            _station("ST-IMP", load=100.0, pv_output=0.0, dispatch_kw=0.0),
            _station("ST-EXP", load=0.0, pv_output=200.0, dispatch_kw=0.0),
        ]
        resources = [_battery("BAT-EXP", station_id="ST-EXP", available=150.0, soc=0.8)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        assert plan.mode == DispatchMode.GRID_SUPPORT
        # 互济指令: 从 ST-EXP 储能放电
        assert any(c.resource_id == "BAT-EXP" for c in plan.commands)
        cmd = next(c for c in plan.commands if c.resource_id == "BAT-EXP")
        assert cmd.target_power_kw > 0
        assert cmd.dispatch_mode == DispatchMode.GRID_SUPPORT

    def test_互济BUG1实际扣减多处余电站点(self, opt, monkeypatch):
        """BUG1契约(卡c7b966cd): deficit 须按实际互济量扣减, 多余电站点接力供给。"""
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        # 缺电站点缺口 150, 两个余电站点各余 100/100, 需接力
        stations = [
            _station("ST-IMP", load=150.0, pv_output=0.0, dispatch_kw=0.0),  # 缺口 150
            _station("ST-EXP1", load=0.0, pv_output=100.0, dispatch_kw=0.0),  # 余 100
            _station("ST-EXP2", load=0.0, pv_output=100.0, dispatch_kw=0.0),  # 余 100
        ]
        resources = [
            _battery("BAT-E1", station_id="ST-EXP1", available=100.0, soc=0.8),
            _battery("BAT-E2", station_id="ST-EXP2", available=100.0, soc=0.8),
        ]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        # 两个余电站点的储能都被调度(证明 deficit 按实际扣减, 非错误归零)
        used = {c.resource_id for c in plan.commands if c.resource_type == ResourceType.BATTERY}
        assert used == {"BAT-E1", "BAT-E2"}
        total_mutual = sum(
            c.target_power_kw for c in plan.commands
            if c.dispatch_mode == DispatchMode.GRID_SUPPORT
        )
        assert total_mutual == pytest.approx(150.0)

    def test_grid_signal触发需求响应(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        stations = [_station("ST-1")]
        resources = [_battery("BAT-1", available=60.0, rated=60.0, soc=0.8)]
        plan = opt.optimize_multi_station_coordination(
            stations, resources, _grid_signal(target_kw=50.0),
        )
        # DR 指令 dispatch_mode=DEMAND_RESPONSE 被合并进来
        assert any(c.dispatch_mode == DispatchMode.DEMAND_RESPONSE for c in plan.commands)

    def test_高电价时段剩余储能经济放电(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)  # 高价
        # 无互济需求(站点平衡), 剩余储能走经济放电
        stations = [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)]
        resources = [_battery("BAT-1", available=100.0, soc=0.8)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        eco_cmd = next(c for c in plan.commands if c.dispatch_mode == DispatchMode.ECONOMIC)
        assert eco_cmd.target_power_kw > 0  # 放电
        assert eco_cmd.priority == 3

    def test_低电价时段储能经济充电(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)  # 低谷
        stations = [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)]
        resources = [_battery("BAT-1", available=100.0, soc=0.3)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        eco_cmd = next(c for c in plan.commands if c.dispatch_mode == DispatchMode.ECONOMIC)
        assert eco_cmd.target_power_kw < 0  # 充电
        assert eco_cmd.priority == 4

    def test_互济已用的储能不重复经济放电(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)  # 高价
        # 该储能被互济用掉 → remaining_batteries 排除它
        stations = [
            _station("ST-IMP", load=50.0, pv_output=0.0, dispatch_kw=0.0),
            _station("ST-EXP", load=0.0, pv_output=100.0, dispatch_kw=0.0),
        ]
        resources = [_battery("BAT-EXP", station_id="ST-EXP", available=100.0, soc=0.8)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        bat_cmds = [c for c in plan.commands if c.resource_id == "BAT-EXP"]
        # 只被互济用一次, 不再叠加经济放电
        assert len(bat_cmds) == 1
        assert bat_cmds[0].dispatch_mode == DispatchMode.GRID_SUPPORT

    def test_离线站点不参与平衡(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        stations = [
            _station("ST-OFF", load=1000.0, pv_output=0.0, dispatch_kw=0.0, online=False),
            _station("ST-ON", load=0.0, pv_output=0.0, dispatch_kw=0.0, online=True),
        ]
        plan = opt.optimize_multi_station_coordination(stations, [])
        assert "ST-ON" in plan.stations_involved
        assert "ST-OFF" not in plan.stations_involved
        assert "参与站点1个" in plan.trigger

    def test_总调度取绝对值之和(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)  # 低谷充电
        stations = [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)]
        resources = [
            _battery("BAT-1", available=100.0, soc=0.3),
            _battery("BAT-2", available=100.0, soc=0.3),
        ]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        # 两个充电指令各 -100, abs 之和 200
        assert plan.total_dispatch_kw == pytest.approx(200.0)

    def test_net_profit计算(self, opt, monkeypatch):
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)
        plan = opt.optimize_multi_station_coordination(
            [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)],
            [_battery("BAT-1", available=100.0, soc=0.8)],
        )
        assert plan.net_profit == pytest.approx(plan.estimated_revenue - plan.estimated_cost)

    def test_余电站点surplus耗尽后continue和break(self, opt, monkeypatch):
        # L536: 余电站点 surplus<=0 时 continue(跳过该站); L545: 站内电池放完 transfer<=0 break
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        # 两个缺电站点接力消耗单一余电站点, 第二个缺电站点时余电已归 0 → continue
        stations = [
            _station("ST-IMP1", load=50.0, pv_output=0.0, dispatch_kw=0.0),   # 缺 50
            _station("ST-IMP2", load=50.0, pv_output=0.0, dispatch_kw=0.0),   # 缺 50
            _station("ST-EXP", load=0.0, pv_output=50.0, dispatch_kw=0.0),    # 余 50
        ]
        # 余电站点电池只能放 50(满足 IMP1), IMP2 时 surplus=0 → continue; 站内无更多电池 → break
        resources = [
            _battery("BAT-EXP", station_id="ST-EXP", available=50.0, soc=0.8),
            # IMP2 缺电站点的本地电池 available 极小, 命中 actual_kw<=0.1 → transfer 不减 → break
            _battery("BAT-IMP2", station_id="ST-IMP2", available=0.05, soc=0.8),
        ]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        # ST-EXP 互济放电 50 给 IMP1, IMP2 因余电耗尽得不到互济
        mutual = [c for c in plan.commands if c.dispatch_mode == DispatchMode.GRID_SUPPORT]
        assert mutual and mutual[0].resource_id == "BAT-EXP"
        assert mutual[0].target_power_kw == pytest.approx(50.0)

    def test_站内多电池满足transfer后break(self, opt, monkeypatch):
        # L545: 同一余电站点多个电池, 第一个就满足 transfer, 内层 for 下次 iteration break
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 15.0)
        stations = [
            _station("ST-IMP", load=30.0, pv_output=0.0, dispatch_kw=0.0),   # 缺 30
            _station("ST-EXP", load=0.0, pv_output=200.0, dispatch_kw=0.0),  # 余 200
        ]
        resources = [
            _battery("BAT-E1", station_id="ST-EXP", available=100.0, soc=0.8, priority=1),
            _battery("BAT-E2", station_id="ST-EXP", available=100.0, soc=0.8, priority=2),
        ]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        # 缺口 30 由 BAT-E1 全部满足, transfer 归 0, BAT-E2 不被调度(内层 break)
        mutual = [c for c in plan.commands if c.dispatch_mode == DispatchMode.GRID_SUPPORT]
        assert {c.resource_id for c in mutual} == {"BAT-E1"}

    def test_高电价但剩余储能SOC过低跳过放电(self, opt, monkeypatch):
        # L586: soc < SOC_MIN+0.1=0.20 continue
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 9.0)
        stations = [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)]
        resources = [_battery("BAT-1", available=100.0, soc=0.15)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        # 无互济也无经济放电(低SOC) → 无指令
        assert plan.commands == []

    def test_低电价但储能SOC已满跳过充电(self, opt, monkeypatch):
        # L606: soc >= SOC_MAX=0.95 continue
        monkeypatch.setattr(opt_mod, "_pricing_hour", lambda now=None: 2.0)
        stations = [_station("ST-1", load=0.0, pv_output=0.0, dispatch_kw=0.0)]
        resources = [_battery("BAT-1", available=100.0, soc=0.99)]
        plan = opt.optimize_multi_station_coordination(stations, resources)
        assert plan.commands == []

    def test_impl异常走安全降级(self, opt, monkeypatch):
        monkeypatch.setattr(
            VPPOptimizer, "_optimize_multi_station_coordination_impl",
            lambda self, s, r, g: (_ for _ in ()).throw(RuntimeError("x")),
        )
        plan = opt.optimize_multi_station_coordination([_station("ST-1", online=True)], [])
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert plan.commands == []


# ═══════════════════════════════════════════════════════════
# _safe_default_plan
# ═══════════════════════════════════════════════════════════

class TestSafeDefaultPlan:
    def test_返回零功率安全计划(self):
        opt = VPPOptimizer()
        plan = opt._safe_default_plan(DispatchMode.ECONOMIC, "测试", [_station("ST-1", online=True)])
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.ECONOMIC
        assert plan.trigger == "异常降级: 测试"
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert plan.estimated_revenue == 0
        assert plan.estimated_cost == 0
        assert plan.net_profit == 0

    def test_仅透传在线站点(self):
        opt = VPPOptimizer()
        stations = [
            _station("ST-ON", online=True),
            _station("ST-OFF", online=False),
        ]
        plan = opt._safe_default_plan(DispatchMode.PEAK_SHAVING, "x", stations)
        assert plan.stations_involved == ["ST-ON"]

    def test_None或空stations返回空列表(self):
        opt = VPPOptimizer()
        for s in (None, []):
            plan = opt._safe_default_plan(DispatchMode.ECONOMIC, "x", s)
            assert plan.stations_involved == []

    def test_stations含异常对象兜底空列表(self):
        # 遍历站点时某对象 online 访问抛错 → 内层 try 兜底 []
        opt = VPPOptimizer()
        bad = MagicMock()
        type(bad).online = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        plan = opt._safe_default_plan(DispatchMode.ECONOMIC, "x", [bad])
        assert plan.stations_involved == []

    def test_构造无DB依赖(self):
        # 即使 settings 缺失也不影响降级计划构造
        opt = VPPOptimizer(config=None)
        plan = opt._safe_default_plan(DispatchMode.GRID_SUPPORT, "无配置", [])
        assert plan.mode == DispatchMode.GRID_SUPPORT


# ═══════════════════════════════════════════════════════════
# 构造与配置
# ═══════════════════════════════════════════════════════════

class TestInit:
    def test_默认配置(self):
        opt = VPPOptimizer()
        assert opt.config == {}
        assert opt.price_multiplier == 1.0
        assert opt.dr_reward_rate == 0.5
        assert opt.frequency_reg_reward == 0.15

    def test_None配置等同空(self):
        opt = VPPOptimizer(None)
        assert opt.config == {}
        assert opt.price_multiplier == 1.0

    def test_自定义配置生效(self):
        opt = VPPOptimizer({
            "price_multiplier": 1.5,
            "dr_reward_rate": 0.8,
            "frequency_reg_reward": 0.2,
        })
        assert opt.price_multiplier == 1.5
        assert opt.dr_reward_rate == 0.8
        assert opt.frequency_reg_reward == 0.2

    def test_类常量存在(self):
        opt = VPPOptimizer()
        assert opt.PEAK_PRICE == 1.2
        assert opt.HIGH_PRICE == 0.9
        assert opt.FLAT_PRICE == 0.6
        assert opt.VALLEY_PRICE == 0.3
        assert opt.BATTERY_SOC_MIN == 0.10
        assert opt.BATTERY_SOC_MAX == 0.95
        assert opt.BATTERY_DISCHARGE_SOC_FLOOR == 0.20

    def test_battery_discharge_soc_floor默认值(self):
        opt = VPPOptimizer()
        assert opt._battery_discharge_soc_floor == 0.20

    def test_ev_curtail_ratio默认值(self):
        opt = VPPOptimizer()
        assert opt._ev_curtail_ratio == 0.5

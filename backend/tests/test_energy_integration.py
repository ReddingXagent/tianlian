"""P1-5 功率预算协同联调集成测试 (预研 §4.3 协同接口)

把供给侧能量调度 (energy_tasks.run_dispatch_cycle) 与需求侧充电排车
(charging_schedule_service.generate_schedule) 串成端到端链路:

    光伏/储能/桩 telemetry → 策略仲裁 → EnergyDispatchPlan.available_power_budget_kw
    → (协同桥接) → generate_schedule(available_power_kw=预算) → 排车计划不超预算
    → EnergyFlowLog 15min 聚合落库

覆盖验收标准:
1. 手动触发 energy_task → plan 有 available_power_budget_kw
2. 用该预算调 generate_schedule → 排车不超预算
3. energy_flow_log 有 15min 聚合记录
4. 端到端全链路通

纯 DB 集成测试: 自建 sqlite 内存库 + create_all, 不走 conftest RBAC client 链路
(autouse _auth_module_level_client 仅对顶层定义 client=TestClient(...) 的模块生效, 本模块零开销)。
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger as SA_BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# sqlite 下 BigInteger PK 自增适配 (对齐 tests/conftest.py / tests/test_energy_tasks.py 既有模式)
@compiles(SA_BigInteger, "sqlite")
def _compile_bigint_sqlite(element, compiler, **kw):
    return "INTEGER"


from app.core.database import Base
from app.models.charging_schedule import ChargingScheduleEntry, ChargingSchedulePlan
from app.models.energy_strategy import (
    EnergyDispatchPlan,
    EnergyFlowLog,
    EnergyPricePeriod,
    EnergyPriceTemplate,
    StationEnergyStrategy,
)
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.pricing_v2 import PeriodType
from app.models.station import Station
from app.models.telemetry_v2 import TelemetryBattery, TelemetryCharger, TelemetryPV
from app.tasks.energy_tasks import (
    POWER_FACTOR_DEFAULT,
    WINDOW_MINUTES,
    apply_power_budget_to_charging,
    run_dispatch_cycle,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures: 独立内存 DB (全表 create_all)
# ═══════════════════════════════════════════════════════════════

@pytest.fixture()
def db():
    """独立 sqlite 内存库 + 全表建表, 不依赖 conftest RBAC seed"""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_NOW = datetime(2026, 8, 1, 12, 7, 0)        # 周六中午, window_start 应 floor 到 12:00
_WIN_START = datetime(2026, 8, 1, 12, 0)
_WIN_END = datetime(2026, 8, 1, 12, 15)


# ═══════════════════════════════════════════════════════════════
# Seed helpers
# ═══════════════════════════════════════════════════════════════

def _seed_station(db, station_id=1, team_id=100, province="四川"):
    st = Station(id=station_id, name=f"测试站{station_id}", code=f"ST{station_id:04d}",
                 team_id=team_id, province=province)
    db.add(st)
    db.flush()
    return st


def _seed_price_template(db, station_id, team_id=100, price=0.30,
                         period_type=PeriodType.VALLEY):
    """当前生效模板 + 全天覆盖时段"""
    tpl = EnergyPriceTemplate(
        province="四川", version=1, effective_from=datetime(2026, 1, 1).date(),
        effective_until=None, is_active=True, team_id=team_id,
    )
    db.add(tpl)
    db.flush()
    period = EnergyPricePeriod(
        template_id=tpl.id, period_type=period_type,
        start_time=datetime(2026, 1, 1, 0, 0).time(),
        end_time=datetime(2026, 1, 1, 23, 59).time(),
        purchase_price=Decimal(str(price)),
    )
    db.add(period)
    db.flush()
    return tpl


def _seed_strategy(db, station_id, team_id=100, template_id=None, **overrides):
    cfg = overrides.pop("strategy_config", {
        "valley_price_threshold": 0.40,
        "peak_price_threshold": 0.90,
        "strategies": {
            "arbitrage": {"enabled": True},
            "solar_absorb": {"enabled": True},
            "boosting": {"enabled": False},   # 关增容, 避免与充电反向冲突
        },
    })
    defaults = dict(
        station_id=station_id, team_id=team_id, price_template_id=template_id,
        transformer_capacity_kva=100.0, pv_capacity_kw=50.0, ess_capacity_kwh=200.0,
        soc_floor=0.10, is_active=True, strategy_config=cfg,
    )
    defaults.update(overrides)
    st = StationEnergyStrategy(**defaults)
    db.add(st)
    db.flush()
    return st


def _seed_telemetry(db, station_id, pv_kw=30.0, grid_kw=10.0, soc_pct=50.0,
                    battery_power=0.0, charger_kw=20.0):
    db.add(TelemetryPV(station_id=station_id, device_id=1, pv_power_total=pv_kw,
                       grid_power_total=grid_kw, daily_generation=100.0))
    db.add(TelemetryBattery(station_id=station_id, device_id=2, battery_soc=soc_pct,
                            battery_power=battery_power,
                            bms_charge_current_limit=100.0,
                            bms_discharge_current_limit=100.0))
    db.add(TelemetryCharger(station_id=station_id, device_id=3, charger_power=charger_kw))
    db.flush()


def _seed_fleet(db, n_vehicles=3, name="协同测试企业", code="EGY_INT"):
    """建企业 + n 辆车, 返回 (enterprise_id, [vehicle_ids])"""
    ent = Enterprise(name=name, code=code, balance=10000.0)
    db.add(ent)
    db.flush()
    vids = []
    for i in range(n_vehicles):
        v = EnterpriseVehicle(
            enterprise_id=ent.id,
            plate_number=f"豫A-EGY-{i:03d}",
            vin=f"LSVAUEGY{ent.id:06d}{i:02d}",
        )
        db.add(v)
        vids.append(v)
    db.flush()
    return ent.id, [v.id for v in vids]


def _seed_full_supply_side(db, station_id=1, team_id=100):
    """建完整供给侧: 站 + 低谷模板 + 策略 + 遥测, 返回 strategy"""
    _seed_station(db, station_id=station_id, team_id=team_id)
    tpl = _seed_price_template(db, station_id=station_id, team_id=team_id, price=0.30)
    strat = _seed_strategy(db, station_id=station_id, team_id=team_id, template_id=tpl.id)
    _seed_telemetry(db, station_id=station_id, pv_kw=30.0, soc_pct=50.0, charger_kw=20.0)
    return strat


# ═══════════════════════════════════════════════════════════════
# 验收标准 1: 供给侧功率预算落库
# ═══════════════════════════════════════════════════════════════

class TestPowerBudgetProduced:
    """手动触发 dispatch → EnergyDispatchPlan 有记录且 available_power_budget_kw 有值"""

    def test_plan_has_power_budget(self, db):
        _seed_full_supply_side(db)
        result = run_dispatch_cycle(db, now=_NOW)

        assert result["plans"] == 1
        plan = db.query(EnergyDispatchPlan).one()
        # 预算非空且为正
        assert plan.available_power_budget_kw is not None
        assert plan.available_power_budget_kw > 0
        # 对齐既有公式: 100kVA*0.9 + pv30 - ess_charge50 = 70kW
        assert plan.available_power_budget_kw == pytest.approx(
            100.0 * POWER_FACTOR_DEFAULT + 30.0 - 50.0
        )

    def test_plan_window_floored_to_15min(self, db):
        _seed_full_supply_side(db)
        run_dispatch_cycle(db, now=_NOW)
        plan = db.query(EnergyDispatchPlan).one()
        assert plan.window_start == _WIN_START
        assert plan.window_end == _WIN_END


# ═══════════════════════════════════════════════════════════════
# 验收标准 2: 预算下发给需求侧 → 排车不超预算
# ═══════════════════════════════════════════════════════════════

class TestScheduleWithinBudget:
    """用 plan.available_power_budget_kw 调 generate_schedule → 排车严格落在预算内"""

    def test_schedule_consumes_plan_budget(self, db):
        _seed_full_supply_side(db)
        run_dispatch_cycle(db, now=_NOW)
        plan = db.query(EnergyDispatchPlan).one()
        budget = float(plan.available_power_budget_kw)

        ent_id, vids = _seed_fleet(db, n_vehicles=3)
        # 3 辆车各 7kW 需求 (总 21kW) < 预算 70, 全部满足
        states = [
            {"vehicle_id": vids[i], "current_soc": 0.2 + i * 0.1,
             "target_soc": 0.9, "max_power_kw": 7.0}
            for i in range(3)
        ]
        result = apply_power_budget_to_charging(
            db, station_id=1, enterprise_id=ent_id, vehicle_states=states,
            window_start=_WIN_START, window_end=_WIN_END,
        )

        assert "error" not in result
        # 预算作为排车功率上限
        assert result["summary"]["available_power_kw"] == pytest.approx(budget)
        # 排车不超预算 (核心契约)
        assert result["summary"]["allocated_power_kw"] <= budget
        assert result["summary"]["charging_vehicles"] == 3
        # 协同溯源: 标注预算来自哪个 plan
        assert result["power_budget_source"]["plan_id"] == plan.id
        assert result["power_budget_source"]["available_power_budget_kw"] == pytest.approx(budget)

    def test_schedule_clipped_when_demand_exceeds_budget(self, db):
        """总需求 > 预算 → 排车被钳到预算上限, allocated == budget, remaining == 0"""
        _seed_full_supply_side(db)
        run_dispatch_cycle(db, now=_NOW)
        plan = db.query(EnergyDispatchPlan).one()
        budget = float(plan.available_power_budget_kw)
        assert budget == pytest.approx(70.0)

        ent_id, vids = _seed_fleet(db, n_vehicles=6)
        # 6 辆车各 20kW 需求 (总 120kW) 远超预算 70 → 必须钳位
        states = [
            {"vehicle_id": vids[i], "current_soc": 0.1 + i * 0.05,
             "target_soc": 0.9, "max_power_kw": 20.0}
            for i in range(6)
        ]
        result = apply_power_budget_to_charging(
            db, station_id=1, enterprise_id=ent_id, vehicle_states=states,
            window_start=_WIN_START, window_end=_WIN_END,
            rule_spec={"max_power_per_vehicle": 20.0},
        )

        assert "error" not in result
        allocated = result["summary"]["allocated_power_kw"]
        # 钳位: allocated 恰好等于预算, 不超发
        assert allocated == pytest.approx(budget)
        assert result["summary"]["remaining_power_kw"] == 0.0
        # 单车不超 max_power_per_vehicle
        for e in result["entries"]:
            assert e["assigned_power_kw"] <= 20.0
        # 排车计划落库
        assert db.query(ChargingSchedulePlan).count() == 1
        assert db.query(ChargingScheduleEntry).count() == 6

    def test_apply_budget_no_plan_returns_error(self, db):
        """无 EnergyDispatchPlan → 协同桥接返回 error (不静默造假预算)"""
        ent_id, vids = _seed_fleet(db, n_vehicles=1)
        states = [{"vehicle_id": vids[0], "current_soc": 0.2,
                   "target_soc": 0.9, "max_power_kw": 7.0}]
        result = apply_power_budget_to_charging(
            db, station_id=999, enterprise_id=ent_id, vehicle_states=states,
            window_start=_WIN_START, window_end=_WIN_END,
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# 验收标准 3: energy_flow_log 15min 聚合记录
# ═══════════════════════════════════════════════════════════════

class TestEnergyFlowLogAggregation:
    """能量流水: 瞬时功率 × (15/60) → 15min 能量值"""

    def test_flow_log_has_15min_aggregation(self, db):
        _seed_full_supply_side(db)
        run_dispatch_cycle(db, now=_NOW)

        flow = db.query(EnergyFlowLog).one()
        kw_to_kwh = WINDOW_MINUTES / 60.0
        # 光伏 30kW × 0.25h = 7.5kWh
        assert flow.pv_generation_kwh == pytest.approx(30.0 * kw_to_kwh)
        # 桩负荷 20kW × 0.25h = 5kWh
        assert flow.charger_load_kwh == pytest.approx(20.0 * kw_to_kwh)
        # 电网购电 10kW × 0.25h = 2.5kWh
        assert flow.grid_purchase_kwh == pytest.approx(10.0 * kw_to_kwh)
        # SOC 快照
        assert flow.soc_snapshot == pytest.approx(0.50)
        # 窗口对齐
        assert flow.window_start == _WIN_START


# ═══════════════════════════════════════════════════════════════
# 验收标准 4: 端到端全链路
# ═══════════════════════════════════════════════════════════════

class TestEndToEndChain:
    """光伏预测(telemetry) → 策略仲裁 → 功率预算 → 排车 → 流水落库 全链路"""

    def test_full_supply_to_demand_chain(self, db):
        # 1. 供给侧数据就绪 (站/模板/策略/遥测)
        _seed_full_supply_side(db)
        # 2. 需求侧企业车队就绪
        ent_id, vids = _seed_fleet(db, n_vehicles=4)

        # 3. 触发能量调度周期: 仲裁 + 预算 + 流水落库
        cycle = run_dispatch_cycle(db, now=_NOW)
        assert cycle["plans"] == 1
        assert cycle["flow_logs"] == 1

        # 验收1: plan 有功率预算
        plan = db.query(EnergyDispatchPlan).one()
        budget = float(plan.available_power_budget_kw)
        assert budget > 0

        # 验收3: flow_log 有 15min 聚合
        flow = db.query(EnergyFlowLog).one()
        assert flow.pv_generation_kwh is not None and flow.pv_generation_kwh > 0

        # 4. 协同桥接: 把预算下发给需求侧排车
        #    4 辆车 SOC 递增, 总需求 4×7=28kW < 预算 70, 全部满足
        states = [
            {"vehicle_id": vids[i], "current_soc": 0.15 + i * 0.1,
             "target_soc": 0.9, "max_power_kw": 7.0}
            for i in range(4)
        ]
        schedule = apply_power_budget_to_charging(
            db, station_id=1, enterprise_id=ent_id, vehicle_states=states,
            window_start=plan.window_start, window_end=plan.window_end,
        )

        # 验收2: 排车计划不超预算
        assert "error" not in schedule
        assert schedule["summary"]["allocated_power_kw"] <= budget
        assert schedule["summary"]["charging_vehicles"] == 4
        # 低 SOC 优先级最高 (priority==1)
        by_priority = sorted(schedule["entries"], key=lambda e: e["priority"])
        assert by_priority[0]["soc_start"] == 0.15
        assert by_priority[0]["priority"] == 1

        # 排车计划 + 条目落库
        assert db.query(ChargingSchedulePlan).count() == 1
        assert db.query(ChargingScheduleEntry).count() == 4

    def test_two_cycles_then_schedule_uses_latest_budget(self, db):
        """两轮调度: 协同桥接始终取站级最新 plan 的预算"""
        _seed_full_supply_side(db)
        ent_id, vids = _seed_fleet(db, n_vehicles=1)

        # 第一轮 12:00
        run_dispatch_cycle(db, now=datetime(2026, 8, 1, 12, 7))
        plan1 = db.query(EnergyDispatchPlan).one()

        # 第二轮 12:15 (窗口后移)
        run_dispatch_cycle(db, now=datetime(2026, 8, 1, 12, 22))
        assert db.query(EnergyDispatchPlan).count() == 2
        latest = (
            db.query(EnergyDispatchPlan)
            .order_by(EnergyDispatchPlan.window_start.desc())
            .first()
        )
        assert latest.window_start == datetime(2026, 8, 1, 12, 15)
        assert latest.id != plan1.id

        states = [{"vehicle_id": vids[0], "current_soc": 0.2,
                   "target_soc": 0.9, "max_power_kw": 7.0}]
        result = apply_power_budget_to_charging(
            db, station_id=1, enterprise_id=ent_id, vehicle_states=states,
            window_start=latest.window_start,
            window_end=latest.window_start + timedelta(minutes=WINDOW_MINUTES),
        )
        # 协同桥接取的是最新 plan
        assert result["power_budget_source"]["plan_id"] == latest.id

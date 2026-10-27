"""
P1-3 celery beat 15min 能量调度任务 + 能量流水落库 测试 (卡片 a76fac6b)

覆盖:
- dispatch_cycle 任务被 celery_app 识别 (注册名 + 在 beat_schedule 中可见 + 15min 周期)
- 现有 beat 任务不受影响 (9 个已有任务名仍在 beat_schedule)
- run_dispatch_cycle 手动调用 (内存 DB): 验证写入 EnergyDispatchPlan + EnergyFlowLog
- 无启用策略场站时跳过 (不报错, 不写记录)
- 正常调度 1 站 (同向充电合成)
- 仲裁裁剪场景 (SOC 超上限 → 充电被裁剪为 idle)

纯 DB 单元测试: 自建 sqlite 内存库 + create_all, 不走 conftest 的 RBAC client 链路
(autouse 的 _auth_module_level_client 仅对顶层定义 client=TestClient(...) 的模块生效, 本模块零开销)。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger as SA_BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# sqlite 下 BigInteger PK 自增适配 (对齐 tests/conftest.py 既有模式:
# 钩子让 BIGINT → INTEGER, 使单列 INTEGER PRIMARY KEY 成为 rowid 别名自增)。
# conftest 的同名钩子定义在 client fixture 内部, 本模块用独立内存库, 需自行注册。
@compiles(SA_BigInteger, "sqlite")
def _compile_bigint_sqlite(element, compiler, **kw):
    return "INTEGER"


from app.core.celery_app import celery_app
from app.core.database import Base
from app.models.energy_strategy import (
    EnergyDispatchPlan,
    EnergyFlowLog,
    EnergyPricePeriod,
    EnergyPriceTemplate,
    StationEnergyStrategy,
)
from app.models.pricing_v2 import PeriodType
from app.models.station import Station
from app.models.telemetry_v2 import TelemetryBattery, TelemetryCharger, TelemetryPV
from app.tasks.energy_tasks import POWER_FACTOR_DEFAULT, WINDOW_MINUTES, dispatch_cycle, run_dispatch_cycle


# ═══════════════════════════════════════════════════════════════
# Fixtures: 自建内存 DB
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


_NOW = datetime(2026, 8, 1, 12, 7, 0)  # 周六中午, window_start 应 floor 到 12:00


def _seed_station(db, station_id=1, team_id=100, province="四川"):
    st = Station(id=station_id, name=f"测试站{station_id}", code=f"ST{station_id:04d}",
                 team_id=team_id, province=province)
    db.add(st)
    db.flush()
    return st


def _seed_price_template(db, station_id, team_id=100, price=0.30, period_type=PeriodType.VALLEY):
    """建当前生效模板 + 一个覆盖全天的时段 (便于测试任意 now 都命中)"""
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


def _seed_cross_midnight_template(db, station_id, team_id=100, price=0.30):
    """跨午夜谷段模板: valley 22:00-08:00 (浙江/四川夜间谷段形态, 卡 fd59ac1c)"""
    tpl = EnergyPriceTemplate(
        province="四川", version=1, effective_from=datetime(2026, 1, 1).date(),
        effective_until=None, is_active=True, team_id=team_id,
    )
    db.add(tpl)
    db.flush()
    period = EnergyPricePeriod(
        template_id=tpl.id, period_type=PeriodType.VALLEY,
        start_time=datetime(2026, 1, 1, 22, 0).time(),
        end_time=datetime(2026, 1, 1, 8, 0).time(),
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
            "boosting": {"enabled": False},  # 关增容, 避免与充电反向冲突
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


# ═══════════════════════════════════════════════════════════════
# celery_app 注册 + beat_schedule
# ═══════════════════════════════════════════════════════════════

class TestTaskRegistration:
    """dispatch_cycle 在 celery_app 中正确注册 + beat 调度"""

    def test_task_name(self):
        assert dispatch_cycle.name == "energy.dispatch_cycle"

    def test_task_registered_in_celery_app(self):
        # 顶部 import 触发 @celery_app.task 注册
        assert "energy.dispatch_cycle" in celery_app.tasks

    def test_in_beat_schedule(self):
        assert "energy-dispatch-cycle" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["energy-dispatch-cycle"]
        assert entry["task"] == "energy.dispatch_cycle"
        # 15min 周期: crontab(minute='*/15') → {0,15,30,45}
        assert set(entry["schedule"].minute) == {0, 15, 30, 45}
        assert entry["options"].get("queue") == "default"

    def test_existing_beat_tasks_preserved(self):
        """现有 9 个 beat 任务名仍存在, 不受新增影响"""
        expected = {
            "daily-health-report", "weekly-data-cleanup", "hourly-fault-prediction",
            "carbon-daily-aggregate", "carbon-monthly-summary", "settlement-daily",
            "settlement-reconcile", "revenue-daily-aggregate",
            "station-daily-metrics-aggregate",
        }
        assert expected <= set(celery_app.conf.beat_schedule.keys())


# ═══════════════════════════════════════════════════════════════
# run_dispatch_cycle: 手动调用 (内存 DB)
# ═══════════════════════════════════════════════════════════════

class TestRunDispatchCycle:
    """run_dispatch_cycle 纯函数: 读策略+遥测 → 仲裁 → 落库"""

    def test_no_active_stations_skips(self, db):
        """空库: 无启用策略场站 → 跳过, 不报错, 不写记录"""
        result = run_dispatch_cycle(db, now=_NOW)
        assert result["stations"] == 0
        assert result["plans"] == 0
        assert result["flow_logs"] == 0
        assert db.query(EnergyDispatchPlan).count() == 0
        assert db.query(EnergyFlowLog).count() == 0

    def test_inactive_strategy_skipped(self, db):
        """策略 is_active=False → 该站跳过"""
        _seed_station(db, station_id=1)
        _seed_strategy(db, station_id=1, is_active=False)
        result = run_dispatch_cycle(db, now=_NOW)
        assert result["stations"] == 0
        assert db.query(EnergyDispatchPlan).count() == 0

    def test_dispatch_one_station_charge(self, db):
        """正常调度 1 站: 低谷电价 + 光伏余电 → 同向充电合成, 落 plan + flow"""
        _seed_station(db, station_id=1)
        tpl = _seed_price_template(db, station_id=1, price=0.30)  # 低谷
        _seed_strategy(db, station_id=1, template_id=tpl.id)
        _seed_telemetry(db, station_id=1, pv_kw=30.0, soc_pct=50.0, charger_kw=20.0)

        result = run_dispatch_cycle(db, now=_NOW)
        assert result["stations"] == 1
        assert result["plans"] == 1
        assert result["flow_logs"] == 1

        plan = db.query(EnergyDispatchPlan).one()
        # window floor 到 15min
        assert plan.window_start == datetime(2026, 8, 1, 12, 0)
        assert plan.window_end == datetime(2026, 8, 1, 12, 15)
        # 仲裁: arbitrage(低谷充50) + solar_absorb(余电充30) 同向充电, MAX 取 50
        assert plan.ess_charge_kw == pytest.approx(50.0)
        assert plan.ess_discharge_kw == 0.0
        assert plan.price_template_id == tpl.id
        # 决策日志落 JSON
        assert plan.winning_strategies is not None
        assert "arbitrage" in (plan.decision_reason or "")
        # 变压器预算: 100kVA*0.9 + pv30 - ess_charge50 = 70
        assert plan.available_power_budget_kw == pytest.approx(
            100.0 * POWER_FACTOR_DEFAULT + 30.0 - 50.0)

        flow = db.query(EnergyFlowLog).one()
        # telemetry 聚合: 瞬时功率 * (15/60)
        kw_to_kwh = WINDOW_MINUTES / 60.0
        assert flow.pv_generation_kwh == pytest.approx(30.0 * kw_to_kwh)
        assert flow.charger_load_kwh == pytest.approx(20.0 * kw_to_kwh)
        assert flow.grid_purchase_kwh == pytest.approx(10.0 * kw_to_kwh)
        assert flow.soc_snapshot == pytest.approx(0.50)

    def test_dispatch_same_window_twice_flow_idempotent(self, db):
        """卡 113e313b: 同窗口跑两次 (acks_late 重投递) → plan/flow 各仅 1 行"""
        _seed_station(db, station_id=1)
        tpl = _seed_price_template(db, station_id=1, price=0.30)
        _seed_strategy(db, station_id=1, template_id=tpl.id)
        _seed_telemetry(db, station_id=1, pv_kw=30.0, soc_pct=50.0)

        run_dispatch_cycle(db, now=_NOW)
        db.commit()
        # 同窗口重跑 (模拟 worker commit 后被杀重投递)
        run_dispatch_cycle(db, now=_NOW)
        db.commit()

        assert db.query(EnergyDispatchPlan).count() == 1
        assert db.query(EnergyFlowLog).count() == 1

    def test_dispatch_multiple_stations(self, db):
        """多站并行调度: 各站独立落 plan + flow"""
        for sid in (1, 2):
            _seed_station(db, station_id=sid, team_id=100 + sid)
            tpl = _seed_price_template(db, station_id=sid, team_id=100 + sid, price=0.30)
            _seed_strategy(db, station_id=sid, team_id=100 + sid, template_id=tpl.id)
            _seed_telemetry(db, station_id=sid, pv_kw=20.0, soc_pct=40.0)

        result = run_dispatch_cycle(db, now=_NOW)
        assert result["stations"] == 2
        assert result["plans"] == 2
        assert result["flow_logs"] == 2
        assert db.query(EnergyDispatchPlan).count() == 2

    def test_arbitration_clip_soc_ceiling(self, db):
        """仲裁裁剪场景: SOC=0.95 超上限 → 充电被裁剪为 idle, power=0"""
        _seed_station(db, station_id=1)
        tpl = _seed_price_template(db, station_id=1, price=0.30)  # 低谷 → 触发充电 advice
        _seed_strategy(db, station_id=1, template_id=tpl.id)
        _seed_telemetry(db, station_id=1, soc_pct=95.0)  # SOC 超上限

        result = run_dispatch_cycle(db, now=_NOW)
        assert result["plans"] == 1

        plan = db.query(EnergyDispatchPlan).one()
        # 硬约束裁剪: SOC 高于上限禁止充电 → idle, 0
        assert plan.ess_charge_kw == 0.0
        assert plan.ess_discharge_kw == 0.0
        # 决策日志记录裁剪原因
        assert plan.decision_reason is not None
        assert "上限" in plan.decision_reason or "禁止充电" in plan.decision_reason

    def test_no_price_template_still_runs(self, db):
        """无电价模板 (price_template_id=None): 套利不触发, 但消纳/流水仍落库"""
        _seed_station(db, station_id=1)
        _seed_strategy(db, station_id=1, template_id=None)  # 无模板
        _seed_telemetry(db, station_id=1, pv_kw=30.0, soc_pct=50.0)

        result = run_dispatch_cycle(db, now=_NOW)
        assert result["plans"] == 1
        plan = db.query(EnergyDispatchPlan).one()
        assert plan.price_template_id is None
        # 光伏余电消纳 advice 仍产生充电指令
        assert plan.ess_charge_kw is not None


# ═══════════════════════════════════════════════════════════════
# _current_grid_price 时区 + 跨午夜时段 (卡 fd59ac1c)
# ═══════════════════════════════════════════════════════════════

from app.tasks.energy_tasks import _current_grid_price  # noqa: E402
from app.tasks.tz_utils import to_aware_biz_tz  # noqa: E402


class TestCurrentGridPriceTzAndCrossMidnight:
    """时区错位 8h + 跨午夜谷段 (start>end) 永不命中两缺陷回归"""

    def test_cross_midnight_hit_naive_biz_wall(self, db):
        """上海 23:30 (naive 业务墙钟) 命中 22:00-08:00 谷段 → 触发套利低谷充电"""
        _seed_station(db, station_id=1)
        tpl = _seed_cross_midnight_template(db, station_id=1, price=0.30)
        _seed_strategy(db, station_id=1, template_id=tpl.id)
        _seed_telemetry(db, station_id=1, soc_pct=50.0)

        now = datetime(2026, 8, 1, 23, 30)
        assert _current_grid_price(db, tpl.id, now) == pytest.approx(0.30)

        result = run_dispatch_cycle(db, now=now)
        assert result["plans"] == 1
        plan = db.query(EnergyDispatchPlan).one()
        assert plan.ess_charge_kw > 0
        assert "arbitrage" in (plan.decision_reason or "")

    def test_cross_midnight_hit_aware_utc(self, db):
        """UTC 15:30 = 上海 23:30, aware 换算后同样命中谷段 (验证未退化)"""
        _seed_station(db, station_id=1)
        tpl = _seed_cross_midnight_template(db, station_id=1, price=0.30)
        _seed_strategy(db, station_id=1, template_id=tpl.id)
        _seed_telemetry(db, station_id=1, soc_pct=50.0)

        now = datetime(2026, 8, 1, 15, 30, tzinfo=timezone.utc)
        assert _current_grid_price(db, tpl.id, now) == pytest.approx(0.30)

        result = run_dispatch_cycle(db, now=now)
        plan = db.query(EnergyDispatchPlan).one()
        assert plan.ess_charge_kw > 0
        assert "arbitrage" in (plan.decision_reason or "")

    def test_aware_utc_noon_hits_period_not_misaligned(self, db):
        """UTC 04:00 = 上海正午: naive-UTC 旧口径会错配; 归一后正午命中全日段"""
        _seed_station(db, station_id=1)
        tpl = _seed_price_template(db, station_id=1, price=0.45)
        now = datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc)  # 上海 12:00
        assert _current_grid_price(db, tpl.id, now) == pytest.approx(0.45)

    def test_cross_midnight_daytime_miss(self, db):
        """上海正午 12:00 不应命中 22:00-08:00 谷段 → None"""
        _seed_station(db, station_id=1)
        tpl = _seed_cross_midnight_template(db, station_id=1, price=0.30)
        for now in (
            datetime(2026, 8, 1, 12, 0),                                   # naive 业务墙钟
            datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),               # = 上海 12:00
        ):
            assert _current_grid_price(db, tpl.id, now) is None

    def test_effective_date_uses_biz_day(self, db):
        """上海 8/1 00:30 (UTC 7/31 16:30): 业务日 8/1 越过 effective_from=8/1 生效"""
        tpl = EnergyPriceTemplate(
            province="四川", version=1, effective_from=datetime(2026, 8, 1).date(),
            effective_until=None, is_active=True, team_id=100,
        )
        db.add(tpl)
        db.flush()
        db.add(EnergyPricePeriod(
            template_id=tpl.id, period_type=PeriodType.VALLEY,
            start_time=datetime(2026, 1, 1, 0, 0).time(),
            end_time=datetime(2026, 1, 1, 23, 59).time(),
            purchase_price=Decimal("0.20"),
        ))
        db.flush()
        now = datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)  # 上海 8/1 00:30
        assert _current_grid_price(db, tpl.id, now) == pytest.approx(0.20)

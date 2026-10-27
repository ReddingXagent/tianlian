"""EnergyFlowPlanner 单元测试 — 能量流优先级链 (SPEC §3)

纯计算模块, 无 DB/外部依赖。覆盖:
- FlowStage 枚举 + DEFAULT_CHAIN 顺序
- EnergyFlowInput/Result 数据结构
- 各环节计算: PV_DIRECT / PV_TO_ESS / EXPORT / ESS_DISCHARGE / GRID_BACKUP
- SOC 底线/上限约束, 防逆流 (allow_export), 弃光保护
- 链重排, 环节开关 (disable), 环节限参 (set_cap), from_config 解析
"""
import pytest

from app.services.charging.energy_flow import (
    DEFAULT_CHAIN,
    EnergyFlowInput,
    EnergyFlowPlanner,
    EnergyFlowResult,
    FlowStage,
)


def _inp(**kw):
    """构造 EnergyFlowInput, pv/load/soc 必填, 其余默认。"""
    base = dict(pv_output_kw=0.0, charger_load_kw=0.0, soc=0.5)
    base.update(kw)
    return EnergyFlowInput(**base)


# ─── 数据结构 / 枚举 ───

class TestEnumsAndDefaults:
    def test_flow_stage_values(self):
        assert FlowStage.PV_DIRECT.value == "pv_direct"
        assert FlowStage.PV_TO_ESS.value == "pv_to_ess"
        assert FlowStage.EXPORT_TO_GRID.value == "export_to_grid"
        assert FlowStage.ESS_DISCHARGE.value == "ess_discharge"
        assert FlowStage.GRID_BACKUP.value == "grid_backup"

    def test_default_chain_order(self):
        """默认链: PV_DIRECT → PV_TO_ESS → EXPORT → ESS_DISCHARGE → GRID_BACKUP。"""
        assert DEFAULT_CHAIN == [
            FlowStage.PV_DIRECT, FlowStage.PV_TO_ESS, FlowStage.EXPORT_TO_GRID,
            FlowStage.ESS_DISCHARGE, FlowStage.GRID_BACKUP,
        ]

    def test_input_defaults(self):
        inp = EnergyFlowInput(pv_output_kw=10, charger_load_kw=5, soc=0.5)
        assert inp.soc_floor == 0.10
        assert inp.soc_ceiling == 0.90
        assert inp.ess_charge_cap_kw == 0.0
        assert inp.ess_discharge_cap_kw == 0.0
        assert inp.allow_export is False

    def test_result_defaults(self):
        r = EnergyFlowResult()
        assert r.pv_direct_kw == 0.0
        assert r.grid_export_kw == 0.0
        assert r.curtailed_kw == 0.0
        assert r.unmet_load_kw == 0.0
        assert r.stages_log == []


# ─── 各环节计算 ───

class TestPVDirect:
    def test_pv_direct_only(self):
        # 光伏充足直供负载, 余电无储能能力 → 弃光
        planner = EnergyFlowPlanner()  # 默认链, 上网关
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=50, soc=0.5))
        assert r.pv_direct_kw == 50.0
        assert r.pv_to_ess_kw == 0.0  # ess_charge_cap=0
        assert r.curtailed_kw == 50.0  # 余电无处去
        assert r.unmet_load_kw == 0.0

    def test_pv_less_than_load(self):
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=30, charger_load_kw=100, soc=0.05,
                              ess_discharge_cap_kw=0))
        assert r.pv_direct_kw == 30.0
        # SOC 低于底线 → 储能不放; 电网兜底补缺口
        assert r.ess_discharge_kw == 0.0
        assert r.grid_purchase_kw == 70.0


class TestPVToESS:
    def test_pv_excess_charges_ess(self):
        # 余电储能: 光伏 > 负载, SOC 低于上限
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.5,
                              ess_charge_cap_kw=50))
        assert r.pv_direct_kw == 30.0
        assert r.pv_to_ess_kw == 50.0  # min(余电70, 充电能力50)
        assert r.curtailed_kw == 20.0

    def test_pv_to_ess_blocked_by_ceiling(self):
        # SOC >= 上限 → 不充电, 余电全弃
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.95,
                              soc_ceiling=0.90, ess_charge_cap_kw=50))
        assert r.pv_to_ess_kw == 0.0
        assert r.curtailed_kw == 70.0

    def test_pv_to_ess_blocked_by_zero_cap(self):
        # 储能充电能力为 0 (默认) → 不充电
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.5,
                              ess_charge_cap_kw=0))
        assert r.pv_to_ess_kw == 0.0
        assert r.curtailed_kw == 70.0


class TestExportAndCurtailment:
    def test_curtailed_when_export_disabled(self):
        # 防逆流: allow_export=False → 余电上网环节关 → 弃光
        planner = EnergyFlowPlanner(allow_export=False)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.5,
                              ess_charge_cap_kw=10))
        assert r.grid_export_kw == 0.0
        assert r.curtailed_kw == 60.0  # 100-30-10

    def test_export_when_allowed(self):
        # planner + input 双方均允许上网 → 余电上网, 无弃光
        planner = EnergyFlowPlanner(allow_export=True)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.95,
                              soc_ceiling=0.90, ess_charge_cap_kw=50, allow_export=True))
        assert r.pv_direct_kw == 30.0
        assert r.pv_to_ess_kw == 0.0  # SOC 超上限不充
        assert r.grid_export_kw == 70.0
        assert r.curtailed_kw == 0.0

    def test_export_blocked_by_input_flag(self):
        # planner 允许但 inp 防逆流 → 上网不触发
        planner = EnergyFlowPlanner(allow_export=True)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.95,
                              soc_ceiling=0.90, ess_charge_cap_kw=50, allow_export=False))
        assert r.grid_export_kw == 0.0
        assert r.curtailed_kw == 70.0


class TestESSDischarge:
    def test_ess_discharge_covers_gap(self):
        # 光伏不足 → 储能放电补负载, 不足部分电网兜底
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=20, charger_load_kw=100, soc=0.8,
                              ess_charge_cap_kw=0, ess_discharge_cap_kw=50))
        assert r.pv_direct_kw == 20.0
        assert r.ess_discharge_kw == 50.0  # 受放电能力限制
        assert r.grid_purchase_kw == 30.0  # 100-20-50

    def test_ess_discharge_blocked_by_floor(self):
        # SOC <= 底线 → 储能禁止放电, 全靠电网
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=20, charger_load_kw=100, soc=0.05,
                              soc_floor=0.10, ess_discharge_cap_kw=50))
        assert r.ess_discharge_kw == 0.0
        assert r.grid_purchase_kw == 80.0


class TestGridBackup:
    def test_grid_backup_covers_remaining(self):
        planner = EnergyFlowPlanner()
        r = planner.plan(_inp(pv_output_kw=0, charger_load_kw=100, soc=0.05,
                              ess_discharge_cap_kw=50))
        assert r.ess_discharge_kw == 0.0  # SOC 低不放
        assert r.grid_purchase_kw == 100.0
        assert r.unmet_load_kw == 0.0

    def test_grid_backup_disabled_creates_unmet(self):
        # 电网兜底关 → 剩余缺口计入 unmet_load
        planner = EnergyFlowPlanner().disable(FlowStage.GRID_BACKUP)
        r = planner.plan(_inp(pv_output_kw=20, charger_load_kw=100, soc=0.05,
                              ess_discharge_cap_kw=50))
        assert r.grid_purchase_kw == 0.0
        assert r.unmet_load_kw == 80.0


# ─── 链编排 / 配置 ───

class TestChainConfig:
    def test_chain_reorder_ess_before_pv_direct(self):
        # 链重排: 储能放电排到光伏直供之前 (SPEC §3 顺序可调)
        chain = [FlowStage.ESS_DISCHARGE, FlowStage.PV_DIRECT, FlowStage.PV_TO_ESS, FlowStage.GRID_BACKUP]
        planner = EnergyFlowPlanner(chain=chain)
        r = planner.plan(_inp(pv_output_kw=50, charger_load_kw=80, soc=0.5,
                              ess_charge_cap_kw=0, ess_discharge_cap_kw=40))
        # 储能先放: min(负载80, 放电能力40)=40; 剩余负载40
        assert r.ess_discharge_kw == 40.0
        # 光伏直供: min(光伏50, 剩余负载40)=40; 余电10
        assert r.pv_direct_kw == 40.0
        assert r.curtailed_kw == 10.0
        assert r.unmet_load_kw == 0.0

    def test_disable_stage_marks_skipped(self):
        planner = EnergyFlowPlanner().disable(FlowStage.PV_TO_ESS)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.5,
                              ess_charge_cap_kw=50))
        assert r.pv_to_ess_kw == 0.0
        assert r.curtailed_kw == 70.0
        # stages_log 中 PV_TO_ESS 标记 skipped:disabled
        ess_log = next(e for e in r.stages_log if e["stage"] == "pv_to_ess")
        assert ess_log.get("skipped") == "disabled"

    def test_set_cap_clamps_pv_direct(self):
        planner = EnergyFlowPlanner().set_cap(FlowStage.PV_DIRECT, 20)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=100, soc=0.5))
        assert r.pv_direct_kw == 20.0  # 受环节限参裁剪

    def test_fluent_api_returns_self(self):
        planner = EnergyFlowPlanner()
        assert planner.disable(FlowStage.GRID_BACKUP) is planner
        assert planner.enable(FlowStage.GRID_BACKUP) is planner
        assert planner.set_cap(FlowStage.PV_DIRECT, 10) is planner
        assert FlowStage.GRID_BACKUP not in planner._disabled


class TestFromConfig:
    def test_none_config_uses_default(self):
        planner = EnergyFlowPlanner.from_config(None)
        assert planner._chain == DEFAULT_CHAIN
        assert planner._allow_export is False  # 默认上网关

    def test_empty_stages_uses_default(self):
        planner = EnergyFlowPlanner.from_config({})
        assert planner._chain == DEFAULT_CHAIN

    def test_custom_config(self):
        config = {"stages": [
            {"stage": "pv_direct", "enabled": True, "priority": 1, "power_cap_kw": 50},
            {"stage": "pv_to_ess", "enabled": True, "priority": 2},
            {"stage": "export_to_grid", "enabled": True, "priority": 3},
            {"stage": "ess_discharge", "enabled": True, "priority": 4},
            {"stage": "grid_backup", "enabled": False, "priority": 5},
        ]}
        planner = EnergyFlowPlanner.from_config(config)
        assert planner._chain[0] is FlowStage.PV_DIRECT
        assert planner._allow_export is True  # export 显式 enabled
        assert FlowStage.GRID_BACKUP in planner._disabled
        assert planner._caps[FlowStage.PV_DIRECT] == 50.0

    def test_config_export_disabled(self):
        config = {"stages": [
            {"stage": "pv_direct", "enabled": True, "priority": 1},
            {"stage": "export_to_grid", "enabled": False, "priority": 2},
        ]}
        planner = EnergyFlowPlanner.from_config(config)
        assert planner._allow_export is False
        assert FlowStage.EXPORT_TO_GRID in planner._disabled

    def test_config_priority_ordering(self):
        # priority 乱序输入 → 按 priority 排序构建链
        config = {"stages": [
            {"stage": "grid_backup", "enabled": True, "priority": 1},
            {"stage": "pv_direct", "enabled": True, "priority": 2},
        ]}
        planner = EnergyFlowPlanner.from_config(config)
        assert planner._chain[0] is FlowStage.GRID_BACKUP
        assert planner._chain[1] is FlowStage.PV_DIRECT


# ─── 综合场景 ───

def test_full_scenario_pv_surplus_with_storage_and_export():
    """光伏充足: 直供 → 充储能 → 上网, 全链路无弃光无缺口。"""
    planner = EnergyFlowPlanner(allow_export=True)
    r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=30, soc=0.5,
                          ess_charge_cap_kw=40, ess_discharge_cap_kw=40, allow_export=True))
    assert r.pv_direct_kw == 30.0
    assert r.pv_to_ess_kw == 40.0   # 余电70, 充电能力40
    assert r.grid_export_kw == 30.0  # 剩余余电上网
    assert r.ess_discharge_kw == 0.0
    assert r.grid_purchase_kw == 0.0
    assert r.curtailed_kw == 0.0
    assert r.unmet_load_kw == 0.0
    # stages_log 覆盖全链 5 环节
    assert len(r.stages_log) == 5


# ─── 异常分支 ───

def _raise_runtime(*args, **kwargs):
    raise RuntimeError("forced failure")


class _BadFloat:
    """真值对象, 但 float() 抛 ValueError, 触发 plan 入口数值守卫。"""
    def __bool__(self):
        return True

    def __float__(self):
        raise ValueError("bad float")


class TestExceptionBranches:
    def test_from_config_invalid_stage_falls_back_to_default(self):
        """非法 stage 名 → FlowStage() ValueError → except → 默认链 + 上网关。"""
        bad = {"stages": [{"stage": "not_a_real_stage", "enabled": True, "priority": 1}]}
        planner = EnergyFlowPlanner.from_config(bad)
        assert planner._chain == DEFAULT_CHAIN
        assert planner._allow_export is False

    def test_set_cap_invalid_string_ignored(self):
        """非数值字符串 → float() ValueError → 警告忽略, 限参不写入。"""
        planner = EnergyFlowPlanner()
        result = planner.set_cap(FlowStage.PV_DIRECT, "not-a-number")
        assert result is planner
        assert FlowStage.PV_DIRECT not in planner._caps

    def test_set_cap_typeerror_ignored(self):
        """无 __float__ 的对象 → float() TypeError → 警告忽略。"""
        planner = EnergyFlowPlanner()
        result = planner.set_cap(FlowStage.PV_DIRECT, object())
        assert result is planner
        assert FlowStage.PV_DIRECT not in planner._caps

    def test_plan_non_numeric_pv_falls_back_to_zero(self):
        """pv_output_kw 坏值 (float 抛) → 入口守卫兜底为 0, 不崩。"""
        planner = EnergyFlowPlanner()
        inp = EnergyFlowInput(pv_output_kw=_BadFloat(), charger_load_kw=10, soc=0.5)
        r = planner.plan(inp)
        assert isinstance(r, EnergyFlowResult)
        assert r.pv_direct_kw == 0.0  # pv 兜底 0, 无直供

    def test_plan_per_stage_exception_is_skipped(self, monkeypatch):
        """单环节 _run_stage 抛 → 跳过该环节, 链继续, 标记 skipped:error。"""
        planner = EnergyFlowPlanner()
        monkeypatch.setattr(planner, "_run_stage", _raise_runtime)
        r = planner.plan(_inp(pv_output_kw=100, charger_load_kw=50, soc=0.5))
        assert isinstance(r, EnergyFlowResult)
        assert any(e.get("skipped") == "error" for e in r.stages_log)

    def test_plan_outer_exception_returns_empty_result(self):
        """_chain 不可迭代 → for 抛 → 外层 except → 全零 EnergyFlowResult。"""
        planner = EnergyFlowPlanner()
        planner._chain = 123  # int 不可迭代
        r = planner.plan(_inp(pv_output_kw=10, charger_load_kw=5, soc=0.5))
        assert r.pv_direct_kw == 0.0
        assert r.curtailed_kw == 0.0
        assert r.unmet_load_kw == 0.0

    def test_run_stage_unknown_stage_returns_zero(self):
        """未知 stage 值 (无 if 命中) → 兜底 return 0.0。"""
        planner = EnergyFlowPlanner()
        result = planner._run_stage(
            "foreign_stage",
            _inp(pv_output_kw=10, charger_load_kw=5, soc=0.5),
            EnergyFlowResult(),
            10, 10, None,
        )
        assert result == 0.0

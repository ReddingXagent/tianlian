"""energy_strategy 光储充能量策略 6 张表 — P1-1 (卡片 469f03ac)

Revision ID: 202608010100
Revises: 202607310600
Create Date: 2026-08-01 01:00:00.000000

新建 6 张能量策略表:
- energy_price_template  : 省级购电价模板 (季节/两部制/余电上网, 平台级 team_id NULL 或团队级)
- energy_price_period    : 模板时段明细 (period_type 复用 pricing_v2.PeriodType: peak/shoulder/flat/valley)
- energy_price_spot      : 现货 96 节点 (仅建结构, P3 用)
- station_energy_strategy: 场站策略配置 (一站一策略, station_id 唯一)
- energy_dispatch_plan   : 15min 调度计划 (仲裁胜出策略 + 决策日志)
- energy_flow_log        : 能量流水 (大数据量, id BigInteger)

约定:
- team_id   = Integer    FK teams.id    (隔离键, 与 Station.team_id 同契约)
- station_id = BigInteger FK stations.id (与 Station.id 同类型, 防 BigInt 溢出)
- JSON 列用 sa.JSON (不用 Text 存 dict)
- PeriodType 复用 pricing_v2.py:20 已有枚举, 不重复定义

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的环境 (与 202607310500 同模式)。
PG/SQLite 双 dialect: period_type 用 sa.Enum(native_enum=False), 两方言都存 VARCHAR,
避免 PG native enum 的 drop 麻烦。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.pricing_v2 import PeriodType


# revision identifiers, used by Alembic.
revision: str = "202608010100"
down_revision: Union[str, Sequence[str], None] = "202607310600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema: 建 6 张能量策略表。"""
    bind = op.get_bind()

    # 1. energy_price_template — 省级购电价模板
    if not _has_table(bind, "energy_price_template"):
        op.create_table(
            "energy_price_template",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("province", sa.String(length=50), nullable=False, comment="省份"),
            sa.Column("version", sa.Integer(), nullable=False, comment="版本号"),
            sa.Column("effective_from", sa.Date(), nullable=False, comment="生效起始日期"),
            sa.Column("effective_until", sa.Date(), nullable=True, comment="失效日期, NULL=当前有效"),
            sa.Column("season_start_month", sa.Integer(), nullable=True, comment="旺季起始月(1-12)"),
            sa.Column("season_end_month", sa.Integer(), nullable=True, comment="旺季结束月(1-12)"),
            sa.Column(
                "allow_export_to_grid", sa.Boolean(), nullable=True,
                server_default=sa.text("false"), comment="余电上网(默认关)",
            ),
            sa.Column(
                "is_two_part_tariff", sa.Boolean(), nullable=True,
                server_default=sa.text("false"), comment="是否两部制电价",
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=True,
                server_default=sa.text("true"), comment="是否启用",
            ),
            sa.Column("team_id", sa.Integer(), nullable=True, comment="所属团队, NULL=平台级模板"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_energy_price_template_province", "energy_price_template", ["province"])
        op.create_index("ix_energy_price_template_effective_from", "energy_price_template", ["effective_from"])
        op.create_index("ix_energy_price_template_effective_until", "energy_price_template", ["effective_until"])
        op.create_index("ix_energy_price_template_team_id", "energy_price_template", ["team_id"])
        op.create_index(
            "ix_ept_province_effective", "energy_price_template",
            ["province", "effective_from", "effective_until"],
        )
        op.create_index("ix_ept_is_active", "energy_price_template", ["is_active"])

    # 2. energy_price_period — 模板时段明细
    if not _has_table(bind, "energy_price_period"):
        op.create_table(
            "energy_price_period",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False, comment="模板ID"),
            sa.Column(
                "period_type",
                sa.Enum(PeriodType, name="energy_period_type", native_enum=False),
                nullable=False, comment="时段类型: peak/shoulder/flat/valley",
            ),
            sa.Column("start_time", sa.Time(), nullable=False, comment="开始时间"),
            sa.Column("end_time", sa.Time(), nullable=False, comment="结束时间"),
            sa.Column("purchase_price", sa.Numeric(precision=10, scale=4), nullable=False, comment="购电单价(元/kWh)"),
            sa.Column("float_ratio", sa.Numeric(precision=6, scale=4), nullable=True, comment="浮动比例"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["template_id"], ["energy_price_template.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_energy_price_period_template_id", "energy_price_period", ["template_id"])
        op.create_index(
            "ix_epp_template_period", "energy_price_period", ["template_id", "period_type"],
        )

    # 3. energy_price_spot — 现货 96 节点 (结构, P3 用)
    if not _has_table(bind, "energy_price_spot"):
        op.create_table(
            "energy_price_spot",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("station_id", sa.BigInteger(), nullable=True, comment="场站ID"),
            sa.Column("team_id", sa.Integer(), nullable=True, comment="团队ID"),
            sa.Column("price_date", sa.Date(), nullable=True, comment="价格日期"),
            sa.Column("node_index", sa.Integer(), nullable=False, comment="节点序号(0-95)"),
            sa.Column("day_ahead_price", sa.Numeric(precision=10, scale=4), nullable=True, comment="日前价(元/kWh)"),
            sa.Column("realtime_price", sa.Numeric(precision=10, scale=4), nullable=True, comment="实时价(元/kWh)"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "station_id", "price_date", "node_index", name="uq_eps_station_date_node",
            ),
        )
        op.create_index("ix_energy_price_spot_station_id", "energy_price_spot", ["station_id"])
        op.create_index("ix_energy_price_spot_team_id", "energy_price_spot", ["team_id"])
        op.create_index("ix_energy_price_spot_price_date", "energy_price_spot", ["price_date"])

    # 4. station_energy_strategy — 场站策略配置 (一站一策略)
    if not _has_table(bind, "station_energy_strategy"):
        op.create_table(
            "station_energy_strategy",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("station_id", sa.BigInteger(), nullable=False, comment="场站ID(一站一策略)"),
            sa.Column("team_id", sa.Integer(), nullable=False, comment="团队ID(隔离键)"),
            sa.Column("price_template_id", sa.Integer(), nullable=True, comment="电价模板ID"),
            sa.Column(
                "scenario_preset", sa.String(length=50), nullable=True,
                comment="场景预设: fleet/public_fast/off_grid/v2g",
            ),
            sa.Column("transformer_capacity_kva", sa.Float(), nullable=True, comment="变压器容量(kVA)"),
            sa.Column("pv_capacity_kw", sa.Float(), nullable=True, comment="光伏容量(kWp)"),
            sa.Column("ess_capacity_kwh", sa.Float(), nullable=True, comment="储能容量(kWh)"),
            sa.Column("declared_demand_kw", sa.Float(), nullable=True, comment="申报需量(kW, 需量管理P2用)"),
            sa.Column("strategy_config", sa.JSON(), nullable=True, comment="各策略开关/阈值/优先级"),
            sa.Column("energy_flow_priority", sa.JSON(), nullable=True, comment="能量流优先级链编排"),
            sa.Column(
                "soc_floor", sa.Float(), nullable=False,
                server_default=sa.text("0.10"), comment="SOC下限(默认0.10)",
            ),
            sa.Column("soc_reserve_min", sa.Float(), nullable=True, comment="SOC预留下限"),
            sa.Column("soc_reserve_max", sa.Float(), nullable=True, comment="SOC预留上限"),
            sa.Column("max_daily_cycles", sa.Integer(), nullable=True, comment="日最大循环次数"),
            sa.Column(
                "is_active", sa.Boolean(), nullable=True,
                server_default=sa.text("true"), comment="是否启用",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["price_template_id"], ["energy_price_template.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("station_id", name="uq_ses_station_id"),
        )
        op.create_index("ix_station_energy_strategy_team_id", "station_energy_strategy", ["team_id"])

    # 5. energy_dispatch_plan — 15min 调度计划
    if not _has_table(bind, "energy_dispatch_plan"):
        op.create_table(
            "energy_dispatch_plan",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("station_id", sa.BigInteger(), nullable=True, comment="场站ID"),
            sa.Column("team_id", sa.Integer(), nullable=True, comment="团队ID(隔离键)"),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=False, comment="窗口开始(15min)"),
            sa.Column("window_end", sa.DateTime(timezone=True), nullable=False, comment="窗口结束(15min)"),
            sa.Column("price_template_id", sa.Integer(), nullable=True, comment="电价模板ID"),
            sa.Column("pv_setpoint_kw", sa.Float(), nullable=True, comment="光伏功率设定(kW)"),
            sa.Column("ess_charge_kw", sa.Float(), nullable=True, comment="储能充电功率(kW)"),
            sa.Column("ess_discharge_kw", sa.Float(), nullable=True, comment="储能放电功率(kW)"),
            sa.Column("grid_purchase_kw", sa.Float(), nullable=True, comment="电网购电功率(kW)"),
            sa.Column("grid_export_kw", sa.Float(), nullable=True, comment="电网上网功率(kW)"),
            sa.Column("available_power_budget_kw", sa.Float(), nullable=True, comment="下发需求侧功率预算(kW)"),
            sa.Column("winning_strategies", sa.JSON(), nullable=True, comment="仲裁胜出策略+决策日志"),
            sa.Column("decision_reason", sa.Text(), nullable=True, comment="决策原因"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["price_template_id"], ["energy_price_template.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_energy_dispatch_plan_station_id", "energy_dispatch_plan", ["station_id"])
        op.create_index("ix_energy_dispatch_plan_team_id", "energy_dispatch_plan", ["team_id"])
        op.create_index(
            "ix_edp_station_window", "energy_dispatch_plan", ["station_id", "window_start"],
        )
        op.create_index(
            "ix_edp_team_window", "energy_dispatch_plan", ["team_id", "window_start"],
        )

    # 6. energy_flow_log — 能量流水 (大数据量)
    if not _has_table(bind, "energy_flow_log"):
        op.create_table(
            "energy_flow_log",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("station_id", sa.BigInteger(), nullable=True, comment="场站ID"),
            sa.Column("team_id", sa.Integer(), nullable=True, comment="团队ID(隔离键)"),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=True, comment="窗口开始"),
            sa.Column("pv_generation_kwh", sa.Float(), nullable=True, comment="光伏发电量(kWh)"),
            sa.Column("pv_self_consumed_kwh", sa.Float(), nullable=True, comment="光伏自用电量(kWh)"),
            sa.Column("ess_charge_kwh", sa.Float(), nullable=True, comment="储能充电量(kWh)"),
            sa.Column("ess_discharge_kwh", sa.Float(), nullable=True, comment="储能放电量(kWh)"),
            sa.Column("grid_purchase_kwh", sa.Float(), nullable=True, comment="电网购电量(kWh)"),
            sa.Column("grid_export_kwh", sa.Float(), nullable=True, comment="电网上网量(kWh)"),
            sa.Column("charger_load_kwh", sa.Float(), nullable=True, comment="充电桩负荷(kWh)"),
            sa.Column("soc_snapshot", sa.Float(), nullable=True, comment="SOC快照"),
            sa.Column("cost_saving_yuan", sa.Numeric(precision=12, scale=2), nullable=True, comment="节省成本(元)"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_energy_flow_log_station_id", "energy_flow_log", ["station_id"])
        op.create_index("ix_energy_flow_log_team_id", "energy_flow_log", ["team_id"])
        op.create_index("ix_energy_flow_log_window_start", "energy_flow_log", ["window_start"])
        op.create_index(
            "ix_efl_station_window", "energy_flow_log", ["station_id", "window_start"],
        )
        op.create_index(
            "ix_efl_team_window", "energy_flow_log", ["team_id", "window_start"],
        )


def downgrade() -> None:
    """Downgrade schema: 删 6 张能量策略表 (反序以解 FK 依赖)。"""
    bind = op.get_bind()

    for table in (
        "energy_flow_log",
        "energy_dispatch_plan",
        "station_energy_strategy",
        "energy_price_spot",
        "energy_price_period",
        "energy_price_template",
    ):
        if _has_table(bind, table):
            op.drop_table(table)

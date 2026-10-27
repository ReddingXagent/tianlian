"""
光储充能量策略模型 - P1-1 (卡片 469f03ac)

6 张表:
1. EnergyPriceTemplate  - 省级购电价模板 (含季节/两部制/余电上网/平台级或团队级)
2. EnergyPricePeriod    - 模板时段明细 (复用 pricing_v2.PeriodType: peak/shoulder/flat/valley)
3. EnergyPriceSpot      - 现货 96 节点 (仅建结构, P3 用)
4. StationEnergyStrategy- 场站策略配置 (一站一策略)
5. EnergyDispatchPlan   - 15min 调度计划 (仲裁胜出策略 + 决策日志)
6. EnergyFlowLog        - 能量流水 (大数据量)

约定:
- PeriodType 复用 pricing_v2.py:20 已有枚举, 不重复定义。
- team_id = Integer FK teams.id (隔离键, 与 Station.team_id 同契约)。
- station_id = BigInteger FK stations.id (与 Station.id 同类型, 防 BigInt 溢出)。
- JSON 列用 SQLAlchemy JSON 类型 (不用 Text 存 dict)。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.pricing_v2 import PeriodType


class EnergyPriceTemplate(Base):
    """省级购电价模板 - 平台级(team_id NULL)或团队级"""
    __tablename__ = "energy_price_template"

    id = Column(Integer, primary_key=True, autoincrement=True)
    province = Column(String(50), nullable=False, index=True, comment="省份")
    version = Column(Integer, nullable=False, comment="版本号")
    effective_from = Column(Date, nullable=False, index=True, comment="生效起始日期")
    effective_until = Column(Date, nullable=True, index=True, comment="失效日期, NULL=当前有效")
    season_start_month = Column(Integer, nullable=True, comment="旺季起始月(1-12)")
    season_end_month = Column(Integer, nullable=True, comment="旺季结束月(1-12)")
    allow_export_to_grid = Column(Boolean, default=False, comment="余电上网(默认关)")
    is_two_part_tariff = Column(Boolean, default=False, comment="是否两部制电价")
    is_active = Column(Boolean, default=True, comment="是否启用")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="所属团队, NULL=平台级模板")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("ix_ept_province_effective", "province", "effective_from", "effective_until"),
        Index("ix_ept_is_active", "is_active"),
    )


class EnergyPricePeriod(Base):
    """模板时段明细 - 复用 PeriodType"""
    __tablename__ = "energy_price_period"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("energy_price_template.id"), nullable=False, index=True, comment="模板ID")
    # 卡 15a07d0f: native_enum=False 对齐迁移 202608010100 的双 dialect 设计
    # (双方言均存 VARCHAR); native 模式下 PG ORM INSERT 会 cast
    # ::energy_period_type, 而 CREATE TABLE 从未创建该 type → fresh 链崩。
    period_type = Column(SAEnum(PeriodType, name="energy_period_type", native_enum=False), nullable=False, comment="时段类型: peak/shoulder/flat/valley")
    start_time = Column(Time, nullable=False, comment="开始时间")
    end_time = Column(Time, nullable=False, comment="结束时间")
    purchase_price = Column(Numeric(10, 4), nullable=False, comment="购电单价(元/kWh)")
    float_ratio = Column(Numeric(6, 4), nullable=True, comment="浮动比例")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("ix_epp_template_period", "template_id", "period_type"),
    )


class EnergyPriceSpot(Base):
    """现货 96 节点电价 - 仅建结构, P3 用"""
    __tablename__ = "energy_price_spot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=True, index=True, comment="场站ID")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="团队ID")
    price_date = Column(Date, nullable=True, index=True, comment="价格日期")
    node_index = Column(Integer, nullable=False, comment="节点序号(0-95)")
    day_ahead_price = Column(Numeric(10, 4), nullable=True, comment="日前价(元/kWh)")
    realtime_price = Column(Numeric(10, 4), nullable=True, comment="实时价(元/kWh)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        UniqueConstraint("station_id", "price_date", "node_index", name="uq_eps_station_date_node"),
    )


class StationEnergyStrategy(Base):
    """场站策略配置 - 一站一策略"""
    __tablename__ = "station_energy_strategy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, unique=True, comment="场站ID(一站一策略)")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True, comment="团队ID(隔离键)")
    price_template_id = Column(Integer, ForeignKey("energy_price_template.id"), nullable=True, index=True, comment="电价模板ID")
    scenario_preset = Column(String(50), nullable=True, comment="场景预设: fleet/public_fast/off_grid/v2g")
    transformer_capacity_kva = Column(Float, nullable=True, comment="变压器容量(kVA)")
    pv_capacity_kw = Column(Float, nullable=True, comment="光伏容量(kWp)")
    ess_capacity_kwh = Column(Float, nullable=True, comment="储能容量(kWh)")
    declared_demand_kw = Column(Float, nullable=True, comment="申报需量(kW, 需量管理P2用)")
    strategy_config = Column(JSON, nullable=True, comment="各策略开关/阈值/优先级")
    energy_flow_priority = Column(JSON, nullable=True, comment="能量流优先级链编排")
    soc_floor = Column(Float, nullable=False, default=0.10, comment="SOC下限(默认0.10)")
    soc_reserve_min = Column(Float, nullable=True, comment="SOC预留下限")
    soc_reserve_max = Column(Float, nullable=True, comment="SOC预留上限")
    max_daily_cycles = Column(Integer, nullable=True, comment="日最大循环次数")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")


class EnergyDispatchPlan(Base):
    """调度计划 - 15min 窗口"""
    __tablename__ = "energy_dispatch_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=True, index=True, comment="场站ID")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="团队ID(隔离键)")
    window_start = Column(DateTime(timezone=True), nullable=False, comment="窗口开始(15min)")
    window_end = Column(DateTime(timezone=True), nullable=False, comment="窗口结束(15min)")
    price_template_id = Column(Integer, ForeignKey("energy_price_template.id"), nullable=True, index=True, comment="电价模板ID")
    pv_setpoint_kw = Column(Float, nullable=True, comment="光伏功率设定(kW)")
    ess_charge_kw = Column(Float, nullable=True, comment="储能充电功率(kW)")
    ess_discharge_kw = Column(Float, nullable=True, comment="储能放电功率(kW)")
    grid_purchase_kw = Column(Float, nullable=True, comment="电网购电功率(kW)")
    grid_export_kw = Column(Float, nullable=True, comment="电网上网功率(kW)")
    available_power_budget_kw = Column(Float, nullable=True, comment="下发需求侧功率预算(kW)")
    winning_strategies = Column(JSON, nullable=True, comment="仲裁胜出策略+决策日志")
    decision_reason = Column(Text, nullable=True, comment="决策原因")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        # 卡 97c83af9: 同窗口唯一约束防 beat 重叠/acks_late 重投递重复写 plan。
        # station_id 可 NULL(全平台)但调度仅按具体站写, NULL 行不受约束影响,
        # 具体站(station_id NOT NULL)重投递必撞约束 → 应用层回退覆盖。
        UniqueConstraint("station_id", "window_start", name="uq_edp_station_window"),
        Index("ix_edp_station_window", "station_id", "window_start"),
        Index("ix_edp_team_window", "team_id", "window_start"),
    )


class EnergyFlowLog(Base):
    """能量流水 - 大数据量"""
    __tablename__ = "energy_flow_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=True, index=True, comment="场站ID")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="团队ID(隔离键)")
    window_start = Column(DateTime(timezone=True), nullable=True, index=True, comment="窗口开始")
    pv_generation_kwh = Column(Float, nullable=True, comment="光伏发电量(kWh)")
    pv_self_consumed_kwh = Column(Float, nullable=True, comment="光伏自用电量(kWh)")
    ess_charge_kwh = Column(Float, nullable=True, comment="储能充电量(kWh)")
    ess_discharge_kwh = Column(Float, nullable=True, comment="储能放电量(kWh)")
    grid_purchase_kwh = Column(Float, nullable=True, comment="电网购电量(kWh)")
    grid_export_kwh = Column(Float, nullable=True, comment="电网上网量(kWh)")
    charger_load_kwh = Column(Float, nullable=True, comment="充电桩负荷(kWh)")
    soc_snapshot = Column(Float, nullable=True, comment="SOC快照")
    cost_saving_yuan = Column(Numeric(12, 2), nullable=True, comment="节省成本(元)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("ix_efl_station_window", "station_id", "window_start"),
        Index("ix_efl_team_window", "team_id", "window_start"),
    )

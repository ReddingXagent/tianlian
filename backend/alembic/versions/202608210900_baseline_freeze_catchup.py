"""baseline 冻结 catch-up: 6 缺表 + 9 缺索引幂等补齐 (卡 6f5a35a2 方案A)

Revision ID: 202608210900
Revises: 202608201000
Create Date: 2026-08-21 09:00:00.000000

0001 baseline 冻结为静态快照后 (基准 commit c0f535d1d 时期模型), 旧动态
baseline 曾经"顺手"吸收的模型漂移不再被建表: 以下 6 张表 / 9 个索引的模型
均在 c0f535d1d 之后新增, 且从未有过专属迁移 (历史全靠 Base.metadata
.create_all 在运行时兜底, 见 c4b8e2f9a1d0 的根因分析)。本迁移沿
c4b8e2f9a1d0 / f5a6b7c8d9e0 的 inspector 幂等风格补齐, 使冻结链
`alembic upgrade head` 的最终 schema 与当前模型名称级零漂移
(缺表 0 / 缺列 0 / 缺索引 0)。

  [缺表] 模型 / 引入时期
  runbooks                     58bb12433 2026-07-25
  inspection_templates/results inspection.py 扩展 (c0f535d1d 后)
  fund_pools + fund_pool_transactions  8f6c57f84 起完整成形于 c0f535d1d 后
  enterprise_device_grants     6ae734573 2026-08-08 (卡 a1468299)

  [缺索引] Column(index=True) 自动 ix_* 索引, 对应迁移只建了显式命名索引
  tenant_brands.ix_tenant_brands_team_id
  merchants.ix_merchants_team_id
  payment_orders.ix_payment_orders_business_order_no
  platform_fee_configs.ix_platform_fee_configs_team_id / _tenant_id
  occupancy_events.ix_occupancy_events_plate_number / _station_id
  invoice_requests.ix_invoice_requests_team_id / _user_id

生产 (PostgreSQL) 已由运行时 create_all 建过这些表 → 守卫全部跳过, 安全。
不包含 alter_column / drop_index 美化项: SQLite 需 batch 模式, 且属于
名称级校验之外的 nullability/索引冗余差异 (见
docs/migrations/0001-baseline-freeze-plan.md 「已知良性差异」)。

幂等可重入: sa.inspect() 探测存在性决定建/删, PG / SQLite 双方言一致。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608210900"
down_revision: Union[str, Sequence[str], None] = "202608201000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_index(bind, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return True  # 表都没有时交给建表流程, 单独的建索引跳过
    return any(i["name"] == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "inspection_templates"):
        op.create_table(
            "inspection_templates",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False, comment="模板名称"),
            sa.Column("description", sa.Text(), nullable=True, comment="模板描述"),
            sa.Column("items", sa.JSON(), nullable=True, comment="巡检项列表（JSON）"),
            sa.Column("device_types", sa.JSON(), nullable=True, comment="适用设备类型列表（JSON）"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="状态 active/inactive"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inspection_templates_id", "inspection_templates", ["id"], unique=False)

    if not _has_table(bind, "inspection_results"):
        op.create_table(
            "inspection_results",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="关联任务ID"),
            sa.Column("item_name", sa.String(length=200), nullable=False, comment="检查项名称"),
            sa.Column("item_value", sa.String(length=500), nullable=True, comment="实测值"),
            sa.Column("result", sa.String(length=20), nullable=False, comment="结果 normal/abnormal"),
            sa.Column("abnormal_desc", sa.Text(), nullable=True, comment="异常描述"),
            sa.Column("photo_url", sa.String(length=500), nullable=True, comment="照片URL"),
            sa.Column("recorded_at", sa.DateTime(), nullable=True, comment="记录时间"),
            sa.ForeignKeyConstraint(["task_id"], ["inspection_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inspection_results_id", "inspection_results", ["id"], unique=False)
        op.create_index("ix_inspection_results_task_id", "inspection_results", ["task_id"], unique=False)

    if not _has_table(bind, "runbooks"):
        op.create_table(
            "runbooks",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False, comment="模板名称"),
            sa.Column("category", sa.String(length=50), nullable=False, comment="设备类别"),
            sa.Column("alarm_type", sa.String(length=200), nullable=False, comment="告警匹配键"),
            sa.Column("description", sa.Text(), nullable=True, comment="模板描述"),
            sa.Column("steps", sa.JSON(), nullable=True, comment="执行步骤列表(JSON)"),
            sa.Column("status", sa.String(length=20), nullable=False, comment="状态 active/inactive"),
            sa.Column("version", sa.Integer(), nullable=False, comment="版本号"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index("ix_runbooks_id", "runbooks", ["id"], unique=False)

    if not _has_table(bind, "fund_pools"):
        op.create_table(
            "fund_pools",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("enterprise_id", sa.Integer(), nullable=True, comment="所属企业ID"),
            sa.Column("enterprise_name", sa.String(length=200), nullable=True, comment="企业名称(冗余, 便于前端展示)"),
            sa.Column("account_name", sa.String(length=100), nullable=False, comment="账户名称"),
            sa.Column("account_type", sa.String(length=50), nullable=False, comment="账户类型(运营账户/维修基金/备用金/保证金/结算账户)"),
            sa.Column("balance", sa.Numeric(precision=12, scale=2), nullable=False, comment="账户余额(元)"),
            sa.Column("status", sa.Enum("ACTIVE", "FROZEN", "INACTIVE", name="fundaccountstatus"), nullable=False, comment="账户状态"),
            sa.Column("bank_name", sa.String(length=100), nullable=True, comment="开户银行"),
            sa.Column("bank_account", sa.String(length=50), nullable=True, comment="银行账号"),
            sa.Column("currency", sa.String(length=10), nullable=False, comment="币种符号"),
            sa.Column("description", sa.Text(), nullable=True, comment="账户描述"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_fund_pool_enterprise", "fund_pools", ["enterprise_id"], unique=False)
        op.create_index("idx_fund_pool_status", "fund_pools", ["status"], unique=False)
        op.create_index("ix_fund_pools_enterprise_id", "fund_pools", ["enterprise_id"], unique=False)

    if not _has_table(bind, "fund_pool_transactions"):
        op.create_table(
            "fund_pool_transactions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("fund_pool_id", sa.Integer(), nullable=False, comment="资金账户ID"),
            sa.Column("transaction_type", sa.Enum("RECHARGE", "CONSUME", "REFUND", name="fundtransactiontype"), nullable=False, comment="流水类型"),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False, comment="发生金额(元)"),
            sa.Column("balance_before", sa.Numeric(precision=12, scale=2), nullable=True, comment="交易前余额"),
            sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=True, comment="交易后余额"),
            sa.Column("status", sa.Enum("PENDING", "SUCCESS", "FAILED", name="fundtransactionstatus"), nullable=False, comment="流水状态"),
            sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["fund_pool_id"], ["fund_pools.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_fund_txn_created", "fund_pool_transactions", ["created_at"], unique=False)
        op.create_index("idx_fund_txn_pool", "fund_pool_transactions", ["fund_pool_id"], unique=False)
        op.create_index("ix_fund_pool_transactions_fund_pool_id", "fund_pool_transactions", ["fund_pool_id"], unique=False)

    if not _has_table(bind, "enterprise_device_grants"):
        op.create_table(
            "enterprise_device_grants",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("enterprise_id", sa.Integer(), nullable=False, comment="被授权的车队(企业)"),
            sa.Column("station_id", sa.Integer(), nullable=False, comment="授权场站"),
            sa.Column("device_id", sa.BigInteger(), nullable=True, comment="NULL=整站授权(该站所有桩); 非空=桩级白名单"),
            sa.Column("note", sa.String(length=200), nullable=True, comment="授权备注"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_edg_enterprise", "enterprise_device_grants", ["enterprise_id"], unique=False)
        op.create_index("ix_edg_enterprise_station_device", "enterprise_device_grants", ["enterprise_id", "station_id", "device_id"], unique=True)
        op.create_index("ix_edg_station", "enterprise_device_grants", ["station_id"], unique=False)
        op.create_index("ix_enterprise_device_grants_device_id", "enterprise_device_grants", ["device_id"], unique=False)
        op.create_index("ix_enterprise_device_grants_enterprise_id", "enterprise_device_grants", ["enterprise_id"], unique=False)
        op.create_index("ix_enterprise_device_grants_station_id", "enterprise_device_grants", ["station_id"], unique=False)

    # 9 个 Column(index=True) 自动命名 ix_* 索引: 迁移建表时只建了显式命名索引
    _index_catchup = [
        ("ix_tenant_brands_team_id", "tenant_brands", ["team_id"], False),
        ("ix_merchants_team_id", "merchants", ["team_id"], False),
        ("ix_payment_orders_business_order_no", "payment_orders", ["business_order_no"], False),
        ("ix_platform_fee_configs_team_id", "platform_fee_configs", ["team_id"], False),
        ("ix_platform_fee_configs_tenant_id", "platform_fee_configs", ["tenant_id"], False),
        ("ix_occupancy_events_plate_number", "occupancy_events", ["plate_number"], False),
        ("ix_occupancy_events_station_id", "occupancy_events", ["station_id"], False),
        ("ix_invoice_requests_team_id", "invoice_requests", ["team_id"], False),
        ("ix_invoice_requests_user_id", "invoice_requests", ["user_id"], False),
    ]
    for name, table, cols, unique in _index_catchup:
        if not _has_index(bind, table, name):
            op.create_index(name, table, cols, unique=unique)


def downgrade() -> None:
    """Downgrade schema: 仅删本迁移新建的索引, 保留表 (与 c4b8e2f9a1d0 同策略,
    避免误删生产运行时数据)。"""
    bind = op.get_bind()
    _index_catchup = [
        ("ix_tenant_brands_team_id", "tenant_brands"),
        ("ix_merchants_team_id", "merchants"),
        ("ix_payment_orders_business_order_no", "payment_orders"),
        ("ix_platform_fee_configs_team_id", "platform_fee_configs"),
        ("ix_platform_fee_configs_tenant_id", "platform_fee_configs"),
        ("ix_occupancy_events_plate_number", "occupancy_events"),
        ("ix_occupancy_events_station_id", "occupancy_events"),
        ("ix_invoice_requests_team_id", "invoice_requests"),
        ("ix_invoice_requests_user_id", "invoice_requests"),
    ]
    for name, table in _index_catchup:
        # 卡 70202e7b: downgrade 必须先判表存在 —— _has_index 对缺表返回 True
        # (upgrade 侧语义: 表没有时跳过建索引), downgrade 沿用会在隔离库/缺表库
        # 上 drop_index 报 no such table/index, 整链 downgrade 中断
        if _has_table(bind, table) and _has_index(bind, table, name):
            op.drop_index(name, table_name=table)

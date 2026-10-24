"""parking_integration: 停车场系统对接开放API两张表 (任务卡 309b4132)

Revision ID: 202608080900
Revises: 202608080200
Create Date: 2026-08-08 09:00:00.000000

停车场系统对接开放API (/open/parking/*)：独立鉴权(X-App-Key/X-App-Secret)，
不走 user JWT。两表：

1. parking_integration_configs — 每站点一对对接凭证 + 权限开关
   - app_key unique: 对接标识
   - app_secret:     对接密钥 (常数时间比较)
   - integration_mode (A/B), allow_query, is_active

2. parking_discount_applied — 减免留痕 (对账凭证)
   - order_no unique: 幂等键
   - station_id 取自凭证 (非请求体)

枚举: integrationmode (A/B)。

幂等建表: inspector 判表存在再建, 兼容已 create_all 的测试环境
(与 occupancy_events / invoice_requests 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608080900"
down_revision: Union[str, Sequence[str], None] = "202608080200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 枚举字面值 (与 app.models.parking_integration.IntegrationMode 一致)
_MODE_VALUES = ("A", "B")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # ── 1. 停车对接集成配置表 ──
    if not _has_table(bind, "parking_integration_configs"):
        op.create_table(
            "parking_integration_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "station_id", sa.Integer(),
                sa.ForeignKey("stations.id"), nullable=False, comment="商户站点ID"),
            sa.Column("provider_name", sa.String(length=100), nullable=True, comment="停车场系统名称"),
            sa.Column("app_key", sa.String(length=100), nullable=False, comment="对接标识(app_key)"),
            sa.Column("app_secret", sa.String(length=200), nullable=False, comment="对接密钥(app_secret)"),
            sa.Column(
                "integration_mode",
                sa.Enum(*_MODE_VALUES, name="integrationmode"),
                nullable=False, server_default="A",
                comment="对接模式 A=查询+留痕/B=仅留痕"),
            sa.Column("allow_query", sa.Boolean(), nullable=False, server_default=sa.true(),
                      comment="是否允许查询(关闭则403)"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(),
                      comment="是否启用(关闭则401)"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("app_key", name="uq_parking_integration_app_key"),
        )
        op.create_index("idx_pic_station", "parking_integration_configs", ["station_id"])
        op.create_index("idx_pic_app_key", "parking_integration_configs", ["app_key"])
        op.create_index("idx_pic_active", "parking_integration_configs", ["is_active"])

    # ── 2. 停车减免留痕表 ──
    if not _has_table(bind, "parking_discount_applied"):
        op.create_table(
            "parking_discount_applied",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "station_id", sa.Integer(),
                sa.ForeignKey("stations.id"), nullable=False,
                comment="商户站点ID(取自对接凭证)"),
            sa.Column("plate_number", sa.String(length=20), nullable=False, comment="车牌号"),
            sa.Column("order_no", sa.String(length=100), nullable=False, comment="停车场订单号(幂等键)"),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, comment="减免金额(元)"),
            sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                      comment="减免发生时间"),
            sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("order_no", name="uq_parking_discount_applied_order_no"),
        )
        op.create_index("idx_pda_station", "parking_discount_applied", ["station_id"])
        op.create_index("idx_pda_plate", "parking_discount_applied", ["plate_number"])
        op.create_index("idx_pda_order_no", "parking_discount_applied", ["order_no"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "parking_discount_applied"):
        op.drop_table("parking_discount_applied")
    if _has_table(bind, "parking_integration_configs"):
        op.drop_table("parking_integration_configs")

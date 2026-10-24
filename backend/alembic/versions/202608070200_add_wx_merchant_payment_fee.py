"""add wx merchant / payment_order / platform_fee_config (工作卡 280c85ee — 云端配套④)

Revision ID: 202608070200
Revises: 202608070100
Create Date: 2026-08-07 02:00:00.000000

IM-B服务商模式三表 (契约 backend/docs/contracts/user-client-contract.md §2/§3/§4):
- merchants: 特约商户进件 (applyment_state 七态状态机 + merchant_status 运行态)。
- payment_orders: IM-B服务商支付订单 (prepay/notify/查询真相源, 独立于 ChargingOrder)。
- platform_fee_configs: 平台服务费分账预留 (本期仅落数据结构, enabled=false)。

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的环境 (与 202608070100 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070200"
down_revision: Union[str, Sequence[str], None] = "202608070100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "merchants"):
        op.create_table(
            "merchants",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("business_code", sa.String(length=64), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=True),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column(
                "merchant_type",
                sa.Enum("micro_merchant", "individual_business", "enterprise", name="merchanttype"),
                nullable=False,
            ),
            sa.Column("merchant_name", sa.String(length=120), nullable=False),
            sa.Column("contact_name", sa.String(length=60), nullable=True),
            sa.Column("contact_phone", sa.String(length=30), nullable=True),
            sa.Column("id_card_name", sa.String(length=60), nullable=True),
            sa.Column("id_card_number", sa.String(length=40), nullable=True),
            sa.Column("settlement_account_type", sa.String(length=20), nullable=True),
            sa.Column("settlement_bank_name", sa.String(length=100), nullable=True),
            sa.Column("settlement_account_number", sa.String(length=60), nullable=True),
            sa.Column("settlement_account_last4", sa.String(length=4), nullable=True),
            sa.Column(
                "applyment_state",
                sa.Enum(
                    "APPLYMENT_EDITING", "AUDITING", "TO_BE_SIGNED", "SIGNING",
                    "FINISH", "REJECTED", "FROZEN", name="applymentstate",
                ),
                nullable=False,
            ),
            sa.Column("sub_mchid", sa.String(length=32), nullable=True),
            sa.Column("reject_reason", sa.String(length=500), nullable=True),
            sa.Column("legal_validation_url", sa.String(length=500), nullable=True),
            sa.Column(
                "merchant_status",
                sa.Enum("ACTIVE", "FROZEN", "PENDING", name="merchantstatus"),
                nullable=False,
            ),
            sa.Column("profit_sharing_enabled", sa.Boolean(), nullable=False),
            sa.Column("station_ids", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_merchants_id", "merchants", ["id"])
        op.create_index("ix_merchants_business_code", "merchants", ["business_code"], unique=True)
        op.create_index("idx_merchant_team", "merchants", ["team_id"])
        op.create_index("idx_merchant_state", "merchants", ["applyment_state"])

    if not _has_table(bind, "payment_orders"):
        op.create_table(
            "payment_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("out_trade_no", sa.String(length=64), nullable=False),
            sa.Column("business_order_no", sa.String(length=64), nullable=False),
            sa.Column("openid", sa.String(length=64), nullable=False),
            sa.Column(
                "scene",
                sa.Enum("miniprogram", "app", name="payscene"),
                nullable=False,
            ),
            sa.Column("sub_mchid", sa.String(length=32), nullable=False),
            sa.Column("amount_fen", sa.Integer(), nullable=False),
            sa.Column("description", sa.String(length=200), nullable=True),
            sa.Column("prepay_id", sa.String(length=64), nullable=True),
            sa.Column("wx_transaction_id", sa.String(length=64), nullable=True),
            sa.Column(
                "payment_status",
                sa.Enum("UNPAID", "PAID", "REFUNDING", "REFUNDED", "CLOSED", name="paymentstatus"),
                nullable=False,
            ),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.Column("notify_count", sa.Integer(), nullable=False),
            sa.Column("notify_processed", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_payment_orders_id", "payment_orders", ["id"])
        op.create_index("ix_payment_orders_out_trade_no", "payment_orders", ["out_trade_no"], unique=True)
        op.create_index("idx_payorder_biz", "payment_orders", ["business_order_no"])
        op.create_index("idx_payorder_status", "payment_orders", ["payment_status"])

    if not _has_table(bind, "platform_fee_configs"):
        op.create_table(
            "platform_fee_configs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("team_id", sa.Integer(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("rate_bp", sa.Integer(), nullable=False),
            sa.Column(
                "scope",
                sa.Enum("all", "whitelist", name="feescope"),
                nullable=False,
            ),
            sa.Column("user_ids", sa.JSON(), nullable=True),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_platform_fee_configs_id", "platform_fee_configs", ["id"])
        op.create_index("idx_fee_config_team", "platform_fee_configs", ["team_id"])
        op.create_index("idx_fee_config_tenant", "platform_fee_configs", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "platform_fee_configs"):
        op.drop_index("idx_fee_config_tenant", table_name="platform_fee_configs")
        op.drop_index("idx_fee_config_team", table_name="platform_fee_configs")
        op.drop_index("ix_platform_fee_configs_id", table_name="platform_fee_configs")
        op.drop_table("platform_fee_configs")
        sa.Enum(name="feescope").drop(bind, checkfirst=True)
    if _has_table(bind, "payment_orders"):
        op.drop_index("idx_payorder_status", table_name="payment_orders")
        op.drop_index("idx_payorder_biz", table_name="payment_orders")
        op.drop_index("ix_payment_orders_out_trade_no", table_name="payment_orders")
        op.drop_index("ix_payment_orders_id", table_name="payment_orders")
        op.drop_table("payment_orders")
        sa.Enum(name="paymentstatus").drop(bind, checkfirst=True)
        sa.Enum(name="payscene").drop(bind, checkfirst=True)
    if _has_table(bind, "merchants"):
        op.drop_index("idx_merchant_state", table_name="merchants")
        op.drop_index("idx_merchant_team", table_name="merchants")
        op.drop_index("ix_merchants_business_code", table_name="merchants")
        op.drop_index("ix_merchants_id", table_name="merchants")
        op.drop_table("merchants")
        sa.Enum(name="merchanttype").drop(bind, checkfirst=True)
        sa.Enum(name="applymentstate").drop(bind, checkfirst=True)
        sa.Enum(name="merchantstatus").drop(bind, checkfirst=True)

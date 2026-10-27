"""add missing fk indexes

Revision ID: 0f669acebada
Revises: k8f9a0b1c2d3
Create Date: 2026-07-26 18:29:11.574178

给高频查询路径的 ForeignKey 列补 index=True，并幂等建索引：
- User.team_id (多租户核心列，API层大量过滤)
- api_gateway 全部FK (client_id / created_by / user_id / api_key_id / registered_by)
- OnCallRule.team_id / station_id
- OnCallLog.user_id / alarm_id

背景: 模型层已为上述 FK 列加 index=True, 但 baseline 0001 用
Base.metadata.create_all() 在运行时建表 —— 建于本次改动之前的持久库
(开发 SQLite / 生产 Postgres) 仍缺这些索引。高频过滤(如 User.team_id)
会全表扫描。本 migration 幂等地补齐索引(已有则跳过)，与
d1e2f3a4b5c6 / j7e8f9a0b1c2 保持同一 idempotent 约定。

注: autogenerate 另检测到 vehicles / enterprise_recharge_applications 表漂移
(历史 baseline 与当前模型不一致)，与本任务无关且涉及删表风险，已剔除，留待单独清理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f669acebada'
down_revision: Union[str, Sequence[str], None] = 'k8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) —— 索引名按 SQLAlchemy 约定为 ix_<table>_<column>
_INDEXES: list[tuple[str, str]] = [
    # User.team_id — 多租户核心
    ("users", "team_id"),
    # api_gateway 模块全部FK
    ("api_clients", "created_by"),
    ("api_endpoints", "registered_by"),
    ("api_request_logs", "api_key_id"),
    ("api_request_logs", "client_id"),
    ("gateway_api_keys", "client_id"),
    ("gateway_api_keys", "created_by"),
    ("oauth_authorization_codes", "client_id"),
    ("oauth_authorization_codes", "user_id"),
    ("rate_limit_rules", "client_id"),
    ("rate_limit_rules", "created_by"),
    ("third_party_integrations", "created_by"),
    # OnCall
    ("on_call_rules", "team_id"),
    ("on_call_rules", "station_id"),
    ("on_call_logs", "user_id"),
    ("on_call_logs", "alarm_id"),
]


def upgrade() -> None:
    """Upgrade schema: 幂等补齐高频FK索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, column in _INDEXES:
        if not inspector.has_table(table):
            # 表尚未创建(create_all 会按最新模型建, 已含索引) -> 跳过
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_{column}"
        if idx_name not in existing_indexes:
            op.create_index(idx_name, table, [column])


def downgrade() -> None:
    """Downgrade schema: 幂等移除新增索引。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, column in _INDEXES:
        if not inspector.has_table(table):
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_{column}"
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name=table)

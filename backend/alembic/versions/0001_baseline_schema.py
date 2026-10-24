"""baseline_schema — 冻结静态快照 (卡 6f5a35a2 方案A baseline 冻结)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-06 00:00:00.000000

本迁移是「baseline 时期」模型状态的冻结 DDL 快照。生成基准 commit: c0f535d1d
(2d3092def 引入 baseline, 3 分钟后 c0f535d1d 修复 __init__ 坏 import, 取该
commit 时期的 app/models 经 alembic autogenerate 对空库导出, 见
docs/migrations/0001-baseline-freeze-plan.md)。

冻结纪律:
- 禁止 import app.* — baseline 不再随当前模型漂移;
- 后续模型变更必须走新增迁移 (0002+), 不得回填本文件;
- revision id / down_revision=None 保持不变, 已 stamp 的库不受影响;
- 生产库 alembic_version 已 stamp 到后续版本, 本迁移在生产永不执行。

快照口径: 与旧动态 baseline 等价 — walk_packages 遍历该时期 app.models 全部
154 张表 (含未被 __init__ 显式导出的模块), 逐表冻结为静态 op.create_table。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- 卡 15a07d0f: 后置 FK 登记表 (原 create_table 内联 ForeignKeyConstraint) ----
# (source_table, referent_table, local_cols, remote_cols, ondelete)
_POSTPONED_FKS = [
    ('teams', 'users', ['leader_id'], ['id'], None),
    ('users', 'teams', ['team_id'], ['id'], None),
    ('api_clients', 'users', ['created_by'], ['id'], None),
    ('api_endpoints', 'users', ['registered_by'], ['id'], None),
    ('api_keys', 'tenants', ['tenant_id'], ['id'], None),
    ('api_keys', 'users', ['user_id'], ['id'], None),
    ('charging_schedule_entries', 'charging_schedule_plans', ['plan_id'], ['id'], None),
    ('enterprises', 'teams', ['owner_team_id'], ['id'], None),
    ('inspection_plans', 'teams', ['team_id'], ['id'], 'SET NULL'),
    ('knowledge_articles', 'users', ['author_id'], ['id'], None),
    ('knowledge_articles', 'knowledge_categories', ['category_id'], ['id'], None),
    ('knowledge_faq', 'users', ['author_id'], ['id'], None),
    ('notification_logs', 'notification_configs', ['config_id'], ['id'], None),
    ('notification_logs', 'notification_templates', ['template_id'], ['id'], None),
    ('repair_guides', 'fault_codes', ['fault_code_id'], ['id'], None),
    ('role_permissions', 'permissions', ['permission_id'], ['id'], 'CASCADE'),
    ('role_permissions', 'roles', ['role_id'], ['id'], 'CASCADE'),
    ('stations', 'users', ['operator_id'], ['id'], None),
    ('stations', 'teams', ['team_id'], ['id'], None),
    ('tenant_audit_logs', 'tenants', ['tenant_id'], ['id'], None),
    ('tenant_audit_logs', 'users', ['user_id'], ['id'], None),
    ('tenant_configs', 'tenants', ['tenant_id'], ['id'], None),
    ('third_party_integrations', 'users', ['created_by'], ['id'], None),
    ('user_roles', 'roles', ['role_id'], ['id'], 'CASCADE'),
    ('user_roles', 'users', ['user_id'], ['id'], 'CASCADE'),
    ('vehicles', 'users', ['driver_id'], ['id'], None),
    ('vehicles', 'tenants', ['tenant_id'], ['id'], None),
    ('webhook_deliveries', 'webhooks', ['webhook_id'], ['id'], 'CASCADE'),
    ('api_key_usage_logs', 'api_keys', ['api_key_id'], ['id'], None),
    ('api_usage_quotas', 'api_clients', ['client_id'], ['id'], None),
    ('devices', 'gateways', ['gateway_id'], ['id'], None),
    ('devices', 'stations', ['station_id'], ['id'], None),
    ('digital_twin_scenes', 'stations', ['station_id'], ['id'], None),
    ('energy_prices', 'time_slot_definitions', ['slot_id'], ['id'], None),
    ('energy_prices', 'stations', ['station_id'], ['id'], None),
    ('enterprise_recharge_applications', 'enterprises', ['enterprise_id'], ['id'], None),
    ('enterprise_stations', 'enterprises', ['enterprise_id'], ['id'], 'CASCADE'),
    ('enterprise_stations', 'stations', ['station_id'], ['id'], 'CASCADE'),
    ('enterprise_vehicles', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_alert_rules', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_carbon_certificates', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_carbon_certificates', 'carbon_reduction_summary', ['summary_id'], ['id'], None),
    ('fleet_charging_policies', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_settlement_bills', 'enterprises', ['enterprise_id'], ['id'], None),
    ('gateway_api_keys', 'api_clients', ['client_id'], ['id'], None),
    ('gateway_api_keys', 'users', ['created_by'], ['id'], None),
    ('inspection_tasks', 'inspection_plans', ['plan_id'], ['id'], 'SET NULL'),
    ('inspection_tasks', 'stations', ['station_id'], ['id'], 'SET NULL'),
    ('oauth_authorization_codes', 'api_clients', ['client_id'], ['id'], None),
    ('oauth_authorization_codes', 'users', ['user_id'], ['id'], None),
    ('occupancy_fee_prices', 'stations', ['station_id'], ['id'], None),
    ('on_call_rules', 'stations', ['station_id'], ['id'], None),
    ('on_call_rules', 'teams', ['team_id'], ['id'], None),
    ('parking_prices', 'stations', ['station_id'], ['id'], None),
    ('rate_limit_rules', 'api_clients', ['client_id'], ['id'], None),
    ('rate_limit_rules', 'users', ['created_by'], ['id'], None),
    ('reservation_fee_prices', 'stations', ['station_id'], ['id'], None),
    ('service_fee_prices', 'stations', ['station_id'], ['id'], None),
    ('station_hourly_stats', 'stations', ['station_id'], ['id'], None),
    ('station_vin_whitelist', 'enterprises', ['enterprise_id'], ['id'], None),
    ('analytics_results', 'devices', ['device_id'], ['id'], None),
    ('api_request_logs', 'gateway_api_keys', ['api_key_id'], ['id'], None),
    ('api_request_logs', 'api_clients', ['client_id'], ['id'], None),
    ('client_certificates', 'devices', ['device_id'], ['id'], None),
    ('client_certificates', 'tenants', ['tenant_id'], ['id'], None),
    ('device_configs', 'devices', ['device_id'], ['id'], None),
    ('device_control_logs', 'devices', ['device_id'], ['id'], None),
    ('device_daily_stats', 'devices', ['device_id'], ['id'], None),
    ('device_daily_stats', 'stations', ['station_id'], ['id'], None),
    ('device_efficiency_logs', 'devices', ['device_id'], ['id'], None),
    ('device_efficiency_logs', 'stations', ['station_id'], ['id'], None),
    ('device_health_history', 'devices', ['device_id'], ['id'], None),
    ('device_health_records', 'devices', ['device_id'], ['id'], None),
    ('device_qrcodes', 'devices', ['device_id'], ['id'], None),
    ('digital_twin_data_points', 'devices', ['device_id'], ['id'], None),
    ('digital_twin_models', 'devices', ['device_id'], ['id'], None),
    ('enterprise_transactions', 'enterprises', ['enterprise_id'], ['id'], None),
    ('enterprise_transactions', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('fleet_alert_records', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_alert_records', 'fleet_alert_rules', ['rule_id'], ['id'], None),
    ('fleet_alert_records', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('fleet_drivers', 'enterprise_vehicles', ['assigned_vehicle_id'], ['id'], None),
    ('fleet_drivers', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_invoice_requests', 'fleet_settlement_bills', ['bill_id'], ['id'], None),
    ('fleet_invoice_requests', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_settlement_details', 'fleet_settlement_bills', ['bill_id'], ['id'], 'CASCADE'),
    ('fleet_v2g_plans', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_v2g_plans', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('fleet_v2g_revenue', 'enterprises', ['enterprise_id'], ['id'], None),
    ('fleet_v2g_revenue', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('fleet_vehicle_insurances', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('fleet_vehicle_maintenances', 'enterprise_vehicles', ['vehicle_id'], ['id'], None),
    ('maintenance_records', 'devices', ['device_id'], ['id'], None),
    ('maintenance_records', 'users', ['engineer_id'], ['id'], None),
    ('maintenance_records', 'stations', ['station_id'], ['id'], None),
    ('on_call_shifts', 'users', ['backup_user_id'], ['id'], None),
    ('on_call_shifts', 'on_call_rules', ['rule_id'], ['id'], None),
    ('on_call_shifts', 'users', ['user_id'], ['id'], None),
    ('prediction_alerts', 'devices', ['device_id'], ['id'], None),
    ('telemetry', 'devices', ['device_id'], ['id'], None),
    ('telemetry_battery', 'devices', ['device_id'], ['id'], None),
    ('telemetry_battery', 'stations', ['station_id'], ['id'], None),
    ('telemetry_charger', 'devices', ['device_id'], ['id'], None),
    ('telemetry_charger', 'stations', ['station_id'], ['id'], None),
    ('telemetry_pv', 'devices', ['device_id'], ['id'], None),
    ('telemetry_pv', 'stations', ['station_id'], ['id'], None),
    ('v2g_dispatch_logs', 'devices', ['device_id'], ['id'], None),
    ('work_orders', 'users', ['assignee_id'], ['id'], None),
    ('work_orders', 'users', ['creator_id'], ['id'], None),
    ('work_orders', 'devices', ['device_id'], ['id'], None),
    ('work_orders', 'stations', ['station_id'], ['id'], None),
    ('alarms', 'devices', ['device_id'], ['id'], None),
    ('alarms', 'users', ['handler_id'], ['id'], None),
    ('alarms', 'alarm_rules', ['rule_id'], ['id'], None),
    ('alarms', 'stations', ['station_id'], ['id'], None),
    ('alarms', 'work_orders', ['workorder_id'], ['id'], None),
    ('fleet_driver_accounts', 'fleet_drivers', ['driver_id'], ['id'], 'CASCADE'),
    ('fleet_driver_attendance', 'fleet_drivers', ['driver_id'], ['id'], None),
    ('work_order_checkins', 'work_orders', ['order_id'], ['id'], None),
    ('work_order_checkins', 'users', ['user_id'], ['id'], None),
    ('work_order_logs', 'work_orders', ['order_id'], ['id'], None),
    ('work_order_logs', 'users', ['user_id'], ['id'], None),
    ('work_order_ratings', 'work_orders', ['order_id'], ['id'], None),
    ('work_order_ratings', 'users', ['user_id'], ['id'], None),
    ('work_order_spare_parts', 'work_orders', ['order_id'], ['id'], None),
    ('work_order_spare_parts', 'users', ['user_id'], ['id'], None),
    ('work_order_support_requests', 'work_orders', ['order_id'], ['id'], None),
    ('work_order_support_requests', 'users', ['target_engineer_id'], ['id'], None),
    ('work_order_support_requests', 'users', ['user_id'], ['id'], None),
    ('ai_diagnosis_records', 'alarms', ['alarm_id'], ['id'], None),
    ('ai_diagnosis_records', 'devices', ['device_id'], ['id'], None),
    ('ai_diagnosis_records', 'stations', ['station_id'], ['id'], None),
    ('alarm_rule_logs', 'alarms', ['alarm_id'], ['id'], None),
    ('alarm_rule_logs', 'devices', ['device_id'], ['id'], None),
    ('alarm_rule_logs', 'alarm_rules', ['rule_id'], ['id'], None),
    ('alarm_rule_logs', 'stations', ['station_id'], ['id'], None),
    ('fleet_driver_transactions', 'fleet_driver_accounts', ['account_id'], ['id'], 'CASCADE'),
    ('on_call_logs', 'alarms', ['alarm_id'], ['id'], None),
    ('on_call_logs', 'on_call_shifts', ['shift_id'], ['id'], None),
    ('on_call_logs', 'users', ['user_id'], ['id'], None),
]
def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('alarm_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('device_ids', sa.JSON(), nullable=True),
    sa.Column('station_ids', sa.JSON(), nullable=True),
    sa.Column('metric', sa.String(length=50), nullable=True),
    sa.Column('operator', sa.String(length=10), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('level', sa.Enum('info', 'warning', 'critical', 'fatal', name='alarmlevel'), nullable=True),
    sa.Column('alarm_template', sa.String(length=200), nullable=True),
    sa.Column('notify_users', sa.JSON(), nullable=True),
    sa.Column('auto_create_workorder', sa.Boolean(), nullable=True),
    sa.Column('workorder_priority', sa.String(length=20), nullable=True),
    sa.Column('escalation_timeout_minutes', sa.Integer(), nullable=True, comment='超时未处理自动升级的分钟数'),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('silence_minutes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alarm_rules_device_type'), 'alarm_rules', ['device_type'], unique=False)
    op.create_index(op.f('ix_alarm_rules_id'), 'alarm_rules', ['id'], unique=False)
    op.create_index(op.f('ix_alarm_rules_name'), 'alarm_rules', ['name'], unique=False)
    op.create_table('app_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='关联系统用户ID(users.id)'),
    sa.Column('phone', sa.String(length=20), nullable=False, comment='手机号'),
    sa.Column('nickname', sa.String(length=100), nullable=True, comment='昵称'),
    sa.Column('avatar', sa.String(length=500), nullable=True, comment='头像URL'),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=True, comment='账户余额(元)'),
    sa.Column('total_charge_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='累计充电量(kWh)'),
    sa.Column('total_spent', sa.Numeric(precision=12, scale=2), nullable=True, comment='累计消费(元)'),
    sa.Column('level', sa.Integer(), nullable=True, comment='用户等级'),
    sa.Column('points', sa.Integer(), nullable=True, comment='积分余额'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_app_user_phone', 'app_users', ['phone'], unique=False)
    op.create_index('idx_app_user_status', 'app_users', ['status'], unique=False)
    op.create_index('idx_app_user_user_id', 'app_users', ['user_id'], unique=False)
    op.create_index(op.f('ix_app_users_phone'), 'app_users', ['phone'], unique=True)
    op.create_index(op.f('ix_app_users_user_id'), 'app_users', ['user_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=50), nullable=True),
    sa.Column('user_role', sa.String(length=20), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=True),
    sa.Column('module', sa.String(length=30), nullable=True),
    sa.Column('target_id', sa.String(length=50), nullable=True),
    sa.Column('target_desc', sa.String(length=200), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.Column('result', sa.String(length=10), nullable=True),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_module'), 'audit_logs', ['module'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_username'), 'audit_logs', ['username'], unique=False)
    op.create_table('carbon_emission_factors',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('year', sa.Integer(), nullable=False, comment='年份'),
    sa.Column('region', sa.String(length=50), nullable=False, comment='区域(如:全国/华东/华北)'),
    sa.Column('factor_type', sa.String(length=50), nullable=False, comment='因子类型(grid-电网/fuel-燃油基准)'),
    sa.Column('emission_factor', sa.Numeric(precision=10, scale=6), nullable=False, comment='排放因子(kgCO2/kWh 或 kgCO2/L)'),
    sa.Column('source', sa.String(length=200), nullable=True, comment='数据来源(如:生态环境部)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cef_year_region_type', 'carbon_emission_factors', ['year', 'region', 'factor_type'], unique=True)
    op.create_table('carbon_reduction_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID(enterprise_vehicles.id)'),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('record_date', sa.Date(), nullable=False, comment='记录日期'),
    sa.Column('charge_energy_kwh', sa.Numeric(precision=12, scale=2), nullable=False, comment='充电量(kWh)'),
    sa.Column('grid_factor', sa.Numeric(precision=10, scale=6), nullable=False, comment='电网排放因子(kgCO2/kWh)'),
    sa.Column('fuel_factor', sa.Numeric(precision=10, scale=6), nullable=False, comment='燃油排放基准(kgCO2/kWh,已含能量转换)'),
    sa.Column('carbon_reduction_kg', sa.Numeric(precision=12, scale=2), nullable=False, comment='碳减排量(kgCO2)'),
    sa.Column('equivalent_fuel_saved_liters', sa.Numeric(precision=12, scale=2), nullable=False, comment='等效节油量(L)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_crr_enterprise_date', 'carbon_reduction_records', ['enterprise_id', 'record_date'], unique=False)
    op.create_index('idx_crr_vehicle_date', 'carbon_reduction_records', ['vehicle_id', 'record_date'], unique=False)
    op.create_table('carbon_reduction_summary',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('report_year', sa.Integer(), nullable=False, comment='报告年份'),
    sa.Column('report_month', sa.Integer(), nullable=False, comment='报告月份(1-12)'),
    sa.Column('total_charge_kwh', sa.Numeric(precision=14, scale=2), nullable=False, comment='总充电量(kWh)'),
    sa.Column('total_reduction_kg', sa.Numeric(precision=14, scale=2), nullable=False, comment='总减排量(kgCO2)'),
    sa.Column('total_fuel_saved_liters', sa.Numeric(precision=14, scale=2), nullable=False, comment='总节油量(L)'),
    sa.Column('vehicle_count', sa.Integer(), nullable=False, comment='参与车辆数'),
    sa.Column('verified', sa.Boolean(), nullable=False, comment='是否已审核'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_crs_enterprise_year_month', 'carbon_reduction_summary', ['enterprise_id', 'report_year', 'report_month'], unique=True)
    op.create_table('card_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('card_no', sa.String(length=50), nullable=False, comment='卡号(唯一)'),
    sa.Column('user_id', sa.Integer(), nullable=True, comment='关联系统用户ID'),
    sa.Column('holder_name', sa.String(length=100), nullable=True, comment='持卡人姓名'),
    sa.Column('bind_phone', sa.String(length=20), nullable=True, comment='绑定手机号'),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=True, comment='卡内余额(元)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive/locked'),
    sa.Column('issued_at', sa.DateTime(), nullable=True, comment='发卡时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_card_user_card_no', 'card_users', ['card_no'], unique=False)
    op.create_index('idx_card_user_phone', 'card_users', ['bind_phone'], unique=False)
    op.create_index('idx_card_user_user_id', 'card_users', ['user_id'], unique=False)
    op.create_index(op.f('ix_card_users_bind_phone'), 'card_users', ['bind_phone'], unique=False)
    op.create_index(op.f('ix_card_users_card_no'), 'card_users', ['card_no'], unique=True)
    op.create_index(op.f('ix_card_users_user_id'), 'card_users', ['user_id'], unique=False)
    op.create_table('charging_orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_no', sa.String(length=64), nullable=False, comment='订单编号'),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='电站ID'),
    sa.Column('device_id', sa.Integer(), nullable=False, comment='充电设备ID'),
    sa.Column('user_id', sa.Integer(), nullable=True, comment='用户ID'),
    sa.Column('user_type', sa.Enum('APP', 'CARD', name='usertype'), nullable=True, comment='用户类型: app/card'),
    sa.Column('vehicle_id', sa.Integer(), nullable=True, comment='车辆ID'),
    sa.Column('plate_number', sa.String(length=20), nullable=True, comment='车牌号'),
    sa.Column('start_time', sa.DateTime(), nullable=True, comment='充电开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=True, comment='充电结束时间'),
    sa.Column('duration_minutes', sa.Integer(), nullable=True, comment='充电时长(分钟)'),
    sa.Column('start_soc', sa.Numeric(precision=5, scale=1), nullable=True, comment='起始SOC%'),
    sa.Column('end_soc', sa.Numeric(precision=5, scale=1), nullable=True, comment='结束SOC%'),
    sa.Column('start_meter', sa.Numeric(precision=12, scale=2), nullable=True, comment='起始电表读数'),
    sa.Column('end_meter', sa.Numeric(precision=12, scale=2), nullable=True, comment='结束电表读数'),
    sa.Column('stop_reason', sa.String(length=50), nullable=True, comment='停止原因: full/active/fault/balance_low'),
    sa.Column('charged_kwh', sa.Numeric(precision=10, scale=2), nullable=True, comment='充电电量(kWh)'),
    sa.Column('electricity_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='电费(元)'),
    sa.Column('service_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='服务费(元)'),
    sa.Column('parking_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='停车费(元)'),
    sa.Column('idle_penalty', sa.Numeric(precision=12, scale=2), nullable=True, comment='超时占用费(元)'),
    sa.Column('occupancy_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='占桩费(元)'),
    sa.Column('reservation_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='预约费(元)'),
    sa.Column('peak_energy', sa.Numeric(precision=10, scale=2), nullable=True, comment='尖峰电量(kWh)'),
    sa.Column('flat_energy', sa.Numeric(precision=10, scale=2), nullable=True, comment='平段电量(kWh)'),
    sa.Column('valley_energy', sa.Numeric(precision=10, scale=2), nullable=True, comment='谷段电量(kWh)'),
    sa.Column('trough_energy', sa.Numeric(precision=10, scale=2), nullable=True, comment='深谷电量(kWh)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='总金额(元)'),
    sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='折扣金额(元)'),
    sa.Column('coupon_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='优惠券抵扣(元)'),
    sa.Column('points_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='积分抵扣(元)'),
    sa.Column('paid_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='实付金额(元)'),
    sa.Column('payment_status', sa.Enum('UNPAID', 'PAID', 'REFUNDING', 'REFUNDED', 'PARTIAL', name='orderpaymentstatus'), nullable=True, comment='支付状态'),
    sa.Column('order_status', sa.Enum('PENDING', 'CHARGING', 'COMPLETED', 'CANCELLED', 'FAILED', name='orderstatus'), nullable=True, comment='订单状态'),
    sa.Column('payment_method', sa.Enum('WECHAT', 'ALIPAY', 'CARD', 'ENTERPRISE', 'BALANCE', name='paymentmethod'), nullable=True, comment='支付方式'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_co_created', 'charging_orders', ['created_at'], unique=False)
    op.create_index('idx_co_device', 'charging_orders', ['device_id'], unique=False)
    op.create_index('idx_co_order_no', 'charging_orders', ['order_no'], unique=True)
    op.create_index('idx_co_station', 'charging_orders', ['station_id'], unique=False)
    op.create_index('idx_co_status', 'charging_orders', ['order_status'], unique=False)
    op.create_index('idx_co_user', 'charging_orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_charging_orders_device_id'), 'charging_orders', ['device_id'], unique=False)
    op.create_index(op.f('ix_charging_orders_order_no'), 'charging_orders', ['order_no'], unique=True)
    op.create_index(op.f('ix_charging_orders_station_id'), 'charging_orders', ['station_id'], unique=False)
    op.create_index(op.f('ix_charging_orders_user_id'), 'charging_orders', ['user_id'], unique=False)
    op.create_table('charging_queue_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='电站ID (null=全局)'),
    sa.Column('rule_name', sa.String(length=100), nullable=False, comment='规则名称'),
    sa.Column('priority_criteria', sa.JSON(), nullable=False, comment='权重计算标准 (JSON array of {field, weight, direction})'),
    sa.Column('max_queue_length', sa.Integer(), nullable=False, comment='最大队列长度'),
    sa.Column('enable', sa.Boolean(), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cqr_enterprise', 'charging_queue_rules', ['enterprise_id'], unique=False)
    op.create_index('idx_cqr_name', 'charging_queue_rules', ['rule_name'], unique=False)
    op.create_index(op.f('ix_charging_queue_rules_created_at'), 'charging_queue_rules', ['created_at'], unique=False)
    op.create_index(op.f('ix_charging_queue_rules_enterprise_id'), 'charging_queue_rules', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_charging_queue_rules_station_id'), 'charging_queue_rules', ['station_id'], unique=False)
    op.create_table('charging_queues',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='电站ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('enterprise_id', sa.Integer(), nullable=True, comment='企业ID'),
    sa.Column('rule_id', sa.Integer(), nullable=True, comment='排序规则ID'),
    sa.Column('priority', sa.Integer(), nullable=False, comment='排序优先级 (数字越小越靠前)'),
    sa.Column('arrival_time', sa.DateTime(), nullable=False, comment='入队时间'),
    sa.Column('estimated_wait_minutes', sa.Integer(), nullable=False, comment='预计等待分钟数'),
    sa.Column('required_energy_kwh', sa.Float(), nullable=False, comment='需求能量(kWh)'),
    sa.Column('target_soc', sa.Float(), nullable=False, comment='目标SOC (0.0-1.0)'),
    sa.Column('current_soc', sa.Float(), nullable=True, comment='当前SOC (0.0-1.0)'),
    sa.Column('status', sa.String(length=20), nullable=False, comment='队列状态'),
    sa.Column('assigned_device_id', sa.Integer(), nullable=True, comment='分配的充电桩设备ID'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cq_arrival', 'charging_queues', ['arrival_time'], unique=False)
    op.create_index('idx_cq_priority', 'charging_queues', ['priority'], unique=False)
    op.create_index('idx_cq_rule', 'charging_queues', ['rule_id'], unique=False)
    op.create_index('idx_cq_station', 'charging_queues', ['station_id'], unique=False)
    op.create_index('idx_cq_status', 'charging_queues', ['status'], unique=False)
    op.create_index('idx_cq_vehicle', 'charging_queues', ['vehicle_id'], unique=False)
    op.create_index(op.f('ix_charging_queues_arrival_time'), 'charging_queues', ['arrival_time'], unique=False)
    op.create_index(op.f('ix_charging_queues_created_at'), 'charging_queues', ['created_at'], unique=False)
    op.create_index(op.f('ix_charging_queues_enterprise_id'), 'charging_queues', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_charging_queues_rule_id'), 'charging_queues', ['rule_id'], unique=False)
    op.create_index(op.f('ix_charging_queues_station_id'), 'charging_queues', ['station_id'], unique=False)
    op.create_index(op.f('ix_charging_queues_status'), 'charging_queues', ['status'], unique=False)
    op.create_index(op.f('ix_charging_queues_vehicle_id'), 'charging_queues', ['vehicle_id'], unique=False)
    op.create_table('charging_schedule_plans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('plan_date', sa.DateTime(), nullable=False, comment='计划生成日期'),
    sa.Column('time_window_start', sa.DateTime(), nullable=False, comment='调度时段开始时间'),
    sa.Column('time_window_end', sa.DateTime(), nullable=False, comment='调度时段结束时间'),
    sa.Column('total_available_power_kw', sa.Float(), nullable=False, comment='可用总功率(kW)'),
    sa.Column('status', sa.Enum('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED', name='chargingscheduleplanstatus'), nullable=False, comment='计划状态'),
    sa.Column('rule_json', sa.JSON(), nullable=True, comment='关联的规则参数(JSON)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_csp_enterprise', 'charging_schedule_plans', ['enterprise_id'], unique=False)
    op.create_index('idx_csp_plan_date', 'charging_schedule_plans', ['plan_date'], unique=False)
    op.create_index('idx_csp_status', 'charging_schedule_plans', ['status'], unique=False)
    op.create_index(op.f('ix_charging_schedule_plans_created_at'), 'charging_schedule_plans', ['created_at'], unique=False)
    op.create_index(op.f('ix_charging_schedule_plans_enterprise_id'), 'charging_schedule_plans', ['enterprise_id'], unique=False)
    op.create_table('charging_schedule_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('rule_type', sa.Enum('PRIORITY_BASED', 'LOAD_BALANCED', 'VALLEY_FILLING', 'V2G_OPTIMIZED', name='chargingscheduleruletype'), nullable=False, comment='规则类型'),
    sa.Column('priority_weight', sa.Float(), nullable=False, comment='优先级权重'),
    sa.Column('max_power_per_vehicle', sa.Float(), nullable=True, comment='单车最大功率限制(kW)'),
    sa.Column('prefer_valley_period', sa.Boolean(), nullable=False, comment='是否偏好谷时充电'),
    sa.Column('v2g_enabled', sa.Boolean(), nullable=False, comment='是否启用V2G'),
    sa.Column('parameter', sa.JSON(), nullable=True, comment='规则扩展参数(JSON)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_csr_enterprise', 'charging_schedule_rules', ['enterprise_id'], unique=False)
    op.create_index('idx_csr_type', 'charging_schedule_rules', ['rule_type'], unique=False)
    op.create_index(op.f('ix_charging_schedule_rules_created_at'), 'charging_schedule_rules', ['created_at'], unique=False)
    op.create_index(op.f('ix_charging_schedule_rules_enterprise_id'), 'charging_schedule_rules', ['enterprise_id'], unique=False)
    op.create_table('cloud_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('config_name', sa.String(length=100), nullable=False, comment='配置名称'),
    sa.Column('provider', sa.String(length=30), nullable=False, comment='云提供商 cloud_provider/vendor_b/aws/private'),
    sa.Column('config_json', sa.Text(), nullable=True, comment='配置JSON: region/endpoint/access配置'),
    sa.Column('bucket', sa.String(length=200), nullable=True, comment='存储桶'),
    sa.Column('sync_strategy', sa.String(length=20), nullable=True, comment='数据同步策略 realtime/hourly/daily'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cloud_provider', 'cloud_configs', ['provider'], unique=False)
    op.create_index('idx_cloud_status', 'cloud_configs', ['status'], unique=False)
    op.create_index('idx_cloud_sync', 'cloud_configs', ['sync_strategy'], unique=False)
    op.create_table('code_sequences',
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('current_value', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_code_sequences_key'), 'code_sequences', ['key'], unique=False)
    op.create_table('compliance_checks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=False, comment='关联 municipal_supervision_configs.id'),
    sa.Column('city', sa.String(length=100), nullable=True, comment='城市(冗余)'),
    sa.Column('check_type', sa.String(length=30), nullable=False, comment='检查类型 data_integrity/report_delay/compliance'),
    sa.Column('result', sa.String(length=20), nullable=False, comment='结果 pass/warn/fail'),
    sa.Column('score', sa.Numeric(precision=5, scale=2), nullable=True, comment='合规得分(0-100)'),
    sa.Column('details', sa.Text(), nullable=True, comment='检查明细(JSON)'),
    sa.Column('checked_at', sa.DateTime(), nullable=True, comment='检查时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cca_config', 'compliance_checks', ['config_id'], unique=False)
    op.create_index('idx_cca_result', 'compliance_checks', ['result'], unique=False)
    op.create_table('coupon_activity_stats',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('coupon_id', sa.Integer(), nullable=False, comment='关联优惠券ID'),
    sa.Column('total_claimed', sa.Integer(), nullable=True, comment='累计领取数'),
    sa.Column('total_used', sa.Integer(), nullable=True, comment='累计使用数'),
    sa.Column('total_discount_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='累计抵扣金额(元)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cas_coupon', 'coupon_activity_stats', ['coupon_id'], unique=False)
    op.create_index(op.f('ix_coupon_activity_stats_coupon_id'), 'coupon_activity_stats', ['coupon_id'], unique=False)
    op.create_table('coupon_batches',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('coupon_id', sa.Integer(), nullable=False, comment='关联优惠券ID'),
    sa.Column('batch_name', sa.String(length=100), nullable=False, comment='批次名称'),
    sa.Column('quantity', sa.Integer(), nullable=False, comment='发放数量'),
    sa.Column('user_type', sa.String(length=50), nullable=True, comment='发放目标用户类型'),
    sa.Column('user_ids', sa.Text(), nullable=True, comment='具体用户ID列表，逗号分隔'),
    sa.Column('distributed_at', sa.DateTime(), nullable=True, comment='发放时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cb_coupon_id', 'coupon_batches', ['coupon_id'], unique=False)
    op.create_index(op.f('ix_coupon_batches_coupon_id'), 'coupon_batches', ['coupon_id'], unique=False)
    op.create_table('coupon_usages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('coupon_id', sa.Integer(), nullable=False, comment='关联优惠券ID'),
    sa.Column('batch_id', sa.Integer(), nullable=True, comment='关联批次ID'),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
    sa.Column('user_type', sa.String(length=50), nullable=True, comment='用户类型'),
    sa.Column('coupon_code', sa.String(length=64), nullable=False, comment='券码'),
    sa.Column('order_id', sa.Integer(), nullable=True, comment='关联订单ID'),
    sa.Column('status', sa.Enum('ACTIVE', 'USED', 'EXPIRED', 'DISABLED', name='couponstatus'), nullable=False, comment='状态'),
    sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=True, comment='实际抵扣金额'),
    sa.Column('used_at', sa.DateTime(), nullable=True, comment='使用时间'),
    sa.Column('expires_at', sa.DateTime(), nullable=False, comment='过期时间'),
    sa.Column('received_at', sa.DateTime(), nullable=True, comment='领取时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cu_expires', 'coupon_usages', ['expires_at'], unique=False)
    op.create_index('idx_cu_status', 'coupon_usages', ['status'], unique=False)
    op.create_index('idx_cu_user_id', 'coupon_usages', ['user_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_batch_id'), 'coupon_usages', ['batch_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_coupon_code'), 'coupon_usages', ['coupon_code'], unique=True)
    op.create_index(op.f('ix_coupon_usages_coupon_id'), 'coupon_usages', ['coupon_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_order_id'), 'coupon_usages', ['order_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_user_id'), 'coupon_usages', ['user_id'], unique=False)
    op.create_table('coupons',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='优惠券名称'),
    sa.Column('coupon_type', sa.Enum('FIXED', 'PERCENTAGE', 'FREE_CHARGE', 'SERVICE_FREE', name='coupontype'), nullable=False, comment='券类型'),
    sa.Column('face_value', sa.Numeric(precision=10, scale=2), nullable=False, comment='面额/折扣率'),
    sa.Column('min_order_amount', sa.Numeric(precision=10, scale=2), nullable=True, comment='最低使用门槛(元)'),
    sa.Column('max_discount_amount', sa.Numeric(precision=10, scale=2), nullable=True, comment='最大优惠金额上限(元)'),
    sa.Column('applicable_user_types', sa.Text(), nullable=True, comment='适用用户类型，逗号分隔'),
    sa.Column('applicable_stations', sa.Text(), nullable=True, comment='适用站点ID列表，逗号分隔'),
    sa.Column('total_stock', sa.Integer(), nullable=False, comment='总库存'),
    sa.Column('remaining_stock', sa.Integer(), nullable=False, comment='剩余库存'),
    sa.Column('per_user_limit', sa.Integer(), nullable=True, comment='每人限领数量'),
    sa.Column('valid_days', sa.Integer(), nullable=False, comment='领取后有效天数'),
    sa.Column('start_time', sa.DateTime(), nullable=False, comment='发放开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=False, comment='发放结束时间'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('description', sa.Text(), nullable=True, comment='描述'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_coupon_active', 'coupons', ['is_active'], unique=False)
    op.create_index('idx_coupon_time', 'coupons', ['start_time', 'end_time'], unique=False)
    op.create_index('idx_coupon_type', 'coupons', ['coupon_type'], unique=False)
    op.create_table('daily_settlements',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('settlement_date', sa.Date(), nullable=False, comment='结算日期'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='站点ID (NULL=全平台)'),
    sa.Column('total_orders', sa.Integer(), nullable=True, comment='总订单数'),
    sa.Column('total_energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='总充电量(kWh)'),
    sa.Column('total_charge_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总电费(元)'),
    sa.Column('total_service_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总服务费(元)'),
    sa.Column('total_parking_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总停车费(元)'),
    sa.Column('total_occupancy_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总占桩费(元)'),
    sa.Column('total_reservation_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总预约费(元)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='应收总额(元)'),
    sa.Column('total_paid', sa.Numeric(precision=12, scale=2), nullable=True, comment='实收总额(元)'),
    sa.Column('total_discount', sa.Numeric(precision=12, scale=2), nullable=True, comment='优惠金额(元)'),
    sa.Column('total_coupon', sa.Numeric(precision=12, scale=2), nullable=True, comment='优惠券抵扣(元)'),
    sa.Column('total_points', sa.Numeric(precision=12, scale=2), nullable=True, comment='积分抵扣(元)'),
    sa.Column('total_refund', sa.Numeric(precision=12, scale=2), nullable=True, comment='退款金额(元)'),
    sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', name='settlementstatus'), nullable=True, comment='结算状态'),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True, comment='确认时间'),
    sa.Column('confirmed_by', sa.String(length=100), nullable=True, comment='确认人'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ds_date_station', 'daily_settlements', ['settlement_date', 'station_id'], unique=False)
    op.create_index('idx_ds_status', 'daily_settlements', ['status'], unique=False)
    op.create_index(op.f('ix_daily_settlements_settlement_date'), 'daily_settlements', ['settlement_date'], unique=False)
    op.create_index(op.f('ix_daily_settlements_station_id'), 'daily_settlements', ['station_id'], unique=False)
    op.create_table('diagnosis_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('fault_category', sa.String(length=50), nullable=True),
    sa.Column('conditions', sa.JSON(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('diagnosis_result', sa.String(length=200), nullable=True),
    sa.Column('repair_actions', sa.JSON(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diagnosis_rules_id'), 'diagnosis_rules', ['id'], unique=False)
    op.create_table('discount_groups',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='分组名称'),
    sa.Column('discount_id', sa.Integer(), nullable=False, comment='关联折扣方案ID'),
    sa.Column('user_type', sa.String(length=50), nullable=False, comment='用户类型: app/card/vin/interconnect/enterprise'),
    sa.Column('user_ids', sa.Text(), nullable=True, comment='关联用户ID列表，逗号分隔; 为空表示该类型所有用户'),
    sa.Column('station_ids', sa.Text(), nullable=True, comment='适用站点ID列表，逗号分隔; 为空表示所有站点'),
    sa.Column('priority', sa.Integer(), nullable=True, comment='优先级'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_dg_active', 'discount_groups', ['is_active'], unique=False)
    op.create_index('idx_dg_discount_id', 'discount_groups', ['discount_id'], unique=False)
    op.create_index('idx_dg_user_type', 'discount_groups', ['user_type'], unique=False)
    op.create_index(op.f('ix_discount_groups_discount_id'), 'discount_groups', ['discount_id'], unique=False)
    op.create_index(op.f('ix_discount_groups_user_type'), 'discount_groups', ['user_type'], unique=False)
    op.create_table('enterprise_accounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_name', sa.String(length=200), nullable=False, comment='企业名称'),
    sa.Column('credit_code', sa.String(length=50), nullable=True, comment='统一社会信用代码'),
    sa.Column('contact_person', sa.String(length=100), nullable=True, comment='联系人'),
    sa.Column('contact_phone', sa.String(length=20), nullable=True, comment='联系电话'),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=True, comment='账户余额(元)'),
    sa.Column('billing_cycle', sa.Enum('MONTHLY', 'QUARTERLY', name='billingcycle'), nullable=True, comment='计费周期 monthly/quarterly'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive/suspended'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_eacct_credit_code', 'enterprise_accounts', ['credit_code'], unique=False)
    op.create_index('idx_eacct_status', 'enterprise_accounts', ['status'], unique=False)
    op.create_index(op.f('ix_enterprise_accounts_credit_code'), 'enterprise_accounts', ['credit_code'], unique=False)
    op.create_table('enterprise_sub_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='关联企业账户ID'),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='关联系统用户ID'),
    sa.Column('department', sa.String(length=100), nullable=True, comment='部门'),
    sa.Column('budget_limit', sa.Numeric(precision=12, scale=2), nullable=True, comment='预算上限(元)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_esub_enterprise', 'enterprise_sub_users', ['enterprise_id'], unique=False)
    op.create_index('idx_esub_user', 'enterprise_sub_users', ['user_id'], unique=False)
    op.create_index(op.f('ix_enterprise_sub_users_enterprise_id'), 'enterprise_sub_users', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_enterprise_sub_users_user_id'), 'enterprise_sub_users', ['user_id'], unique=False)
    op.create_table('fault_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fault_code', sa.String(length=20), nullable=False),
    sa.Column('fault_name', sa.String(length=100), nullable=False),
    sa.Column('fault_description', sa.Text(), nullable=True),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('fault_category', sa.Enum('GRID', 'INVERTER', 'BATTERY', 'BUS', 'TEMPERATURE', 'RELAY', 'OVERLOAD', 'OTHER', 'BCU_BMS', 'POWER_CONTROL', 'CHARGING_MODULE', 'CHARGING_CONTROLLER', 'AC_DISTRIBUTION', 'DC_DISTRIBUTION', 'BMS_RELATED', 'ENVIRONMENT', 'COMMUNICATION', name='faultcategory'), nullable=True),
    sa.Column('fault_level', sa.Enum('EMERGENCY', 'SERIOUS', 'WARNING_SERIOUS', 'WARNING_GENERAL', name='faultlevel'), nullable=True),
    sa.Column('modbus_address', sa.Integer(), nullable=True),
    sa.Column('mqtt_code', sa.String(length=20), nullable=True),
    sa.Column('possible_causes', sa.JSON(), nullable=True),
    sa.Column('diagnosis_steps', sa.JSON(), nullable=True),
    sa.Column('repair_suggestions', sa.JSON(), nullable=True),
    sa.Column('response_time_minutes', sa.Integer(), nullable=True),
    sa.Column('auto_stop', sa.Boolean(), nullable=True),
    sa.Column('remote_fixable', sa.Boolean(), nullable=True),
    sa.Column('occurrence_count', sa.Integer(), nullable=True),
    sa.Column('avg_repair_time_minutes', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fault_codes_device_type'), 'fault_codes', ['device_type'], unique=False)
    op.create_index(op.f('ix_fault_codes_fault_category'), 'fault_codes', ['fault_category'], unique=False)
    op.create_index(op.f('ix_fault_codes_fault_code'), 'fault_codes', ['fault_code'], unique=True)
    op.create_index(op.f('ix_fault_codes_id'), 'fault_codes', ['id'], unique=False)
    op.create_table('firmware',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('model', sa.String(length=50), nullable=False),
    sa.Column('file_path', sa.String(length=200), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('checksum', sa.String(length=100), nullable=True),
    sa.Column('changelog', sa.Text(), nullable=True),
    sa.Column('release_date', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_index(op.f('ix_firmware_id'), 'firmware', ['id'], unique=False)
    op.create_table('gateway_sn',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('sn', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('batch_no', sa.String(length=50), nullable=True),
    sa.Column('gateway_id', sa.Integer(), nullable=True),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('team_id', sa.Integer(), nullable=True),
    sa.Column('generated_at', sa.DateTime(), nullable=True),
    sa.Column('written_at', sa.DateTime(), nullable=True),
    sa.Column('activated_at', sa.DateTime(), nullable=True),
    sa.Column('locked_at', sa.DateTime(), nullable=True),
    sa.Column('recalled_at', sa.DateTime(), nullable=True),
    sa.Column('generated_by', sa.Integer(), nullable=True),
    sa.Column('written_by', sa.Integer(), nullable=True),
    sa.Column('activated_by', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateway_sn_id'), 'gateway_sn', ['id'], unique=False)
    op.create_index(op.f('ix_gateway_sn_sn'), 'gateway_sn', ['sn'], unique=True)
    op.create_table('gateways',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('sn', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('model', sa.String(length=50), nullable=True),
    sa.Column('manufacturer', sa.String(length=50), nullable=True),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('firmware_version', sa.String(length=20), nullable=True),
    sa.Column('last_online', sa.DateTime(), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('mac_address', sa.String(length=50), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('health_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateways_id'), 'gateways', ['id'], unique=False)
    op.create_index(op.f('ix_gateways_sn'), 'gateways', ['sn'], unique=True)
    op.create_index(op.f('ix_gateways_station_id'), 'gateways', ['station_id'], unique=False)
    op.create_table('healing_executions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=True, comment='关联自愈规则ID'),
    sa.Column('rule_name', sa.String(length=100), nullable=True, comment='快照：规则名称'),
    sa.Column('alarm_id', sa.Integer(), nullable=True, comment='触发告警ID'),
    sa.Column('device_id', sa.Integer(), nullable=True, comment='设备ID'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='站点ID'),
    sa.Column('runbook_id', sa.String(length=64), nullable=True, comment='Runbook执行ID'),
    sa.Column('runbook_template', sa.String(length=200), nullable=True, comment='使用的Runbook模板'),
    sa.Column('fault_type', sa.String(length=200), nullable=True, comment='故障类型'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='执行状态'),
    sa.Column('steps', sa.JSON(), nullable=True, comment='执行步骤详情'),
    sa.Column('approved_by', sa.String(length=100), nullable=True, comment='审批人'),
    sa.Column('approved_at', sa.DateTime(), nullable=True, comment='审批时间'),
    sa.Column('reject_reason', sa.Text(), nullable=True, comment='拒绝原因'),
    sa.Column('total_duration_ms', sa.Integer(), nullable=True, comment='总耗时(ms)'),
    sa.Column('success_steps', sa.Integer(), nullable=True, comment='成功步骤数'),
    sa.Column('failed_steps', sa.Integer(), nullable=True, comment='失败步骤数'),
    sa.Column('retry_count', sa.Integer(), nullable=True, comment='已重试次数'),
    sa.Column('result', sa.Text(), nullable=True, comment='执行结果摘要'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('verified', sa.Boolean(), nullable=True, comment='是否已验证效果'),
    sa.Column('verified_at', sa.DateTime(), nullable=True, comment='验证时间'),
    sa.Column('verification_result', sa.String(length=20), nullable=True, comment='验证结果: healed/unhealed/partial'),
    sa.Column('alarm_cleared', sa.Boolean(), nullable=True, comment='告警是否已清除'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始执行时间'),
    sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_healing_executions_alarm_id'), 'healing_executions', ['alarm_id'], unique=False)
    op.create_index(op.f('ix_healing_executions_device_id'), 'healing_executions', ['device_id'], unique=False)
    op.create_index(op.f('ix_healing_executions_id'), 'healing_executions', ['id'], unique=False)
    op.create_index(op.f('ix_healing_executions_rule_id'), 'healing_executions', ['rule_id'], unique=False)
    op.create_index(op.f('ix_healing_executions_station_id'), 'healing_executions', ['station_id'], unique=False)
    op.create_index(op.f('ix_healing_executions_status'), 'healing_executions', ['status'], unique=False)
    op.create_table('healing_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='规则名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='规则描述'),
    sa.Column('alarm_pattern', sa.JSON(), nullable=False, comment='告警匹配条件'),
    sa.Column('runbook_template', sa.String(length=200), nullable=True, comment='关联Runbook模板名称'),
    sa.Column('auto_approve', sa.Boolean(), nullable=True, comment='是否自动审批（仅对低风险步骤生效）'),
    sa.Column('max_retries', sa.Integer(), nullable=True, comment='最大重试次数'),
    sa.Column('cooldown_minutes', sa.Integer(), nullable=True, comment='冷却时间（分钟），防止同一规则频繁触发'),
    sa.Column('priority', sa.Integer(), nullable=True, comment='优先级，数值越大越优先'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_healing_rules_id'), 'healing_rules', ['id'], unique=False)
    op.create_table('interconnect_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform_name', sa.String(length=100), nullable=False, comment='平台名称'),
    sa.Column('platform_code', sa.String(length=50), nullable=False, comment='平台编码 huawei/sgcc/csg/teld/other'),
    sa.Column('api_base_url', sa.String(length=500), nullable=False, comment='API接入地址'),
    sa.Column('auth_type', sa.String(length=20), nullable=False, comment='认证方式 apikey/oauth'),
    sa.Column('auth_params', sa.Text(), nullable=True, comment='认证参数(JSON): apikey/oauth 配置'),
    sa.Column('revenue_share_ratio', sa.Numeric(precision=5, scale=4), nullable=True, comment='我方分成比例(0.7000=70%)'),
    sa.Column('data_sync_interval', sa.Integer(), nullable=True, comment='数据同步间隔(秒)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_iconfig_code', 'interconnect_configs', ['platform_code'], unique=False)
    op.create_index('idx_iconfig_status', 'interconnect_configs', ['status'], unique=False)
    op.create_table('interconnect_orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform_id', sa.Integer(), nullable=False, comment='关联 interconnect_configs.id'),
    sa.Column('platform_code', sa.String(length=50), nullable=False, comment='来源平台编码(冗余,便于筛选)'),
    sa.Column('outer_order_id', sa.String(length=100), nullable=False, comment='外部订单号'),
    sa.Column('outer_user_id', sa.String(length=100), nullable=True, comment='外部用户标识'),
    sa.Column('station_id', sa.String(length=100), nullable=True, comment='站点标识'),
    sa.Column('device_id', sa.String(length=100), nullable=True, comment='设备标识'),
    sa.Column('charge_energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='充电量(kWh)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='订单总费用(元)'),
    sa.Column('our_share', sa.Numeric(precision=12, scale=2), nullable=True, comment='我方分成(元)'),
    sa.Column('partner_share', sa.Numeric(precision=12, scale=2), nullable=True, comment='合作方分成(元)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 synced/settled/conflict'),
    sa.Column('synced_at', sa.DateTime(), nullable=True, comment='同步时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_iorder_outer', 'interconnect_orders', ['outer_order_id'], unique=False)
    op.create_index('idx_iorder_platform', 'interconnect_orders', ['platform_id', 'platform_code'], unique=False)
    op.create_index('idx_iorder_status', 'interconnect_orders', ['status'], unique=False)
    op.create_table('interconnect_platforms',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform_name', sa.String(length=100), nullable=False, comment='平台名称'),
    sa.Column('platform_code', sa.String(length=50), nullable=False, comment='平台编码'),
    sa.Column('api_key', sa.String(length=200), nullable=True, comment='对接API Key'),
    sa.Column('contact', sa.String(length=100), nullable=True, comment='联系人'),
    sa.Column('phone', sa.String(length=20), nullable=True, comment='联系电话'),
    sa.Column('revenue_share_ratio', sa.Numeric(precision=5, scale=4), nullable=True, comment='我方分成比例(0.7000=70%)'),
    sa.Column('bind_date', sa.DateTime(), nullable=True, comment='绑定日期'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_iplat_code', 'interconnect_platforms', ['platform_code'], unique=False)
    op.create_index('idx_iplat_status', 'interconnect_platforms', ['status'], unique=False)
    op.create_index(op.f('ix_interconnect_platforms_platform_code'), 'interconnect_platforms', ['platform_code'], unique=True)
    op.create_table('interconnect_settlements',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform_id', sa.String(length=100), nullable=False, comment='第三方平台标识'),
    sa.Column('platform_name', sa.String(length=200), nullable=True, comment='平台名称'),
    sa.Column('start_date', sa.Date(), nullable=False, comment='结算周期开始'),
    sa.Column('end_date', sa.Date(), nullable=False, comment='结算周期结束'),
    sa.Column('total_orders', sa.Integer(), nullable=True, comment='导流订单数'),
    sa.Column('total_energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='总充电量(kWh)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='订单总金额(元)'),
    sa.Column('revenue_share_ratio', sa.Numeric(precision=5, scale=4), nullable=True, comment='分成比例(如0.7000=70%)'),
    sa.Column('our_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='我方收入(元)'),
    sa.Column('partner_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='合作方收入(元)'),
    sa.Column('settlement_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='实际结算金额(元)'),
    sa.Column('invoice_id', sa.Integer(), nullable=True, comment='关联发票ID'),
    sa.Column('status', sa.Enum('PENDING', 'SETTLED', name='interconnectsettlementstatus'), nullable=True, comment='结算状态'),
    sa.Column('settled_at', sa.DateTime(), nullable=True, comment='结算时间'),
    sa.Column('settled_by', sa.String(length=100), nullable=True, comment='结算操作人'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_is_period', 'interconnect_settlements', ['start_date', 'end_date'], unique=False)
    op.create_index('idx_is_platform', 'interconnect_settlements', ['platform_id'], unique=False)
    op.create_index('idx_is_status', 'interconnect_settlements', ['status'], unique=False)
    op.create_table('interconnect_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform_id', sa.Integer(), nullable=False, comment='关联互联互通平台ID'),
    sa.Column('outer_user_id', sa.String(length=100), nullable=False, comment='外部平台用户标识'),
    sa.Column('nickname', sa.String(length=100), nullable=True, comment='昵称'),
    sa.Column('phone', sa.String(length=20), nullable=True, comment='手机号'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_iuser_outer', 'interconnect_users', ['outer_user_id'], unique=False)
    op.create_index('idx_iuser_platform', 'interconnect_users', ['platform_id'], unique=False)
    op.create_index(op.f('ix_interconnect_users_outer_user_id'), 'interconnect_users', ['outer_user_id'], unique=False)
    op.create_index(op.f('ix_interconnect_users_platform_id'), 'interconnect_users', ['platform_id'], unique=False)
    op.create_table('invoice_platform_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False, comment='所属团队ID'),
    sa.Column('platform_type', sa.Enum('BAIWANG', 'HANGXIN', 'NUONUO', 'OTHER', name='platformtype'), nullable=False, comment='平台类型(百旺/航信/诺诺)'),
    sa.Column('platform_name', sa.String(length=100), nullable=False, comment='平台显示名称'),
    sa.Column('api_url', sa.String(length=500), nullable=True, comment='平台API地址'),
    sa.Column('app_key', sa.String(length=200), nullable=True, comment='应用Key'),
    sa.Column('app_secret', sa.String(length=500), nullable=True, comment='应用密钥'),
    sa.Column('taxpayer_id', sa.String(length=50), nullable=True, comment='纳税人识别号'),
    sa.Column('tax_classification_code', sa.String(length=50), nullable=True, comment='税收分类编码'),
    sa.Column('is_default', sa.Boolean(), nullable=True, comment='是否团队默认平台'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ipc_team', 'invoice_platform_configs', ['team_id'], unique=False)
    op.create_index('idx_ipc_team_default', 'invoice_platform_configs', ['team_id', 'is_default'], unique=False)
    op.create_index('idx_ipc_team_enabled', 'invoice_platform_configs', ['team_id', 'enabled'], unique=False)
    op.create_index(op.f('ix_invoice_platform_configs_team_id'), 'invoice_platform_configs', ['team_id'], unique=False)
    op.create_table('invoice_titles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True, comment='关联用户ID (NULL=运营公用)'),
    sa.Column('title_type', sa.Enum('PERSONAL', 'ENTERPRISE', name='titletype'), nullable=True, comment='抬头类型'),
    sa.Column('title_name', sa.String(length=200), nullable=False, comment='抬头名称'),
    sa.Column('tax_id', sa.String(length=50), nullable=True, comment='纳税人识别号'),
    sa.Column('register_address', sa.String(length=500), nullable=True, comment='注册地址'),
    sa.Column('register_phone', sa.String(length=20), nullable=True, comment='注册电话'),
    sa.Column('bank_name', sa.String(length=200), nullable=True, comment='开户银行'),
    sa.Column('bank_account', sa.String(length=50), nullable=True, comment='银行账号'),
    sa.Column('email', sa.String(length=100), nullable=True, comment='接收邮箱'),
    sa.Column('is_default', sa.Boolean(), nullable=True, comment='是否默认抬头'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_it_type', 'invoice_titles', ['title_type'], unique=False)
    op.create_index('idx_it_user', 'invoice_titles', ['user_id'], unique=False)
    op.create_index(op.f('ix_invoice_titles_user_id'), 'invoice_titles', ['user_id'], unique=False)
    op.create_table('knowledge_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_categories_id'), 'knowledge_categories', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_categories_name'), 'knowledge_categories', ['name'], unique=True)
    op.create_table('ml_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('model_name', sa.String(length=100), nullable=False),
    sa.Column('model_type', sa.String(length=50), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('performance_metrics', sa.JSON(), nullable=True),
    sa.Column('trained_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ml_models_id'), 'ml_models', ['id'], unique=False)
    op.create_index(op.f('ix_ml_models_is_active'), 'ml_models', ['is_active'], unique=False)
    op.create_index(op.f('ix_ml_models_model_name'), 'ml_models', ['model_name'], unique=False)
    op.create_index(op.f('ix_ml_models_model_type'), 'ml_models', ['model_type'], unique=False)
    op.create_table('municipal_supervision_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False, comment='对接城市'),
    sa.Column('platform_url', sa.String(length=500), nullable=False, comment='监管平台URL'),
    sa.Column('auth_config', sa.Text(), nullable=True, comment='认证配置(JSON): data接口/auth接口凭证'),
    sa.Column('report_strategy', sa.String(length=20), nullable=True, comment='上报策略 scheduled/realtime'),
    sa.Column('report_interval_seconds', sa.Integer(), nullable=True, comment='定时上报间隔(秒)'),
    sa.Column('station_endpoints', sa.Text(), nullable=True, comment='各上报端点配置(JSON): station/device/order/heartbeat'),
    sa.Column('heartbeat_enabled', sa.Integer(), nullable=True, comment='心跳保活 1/0'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_msupercity', 'municipal_supervision_configs', ['city'], unique=False)
    op.create_index('idx_msuperstatus', 'municipal_supervision_configs', ['status'], unique=False)
    op.create_table('notification_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='配置名称'),
    sa.Column('scope_type', sa.String(length=20), nullable=False, comment='作用域类型'),
    sa.Column('scope_id', sa.Integer(), nullable=True, comment='作用域ID (租户ID/站点ID/用户ID/设备ID)'),
    sa.Column('sms_enabled', sa.Boolean(), nullable=True, comment='短信启用'),
    sa.Column('email_enabled', sa.Boolean(), nullable=True, comment='邮件启用'),
    sa.Column('app_push_enabled', sa.Boolean(), nullable=True, comment='APP推送启用'),
    sa.Column('im_b_enabled', sa.Boolean(), nullable=True, comment='IM-B启用'),
    sa.Column('im_enabled', sa.Boolean(), nullable=True, comment='IM启用'),
    sa.Column('receivers', sa.JSON(), nullable=True, comment='固定接收人列表'),
    sa.Column('receiver_roles', sa.JSON(), nullable=True, comment="接收角色: ['admin', 'engineer', 'station_manager']"),
    sa.Column('trigger_events', sa.JSON(), nullable=True, comment="触发事件: ['workorder_dispatch', 'workorder_urge', 'alarm_trigger', 'alarm_escalate', 'workorder_complete']"),
    sa.Column('template_overrides', sa.JSON(), nullable=True, comment="模板覆盖: {'sms': 'custom template', 'email': 'custom template'}"),
    sa.Column('quiet_start', sa.String(length=5), nullable=True, comment='静默开始时间 HH:MM'),
    sa.Column('quiet_end', sa.String(length=5), nullable=True, comment='静默结束时间 HH:MM'),
    sa.Column('timezone', sa.String(length=50), nullable=True, comment='时区'),
    sa.Column('rate_limit_per_hour', sa.Integer(), nullable=True, comment='每小时限制发送数'),
    sa.Column('rate_limit_per_day', sa.Integer(), nullable=True, comment='每天限制发送数'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('priority', sa.Integer(), nullable=True, comment='优先级，数值越大越优先'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_configs_enabled', 'notification_configs', ['enabled'], unique=False)
    op.create_index(op.f('ix_notification_configs_id'), 'notification_configs', ['id'], unique=False)
    op.create_index('ix_notification_configs_scope', 'notification_configs', ['scope_type', 'scope_id'], unique=False)
    op.create_index(op.f('ix_notification_configs_scope_id'), 'notification_configs', ['scope_id'], unique=False)
    op.create_table('notification_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=True),
    sa.Column('channels', sa.JSON(), nullable=True),
    sa.Column('receivers', sa.JSON(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_rules_id'), 'notification_rules', ['id'], unique=False)
    op.create_index(op.f('ix_notification_rules_level'), 'notification_rules', ['level'], unique=False)
    op.create_table('notification_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='模板名称'),
    sa.Column('code', sa.String(length=50), nullable=False, comment='模板代码，如 workorder_dispatch_sms'),
    sa.Column('channel', sa.String(length=20), nullable=False, comment='渠道: sms/email/app/im_b/im'),
    sa.Column('event_type', sa.String(length=50), nullable=False, comment='事件类型: workorder_dispatch/workorder_urge/alarm_trigger/...'),
    sa.Column('subject', sa.String(length=200), nullable=True, comment='主题（邮件用）'),
    sa.Column('content', sa.Text(), nullable=False, comment='模板内容，支持 {variable} 占位符'),
    sa.Column('variables', sa.JSON(), nullable=True, comment="变量列表: [{'name': 'order_id', 'desc': '工单号', 'example': 'WO-20260101-001'}]"),
    sa.Column('is_system', sa.Boolean(), nullable=True, comment='是否系统内置模板'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_templates_channel'), 'notification_templates', ['channel'], unique=False)
    op.create_index(op.f('ix_notification_templates_code'), 'notification_templates', ['code'], unique=True)
    op.create_index(op.f('ix_notification_templates_event_type'), 'notification_templates', ['event_type'], unique=False)
    op.create_index(op.f('ix_notification_templates_id'), 'notification_templates', ['id'], unique=False)
    op.create_table('ops_invoices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('applicant_name', sa.String(length=100), nullable=True, comment='申请人姓名'),
    sa.Column('applicant_phone', sa.String(length=20), nullable=True, comment='申请人手机'),
    sa.Column('apply_source', sa.String(length=20), nullable=True, comment='申请来源(app/admin)'),
    sa.Column('order_ids', sa.Text(), nullable=True, comment='关联订单ID列表(JSON)'),
    sa.Column('invoice_title_id', sa.Integer(), nullable=True, comment='关联抬头ID'),
    sa.Column('title_name', sa.String(length=200), nullable=False, comment='发票抬头(冗余)'),
    sa.Column('tax_id', sa.String(length=50), nullable=True, comment='税号(冗余)'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='开票金额(元)'),
    sa.Column('invoice_type', sa.Enum('ELECTRONIC', 'PAPER', name='opsinvoicetype'), nullable=True, comment='发票类型'),
    sa.Column('invoice_no', sa.String(length=50), nullable=True, comment='发票号码'),
    sa.Column('invoice_code', sa.String(length=50), nullable=True, comment='发票代码'),
    sa.Column('pdf_url', sa.String(length=500), nullable=True, comment='发票PDF链接'),
    sa.Column('status', sa.Enum('PENDING', 'REVIEWED', 'ISSUED', 'VOIDED', 'REJECTED', name='opsinvoicestatus'), nullable=True, comment='发票状态'),
    sa.Column('reviewer_id', sa.Integer(), nullable=True, comment='审核人ID'),
    sa.Column('review_time', sa.DateTime(), nullable=True, comment='审核时间'),
    sa.Column('review_remark', sa.String(length=500), nullable=True, comment='审核备注'),
    sa.Column('issue_time', sa.DateTime(), nullable=True, comment='开票时间'),
    sa.Column('issued_by', sa.String(length=100), nullable=True, comment='开票人'),
    sa.Column('void_reason', sa.String(length=500), nullable=True, comment='红冲原因'),
    sa.Column('void_time', sa.DateTime(), nullable=True, comment='红冲时间'),
    sa.Column('apply_time', sa.DateTime(), nullable=True, comment='申请时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_oi_apply_time', 'ops_invoices', ['apply_time'], unique=False)
    op.create_index('idx_oi_status', 'ops_invoices', ['status'], unique=False)
    op.create_index('idx_oi_title', 'ops_invoices', ['title_name'], unique=False)
    op.create_table('order_charge_curves',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False, comment='关联订单ID(charging_orders.id)'),
    sa.Column('record_time', sa.DateTime(), nullable=False, comment='记录时间'),
    sa.Column('current_power', sa.Numeric(precision=10, scale=2), nullable=True, comment='当前功率(kW)'),
    sa.Column('energy_this_minute', sa.Numeric(precision=10, scale=4), nullable=True, comment='本分钟电量(kWh)'),
    sa.Column('voltage', sa.Numeric(precision=10, scale=2), nullable=True, comment='电压(V)'),
    sa.Column('current', sa.Numeric(precision=10, scale=2), nullable=True, comment='电流(A)'),
    sa.Column('soc', sa.Numeric(precision=5, scale=2), nullable=True, comment='电池SOC(%)'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_occ_order', 'order_charge_curves', ['order_id'], unique=False)
    op.create_index('idx_occ_order_time', 'order_charge_curves', ['order_id', 'record_time'], unique=False)
    op.create_index(op.f('ix_order_charge_curves_order_id'), 'order_charge_curves', ['order_id'], unique=False)
    op.create_table('order_fee_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False, comment='充电订单ID'),
    sa.Column('fee_type', sa.Enum('ELECTRICITY', 'SERVICE', 'PARKING', 'OCCUPANCY', 'RESERVATION', 'DISCOUNT', 'COUPON', 'POINTS', name='feetype'), nullable=False, comment='费用类型'),
    sa.Column('fee_name', sa.String(length=64), nullable=False, comment='费用项名称'),
    sa.Column('quantity', sa.Numeric(precision=12, scale=4), nullable=True, comment='数量'),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=6), nullable=True, comment='单价'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='金额(元)'),
    sa.Column('unit', sa.String(length=20), nullable=True, comment='单位: kWh/小时/分钟/元/次'),
    sa.Column('remark', sa.String(length=255), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ofi_order', 'order_fee_items', ['order_id'], unique=False)
    op.create_index('idx_ofi_type', 'order_fee_items', ['fee_type'], unique=False)
    op.create_index(op.f('ix_order_fee_items_order_id'), 'order_fee_items', ['order_id'], unique=False)
    op.create_table('parking_discounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='商户站点ID'),
    sa.Column('merchant_name', sa.String(length=100), nullable=True, comment='商户名称'),
    sa.Column('discount_type', sa.String(length=30), nullable=False, comment='折扣类型: free_minutes/percentage/fixed'),
    sa.Column('free_minutes', sa.Integer(), nullable=True, comment='免费时长(分钟)'),
    sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True, comment='折扣比例(%)'),
    sa.Column('fixed_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='固定减免(元)'),
    sa.Column('max_discount', sa.Numeric(precision=12, scale=2), nullable=True, comment='单次最大减免(元)'),
    sa.Column('valid_start', sa.String(length=5), nullable=True, comment='每日有效开始 HH:MM'),
    sa.Column('valid_end', sa.String(length=5), nullable=True, comment='每日有效结束 HH:MM'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pd_active', 'parking_discounts', ['is_active'], unique=False)
    op.create_index('idx_pd_station', 'parking_discounts', ['station_id'], unique=False)
    op.create_index(op.f('ix_parking_discounts_station_id'), 'parking_discounts', ['station_id'], unique=False)
    op.create_table('payment_reconciliation',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('settlement_date', sa.Date(), nullable=False, comment='对账日期'),
    sa.Column('payment_channel', sa.String(length=50), nullable=False, comment='支付渠道(im_b/alipay/unionpay)'),
    sa.Column('platform_orders_count', sa.Integer(), nullable=True, comment='平台订单数'),
    sa.Column('platform_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='平台流水金额(元)'),
    sa.Column('payment_orders_count', sa.Integer(), nullable=True, comment='渠道订单数'),
    sa.Column('payment_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='渠道流水金额(元)'),
    sa.Column('difference_count', sa.Integer(), nullable=True, comment='差异数量'),
    sa.Column('difference_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='差异金额(元)'),
    sa.Column('difference_detail', sa.String(length=1000), nullable=True, comment='差异说明'),
    sa.Column('status', sa.Enum('PENDING', 'RECONCILED', name='reconciliationstatus'), nullable=True, comment='对账状态'),
    sa.Column('reconciled_at', sa.DateTime(), nullable=True, comment='对账完成时间'),
    sa.Column('reconciled_by', sa.String(length=100), nullable=True, comment='对账操作人'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pr_date_channel', 'payment_reconciliation', ['settlement_date', 'payment_channel'], unique=False)
    op.create_index('idx_pr_status', 'payment_reconciliation', ['status'], unique=False)
    op.create_index(op.f('ix_payment_reconciliation_settlement_date'), 'payment_reconciliation', ['settlement_date'], unique=False)
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('resource', sa.String(length=50), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_permissions_id'), 'permissions', ['id'], unique=False)
    op.create_index(op.f('ix_permissions_name'), 'permissions', ['name'], unique=True)
    op.create_table('points_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
    sa.Column('user_type', sa.String(length=50), nullable=True, comment='用户类型'),
    sa.Column('rule_id', sa.Integer(), nullable=True, comment='关联规则ID'),
    sa.Column('record_type', sa.Enum('EARN', 'REDEEM', 'EXPIRE', 'ADJUST', name='pointsrecordtype'), nullable=False, comment='流水类型'),
    sa.Column('points', sa.Integer(), nullable=False, comment='积分变动值(正数为获取)'),
    sa.Column('balance_before', sa.Integer(), nullable=False, comment='变动前余额'),
    sa.Column('balance_after', sa.Integer(), nullable=False, comment='变动后余额'),
    sa.Column('description', sa.Text(), nullable=True, comment='备注'),
    sa.Column('order_id', sa.Integer(), nullable=True, comment='关联订单ID'),
    sa.Column('expires_at', sa.DateTime(), nullable=True, comment='积分过期时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_prec_created', 'points_records', ['created_at'], unique=False)
    op.create_index('idx_prec_type', 'points_records', ['record_type'], unique=False)
    op.create_index('idx_prec_user_id', 'points_records', ['user_id'], unique=False)
    op.create_index(op.f('ix_points_records_order_id'), 'points_records', ['order_id'], unique=False)
    op.create_index(op.f('ix_points_records_rule_id'), 'points_records', ['rule_id'], unique=False)
    op.create_index(op.f('ix_points_records_user_id'), 'points_records', ['user_id'], unique=False)
    op.create_table('points_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='规则名称'),
    sa.Column('rule_type', sa.Enum('CHARGE', 'RECHARGE', 'SIGN_IN', 'INVITE', 'BIRTHDAY', 'ACTIVITY', 'SYSTEM', name='pointsruletype'), nullable=False, comment='规则类型'),
    sa.Column('points', sa.Integer(), nullable=False, comment='积分值'),
    sa.Column('unit', sa.String(length=50), nullable=True, comment="积分单位描述（如 '每消费1元'）"),
    sa.Column('daily_limit', sa.Integer(), nullable=True, comment='每日上限'),
    sa.Column('weekly_limit', sa.Integer(), nullable=True, comment='每周上限'),
    sa.Column('total_limit', sa.Integer(), nullable=True, comment='总上限'),
    sa.Column('applicable_user_types', sa.Text(), nullable=True, comment='适用用户类型，逗号分隔'),
    sa.Column('min_amount', sa.Numeric(precision=10, scale=2), nullable=True, comment='最低触发金额(元)'),
    sa.Column('points_expire_days', sa.Integer(), nullable=True, comment='积分过期天数'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('start_time', sa.DateTime(), nullable=True, comment='规则生效开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=True, comment='规则生效结束时间'),
    sa.Column('description', sa.Text(), nullable=True, comment='规则描述'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_points_rule_active', 'points_rules', ['is_active'], unique=False)
    op.create_index('idx_points_rule_type', 'points_rules', ['rule_type'], unique=False)
    op.create_table('price_discounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='折扣名称'),
    sa.Column('discount_type', sa.Enum('PERCENTAGE', 'FIXED', 'TIERED', name='discounttype'), nullable=False, comment='折扣类型'),
    sa.Column('discount_rate', sa.Numeric(precision=5, scale=2), nullable=False, comment='折扣率(0.00~1.00) 或固定金额'),
    sa.Column('applicable_user_types', sa.Text(), nullable=True, comment='适用用户类型，逗号分隔: app,card,vin,interconnect,enterprise'),
    sa.Column('min_consumption', sa.Numeric(precision=10, scale=2), nullable=True, comment='最低消费门槛(元)'),
    sa.Column('max_discount_amount', sa.Numeric(precision=10, scale=2), nullable=True, comment='最大折扣金额上限(元)'),
    sa.Column('start_time', sa.DateTime(), nullable=False, comment='生效开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=False, comment='生效结束时间'),
    sa.Column('priority', sa.Integer(), nullable=True, comment='优先级，数字越大越优先'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('description', sa.Text(), nullable=True, comment='描述'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_price_disc_active', 'price_discounts', ['is_active'], unique=False)
    op.create_index('idx_price_disc_priority', 'price_discounts', ['priority'], unique=False)
    op.create_index('idx_price_disc_type', 'price_discounts', ['discount_type'], unique=False)
    op.create_table('pricing_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='规则名称'),
    sa.Column('period_type', sa.Enum('PEAK', 'SHOULDER', 'VALLEY', 'FLAT', name='periodtype'), nullable=False, comment='时段类型: peak/shoulder/valley/flat'),
    sa.Column('start_time', sa.Time(), nullable=False, comment='时段开始时间'),
    sa.Column('end_time', sa.Time(), nullable=False, comment='时段结束时间'),
    sa.Column('electricity_price', sa.Numeric(precision=10, scale=4), nullable=False, comment='电价(元/kWh)'),
    sa.Column('service_fee_rate', sa.Numeric(precision=10, scale=4), nullable=False, comment='服务费率(元/kWh)'),
    sa.Column('parking_fee_per_hour', sa.Numeric(precision=10, scale=2), nullable=False, comment='停车费(元/小时)'),
    sa.Column('idle_penalty_per_min', sa.Numeric(precision=10, scale=2), nullable=False, comment='超时占用费(元/分钟)'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pr_active', 'pricing_rules', ['is_active'], unique=False)
    op.create_index('idx_pr_period', 'pricing_rules', ['period_type'], unique=False)
    op.create_table('refund_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False, comment='充电订单ID'),
    sa.Column('user_id', sa.Integer(), nullable=True, comment='用户ID'),
    sa.Column('refund_amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='退款金额(元)'),
    sa.Column('reason', sa.String(length=500), nullable=False, comment='退款原因'),
    sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REFUNDED', 'REJECTED', name='refundstatus'), nullable=False, comment='退款状态'),
    sa.Column('reviewer_id', sa.Integer(), nullable=True, comment='审核人ID'),
    sa.Column('reviewed_at', sa.DateTime(), nullable=True, comment='审核时间'),
    sa.Column('refunded_at', sa.DateTime(), nullable=True, comment='退款到账时间'),
    sa.Column('reject_reason', sa.String(length=500), nullable=True, comment='拒绝原因'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rr_order', 'refund_records', ['order_id'], unique=False)
    op.create_index('idx_rr_status', 'refund_records', ['status'], unique=False)
    op.create_index('idx_rr_user', 'refund_records', ['user_id'], unique=False)
    op.create_index(op.f('ix_refund_records_order_id'), 'refund_records', ['order_id'], unique=False)
    op.create_index(op.f('ix_refund_records_user_id'), 'refund_records', ['user_id'], unique=False)
    op.create_table('regulatory_reports',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=False, comment='关联 municipal_supervision_configs.id'),
    sa.Column('city', sa.String(length=100), nullable=True, comment='城市(冗余,便于筛选)'),
    sa.Column('report_type', sa.String(length=20), nullable=False, comment='上报类型 station/device/order/heartbeat'),
    sa.Column('report_content', sa.Text(), nullable=True, comment='上报内容(JSON)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 success/failed/pending'),
    sa.Column('retry_count', sa.Integer(), nullable=True, comment='重试次数'),
    sa.Column('error_message', sa.String(length=500), nullable=True, comment='失败错误信息'),
    sa.Column('reported_at', sa.DateTime(), nullable=True, comment='实际上报时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rreport_config', 'regulatory_reports', ['config_id'], unique=False)
    op.create_index('idx_rreport_status', 'regulatory_reports', ['status'], unique=False)
    op.create_index('idx_rreport_type', 'regulatory_reports', ['report_type'], unique=False)
    op.create_table('revenue_daily',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('record_date', sa.DateTime(), nullable=False, comment='统计日期'),
    sa.Column('user_type', sa.String(length=50), nullable=True, comment='用户类型 app/card/vin/interconnect/enterprise'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='站点ID'),
    sa.Column('orders_count', sa.Integer(), nullable=True, comment='订单数'),
    sa.Column('energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='充电量(kWh)'),
    sa.Column('charge_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='电费(元)'),
    sa.Column('service_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='服务费(元)'),
    sa.Column('parking_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='停车费(元)'),
    sa.Column('occupancy_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='占桩费(元)'),
    sa.Column('reservation_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='预约费(元)'),
    sa.Column('total_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='总营收(元)'),
    sa.Column('paid_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='已收营收(元)'),
    sa.Column('refund_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='退款金额(元)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rev_date', 'revenue_daily', ['record_date'], unique=False)
    op.create_index('idx_rev_station', 'revenue_daily', ['station_id'], unique=False)
    op.create_index('idx_rev_user_type', 'revenue_daily', ['user_type'], unique=False)
    op.create_index(op.f('ix_revenue_daily_record_date'), 'revenue_daily', ['record_date'], unique=False)
    op.create_index(op.f('ix_revenue_daily_station_id'), 'revenue_daily', ['station_id'], unique=False)
    op.create_index(op.f('ix_revenue_daily_user_type'), 'revenue_daily', ['user_type'], unique=False)
    op.create_table('roles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)
    op.create_table('runbook_approval_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('approval_id', sa.Integer(), nullable=True, comment='关联审批ID'),
    sa.Column('action', sa.String(length=20), nullable=True, comment='操作: approve/reject/expire/escalate'),
    sa.Column('operator_id', sa.Integer(), nullable=True, comment='操作人ID'),
    sa.Column('operator_name', sa.String(length=100), nullable=True, comment='操作人姓名'),
    sa.Column('comment', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_runbook_approval_logs_approval_id'), 'runbook_approval_logs', ['approval_id'], unique=False)
    op.create_index(op.f('ix_runbook_approval_logs_id'), 'runbook_approval_logs', ['id'], unique=False)
    op.create_table('runbook_approvals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('runbook_id', sa.String(length=64), nullable=True, comment='关联Runbook执行ID'),
    sa.Column('alarm_id', sa.Integer(), nullable=True, comment='关联告警ID'),
    sa.Column('step_index', sa.Integer(), nullable=True, comment='等待审批的步骤索引(JSON中)'),
    sa.Column('step_description', sa.String(length=500), nullable=True, comment='步骤描述'),
    sa.Column('action_type', sa.String(length=50), nullable=True, comment='动作类型'),
    sa.Column('command_preview', sa.Text(), nullable=True, comment='将执行的命令预览'),
    sa.Column('risk_level', sa.String(length=20), nullable=True, comment='风险等级: medium/high/critical'),
    sa.Column('rollback_preview', sa.Text(), nullable=True, comment='回滚命令预览'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='审批状态: pending/approved/rejected/expired'),
    sa.Column('required_level', sa.String(length=20), nullable=True, comment='所需审批人级别: operator/manager/admin'),
    sa.Column('approver_id', sa.Integer(), nullable=True, comment='审批人ID'),
    sa.Column('approver_name', sa.String(length=100), nullable=True, comment='审批人姓名'),
    sa.Column('approved_at', sa.DateTime(), nullable=True, comment='审批时间'),
    sa.Column('reject_reason', sa.Text(), nullable=True, comment='拒绝原因'),
    sa.Column('auto_execute_after_approval', sa.Boolean(), nullable=True, comment='审批通过后是否自动执行'),
    sa.Column('executed_after_approval', sa.Boolean(), nullable=True, comment='审批后是否已执行'),
    sa.Column('expires_at', sa.DateTime(), nullable=True, comment='审批超时时间(默认30分钟)'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_runbook_approvals_alarm_id'), 'runbook_approvals', ['alarm_id'], unique=False)
    op.create_index(op.f('ix_runbook_approvals_id'), 'runbook_approvals', ['id'], unique=False)
    op.create_index(op.f('ix_runbook_approvals_runbook_id'), 'runbook_approvals', ['runbook_id'], unique=False)
    op.create_table('runbook_executions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('runbook_id', sa.String(length=64), nullable=True, comment='Runbook执行ID'),
    sa.Column('alarm_id', sa.Integer(), nullable=True, comment='关联告警ID'),
    sa.Column('diagnosis_record_id', sa.Integer(), nullable=True, comment='关联AI诊断记录ID'),
    sa.Column('device_id', sa.Integer(), nullable=True, comment='关联设备ID'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='关联站点ID'),
    sa.Column('fault_type', sa.String(length=200), nullable=True, comment='故障类型'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='执行状态'),
    sa.Column('steps_json', sa.JSON(), nullable=True, comment='执行步骤详情(JSON)'),
    sa.Column('start_time', sa.DateTime(), nullable=True, comment='开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=True, comment='结束时间'),
    sa.Column('total_duration_ms', sa.Integer(), nullable=True, comment='总耗时(ms)'),
    sa.Column('success_steps', sa.Integer(), nullable=True),
    sa.Column('failed_steps', sa.Integer(), nullable=True),
    sa.Column('skipped_steps', sa.Integer(), nullable=True),
    sa.Column('auto_executed', sa.Integer(), nullable=True, comment='自动执行步骤数'),
    sa.Column('manual_required', sa.Integer(), nullable=True, comment='需人工步骤数'),
    sa.Column('workorder_id', sa.Integer(), nullable=True, comment='自动创建的工单ID'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_runbook_executions_alarm_id'), 'runbook_executions', ['alarm_id'], unique=False)
    op.create_index(op.f('ix_runbook_executions_device_id'), 'runbook_executions', ['device_id'], unique=False)
    op.create_index(op.f('ix_runbook_executions_id'), 'runbook_executions', ['id'], unique=False)
    op.create_index(op.f('ix_runbook_executions_runbook_id'), 'runbook_executions', ['runbook_id'], unique=True)
    op.create_index(op.f('ix_runbook_executions_station_id'), 'runbook_executions', ['station_id'], unique=False)
    op.create_table('sms_verification_codes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False, comment='手机号'),
    sa.Column('code', sa.String(length=6), nullable=False, comment='验证码'),
    sa.Column('purpose', sa.String(length=20), nullable=False, comment='用途: login/register/reset'),
    sa.Column('used', sa.Integer(), nullable=True, comment='是否已使用: 0=未使用, 1=已使用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment='过期时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sms_expires_at', 'sms_verification_codes', ['expires_at'], unique=False)
    op.create_index('ix_sms_phone_purpose_used', 'sms_verification_codes', ['phone', 'purpose', 'used'], unique=False)
    op.create_index(op.f('ix_sms_verification_codes_id'), 'sms_verification_codes', ['id'], unique=False)
    op.create_index(op.f('ix_sms_verification_codes_phone'), 'sms_verification_codes', ['phone'], unique=False)
    op.create_table('ssl_certificates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False, comment='域名/IP'),
    sa.Column('email', sa.String(length=255), nullable=False, comment="Let's Encrypt 通知邮箱"),
    sa.Column('cert_path', sa.String(length=512), nullable=True, comment='证书完整路径'),
    sa.Column('key_path', sa.String(length=512), nullable=True, comment='私钥路径'),
    sa.Column('issuer', sa.String(length=255), nullable=True, comment='签发机构'),
    sa.Column('serial_number', sa.String(length=128), nullable=True, comment='证书序列号'),
    sa.Column('not_before', sa.DateTime(), nullable=True, comment='生效时间'),
    sa.Column('not_after', sa.DateTime(), nullable=True, comment='过期时间'),
    sa.Column('subject_alt_names', sa.Text(), nullable=True, comment='SAN 列表 (JSON数组)'),
    sa.Column('auto_renew', sa.Boolean(), nullable=True, comment='是否自动续期'),
    sa.Column('renew_days_before', sa.Integer(), nullable=True, comment='提前多少天续期'),
    sa.Column('status', sa.String(length=32), nullable=True, comment='状态: pending|active|expiring_soon|expired|error'),
    sa.Column('last_renew_at', sa.DateTime(), nullable=True, comment='上次续期时间'),
    sa.Column('last_renew_success', sa.Boolean(), nullable=True, comment='上次续期是否成功'),
    sa.Column('last_renew_error', sa.Text(), nullable=True, comment='上次续期错误信息'),
    sa.Column('last_check_at', sa.DateTime(), nullable=True, comment='上次状态检查时间'),
    sa.Column('nginx_conf_path', sa.String(length=512), nullable=True, comment='Nginx 配置文件路径'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ssl_certificates_domain'), 'ssl_certificates', ['domain'], unique=True)
    op.create_index(op.f('ix_ssl_certificates_id'), 'ssl_certificates', ['id'], unique=False)
    op.create_table('station_daily_metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('record_date', sa.DateTime(), nullable=False, comment='统计日期'),
    sa.Column('active_users', sa.Integer(), nullable=True, comment='活跃用户数'),
    sa.Column('new_users', sa.Integer(), nullable=True, comment='新增用户数'),
    sa.Column('orders_count', sa.Integer(), nullable=True, comment='订单数'),
    sa.Column('energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='充电量(kWh)'),
    sa.Column('revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='营收(元)'),
    sa.Column('utilization_rate', sa.Numeric(precision=5, scale=2), nullable=True, comment='利用率(%)'),
    sa.Column('avg_charge_duration', sa.Integer(), nullable=True, comment='平均充电时长(分钟)'),
    sa.Column('avg_wait_time', sa.Integer(), nullable=True, comment='平均等待时长(分钟)'),
    sa.Column('online_devices', sa.Integer(), nullable=True, comment='在线设备数'),
    sa.Column('idle_ratio', sa.Numeric(precision=5, scale=2), nullable=True, comment='空闲率(%)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sdm_date', 'station_daily_metrics', ['record_date'], unique=False)
    op.create_index('idx_sdm_station', 'station_daily_metrics', ['station_id'], unique=False)
    op.create_index('idx_sdm_station_date', 'station_daily_metrics', ['station_id', 'record_date'], unique=False)
    op.create_index(op.f('ix_station_daily_metrics_record_date'), 'station_daily_metrics', ['record_date'], unique=False)
    op.create_index(op.f('ix_station_daily_metrics_station_id'), 'station_daily_metrics', ['station_id'], unique=False)
    op.create_table('teams',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=True),
    sa.Column('leader_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_teams_code'), 'teams', ['code'], unique=True)
    op.create_index(op.f('ix_teams_id'), 'teams', ['id'], unique=False)
    op.create_index(op.f('ix_teams_name'), 'teams', ['name'], unique=True)
    op.create_table('tenants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='租户名称'),
    sa.Column('code', sa.String(length=50), nullable=False, comment='租户编码'),
    sa.Column('description', sa.Text(), nullable=True, comment='描述'),
    sa.Column('contact_name', sa.String(length=50), nullable=True, comment='联系人'),
    sa.Column('contact_phone', sa.String(length=20), nullable=True, comment='联系电话'),
    sa.Column('contact_email', sa.String(length=100), nullable=True, comment='联系邮箱'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态: active/inactive/suspended'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否激活'),
    sa.Column('max_stations', sa.Integer(), nullable=True, comment='最大站点数'),
    sa.Column('max_devices', sa.Integer(), nullable=True, comment='最大设备数'),
    sa.Column('max_users', sa.Integer(), nullable=True, comment='最大用户数'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('expired_at', sa.DateTime(), nullable=True, comment='过期时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index('idx_tenant_code', 'tenants', ['code'], unique=False)
    op.create_index('idx_tenant_status', 'tenants', ['status'], unique=False)
    op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)
    op.create_table('terminals',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('terminal_code', sa.String(length=100), nullable=False, comment='终端编号(唯一)'),
    sa.Column('terminal_type', sa.String(length=30), nullable=False, comment='类型 camera/sensor/access_control'),
    sa.Column('station_name', sa.String(length=200), nullable=True, comment='安装站点'),
    sa.Column('ip_address', sa.String(length=50), nullable=True, comment='IP地址'),
    sa.Column('rtsp_url', sa.String(length=500), nullable=True, comment='流地址 RTSP/RTMP'),
    sa.Column('recording_config', sa.Text(), nullable=True, comment='录制配置(JSON): enable/quality/retention_days'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 online/offline/maintenance'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('terminal_code')
    )
    op.create_index('idx_terminal_station', 'terminals', ['station_name'], unique=False)
    op.create_index('idx_terminal_status', 'terminals', ['status'], unique=False)
    op.create_index('idx_terminal_type', 'terminals', ['terminal_type'], unique=False)
    op.create_table('time_slot_definitions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False, comment='时段名称: 尖/峰/平/谷'),
    sa.Column('period_type', sa.Enum('PEAK', 'SHOULDER', 'FLAT', 'VALLEY', name='periodtype'), nullable=False, comment='时段类型枚举'),
    sa.Column('start_time', sa.Time(), nullable=False, comment='开始时间'),
    sa.Column('end_time', sa.Time(), nullable=False, comment='结束时间'),
    sa.Column('description', sa.String(length=200), nullable=True, comment='描述'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('sort_order', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('period_type')
    )
    op.create_index('idx_tsd_active', 'time_slot_definitions', ['is_active'], unique=False)
    op.create_index('idx_tsd_period', 'time_slot_definitions', ['period_type'], unique=False)
    op.create_table('upgrade_tasks',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('gateway_id', sa.BigInteger(), nullable=False),
    sa.Column('firmware_id', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=True),
    sa.Column('start_time', sa.DateTime(), nullable=True),
    sa.Column('end_time', sa.DateTime(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_upgrade_tasks_id'), 'upgrade_tasks', ['id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('real_name', sa.String(length=100), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('role', sa.Enum('super_admin', 'admin', 'dispatcher', 'station_master', 'engineer', 'operator', 'viewer', 'technician', 'auditor', name='userrole'), nullable=True),
    sa.Column('level', sa.Enum('junior', 'middle', 'senior', name='engineerlevel'), nullable=True),
    sa.Column('team_id', sa.Integer(), nullable=True),
    sa.Column('skills', sa.Text(), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('last_location_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('vin_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('vin', sa.String(length=50), nullable=False, comment='车辆识别码(VIN)'),
    sa.Column('brand', sa.String(length=50), nullable=True, comment='品牌'),
    sa.Column('model', sa.String(length=100), nullable=True, comment='车型'),
    sa.Column('plate_number', sa.String(length=20), nullable=True, comment='车牌号'),
    sa.Column('user_id', sa.Integer(), nullable=True, comment='关联系统用户ID'),
    sa.Column('bind_phone', sa.String(length=20), nullable=True, comment='绑定手机号'),
    sa.Column('auto_pay_account', sa.String(length=100), nullable=True, comment='自动代扣账户'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态 active/inactive'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_vin_user_plate', 'vin_users', ['plate_number'], unique=False)
    op.create_index('idx_vin_user_user_id', 'vin_users', ['user_id'], unique=False)
    op.create_index('idx_vin_user_vin', 'vin_users', ['vin'], unique=False)
    op.create_index(op.f('ix_vin_users_plate_number'), 'vin_users', ['plate_number'], unique=False)
    op.create_index(op.f('ix_vin_users_user_id'), 'vin_users', ['user_id'], unique=False)
    op.create_index(op.f('ix_vin_users_vin'), 'vin_users', ['vin'], unique=True)
    op.create_table('webhooks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='Webhook 名称'),
    sa.Column('url', sa.String(length=500), nullable=False, comment='回调 URL'),
    sa.Column('event_types', sa.Text(), nullable=False, comment='订阅事件类型 JSON: ["alert","ticket"]'),
    sa.Column('secret', sa.String(length=256), nullable=True, comment='HMAC-SHA256 签名密钥'),
    sa.Column('retry_count', sa.Integer(), nullable=True, comment='失败重试次数'),
    sa.Column('retry_interval', sa.Integer(), nullable=True, comment='重试间隔(秒)'),
    sa.Column('timeout', sa.Integer(), nullable=True, comment='请求超时(秒)'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('description', sa.String(length=500), nullable=True, comment='描述'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_webhook_enabled', 'webhooks', ['enabled'], unique=False)
    op.create_table('api_clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('client_secret_hash', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('callback_url', sa.String(length=500), nullable=True),
    sa.Column('scopes', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('rate_limit', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_clients_client_id'), 'api_clients', ['client_id'], unique=True)
    op.create_index(op.f('ix_api_clients_id'), 'api_clients', ['id'], unique=False)
    op.create_table('api_endpoints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('path', sa.String(length=500), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('rate_limit', sa.Integer(), nullable=True),
    sa.Column('require_auth', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('registered_at', sa.DateTime(), nullable=True),
    sa.Column('deprecated_at', sa.DateTime(), nullable=True),
    sa.Column('registered_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True
    )
    op.create_index(op.f('ix_api_endpoints_id'), 'api_endpoints', ['id'], unique=False)
    op.create_table('api_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False, comment='密钥哈希'),
    sa.Column('key_prefix', sa.String(length=10), nullable=False, comment='密钥前缀(用于识别)'),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False, comment='密钥名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='描述'),
    sa.Column('scopes', sa.JSON(), nullable=True, comment='权限范围'),
    sa.Column('ip_whitelist', sa.JSON(), nullable=True, comment='IP白名单'),
    sa.Column('rate_limit', sa.Integer(), nullable=True, comment='每分钟请求限制'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否激活'),
    sa.Column('is_revoked', sa.Boolean(), nullable=True, comment='是否已撤销'),
    sa.Column('revoked_reason', sa.Text(), nullable=True, comment='撤销原因'),
    sa.Column('revoked_at', sa.DateTime(), nullable=True, comment='撤销时间'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True, comment='过期时间'),
    sa.Column('last_used_at', sa.DateTime(), nullable=True, comment='最后使用时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_api_key_active', 'api_keys', ['is_active', 'is_revoked'], unique=False)
    op.create_index('idx_api_key_tenant', 'api_keys', ['tenant_id'], unique=False)
    op.create_index('idx_api_key_user', 'api_keys', ['user_id'], unique=False)
    op.create_index(op.f('ix_api_keys_id'), 'api_keys', ['id'], unique=False)
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=True)
    op.create_index(op.f('ix_api_keys_tenant_id'), 'api_keys', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_api_keys_user_id'), 'api_keys', ['user_id'], unique=False)
    op.create_table('charging_schedule_entries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False, comment='所属计划ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('assigned_power_kw', sa.Float(), nullable=False, comment='分配功率(kW)'),
    sa.Column('start_time', sa.DateTime(), nullable=False, comment='开始充电时间'),
    sa.Column('end_time', sa.DateTime(), nullable=True, comment='结束充电时间'),
    sa.Column('priority', sa.Integer(), nullable=False, comment='调度优先级 (数字越小越优先)'),
    sa.Column('soc_start', sa.Float(), nullable=False, comment='开始SOC (0.0-1.0)'),
    sa.Column('soc_target', sa.Float(), nullable=False, comment='目标SOC (0.0-1.0)'),
    sa.Column('charge_mode', sa.Enum('CHARGE', 'DISCHARGE', 'IDLE', name='chargingentrymode'), nullable=False, comment='充放电模式(charge/discharge/idle)'),
    sa.Column('period_type', sa.Enum('PEAK', 'FLAT', 'VALLEY', name='chargingperiodtype'), nullable=True, comment='时段类型(peak/flat/valley)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cse_plan', 'charging_schedule_entries', ['plan_id'], unique=False)
    op.create_index('idx_cse_priority', 'charging_schedule_entries', ['priority'], unique=False)
    op.create_index('idx_cse_vehicle', 'charging_schedule_entries', ['vehicle_id'], unique=False)
    op.create_index(op.f('ix_charging_schedule_entries_plan_id'), 'charging_schedule_entries', ['plan_id'], unique=False)
    op.create_index(op.f('ix_charging_schedule_entries_vehicle_id'), 'charging_schedule_entries', ['vehicle_id'], unique=False)
    op.create_table('enterprises',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False, comment='企业名称'),
    sa.Column('code', sa.String(length=50), nullable=False, comment='企业编码'),
    sa.Column('contact', sa.String(length=100), nullable=True, comment='联系人'),
    sa.Column('phone', sa.String(length=20), nullable=True, comment='联系电话'),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=True, comment='账户余额(元)'),
    sa.Column('credit_limit', sa.Numeric(precision=12, scale=2), nullable=True, comment='信用额度(元)'),
    sa.Column('default_vehicle_config', sa.JSON(), nullable=True, comment='默认车辆配置(JSON)'),
    sa.Column('owner_team_id', sa.Integer(), nullable=True, comment='经营团队ID'),
    sa.Column('address', sa.String(length=500), nullable=True, comment='企业地址'),
    sa.Column('description', sa.Text(), nullable=True, comment='企业描述'),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'SUSPENDED', name='enterprisestatus'), nullable=True, comment='状态'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index('idx_enterprise_code', 'enterprises', ['code'], unique=False)
    op.create_index('idx_enterprise_owner_team', 'enterprises', ['owner_team_id'], unique=False)
    op.create_index('idx_enterprise_status', 'enterprises', ['status'], unique=False)
    op.create_index(op.f('ix_enterprises_owner_team_id'), 'enterprises', ['owner_team_id'], unique=False)
    op.create_table('inspection_plans',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False, comment='计划名称'),
    sa.Column('cycle', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY', name='plancycle'), nullable=False, comment='执行周期'),
    sa.Column('target', sa.Enum('ALL', 'INVERTER', 'BATTERY', 'CHARGER', 'GATEWAY', name='plantarget'), nullable=True, comment='巡检对象'),
    sa.Column('assignee', sa.String(length=100), nullable=True, comment='负责人'),
    sa.Column('assignee_id', sa.Integer(), nullable=True, comment='负责人用户ID'),
    sa.Column('team_id', sa.Integer(), nullable=True, comment='所属团队'),
    sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', name='planstatus'), nullable=True, comment='计划状态'),
    sa.Column('next_execute', sa.Date(), nullable=True, comment='下次执行日期'),
    sa.Column('last_execute', sa.Date(), nullable=True, comment='上次执行日期'),
    sa.Column('description', sa.Text(), nullable=True, comment='计划描述'),
    sa.Column('config', sa.JSON(), nullable=True, comment='检查项配置（JSON）'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspection_plans_id'), 'inspection_plans', ['id'], unique=False)
    op.create_table('knowledge_articles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tags', sa.String(length=500), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('view_count', sa.Integer(), nullable=True),
    sa.Column('published', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_articles_category'), 'knowledge_articles', ['category'], unique=False)
    op.create_index(op.f('ix_knowledge_articles_id'), 'knowledge_articles', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_articles_title'), 'knowledge_articles', ['title'], unique=False)
    op.create_table('knowledge_faq',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question', sa.String(length=500), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('tags', sa.String(length=500), nullable=True),
    sa.Column('views', sa.Integer(), nullable=True),
    sa.Column('helpful_count', sa.Integer(), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_faq_category'), 'knowledge_faq', ['category'], unique=False)
    op.create_index(op.f('ix_knowledge_faq_id'), 'knowledge_faq', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_faq_question'), 'knowledge_faq', ['question'], unique=False)
    op.create_table('notification_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=True, comment='关联配置ID'),
    sa.Column('event_type', sa.String(length=50), nullable=False, comment='事件类型'),
    sa.Column('event_id', sa.String(length=100), nullable=True, comment='事件ID (工单号/告警ID)'),
    sa.Column('event_data', sa.JSON(), nullable=True, comment='事件数据快照，用于模板渲染'),
    sa.Column('channel', sa.String(length=20), nullable=False, comment='发送渠道'),
    sa.Column('template_id', sa.Integer(), nullable=True, comment='使用的模板ID'),
    sa.Column('template_code', sa.String(length=50), nullable=True, comment='模板代码（冗余）'),
    sa.Column('receiver_type', sa.String(length=20), nullable=False, comment='接收者类型: user/phone/email/webhook'),
    sa.Column('receiver_id', sa.String(length=100), nullable=False, comment='接收者标识'),
    sa.Column('receiver_name', sa.String(length=100), nullable=True, comment='接收者姓名'),
    sa.Column('subject', sa.String(length=200), nullable=True, comment='主题'),
    sa.Column('content', sa.Text(), nullable=False, comment='实际发送内容'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态: pending/sent/failed/blocked'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('provider_response', sa.JSON(), nullable=True, comment='服务商响应'),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True, comment='发送时间'),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True, comment='送达时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_logs_channel'), 'notification_logs', ['channel'], unique=False)
    op.create_index(op.f('ix_notification_logs_config_id'), 'notification_logs', ['config_id'], unique=False)
    op.create_index('ix_notification_logs_event', 'notification_logs', ['event_type', 'event_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_event_id'), 'notification_logs', ['event_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_event_type'), 'notification_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_notification_logs_id'), 'notification_logs', ['id'], unique=False)
    op.create_index('ix_notification_logs_receiver', 'notification_logs', ['receiver_type', 'receiver_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_receiver_id'), 'notification_logs', ['receiver_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_status'), 'notification_logs', ['status'], unique=False)
    op.create_index('ix_notification_logs_status_time', 'notification_logs', ['status', 'created_at'], unique=False)
    op.create_table('repair_guides',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('fault_code_id', sa.Integer(), nullable=True),
    sa.Column('symptoms', sa.JSON(), nullable=True),
    sa.Column('diagnosis_process', sa.JSON(), nullable=True),
    sa.Column('repair_steps', sa.JSON(), nullable=True),
    sa.Column('required_tools', sa.JSON(), nullable=True),
    sa.Column('safety_notes', sa.JSON(), nullable=True),
    sa.Column('estimated_time_minutes', sa.Integer(), nullable=True),
    sa.Column('difficulty_level', sa.Integer(), nullable=True),
    sa.Column('success_rate', sa.Float(), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repair_guides_id'), 'repair_guides', ['id'], unique=False)
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_table('stations',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('province', sa.String(length=50), nullable=True),
    sa.Column('city', sa.String(length=50), nullable=True),
    sa.Column('district', sa.String(length=50), nullable=True),
    sa.Column('address', sa.String(length=200), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('operator_id', sa.Integer(), nullable=True),
    sa.Column('operator_name', sa.String(length=100), nullable=True),
    sa.Column('team_id', sa.Integer(), nullable=True),
    sa.Column('total_power', sa.Float(), nullable=True),
    sa.Column('total_devices', sa.Integer(), nullable=True),
    sa.Column('gun_count', sa.Integer(), nullable=True),
    sa.Column('venue_type', sa.String(length=50), nullable=True, comment='建设场所: highway_station/transport_hub/mall/community/industrial_park'),
    sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True, comment='站点总成本(元)'),
    sa.Column('parking_spots', sa.Integer(), nullable=True, comment='车位数'),
    sa.Column('station_type', sa.String(length=50), nullable=True, comment='站点类型: public/private/residential'),
    sa.Column('status', sa.Enum('NORMAL', 'MAINTENANCE', 'CLOSED', 'ACTIVE', name='stationstatus'), nullable=True),
    sa.Column('health_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stations_code'), 'stations', ['code'], unique=True)
    op.create_index(op.f('ix_stations_id'), 'stations', ['id'], unique=False)
    op.create_index(op.f('ix_stations_name'), 'stations', ['name'], unique=False)
    op.create_table('tenant_audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False, comment='操作类型'),
    sa.Column('resource_type', sa.String(length=50), nullable=False, comment='资源类型'),
    sa.Column('resource_id', sa.Integer(), nullable=True, comment='资源ID'),
    sa.Column('old_value', sa.Text(), nullable=True, comment='旧值(JSON)'),
    sa.Column('new_value', sa.Text(), nullable=True, comment='新值(JSON)'),
    sa.Column('ip_address', sa.String(length=50), nullable=True, comment='IP地址'),
    sa.Column('user_agent', sa.Text(), nullable=True, comment='User-Agent'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tenant_audit_action', 'tenant_audit_logs', ['action'], unique=False)
    op.create_index('idx_tenant_audit_created', 'tenant_audit_logs', ['created_at'], unique=False)
    op.create_index('idx_tenant_audit_tenant', 'tenant_audit_logs', ['tenant_id'], unique=False)
    op.create_index('idx_tenant_audit_user', 'tenant_audit_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_tenant_audit_logs_id'), 'tenant_audit_logs', ['id'], unique=False)
    op.create_table('tenant_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('config_key', sa.String(length=100), nullable=False, comment='配置键'),
    sa.Column('config_value', sa.Text(), nullable=True, comment='配置值(JSON)'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tenant_config', 'tenant_configs', ['tenant_id', 'config_key'], unique=True)
    op.create_index(op.f('ix_tenant_configs_id'), 'tenant_configs', ['id'], unique=False)
    op.create_table('third_party_integrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('config_type', sa.String(length=50), nullable=True),
    sa.Column('config_data', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('webhook_url', sa.String(length=500), nullable=True),
    sa.Column('webhook_secret', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_third_party_integrations_id'), 'third_party_integrations', ['id'], unique=False)
    op.create_table('user_roles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_table('vehicles',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('plate_number', sa.String(length=20), nullable=False, comment='车牌号'),
    sa.Column('vin', sa.String(length=50), nullable=False, comment='VIN码'),
    sa.Column('brand', sa.String(length=50), nullable=True, comment='品牌'),
    sa.Column('model', sa.String(length=100), nullable=True, comment='车型'),
    sa.Column('color', sa.String(length=20), nullable=True, comment='颜色'),
    sa.Column('year', sa.Integer(), nullable=True, comment='出厂年份'),
    sa.Column('energy_type', sa.String(length=20), nullable=True, comment='能源类型: electric/gasoline/diesel/hybrid'),
    sa.Column('battery_capacity', sa.Float(), nullable=True, comment='电池容量(kWh)'),
    sa.Column('mileage', sa.Float(), nullable=True, comment='累计里程(km)'),
    sa.Column('driver_id', sa.Integer(), nullable=True, comment='绑定的司机用户ID'),
    sa.Column('driver_name', sa.String(length=100), nullable=True, comment='司机姓名'),
    sa.Column('driver_phone', sa.String(length=20), nullable=True, comment='司机电话'),
    sa.Column('tenant_id', sa.Integer(), nullable=True, comment='所属企业租户ID'),
    sa.Column('status', sa.Enum('ACTIVE', 'IDLE', 'MAINTENANCE', 'RETIRED', name='vehiclestatus'), nullable=True, comment='车辆状态'),
    sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=True, comment='购入日期'),
    sa.Column('insurance_expire', sa.DateTime(timezone=True), nullable=True, comment='保险到期'),
    sa.Column('last_maintenance_date', sa.DateTime(timezone=True), nullable=True, comment='上次保养日期'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('vin')
    )
    op.create_index(op.f('ix_vehicles_driver_id'), 'vehicles', ['driver_id'], unique=False)
    op.create_index(op.f('ix_vehicles_id'), 'vehicles', ['id'], unique=False)
    op.create_index(op.f('ix_vehicles_plate_number'), 'vehicles', ['plate_number'], unique=True)
    op.create_index(op.f('ix_vehicles_tenant_id'), 'vehicles', ['tenant_id'], unique=False)
    op.create_table('webhook_deliveries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('webhook_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=30), nullable=True, comment='触发事件类型'),
    sa.Column('payload', sa.Text(), nullable=True, comment='请求体 JSON'),
    sa.Column('status_code', sa.Integer(), nullable=True, comment='HTTP 响应码'),
    sa.Column('response_body', sa.Text(), nullable=True, comment='响应内容(截取前2000字符)'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='投递状态 success/failed/pending/retrying'),
    sa.Column('duration_ms', sa.Integer(), nullable=True, comment='耗时(毫秒)'),
    sa.Column('attempt', sa.Integer(), nullable=True, comment='第几次尝试'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_delivery_status', 'webhook_deliveries', ['status'], unique=False)
    op.create_index('idx_delivery_webhook', 'webhook_deliveries', ['webhook_id'], unique=False)
    op.create_index(op.f('ix_webhook_deliveries_webhook_id'), 'webhook_deliveries', ['webhook_id'], unique=False)
    op.create_table('api_key_usage_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('api_key_id', sa.Integer(), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False, comment='HTTP方法'),
    sa.Column('path', sa.String(length=500), nullable=False, comment='请求路径'),
    sa.Column('status_code', sa.Integer(), nullable=True, comment='状态码'),
    sa.Column('ip_address', sa.String(length=50), nullable=True, comment='IP地址'),
    sa.Column('user_agent', sa.Text(), nullable=True, comment='User-Agent'),
    sa.Column('duration_ms', sa.Integer(), nullable=True, comment='响应时间ms'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_api_usage_created', 'api_key_usage_logs', ['created_at'], unique=False)
    op.create_index('idx_api_usage_key', 'api_key_usage_logs', ['api_key_id'], unique=False)
    op.create_index('idx_api_usage_path', 'api_key_usage_logs', ['path'], unique=False)
    op.create_index(op.f('ix_api_key_usage_logs_api_key_id'), 'api_key_usage_logs', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_api_key_usage_logs_id'), 'api_key_usage_logs', ['id'], unique=False)
    op.create_table('api_usage_quotas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('quota_type', sa.String(length=50), nullable=True),
    sa.Column('monthly_limit', sa.BigInteger(), nullable=True),
    sa.Column('current_month_usage', sa.BigInteger(), nullable=True),
    sa.Column('daily_limit', sa.Integer(), nullable=True),
    sa.Column('current_day_usage', sa.Integer(), nullable=True),
    sa.Column('reset_day', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id')
    )
    op.create_index(op.f('ix_api_usage_quotas_id'), 'api_usage_quotas', ['id'], unique=False)
    op.create_table('devices',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('sn', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('type', sa.Enum('CHARGER_DC', 'CHARGER_AC', 'V2G_CHARGER', 'PV_INVERTER', 'BATTERY_INVERTER', 'PCS', 'BATTERY', 'METER', 'GATEWAY', name='devicetype'), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=True),
    sa.Column('manufacturer', sa.String(length=100), nullable=True),
    sa.Column('brand', sa.String(length=50), nullable=True),
    sa.Column('protocol_type', sa.Enum('MODBUS_RTU', 'MQTT', 'MODBUS_TCP', 'CAN', 'OPCUA', name='protocoltype'), nullable=True),
    sa.Column('device_address', sa.Integer(), nullable=True),
    sa.Column('tcu_address', sa.String(length=50), nullable=True),
    sa.Column('firmware_version', sa.String(length=20), nullable=True),
    sa.Column('hardware_version', sa.String(length=20), nullable=True),
    sa.Column('modbus_baudrate', sa.Integer(), nullable=True),
    sa.Column('modbus_databits', sa.Integer(), nullable=True),
    sa.Column('modbus_parity', sa.String(length=10), nullable=True),
    sa.Column('modbus_stopbits', sa.Integer(), nullable=True),
    sa.Column('modbus_timeout_ms', sa.Integer(), nullable=True),
    sa.Column('modbus_retry_count', sa.Integer(), nullable=True),
    sa.Column('mqtt_client_id', sa.String(length=100), nullable=True),
    sa.Column('mqtt_qos', sa.Integer(), nullable=True),
    sa.Column('mqtt_keepalive', sa.Integer(), nullable=True),
    sa.Column('comm_config', sa.JSON(), nullable=True),
    sa.Column('rated_power', sa.Float(), nullable=True),
    sa.Column('rated_voltage', sa.Float(), nullable=True),
    sa.Column('rated_current', sa.Float(), nullable=True),
    sa.Column('gun_count', sa.Integer(), nullable=True),
    sa.Column('station_id', sa.Integer(), nullable=False),
    sa.Column('gateway_id', sa.Integer(), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('status', sa.Enum('ONLINE', 'OFFLINE', 'CHARGING', 'FAULT', 'MAINTENANCE', name='devicestatus'), nullable=True),
    sa.Column('health_score', sa.Float(), nullable=True),
    sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
    sa.Column('total_run_hours', sa.Float(), nullable=True),
    sa.Column('total_charge_kwh', sa.Float(), nullable=True),
    sa.Column('total_discharge_kwh', sa.Float(), nullable=True),
    sa.Column('total_generation_kwh', sa.Float(), nullable=True),
    sa.Column('utilization_rate', sa.Float(), nullable=True, comment='设备利用率(%)'),
    sa.Column('pv_pr_ratio', sa.Float(), nullable=True, comment='光伏PR性能比'),
    sa.Column('rated_power_kw', sa.Float(), nullable=True, comment='额定功率(kW)'),
    sa.Column('last_runtime_hours', sa.Float(), nullable=True, comment='最后运行时长(h)'),
    sa.Column('total_runtime_hours', sa.Float(), nullable=True, comment='累计运行时长(h)'),
    sa.Column('last_maintenance', sa.Date(), nullable=True),
    sa.Column('next_maintenance', sa.Date(), nullable=True),
    sa.Column('maintenance_interval_days', sa.Integer(), nullable=True),
    sa.Column('install_date', sa.Date(), nullable=True),
    sa.Column('warranty_expire_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_devices_code'), 'devices', ['code'], unique=True)
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    op.create_index(op.f('ix_devices_name'), 'devices', ['name'], unique=False)
    op.create_index(op.f('ix_devices_protocol_type'), 'devices', ['protocol_type'], unique=False)
    op.create_index(op.f('ix_devices_sn'), 'devices', ['sn'], unique=True)
    op.create_index(op.f('ix_devices_station_id'), 'devices', ['station_id'], unique=False)
    op.create_index(op.f('ix_devices_type'), 'devices', ['type'], unique=False)
    op.create_table('digital_twin_scenes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('scene_config', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digital_twin_scenes_id'), 'digital_twin_scenes', ['id'], unique=False)
    op.create_index(op.f('ix_digital_twin_scenes_station_id'), 'digital_twin_scenes', ['station_id'], unique=False)
    op.create_table('energy_prices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('slot_id', sa.Integer(), nullable=False, comment='时段ID'),
    sa.Column('price_per_kwh', sa.Numeric(precision=10, scale=4), nullable=False, comment='电价(元/kWh)'),
    sa.Column('effective_date', sa.Date(), nullable=False, comment='生效日期'),
    sa.Column('expire_date', sa.Date(), nullable=True, comment='失效日期'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ep_active', 'energy_prices', ['is_active'], unique=False)
    op.create_index('idx_ep_effective', 'energy_prices', ['effective_date', 'expire_date'], unique=False)
    op.create_index('idx_ep_station_slot', 'energy_prices', ['station_id', 'slot_id'], unique=False)
    op.create_index(op.f('ix_energy_prices_effective_date'), 'energy_prices', ['effective_date'], unique=False)
    op.create_index(op.f('ix_energy_prices_expire_date'), 'energy_prices', ['expire_date'], unique=False)
    op.create_index(op.f('ix_energy_prices_slot_id'), 'energy_prices', ['slot_id'], unique=False)
    op.create_index(op.f('ix_energy_prices_station_id'), 'energy_prices', ['station_id'], unique=False)
    op.create_table('enterprise_recharge_applications',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='申请金额(元)'),
    sa.Column('proof_image', sa.String(length=500), nullable=True, comment='转账证明图片URL'),
    sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='rechargestatus'), nullable=True, comment='状态: pending/approved/rejected'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('applicant', sa.String(length=100), nullable=True, comment='申请人'),
    sa.Column('approver', sa.String(length=100), nullable=True, comment='审批人'),
    sa.Column('reject_reason', sa.String(length=500), nullable=True, comment='拒绝原因'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_era_enterprise', 'enterprise_recharge_applications', ['enterprise_id'], unique=False)
    op.create_index('idx_era_status', 'enterprise_recharge_applications', ['status'], unique=False)
    op.create_table('enterprise_stations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_enterprise_station_unique', 'enterprise_stations', ['enterprise_id', 'station_id'], unique=True)
    op.create_index(op.f('ix_enterprise_stations_enterprise_id'), 'enterprise_stations', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_enterprise_stations_station_id'), 'enterprise_stations', ['station_id'], unique=False)
    op.create_table('enterprise_vehicles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('plate_number', sa.String(length=20), nullable=False, comment='车牌号'),
    sa.Column('vin', sa.String(length=50), nullable=False, comment='VIN码'),
    sa.Column('driver_name', sa.String(length=100), nullable=True, comment='司机姓名'),
    sa.Column('driver_phone', sa.String(length=20), nullable=True, comment='司机电话'),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'MAINTENANCE', 'RETIRED', name='enterprisevehiclestatus'), nullable=True, comment='状态'),
    sa.Column('approval_status', sa.Enum('PENDING', 'CONFIRMED', 'REJECTED', name='approvalstatus'), nullable=False, comment='确认状态'),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True, comment='确认时间'),
    sa.Column('confirmed_by', sa.String(length=100), nullable=True, comment='确认人'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('vin')
    )
    op.create_index('idx_ev_approval', 'enterprise_vehicles', ['enterprise_id', 'approval_status'], unique=False)
    op.create_index('idx_ev_enterprise', 'enterprise_vehicles', ['enterprise_id'], unique=False)
    op.create_index('idx_ev_plate', 'enterprise_vehicles', ['plate_number'], unique=False)
    op.create_index('idx_ev_vin', 'enterprise_vehicles', ['vin'], unique=True)
    op.create_table('fleet_alert_rules',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('rule_type', sa.Enum('LOW_BATTERY', 'ABNORMAL_CHARGING', 'OVERTIME_PARKING', name='alertruletype'), nullable=False, comment='规则类型'),
    sa.Column('threshold', sa.JSON(), nullable=False, comment='阈值配置(JSON), 如 {soc_below:20}'),
    sa.Column('notify_channels', sa.JSON(), nullable=False, comment='通知渠道(JSON), 如 [im, sms]'),
    sa.Column('enable', sa.Boolean(), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_far_enterprise_type', 'fleet_alert_rules', ['enterprise_id', 'rule_type'], unique=False)
    op.create_index(op.f('ix_fleet_alert_rules_enterprise_id'), 'fleet_alert_rules', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_fleet_alert_rules_rule_type'), 'fleet_alert_rules', ['rule_type'], unique=False)
    op.create_table('fleet_carbon_certificates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('summary_id', sa.Integer(), nullable=False, comment='关联碳减排月度汇总ID'),
    sa.Column('certificate_no', sa.String(length=64), nullable=False, comment='核证编号'),
    sa.Column('verified_at', sa.DateTime(), nullable=True, comment='核证时间'),
    sa.Column('trade_volume', sa.Numeric(precision=14, scale=2), nullable=False, comment='交易量(吨CO2)'),
    sa.Column('trade_price', sa.Numeric(precision=12, scale=2), nullable=False, comment='交易单价(元/吨)'),
    sa.Column('status', sa.Enum('PENDING', 'VERIFIED', 'TRADED', 'CANCELLED', name='certificatestatus'), nullable=False, comment='核证状态'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fcc_enterprise_status', 'fleet_carbon_certificates', ['enterprise_id', 'status'], unique=False)
    op.create_index('idx_fcc_summary', 'fleet_carbon_certificates', ['summary_id'], unique=False)
    op.create_index(op.f('ix_fleet_carbon_certificates_certificate_no'), 'fleet_carbon_certificates', ['certificate_no'], unique=True)
    op.create_index(op.f('ix_fleet_carbon_certificates_enterprise_id'), 'fleet_carbon_certificates', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_fleet_carbon_certificates_status'), 'fleet_carbon_certificates', ['status'], unique=False)
    op.create_index(op.f('ix_fleet_carbon_certificates_summary_id'), 'fleet_carbon_certificates', ['summary_id'], unique=False)
    op.create_table('fleet_charging_policies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('daily_kwh_limit', sa.Float(), nullable=False, comment='企业日充电限额(kWh), 0表示不限'),
    sa.Column('allowed_time_slots', sa.JSON(), nullable=True, comment='允许时段列表, 如 ["谷","平"]; 空表示不限'),
    sa.Column('allowed_station_ids', sa.JSON(), nullable=True, comment='允许站点ID列表; 空表示不限'),
    sa.Column('enable', sa.Boolean(), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fcp_enable', 'fleet_charging_policies', ['enable'], unique=False)
    op.create_index('idx_fcp_enterprise', 'fleet_charging_policies', ['enterprise_id'], unique=False)
    op.create_table('fleet_settlement_bills',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('bill_no', sa.String(length=64), nullable=False, comment='账单编号'),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('bill_period', sa.String(length=20), nullable=False, comment='账期 YYYY-MM'),
    sa.Column('total_orders', sa.Integer(), nullable=True, comment='订单数'),
    sa.Column('total_energy_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='总电量(kWh)'),
    sa.Column('total_charge_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总电费(元)'),
    sa.Column('total_service_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总服务费(元)'),
    sa.Column('total_parking_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='总停车费(元)'),
    sa.Column('total_discount', sa.Numeric(precision=12, scale=2), nullable=True, comment='总优惠(元)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='应付总额(元)'),
    sa.Column('paid_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='已付金额(元)'),
    sa.Column('balance_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='待结余额(元)'),
    sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', 'PAID', name='billstatus'), nullable=True, comment='账单状态'),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True, comment='确认时间'),
    sa.Column('paid_at', sa.DateTime(), nullable=True, comment='付款时间'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('enterprise_id', 'bill_period', name='uq_bill_enterprise_period')
    )
    op.create_index('idx_fsb_enterprise', 'fleet_settlement_bills', ['enterprise_id'], unique=False)
    op.create_index('idx_fsb_period', 'fleet_settlement_bills', ['bill_period'], unique=False)
    op.create_index('idx_fsb_status', 'fleet_settlement_bills', ['status'], unique=False)
    op.create_index(op.f('ix_fleet_settlement_bills_bill_no'), 'fleet_settlement_bills', ['bill_no'], unique=True)
    op.create_table('gateway_api_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key_id', sa.String(length=32), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('api_key', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('api_key')
    )
    op.create_index(op.f('ix_gateway_api_keys_key_id'), 'gateway_api_keys', ['key_id'], unique=True)
    op.create_table('inspection_tasks',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False, comment='任务名称'),
    sa.Column('plan_id', sa.Integer(), nullable=True, comment='关联计划ID'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='关联站点ID'),
    sa.Column('station_name', sa.String(length=200), nullable=True, comment='站点名称'),
    sa.Column('assignee', sa.String(length=100), nullable=True, comment='负责人'),
    sa.Column('assignee_id', sa.Integer(), nullable=True, comment='负责人用户ID'),
    sa.Column('status', sa.Enum('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='taskstatus'), nullable=True, comment='任务状态'),
    sa.Column('total_items', sa.Integer(), nullable=True, comment='检查项总数'),
    sa.Column('completed_items', sa.Integer(), nullable=True, comment='已完成项数'),
    sa.Column('scheduled_date', sa.Date(), nullable=True, comment='计划执行日期'),
    sa.Column('actual_date', sa.Date(), nullable=True, comment='实际执行日期'),
    sa.Column('description', sa.Text(), nullable=True, comment='任务描述'),
    sa.Column('result', sa.JSON(), nullable=True, comment='检查结果（JSON）'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspection_tasks_id'), 'inspection_tasks', ['id'], unique=False)
    op.create_table('oauth_authorization_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('redirect_uri', sa.String(length=500), nullable=True),
    sa.Column('scopes', sa.String(length=500), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_oauth_authorization_codes_id'), 'oauth_authorization_codes', ['id'], unique=False)
    op.create_table('occupancy_fee_prices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('grace_minutes', sa.Integer(), nullable=True, comment='免罚时长(分钟)'),
    sa.Column('rate_per_minute', sa.Numeric(precision=10, scale=2), nullable=False, comment='罚金费率(元/分钟)'),
    sa.Column('max_fee', sa.Numeric(precision=10, scale=2), nullable=True, comment='单次封顶金额'),
    sa.Column('effective_date', sa.Date(), nullable=False, comment='生效日期'),
    sa.Column('expire_date', sa.Date(), nullable=True, comment='失效日期'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ofp_active', 'occupancy_fee_prices', ['is_active'], unique=False)
    op.create_index('idx_ofp_effective', 'occupancy_fee_prices', ['effective_date', 'expire_date'], unique=False)
    op.create_index('idx_ofp_station', 'occupancy_fee_prices', ['station_id'], unique=False)
    op.create_index(op.f('ix_occupancy_fee_prices_effective_date'), 'occupancy_fee_prices', ['effective_date'], unique=False)
    op.create_index(op.f('ix_occupancy_fee_prices_expire_date'), 'occupancy_fee_prices', ['expire_date'], unique=False)
    op.create_index(op.f('ix_occupancy_fee_prices_station_id'), 'occupancy_fee_prices', ['station_id'], unique=False)
    op.create_table('on_call_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False, comment='规则名称 (如: 一线工程师轮值)'),
    sa.Column('team_id', sa.Integer(), nullable=False, comment='所属团队'),
    sa.Column('station_id', sa.Integer(), nullable=True, comment='适用站点 (NULL=全局)'),
    sa.Column('schedule_type', sa.String(length=32), nullable=True, comment='轮换类型: daily|weekly|monthly|custom'),
    sa.Column('rotation_order', sa.JSON(), nullable=False, comment='轮换顺序 (用户ID列表)'),
    sa.Column('shift_duration_hours', sa.Integer(), nullable=True, comment='每班时长(小时), 默认168=1周'),
    sa.Column('overlap_minutes', sa.Integer(), nullable=True, comment='交接班重叠分钟数'),
    sa.Column('escalation_level', sa.Integer(), nullable=True, comment='升级级别数'),
    sa.Column('escalation_timeout_minutes', sa.Integer(), nullable=True, comment='升级超时(分钟)'),
    sa.Column('notify_methods', sa.JSON(), nullable=True, comment='通知方式列表'),
    sa.Column('auto_assign_workorders', sa.Boolean(), nullable=True, comment='自动将告警工单分配给当班人'),
    sa.Column('enabled', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_on_call_rules_id'), 'on_call_rules', ['id'], unique=False)
    op.create_table('parking_prices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('free_minutes', sa.Integer(), nullable=True, comment='免费时长(分钟)'),
    sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=False, comment='小时费率(元/小时)'),
    sa.Column('daily_cap', sa.Numeric(precision=10, scale=2), nullable=True, comment='日封顶金额'),
    sa.Column('enable_night_rate', sa.Boolean(), nullable=True, comment='是否启用夜间费率'),
    sa.Column('night_rate', sa.Numeric(precision=10, scale=2), nullable=True, comment='夜间费率(元/小时)'),
    sa.Column('night_start', sa.Time(), nullable=True, comment='夜间开始时间'),
    sa.Column('night_end', sa.Time(), nullable=True, comment='夜间结束时间'),
    sa.Column('effective_date', sa.Date(), nullable=False, comment='生效日期'),
    sa.Column('expire_date', sa.Date(), nullable=True, comment='失效日期'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pp_active', 'parking_prices', ['is_active'], unique=False)
    op.create_index('idx_pp_effective', 'parking_prices', ['effective_date', 'expire_date'], unique=False)
    op.create_index('idx_pp_station', 'parking_prices', ['station_id'], unique=False)
    op.create_index(op.f('ix_parking_prices_effective_date'), 'parking_prices', ['effective_date'], unique=False)
    op.create_index(op.f('ix_parking_prices_expire_date'), 'parking_prices', ['expire_date'], unique=False)
    op.create_index(op.f('ix_parking_prices_station_id'), 'parking_prices', ['station_id'], unique=False)
    op.create_table('rate_limit_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('endpoint_pattern', sa.String(length=500), nullable=True),
    sa.Column('method', sa.String(length=10), nullable=True),
    sa.Column('limit_per_minute', sa.Integer(), nullable=True),
    sa.Column('limit_per_hour', sa.Integer(), nullable=True),
    sa.Column('limit_per_day', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rate_limit_rules_id'), 'rate_limit_rules', ['id'], unique=False)
    op.create_table('reservation_fee_prices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('deposit_amount', sa.Numeric(precision=10, scale=2), nullable=False, comment='预约冻结金额'),
    sa.Column('reservation_policy', sa.Enum('SLOT_BASED', 'FLAT', name='reservationpolicy'), nullable=False, comment='预约策略: slot_based/flat'),
    sa.Column('fee_amount', sa.Numeric(precision=10, scale=2), nullable=False, comment='预约费金额'),
    sa.Column('no_show_penalty', sa.Numeric(precision=10, scale=2), nullable=False, comment='爽约罚款金额'),
    sa.Column('effective_date', sa.Date(), nullable=False, comment='生效日期'),
    sa.Column('expire_date', sa.Date(), nullable=True, comment='失效日期'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_rfp_active', 'reservation_fee_prices', ['is_active'], unique=False)
    op.create_index('idx_rfp_effective', 'reservation_fee_prices', ['effective_date', 'expire_date'], unique=False)
    op.create_index('idx_rfp_station', 'reservation_fee_prices', ['station_id'], unique=False)
    op.create_index(op.f('ix_reservation_fee_prices_effective_date'), 'reservation_fee_prices', ['effective_date'], unique=False)
    op.create_index(op.f('ix_reservation_fee_prices_expire_date'), 'reservation_fee_prices', ['expire_date'], unique=False)
    op.create_index(op.f('ix_reservation_fee_prices_station_id'), 'reservation_fee_prices', ['station_id'], unique=False)
    op.create_table('service_fee_prices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='站点ID'),
    sa.Column('user_type', sa.Enum('APP', 'CARD', 'VIN', 'INTERCONNECT', 'ENTERPRISE', name='usertype'), nullable=False, comment='用户类型'),
    sa.Column('fee_type', sa.Enum('FIXED', 'PERCENT', name='feetype'), nullable=False, comment='费用类型: fixed/percent'),
    sa.Column('fee_value', sa.Numeric(precision=10, scale=4), nullable=False, comment='费用值: 固定金额(元/次) 或 费率(元/kWh)'),
    sa.Column('effective_date', sa.Date(), nullable=False, comment='生效日期'),
    sa.Column('expire_date', sa.Date(), nullable=True, comment='失效日期'),
    sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sfp_active', 'service_fee_prices', ['is_active'], unique=False)
    op.create_index('idx_sfp_effective', 'service_fee_prices', ['effective_date', 'expire_date'], unique=False)
    op.create_index('idx_sfp_station_user', 'service_fee_prices', ['station_id', 'user_type'], unique=False)
    op.create_index(op.f('ix_service_fee_prices_effective_date'), 'service_fee_prices', ['effective_date'], unique=False)
    op.create_index(op.f('ix_service_fee_prices_expire_date'), 'service_fee_prices', ['expire_date'], unique=False)
    op.create_index(op.f('ix_service_fee_prices_station_id'), 'service_fee_prices', ['station_id'], unique=False)
    op.create_index(op.f('ix_service_fee_prices_user_type'), 'service_fee_prices', ['user_type'], unique=False)
    op.create_table('station_hourly_stats',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=False),
    sa.Column('hour', sa.DateTime(timezone=True), nullable=False),
    sa.Column('region_id', sa.String(length=32), nullable=False),
    sa.Column('pod_id', sa.String(length=32), nullable=False),
    sa.Column('avg_total_power', sa.Float(), nullable=True),
    sa.Column('max_total_power', sa.Float(), nullable=True),
    sa.Column('min_total_power', sa.Float(), nullable=True),
    sa.Column('avg_pv_power', sa.Float(), nullable=True),
    sa.Column('max_pv_power', sa.Float(), nullable=True),
    sa.Column('pv_generation_kwh', sa.Float(), nullable=True),
    sa.Column('avg_battery_soc', sa.Float(), nullable=True),
    sa.Column('avg_battery_power', sa.Float(), nullable=True),
    sa.Column('charge_kwh', sa.Float(), nullable=True),
    sa.Column('discharge_kwh', sa.Float(), nullable=True),
    sa.Column('avg_charger_power', sa.Float(), nullable=True),
    sa.Column('max_charger_power', sa.Float(), nullable=True),
    sa.Column('charger_kwh', sa.Float(), nullable=True),
    sa.Column('charging_sessions', sa.Integer(), nullable=True),
    sa.Column('avg_temperature', sa.Float(), nullable=True),
    sa.Column('max_temperature', sa.Float(), nullable=True),
    sa.Column('device_count', sa.Integer(), nullable=True),
    sa.Column('online_devices', sa.Integer(), nullable=True),
    sa.Column('fault_devices', sa.Integer(), nullable=True),
    sa.Column('data_points', sa.Integer(), nullable=True),
    sa.Column('uptime_minutes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_station_hourly_region', 'station_hourly_stats', ['region_id', 'hour'], unique=False)
    op.create_index('idx_station_hourly_station_time', 'station_hourly_stats', ['station_id', 'hour'], unique=False)
    op.create_index(op.f('ix_station_hourly_stats_pod_id'), 'station_hourly_stats', ['pod_id'], unique=False)
    op.create_index(op.f('ix_station_hourly_stats_region_id'), 'station_hourly_stats', ['region_id'], unique=False)
    op.create_index(op.f('ix_station_hourly_stats_station_id'), 'station_hourly_stats', ['station_id'], unique=False)
    op.create_table('station_vin_whitelist',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False, comment='场站ID'),
    sa.Column('vin', sa.String(length=50), nullable=False, comment='VIN码'),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('source', sa.String(length=50), nullable=False, comment='来源: vehicle_confirm/manual/auto'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_svw_enterprise', 'station_vin_whitelist', ['enterprise_id'], unique=False)
    op.create_index('idx_svw_station_vin', 'station_vin_whitelist', ['station_id', 'vin'], unique=True)
    op.create_index('idx_svw_vin', 'station_vin_whitelist', ['vin'], unique=False)
    op.create_table('analytics_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('analysis_type', sa.String(length=50), nullable=True),
    sa.Column('result_json', sa.JSON(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analytics_results_analysis_type'), 'analytics_results', ['analysis_type'], unique=False)
    op.create_index(op.f('ix_analytics_results_device_id'), 'analytics_results', ['device_id'], unique=False)
    op.create_index(op.f('ix_analytics_results_generated_at'), 'analytics_results', ['generated_at'], unique=False)
    op.create_index(op.f('ix_analytics_results_id'), 'analytics_results', ['id'], unique=False)
    op.create_table('api_request_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('api_key_id', sa.Integer(), nullable=True),
    sa.Column('endpoint', sa.String(length=500), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('request_time', sa.DateTime(), nullable=True),
    sa.Column('response_time', sa.Float(), nullable=True),
    sa.Column('response_status', sa.Integer(), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('client_ip', sa.String(length=45), nullable=True),
    sa.Column('query_params', sa.Text(), nullable=True),
    sa.Column('request_body', sa.Text(), nullable=True),
    sa.Column('response_body', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_request_logs_id'), 'api_request_logs', ['id'], unique=False)
    op.create_index(op.f('ix_api_request_logs_request_id'), 'api_request_logs', ['request_id'], unique=True)
    op.create_index(op.f('ix_api_request_logs_request_time'), 'api_request_logs', ['request_time'], unique=False)
    op.create_table('client_certificates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cert_serial', sa.String(length=64), nullable=False, comment='证书序列号'),
    sa.Column('cert_fingerprint', sa.String(length=64), nullable=False, comment='证书指纹'),
    sa.Column('cert_subject', sa.Text(), nullable=False, comment='证书主题'),
    sa.Column('cert_issuer', sa.Text(), nullable=False, comment='证书颁发者'),
    sa.Column('cert_pem', sa.Text(), nullable=False, comment='证书PEM'),
    sa.Column('tenant_id', sa.Integer(), nullable=True),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('is_revoked', sa.Boolean(), nullable=True),
    sa.Column('revoked_reason', sa.Text(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('valid_from', sa.DateTime(), nullable=False),
    sa.Column('valid_until', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cert_fingerprint')
    )
    op.create_index('idx_client_cert_active', 'client_certificates', ['is_active', 'is_revoked'], unique=False)
    op.create_index('idx_client_cert_device', 'client_certificates', ['device_id'], unique=False)
    op.create_index('idx_client_cert_tenant', 'client_certificates', ['tenant_id'], unique=False)
    op.create_index('idx_client_cert_valid', 'client_certificates', ['valid_until'], unique=False)
    op.create_index(op.f('ix_client_certificates_cert_serial'), 'client_certificates', ['cert_serial'], unique=True)
    op.create_index(op.f('ix_client_certificates_device_id'), 'client_certificates', ['device_id'], unique=False)
    op.create_index(op.f('ix_client_certificates_id'), 'client_certificates', ['id'], unique=False)
    op.create_index(op.f('ix_client_certificates_tenant_id'), 'client_certificates', ['tenant_id'], unique=False)
    op.create_table('device_configs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('voltage_limit', sa.Float(), nullable=True),
    sa.Column('current_limit', sa.Float(), nullable=True),
    sa.Column('max_power', sa.Float(), nullable=True),
    sa.Column('charge_mode', sa.Enum('FAST', 'SMART', 'ECO', name='chargemode'), nullable=True),
    sa.Column('overload_protection', sa.Boolean(), nullable=True),
    sa.Column('time_periods', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_configs_device_id'), 'device_configs', ['device_id'], unique=True)
    op.create_index(op.f('ix_device_configs_id'), 'device_configs', ['id'], unique=False)
    op.create_table('device_control_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('device_name', sa.String(length=200), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('parameter', sa.String(length=200), nullable=True),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('params', sa.JSON(), nullable=True),
    sa.Column('result', sa.String(length=50), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('operator', sa.String(length=100), nullable=True),
    sa.Column('operator_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_control_logs_action'), 'device_control_logs', ['action'], unique=False)
    op.create_index(op.f('ix_device_control_logs_created_at'), 'device_control_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_device_control_logs_device_id'), 'device_control_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_control_logs_id'), 'device_control_logs', ['id'], unique=False)
    op.create_table('device_daily_stats',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('region_id', sa.String(length=32), nullable=False),
    sa.Column('pod_id', sa.String(length=32), nullable=False),
    sa.Column('device_type', sa.String(length=50), nullable=True),
    sa.Column('avg_power', sa.Float(), nullable=True),
    sa.Column('max_power', sa.Float(), nullable=True),
    sa.Column('min_power', sa.Float(), nullable=True),
    sa.Column('avg_pv_power', sa.Float(), nullable=True),
    sa.Column('pv_generation_kwh', sa.Float(), nullable=True),
    sa.Column('peak_sun_hours', sa.Float(), nullable=True),
    sa.Column('avg_soc', sa.Float(), nullable=True),
    sa.Column('avg_soh', sa.Float(), nullable=True),
    sa.Column('charge_kwh', sa.Float(), nullable=True),
    sa.Column('discharge_kwh', sa.Float(), nullable=True),
    sa.Column('cycle_count', sa.Integer(), nullable=True),
    sa.Column('avg_charger_power', sa.Float(), nullable=True),
    sa.Column('charger_kwh', sa.Float(), nullable=True),
    sa.Column('charging_sessions', sa.Integer(), nullable=True),
    sa.Column('avg_session_duration', sa.Float(), nullable=True),
    sa.Column('avg_internal_temp', sa.Float(), nullable=True),
    sa.Column('max_internal_temp', sa.Float(), nullable=True),
    sa.Column('avg_ambient_temp', sa.Float(), nullable=True),
    sa.Column('total_generation', sa.Float(), nullable=True),
    sa.Column('total_consumption', sa.Float(), nullable=True),
    sa.Column('uptime_minutes', sa.Integer(), nullable=True),
    sa.Column('downtime_minutes', sa.Integer(), nullable=True),
    sa.Column('data_points', sa.Integer(), nullable=True),
    sa.Column('avg_data_interval_seconds', sa.Float(), nullable=True),
    sa.Column('avg_health_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_device_daily_device_date', 'device_daily_stats', ['device_id', 'date'], unique=False)
    op.create_index('idx_device_daily_region', 'device_daily_stats', ['region_id', 'date'], unique=False)
    op.create_index('idx_device_daily_station_date', 'device_daily_stats', ['station_id', 'date'], unique=False)
    op.create_index('idx_device_daily_type', 'device_daily_stats', ['device_type', 'date'], unique=False)
    op.create_index(op.f('ix_device_daily_stats_device_id'), 'device_daily_stats', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_daily_stats_device_type'), 'device_daily_stats', ['device_type'], unique=False)
    op.create_index(op.f('ix_device_daily_stats_pod_id'), 'device_daily_stats', ['pod_id'], unique=False)
    op.create_index(op.f('ix_device_daily_stats_region_id'), 'device_daily_stats', ['region_id'], unique=False)
    op.create_index(op.f('ix_device_daily_stats_station_id'), 'device_daily_stats', ['station_id'], unique=False)
    op.create_table('device_efficiency_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=True),
    sa.Column('utilization', sa.Float(), nullable=True, comment='设备利用率(%)'),
    sa.Column('charge_efficiency', sa.Float(), nullable=True, comment='充电效率(%)'),
    sa.Column('generation_efficiency', sa.Float(), nullable=True, comment='发电效率(%)'),
    sa.Column('pv_pr', sa.Float(), nullable=True, comment='光伏PR性能比'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='原始遥测数据快照'),
    sa.Column('metric_type', sa.String(length=50), nullable=True, comment='指标类型: utilization/charge/generation'),
    sa.Column('metric_name', sa.String(length=100), nullable=True, comment='指标名称'),
    sa.Column('metric_value', sa.Float(), nullable=True, comment='指标值'),
    sa.Column('unit', sa.String(length=20), nullable=True, comment='单位'),
    sa.Column('threshold_warn', sa.Float(), nullable=True, comment='告警阈值'),
    sa.Column('threshold_critical', sa.Float(), nullable=True, comment='严重阈值'),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True, comment='记录时间'),
    sa.Column('log_date', sa.String(length=10), nullable=False, comment='日志日期 YYYY-MM-DD'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_efficiency_logs_device_id'), 'device_efficiency_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_efficiency_logs_id'), 'device_efficiency_logs', ['id'], unique=False)
    op.create_index(op.f('ix_device_efficiency_logs_log_date'), 'device_efficiency_logs', ['log_date'], unique=False)
    op.create_index(op.f('ix_device_efficiency_logs_metric_type'), 'device_efficiency_logs', ['metric_type'], unique=False)
    op.create_index(op.f('ix_device_efficiency_logs_recorded_at'), 'device_efficiency_logs', ['recorded_at'], unique=False)
    op.create_index(op.f('ix_device_efficiency_logs_station_id'), 'device_efficiency_logs', ['station_id'], unique=False)
    op.create_table('device_health_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('health_score', sa.Float(), nullable=False),
    sa.Column('risk_level', sa.String(length=20), nullable=False),
    sa.Column('component_scores', sa.JSON(), nullable=True),
    sa.Column('maintenance_recommendations', sa.JSON(), nullable=True),
    sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_health_history_calculated_at'), 'device_health_history', ['calculated_at'], unique=False)
    op.create_index(op.f('ix_device_health_history_device_id'), 'device_health_history', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_health_history_id'), 'device_health_history', ['id'], unique=False)
    op.create_table('device_health_records',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('electrical_safe_score', sa.Integer(), nullable=True),
    sa.Column('thermal_score', sa.Integer(), nullable=True),
    sa.Column('comm_score', sa.Integer(), nullable=True),
    sa.Column('power_quality_score', sa.Integer(), nullable=True),
    sa.Column('mechanical_score', sa.Integer(), nullable=True),
    sa.Column('total_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_health_records_device_id'), 'device_health_records', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_health_records_id'), 'device_health_records', ['id'], unique=False)
    op.create_table('device_qrcodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('qr_code', sa.String(length=200), nullable=False),
    sa.Column('qr_image_path', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('print_count', sa.Integer(), nullable=True),
    sa.Column('last_print_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('scan_count', sa.Integer(), nullable=True),
    sa.Column('last_scan_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_qrcodes_device_id'), 'device_qrcodes', ['device_id'], unique=True)
    op.create_index(op.f('ix_device_qrcodes_id'), 'device_qrcodes', ['id'], unique=False)
    op.create_index(op.f('ix_device_qrcodes_qr_code'), 'device_qrcodes', ['qr_code'], unique=True)
    op.create_table('digital_twin_data_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('param_key', sa.String(length=100), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=True),
    sa.Column('visual_type', sa.String(length=30), nullable=True),
    sa.Column('normal_range', sa.JSON(), nullable=True),
    sa.Column('warn_range', sa.JSON(), nullable=True),
    sa.Column('danger_range', sa.JSON(), nullable=True),
    sa.Column('normal_color', sa.String(length=20), nullable=True),
    sa.Column('warn_color', sa.String(length=20), nullable=True),
    sa.Column('danger_color', sa.String(length=20), nullable=True),
    sa.Column('animation_config', sa.JSON(), nullable=True),
    sa.Column('show_value', sa.Boolean(), nullable=True),
    sa.Column('show_unit', sa.Boolean(), nullable=True),
    sa.Column('decimal_places', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digital_twin_data_points_device_id'), 'digital_twin_data_points', ['device_id'], unique=False)
    op.create_index(op.f('ix_digital_twin_data_points_id'), 'digital_twin_data_points', ['id'], unique=False)
    op.create_table('digital_twin_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('model_type', sa.Enum('SOLAR_INVERTER', 'BATTERY_INVERTER', 'PCS', 'BATTERY_RACK', 'CHARGER_DC', 'CHARGER_AC', 'GATEWAY', 'METER', 'TRANSFORMER', 'PANEL', name='threedmodeltype'), nullable=False),
    sa.Column('scale_x', sa.Float(), nullable=True),
    sa.Column('scale_y', sa.Float(), nullable=True),
    sa.Column('scale_z', sa.Float(), nullable=True),
    sa.Column('position_x', sa.Float(), nullable=True),
    sa.Column('position_y', sa.Float(), nullable=True),
    sa.Column('position_z', sa.Float(), nullable=True),
    sa.Column('rotation_x', sa.Float(), nullable=True),
    sa.Column('rotation_y', sa.Float(), nullable=True),
    sa.Column('rotation_z', sa.Float(), nullable=True),
    sa.Column('color_primary', sa.String(length=20), nullable=True),
    sa.Column('color_secondary', sa.String(length=20), nullable=True),
    sa.Column('color_accent', sa.String(length=20), nullable=True),
    sa.Column('animations', sa.JSON(), nullable=True),
    sa.Column('status_mapping', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digital_twin_models_device_id'), 'digital_twin_models', ['device_id'], unique=True)
    op.create_index(op.f('ix_digital_twin_models_id'), 'digital_twin_models', ['id'], unique=False)
    op.create_index(op.f('ix_digital_twin_models_model_type'), 'digital_twin_models', ['model_type'], unique=False)
    op.create_table('enterprise_transactions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=True, comment='关联车辆ID(可为空)'),
    sa.Column('type', sa.Enum('RECHARGE', 'CONSUME', 'REFUND', name='transactiontype'), nullable=False, comment='交易类型: recharge/consume/refund'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='交易金额(元)'),
    sa.Column('balance_after', sa.Numeric(precision=12, scale=2), nullable=False, comment='交易后余额(元)'),
    sa.Column('order_id', sa.String(length=64), nullable=True, comment='关联订单号'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_et_created', 'enterprise_transactions', ['created_at'], unique=False)
    op.create_index('idx_et_enterprise', 'enterprise_transactions', ['enterprise_id'], unique=False)
    op.create_index('idx_et_order', 'enterprise_transactions', ['order_id'], unique=False)
    op.create_index('idx_et_type', 'enterprise_transactions', ['type'], unique=False)
    op.create_table('fleet_alert_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False, comment='规则ID'),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=True, comment='车辆ID'),
    sa.Column('plate_number', sa.String(length=20), nullable=True, comment='车牌号'),
    sa.Column('triggered_at', sa.DateTime(), nullable=False, comment='触发时间'),
    sa.Column('alert_value', sa.String(length=100), nullable=True, comment='触发取值描述, 如 soc=15.0%'),
    sa.Column('notified', sa.Boolean(), nullable=True, comment='是否已通知'),
    sa.Column('status', sa.Enum('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED', name='alertrecordstatus'), nullable=True, comment='处理状态'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_farec_enterprise_status', 'fleet_alert_records', ['enterprise_id', 'status'], unique=False)
    op.create_index('idx_farec_rule_vehicle_status', 'fleet_alert_records', ['rule_id', 'vehicle_id', 'status'], unique=False)
    op.create_index(op.f('ix_fleet_alert_records_enterprise_id'), 'fleet_alert_records', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_fleet_alert_records_rule_id'), 'fleet_alert_records', ['rule_id'], unique=False)
    op.create_index(op.f('ix_fleet_alert_records_status'), 'fleet_alert_records', ['status'], unique=False)
    op.create_index(op.f('ix_fleet_alert_records_triggered_at'), 'fleet_alert_records', ['triggered_at'], unique=False)
    op.create_index(op.f('ix_fleet_alert_records_vehicle_id'), 'fleet_alert_records', ['vehicle_id'], unique=False)
    op.create_table('fleet_drivers',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='所属企业ID'),
    sa.Column('name', sa.String(length=100), nullable=False, comment='司机姓名'),
    sa.Column('phone', sa.String(length=20), nullable=False, comment='手机号'),
    sa.Column('license_no', sa.String(length=50), nullable=False, comment='驾驶证号'),
    sa.Column('license_type', sa.Enum('A1', 'A2', 'B1', 'B2', 'C1', 'C2', name='licensetype'), nullable=False, comment='准驾车型'),
    sa.Column('assigned_vehicle_id', sa.Integer(), nullable=True, comment='分配车辆ID'),
    sa.Column('hire_date', sa.DateTime(), nullable=True, comment='入职日期'),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'SUSPENDED', 'TERMINATED', name='driverstatus'), nullable=True, comment='状态'),
    sa.Column('total_charge_kwh', sa.Numeric(precision=12, scale=2), nullable=True, comment='累计充电量(kWh)'),
    sa.Column('total_spent', sa.Numeric(precision=12, scale=2), nullable=True, comment='累计消费(元)'),
    sa.Column('rating', sa.Numeric(precision=3, scale=1), nullable=True, comment='评分(1-5)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fd_enterprise', 'fleet_drivers', ['enterprise_id'], unique=False)
    op.create_index('idx_fd_license', 'fleet_drivers', ['license_no'], unique=False)
    op.create_index('idx_fd_phone', 'fleet_drivers', ['phone'], unique=False)
    op.create_index('idx_fd_status', 'fleet_drivers', ['status'], unique=False)
    op.create_table('fleet_invoice_requests',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('bill_id', sa.Integer(), nullable=True, comment='关联账单ID'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='开票金额(元)'),
    sa.Column('invoice_type', sa.Enum('GENERAL', 'SPECIAL', name='invoicetype'), nullable=True, comment='发票类型'),
    sa.Column('title', sa.String(length=200), nullable=False, comment='发票抬头'),
    sa.Column('tax_no', sa.String(length=50), nullable=True, comment='税号'),
    sa.Column('email', sa.String(length=100), nullable=True, comment='接收邮箱'),
    sa.Column('status', sa.Enum('PENDING', 'ISSUED', 'REJECTED', name='invoicestatus'), nullable=True, comment='状态'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fir_bill', 'fleet_invoice_requests', ['bill_id'], unique=False)
    op.create_index('idx_fir_enterprise', 'fleet_invoice_requests', ['enterprise_id'], unique=False)
    op.create_index('idx_fir_status', 'fleet_invoice_requests', ['status'], unique=False)
    op.create_table('fleet_settlement_details',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('bill_id', sa.Integer(), nullable=False, comment='所属账单ID'),
    sa.Column('order_id', sa.Integer(), nullable=False, comment='充电订单ID'),
    sa.Column('order_no', sa.String(length=64), nullable=True, comment='订单编号'),
    sa.Column('vehicle_id', sa.Integer(), nullable=True, comment='车辆ID'),
    sa.Column('plate_number', sa.String(length=20), nullable=True, comment='车牌号'),
    sa.Column('driver_id', sa.Integer(), nullable=True, comment='司机ID'),
    sa.Column('charging_time', sa.DateTime(), nullable=True, comment='充电时间'),
    sa.Column('energy_kwh', sa.Numeric(precision=10, scale=2), nullable=True, comment='充电量(kWh)'),
    sa.Column('charge_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='电费(元)'),
    sa.Column('service_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='服务费(元)'),
    sa.Column('parking_fee', sa.Numeric(precision=12, scale=2), nullable=True, comment='停车费(元)'),
    sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='优惠金额(元)'),
    sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='订单总额(元)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fsd_bill', 'fleet_settlement_details', ['bill_id'], unique=False)
    op.create_index('idx_fsd_order', 'fleet_settlement_details', ['order_id'], unique=False)
    op.create_index('idx_fsd_vehicle', 'fleet_settlement_details', ['vehicle_id'], unique=False)
    op.create_table('fleet_v2g_plans',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('plan_date', sa.Date(), nullable=False, comment='计划日期'),
    sa.Column('planned_charge_start', sa.DateTime(), nullable=True, comment='计划充电开始时间'),
    sa.Column('planned_charge_end', sa.DateTime(), nullable=True, comment='计划充电结束时间'),
    sa.Column('planned_discharge_start', sa.DateTime(), nullable=True, comment='计划放电开始时间'),
    sa.Column('planned_discharge_end', sa.DateTime(), nullable=True, comment='计划放电结束时间'),
    sa.Column('target_soc_min', sa.Float(), nullable=False, comment='目标最小SOC(%)'),
    sa.Column('target_soc_max', sa.Float(), nullable=False, comment='目标最大SOC(%)'),
    sa.Column('status', sa.Enum('SCHEDULED', 'CHARGING', 'DISCHARGING', 'COMPLETED', 'CANCELLED', 'FAILED', name='v2gplanstatus'), nullable=True, comment='计划状态'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fv2gp_enterprise_date', 'fleet_v2g_plans', ['enterprise_id', 'plan_date'], unique=False)
    op.create_index('idx_fv2gp_status_date', 'fleet_v2g_plans', ['status', 'plan_date'], unique=False)
    op.create_index('idx_fv2gp_vehicle_date', 'fleet_v2g_plans', ['vehicle_id', 'plan_date'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_plans_enterprise_id'), 'fleet_v2g_plans', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_plans_plan_date'), 'fleet_v2g_plans', ['plan_date'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_plans_status'), 'fleet_v2g_plans', ['status'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_plans_vehicle_id'), 'fleet_v2g_plans', ['vehicle_id'], unique=False)
    op.create_table('fleet_v2g_revenue',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('enterprise_id', sa.Integer(), nullable=False, comment='企业ID'),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('record_date', sa.Date(), nullable=False, comment='记录日期'),
    sa.Column('discharge_energy_kwh', sa.Numeric(precision=10, scale=2), nullable=True, comment='放电电量(kWh)'),
    sa.Column('discharge_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='放电收益(元)'),
    sa.Column('grid_response_count', sa.Integer(), nullable=True, comment='电网响应次数'),
    sa.Column('peak_shaving_kwh', sa.Numeric(precision=10, scale=2), nullable=True, comment='削峰电量(kWh)'),
    sa.Column('valley_filling_kwh', sa.Numeric(precision=10, scale=2), nullable=True, comment='填谷电量(kWh)'),
    sa.Column('total_revenue', sa.Numeric(precision=12, scale=2), nullable=True, comment='总收益(元)'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fv2gr_enterprise_date', 'fleet_v2g_revenue', ['enterprise_id', 'record_date'], unique=False)
    op.create_index('idx_fv2gr_enterprise_vehicle_date', 'fleet_v2g_revenue', ['enterprise_id', 'vehicle_id', 'record_date'], unique=True)
    op.create_index('idx_fv2gr_vehicle_date', 'fleet_v2g_revenue', ['vehicle_id', 'record_date'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_revenue_enterprise_id'), 'fleet_v2g_revenue', ['enterprise_id'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_revenue_record_date'), 'fleet_v2g_revenue', ['record_date'], unique=False)
    op.create_index(op.f('ix_fleet_v2g_revenue_vehicle_id'), 'fleet_v2g_revenue', ['vehicle_id'], unique=False)
    op.create_table('fleet_vehicle_insurances',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('insurance_type', sa.Enum('COMPULSORY', 'COMMERCIAL', 'THIRD_PARTY', name='vehicleinsurancetype'), nullable=False, comment='保险类型: compulsory/commercial/third_party'),
    sa.Column('company', sa.String(length=100), nullable=False, comment='保险公司'),
    sa.Column('policy_no', sa.String(length=100), nullable=False, comment='保单号'),
    sa.Column('start_date', sa.DateTime(), nullable=False, comment='起保日期'),
    sa.Column('end_date', sa.DateTime(), nullable=False, comment='到期日期'),
    sa.Column('premium', sa.Numeric(precision=12, scale=2), nullable=True, comment='保费(元)'),
    sa.Column('attachment_url', sa.String(length=500), nullable=True, comment='保单附件URL'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fvi_end', 'fleet_vehicle_insurances', ['end_date'], unique=False)
    op.create_index('idx_fvi_type', 'fleet_vehicle_insurances', ['insurance_type'], unique=False)
    op.create_index('idx_fvi_vehicle', 'fleet_vehicle_insurances', ['vehicle_id'], unique=False)
    op.create_table('fleet_vehicle_maintenances',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False, comment='车辆ID'),
    sa.Column('type', sa.Enum('MAINTENANCE', 'REPAIR', 'INSPECTION', name='vehiclemaintenancetype'), nullable=False, comment='类型: maintenance/repair/inspection'),
    sa.Column('start_at', sa.DateTime(), nullable=True, comment='开始时间'),
    sa.Column('end_at', sa.DateTime(), nullable=True, comment='结束时间'),
    sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=True, comment='费用(元)'),
    sa.Column('mileage', sa.Numeric(precision=12, scale=2), nullable=True, comment='里程(km)'),
    sa.Column('description', sa.String(length=500), nullable=True, comment='描述'),
    sa.Column('status', sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='vehiclemaintenancestatus'), nullable=True, comment='状态'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fvm_status', 'fleet_vehicle_maintenances', ['status'], unique=False)
    op.create_index('idx_fvm_type', 'fleet_vehicle_maintenances', ['type'], unique=False)
    op.create_index('idx_fvm_vehicle', 'fleet_vehicle_maintenances', ['vehicle_id'], unique=False)
    op.create_table('maintenance_records',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('engineer_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.Enum('PREVENTIVE', 'CORRECTIVE', 'CONDITION_BASED', 'EMERGENCY', name='maintenancetype'), nullable=False),
    sa.Column('status', sa.Enum('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='maintenancestatus'), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('solution', sa.Text(), nullable=True),
    sa.Column('parts_replaced', sa.Text(), nullable=True),
    sa.Column('cost', sa.Integer(), nullable=True),
    sa.Column('planned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_records_device_id'), 'maintenance_records', ['device_id'], unique=False)
    op.create_index(op.f('ix_maintenance_records_engineer_id'), 'maintenance_records', ['engineer_id'], unique=False)
    op.create_index(op.f('ix_maintenance_records_id'), 'maintenance_records', ['id'], unique=False)
    op.create_index(op.f('ix_maintenance_records_station_id'), 'maintenance_records', ['station_id'], unique=False)
    op.create_table('on_call_shifts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='值班人员'),
    sa.Column('backup_user_id', sa.Integer(), nullable=True, comment='备份/二级值班人'),
    sa.Column('start_time', sa.DateTime(), nullable=False, comment='班次开始时间'),
    sa.Column('end_time', sa.DateTime(), nullable=False, comment='班次结束时间'),
    sa.Column('status', sa.String(length=32), nullable=True, comment='状态: scheduled|active|completed|cancelled|missed'),
    sa.Column('handover_notes', sa.Text(), nullable=True, comment='交接班备注'),
    sa.Column('handover_completed', sa.Boolean(), nullable=True, comment='交接是否完成'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_on_call_shifts_id'), 'on_call_shifts', ['id'], unique=False)
    op.create_index(op.f('ix_on_call_shifts_rule_id'), 'on_call_shifts', ['rule_id'], unique=False)
    op.create_index(op.f('ix_on_call_shifts_start_time'), 'on_call_shifts', ['start_time'], unique=False)
    op.create_index(op.f('ix_on_call_shifts_user_id'), 'on_call_shifts', ['user_id'], unique=False)
    op.create_table('prediction_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('alert_type', sa.String(length=50), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('predicted_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('suggested_action', sa.Text(), nullable=True),
    sa.Column('acknowledged', sa.Boolean(), server_default='false', nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_alerts_acknowledged'), 'prediction_alerts', ['acknowledged'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_alert_type'), 'prediction_alerts', ['alert_type'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_created_at'), 'prediction_alerts', ['created_at'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_device_id'), 'prediction_alerts', ['device_id'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_id'), 'prediction_alerts', ['id'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_severity'), 'prediction_alerts', ['severity'], unique=False)
    op.create_table('telemetry',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('grid_voltage_a', sa.Float(), nullable=True),
    sa.Column('grid_current_a', sa.Float(), nullable=True),
    sa.Column('grid_power_a', sa.Float(), nullable=True),
    sa.Column('grid_reactive_a', sa.Float(), nullable=True),
    sa.Column('grid_voltage_b', sa.Float(), nullable=True),
    sa.Column('grid_current_b', sa.Float(), nullable=True),
    sa.Column('grid_power_b', sa.Float(), nullable=True),
    sa.Column('grid_reactive_b', sa.Float(), nullable=True),
    sa.Column('grid_voltage_c', sa.Float(), nullable=True),
    sa.Column('grid_current_c', sa.Float(), nullable=True),
    sa.Column('grid_power_c', sa.Float(), nullable=True),
    sa.Column('grid_reactive_c', sa.Float(), nullable=True),
    sa.Column('grid_frequency', sa.Float(), nullable=True),
    sa.Column('grid_power_total', sa.Float(), nullable=True),
    sa.Column('grid_reactive_total', sa.Float(), nullable=True),
    sa.Column('grid_power_factor', sa.Float(), nullable=True),
    sa.Column('inv_voltage_a', sa.Float(), nullable=True),
    sa.Column('inv_current_a', sa.Float(), nullable=True),
    sa.Column('inv_power_a', sa.Float(), nullable=True),
    sa.Column('inv_voltage_b', sa.Float(), nullable=True),
    sa.Column('inv_current_b', sa.Float(), nullable=True),
    sa.Column('inv_power_b', sa.Float(), nullable=True),
    sa.Column('inv_voltage_c', sa.Float(), nullable=True),
    sa.Column('inv_current_c', sa.Float(), nullable=True),
    sa.Column('inv_power_c', sa.Float(), nullable=True),
    sa.Column('inv_power_total', sa.Float(), nullable=True),
    sa.Column('battery_voltage', sa.Float(), nullable=True),
    sa.Column('battery_current', sa.Float(), nullable=True),
    sa.Column('battery_power', sa.Float(), nullable=True),
    sa.Column('battery_soc', sa.Float(), nullable=True),
    sa.Column('battery_soh', sa.Float(), nullable=True),
    sa.Column('battery_temperature', sa.Float(), nullable=True),
    sa.Column('bms_charge_current_limit', sa.Float(), nullable=True),
    sa.Column('bms_discharge_current_limit', sa.Float(), nullable=True),
    sa.Column('bms_alarm_word', sa.Integer(), nullable=True),
    sa.Column('bms_alarm_word2', sa.Integer(), nullable=True),
    sa.Column('bms_alarm_word3', sa.Integer(), nullable=True),
    sa.Column('pv1_voltage', sa.Float(), nullable=True),
    sa.Column('pv1_current', sa.Float(), nullable=True),
    sa.Column('pv1_power', sa.Float(), nullable=True),
    sa.Column('pv2_voltage', sa.Float(), nullable=True),
    sa.Column('pv2_current', sa.Float(), nullable=True),
    sa.Column('pv2_power', sa.Float(), nullable=True),
    sa.Column('pv_power_total', sa.Float(), nullable=True),
    sa.Column('bus_voltage_pos', sa.Float(), nullable=True),
    sa.Column('bus_voltage_neg', sa.Float(), nullable=True),
    sa.Column('charger_voltage', sa.Float(), nullable=True),
    sa.Column('charger_current', sa.Float(), nullable=True),
    sa.Column('charger_power', sa.Float(), nullable=True),
    sa.Column('charger_soc', sa.Float(), nullable=True),
    sa.Column('charger_kwh', sa.Float(), nullable=True),
    sa.Column('gun_status', sa.Integer(), nullable=True),
    sa.Column('gun_temperature', sa.Float(), nullable=True),
    sa.Column('ambient_temperature', sa.Float(), nullable=True),
    sa.Column('internal_temperature', sa.Float(), nullable=True),
    sa.Column('pv_temperature', sa.Float(), nullable=True),
    sa.Column('inv_temperature', sa.Float(), nullable=True),
    sa.Column('daily_generation', sa.Float(), nullable=True),
    sa.Column('daily_consumption', sa.Float(), nullable=True),
    sa.Column('daily_charge', sa.Float(), nullable=True),
    sa.Column('daily_discharge', sa.Float(), nullable=True),
    sa.Column('total_generation', sa.Float(), nullable=True),
    sa.Column('total_consumption', sa.Float(), nullable=True),
    sa.Column('total_charge', sa.Float(), nullable=True),
    sa.Column('total_discharge', sa.Float(), nullable=True),
    sa.Column('run_time', sa.Integer(), nullable=True),
    sa.Column('run_mode', sa.Integer(), nullable=True),
    sa.Column('system_status', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_telemetry_device_id'), 'telemetry', ['device_id'], unique=False)
    op.create_index(op.f('ix_telemetry_id'), 'telemetry', ['id'], unique=False)
    op.create_index(op.f('ix_telemetry_timestamp'), 'telemetry', ['timestamp'], unique=False)
    op.create_table('telemetry_battery',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('region_id', sa.String(length=32), nullable=False),
    sa.Column('pod_id', sa.String(length=32), nullable=False),
    sa.Column('grid_voltage_a', sa.Float(), nullable=True),
    sa.Column('grid_voltage_b', sa.Float(), nullable=True),
    sa.Column('grid_voltage_c', sa.Float(), nullable=True),
    sa.Column('grid_current_a', sa.Float(), nullable=True),
    sa.Column('grid_current_b', sa.Float(), nullable=True),
    sa.Column('grid_current_c', sa.Float(), nullable=True),
    sa.Column('grid_power_total', sa.Float(), nullable=True),
    sa.Column('grid_frequency', sa.Float(), nullable=True),
    sa.Column('grid_power_factor', sa.Float(), nullable=True),
    sa.Column('battery_voltage', sa.Float(), nullable=True),
    sa.Column('battery_current', sa.Float(), nullable=True),
    sa.Column('battery_power', sa.Float(), nullable=True),
    sa.Column('battery_soc', sa.Float(), nullable=True),
    sa.Column('battery_soh', sa.Float(), nullable=True),
    sa.Column('battery_temperature', sa.Float(), nullable=True),
    sa.Column('bms_charge_current_limit', sa.Float(), nullable=True),
    sa.Column('bms_discharge_current_limit', sa.Float(), nullable=True),
    sa.Column('bms_alarm_word', sa.Integer(), nullable=True),
    sa.Column('bms_alarm_word2', sa.Integer(), nullable=True),
    sa.Column('bms_alarm_word3', sa.Integer(), nullable=True),
    sa.Column('daily_charge', sa.Float(), nullable=True),
    sa.Column('daily_discharge', sa.Float(), nullable=True),
    sa.Column('total_charge', sa.Float(), nullable=True),
    sa.Column('total_discharge', sa.Float(), nullable=True),
    sa.Column('internal_temperature', sa.Float(), nullable=True),
    sa.Column('ambient_temperature', sa.Float(), nullable=True),
    sa.Column('run_time', sa.Integer(), nullable=True),
    sa.Column('run_mode', sa.Integer(), nullable=True),
    sa.Column('system_status', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_battery_device_region', 'telemetry_battery', ['device_id', 'region_id'], unique=False)
    op.create_index('idx_battery_station_device_ts', 'telemetry_battery', ['station_id', 'device_id', sa.literal_column('timestamp DESC')], unique=False)
    op.create_index('idx_battery_ts', 'telemetry_battery', [sa.literal_column('timestamp DESC')], unique=False)
    op.create_index(op.f('ix_telemetry_battery_device_id'), 'telemetry_battery', ['device_id'], unique=False)
    op.create_index(op.f('ix_telemetry_battery_pod_id'), 'telemetry_battery', ['pod_id'], unique=False)
    op.create_index(op.f('ix_telemetry_battery_region_id'), 'telemetry_battery', ['region_id'], unique=False)
    op.create_index(op.f('ix_telemetry_battery_station_id'), 'telemetry_battery', ['station_id'], unique=False)
    op.create_table('telemetry_charger',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('region_id', sa.String(length=32), nullable=False),
    sa.Column('pod_id', sa.String(length=32), nullable=False),
    sa.Column('charger_voltage', sa.Float(), nullable=True),
    sa.Column('charger_current', sa.Float(), nullable=True),
    sa.Column('charger_power', sa.Float(), nullable=True),
    sa.Column('charger_soc', sa.Float(), nullable=True),
    sa.Column('charger_kwh', sa.Float(), nullable=True),
    sa.Column('gun_status', sa.Integer(), nullable=True),
    sa.Column('gun_temperature', sa.Float(), nullable=True),
    sa.Column('internal_temperature', sa.Float(), nullable=True),
    sa.Column('ambient_temperature', sa.Float(), nullable=True),
    sa.Column('run_time', sa.Integer(), nullable=True),
    sa.Column('run_mode', sa.Integer(), nullable=True),
    sa.Column('system_status', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_charger_device_region', 'telemetry_charger', ['device_id', 'region_id'], unique=False)
    op.create_index('idx_charger_station_device_ts', 'telemetry_charger', ['station_id', 'device_id', sa.literal_column('timestamp DESC')], unique=False)
    op.create_index('idx_charger_ts', 'telemetry_charger', [sa.literal_column('timestamp DESC')], unique=False)
    op.create_index(op.f('ix_telemetry_charger_device_id'), 'telemetry_charger', ['device_id'], unique=False)
    op.create_index(op.f('ix_telemetry_charger_pod_id'), 'telemetry_charger', ['pod_id'], unique=False)
    op.create_index(op.f('ix_telemetry_charger_region_id'), 'telemetry_charger', ['region_id'], unique=False)
    op.create_index(op.f('ix_telemetry_charger_station_id'), 'telemetry_charger', ['station_id'], unique=False)
    op.create_table('telemetry_pv',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('region_id', sa.String(length=32), nullable=False),
    sa.Column('pod_id', sa.String(length=32), nullable=False),
    sa.Column('grid_voltage_a', sa.Float(), nullable=True),
    sa.Column('grid_voltage_b', sa.Float(), nullable=True),
    sa.Column('grid_voltage_c', sa.Float(), nullable=True),
    sa.Column('grid_current_a', sa.Float(), nullable=True),
    sa.Column('grid_current_b', sa.Float(), nullable=True),
    sa.Column('grid_current_c', sa.Float(), nullable=True),
    sa.Column('grid_power_total', sa.Float(), nullable=True),
    sa.Column('grid_frequency', sa.Float(), nullable=True),
    sa.Column('grid_power_factor', sa.Float(), nullable=True),
    sa.Column('pv1_voltage', sa.Float(), nullable=True),
    sa.Column('pv1_current', sa.Float(), nullable=True),
    sa.Column('pv1_power', sa.Float(), nullable=True),
    sa.Column('pv2_voltage', sa.Float(), nullable=True),
    sa.Column('pv2_current', sa.Float(), nullable=True),
    sa.Column('pv2_power', sa.Float(), nullable=True),
    sa.Column('pv_power_total', sa.Float(), nullable=True),
    sa.Column('bus_voltage_pos', sa.Float(), nullable=True),
    sa.Column('bus_voltage_neg', sa.Float(), nullable=True),
    sa.Column('internal_temperature', sa.Float(), nullable=True),
    sa.Column('pv_temperature', sa.Float(), nullable=True),
    sa.Column('inv_temperature', sa.Float(), nullable=True),
    sa.Column('battery_temperature', sa.Float(), nullable=True),
    sa.Column('daily_generation', sa.Float(), nullable=True),
    sa.Column('total_generation', sa.Float(), nullable=True),
    sa.Column('run_time', sa.Integer(), nullable=True),
    sa.Column('run_mode', sa.Integer(), nullable=True),
    sa.Column('system_status', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pv_device_region', 'telemetry_pv', ['device_id', 'region_id'], unique=False)
    op.create_index('idx_pv_station_device_ts', 'telemetry_pv', ['station_id', 'device_id', sa.literal_column('timestamp DESC')], unique=False)
    op.create_index('idx_pv_ts', 'telemetry_pv', [sa.literal_column('timestamp DESC')], unique=False)
    op.create_index(op.f('ix_telemetry_pv_device_id'), 'telemetry_pv', ['device_id'], unique=False)
    op.create_index(op.f('ix_telemetry_pv_pod_id'), 'telemetry_pv', ['pod_id'], unique=False)
    op.create_index(op.f('ix_telemetry_pv_region_id'), 'telemetry_pv', ['region_id'], unique=False)
    op.create_index(op.f('ix_telemetry_pv_station_id'), 'telemetry_pv', ['station_id'], unique=False)
    op.create_table('v2g_dispatch_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('dispatch_type', sa.String(length=20), nullable=False, comment='调度类型: charge/discharge/standby'),
    sa.Column('target_power_kw', sa.Float(), nullable=False, comment='目标功率(kW)'),
    sa.Column('actual_power_kw', sa.Float(), nullable=False, comment='实际功率(kW)'),
    sa.Column('status', sa.String(length=20), nullable=False, comment='状态: pending/executing/completed/failed'),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=True, comment='开始时间'),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=True, comment='结束时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_v2g_dispatch_logs_device_id'), 'v2g_dispatch_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_v2g_dispatch_logs_dispatch_type'), 'v2g_dispatch_logs', ['dispatch_type'], unique=False)
    op.create_index(op.f('ix_v2g_dispatch_logs_id'), 'v2g_dispatch_logs', ['id'], unique=False)
    op.create_index(op.f('ix_v2g_dispatch_logs_status'), 'v2g_dispatch_logs', ['status'], unique=False)
    op.create_table('work_orders',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('type', sa.Enum('preventive', 'emergency', 'plan', 'maintenance', 'inspection', 'upgrade', 'repair', name='workordertype'), nullable=True),
    sa.Column('level', sa.Enum('info', 'warning', 'critical', 'P0', 'P1', 'P2', name='workorderlevel'), nullable=True),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('assignee_id', sa.Integer(), nullable=True),
    sa.Column('creator_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'accepted', 'processing', 'pending_verify', 'completed', 'assigned', 'in_progress', 'resolved', 'closed', name='workorderstatus'), nullable=True),
    sa.Column('fault_desc', sa.Text(), nullable=True),
    sa.Column('solution', sa.Text(), nullable=True),
    sa.Column('attachments', sa.JSON(), nullable=True),
    sa.Column('create_time', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('accept_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finish_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verify_time', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_orders_assignee_id'), 'work_orders', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_work_orders_device_id'), 'work_orders', ['device_id'], unique=False)
    op.create_index(op.f('ix_work_orders_station_id'), 'work_orders', ['station_id'], unique=False)
    op.create_table('alarms',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('device_id', sa.BigInteger(), nullable=False),
    sa.Column('station_id', sa.BigInteger(), nullable=True),
    sa.Column('rule_id', sa.Integer(), nullable=True),
    sa.Column('alarm_type', sa.String(length=50), nullable=True),
    sa.Column('level', sa.Enum('info', 'warning', 'critical', 'fatal', name='alarmlevel'), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('fault_code', sa.String(length=20), nullable=True),
    sa.Column('fault_source', sa.String(length=50), nullable=True),
    sa.Column('sequence_no', sa.Integer(), nullable=True),
    sa.Column('modbus_address', sa.Integer(), nullable=True),
    sa.Column('mqtt_message_type', sa.Integer(), nullable=True),
    sa.Column('diagnosis_result', sa.Text(), nullable=True),
    sa.Column('repair_suggestion', sa.Text(), nullable=True),
    sa.Column('remote_fixable', sa.Boolean(), nullable=True),
    sa.Column('trigger_metric', sa.String(length=50), nullable=True),
    sa.Column('trigger_value', sa.Float(), nullable=True),
    sa.Column('trigger_threshold', sa.Float(), nullable=True),
    sa.Column('trigger_operator', sa.String(length=10), nullable=True),
    sa.Column('escalated_from', sa.String(length=20), nullable=True, comment='从哪个级别升级而来'),
    sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True, comment='升级时间'),
    sa.Column('original_level', sa.String(length=20), nullable=True, comment='原始告警级别'),
    sa.Column('aggregation_count', sa.Integer(), nullable=True, comment='聚合告警计数'),
    sa.Column('aggregation_first_at', sa.DateTime(timezone=True), nullable=True, comment='聚合首条告警时间'),
    sa.Column('aggregation_last_at', sa.DateTime(timezone=True), nullable=True, comment='聚合末条告警时间'),
    sa.Column('status', sa.Enum('active', 'acknowledged', 'processing', 'resolved', 'processed', 'ignored', name='alarmstatus'), nullable=True),
    sa.Column('handler_id', sa.Integer(), nullable=True),
    sa.Column('handle_desc', sa.Text(), nullable=True),
    sa.Column('workorder_id', sa.String(length=50), nullable=True),
    sa.Column('remote_fix_attempted', sa.Boolean(), nullable=True),
    sa.Column('remote_fix_result', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alarms_alarm_type'), 'alarms', ['alarm_type'], unique=False)
    op.create_index(op.f('ix_alarms_device_id'), 'alarms', ['device_id'], unique=False)
    op.create_index(op.f('ix_alarms_fault_code'), 'alarms', ['fault_code'], unique=False)
    op.create_index(op.f('ix_alarms_id'), 'alarms', ['id'], unique=False)
    op.create_index(op.f('ix_alarms_rule_id'), 'alarms', ['rule_id'], unique=False)
    op.create_index(op.f('ix_alarms_station_id'), 'alarms', ['station_id'], unique=False)
    op.create_index(op.f('ix_alarms_workorder_id'), 'alarms', ['workorder_id'], unique=False)
    op.create_table('fleet_driver_accounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=False, comment='司机ID'),
    sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=True, comment='账户余额(元)'),
    sa.Column('pay_password', sa.String(length=255), nullable=True, comment='支付密码hash'),
    sa.Column('status', sa.Enum('ACTIVE', 'FROZEN', 'CLOSED', name='accountstatus'), nullable=True, comment='账户状态'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('driver_id')
    )
    op.create_index('idx_fda_driver', 'fleet_driver_accounts', ['driver_id'], unique=False)
    op.create_index('idx_fda_status', 'fleet_driver_accounts', ['status'], unique=False)
    op.create_table('fleet_driver_attendance',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=False, comment='司机ID'),
    sa.Column('date', sa.String(length=10), nullable=False, comment='考勤日期 YYYY-MM-DD'),
    sa.Column('shift_type', sa.String(length=10), nullable=False, comment='班次: day/night/rest'),
    sa.Column('hours', sa.Float(), nullable=False, comment='工时(小时)'),
    sa.Column('status', sa.String(length=10), nullable=False, comment='状态: normal/late/absent'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fatt_date', 'fleet_driver_attendance', ['date'], unique=False)
    op.create_index('idx_fatt_driver_date', 'fleet_driver_attendance', ['driver_id', 'date'], unique=True)
    op.create_index('idx_fatt_status', 'fleet_driver_attendance', ['status'], unique=False)
    op.create_table('work_order_checkins',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('photo_url', sa.String(length=500), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_checkins_created_at'), 'work_order_checkins', ['created_at'], unique=False)
    op.create_index(op.f('ix_work_order_checkins_id'), 'work_order_checkins', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_checkins_order_id'), 'work_order_checkins', ['order_id'], unique=False)
    op.create_table('work_order_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('attachments', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_logs_id'), 'work_order_logs', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_logs_order_id'), 'work_order_logs', ['order_id'], unique=False)
    op.create_table('work_order_ratings',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('response_rating', sa.Integer(), nullable=False),
    sa.Column('quality_rating', sa.Integer(), nullable=False),
    sa.Column('attitude_rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_ratings_id'), 'work_order_ratings', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_ratings_order_id'), 'work_order_ratings', ['order_id'], unique=True)
    op.create_table('work_order_spare_parts',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('part_name', sa.String(length=100), nullable=False),
    sa.Column('part_model', sa.String(length=100), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_spare_parts_created_at'), 'work_order_spare_parts', ['created_at'], unique=False)
    op.create_index(op.f('ix_work_order_spare_parts_id'), 'work_order_spare_parts', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_spare_parts_order_id'), 'work_order_spare_parts', ['order_id'], unique=False)
    op.create_table('work_order_support_requests',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('target_engineer_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('remote', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_support_requests_created_at'), 'work_order_support_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_work_order_support_requests_id'), 'work_order_support_requests', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_support_requests_order_id'), 'work_order_support_requests', ['order_id'], unique=False)
    op.create_table('ai_diagnosis_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alarm_id', sa.Integer(), nullable=True),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', name='diagnosisstatus'), nullable=True),
    sa.Column('trigger_type', sa.String(length=20), nullable=True),
    sa.Column('log_source', sa.String(length=50), nullable=True),
    sa.Column('raw_log', sa.Text(), nullable=True),
    sa.Column('fault_type', sa.String(length=100), nullable=True),
    sa.Column('fault_location', sa.String(length=200), nullable=True),
    sa.Column('root_cause', sa.Text(), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('matched_fault_code', sa.String(length=20), nullable=True),
    sa.Column('matched_fault_name', sa.String(length=100), nullable=True),
    sa.Column('immediate_actions', sa.JSON(), nullable=True),
    sa.Column('repair_suggestions', sa.JSON(), nullable=True),
    sa.Column('preventive_measures', sa.JSON(), nullable=True),
    sa.Column('remote_fixable', sa.Boolean(), nullable=True),
    sa.Column('raw_ai_response', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('user_feedback', sa.String(length=20), nullable=True),
    sa.Column('user_comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_diagnosis_records_alarm_id'), 'ai_diagnosis_records', ['alarm_id'], unique=False)
    op.create_index(op.f('ix_ai_diagnosis_records_device_id'), 'ai_diagnosis_records', ['device_id'], unique=False)
    op.create_index(op.f('ix_ai_diagnosis_records_id'), 'ai_diagnosis_records', ['id'], unique=False)
    op.create_index(op.f('ix_ai_diagnosis_records_station_id'), 'ai_diagnosis_records', ['station_id'], unique=False)
    op.create_table('alarm_rule_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('rule_id', sa.BigInteger(), nullable=False),
    sa.Column('rule_name', sa.String(length=100), nullable=True),
    sa.Column('device_id', sa.Integer(), nullable=True),
    sa.Column('device_name', sa.String(length=100), nullable=True),
    sa.Column('station_id', sa.Integer(), nullable=True),
    sa.Column('metric', sa.String(length=50), nullable=True),
    sa.Column('current_value', sa.Float(), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('operator', sa.String(length=10), nullable=True),
    sa.Column('triggered', sa.Boolean(), nullable=True),
    sa.Column('alarm_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alarm_rule_logs_device_id'), 'alarm_rule_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_alarm_rule_logs_id'), 'alarm_rule_logs', ['id'], unique=False)
    op.create_index(op.f('ix_alarm_rule_logs_rule_id'), 'alarm_rule_logs', ['rule_id'], unique=False)
    op.create_index(op.f('ix_alarm_rule_logs_station_id'), 'alarm_rule_logs', ['station_id'], unique=False)
    op.create_table('fleet_driver_transactions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False, comment='账户ID'),
    sa.Column('type', sa.Enum('RECHARGE', 'CONSUME', 'REFUND', name='drivertransactiontype'), nullable=False, comment='交易类型: recharge/consume/refund'),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False, comment='交易金额(元)'),
    sa.Column('balance_after', sa.Numeric(precision=12, scale=2), nullable=False, comment='交易后余额(元)'),
    sa.Column('related_order_id', sa.String(length=64), nullable=True, comment='关联订单号'),
    sa.Column('remark', sa.String(length=500), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fdt_account', 'fleet_driver_transactions', ['account_id'], unique=False)
    op.create_index('idx_fdt_created', 'fleet_driver_transactions', ['created_at'], unique=False)
    op.create_index('idx_fdt_order', 'fleet_driver_transactions', ['related_order_id'], unique=False)
    op.create_index('idx_fdt_type', 'fleet_driver_transactions', ['type'], unique=False)
    op.create_table('on_call_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shift_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='记录人'),
    sa.Column('event_type', sa.String(length=32), nullable=True, comment='事件类型: note|alarm|workorder|handover|escalation|incident'),
    sa.Column('content', sa.Text(), nullable=False, comment='日志内容'),
    sa.Column('alarm_id', sa.Integer(), nullable=True, comment='关联告警'),
    sa.Column('workorder_id', sa.String(length=50), nullable=True, comment='关联工单号'),
    sa.Column('severity', sa.String(length=32), nullable=True, comment='严重级别: info|warning|critical'),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_on_call_logs_id'), 'on_call_logs', ['id'], unique=False)
    op.create_index(op.f('ix_on_call_logs_shift_id'), 'on_call_logs', ['shift_id'], unique=False)
    # ---- 卡 15a07d0f: FK 全部后置补挂 (140 条, 原 create_table 内联) ----
    # PG 建表严格校验 FK 目标表存在, teams<->users 互引成环, 任何建表序都
    # 无法满足; 改为全部建表后统一补挂。SQLite 不支持 ALTER TABLE
    # ADD CONSTRAINT, 方言守卫跳过 (SQLite fresh 库无 FK 约束, 业务测试全
    # 走 create_all 不受影响)。列/类型/索引/PK/UQ 语义与冻结快照一致。
    if op.get_bind().dialect.name != "sqlite":
        for _src, _ref, _lcols, _rcols, _ondelete in _POSTPONED_FKS:
            if _ondelete is None:
                op.create_foreign_key(None, _src, _ref, _lcols, _rcols)
            else:
                op.create_foreign_key(None, _src, _ref, _lcols, _rcols, ondelete=_ondelete)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_on_call_logs_shift_id'), table_name='on_call_logs')
    op.drop_index(op.f('ix_on_call_logs_id'), table_name='on_call_logs')
    op.drop_table('on_call_logs')
    op.drop_index('idx_fdt_type', table_name='fleet_driver_transactions')
    op.drop_index('idx_fdt_order', table_name='fleet_driver_transactions')
    op.drop_index('idx_fdt_created', table_name='fleet_driver_transactions')
    op.drop_index('idx_fdt_account', table_name='fleet_driver_transactions')
    op.drop_table('fleet_driver_transactions')
    op.drop_index(op.f('ix_alarm_rule_logs_station_id'), table_name='alarm_rule_logs')
    op.drop_index(op.f('ix_alarm_rule_logs_rule_id'), table_name='alarm_rule_logs')
    op.drop_index(op.f('ix_alarm_rule_logs_id'), table_name='alarm_rule_logs')
    op.drop_index(op.f('ix_alarm_rule_logs_device_id'), table_name='alarm_rule_logs')
    op.drop_table('alarm_rule_logs')
    op.drop_index(op.f('ix_ai_diagnosis_records_station_id'), table_name='ai_diagnosis_records')
    op.drop_index(op.f('ix_ai_diagnosis_records_id'), table_name='ai_diagnosis_records')
    op.drop_index(op.f('ix_ai_diagnosis_records_device_id'), table_name='ai_diagnosis_records')
    op.drop_index(op.f('ix_ai_diagnosis_records_alarm_id'), table_name='ai_diagnosis_records')
    op.drop_table('ai_diagnosis_records')
    op.drop_index(op.f('ix_work_order_support_requests_order_id'), table_name='work_order_support_requests')
    op.drop_index(op.f('ix_work_order_support_requests_id'), table_name='work_order_support_requests')
    op.drop_index(op.f('ix_work_order_support_requests_created_at'), table_name='work_order_support_requests')
    op.drop_table('work_order_support_requests')
    op.drop_index(op.f('ix_work_order_spare_parts_order_id'), table_name='work_order_spare_parts')
    op.drop_index(op.f('ix_work_order_spare_parts_id'), table_name='work_order_spare_parts')
    op.drop_index(op.f('ix_work_order_spare_parts_created_at'), table_name='work_order_spare_parts')
    op.drop_table('work_order_spare_parts')
    op.drop_index(op.f('ix_work_order_ratings_order_id'), table_name='work_order_ratings')
    op.drop_index(op.f('ix_work_order_ratings_id'), table_name='work_order_ratings')
    op.drop_table('work_order_ratings')
    op.drop_index(op.f('ix_work_order_logs_order_id'), table_name='work_order_logs')
    op.drop_index(op.f('ix_work_order_logs_id'), table_name='work_order_logs')
    op.drop_table('work_order_logs')
    op.drop_index(op.f('ix_work_order_checkins_order_id'), table_name='work_order_checkins')
    op.drop_index(op.f('ix_work_order_checkins_id'), table_name='work_order_checkins')
    op.drop_index(op.f('ix_work_order_checkins_created_at'), table_name='work_order_checkins')
    op.drop_table('work_order_checkins')
    op.drop_index('idx_fatt_status', table_name='fleet_driver_attendance')
    op.drop_index('idx_fatt_driver_date', table_name='fleet_driver_attendance')
    op.drop_index('idx_fatt_date', table_name='fleet_driver_attendance')
    op.drop_table('fleet_driver_attendance')
    op.drop_index('idx_fda_status', table_name='fleet_driver_accounts')
    op.drop_index('idx_fda_driver', table_name='fleet_driver_accounts')
    op.drop_table('fleet_driver_accounts')
    op.drop_index(op.f('ix_alarms_workorder_id'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_station_id'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_rule_id'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_id'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_fault_code'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_device_id'), table_name='alarms')
    op.drop_index(op.f('ix_alarms_alarm_type'), table_name='alarms')
    op.drop_table('alarms')
    op.drop_index(op.f('ix_work_orders_station_id'), table_name='work_orders')
    op.drop_index(op.f('ix_work_orders_device_id'), table_name='work_orders')
    op.drop_index(op.f('ix_work_orders_assignee_id'), table_name='work_orders')
    op.drop_table('work_orders')
    op.drop_index(op.f('ix_v2g_dispatch_logs_status'), table_name='v2g_dispatch_logs')
    op.drop_index(op.f('ix_v2g_dispatch_logs_id'), table_name='v2g_dispatch_logs')
    op.drop_index(op.f('ix_v2g_dispatch_logs_dispatch_type'), table_name='v2g_dispatch_logs')
    op.drop_index(op.f('ix_v2g_dispatch_logs_device_id'), table_name='v2g_dispatch_logs')
    op.drop_table('v2g_dispatch_logs')
    op.drop_index(op.f('ix_telemetry_pv_station_id'), table_name='telemetry_pv')
    op.drop_index(op.f('ix_telemetry_pv_region_id'), table_name='telemetry_pv')
    op.drop_index(op.f('ix_telemetry_pv_pod_id'), table_name='telemetry_pv')
    op.drop_index(op.f('ix_telemetry_pv_device_id'), table_name='telemetry_pv')
    op.drop_index('idx_pv_ts', table_name='telemetry_pv')
    op.drop_index('idx_pv_station_device_ts', table_name='telemetry_pv')
    op.drop_index('idx_pv_device_region', table_name='telemetry_pv')
    op.drop_table('telemetry_pv')
    op.drop_index(op.f('ix_telemetry_charger_station_id'), table_name='telemetry_charger')
    op.drop_index(op.f('ix_telemetry_charger_region_id'), table_name='telemetry_charger')
    op.drop_index(op.f('ix_telemetry_charger_pod_id'), table_name='telemetry_charger')
    op.drop_index(op.f('ix_telemetry_charger_device_id'), table_name='telemetry_charger')
    op.drop_index('idx_charger_ts', table_name='telemetry_charger')
    op.drop_index('idx_charger_station_device_ts', table_name='telemetry_charger')
    op.drop_index('idx_charger_device_region', table_name='telemetry_charger')
    op.drop_table('telemetry_charger')
    op.drop_index(op.f('ix_telemetry_battery_station_id'), table_name='telemetry_battery')
    op.drop_index(op.f('ix_telemetry_battery_region_id'), table_name='telemetry_battery')
    op.drop_index(op.f('ix_telemetry_battery_pod_id'), table_name='telemetry_battery')
    op.drop_index(op.f('ix_telemetry_battery_device_id'), table_name='telemetry_battery')
    op.drop_index('idx_battery_ts', table_name='telemetry_battery')
    op.drop_index('idx_battery_station_device_ts', table_name='telemetry_battery')
    op.drop_index('idx_battery_device_region', table_name='telemetry_battery')
    op.drop_table('telemetry_battery')
    op.drop_index(op.f('ix_telemetry_timestamp'), table_name='telemetry')
    op.drop_index(op.f('ix_telemetry_id'), table_name='telemetry')
    op.drop_index(op.f('ix_telemetry_device_id'), table_name='telemetry')
    op.drop_table('telemetry')
    op.drop_index(op.f('ix_prediction_alerts_severity'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_id'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_device_id'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_created_at'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_alert_type'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_acknowledged'), table_name='prediction_alerts')
    op.drop_table('prediction_alerts')
    op.drop_index(op.f('ix_on_call_shifts_user_id'), table_name='on_call_shifts')
    op.drop_index(op.f('ix_on_call_shifts_start_time'), table_name='on_call_shifts')
    op.drop_index(op.f('ix_on_call_shifts_rule_id'), table_name='on_call_shifts')
    op.drop_index(op.f('ix_on_call_shifts_id'), table_name='on_call_shifts')
    op.drop_table('on_call_shifts')
    op.drop_index(op.f('ix_maintenance_records_station_id'), table_name='maintenance_records')
    op.drop_index(op.f('ix_maintenance_records_id'), table_name='maintenance_records')
    op.drop_index(op.f('ix_maintenance_records_engineer_id'), table_name='maintenance_records')
    op.drop_index(op.f('ix_maintenance_records_device_id'), table_name='maintenance_records')
    op.drop_table('maintenance_records')
    op.drop_index('idx_fvm_vehicle', table_name='fleet_vehicle_maintenances')
    op.drop_index('idx_fvm_type', table_name='fleet_vehicle_maintenances')
    op.drop_index('idx_fvm_status', table_name='fleet_vehicle_maintenances')
    op.drop_table('fleet_vehicle_maintenances')
    op.drop_index('idx_fvi_vehicle', table_name='fleet_vehicle_insurances')
    op.drop_index('idx_fvi_type', table_name='fleet_vehicle_insurances')
    op.drop_index('idx_fvi_end', table_name='fleet_vehicle_insurances')
    op.drop_table('fleet_vehicle_insurances')
    op.drop_index(op.f('ix_fleet_v2g_revenue_vehicle_id'), table_name='fleet_v2g_revenue')
    op.drop_index(op.f('ix_fleet_v2g_revenue_record_date'), table_name='fleet_v2g_revenue')
    op.drop_index(op.f('ix_fleet_v2g_revenue_enterprise_id'), table_name='fleet_v2g_revenue')
    op.drop_index('idx_fv2gr_vehicle_date', table_name='fleet_v2g_revenue')
    op.drop_index('idx_fv2gr_enterprise_vehicle_date', table_name='fleet_v2g_revenue')
    op.drop_index('idx_fv2gr_enterprise_date', table_name='fleet_v2g_revenue')
    op.drop_table('fleet_v2g_revenue')
    op.drop_index(op.f('ix_fleet_v2g_plans_vehicle_id'), table_name='fleet_v2g_plans')
    op.drop_index(op.f('ix_fleet_v2g_plans_status'), table_name='fleet_v2g_plans')
    op.drop_index(op.f('ix_fleet_v2g_plans_plan_date'), table_name='fleet_v2g_plans')
    op.drop_index(op.f('ix_fleet_v2g_plans_enterprise_id'), table_name='fleet_v2g_plans')
    op.drop_index('idx_fv2gp_vehicle_date', table_name='fleet_v2g_plans')
    op.drop_index('idx_fv2gp_status_date', table_name='fleet_v2g_plans')
    op.drop_index('idx_fv2gp_enterprise_date', table_name='fleet_v2g_plans')
    op.drop_table('fleet_v2g_plans')
    op.drop_index('idx_fsd_vehicle', table_name='fleet_settlement_details')
    op.drop_index('idx_fsd_order', table_name='fleet_settlement_details')
    op.drop_index('idx_fsd_bill', table_name='fleet_settlement_details')
    op.drop_table('fleet_settlement_details')
    op.drop_index('idx_fir_status', table_name='fleet_invoice_requests')
    op.drop_index('idx_fir_enterprise', table_name='fleet_invoice_requests')
    op.drop_index('idx_fir_bill', table_name='fleet_invoice_requests')
    op.drop_table('fleet_invoice_requests')
    op.drop_index('idx_fd_status', table_name='fleet_drivers')
    op.drop_index('idx_fd_phone', table_name='fleet_drivers')
    op.drop_index('idx_fd_license', table_name='fleet_drivers')
    op.drop_index('idx_fd_enterprise', table_name='fleet_drivers')
    op.drop_table('fleet_drivers')
    op.drop_index(op.f('ix_fleet_alert_records_vehicle_id'), table_name='fleet_alert_records')
    op.drop_index(op.f('ix_fleet_alert_records_triggered_at'), table_name='fleet_alert_records')
    op.drop_index(op.f('ix_fleet_alert_records_status'), table_name='fleet_alert_records')
    op.drop_index(op.f('ix_fleet_alert_records_rule_id'), table_name='fleet_alert_records')
    op.drop_index(op.f('ix_fleet_alert_records_enterprise_id'), table_name='fleet_alert_records')
    op.drop_index('idx_farec_rule_vehicle_status', table_name='fleet_alert_records')
    op.drop_index('idx_farec_enterprise_status', table_name='fleet_alert_records')
    op.drop_table('fleet_alert_records')
    op.drop_index('idx_et_type', table_name='enterprise_transactions')
    op.drop_index('idx_et_order', table_name='enterprise_transactions')
    op.drop_index('idx_et_enterprise', table_name='enterprise_transactions')
    op.drop_index('idx_et_created', table_name='enterprise_transactions')
    op.drop_table('enterprise_transactions')
    op.drop_index(op.f('ix_digital_twin_models_model_type'), table_name='digital_twin_models')
    op.drop_index(op.f('ix_digital_twin_models_id'), table_name='digital_twin_models')
    op.drop_index(op.f('ix_digital_twin_models_device_id'), table_name='digital_twin_models')
    op.drop_table('digital_twin_models')
    op.drop_index(op.f('ix_digital_twin_data_points_id'), table_name='digital_twin_data_points')
    op.drop_index(op.f('ix_digital_twin_data_points_device_id'), table_name='digital_twin_data_points')
    op.drop_table('digital_twin_data_points')
    op.drop_index(op.f('ix_device_qrcodes_qr_code'), table_name='device_qrcodes')
    op.drop_index(op.f('ix_device_qrcodes_id'), table_name='device_qrcodes')
    op.drop_index(op.f('ix_device_qrcodes_device_id'), table_name='device_qrcodes')
    op.drop_table('device_qrcodes')
    op.drop_index(op.f('ix_device_health_records_id'), table_name='device_health_records')
    op.drop_index(op.f('ix_device_health_records_device_id'), table_name='device_health_records')
    op.drop_table('device_health_records')
    op.drop_index(op.f('ix_device_health_history_id'), table_name='device_health_history')
    op.drop_index(op.f('ix_device_health_history_device_id'), table_name='device_health_history')
    op.drop_index(op.f('ix_device_health_history_calculated_at'), table_name='device_health_history')
    op.drop_table('device_health_history')
    op.drop_index(op.f('ix_device_efficiency_logs_station_id'), table_name='device_efficiency_logs')
    op.drop_index(op.f('ix_device_efficiency_logs_recorded_at'), table_name='device_efficiency_logs')
    op.drop_index(op.f('ix_device_efficiency_logs_metric_type'), table_name='device_efficiency_logs')
    op.drop_index(op.f('ix_device_efficiency_logs_log_date'), table_name='device_efficiency_logs')
    op.drop_index(op.f('ix_device_efficiency_logs_id'), table_name='device_efficiency_logs')
    op.drop_index(op.f('ix_device_efficiency_logs_device_id'), table_name='device_efficiency_logs')
    op.drop_table('device_efficiency_logs')
    op.drop_index(op.f('ix_device_daily_stats_station_id'), table_name='device_daily_stats')
    op.drop_index(op.f('ix_device_daily_stats_region_id'), table_name='device_daily_stats')
    op.drop_index(op.f('ix_device_daily_stats_pod_id'), table_name='device_daily_stats')
    op.drop_index(op.f('ix_device_daily_stats_device_type'), table_name='device_daily_stats')
    op.drop_index(op.f('ix_device_daily_stats_device_id'), table_name='device_daily_stats')
    op.drop_index('idx_device_daily_type', table_name='device_daily_stats')
    op.drop_index('idx_device_daily_station_date', table_name='device_daily_stats')
    op.drop_index('idx_device_daily_region', table_name='device_daily_stats')
    op.drop_index('idx_device_daily_device_date', table_name='device_daily_stats')
    op.drop_table('device_daily_stats')
    op.drop_index(op.f('ix_device_control_logs_id'), table_name='device_control_logs')
    op.drop_index(op.f('ix_device_control_logs_device_id'), table_name='device_control_logs')
    op.drop_index(op.f('ix_device_control_logs_created_at'), table_name='device_control_logs')
    op.drop_index(op.f('ix_device_control_logs_action'), table_name='device_control_logs')
    op.drop_table('device_control_logs')
    op.drop_index(op.f('ix_device_configs_id'), table_name='device_configs')
    op.drop_index(op.f('ix_device_configs_device_id'), table_name='device_configs')
    op.drop_table('device_configs')
    op.drop_index(op.f('ix_client_certificates_tenant_id'), table_name='client_certificates')
    op.drop_index(op.f('ix_client_certificates_id'), table_name='client_certificates')
    op.drop_index(op.f('ix_client_certificates_device_id'), table_name='client_certificates')
    op.drop_index(op.f('ix_client_certificates_cert_serial'), table_name='client_certificates')
    op.drop_index('idx_client_cert_valid', table_name='client_certificates')
    op.drop_index('idx_client_cert_tenant', table_name='client_certificates')
    op.drop_index('idx_client_cert_device', table_name='client_certificates')
    op.drop_index('idx_client_cert_active', table_name='client_certificates')
    op.drop_table('client_certificates')
    op.drop_index(op.f('ix_api_request_logs_request_time'), table_name='api_request_logs')
    op.drop_index(op.f('ix_api_request_logs_request_id'), table_name='api_request_logs')
    op.drop_index(op.f('ix_api_request_logs_id'), table_name='api_request_logs')
    op.drop_table('api_request_logs')
    op.drop_index(op.f('ix_analytics_results_id'), table_name='analytics_results')
    op.drop_index(op.f('ix_analytics_results_generated_at'), table_name='analytics_results')
    op.drop_index(op.f('ix_analytics_results_device_id'), table_name='analytics_results')
    op.drop_index(op.f('ix_analytics_results_analysis_type'), table_name='analytics_results')
    op.drop_table('analytics_results')
    op.drop_index('idx_svw_vin', table_name='station_vin_whitelist')
    op.drop_index('idx_svw_station_vin', table_name='station_vin_whitelist')
    op.drop_index('idx_svw_enterprise', table_name='station_vin_whitelist')
    op.drop_table('station_vin_whitelist')
    op.drop_index(op.f('ix_station_hourly_stats_station_id'), table_name='station_hourly_stats')
    op.drop_index(op.f('ix_station_hourly_stats_region_id'), table_name='station_hourly_stats')
    op.drop_index(op.f('ix_station_hourly_stats_pod_id'), table_name='station_hourly_stats')
    op.drop_index('idx_station_hourly_station_time', table_name='station_hourly_stats')
    op.drop_index('idx_station_hourly_region', table_name='station_hourly_stats')
    op.drop_table('station_hourly_stats')
    op.drop_index(op.f('ix_service_fee_prices_user_type'), table_name='service_fee_prices')
    op.drop_index(op.f('ix_service_fee_prices_station_id'), table_name='service_fee_prices')
    op.drop_index(op.f('ix_service_fee_prices_expire_date'), table_name='service_fee_prices')
    op.drop_index(op.f('ix_service_fee_prices_effective_date'), table_name='service_fee_prices')
    op.drop_index('idx_sfp_station_user', table_name='service_fee_prices')
    op.drop_index('idx_sfp_effective', table_name='service_fee_prices')
    op.drop_index('idx_sfp_active', table_name='service_fee_prices')
    op.drop_table('service_fee_prices')
    op.drop_index(op.f('ix_reservation_fee_prices_station_id'), table_name='reservation_fee_prices')
    op.drop_index(op.f('ix_reservation_fee_prices_expire_date'), table_name='reservation_fee_prices')
    op.drop_index(op.f('ix_reservation_fee_prices_effective_date'), table_name='reservation_fee_prices')
    op.drop_index('idx_rfp_station', table_name='reservation_fee_prices')
    op.drop_index('idx_rfp_effective', table_name='reservation_fee_prices')
    op.drop_index('idx_rfp_active', table_name='reservation_fee_prices')
    op.drop_table('reservation_fee_prices')
    op.drop_index(op.f('ix_rate_limit_rules_id'), table_name='rate_limit_rules')
    op.drop_table('rate_limit_rules')
    op.drop_index(op.f('ix_parking_prices_station_id'), table_name='parking_prices')
    op.drop_index(op.f('ix_parking_prices_expire_date'), table_name='parking_prices')
    op.drop_index(op.f('ix_parking_prices_effective_date'), table_name='parking_prices')
    op.drop_index('idx_pp_station', table_name='parking_prices')
    op.drop_index('idx_pp_effective', table_name='parking_prices')
    op.drop_index('idx_pp_active', table_name='parking_prices')
    op.drop_table('parking_prices')
    op.drop_index(op.f('ix_on_call_rules_id'), table_name='on_call_rules')
    op.drop_table('on_call_rules')
    op.drop_index(op.f('ix_occupancy_fee_prices_station_id'), table_name='occupancy_fee_prices')
    op.drop_index(op.f('ix_occupancy_fee_prices_expire_date'), table_name='occupancy_fee_prices')
    op.drop_index(op.f('ix_occupancy_fee_prices_effective_date'), table_name='occupancy_fee_prices')
    op.drop_index('idx_ofp_station', table_name='occupancy_fee_prices')
    op.drop_index('idx_ofp_effective', table_name='occupancy_fee_prices')
    op.drop_index('idx_ofp_active', table_name='occupancy_fee_prices')
    op.drop_table('occupancy_fee_prices')
    op.drop_index(op.f('ix_oauth_authorization_codes_id'), table_name='oauth_authorization_codes')
    op.drop_table('oauth_authorization_codes')
    op.drop_index(op.f('ix_inspection_tasks_id'), table_name='inspection_tasks')
    op.drop_table('inspection_tasks')
    op.drop_index(op.f('ix_gateway_api_keys_key_id'), table_name='gateway_api_keys')
    op.drop_table('gateway_api_keys')
    op.drop_index(op.f('ix_fleet_settlement_bills_bill_no'), table_name='fleet_settlement_bills')
    op.drop_index('idx_fsb_status', table_name='fleet_settlement_bills')
    op.drop_index('idx_fsb_period', table_name='fleet_settlement_bills')
    op.drop_index('idx_fsb_enterprise', table_name='fleet_settlement_bills')
    op.drop_table('fleet_settlement_bills')
    op.drop_index('idx_fcp_enterprise', table_name='fleet_charging_policies')
    op.drop_index('idx_fcp_enable', table_name='fleet_charging_policies')
    op.drop_table('fleet_charging_policies')
    op.drop_index(op.f('ix_fleet_carbon_certificates_summary_id'), table_name='fleet_carbon_certificates')
    op.drop_index(op.f('ix_fleet_carbon_certificates_status'), table_name='fleet_carbon_certificates')
    op.drop_index(op.f('ix_fleet_carbon_certificates_enterprise_id'), table_name='fleet_carbon_certificates')
    op.drop_index(op.f('ix_fleet_carbon_certificates_certificate_no'), table_name='fleet_carbon_certificates')
    op.drop_index('idx_fcc_summary', table_name='fleet_carbon_certificates')
    op.drop_index('idx_fcc_enterprise_status', table_name='fleet_carbon_certificates')
    op.drop_table('fleet_carbon_certificates')
    op.drop_index(op.f('ix_fleet_alert_rules_rule_type'), table_name='fleet_alert_rules')
    op.drop_index(op.f('ix_fleet_alert_rules_enterprise_id'), table_name='fleet_alert_rules')
    op.drop_index('idx_far_enterprise_type', table_name='fleet_alert_rules')
    op.drop_table('fleet_alert_rules')
    op.drop_index('idx_ev_vin', table_name='enterprise_vehicles')
    op.drop_index('idx_ev_plate', table_name='enterprise_vehicles')
    op.drop_index('idx_ev_enterprise', table_name='enterprise_vehicles')
    op.drop_index('idx_ev_approval', table_name='enterprise_vehicles')
    op.drop_table('enterprise_vehicles')
    op.drop_index(op.f('ix_enterprise_stations_station_id'), table_name='enterprise_stations')
    op.drop_index(op.f('ix_enterprise_stations_enterprise_id'), table_name='enterprise_stations')
    op.drop_index('idx_enterprise_station_unique', table_name='enterprise_stations')
    op.drop_table('enterprise_stations')
    op.drop_index('idx_era_status', table_name='enterprise_recharge_applications')
    op.drop_index('idx_era_enterprise', table_name='enterprise_recharge_applications')
    op.drop_table('enterprise_recharge_applications')
    op.drop_index(op.f('ix_energy_prices_station_id'), table_name='energy_prices')
    op.drop_index(op.f('ix_energy_prices_slot_id'), table_name='energy_prices')
    op.drop_index(op.f('ix_energy_prices_expire_date'), table_name='energy_prices')
    op.drop_index(op.f('ix_energy_prices_effective_date'), table_name='energy_prices')
    op.drop_index('idx_ep_station_slot', table_name='energy_prices')
    op.drop_index('idx_ep_effective', table_name='energy_prices')
    op.drop_index('idx_ep_active', table_name='energy_prices')
    op.drop_table('energy_prices')
    op.drop_index(op.f('ix_digital_twin_scenes_station_id'), table_name='digital_twin_scenes')
    op.drop_index(op.f('ix_digital_twin_scenes_id'), table_name='digital_twin_scenes')
    op.drop_table('digital_twin_scenes')
    op.drop_index(op.f('ix_devices_type'), table_name='devices')
    op.drop_index(op.f('ix_devices_station_id'), table_name='devices')
    op.drop_index(op.f('ix_devices_sn'), table_name='devices')
    op.drop_index(op.f('ix_devices_protocol_type'), table_name='devices')
    op.drop_index(op.f('ix_devices_name'), table_name='devices')
    op.drop_index(op.f('ix_devices_id'), table_name='devices')
    op.drop_index(op.f('ix_devices_code'), table_name='devices')
    op.drop_table('devices')
    op.drop_index(op.f('ix_api_usage_quotas_id'), table_name='api_usage_quotas')
    op.drop_table('api_usage_quotas')
    op.drop_index(op.f('ix_api_key_usage_logs_id'), table_name='api_key_usage_logs')
    op.drop_index(op.f('ix_api_key_usage_logs_api_key_id'), table_name='api_key_usage_logs')
    op.drop_index('idx_api_usage_path', table_name='api_key_usage_logs')
    op.drop_index('idx_api_usage_key', table_name='api_key_usage_logs')
    op.drop_index('idx_api_usage_created', table_name='api_key_usage_logs')
    op.drop_table('api_key_usage_logs')
    op.drop_index(op.f('ix_webhook_deliveries_webhook_id'), table_name='webhook_deliveries')
    op.drop_index('idx_delivery_webhook', table_name='webhook_deliveries')
    op.drop_index('idx_delivery_status', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')
    op.drop_index(op.f('ix_vehicles_tenant_id'), table_name='vehicles')
    op.drop_index(op.f('ix_vehicles_plate_number'), table_name='vehicles')
    op.drop_index(op.f('ix_vehicles_id'), table_name='vehicles')
    op.drop_index(op.f('ix_vehicles_driver_id'), table_name='vehicles')
    op.drop_table('vehicles')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_third_party_integrations_id'), table_name='third_party_integrations')
    op.drop_table('third_party_integrations')
    op.drop_index(op.f('ix_tenant_configs_id'), table_name='tenant_configs')
    op.drop_index('idx_tenant_config', table_name='tenant_configs')
    op.drop_table('tenant_configs')
    op.drop_index(op.f('ix_tenant_audit_logs_id'), table_name='tenant_audit_logs')
    op.drop_index('idx_tenant_audit_user', table_name='tenant_audit_logs')
    op.drop_index('idx_tenant_audit_tenant', table_name='tenant_audit_logs')
    op.drop_index('idx_tenant_audit_created', table_name='tenant_audit_logs')
    op.drop_index('idx_tenant_audit_action', table_name='tenant_audit_logs')
    op.drop_table('tenant_audit_logs')
    op.drop_index(op.f('ix_stations_name'), table_name='stations')
    op.drop_index(op.f('ix_stations_id'), table_name='stations')
    op.drop_index(op.f('ix_stations_code'), table_name='stations')
    op.drop_table('stations')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_repair_guides_id'), table_name='repair_guides')
    op.drop_table('repair_guides')
    op.drop_index('ix_notification_logs_status_time', table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_status'), table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_receiver_id'), table_name='notification_logs')
    op.drop_index('ix_notification_logs_receiver', table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_id'), table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_event_type'), table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_event_id'), table_name='notification_logs')
    op.drop_index('ix_notification_logs_event', table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_config_id'), table_name='notification_logs')
    op.drop_index(op.f('ix_notification_logs_channel'), table_name='notification_logs')
    op.drop_table('notification_logs')
    op.drop_index(op.f('ix_knowledge_faq_question'), table_name='knowledge_faq')
    op.drop_index(op.f('ix_knowledge_faq_id'), table_name='knowledge_faq')
    op.drop_index(op.f('ix_knowledge_faq_category'), table_name='knowledge_faq')
    op.drop_table('knowledge_faq')
    op.drop_index(op.f('ix_knowledge_articles_title'), table_name='knowledge_articles')
    op.drop_index(op.f('ix_knowledge_articles_id'), table_name='knowledge_articles')
    op.drop_index(op.f('ix_knowledge_articles_category'), table_name='knowledge_articles')
    op.drop_table('knowledge_articles')
    op.drop_index(op.f('ix_inspection_plans_id'), table_name='inspection_plans')
    op.drop_table('inspection_plans')
    op.drop_index(op.f('ix_enterprises_owner_team_id'), table_name='enterprises')
    op.drop_index('idx_enterprise_status', table_name='enterprises')
    op.drop_index('idx_enterprise_owner_team', table_name='enterprises')
    op.drop_index('idx_enterprise_code', table_name='enterprises')
    op.drop_table('enterprises')
    op.drop_index(op.f('ix_charging_schedule_entries_vehicle_id'), table_name='charging_schedule_entries')
    op.drop_index(op.f('ix_charging_schedule_entries_plan_id'), table_name='charging_schedule_entries')
    op.drop_index('idx_cse_vehicle', table_name='charging_schedule_entries')
    op.drop_index('idx_cse_priority', table_name='charging_schedule_entries')
    op.drop_index('idx_cse_plan', table_name='charging_schedule_entries')
    op.drop_table('charging_schedule_entries')
    op.drop_index(op.f('ix_api_keys_user_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_tenant_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_id'), table_name='api_keys')
    op.drop_index('idx_api_key_user', table_name='api_keys')
    op.drop_index('idx_api_key_tenant', table_name='api_keys')
    op.drop_index('idx_api_key_active', table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_index(op.f('ix_api_endpoints_id'), table_name='api_endpoints')
    op.drop_table('api_endpoints')
    op.drop_index(op.f('ix_api_clients_id'), table_name='api_clients')
    op.drop_index(op.f('ix_api_clients_client_id'), table_name='api_clients')
    op.drop_table('api_clients')
    op.drop_index('idx_webhook_enabled', table_name='webhooks')
    op.drop_table('webhooks')
    op.drop_index(op.f('ix_vin_users_vin'), table_name='vin_users')
    op.drop_index(op.f('ix_vin_users_user_id'), table_name='vin_users')
    op.drop_index(op.f('ix_vin_users_plate_number'), table_name='vin_users')
    op.drop_index('idx_vin_user_vin', table_name='vin_users')
    op.drop_index('idx_vin_user_user_id', table_name='vin_users')
    op.drop_index('idx_vin_user_plate', table_name='vin_users')
    op.drop_table('vin_users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_phone'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_upgrade_tasks_id'), table_name='upgrade_tasks')
    op.drop_table('upgrade_tasks')
    op.drop_index('idx_tsd_period', table_name='time_slot_definitions')
    op.drop_index('idx_tsd_active', table_name='time_slot_definitions')
    op.drop_table('time_slot_definitions')
    op.drop_index('idx_terminal_type', table_name='terminals')
    op.drop_index('idx_terminal_status', table_name='terminals')
    op.drop_index('idx_terminal_station', table_name='terminals')
    op.drop_table('terminals')
    op.drop_index(op.f('ix_tenants_id'), table_name='tenants')
    op.drop_index('idx_tenant_status', table_name='tenants')
    op.drop_index('idx_tenant_code', table_name='tenants')
    op.drop_table('tenants')
    op.drop_index(op.f('ix_teams_name'), table_name='teams')
    op.drop_index(op.f('ix_teams_id'), table_name='teams')
    op.drop_index(op.f('ix_teams_code'), table_name='teams')
    op.drop_table('teams')
    op.drop_index(op.f('ix_station_daily_metrics_station_id'), table_name='station_daily_metrics')
    op.drop_index(op.f('ix_station_daily_metrics_record_date'), table_name='station_daily_metrics')
    op.drop_index('idx_sdm_station_date', table_name='station_daily_metrics')
    op.drop_index('idx_sdm_station', table_name='station_daily_metrics')
    op.drop_index('idx_sdm_date', table_name='station_daily_metrics')
    op.drop_table('station_daily_metrics')
    op.drop_index(op.f('ix_ssl_certificates_id'), table_name='ssl_certificates')
    op.drop_index(op.f('ix_ssl_certificates_domain'), table_name='ssl_certificates')
    op.drop_table('ssl_certificates')
    op.drop_index(op.f('ix_sms_verification_codes_phone'), table_name='sms_verification_codes')
    op.drop_index(op.f('ix_sms_verification_codes_id'), table_name='sms_verification_codes')
    op.drop_index('ix_sms_phone_purpose_used', table_name='sms_verification_codes')
    op.drop_index('ix_sms_expires_at', table_name='sms_verification_codes')
    op.drop_table('sms_verification_codes')
    op.drop_index(op.f('ix_runbook_executions_station_id'), table_name='runbook_executions')
    op.drop_index(op.f('ix_runbook_executions_runbook_id'), table_name='runbook_executions')
    op.drop_index(op.f('ix_runbook_executions_id'), table_name='runbook_executions')
    op.drop_index(op.f('ix_runbook_executions_device_id'), table_name='runbook_executions')
    op.drop_index(op.f('ix_runbook_executions_alarm_id'), table_name='runbook_executions')
    op.drop_table('runbook_executions')
    op.drop_index(op.f('ix_runbook_approvals_runbook_id'), table_name='runbook_approvals')
    op.drop_index(op.f('ix_runbook_approvals_id'), table_name='runbook_approvals')
    op.drop_index(op.f('ix_runbook_approvals_alarm_id'), table_name='runbook_approvals')
    op.drop_table('runbook_approvals')
    op.drop_index(op.f('ix_runbook_approval_logs_id'), table_name='runbook_approval_logs')
    op.drop_index(op.f('ix_runbook_approval_logs_approval_id'), table_name='runbook_approval_logs')
    op.drop_table('runbook_approval_logs')
    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_index(op.f('ix_roles_id'), table_name='roles')
    op.drop_table('roles')
    op.drop_index(op.f('ix_revenue_daily_user_type'), table_name='revenue_daily')
    op.drop_index(op.f('ix_revenue_daily_station_id'), table_name='revenue_daily')
    op.drop_index(op.f('ix_revenue_daily_record_date'), table_name='revenue_daily')
    op.drop_index('idx_rev_user_type', table_name='revenue_daily')
    op.drop_index('idx_rev_station', table_name='revenue_daily')
    op.drop_index('idx_rev_date', table_name='revenue_daily')
    op.drop_table('revenue_daily')
    op.drop_index('idx_rreport_type', table_name='regulatory_reports')
    op.drop_index('idx_rreport_status', table_name='regulatory_reports')
    op.drop_index('idx_rreport_config', table_name='regulatory_reports')
    op.drop_table('regulatory_reports')
    op.drop_index(op.f('ix_refund_records_user_id'), table_name='refund_records')
    op.drop_index(op.f('ix_refund_records_order_id'), table_name='refund_records')
    op.drop_index('idx_rr_user', table_name='refund_records')
    op.drop_index('idx_rr_status', table_name='refund_records')
    op.drop_index('idx_rr_order', table_name='refund_records')
    op.drop_table('refund_records')
    op.drop_index('idx_pr_period', table_name='pricing_rules')
    op.drop_index('idx_pr_active', table_name='pricing_rules')
    op.drop_table('pricing_rules')
    op.drop_index('idx_price_disc_type', table_name='price_discounts')
    op.drop_index('idx_price_disc_priority', table_name='price_discounts')
    op.drop_index('idx_price_disc_active', table_name='price_discounts')
    op.drop_table('price_discounts')
    op.drop_index('idx_points_rule_type', table_name='points_rules')
    op.drop_index('idx_points_rule_active', table_name='points_rules')
    op.drop_table('points_rules')
    op.drop_index(op.f('ix_points_records_user_id'), table_name='points_records')
    op.drop_index(op.f('ix_points_records_rule_id'), table_name='points_records')
    op.drop_index(op.f('ix_points_records_order_id'), table_name='points_records')
    op.drop_index('idx_prec_user_id', table_name='points_records')
    op.drop_index('idx_prec_type', table_name='points_records')
    op.drop_index('idx_prec_created', table_name='points_records')
    op.drop_table('points_records')
    op.drop_index(op.f('ix_permissions_name'), table_name='permissions')
    op.drop_index(op.f('ix_permissions_id'), table_name='permissions')
    op.drop_table('permissions')
    op.drop_index(op.f('ix_payment_reconciliation_settlement_date'), table_name='payment_reconciliation')
    op.drop_index('idx_pr_status', table_name='payment_reconciliation')
    op.drop_index('idx_pr_date_channel', table_name='payment_reconciliation')
    op.drop_table('payment_reconciliation')
    op.drop_index(op.f('ix_parking_discounts_station_id'), table_name='parking_discounts')
    op.drop_index('idx_pd_station', table_name='parking_discounts')
    op.drop_index('idx_pd_active', table_name='parking_discounts')
    op.drop_table('parking_discounts')
    op.drop_index(op.f('ix_order_fee_items_order_id'), table_name='order_fee_items')
    op.drop_index('idx_ofi_type', table_name='order_fee_items')
    op.drop_index('idx_ofi_order', table_name='order_fee_items')
    op.drop_table('order_fee_items')
    op.drop_index(op.f('ix_order_charge_curves_order_id'), table_name='order_charge_curves')
    op.drop_index('idx_occ_order_time', table_name='order_charge_curves')
    op.drop_index('idx_occ_order', table_name='order_charge_curves')
    op.drop_table('order_charge_curves')
    op.drop_index('idx_oi_title', table_name='ops_invoices')
    op.drop_index('idx_oi_status', table_name='ops_invoices')
    op.drop_index('idx_oi_apply_time', table_name='ops_invoices')
    op.drop_table('ops_invoices')
    op.drop_index(op.f('ix_notification_templates_id'), table_name='notification_templates')
    op.drop_index(op.f('ix_notification_templates_event_type'), table_name='notification_templates')
    op.drop_index(op.f('ix_notification_templates_code'), table_name='notification_templates')
    op.drop_index(op.f('ix_notification_templates_channel'), table_name='notification_templates')
    op.drop_table('notification_templates')
    op.drop_index(op.f('ix_notification_rules_level'), table_name='notification_rules')
    op.drop_index(op.f('ix_notification_rules_id'), table_name='notification_rules')
    op.drop_table('notification_rules')
    op.drop_index(op.f('ix_notification_configs_scope_id'), table_name='notification_configs')
    op.drop_index('ix_notification_configs_scope', table_name='notification_configs')
    op.drop_index(op.f('ix_notification_configs_id'), table_name='notification_configs')
    op.drop_index('ix_notification_configs_enabled', table_name='notification_configs')
    op.drop_table('notification_configs')
    op.drop_index('idx_msuperstatus', table_name='municipal_supervision_configs')
    op.drop_index('idx_msupercity', table_name='municipal_supervision_configs')
    op.drop_table('municipal_supervision_configs')
    op.drop_index(op.f('ix_ml_models_model_type'), table_name='ml_models')
    op.drop_index(op.f('ix_ml_models_model_name'), table_name='ml_models')
    op.drop_index(op.f('ix_ml_models_is_active'), table_name='ml_models')
    op.drop_index(op.f('ix_ml_models_id'), table_name='ml_models')
    op.drop_table('ml_models')
    op.drop_index(op.f('ix_knowledge_categories_name'), table_name='knowledge_categories')
    op.drop_index(op.f('ix_knowledge_categories_id'), table_name='knowledge_categories')
    op.drop_table('knowledge_categories')
    op.drop_index(op.f('ix_invoice_titles_user_id'), table_name='invoice_titles')
    op.drop_index('idx_it_user', table_name='invoice_titles')
    op.drop_index('idx_it_type', table_name='invoice_titles')
    op.drop_table('invoice_titles')
    op.drop_index(op.f('ix_invoice_platform_configs_team_id'), table_name='invoice_platform_configs')
    op.drop_index('idx_ipc_team_enabled', table_name='invoice_platform_configs')
    op.drop_index('idx_ipc_team_default', table_name='invoice_platform_configs')
    op.drop_index('idx_ipc_team', table_name='invoice_platform_configs')
    op.drop_table('invoice_platform_configs')
    op.drop_index(op.f('ix_interconnect_users_platform_id'), table_name='interconnect_users')
    op.drop_index(op.f('ix_interconnect_users_outer_user_id'), table_name='interconnect_users')
    op.drop_index('idx_iuser_platform', table_name='interconnect_users')
    op.drop_index('idx_iuser_outer', table_name='interconnect_users')
    op.drop_table('interconnect_users')
    op.drop_index('idx_is_status', table_name='interconnect_settlements')
    op.drop_index('idx_is_platform', table_name='interconnect_settlements')
    op.drop_index('idx_is_period', table_name='interconnect_settlements')
    op.drop_table('interconnect_settlements')
    op.drop_index(op.f('ix_interconnect_platforms_platform_code'), table_name='interconnect_platforms')
    op.drop_index('idx_iplat_status', table_name='interconnect_platforms')
    op.drop_index('idx_iplat_code', table_name='interconnect_platforms')
    op.drop_table('interconnect_platforms')
    op.drop_index('idx_iorder_status', table_name='interconnect_orders')
    op.drop_index('idx_iorder_platform', table_name='interconnect_orders')
    op.drop_index('idx_iorder_outer', table_name='interconnect_orders')
    op.drop_table('interconnect_orders')
    op.drop_index('idx_iconfig_status', table_name='interconnect_configs')
    op.drop_index('idx_iconfig_code', table_name='interconnect_configs')
    op.drop_table('interconnect_configs')
    op.drop_index(op.f('ix_healing_rules_id'), table_name='healing_rules')
    op.drop_table('healing_rules')
    op.drop_index(op.f('ix_healing_executions_status'), table_name='healing_executions')
    op.drop_index(op.f('ix_healing_executions_station_id'), table_name='healing_executions')
    op.drop_index(op.f('ix_healing_executions_rule_id'), table_name='healing_executions')
    op.drop_index(op.f('ix_healing_executions_id'), table_name='healing_executions')
    op.drop_index(op.f('ix_healing_executions_device_id'), table_name='healing_executions')
    op.drop_index(op.f('ix_healing_executions_alarm_id'), table_name='healing_executions')
    op.drop_table('healing_executions')
    op.drop_index(op.f('ix_gateways_station_id'), table_name='gateways')
    op.drop_index(op.f('ix_gateways_sn'), table_name='gateways')
    op.drop_index(op.f('ix_gateways_id'), table_name='gateways')
    op.drop_table('gateways')
    op.drop_index(op.f('ix_gateway_sn_sn'), table_name='gateway_sn')
    op.drop_index(op.f('ix_gateway_sn_id'), table_name='gateway_sn')
    op.drop_table('gateway_sn')
    op.drop_index(op.f('ix_firmware_id'), table_name='firmware')
    op.drop_table('firmware')
    op.drop_index(op.f('ix_fault_codes_id'), table_name='fault_codes')
    op.drop_index(op.f('ix_fault_codes_fault_code'), table_name='fault_codes')
    op.drop_index(op.f('ix_fault_codes_fault_category'), table_name='fault_codes')
    op.drop_index(op.f('ix_fault_codes_device_type'), table_name='fault_codes')
    op.drop_table('fault_codes')
    op.drop_index(op.f('ix_enterprise_sub_users_user_id'), table_name='enterprise_sub_users')
    op.drop_index(op.f('ix_enterprise_sub_users_enterprise_id'), table_name='enterprise_sub_users')
    op.drop_index('idx_esub_user', table_name='enterprise_sub_users')
    op.drop_index('idx_esub_enterprise', table_name='enterprise_sub_users')
    op.drop_table('enterprise_sub_users')
    op.drop_index(op.f('ix_enterprise_accounts_credit_code'), table_name='enterprise_accounts')
    op.drop_index('idx_eacct_status', table_name='enterprise_accounts')
    op.drop_index('idx_eacct_credit_code', table_name='enterprise_accounts')
    op.drop_table('enterprise_accounts')
    op.drop_index(op.f('ix_discount_groups_user_type'), table_name='discount_groups')
    op.drop_index(op.f('ix_discount_groups_discount_id'), table_name='discount_groups')
    op.drop_index('idx_dg_user_type', table_name='discount_groups')
    op.drop_index('idx_dg_discount_id', table_name='discount_groups')
    op.drop_index('idx_dg_active', table_name='discount_groups')
    op.drop_table('discount_groups')
    op.drop_index(op.f('ix_diagnosis_rules_id'), table_name='diagnosis_rules')
    op.drop_table('diagnosis_rules')
    op.drop_index(op.f('ix_daily_settlements_station_id'), table_name='daily_settlements')
    op.drop_index(op.f('ix_daily_settlements_settlement_date'), table_name='daily_settlements')
    op.drop_index('idx_ds_status', table_name='daily_settlements')
    op.drop_index('idx_ds_date_station', table_name='daily_settlements')
    op.drop_table('daily_settlements')
    op.drop_index('idx_coupon_type', table_name='coupons')
    op.drop_index('idx_coupon_time', table_name='coupons')
    op.drop_index('idx_coupon_active', table_name='coupons')
    op.drop_table('coupons')
    op.drop_index(op.f('ix_coupon_usages_user_id'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_order_id'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_coupon_id'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_coupon_code'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_batch_id'), table_name='coupon_usages')
    op.drop_index('idx_cu_user_id', table_name='coupon_usages')
    op.drop_index('idx_cu_status', table_name='coupon_usages')
    op.drop_index('idx_cu_expires', table_name='coupon_usages')
    op.drop_table('coupon_usages')
    op.drop_index(op.f('ix_coupon_batches_coupon_id'), table_name='coupon_batches')
    op.drop_index('idx_cb_coupon_id', table_name='coupon_batches')
    op.drop_table('coupon_batches')
    op.drop_index(op.f('ix_coupon_activity_stats_coupon_id'), table_name='coupon_activity_stats')
    op.drop_index('idx_cas_coupon', table_name='coupon_activity_stats')
    op.drop_table('coupon_activity_stats')
    op.drop_index('idx_cca_result', table_name='compliance_checks')
    op.drop_index('idx_cca_config', table_name='compliance_checks')
    op.drop_table('compliance_checks')
    op.drop_index(op.f('ix_code_sequences_key'), table_name='code_sequences')
    op.drop_table('code_sequences')
    op.drop_index('idx_cloud_sync', table_name='cloud_configs')
    op.drop_index('idx_cloud_status', table_name='cloud_configs')
    op.drop_index('idx_cloud_provider', table_name='cloud_configs')
    op.drop_table('cloud_configs')
    op.drop_index(op.f('ix_charging_schedule_rules_enterprise_id'), table_name='charging_schedule_rules')
    op.drop_index(op.f('ix_charging_schedule_rules_created_at'), table_name='charging_schedule_rules')
    op.drop_index('idx_csr_type', table_name='charging_schedule_rules')
    op.drop_index('idx_csr_enterprise', table_name='charging_schedule_rules')
    op.drop_table('charging_schedule_rules')
    op.drop_index(op.f('ix_charging_schedule_plans_enterprise_id'), table_name='charging_schedule_plans')
    op.drop_index(op.f('ix_charging_schedule_plans_created_at'), table_name='charging_schedule_plans')
    op.drop_index('idx_csp_status', table_name='charging_schedule_plans')
    op.drop_index('idx_csp_plan_date', table_name='charging_schedule_plans')
    op.drop_index('idx_csp_enterprise', table_name='charging_schedule_plans')
    op.drop_table('charging_schedule_plans')
    op.drop_index(op.f('ix_charging_queues_vehicle_id'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_status'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_station_id'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_rule_id'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_enterprise_id'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_created_at'), table_name='charging_queues')
    op.drop_index(op.f('ix_charging_queues_arrival_time'), table_name='charging_queues')
    op.drop_index('idx_cq_vehicle', table_name='charging_queues')
    op.drop_index('idx_cq_status', table_name='charging_queues')
    op.drop_index('idx_cq_station', table_name='charging_queues')
    op.drop_index('idx_cq_rule', table_name='charging_queues')
    op.drop_index('idx_cq_priority', table_name='charging_queues')
    op.drop_index('idx_cq_arrival', table_name='charging_queues')
    op.drop_table('charging_queues')
    op.drop_index(op.f('ix_charging_queue_rules_station_id'), table_name='charging_queue_rules')
    op.drop_index(op.f('ix_charging_queue_rules_enterprise_id'), table_name='charging_queue_rules')
    op.drop_index(op.f('ix_charging_queue_rules_created_at'), table_name='charging_queue_rules')
    op.drop_index('idx_cqr_name', table_name='charging_queue_rules')
    op.drop_index('idx_cqr_enterprise', table_name='charging_queue_rules')
    op.drop_table('charging_queue_rules')
    op.drop_index(op.f('ix_charging_orders_user_id'), table_name='charging_orders')
    op.drop_index(op.f('ix_charging_orders_station_id'), table_name='charging_orders')
    op.drop_index(op.f('ix_charging_orders_order_no'), table_name='charging_orders')
    op.drop_index(op.f('ix_charging_orders_device_id'), table_name='charging_orders')
    op.drop_index('idx_co_user', table_name='charging_orders')
    op.drop_index('idx_co_status', table_name='charging_orders')
    op.drop_index('idx_co_station', table_name='charging_orders')
    op.drop_index('idx_co_order_no', table_name='charging_orders')
    op.drop_index('idx_co_device', table_name='charging_orders')
    op.drop_index('idx_co_created', table_name='charging_orders')
    op.drop_table('charging_orders')
    op.drop_index(op.f('ix_card_users_user_id'), table_name='card_users')
    op.drop_index(op.f('ix_card_users_card_no'), table_name='card_users')
    op.drop_index(op.f('ix_card_users_bind_phone'), table_name='card_users')
    op.drop_index('idx_card_user_user_id', table_name='card_users')
    op.drop_index('idx_card_user_phone', table_name='card_users')
    op.drop_index('idx_card_user_card_no', table_name='card_users')
    op.drop_table('card_users')
    op.drop_index('idx_crs_enterprise_year_month', table_name='carbon_reduction_summary')
    op.drop_table('carbon_reduction_summary')
    op.drop_index('idx_crr_vehicle_date', table_name='carbon_reduction_records')
    op.drop_index('idx_crr_enterprise_date', table_name='carbon_reduction_records')
    op.drop_table('carbon_reduction_records')
    op.drop_index('idx_cef_year_region_type', table_name='carbon_emission_factors')
    op.drop_table('carbon_emission_factors')
    op.drop_index(op.f('ix_audit_logs_username'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_timestamp'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_module'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_app_users_user_id'), table_name='app_users')
    op.drop_index(op.f('ix_app_users_phone'), table_name='app_users')
    op.drop_index('idx_app_user_user_id', table_name='app_users')
    op.drop_index('idx_app_user_status', table_name='app_users')
    op.drop_index('idx_app_user_phone', table_name='app_users')
    op.drop_table('app_users')
    op.drop_index(op.f('ix_alarm_rules_name'), table_name='alarm_rules')
    op.drop_index(op.f('ix_alarm_rules_id'), table_name='alarm_rules')
    op.drop_index(op.f('ix_alarm_rules_device_type'), table_name='alarm_rules')
    op.drop_table('alarm_rules')
    # ### end Alembic commands ###

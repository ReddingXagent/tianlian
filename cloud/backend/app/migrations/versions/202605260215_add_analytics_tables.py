"""add analytics tables

Revision ID: 202605260215
Revises: 
Create Date: 2026-05-26 02:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '202605260215'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建分析结果表
    op.create_table('analytics_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=True),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analytics_results_analysis_type'), 'analytics_results', ['analysis_type'], unique=False)
    op.create_index(op.f('ix_analytics_results_device_id'), 'analytics_results', ['device_id'], unique=False)
    op.create_index(op.f('ix_analytics_results_generated_at'), 'analytics_results', ['generated_at'], unique=False)
    
    # 创建模型训练记录表
    op.create_table('ml_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('performance_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trained_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ml_models_model_name'), 'ml_models', ['model_name'], unique=False)
    op.create_index(op.f('ix_ml_models_model_type'), 'ml_models', ['model_type'], unique=False)
    op.create_index(op.f('ix_ml_models_is_active'), 'ml_models', ['is_active'], unique=False)
    
    # 创建预测告警表
    op.create_table('prediction_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('predicted_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('suggested_action', sa.Text(), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_alerts_alert_type'), 'prediction_alerts', ['alert_type'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_device_id'), 'prediction_alerts', ['device_id'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_severity'), 'prediction_alerts', ['severity'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_created_at'), 'prediction_alerts', ['created_at'], unique=False)
    op.create_index(op.f('ix_prediction_alerts_acknowledged'), 'prediction_alerts', ['acknowledged'], unique=False)
    
    # 创建设备健康度历史表
    op.create_table('device_health_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('health_score', sa.Float(), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('component_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('maintenance_recommendations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_health_history_device_id'), 'device_health_history', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_healthhealth_history_calculated_at'), 'device_health_history', ['calculated_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_device_healthhealth_history_calculated_at'), table_name='device_health_history')
    op.drop_index(op.f('ix_device_health_history_device_id'), table_name='device_health_history')
    op.drop_table('device_health_history')
    
    op.drop_index(op.f('ix_prediction_alerts_acknowledged'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_created_at'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_severity'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_device_id'), table_name='prediction_alerts')
    op.drop_index(op.f('ix_prediction_alerts_alert_type'), table_name='prediction_alerts')
    op.drop_table('prediction_alerts')
    
    op.drop_index(op.f('ix_ml_models_is_active'), table_name='ml_models')
    op.drop_index(op.f('ix_ml_models_model_type'), table_name='ml_models')
    op.drop_index(op.f('ix_ml_models_model_name'), table_name='ml_models')
    op.drop_table('ml_models')
    
    op.drop_index(op.f('ix_analytics_results_generated_at'), table_name='analytics_results')
    op.drop_index(op.f('ix_analytics_results_device_id'), table_name='analytics_results')
    op.drop_index(op.f('ix_analytics_results_analysis_type'), table_name='analytics_results')
    op.drop_table('analytics_results')
"""热点表索引存在性验证 (卡 3839b256)

用 SQLite PRAGMA index_list 验证模型层声明 + create_all 实际落库的索引。
SQLite 会为 index=True / Index(...) 全部创建, 与生产 Postgres 语义一致
(索引名由 SQLAlchemy 统一生成)。
"""
from sqlalchemy import create_engine, text

from app.core.database import Base
import app.models  # noqa: F401  确保所有模型注册到 metadata


def _make_engine(*tables: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine, tables=[Base.metadata.tables[t] for t in tables]
    )
    return engine


def _index_names(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA index_list({table})"))}


def _index_columns(engine, index: str) -> list[str]:
    with engine.connect() as conn:
        return [row[2] for row in conn.execute(text(f"PRAGMA index_info({index})"))]


def test_telemetry_composite_index():
    engine = _make_engine("telemetry")
    assert "ix_telemetry_device_ts" in _index_names(engine, "telemetry")
    # 复合索引列序: device_id 在前
    assert _index_columns(engine, "ix_telemetry_device_ts") == ["device_id", "timestamp"]


def test_enterprise_transaction_indexes():
    engine = _make_engine("enterprise_transactions")
    idx = _index_names(engine, "enterprise_transactions")
    assert "ix_enterprise_transactions_enterprise_id" in idx
    assert "ix_enterprise_transactions_vehicle_id" in idx


def test_telemetry_v2_family_fk_indexes():
    engine = _make_engine("telemetry_pv", "telemetry_battery", "telemetry_charger")
    for table in ("telemetry_pv", "telemetry_battery", "telemetry_charger"):
        idx = _index_names(engine, table)
        assert f"ix_{table}_device_id" in idx, table
        assert f"ix_{table}_station_id" in idx, table


def test_p1_hot_table_fk_indexes():
    """P1 次热表 FK 索引 (卡 f1c99ce5): 模型声明 + create_all 落库验证。"""
    expect = {
        "api_request_logs": ["ix_api_request_logs_client_id", "ix_api_request_logs_api_key_id"],
        "device_health_records": ["ix_device_health_records_device_id"],
        "device_efficiency_logs": ["ix_device_efficiency_logs_device_id", "ix_device_efficiency_logs_station_id"],
        "occupancy_events": ["ix_occupancy_events_station_id"],
        "fund_pool_transactions": ["idx_fund_txn_pool", "ix_fund_pool_transactions_fund_pool_id"],
        "device_control_logs": ["ix_device_control_logs_device_id"],
        "enterprise_transactions": ["ix_enterprise_transactions_vehicle_id"],
    }
    engine = _make_engine(*expect.keys())
    for table, names in expect.items():
        idx = _index_names(engine, table)
        for name in names:
            assert name in idx, f"{table} 缺 {name}"

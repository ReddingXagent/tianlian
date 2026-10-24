"""卡 8b9f543a: device_health_records 补 created_at 索引.

模型 DeviceHealthRecord.created_at 原先零索引, 三个热点查询路径受损:
health_monitor.py 健康总览全局 ORDER BY created_at DESC LIMIT 20 (全表扫+top-N排序)、
diagnosis.py device_id+created_at>=N天 时间窗 (仅单列 device_id 索引)、
services/health.py group_by(device_id).max(created_at)+join 回查。

覆盖:
1. 结构: 表创建后 inspect 验证 ix_dhr_device_created/ix_dhr_created_at 存在且列正确。
2. 迁移文件存在且 down_revision 接在当前 head 202610051300 之后。
"""
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect

from app.models.device import DeviceHealthRecord


def _get_indexes(engine):
    return {i["name"]: i["column_names"] for i in inspect(engine).get_indexes("device_health_records")}


def test_indexes_exist_on_table_create():
    engine = create_engine("sqlite://")
    DeviceHealthRecord.__table__.create(engine)
    try:
        idx = _get_indexes(engine)
        assert idx.get("ix_dhr_device_created") == ["device_id", "created_at"]
        assert idx.get("ix_dhr_created_at") == ["created_at"]
    finally:
        engine.dispose()


def test_indexes_not_unique():
    engine = create_engine("sqlite://")
    DeviceHealthRecord.__table__.create(engine)
    try:
        idx = {i["name"]: i for i in inspect(engine).get_indexes("device_health_records")}
        assert not idx["ix_dhr_device_created"]["unique"]
        assert not idx["ix_dhr_created_at"]["unique"]
    finally:
        engine.dispose()


def test_migration_file_exists_and_chained():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions.glob("*dhr_created_at_indexes.py"))
    assert matches, "迁移文件缺失"
    text = matches[0].read_text(encoding="utf-8")
    assert re.search(r'revision:\s*str\s*=\s*"\d+"', text)
    assert 'down_revision' in text and '202610051300' in text
    # 幂等守卫: 表不存在双向早退
    assert 'has_table' in text
    # 不含数据/结构变更, 纯索引
    assert 'add_column' not in text and 'drop_column' not in text and 'create_table' not in text

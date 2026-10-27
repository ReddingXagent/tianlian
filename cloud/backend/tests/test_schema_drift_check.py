"""tests/test_schema_drift_check.py

单元测试 backend/scripts/check_schema_drift.py —— mock inspector, 不依赖真实 PG。
覆盖 5 路径: 无漂移 / 缺列 / 缺索引 / 孤儿列(仅报告) / 连接失败, 外加端到端 exit code 与
真实 app.models 全量 metadata smoke。
"""
import os
import importlib.util

import pytest
from sqlalchemy import MetaData, Table, Column, Integer, String, Index


def _load_script():
    """用 importlib 从文件路径加载脚本模块 (scripts/ 非 package, 无 __init__.py)。"""
    here = os.path.dirname(__file__)
    path = os.path.abspath(os.path.join(here, "..", "scripts", "check_schema_drift.py"))
    spec = importlib.util.spec_from_file_location("check_schema_drift", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def csd():
    return _load_script()


def _make_meta():
    """构造一份独立的小 metadata (不依赖 app.models), 含主键/匿名 index/显式 Index。"""
    md = MetaData()
    Table(
        "devices",
        md,
        Column("id", Integer, primary_key=True),     # 主键约束, 不算显式索引
        Column("name", String, index=True),           # 匿名 ix_devices_name
        Column("status", String),
    )
    Table(
        "alarms",
        md,
        Column("id", Integer, primary_key=True),
        Column("level", String),
        Column("station_id", Integer, index=True),    # 匿名 ix_alarms_station_id
        Index("idx_alarms_custom", "level"),          # 显式命名索引
    )
    return md


class FakeInspector:
    """基于一份 metadata 生成“匹配”的库结构, 允许通过参数制造漂移。

    - drop_columns: 库里删掉这些列 (→ 模型缺列)
    - extra_columns: 库里多出这些列 (→ 孤儿列)
    - drop_indexes: 库里删掉这些索引名 (→ 模型缺索引)
    - table_names: 覆盖库实际存在的表名集合 (→ 模拟缺表)
    """

    def __init__(self, metadata, *, drop_columns=None, extra_columns=None,
                 drop_indexes=None, table_names=None):
        self.metadata = metadata
        self.drop_columns = drop_columns or {}
        self.extra_columns = extra_columns or {}
        self.drop_indexes = drop_indexes or {}
        self._table_names = table_names

    def _has_table(self, table):
        return table in set(self.get_table_names())

    def get_table_names(self):
        if self._table_names is not None:
            return list(self._table_names)
        return list(self.metadata.tables.keys())

    def get_columns(self, table):
        if not self._has_table(table):
            return []
        tbl = self.metadata.tables[table]
        cols = [c.name for c in tbl.columns]
        for c in self.drop_columns.get(table, []):
            if c in cols:
                cols.remove(c)
        cols = list(cols) + list(self.extra_columns.get(table, []))
        return [{"name": c} for c in cols]

    def get_indexes(self, table):
        if not self._has_table(table):
            return []
        tbl = self.metadata.tables[table]
        names = [idx.name for idx in tbl.indexes if idx.name]
        for n in self.drop_indexes.get(table, []):
            if n in names:
                names.remove(n)
        return [{"name": n} for n in names]

    def get_pk_constraint(self, table):
        return {"name": None, "constrained_columns": []}

    def get_unique_constraints(self, table):
        return []


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeEngine:
    """配合 monkeypatch inspect → inspector 使用; connect() 仅返回占位 conn。"""

    def connect(self):
        return _FakeConn()


# ─── 5 路径 ──────────────────────────────────────────────────────────────────

def test_no_drift(csd):
    """路径1: 模型与库完全一致 → 无漂移。"""
    md = _make_meta()
    report = csd.detect_drift(FakeInspector(md), md)
    assert not report.has_blocking_drift()
    assert report.missing_columns == {}
    assert report.missing_indexes == {}
    assert report.orphan_columns == {}


def test_missing_column(csd):
    """路径2: 模型有/库无列 → 漂移。"""
    md = _make_meta()
    inspector = FakeInspector(md, drop_columns={"devices": ["status"]})
    report = csd.detect_drift(inspector, md)
    assert report.has_blocking_drift()
    assert report.missing_columns == {"devices": ["status"]}


def test_missing_index(csd):
    """路径3: 模型显式声明索引/库无 → 漂移; 主键约束索引不误报。"""
    md = _make_meta()
    inspector = FakeInspector(md, drop_indexes={"alarms": ["idx_alarms_custom"]})
    report = csd.detect_drift(inspector, md)
    assert report.has_blocking_drift()
    assert report.missing_indexes == {"alarms": ["idx_alarms_custom"]}


def test_orphan_column_not_blocking(csd):
    """路径4: 库有/模型无列 → 仅报告, 不算漂移 (exit 0)。"""
    md = _make_meta()
    inspector = FakeInspector(md, extra_columns={"devices": ["legacy_col"]})
    report = csd.detect_drift(inspector, md)
    assert not report.has_blocking_drift()
    assert report.orphan_columns == {"devices": ["legacy_col"]}
    text = csd.render_report(report, "sqlite:///fake")
    assert "legacy_col" in text          # 被报告
    assert "孤儿列" in text               # 标注为孤儿


def test_connection_failure_exit_2(csd, monkeypatch):
    """路径5: 连接失败 → exit 2。"""
    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(csd, "create_engine", boom)
    code, text = csd.run_check("postgresql://x:y@nonexistent:5432/db")
    assert code == 2
    assert "connection refused" in text


# ─── 端到端 exit code + 真实模型 smoke ────────────────────────────────────────

def test_run_check_missing_column_exit_1(csd, monkeypatch):
    """端到端: run_check 在缺列时返回 exit 1 且报告含列名。"""
    md = _make_meta()
    inspector = FakeInspector(md, drop_columns={"devices": ["status"]})
    monkeypatch.setattr(csd, "create_engine", lambda url: _FakeEngine())
    monkeypatch.setattr(csd, "inspect", lambda conn: inspector)
    code, text = csd.run_check("sqlite:///fake", metadata=md)
    assert code == 1
    assert "devices.status" in text


def test_smoke_real_app_models(csd):
    """smoke: 脚本能吃 app.models 全量 Base.metadata 且在匹配库下判无漂移。"""
    import app.models  # noqa: F401 — 触发全部模型注册
    from app.core.database import Base
    report = csd.detect_drift(FakeInspector(Base.metadata), Base.metadata)
    assert not report.has_blocking_drift()

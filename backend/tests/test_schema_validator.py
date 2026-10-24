"""
schema_validator 单元测试

验证启动时 schema 同步保障逻辑:
  - 缺表 → 自动 CREATE TABLE
  - 缺列（开发环境 sqlite）→ 自动 ALTER TABLE ADD COLUMN
  - 缺列（生产环境 postgres）→ 仅 WARNING，不改 schema
  - 永不抛异常（阻断启动）
"""
import pytest
from sqlalchemy import create_engine, Column, Integer, String, inspect as sa_inspect
from sqlalchemy.orm import declarative_base


def _sqlite_engine():
    """内存 SQLite，每次独立"""
    return create_engine("sqlite://", connect_args={"check_same_thread": False})


def test_missing_table_autocreate():
    """缺表 → 自动创建"""
    from app.utils.schema_validator import validate_schema

    Base = declarative_base()

    class Foo(Base):
        __tablename__ = "foo_auto_test"
        id = Column(Integer, primary_key=True)
        name = Column(String(32))

    eng = _sqlite_engine()
    # engine 上初始无任何表
    assert "foo_auto_test" not in sa_inspect(eng).get_table_names()

    res = validate_schema(eng, Base.metadata)

    assert "foo_auto_test" in res["created_tables"]
    assert "foo_auto_test" in sa_inspect(eng).get_table_names()


def test_missing_column_dev_autofix(monkeypatch):
    """缺列 + 开发环境 → 自动 ALTER ADD COLUMN"""
    import app.utils.schema_validator as sv
    # 强制 dev 模式（不依赖 .env 的 DB_TYPE）
    monkeypatch.setattr(sv, "DB_TYPE", "sqlite")

    from app.utils.schema_validator import validate_schema

    Base = declarative_base()

    class Bar(Base):
        __tablename__ = "bar_auto_test"
        id = Column(Integer, primary_key=True)

    eng = _sqlite_engine()
    Base.metadata.create_all(eng, tables=[Bar.__table__])
    # 模拟 model 新增列（DB 无）
    Base.metadata.tables["bar_auto_test"].append_column(Column("extra", String(32)))

    res = validate_schema(eng, Base.metadata)

    assert "bar_auto_test.extra" in res["added_columns"]
    db_cols = {c["name"] for c in sa_inspect(eng).get_columns("bar_auto_test")}
    assert "extra" in db_cols


def test_missing_column_prod_warning_only(monkeypatch):
    """缺列 + 生产环境(postgres) → 只 WARNING，不动 schema"""
    import app.utils.schema_validator as sv
    monkeypatch.setattr(sv, "DB_TYPE", "postgres")
    from app.utils.schema_validator import validate_schema

    Base = declarative_base()

    class Baz(Base):
        __tablename__ = "baz_prod_test"
        id = Column(Integer, primary_key=True)

    # 用 sqlite engine 但伪装 prod（DB_TYPE=postgres）
    eng = _sqlite_engine()
    Base.metadata.create_all(eng)
    Base.metadata.tables["baz_prod_test"].append_column(Column("newcol", String(16)))

    res = validate_schema(eng, Base.metadata)

    # 生产不应自动补列
    assert res["added_columns"] == []
    # 应产出 warning
    assert any("baz_prod_test.newcol" in w for w in res["warnings"])
    # DB 上确实没有 newcol
    db_cols = {c["name"] for c in sa_inspect(eng).get_columns("baz_prod_test")}
    assert "newcol" not in db_cols


def test_no_missing_returns_empty():
    """schema 完全一致 → 返回空结果"""
    from app.utils.schema_validator import validate_schema

    Base = declarative_base()

    class Quux(Base):
        __tablename__ = "quux_ok_test"
        id = Column(Integer, primary_key=True)
        v = Column(String(8))

    eng = _sqlite_engine()
    Base.metadata.create_all(eng)

    res = validate_schema(eng, Base.metadata)

    assert res["created_tables"] == []
    assert res["added_columns"] == []
    assert res["warnings"] == []


def test_never_raises_on_bad_engine():
    """engine 不可用 → 不抛异常，返回 warning"""
    from app.utils.schema_validator import validate_schema

    Base = declarative_base()

    class Dead(Base):
        __tablename__ = "dead_test"
        id = Column(Integer, primary_key=True)

    # 用一个 dispose 后无法连接的 engine
    eng = _sqlite_engine()
    eng.dispose()
    # 不抛
    res = validate_schema(eng, Base.metadata)
    assert isinstance(res, dict)

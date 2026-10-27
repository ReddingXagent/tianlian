"""全新库 alembic 迁移链回归测试 (卡 24698c70)。

baseline 0001 用 Base.metadata.create_all 建表 → 全新库已含全部列;
后续 add_column 迁移必须带幂等守卫 (与 0c60e5c087e0 一致) 否则
duplicate column 崩溃。本测试在 tmp_path 空 sqlite 库上跑完整
`upgrade head` 并断言到达动态解析的 head revision。
"""
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests._test_helpers import preserve_global_logging

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _resolve_head() -> str:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def test_fresh_db_upgrade_head_reaches_head(tmp_path, monkeypatch):
    db_file = tmp_path / "fresh.db"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_file}")

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    # [卡057c8a9e] preserve 包裹: env.py 的 fileConfig 会重配 root
    # (handlers=console, level=WARNING), 不恢复则跨测试残留 → 后续 caplog
    # 断言族消息缺失 (全量串行 34 红根因之一); disabled 面由 env.py 的
    # disable_existing_loggers=False 根治, 此处快照恢复兜底 root 与 logger level。
    with preserve_global_logging():
        command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        with engine.connect() as conn:
            version = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar()
    finally:
        engine.dispose()

    assert version == _resolve_head()


# ---- 卡 2520e93d: stations 5 列 + fleet_recharge_requests 2 索引 drift 回归 ----

_STATIONS_COLUMNS = {
    "contact_person": "VARCHAR",
    "contact_phone": "VARCHAR",
    "description": "TEXT",
    "pv_capacity": "FLOAT",
    "ess_capacity": "FLOAT",
}


def _fresh_upgrade_head(tmp_path, monkeypatch):
    db_file = tmp_path / "fresh.db"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_file}")
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    # [卡057c8a9e] 同 test_fresh_db_upgrade_head_reaches_head: preserve 包裹防
    # fileConfig 的 root 重配跨测试残留。
    with preserve_global_logging():
        command.upgrade(cfg, "head")
    return sa.create_engine(f"sqlite:///{db_file}")


def test_fresh_db_stations_has_contact_and_capacity_columns(tmp_path, monkeypatch):
    engine = _fresh_upgrade_head(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa.text("PRAGMA table_info(stations)")).fetchall()
    finally:
        engine.dispose()
    col_types = {r[1]: (r[2] or "").upper() for r in rows}
    for name, expected in _STATIONS_COLUMNS.items():
        assert name in col_types, f"stations 缺列 {name}: 现有 {sorted(col_types)}"
        assert col_types[name].startswith(expected), (
            f"stations.{name} 类型 {col_types[name]} != {expected}"
        )


def test_fresh_db_fleet_recharge_requests_ix_indexes(tmp_path, monkeypatch):
    engine = _fresh_upgrade_head(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            names = {
                r[1]
                for r in conn.execute(
                    sa.text("PRAGMA index_list(fleet_recharge_requests)")
                ).fetchall()
            }
    finally:
        engine.dispose()
    assert "ix_fleet_recharge_requests_enterprise_id" in names, sorted(names)
    assert "ix_fleet_recharge_requests_status" in names, sorted(names)

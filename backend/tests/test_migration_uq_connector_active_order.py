"""卡 71e2f120: uq_connector_active_order partial unique index 迁移落地测试.

模型 app/models/charging_order.py:120 早已声明该索引, 但迁移链从未落地 → 生产 PG
同枪并发建单防线 (卡 d9bba836 的 DB 级兜底) 实际不存在。本文件测试补齐迁移
(202608161500) 的四个面:

1. upgrade 收敛历史重复: 同 (device_id, connector_id) 多条 active 订单只留最新
   (MAX(id)), 其余置 CANCELLED + 固定 remark; 终态订单与 NULL connector 不动。
2. 索引真拦截: 同 connector 第二条 active INSERT 报 IntegrityError; 终态不受
   partial WHERE 限制; NULL connector 多条共存 (SQL 多 NULL 不冲突)。
3. WHERE 用枚举 name 大写 'PENDING'/'CHARGING' —— 用小写 value 会导致永不命中、
   索引形同虚设 (模型注释明示此坑, 卡 d9bba836)。
4. downgrade 反向 DROP INDEX; 索引已存在时 upgrade 幂等 (inspector 判存守卫)。

验证方法 = 迁移隔离验证 (记忆卡 93c1e2b95): 从空库跑全链 `upgrade head` 必败
(baseline create_all 与增量 ALTER 冲突是预存缺陷), 故只建 charging_orders 单表
(带模型全部索引) → DROP 目标索引模拟迁移前 → `alembic stamp` 前驱版本 →
`upgrade head` 仅执行本迁移。全部走 subprocess + ALEMBIC_DATABASE_URL env
override (alembic_url_resolver 优先级 1), 与生产 CLI 行为一致。
"""
import os
import subprocess
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect

from app.models.charging_order import ChargingOrder, OrderStatus

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ALEMBIC_INI = os.path.join(BACKEND_DIR, "alembic.ini")
DOWN_REV = "202608161400"  # 新迁移前驱 (隔离验证起点)
NEW_REV = "202608161500"  # 本迁移 (卡 71e2f120)
INDEX_NAME = "uq_connector_active_order"
REMARK = "迁移71e2f120收敛：partial unique index上线前清理重复active订单"


class MigrationDb:
    """隔离迁移验证库: 单表 + 目标索引摘除 + alembic CLI 包装。"""

    def __init__(self, db_path):
        self.url = f"sqlite:///{db_path}"
        engine = create_engine(self.url)
        ChargingOrder.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP INDEX {INDEX_NAME}"))
        engine.dispose()

    def alembic(self, *args):
        env = dict(os.environ, ALEMBIC_DATABASE_URL=self.url)
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    def seed(self, rows):
        """rows: [(device_id, connector_id, order_status, remark), ...] 逐条插, id 自增。"""
        engine = create_engine(self.url)
        with engine.begin() as conn:
            for i, (device_id, connector_id, status, remark) in enumerate(rows):
                conn.execute(
                    ChargingOrder.__table__.insert().values(
                        order_no=f"NO{i:04d}",
                        station_id=1,
                        device_id=device_id,
                        connector_id=connector_id,
                        order_status=status,
                        remark=remark,
                    )
                )
        engine.dispose()

    def scalar(self, sql):
        engine = create_engine(self.url)
        try:
            with engine.begin() as conn:
                return conn.execute(sa.text(sql)).scalar()
        finally:
            engine.dispose()

    def rows(self, sql):
        engine = create_engine(self.url)
        try:
            with engine.begin() as conn:
                return [dict(r._mapping) for r in conn.execute(sa.text(sql))]
        finally:
            engine.dispose()

    def execute(self, sql):
        engine = create_engine(self.url)
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(sql))
        finally:
            engine.dispose()

    def has_index(self):
        engine = create_engine(self.url)
        try:
            names = {
                i["name"]
                for i in inspect(engine).get_indexes("charging_orders")
            }
            return INDEX_NAME in names
        finally:
            engine.dispose()

    def index_is_unique(self):
        engine = create_engine(self.url)
        try:
            for i in inspect(engine).get_indexes("charging_orders"):
                if i["name"] == INDEX_NAME:
                    return bool(i["unique"])
            return False
        finally:
            engine.dispose()


@pytest.fixture()
def mig(tmp_path):
    """迁移前状态: 表在、索引无、版本标在前驱。"""
    db = MigrationDb(tmp_path / "mig.db")
    r = db.alembic("stamp", DOWN_REV)
    assert r.returncode == 0, r.stderr
    return db


def _upgrade(mig):
    r = mig.alembic("upgrade", "head")
    assert r.returncode == 0, r.stdout + r.stderr
    return r


class TestUpgradeConvergesDuplicates:
    def test_keeps_only_newest_active_per_connector(self, mig):
        mig.seed(
            [
                # 同 (1,1) 三条 active: id 1/2 应被收敛, id 3 (最新) 保留
                (1, 1, OrderStatus.PENDING, "历史备注A"),
                (1, 1, OrderStatus.CHARGING, None),
                (1, 1, OrderStatus.CHARGING, "最新单"),
                # 同 (1,2) 一条 active: 无重复, 原样保留
                (1, 2, OrderStatus.PENDING, None),
                # 同 (1,1) 的终态单: 不参与收敛, remark 不被覆盖
                (1, 1, OrderStatus.COMPLETED, "完工单"),
            ]
        )
        _upgrade(mig)

        rows = mig.rows(
            "SELECT id, order_status, remark FROM charging_orders "
            "ORDER BY id"
        )
        by_id = {r["id"]: r for r in rows}
        # id 1/2 收敛为 CANCELLED + 固定 remark
        assert by_id[1]["order_status"] == "CANCELLED"
        assert by_id[1]["remark"] == REMARK
        assert by_id[2]["order_status"] == "CANCELLED"
        assert by_id[2]["remark"] == REMARK
        # id 3 (最新 active) 原样保留
        assert by_id[3]["order_status"] == "CHARGING"
        assert by_id[3]["remark"] == "最新单"
        # id 4 无重复, id 5 终态不动
        assert by_id[4]["order_status"] == "PENDING"
        assert by_id[5]["order_status"] == "COMPLETED"
        assert by_id[5]["remark"] == "完工单"

    def test_null_connector_actives_untouched(self, mig):
        # SQL 多 NULL 不冲突 → 索引不约束 NULL connector, 收敛也不应动它们
        mig.seed(
            [
                (1, None, OrderStatus.PENDING, "n1"),
                (1, None, OrderStatus.CHARGING, "n2"),
            ]
        )
        _upgrade(mig)
        rows = mig.rows(
            "SELECT order_status, remark FROM charging_orders ORDER BY id"
        )
        assert all(r["order_status"] in ("PENDING", "CHARGING") for r in rows)
        assert rows[0]["remark"] == "n1"
        assert rows[1]["remark"] == "n2"

    def test_upgrade_is_a_noop_when_no_duplicates(self, mig):
        mig.seed([(1, 1, OrderStatus.PENDING, None), (2, 3, OrderStatus.CHARGING, None)])
        _upgrade(mig)
        assert mig.scalar("SELECT COUNT(*) FROM charging_orders") == 2
        assert mig.scalar(
            "SELECT COUNT(*) FROM charging_orders WHERE order_status = 'CANCELLED'"
        ) == 0


class TestIndexEnforcesUniqueness:
    def test_second_active_insert_on_same_connector_blocked(self, mig):
        mig.seed([(1, 5, OrderStatus.PENDING, None)])
        _upgrade(mig)
        with pytest.raises(sa.exc.IntegrityError):
            mig.execute(
                "INSERT INTO charging_orders (order_no, station_id, device_id, "
                "connector_id, order_status) VALUES ('DUP', 1, 1, 5, 'CHARGING')"
            )

    def test_terminal_status_insert_not_blocked(self, mig):
        # partial WHERE: 终态不参与唯一约束 → 同 connector 可并存终态单
        mig.seed([(1, 5, OrderStatus.CHARGING, None)])
        _upgrade(mig)
        mig.execute(
            "INSERT INTO charging_orders (order_no, station_id, device_id, "
            "connector_id, order_status) VALUES ('DONE', 1, 1, 5, 'COMPLETED')"
        )
        assert mig.scalar("SELECT COUNT(*) FROM charging_orders") == 2

    def test_null_connector_multiple_actives_allowed(self, mig):
        mig.seed([(1, None, OrderStatus.PENDING, None)])
        _upgrade(mig)
        mig.execute(
            "INSERT INTO charging_orders (order_no, station_id, device_id, "
            "connector_id, order_status) VALUES ('NULL2', 1, 1, NULL, 'PENDING')"
        )
        assert mig.scalar("SELECT COUNT(*) FROM charging_orders") == 2

    def test_where_clause_uses_enum_names_uppercase(self, mig):
        # 模型注释 (卡 d9bba836): WHERE 必须用枚举 name 大写; 小写 value 永不命中
        _upgrade(mig)
        sql = mig.scalar(
            f"SELECT sql FROM sqlite_master WHERE type='index' AND name='{INDEX_NAME}'"
        )
        assert sql, "索引未创建"
        assert "IN ('PENDING', 'CHARGING')" in sql
        assert "'pending'" not in sql and "'charging'" not in sql
        assert mig.index_is_unique()


class TestDowngradeAndIdempotency:
    def test_downgrade_drops_index(self, mig):
        _upgrade(mig)
        assert mig.has_index()
        r = mig.alembic("downgrade", DOWN_REV)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not mig.has_index()
        # 索引摘除后同枪第二条 active 可再插入 (反向可回滚的语义验证)
        mig.seed([(9, 9, OrderStatus.PENDING, None)])
        mig.execute(
            "INSERT INTO charging_orders (order_no, station_id, device_id, "
            "connector_id, order_status) VALUES ('DUP2', 1, 9, 9, 'PENDING')"
        )
        assert mig.scalar("SELECT COUNT(*) FROM charging_orders") == 2

    def test_upgrade_idempotent_when_index_already_exists(self, mig):
        # create_all 环境已带索引但版本未推进 (如手滑 stamp 错位): inspector 判存
        # 守卫应跳过建索引不报错
        engine = create_engine(mig.url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE UNIQUE INDEX uq_connector_active_order ON "
                    "charging_orders (device_id, connector_id) "
                    "WHERE order_status IN ('PENDING', 'CHARGING')"
                )
            )
        engine.dispose()
        _upgrade(mig)
        assert mig.has_index() and mig.index_is_unique()

    def test_head_version_reached(self, mig):
        _upgrade(mig)
        # 卡 f42bdf5a: head 推进至 202608170900 (invoice_requests void 列)。
        # 本测试只锁「202608161500 已被越过」—— upgrade head 后版本号 ≥ 本迁移,
        # 精确值随迁移链前进演进 (链尾是全局 head, 非 71e2f120 专属)。
        version = mig.scalar("SELECT version_num FROM alembic_version")
        assert version >= NEW_REV

"""
定时任务落库幂等唯一约束 + 并发竞态回归测试 (卡 97c83af9)

三处:
1. DailySettlement:  (settlement_date, station_key=COALESCE(station_id,0)) 唯一
2. PaymentReconciliation: (settlement_date, payment_channel) 唯一
3. EnergyDispatchPlan: (station_id, window_start) 唯一

覆盖: 重复执行 / 线程并发执行 / 唯一约束存在性 / NULL 哨兵映射。
"""
import threading
from datetime import date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.models.energy_strategy import EnergyDispatchPlan
from app.models.ops_settlement.daily_settlement import DailySettlement
from app.models.ops_settlement.payment_reconciliation import PaymentReconciliation
from app.tasks.settlement_tasks import build_daily_settlement, reconcile_payments
from tests.test_settlement_tasks import _make_order


# ═══════════════════════════════════════════════════════════════
# 唯一约束存在性 (schema 层)
# ═══════════════════════════════════════════════════════════════

class TestUniqueConstraintsExist:
    """三张表的唯一约束在模型 schema 中落地。

    SQLite 把 CREATE TABLE 内联 UNIQUE 落成 sqlite_autoindex_*, SQLAlchemy
    inspector.get_indexes 不返回它, 故这里取表内唯一索引名集合 = 显式 Index(unique)
    ∪ sqlite_autoindex (内联 UniqueConstraint), 断言唯一索引存在且列正确。
    """

    def _unique_indexes(self, db, table: str) -> dict:
        insp = sa.inspect(db.get_bind())
        uniq = {
            i["name"]: i["column_names"]
            for i in insp.get_indexes(table) if i["unique"]
        }
        # 内联 UniqueConstraint → sqlite_autoindex_<table>_N (sql 为 NULL)
        auto = [
            r[0] for r in db.execute(
                sa.text(f"SELECT name FROM sqlite_master WHERE type='index' "
                        f"AND tbl_name='{table}' AND sql IS NULL")
            )
        ]
        for name in auto:
            # PRAGMA index_info 走原始 DBAPI conn (经 ORM Session 结果为 seqno 下标)
            conn = db.connection().connection
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{name}')").fetchall()]
            uniq[name] = cols
        return uniq

    def test_daily_settlement_unique_index(self, test_db):
        db = test_db["session"]
        uniq = self._unique_indexes(db, "daily_settlements")
        assert uniq, "未取到任何唯一索引"
        assert any(set(c) == {"settlement_date", "station_key"} for c in uniq.values()), uniq

    def test_payment_reconciliation_unique_index(self, test_db):
        db = test_db["session"]
        uniq = self._unique_indexes(db, "payment_reconciliation")
        assert any(set(c) == {"settlement_date", "payment_channel"} for c in uniq.values())

    def test_energy_dispatch_plan_unique_index(self, test_db):
        db = test_db["session"]
        uniq = self._unique_indexes(db, "energy_dispatch_plan")
        assert any(set(c) == {"station_id", "window_start"} for c in uniq.values())


class TestNullSentinelStationKey:
    """station_id NULL (全平台) → station_key=0 哨兵映射"""

    def test_platform_row_maps_to_zero(self, test_db):
        db = test_db["session"]
        db.add(DailySettlement(settlement_date=date(2026, 8, 1), station_id=None))
        db.flush()
        row = db.query(DailySettlement).one()
        assert row.station_key == 0

    def test_station_row_maps_to_station_id(self, test_db):
        db = test_db["session"]
        db.add(DailySettlement(settlement_date=date(2026, 8, 1), station_id=7))
        db.flush()
        assert db.query(DailySettlement).one().station_key == 7

    def test_two_platform_rows_same_date_rejected(self, test_db):
        """两条 NULL=0 全平台行同日期 → 撞约束 (PG 多 NULL 不去重已由哨兵规避)"""
        db = test_db["session"]
        db.add(DailySettlement(settlement_date=date(2026, 8, 1), station_id=None))
        db.flush()
        db.add(DailySettlement(settlement_date=date(2026, 8, 1), station_id=None))
        with pytest.raises(IntegrityError):
            db.flush()


# ═══════════════════════════════════════════════════════════════
# 任务层幂等: 重复执行
# ═══════════════════════════════════════════════════════════════

class TestSettlementTaskIdempotent:

    def test_daily_settlement_rerun_no_duplicate(self, test_db):
        """同一天重复跑 build_daily_settlement 不插重复行, 数值覆盖"""
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 8, 1, 10, 0)))
        db.flush()

        r1 = build_daily_settlement(db, "2026-08-01")
        db.commit()
        r2 = build_daily_settlement(db, "2026-08-01")
        db.commit()

        assert r1["status"] == r2["status"] == "completed"
        rows = db.query(DailySettlement).filter(
            DailySettlement.settlement_date == date(2026, 8, 1)).all()
        assert len(rows) == 1
        # 订单只有 1 条, 重复跑覆盖后聚合值不变
        assert rows[0].total_orders == 1

    def test_reconcile_payments_rerun_no_duplicate(self, test_db):
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 8, 1, 10, 0)))
        db.flush()

        r1 = reconcile_payments(db, "2026-08-01")
        db.commit()
        r2 = reconcile_payments(db, "2026-08-01")
        db.commit()

        assert r1["channels_reconciled"] == r2["channels_reconciled"] == 1
        rows = db.query(PaymentReconciliation).filter(
            PaymentReconciliation.settlement_date == date(2026, 8, 1)).all()
        assert len(rows) == 1
        assert float(rows[0].platform_amount) == 50.0


# ═══════════════════════════════════════════════════════════════
# 任务层幂等: 线程并发 (check-then-act 竞态)
# ═══════════════════════════════════════════════════════════════

class TestSettlementTaskConcurrent:

    def test_daily_settlement_concurrent_single_row(self, test_db):
        """4 线程并发跑同一天日结 → 仅 1 行 (IntegrityError 回退覆盖语义)"""
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 8, 2, 10, 0)))
        db.commit()

        TestingSessionLocal = test_db["SessionLocal"]

        errors = []

        def _worker():
            s = TestingSessionLocal()
            try:
                build_daily_settlement(s, "2026-08-02")
                s.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(e)
                s.rollback()
            finally:
                s.close()

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        db.expire_all()
        rows = db.query(DailySettlement).filter(
            DailySettlement.settlement_date == date(2026, 8, 2)).all()
        assert len(rows) == 1, f"并发日结产生 {len(rows)} 行: {[r.id for r in rows]}"

    def test_reconcile_payments_concurrent_single_row(self, test_db):
        db = test_db["session"]
        db.add(_make_order(60, 50, 10, datetime(2026, 8, 3, 10, 0)))
        db.commit()

        TestingSessionLocal = test_db["SessionLocal"]
        errors = []

        def _worker():
            s = TestingSessionLocal()
            try:
                reconcile_payments(s, "2026-08-03")
                s.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(e)
                s.rollback()
            finally:
                s.close()

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        db.expire_all()
        rows = db.query(PaymentReconciliation).filter(
            PaymentReconciliation.settlement_date == date(2026, 8, 3)).all()
        assert len(rows) == 1, f"并发对账产生 {len(rows)} 行"


# ═══════════════════════════════════════════════════════════════
# EnergyDispatchPlan 同窗口唯一
# ═══════════════════════════════════════════════════════════════

class TestEnergyDispatchPlanWindowUnique:

    def test_same_station_window_rejected(self, test_db):
        db = test_db["session"]
        ws = datetime(2026, 8, 1, 12, 0)
        we = datetime(2026, 8, 1, 12, 15)
        db.add(EnergyDispatchPlan(station_id=1, team_id=100, window_start=ws, window_end=we))
        db.flush()
        db.add(EnergyDispatchPlan(station_id=1, team_id=100, window_start=ws, window_end=we))
        with pytest.raises(IntegrityError):
            db.flush()

    def test_same_station_different_window_ok(self, test_db):
        db = test_db["session"]
        db.add(EnergyDispatchPlan(station_id=1, team_id=100,
                                  window_start=datetime(2026, 8, 1, 12, 0),
                                  window_end=datetime(2026, 8, 1, 12, 15)))
        db.add(EnergyDispatchPlan(station_id=1, team_id=100,
                                  window_start=datetime(2026, 8, 1, 12, 15),
                                  window_end=datetime(2026, 8, 1, 12, 30)))
        db.flush()  # 不应抛
        assert db.query(EnergyDispatchPlan).count() == 2

    def test_dispatch_cycle_rerun_same_window_single_plan(self):
        """run_dispatch_cycle 同窗口重跑 → plan 覆盖不重复 (能量流水翻倍防线)"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.database import Base
        from app.tasks.energy_tasks import run_dispatch_cycle
        from tests.test_energy_tasks import (
            _seed_station, _seed_price_template, _seed_strategy, _seed_telemetry,
        )

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            _seed_station(db, station_id=1)
            tpl = _seed_price_template(db, station_id=1, price=0.30)
            _seed_strategy(db, station_id=1, template_id=tpl.id)
            _seed_telemetry(db, station_id=1, pv_kw=30.0, soc_pct=50.0, charger_kw=20.0)
            db.commit()

            now = datetime(2026, 8, 1, 12, 7, 0)
            run_dispatch_cycle(db, now=now)
            db.commit()
            run_dispatch_cycle(db, now=now)  # beat 重叠 / acks_late 重投递
            db.commit()

            assert db.query(EnergyDispatchPlan).count() == 1
            # flow log 是瞬时遥测快照, 重投递补写一行属审计语义, 不参与预算下发;
            # 关键防线是 plan 唯一 (apply_power_budget_to_charging 取最新 plan)
        finally:
            db.close()
            engine.dispose()

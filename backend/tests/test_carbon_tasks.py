"""
碳减排定时任务单元测试
"""
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from app.tasks import carbon_tasks
from app.tasks.carbon_tasks import (
    aggregate_carbon_for_date,
    build_carbon_monthly_summary,
    notify_carbon_monthly_report,
    carbon_daily_aggregate,
    carbon_monthly_summary,
)
from app.models.carbon_emission import (
    CarbonReductionRecord,
    CarbonReductionSummary,
)
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle

GRID_FACTOR = Decimal("0.5703")
FUEL_FACTOR = Decimal("0.56") * Decimal("2.1625")  # = 1.211


def _seed_enterprise_with_vehicles(db):
    ent = Enterprise(name="测试车队", code="ENT-CARBON-TASK-001", status="active")
    db.add(ent)
    db.flush()
    v1 = EnterpriseVehicle(
        enterprise_id=ent.id, plate_number="京T00001", vin="LTASK111111111111",
        status="active",
    )
    v2 = EnterpriseVehicle(
        enterprise_id=ent.id, plate_number="京T00002", vin="LTASK222222222222",
        status="active",
    )
    db.add_all([v1, v2])
    db.flush()
    return {"ent": ent, "v1": v1, "v2": v2}


def _make_order(vehicle_id, kwh, end_dt, status=OrderStatus.COMPLETED):
    return ChargingOrder(
        order_no=f"NO-{vehicle_id}-{end_dt.strftime('%Y%m%d%H%M')}-{kwh}",
        station_id=1,
        device_id=1,
        vehicle_id=vehicle_id,
        charged_kwh=kwh,
        end_time=end_dt,
        order_status=status,
    )


class TestDailyAggregate:

    def test_aggregates_completed_orders_by_vehicle(self, test_db):
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        target = date(2026, 7, 15)

        db.add_all([
            _make_order(seed["v1"].id, 50, datetime(2026, 7, 15, 12, 0)),
            # 18:00 UTC = 上海次日 02:00 → 归次日业务日 (卡 f7422bbc naive-UTC 口径), 改 09:00
            _make_order(seed["v1"].id, 60, datetime(2026, 7, 15, 9, 0)),
            _make_order(seed["v2"].id, 100, datetime(2026, 7, 15, 12, 0)),
        ])
        db.flush()

        result = aggregate_carbon_for_date(db, target.isoformat())

        recs = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.record_date == target
        ).all()
        by_veh = {r.vehicle_id: r for r in recs}
        assert len(recs) == 2
        assert float(by_veh[seed["v1"].id].charge_energy_kwh) == 110.0
        assert float(by_veh[seed["v2"].id].charge_energy_kwh) == 100.0
        assert by_veh[seed["v1"].id].enterprise_id == seed["ent"].id
        assert result["records_written"] == 2

    def test_filters_non_completed_and_no_vehicle(self, test_db):
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        target = date(2026, 7, 15)

        db.add_all([
            _make_order(seed["v1"].id, 999, datetime(2026, 7, 15, 10, 0), OrderStatus.PENDING),
            _make_order(seed["v1"].id, 200, datetime(2026, 7, 14, 10, 0)),
            _make_order(None, 500, datetime(2026, 7, 15, 10, 0)),
            _make_order(seed["v1"].id, 80, datetime(2026, 7, 15, 10, 0)),
        ])
        db.flush()

        aggregate_carbon_for_date(db, target.isoformat())

        recs = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.record_date == target
        ).all()
        assert len(recs) == 1
        assert float(recs[0].charge_energy_kwh) == 80.0

    def test_formula_correct(self, test_db):
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        target = date(2026, 7, 15)
        db.add(_make_order(seed["v1"].id, 100, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        aggregate_carbon_for_date(db, target.isoformat())

        rec = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.record_date == target
        ).one()
        expected = (FUEL_FACTOR - GRID_FACTOR) * Decimal("100")
        assert abs(float(rec.carbon_reduction_kg) - float(expected)) < 0.5
        assert abs(float(rec.equivalent_fuel_saved_liters) - 56.0) < 0.5

    def test_idempotent_rerun(self, test_db):
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        target = date(2026, 7, 15)
        db.add(_make_order(seed["v1"].id, 100, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        aggregate_carbon_for_date(db, target.isoformat())
        db.add(_make_order(seed["v1"].id, 50, datetime(2026, 7, 15, 14, 0)))
        db.flush()
        aggregate_carbon_for_date(db, target.isoformat())

        recs = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.record_date == target,
            CarbonReductionRecord.vehicle_id == seed["v1"].id,
        ).all()
        assert len(recs) == 1
        assert float(recs[0].charge_energy_kwh) == 150.0


class TestMonthlySummary:

    def _seed_month_records(self, db):
        seed = _seed_enterprise_with_vehicles(db)
        for d, kwh in [("2026-07-01", 100), ("2026-07-10", 80), ("2026-07-20", 120)]:
            db.add(CarbonReductionRecord(
                vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
                record_date=date.fromisoformat(d), charge_energy_kwh=kwh,
                grid_factor=GRID_FACTOR, fuel_factor=FUEL_FACTOR,
                carbon_reduction_kg=(FUEL_FACTOR - GRID_FACTOR) * Decimal(kwh),
                equivalent_fuel_saved_liters=Decimal("0.56") * Decimal(kwh),
            ))
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v2"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 7, 5), charge_energy_kwh=50,
            grid_factor=GRID_FACTOR, fuel_factor=FUEL_FACTOR,
            carbon_reduction_kg=(FUEL_FACTOR - GRID_FACTOR) * Decimal("50"),
            equivalent_fuel_saved_liters=Decimal("0.56") * Decimal("50"),
        ))
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 6, 30), charge_energy_kwh=999,
            grid_factor=GRID_FACTOR, fuel_factor=FUEL_FACTOR,
            carbon_reduction_kg=Decimal("0"), equivalent_fuel_saved_liters=Decimal("0"),
        ))
        db.flush()
        return seed

    def test_aggregates_month(self, test_db):
        db = test_db["session"]
        seed = self._seed_month_records(db)

        result = build_carbon_monthly_summary(db, 2026, 7)

        s = db.query(CarbonReductionSummary).filter(
            CarbonReductionSummary.enterprise_id == seed["ent"].id,
            CarbonReductionSummary.report_year == 2026,
            CarbonReductionSummary.report_month == 7,
        ).one()
        assert float(s.total_charge_kwh) == 350.0
        assert s.vehicle_count == 2
        assert result["summaries_built"] == 1

    def test_idempotent_update(self, test_db):
        db = test_db["session"]
        seed = self._seed_month_records(db)

        build_carbon_monthly_summary(db, 2026, 7)
        build_carbon_monthly_summary(db, 2026, 7)

        rows = db.query(CarbonReductionSummary).filter(
            CarbonReductionSummary.enterprise_id == seed["ent"].id,
            CarbonReductionSummary.report_year == 2026,
            CarbonReductionSummary.report_month == 7,
        ).all()
        assert len(rows) == 1

    def test_no_records_skips(self, test_db):
        db = test_db["session"]
        result = build_carbon_monthly_summary(db, 2026, 7)
        assert result["summaries_built"] == 0
        assert db.query(CarbonReductionSummary).count() == 0


class TestNotifyMonthlyReport:

    def test_webhook_not_configured_returns_false(self):
        with patch.object(carbon_tasks, "im_notify_service") as mock_svc:
            mock_svc.webhook_url = None
            ok = notify_carbon_monthly_report([
                {"enterprise_name": "测试车队", "report_year": 2026, "report_month": 7,
                 "total_charge_kwh": 350.0, "total_reduction_kg": 224.0,
                 "total_fuel_saved_liters": 196.0, "vehicle_count": 2}
            ])
        assert ok is False

    def test_sends_card_with_enterprise_and_month(self):
        with patch.object(carbon_tasks, "im_notify_service") as mock_svc:
            mock_svc.webhook_url = "https://example.com/hook"
            mock_svc.send_webhook_message = AsyncMock(return_value=True)
            ok = notify_carbon_monthly_report([
                {"enterprise_name": "测试车队", "report_year": 2026, "report_month": 7,
                 "total_charge_kwh": 350.0, "total_reduction_kg": 224.245,
                 "total_fuel_saved_liters": 196.0, "vehicle_count": 2}
            ])
        assert ok is True
        mock_svc.send_webhook_message.assert_awaited_once()


class TestTaskWrappers:

    def test_daily_task_importable_and_callable(self, test_db):
        """carbon_daily_aggregate 可导入且纯函数端到端正确"""
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        db.add(_make_order(seed["v1"].id, 100, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        result = aggregate_carbon_for_date(db, "2026-07-15")
        db.commit()

        assert result["status"] == "completed"
        assert result["records_written"] == 1
        rec = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.vehicle_id == seed["v1"].id,
            CarbonReductionRecord.record_date == date(2026, 7, 15),
        ).one()
        assert float(rec.charge_energy_kwh) == 100.0
        assert rec.enterprise_id == seed["ent"].id

    def test_monthly_task_with_notify(self, test_db):
        """月度汇总 + 推送 mock"""
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 7, 10), charge_energy_kwh=200,
            grid_factor=GRID_FACTOR, fuel_factor=FUEL_FACTOR,
            carbon_reduction_kg=(FUEL_FACTOR - GRID_FACTOR) * Decimal("200"),
            equivalent_fuel_saved_liters=Decimal("0.56") * Decimal("200"),
        ))
        db.flush()

        result = build_carbon_monthly_summary(db, 2026, 7)
        db.commit()

        assert result["status"] == "completed"
        assert result["summaries_built"] == 1
        # 验证推送数据正确
        s = result["summaries"][0]
        assert s["enterprise_name"] == "测试车队"
        assert s["total_charge_kwh"] == 200.0
        # 推送函数可调用（webhook未配置返回False）
        ok = notify_carbon_monthly_report(result["summaries"])
        assert ok is False  # webhook 未配置


# ═══════════════════════════════════════════════════════════════════
# 幂等唯一约束 + IntegrityError 兜底 (卡 7ea84b57)
# ═══════════════════════════════════════════════════════════════════

class TestCarbonIdempotencyCard7ea84b57:
    """uq_crr_vehicle_date 唯一约束 + aggregate/summary 的 IntegrityError 兜底。

    同族缺陷: 卡 97c83af9 / 9863018d。celery worker_concurrency=4 +
    task_acks_late=True 重投递 / 手动补算并发 → check-then-act 插重复行,
    下游 carbon_emission / enterprise_vehicles 的 func.sum 双倍计算。
    """

    def _unique_indexes(self, engine, table):
        """SQLite 表级 UniqueConstraint 生成匿名 sqlite_autoindex, 不进
        inspector.get_indexes; 用 PRAGMA index_list 取 origin='u' 唯一索引。"""
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(f"PRAGMA index_list({table})").fetchall()
            out = []
            for r in rows:
                # (seq, name, unique, origin, partial)
                if r[2]:
                    cols = {c[2] for c in conn.exec_driver_sql(
                        f"PRAGMA index_info({r[1]})").fetchall()}
                    out.append(cols)
            return out

    def test_record_unique_constraint_exists(self, test_db):
        uniques = self._unique_indexes(test_db["engine"], "carbon_reduction_records")
        assert {"vehicle_id", "record_date"} in uniques

    def test_record_duplicate_insert_rejected(self, test_db):
        from sqlalchemy.exc import IntegrityError
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 7, 15), charge_energy_kwh=100,
        ))
        db.commit()
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 7, 15), charge_energy_kwh=200,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_daily_integrity_error_fallback_overwrite(self, test_db):
        """IntegrityError 兜底: 强制 upsert 首轮走 add 分支 (existing 恒 None) →
        flush 撞唯一约束 → 兜底 rollback 重跑转纯覆盖, 最终 1 行且值正确。"""
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        target = date(2026, 7, 15)
        db.add(_make_order(seed["v1"].id, 100, datetime(2026, 7, 15, 10, 0)))
        db.commit()

        aggregate_carbon_for_date(db, target.isoformat())
        db.commit()
        assert db.query(CarbonReductionRecord).count() == 1

        # 模拟竞态: 删本 session 行 + 外部插同键行 → 本轮 existing 查询 miss → add 撞约束
        db.query(CarbonReductionRecord).delete()
        db.commit()
        other = test_db["SessionLocal"]()
        try:
            other.add(CarbonReductionRecord(
                vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
                record_date=target, charge_energy_kwh=999,
            ))
            other.commit()
        finally:
            other.close()
        # 让本 session 的 existing 查询恒 miss (Session identity map 快照) → add 撞约束
        db.expire_all()

        # monkeypatch db.query 对 CarbonReductionRecord 的 .first() 首轮返回 None
        real_first_calls = {"n": 0}

        class _QProxy:
            def __init__(self, real):
                self._real = real

            def first(self):
                real_first_calls["n"] += 1
                if real_first_calls["n"] <= 1:
                    return None  # 首轮 check-then-act miss → add 撞约束
                return self._real.first()

            def __getattr__(self, name):
                return getattr(self._real, name)

        _orig_query = db.query

        def _patched_query(*a, **kw):
            q = _orig_query(*a, **kw)
            if a and a[0] is CarbonReductionRecord:
                return _QProxy(q)
            return q

        with patch.object(type(db), "query", side_effect=_patched_query):
            result = aggregate_carbon_for_date(db, target.isoformat())
        db.commit()

        assert result["records_written"] == 1
        recs = db.query(CarbonReductionRecord).filter(
            CarbonReductionRecord.record_date == target
        ).all()
        assert len(recs) == 1  # 未插重复行
        assert float(recs[0].charge_energy_kwh) == 100.0  # 覆盖为聚合正确值

    def test_monthly_integrity_error_fallback(self, test_db):
        """月度汇总 IntegrityError 兜底: 竞态撞 uq_crs_enterprise_year_month →
        rollback 重跑转纯覆盖, 不再向上抛异常导致任务失败重试。"""
        db = test_db["session"]
        seed = _seed_enterprise_with_vehicles(db)
        db.add(CarbonReductionRecord(
            vehicle_id=seed["v1"].id, enterprise_id=seed["ent"].id,
            record_date=date(2026, 7, 10), charge_energy_kwh=200,
        ))
        db.commit()

        build_carbon_monthly_summary(db, 2026, 7)
        db.commit()
        assert db.query(CarbonReductionSummary).count() == 1

        # 模拟竞态: 删本 session 行 + 外部插同键 summary → existing 恒 miss 撞约束
        db.query(CarbonReductionSummary).delete()
        db.commit()
        other = test_db["SessionLocal"]()
        try:
            other.add(CarbonReductionSummary(
                enterprise_id=seed["ent"].id, report_year=2026, report_month=7,
                total_charge_kwh=1,
            ))
            other.commit()
        finally:
            other.close()
        db.expire_all()

        _orig_query = db.query
        calls = {"n": 0}

        class _QProxy:
            def __init__(self, real):
                self._real = real

            def first(self):
                calls["n"] += 1
                if calls["n"] <= 1:
                    return None
                return self._real.first()

            def __getattr__(self, name):
                return getattr(self._real, name)

        def _patched_query(*a, **kw):
            q = _orig_query(*a, **kw)
            if a and a[0] is CarbonReductionSummary:
                return _QProxy(q)
            return q

        with patch.object(type(db), "query", side_effect=_patched_query):
            result = build_carbon_monthly_summary(db, 2026, 7)
        db.commit()

        assert result["status"] == "completed"
        rows = db.query(CarbonReductionSummary).filter(
            CarbonReductionSummary.enterprise_id == seed["ent"].id
        ).all()
        assert len(rows) == 1
        assert float(rows[0].total_charge_kwh) == 200.0  # 覆盖为正确值


# ═══════════════════════════════════════════════════════════════════
# 默认 target 业务时区 wiring (卡 c42ac99a)
# ═══════════════════════════════════════════════════════════════════

class TestDefaultTargetBizTz:
    """carbon_daily_aggregate / carbon_monthly_summary 默认参数走业务时区。

    - daily: 无参 → target_date 取业务时区昨日 (旧 date.today()-1d 在 UTC 容器错算前天)
    - monthly: 无参 → 汇总上月; 月初边界 (上海1号03:00=UTC上月末19:00) 仍指上月
      (旧 date.today() 在 UTC 容器取上月末 → 汇总上上月, 每月固定错)

    时区逻辑本身见 test_tasks_tz_utils.py; 此处证明任务默认分支确实消费 helper。
    """

    def test_daily_default_target_is_biz_yesterday(self, monkeypatch):
        """无参 carbon_daily_aggregate → build 收到业务时区昨日。"""
        from app.tasks import carbon_tasks

        captured = {}
        monkeypatch.setattr(carbon_tasks, "yesterday_in_biz_tz", lambda: date(2026, 8, 6))

        class _FakeDB:
            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(carbon_tasks, "SessionLocal", lambda: _FakeDB())
        monkeypatch.setattr(
            carbon_tasks, "aggregate_carbon_for_date",
            lambda db, td: captured.setdefault("target_date", td) or {"status": "completed"},
        )

        carbon_tasks.carbon_daily_aggregate.__wrapped__()
        assert captured["target_date"] == "2026-08-06"

    def test_monthly_default_picks_last_month_at_month_start(self, monkeypatch):
        """月初边界: patch today_in_biz_tz 为上海月初 (08-01) → 汇总 7 月。

        复刻上海 08-01 03:00 beat 场景: 业务时区 today=08-01 → 上月=7月。
        旧实现 date.today() 在 UTC 容器=07-31 → replace(day=1)-1d=06-30 → 错汇总6月。
        """
        from app.tasks import carbon_tasks

        captured = {}
        monkeypatch.setattr(carbon_tasks, "today_in_biz_tz", lambda: date(2026, 8, 1))

        class _FakeDB:
            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(carbon_tasks, "SessionLocal", lambda: _FakeDB())
        monkeypatch.setattr(
            carbon_tasks, "notify_carbon_monthly_report", lambda summaries: False,
        )

        def _capture(db, year, month):
            captured["year"], captured["month"] = year, month
            return {"status": "completed", "summaries": []}

        monkeypatch.setattr(carbon_tasks, "build_carbon_monthly_summary", _capture)

        carbon_tasks.carbon_monthly_summary.__wrapped__()
        assert (captured["year"], captured["month"]) == (2026, 7)

    def test_monthly_explicit_args_not_overridden(self, monkeypatch):
        """显式传 year/month 不走默认分支 (手动补算场景)。"""
        from app.tasks import carbon_tasks

        captured = {}

        class _FakeDB:
            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(carbon_tasks, "SessionLocal", lambda: _FakeDB())

        def _capture(db, year, month):
            captured["year"], captured["month"] = year, month
            return {"status": "completed", "summaries": []}

        monkeypatch.setattr(carbon_tasks, "build_carbon_monthly_summary", _capture)
        carbon_tasks.carbon_monthly_summary.__wrapped__(2026, 3)
        assert (captured["year"], captured["month"]) == (2026, 3)

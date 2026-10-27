"""
卡片 411936df: Celery 软超时穿透 + beat expires 回归测试

背景: task_soft_time_limit=300 抛 SoftTimeLimitExceeded (Exception 子类),
被任务体内宽 except Exception 吞掉 → 软超时失效 → 跑满 600s 硬杀 →
task_reject_on_worker_lost 重投 → 从头重跑 → agent_memory 重复 finding。

契约:
1. 所有宽 except 站点前置 `except SoftTimeLimitExceeded: raise`
2. beat_schedule 每条目 options.expires 存在且 < 调度周期
"""
from unittest.mock import MagicMock

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from tests.test_agent_memory import _make_device, _make_station, _make_team

# beat 条目名 → 调度周期 (秒)。expires 必须严格小于周期 (积压任务过期不再入队)。
BEAT_PERIOD_SECONDS = {
    "daily-health-report": 86400,
    "weekly-data-cleanup": 604800,
    "daily-retention-logs-cleanup": 86400,
    "hourly-fault-prediction": 3600,
    "carbon-daily-aggregate": 86400,
    "carbon-monthly-summary": 2592000,  # 30d
    "settlement-daily": 86400,
    "settlement-reconcile": 86400,
    "revenue-daily-aggregate": 86400,
    "station-daily-metrics-aggregate": 86400,
    "energy-dispatch-cycle": 900,
    "stale-pending-order-cleanup": 300,
    "agent-patrol-maintenance": 300,
    "fleet-alert-scan": 300,
    "agent-patrol-operations": 600,
    "agent-patrol-platform": 1800,
}


class TestBeatScheduleExpires:
    def test_every_entry_has_expires_below_period(self):
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert schedule, "beat_schedule 不应为空"
        assert set(schedule) == set(BEAT_PERIOD_SECONDS), (
            f"beat 条目集与测试期望不一致: {set(schedule) ^ set(BEAT_PERIOD_SECONDS)}"
        )
        for name, entry in schedule.items():
            opts = entry.get("options") or {}
            period = BEAT_PERIOD_SECONDS[name]
            assert "expires" in opts, f"{name} 缺少 options.expires"
            expires = opts["expires"]
            assert 0 < expires < period, (
                f"{name} expires={expires} 应满足 0 < expires < {period}"
            )


def _forbid_retry(task, monkeypatch):
    """把 task.retry 换成哨兵: 被调用即说明软超时被吞成重试。"""
    def _fail(*args, **kwargs):
        raise AssertionError("软超时不应触发 self.retry, 应原样上抛 SoftTimeLimitExceeded")
    monkeypatch.setattr(task, "retry", _fail)


class TestAgentPatrolSoftTimeout:
    def test_per_check_block_lets_soft_timeout_through(self, test_db, monkeypatch):
        """运维巡检 per-check 宽 except 不吞 SoftTimeLimitExceeded"""
        from datetime import datetime, timedelta, timezone
        from app.models.device import DeviceStatus
        from app.tasks import agent_patrol

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(
            session, st.id, sn="D-SOFT-TO",
            status=DeviceStatus.ONLINE,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=30),
        )

        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(agent_patrol, "_save_finding", _raise)
        with pytest.raises(SoftTimeLimitExceeded):
            agent_patrol.patrol_maintenance.__wrapped__(team.id)

    def test_maintenance_all_tenant_loop_lets_soft_timeout_through(
        self, test_db, monkeypatch
    ):
        """patrol_maintenance_all 租户循环不吞 SoftTimeLimitExceeded"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        _make_team(session)

        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(agent_patrol, "_patrol_maintenance_single", _raise)
        with pytest.raises(SoftTimeLimitExceeded):
            agent_patrol.patrol_maintenance_all.__wrapped__()

    def test_operations_all_tenant_loop_lets_soft_timeout_through(
        self, test_db, monkeypatch
    ):
        """patrol_operations_all 租户循环不吞 SoftTimeLimitExceeded"""
        from app.tasks import agent_patrol

        session = test_db["session"]
        _make_team(session)

        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(agent_patrol, "_patrol_operations_single", _raise)
        with pytest.raises(SoftTimeLimitExceeded):
            agent_patrol.patrol_operations_all.__wrapped__()


class TestEnergySoftTimeout:
    def test_dispatch_station_loop_lets_soft_timeout_through(self, monkeypatch):
        """run_dispatch_cycle 逐站循环不吞 SoftTimeLimitExceeded"""
        from app.tasks import energy_tasks

        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(energy_tasks, "_dispatch_one_station", _raise)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [MagicMock()]
        with pytest.raises(SoftTimeLimitExceeded):
            energy_tasks.run_dispatch_cycle(db)

    def test_dispatch_cycle_task_does_not_retry_on_soft_timeout(self, monkeypatch):
        """dispatch_cycle 任务级 except 不把软超时转成 self.retry"""
        from app.tasks import energy_tasks

        def _raise(db):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(energy_tasks, "run_dispatch_cycle", _raise)
        fake_db = MagicMock()
        monkeypatch.setattr(
            "app.core.database.SessionLocal", lambda: fake_db, raising=True
        )
        _forbid_retry(energy_tasks.dispatch_cycle, monkeypatch)
        with pytest.raises(SoftTimeLimitExceeded):
            energy_tasks.dispatch_cycle.__wrapped__()


class TestFleetAlertSoftTimeout:
    def test_scan_loop_lets_soft_timeout_through(self, test_db, monkeypatch):
        """车队告警扫描逐企业/逐检查循环不吞 SoftTimeLimitExceeded"""
        from app.services import fleet_alert_service
        from app.tasks import fleet_alert_tasks

        def _raise(enterprise_id):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(fleet_alert_tasks, "_enabled_enterprise_ids", lambda db: [1])
        monkeypatch.setattr(fleet_alert_service, "check_low_battery", _raise)
        _forbid_retry(fleet_alert_tasks.scan_fleet_alerts_task, monkeypatch)
        with pytest.raises(SoftTimeLimitExceeded):
            fleet_alert_tasks.scan_fleet_alerts_task.__wrapped__()


class TestMaintenanceSoftTimeout:
    def test_batch_predict_device_loop_lets_soft_timeout_through(
        self, test_db, monkeypatch
    ):
        """批量故障预测逐设备循环不吞 SoftTimeLimitExceeded"""
        from app.tasks import maintenance_tasks

        session = test_db["session"]
        team = _make_team(session)
        st = _make_station(session, team.id)
        _make_device(session, st.id, sn="D-PRED-TO")

        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(
            maintenance_tasks.predict_faults_task, "__wrapped__", _raise
        )
        with pytest.raises(SoftTimeLimitExceeded):
            maintenance_tasks.batch_predict_faults_task.__wrapped__()


class TestCarbonSettlementSoftTimeout:
    """carbon/settlement 任务级 except (rollback + self.retry) 不吞软超时"""

    def _run_bound_task(self, monkeypatch, module, dep_name, task):
        def _raise(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(module, dep_name, _raise)
        monkeypatch.setattr(module, "SessionLocal", lambda: MagicMock())
        _forbid_retry(task, monkeypatch)
        with pytest.raises(SoftTimeLimitExceeded):
            task.__wrapped__()

    def test_carbon_daily_aggregate(self, monkeypatch):
        from app.tasks import carbon_tasks
        self._run_bound_task(
            monkeypatch, carbon_tasks, "aggregate_carbon_for_date",
            carbon_tasks.carbon_daily_aggregate,
        )

    def test_carbon_monthly_summary(self, monkeypatch):
        from app.tasks import carbon_tasks
        self._run_bound_task(
            monkeypatch, carbon_tasks, "build_carbon_monthly_summary",
            carbon_tasks.carbon_monthly_summary,
        )

    def test_settlement_daily(self, monkeypatch):
        from app.tasks import settlement_tasks
        self._run_bound_task(
            monkeypatch, settlement_tasks, "build_daily_settlement",
            settlement_tasks.settlement_daily,
        )

    def test_settlement_reconcile(self, monkeypatch):
        from app.tasks import settlement_tasks
        self._run_bound_task(
            monkeypatch, settlement_tasks, "reconcile_payments",
            settlement_tasks.settlement_reconcile,
        )

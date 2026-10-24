"""app/core/celery_app.py Celery 任务队列配置单测

celery 5.6.3 已装 → 走 CELERY_AVAILABLE=True 分支 (真实 Celery 实例)。
覆盖: broker/backend 配置常量 / celery_app.conf 各项 / beat_schedule 11 个定时任务 /
task_routes / include / get_celery_status (mock inspector 三态 + broker 脱敏)。
"""
from unittest.mock import MagicMock

import pytest
from celery import Celery
from celery.schedules import crontab

from app.core import celery_app as cab


# ────────────────────────────────────────────────────────────────────
# Celery 可用 + 真实实例
# ────────────────────────────────────────────────────────────────────
class TestCeleryAvailable:
    def test_celery_available_flag(self):
        assert cab.CELERY_AVAILABLE is True

    def test_celery_app_is_real_celery_instance(self):
        assert isinstance(cab.celery_app, Celery)

    def test_celery_app_name(self):
        assert cab.celery_app.main == "tianlian_v3"


class TestBrokerConstants:
    def test_broker_url_default(self):
        # 测试环境未设 CELERY_BROKER_URL → import 期回落 redis 默认
        assert cab.CELERY_BROKER_URL == "redis://localhost:6379/0"

    def test_result_backend_default(self):
        assert cab.CELERY_RESULT_BACKEND == "redis://localhost:6379/1"


# ────────────────────────────────────────────────────────────────────
# celery_app.conf
# ────────────────────────────────────────────────────────────────────
class TestCeleryConfiguration:
    def test_serialization_json(self):
        conf = cab.celery_app.conf
        assert conf.task_serializer == "json"
        assert conf.result_serializer == "json"
        assert "json" in conf.accept_content

    def test_timezone_shanghai_and_utc(self):
        conf = cab.celery_app.conf
        assert conf.timezone == "Asia/Shanghai"
        assert conf.enable_utc is True

    def test_result_expires_one_hour(self):
        assert cab.celery_app.conf.result_expires == 3600

    def test_time_limits(self):
        conf = cab.celery_app.conf
        assert conf.task_soft_time_limit == 300  # 5min 软超时
        assert conf.task_time_limit == 600       # 10min 硬超时

    def test_worker_concurrency(self):
        conf = cab.celery_app.conf
        assert conf.worker_concurrency == 4
        assert conf.worker_prefetch_multiplier == 2

    def test_retry_semantics(self):
        conf = cab.celery_app.conf
        assert conf.task_acks_late is True
        assert conf.task_reject_on_worker_lost is True

    def test_default_queue(self):
        assert cab.celery_app.conf.task_default_queue == "default"


# ────────────────────────────────────────────────────────────────────
# task_routes + include
# ────────────────────────────────────────────────────────────────────
class TestTaskRouting:
    def test_analytics_routed(self):
        routes = cab.celery_app.conf.task_routes
        assert routes["app.tasks.analytics_tasks.*"]["queue"] == "analytics"

    def test_maintenance_routed(self):
        routes = cab.celery_app.conf.task_routes
        assert routes["app.tasks.maintenance_tasks.*"]["queue"] == "maintenance"

    def test_include_task_modules(self):
        included = cab.celery_app.conf.include
        for mod in ("app.tasks.settlement_tasks", "app.tasks.analytics_tasks",
                    "app.tasks.maintenance_tasks", "app.tasks.carbon_tasks",
                    "app.tasks.energy_tasks"):
            assert mod in included, f"missing include: {mod}"


# ────────────────────────────────────────────────────────────────────
# beat_schedule (定时任务矩阵)
# ────────────────────────────────────────────────────────────────────
class TestBeatSchedule:
    EXPECTED = (
        "daily-health-report", "weekly-data-cleanup", "hourly-fault-prediction",
        "carbon-daily-aggregate", "carbon-monthly-summary", "settlement-daily",
        "settlement-reconcile", "revenue-daily-aggregate",
        "station-daily-metrics-aggregate", "energy-dispatch-cycle",
    )

    def test_all_schedules_present(self):
        bs = cab.celery_app.conf.beat_schedule
        for name in self.EXPECTED:
            assert name in bs, f"missing beat schedule: {name}"

    def test_schedule_entries_use_crontab(self):
        bs = cab.celery_app.conf.beat_schedule
        for name in self.EXPECTED:
            assert isinstance(bs[name]["schedule"], crontab), name

    def test_health_report_target_and_queue(self):
        entry = cab.celery_app.conf.beat_schedule["daily-health-report"]
        assert entry["task"] == "analytics.batch_health_report"
        assert entry["options"]["queue"] == "analytics"

    def test_weekly_cleanup_args_30_days(self):
        entry = cab.celery_app.conf.beat_schedule["weekly-data-cleanup"]
        assert entry["task"] == "maintenance.cleanup_old_data"
        assert entry["args"] == (30,)
        assert entry["options"]["queue"] == "maintenance"

    def test_energy_dispatch_is_crontab(self):
        entry = cab.celery_app.conf.beat_schedule["energy-dispatch-cycle"]
        assert entry["task"] == "energy.dispatch_cycle"
        assert isinstance(entry["schedule"], crontab)


# ────────────────────────────────────────────────────────────────────
# get_celery_status (mock inspector — 不连真实 broker)
# ────────────────────────────────────────────────────────────────────
class TestGetCeleryStatus:
    @staticmethod
    def _patch_control(monkeypatch, active, stats):
        inspect = MagicMock()
        inspect.active.return_value = active
        inspect.stats.return_value = stats
        control = MagicMock()
        control.inspect.return_value = inspect
        monkeypatch.setattr(cab.celery_app, "control", control)
        return control

    def test_status_running_with_workers(self, monkeypatch):
        self._patch_control(monkeypatch, {"w1": []}, {"w1": {"pool": "prefork"}})
        status = cab.get_celery_status()
        assert status["status"] == "running"
        assert status["workers"] == ["w1"]
        assert status["active_tasks"] == 0

    def test_active_tasks_counted_across_workers(self, monkeypatch):
        self._patch_control(
            monkeypatch,
            {"w1": [{"id": "t1"}, {"id": "t2"}], "w2": [{"id": "t3"}]},
            {"w1": {}, "w2": {}},
        )
        assert cab.get_celery_status()["active_tasks"] == 3

    def test_no_workers_when_stats_empty(self, monkeypatch):
        self._patch_control(monkeypatch, None, {})
        status = cab.get_celery_status()
        assert status["status"] == "no_workers"
        assert status["workers"] == []

    def test_no_workers_when_active_none(self, monkeypatch):
        self._patch_control(monkeypatch, None, {})
        assert cab.get_celery_status()["active_tasks"] == 0

    def test_exception_returns_unavailable(self, monkeypatch):
        control = MagicMock()
        control.inspect.side_effect = Exception("broker down")
        monkeypatch.setattr(cab.celery_app, "control", control)
        status = cab.get_celery_status()
        assert status["status"] == "unavailable"
        assert "broker down" in status["error"]

    def test_broker_url_redacted_strips_credentials(self, monkeypatch):
        """broker URL 含 :secret@ 时只返回 host 段, 不泄漏密码。"""
        self._patch_control(monkeypatch, None, {})
        monkeypatch.setattr(cab, "CELERY_BROKER_URL", "redis://:s3cr3t@host:6379/0")
        status = cab.get_celery_status()
        assert status["broker_url"] == "host:6379/0"
        assert "s3cr3t" not in status["broker_url"]

    def test_broker_url_no_credentials_passthrough(self, monkeypatch):
        self._patch_control(monkeypatch, None, {})
        monkeypatch.setattr(cab, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        assert cab.get_celery_status()["broker_url"] == "redis://localhost:6379/0"

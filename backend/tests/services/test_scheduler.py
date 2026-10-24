#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康度调度器服务测试 - 覆盖率补强 ≥70%

被测: app/services/scheduler.py (HealthScheduler 单例)
设计: mock 外部依赖 (health_monitor / evaluate_all_rules / scan_and_escalate /
      maintenance_schedule_checker / schedule / threading.Thread), 隔离真链路,
      走 run_health_check 各分支 + escalation/maintenance check + start/stop。

覆盖:
- 单例/属性 smoke           health_scheduler 存在, 方法/配置齐备
- run_escalation_scan       result truthy→log / except 吞错
- run_maintenance_check     result truthy→log / except 吞错
- run_health_check          正常(alarms空+triggered空) / 有alarms+triggered / 异常→None
- start                     首次启动(注册3任务+立即跑) / 已运行跳过
- stop                      复位 running + join 线程
- start/stop_health_scheduler   模块级函数转发到单例
"""
from unittest.mock import MagicMock

import pytest

from app.services import scheduler as sched_mod
from app.services.scheduler import (
    HealthScheduler,
    health_scheduler,
    start_health_scheduler,
    stop_health_scheduler,
)


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    """单例状态跨用例隔离: 每用例前后复位 running/thread。"""
    health_scheduler.running = False
    health_scheduler.thread = None
    yield
    health_scheduler.running = False
    health_scheduler.thread = None


# ═══════════════════════════════════════════════════════════════
# smoke: 单例与属性
# ═══════════════════════════════════════════════════════════════

class TestSingleton:

    def test_singleton_exists(self):
        assert isinstance(health_scheduler, HealthScheduler)

    def test_has_methods_and_config(self):
        for attr in ("start", "stop", "run_health_check",
                     "run_escalation_scan", "run_maintenance_check"):
            assert callable(getattr(health_scheduler, attr))
        assert hasattr(health_scheduler, "running")
        assert hasattr(health_scheduler, "interval") or hasattr(health_scheduler, "check_interval")


# ═══════════════════════════════════════════════════════════════
# run_escalation_scan
# ═══════════════════════════════════════════════════════════════

class TestRunEscalationScan:

    def test_truthy_result_logs_count(self, monkeypatch):
        # result 非空 → 进入 if 打日志 (覆盖 line 32-33)
        monkeypatch.setattr(sched_mod, "scan_and_escalate", lambda: [{"id": 1}])
        health_scheduler.run_escalation_scan()  # 不抛即通过

    def test_swallows_exception(self, monkeypatch):
        # 覆盖 line 34-35 except 吞错
        def _raise():
            raise RuntimeError("scan boom")
        monkeypatch.setattr(sched_mod, "scan_and_escalate", _raise)
        health_scheduler.run_escalation_scan()  # 异常被吞, 不外抛


# ═══════════════════════════════════════════════════════════════
# run_maintenance_check
# ═══════════════════════════════════════════════════════════════

class TestRunMaintenanceCheck:

    def test_truthy_result_logs_count(self, monkeypatch):
        fake_checker = MagicMock()
        fake_checker.check_maintenance_schedule.return_value = [{"device": 1}]
        monkeypatch.setattr(sched_mod, "maintenance_schedule_checker", fake_checker)
        health_scheduler.run_maintenance_check()

    def test_swallows_exception(self, monkeypatch):
        fake_checker = MagicMock()
        fake_checker.check_maintenance_schedule.side_effect = RuntimeError("maint boom")
        monkeypatch.setattr(sched_mod, "maintenance_schedule_checker", fake_checker)
        health_scheduler.run_maintenance_check()  # 异常被吞


# ═══════════════════════════════════════════════════════════════
# run_health_check
# ═══════════════════════════════════════════════════════════════

class TestRunHealthCheck:

    def test_normal_path_returns_true(self, test_db, monkeypatch):
        # alarms 空 + triggered 空 + escalation 空 (覆盖 falsy 各分支)
        monkeypatch.setattr(sched_mod, "SessionLocal", test_db["SessionLocal"])
        fake_hm = MagicMock()
        fake_hm.calculate_all_health.return_value = [1]
        fake_hm.check_and_create_alarms.return_value = []
        monkeypatch.setattr(sched_mod, "health_monitor", fake_hm)
        monkeypatch.setattr(sched_mod, "evaluate_all_rules", lambda: [])
        monkeypatch.setattr(sched_mod, "scan_and_escalate", lambda: [])

        assert health_scheduler.run_health_check() is True

    def test_with_alarms_and_triggered(self, test_db, monkeypatch):
        # 覆盖 alarms truthy (line 58-61) + triggered 非空 (line 66-69)
        monkeypatch.setattr(sched_mod, "SessionLocal", test_db["SessionLocal"])
        fake_hm = MagicMock()
        fake_hm.calculate_all_health.return_value = [1, 2]
        fake_hm.check_and_create_alarms.return_value = [
            {"device": "D1", "score": 42.5, "workorder_id": "WO-1"},
        ]
        monkeypatch.setattr(sched_mod, "health_monitor", fake_hm)
        monkeypatch.setattr(sched_mod, "evaluate_all_rules", lambda: [
            {"triggered": True, "rule_name": "高温", "devices": [1, 2]},
            {"triggered": False},
        ])
        monkeypatch.setattr(sched_mod, "scan_and_escalate", lambda: [{"id": 1}])

        assert health_scheduler.run_health_check() is True

    def test_exception_returns_none(self, test_db, monkeypatch):
        # 覆盖 line 73-75 except → return None + finally close
        monkeypatch.setattr(sched_mod, "SessionLocal", test_db["SessionLocal"])
        fake_hm = MagicMock()
        fake_hm.calculate_all_health.side_effect = RuntimeError("db down")
        monkeypatch.setattr(sched_mod, "health_monitor", fake_hm)

        assert health_scheduler.run_health_check() is None


# ═══════════════════════════════════════════════════════════════
# start / stop
# ═══════════════════════════════════════════════════════════════

class _FakeThread:
    """替身 threading.Thread: start/join 不真起线程。"""

    def __init__(self, *a, **kw):
        self.started = False
        self.joined = False

    def start(self):
        self.started = True

    def join(self, timeout=None):
        self.joined = True


class TestStartStop:

    def test_start_skips_when_already_running(self, monkeypatch):
        # running=True → 直接 return, schedule.every 不被调 (覆盖 line 83-85)
        fake_sched = MagicMock()
        monkeypatch.setattr(sched_mod, "schedule", fake_sched)
        health_scheduler.running = True

        health_scheduler.start(5)

        fake_sched.every.assert_not_called()
        # running 仍为 True (未重置)

    def test_start_registers_tasks_and_runs_immediately(self, monkeypatch):
        # 覆盖 line 87-108: 设 running, 注册 3 任务, 立即跑 health/maintenance, 起线程
        fake_sched = MagicMock()
        monkeypatch.setattr(sched_mod, "schedule", fake_sched)
        monkeypatch.setattr(sched_mod.threading, "Thread", _FakeThread)

        ran = {"health": False, "maintenance": False}
        monkeypatch.setattr(health_scheduler, "run_health_check",
                            lambda: ran.__setitem__("health", True))
        monkeypatch.setattr(health_scheduler, "run_maintenance_check",
                            lambda: ran.__setitem__("maintenance", True))

        health_scheduler.start(10)

        assert health_scheduler.running is True
        assert health_scheduler.thread is not None
        assert health_scheduler.thread.started is True
        # schedule.every 被调 3 次: health / escalation / maintenance
        assert fake_sched.every.call_count == 3
        # 立即执行了一次 health + maintenance
        assert ran["health"] is True
        assert ran["maintenance"] is True

    def test_stop_resets_state_and_joins_thread(self):
        thread = _FakeThread()
        health_scheduler.thread = thread
        health_scheduler.running = True

        health_scheduler.stop()

        assert health_scheduler.running is False
        assert thread.joined is True

    def test_stop_without_thread(self):
        # thread=None → 不 join, 仅复位 running (覆盖 line 113 if 判空)
        health_scheduler.thread = None
        health_scheduler.running = True
        health_scheduler.stop()
        assert health_scheduler.running is False


# ═══════════════════════════════════════════════════════════════
# 模块级 start/stop 转发函数
# ═══════════════════════════════════════════════════════════════

class TestModuleFunctions:

    def test_start_stop_delegate_to_singleton(self, monkeypatch):
        called = {"start": None, "stop": False}
        monkeypatch.setattr(health_scheduler, "start",
                            lambda interval_minutes=30: called.__setitem__("start", interval_minutes))
        monkeypatch.setattr(health_scheduler, "stop",
                            lambda: called.__setitem__("stop", True))

        start_health_scheduler(interval_minutes=7)
        stop_health_scheduler()

        assert called["start"] == 7
        assert called["stop"] is True

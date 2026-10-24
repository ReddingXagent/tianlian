"""test_scheduler.py — HealthScheduler 单元测试

被测对象: app/services/scheduler.py 的 HealthScheduler(健康度/告警升级/维护计划定时调度)。

纯逻辑测试: DB session、health_monitor、evaluate_all_rules、scan_and_escalate、
maintenance_schedule_checker、schedule 库、threading 全部用 MagicMock/patch 替换,
不创建真实 DB 连接, 不启动真实调度线程。

覆盖维度:
- run_escalation_scan: 成功/空结果/异常隔离。
- run_maintenance_check: 成功/异常隔离。
- run_health_check: 正常流程、有告警、有触发规则、异常返回 None 且 finally 关 db。
- start: 幂等(已运行直接返回)、注册 3 个定时任务、立即执行一次、启动调度线程。
- stop: 清 running 标志、join 线程(timeout=5)、无线程时安全。
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.scheduler import HealthScheduler


@pytest.fixture
def scheduler():
    """每个用例一个独立 HealthScheduler(running=False, thread=None)。"""
    return HealthScheduler()


# ═══════════════════════════════════════════════════════════════
# run_escalation_scan
# ═══════════════════════════════════════════════════════════════

class TestRunEscalationScan:
    def test_calls_scan_and_escalate(self, scheduler):
        with patch("app.services.scheduler.scan_and_escalate", return_value=[1, 2]) as mock:
            scheduler.run_escalation_scan()
            mock.assert_called_once()

    def test_empty_result_no_error(self, scheduler):
        with patch("app.services.scheduler.scan_and_escalate", return_value=[]):
            scheduler.run_escalation_scan()  # 不应抛异常

    def test_swallows_exception(self, scheduler):
        """scan_and_escalate 抛异常时, run_escalation_scan 内部捕获不外泄。"""
        with patch("app.services.scheduler.scan_and_escalate", side_effect=RuntimeError("db down")):
            scheduler.run_escalation_scan()  # 不应抛


# ═══════════════════════════════════════════════════════════════
# run_maintenance_check
# ═══════════════════════════════════════════════════════════════

class TestRunMaintenanceCheck:
    def test_calls_check_maintenance_schedule(self, scheduler):
        checker = MagicMock()
        checker.check_maintenance_schedule.return_value = ["dev1", "dev2"]
        with patch("app.services.scheduler.maintenance_schedule_checker", checker):
            scheduler.run_maintenance_check()
            checker.check_maintenance_schedule.assert_called_once()

    def test_empty_result_no_error(self, scheduler):
        checker = MagicMock()
        checker.check_maintenance_schedule.return_value = []
        with patch("app.services.scheduler.maintenance_schedule_checker", checker):
            scheduler.run_maintenance_check()

    def test_swallows_exception(self, scheduler):
        checker = MagicMock()
        checker.check_maintenance_schedule.side_effect = RuntimeError("fail")
        with patch("app.services.scheduler.maintenance_schedule_checker", checker):
            scheduler.run_maintenance_check()  # 不应抛


# ═══════════════════════════════════════════════════════════════
# run_health_check
# ═══════════════════════════════════════════════════════════════

class TestRunHealthCheck:
    def test_success_returns_true_and_closes_db(self, scheduler):
        db = MagicMock()
        hm = MagicMock()
        hm.calculate_all_health.return_value = ["d1"]
        hm.check_and_create_alarms.return_value = []
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules", return_value=[]), \
             patch.object(scheduler, "run_escalation_scan") as esc:
            result = scheduler.run_health_check()

        assert result is True
        hm.calculate_all_health.assert_called_once_with(db)
        hm.check_and_create_alarms.assert_called_once_with(db)
        esc.assert_called_once()
        db.close.assert_called_once()  # finally 关闭

    def test_with_alarms_logs_and_succeeds(self, scheduler):
        db = MagicMock()
        alarm = {"device": "INV1", "score": 80.0, "workorder_id": "WO-1"}
        hm = MagicMock()
        hm.calculate_all_health.return_value = ["d1"]
        hm.check_and_create_alarms.return_value = [alarm]
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules", return_value=[]), \
             patch.object(scheduler, "run_escalation_scan"):
            result = scheduler.run_health_check()

        assert result is True

    def test_with_triggered_rules_succeeds(self, scheduler):
        db = MagicMock()
        rule = {"triggered": True, "rule_name": "过温", "devices": ["d1", "d2"]}
        hm = MagicMock()
        hm.calculate_all_health.return_value = []
        hm.check_and_create_alarms.return_value = []
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules", return_value=[rule]), \
             patch.object(scheduler, "run_escalation_scan"):
            result = scheduler.run_health_check()

        assert result is True

    def test_untriggered_rule_not_logged_path(self, scheduler):
        """rule triggered=False → 不进 triggered 分支, 仍正常返回 True。"""
        db = MagicMock()
        rule = {"triggered": False, "rule_name": "x", "devices": []}
        hm = MagicMock()
        hm.calculate_all_health.return_value = []
        hm.check_and_create_alarms.return_value = []
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules", return_value=[rule]), \
             patch.object(scheduler, "run_escalation_scan"):
            result = scheduler.run_health_check()

        assert result is True

    def test_exception_returns_none_but_closes_db(self, scheduler):
        """中间步骤抛异常 → 返回 None, finally 仍关闭 db。"""
        db = MagicMock()
        hm = MagicMock()
        hm.calculate_all_health.return_value = []
        hm.check_and_create_alarms.return_value = []
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules",
                   side_effect=RuntimeError("boom")), \
             patch.object(scheduler, "run_escalation_scan"):
            result = scheduler.run_health_check()

        assert result is None
        db.close.assert_called_once()

    def test_calculate_all_health_exception_returns_none(self, scheduler):
        db = MagicMock()
        hm = MagicMock()
        hm.calculate_all_health.side_effect = RuntimeError("calc fail")
        with patch("app.services.scheduler.SessionLocal", return_value=db), \
             patch("app.services.scheduler.health_monitor", hm), \
             patch("app.services.scheduler.evaluate_all_rules"), \
             patch.object(scheduler, "run_escalation_scan"):
            result = scheduler.run_health_check()

        assert result is None
        db.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# start / stop
# ═══════════════════════════════════════════════════════════════

class TestStartStop:
    def test_start_idempotent_when_already_running(self, scheduler):
        """running=True 时 start 直接返回, 不重复注册任务/起线程。"""
        scheduler.running = True
        with patch("app.services.scheduler.schedule") as sched, \
             patch("app.services.scheduler.threading") as thread:
            scheduler.start()

            sched.every.assert_not_called()
            thread.Thread.assert_not_called()

    def test_start_registers_three_jobs_and_runs_immediately(self, scheduler):
        with patch("app.services.scheduler.schedule") as sched, \
             patch("app.services.scheduler.threading") as thread, \
             patch.object(scheduler, "run_health_check") as hc, \
             patch.object(scheduler, "run_maintenance_check") as mc:
            scheduler.start(interval_minutes=15)

            # 3 个定时任务: 健康检查(15min) + 升级扫描(5min) + 维护检查(60min)
            assert sched.every.call_count == 3
            # 立即执行一次健康检查与维护检查
            hc.assert_called_once()
            mc.assert_called_once()
            # 启动了调度线程
            thread.Thread.assert_called_once()
            thread.Thread.return_value.start.assert_called_once()
            assert scheduler.running is True

    def test_stop_resets_running_flag(self, scheduler):
        scheduler.running = True
        scheduler.thread = None

        scheduler.stop()

        assert scheduler.running is False

    def test_stop_joins_thread_with_timeout(self, scheduler):
        scheduler.running = True
        fake_thread = MagicMock()
        scheduler.thread = fake_thread

        scheduler.stop()

        fake_thread.join.assert_called_once_with(timeout=5)
        assert scheduler.running is False

    def test_stop_safe_when_no_thread(self, scheduler):
        scheduler.running = False
        scheduler.thread = None

        scheduler.stop()  # 不应抛异常

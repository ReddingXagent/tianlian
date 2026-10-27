"""卡5b218b9c: HealthScheduler stop() 不清 schedule jobs — start→stop→start 任务双倍注册"""
import schedule

from app.services.scheduler import HealthScheduler


def _make_scheduler(monkeypatch):
    s = HealthScheduler()
    monkeypatch.setattr(s, "run_health_check", lambda: None)
    monkeypatch.setattr(s, "run_maintenance_check", lambda: None)
    monkeypatch.setattr(s, "run_escalation_scan", lambda: None)
    return s


def test_start_stop_start_no_duplicate_jobs(monkeypatch):
    s = _make_scheduler(monkeypatch)
    try:
        s.start()
        s.stop()
        s.start()
        assert len(schedule.get_jobs()) == 3
        s.stop()
    finally:
        schedule.clear()


def test_stop_clears_jobs(monkeypatch):
    s = _make_scheduler(monkeypatch)
    try:
        s.start()
        assert len(schedule.get_jobs()) == 3
        s.stop()
        assert schedule.get_jobs() == []
    finally:
        schedule.clear()


def test_start_reentry_guard_keeps_three_jobs(monkeypatch):
    s = _make_scheduler(monkeypatch)
    try:
        s.start()
        s.start()  # 重入守卫：直接 return，不重复注册
        assert len(schedule.get_jobs()) == 3
        s.stop()
    finally:
        schedule.clear()

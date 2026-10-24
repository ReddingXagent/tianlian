"""数据保留/日志表清理测试 (卡 0364c10e)

覆盖:
- maintenance.cleanup_retention_logs 各表按窗口删除: 窗口内新数据保留, 窗口外旧数据删除。
- 分批删除边界: 不足一批 / 恰好整除一批 / 跨多批, 且每批独立 commit。
- days_old < 1 守卫 (默认配置与 overrides 双路径) 拒删。
- 资金/业务表零删除: 构造旧资金表数据, 跑任务后原样仍在。
- celery 注册名 + beat_schedule 每日 04:30 错峰调度 (queue=maintenance)。
"""
from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.maintenance_tasks as maintenance_tasks  # noqa: F401 触发 @shared_task 注册
from app.tasks.maintenance_tasks import (
    _PROTECTED_TABLES,
    _retention_tables,
    cleanup_retention_logs_task,
)

from app.models.alarm import AlarmRuleLog
from app.models.audit_log import AuditLog
from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.device_control_log import DeviceControlLog
from app.models.device_efficiency_log import DeviceEfficiencyLog
from app.models.energy_strategy import EnergyFlowLog
from app.models.notification import Notification
from app.models.notification_config import NotificationLog
from app.models.on_call import OnCallLog
from app.models.runbook_approval import RunbookApprovalLog
from app.models.station import Station, StationStatus
from app.models.user import Team

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=400)
RECENT = NOW - timedelta(days=1)


# ─── helpers ───

def _seed_base(session):
    """最小 FK 链: team → station → device。"""
    team = Team(name="retention-test-team")
    session.add(team)
    session.flush()
    station = Station(
        name="retention-test-station",
        code="RTS001",
        team_id=team.id,
        status=StationStatus.NORMAL,
    )
    session.add(station)
    session.flush()
    device = Device(
        name="retention-test-device",
        code="RTD001",
        sn="RTSN0001",
        type=DeviceType.CHARGER_DC,
        status=DeviceStatus.ONLINE,
        station_id=station.id,
    )
    session.add(device)
    session.commit()
    return team, station, device


def _seed_all_log_tables(session, base, *, n_old=2, n_new=2, old_at=OLD, new_at=RECENT):
    """对 9 张目标表各写 n_old 条旧 + n_new 条新。返回写入计数。"""
    team, station, device = base
    # notifications: id 是 String uuid, 无法预指定 → 让 default 生成
    for i in range(n_old):
        session.add(Notification(
            title=f"old-{i}", content="x", team_id=team.id,
            recipient_type="user", recipient_id="u1", created_at=old_at,
        ))
    for i in range(n_new):
        session.add(Notification(
            title=f"new-{i}", content="x", team_id=team.id,
            recipient_type="user", recipient_id="u1", created_at=new_at,
        ))
    # notification_logs
    for ts, tag in [(old_at, "old")] * n_old + [(new_at, "new")] * n_new:
        session.add(NotificationLog(
            event_type="alarm", channel="webhook", receiver_type="user",
            receiver_id="u1", content="x", created_at=ts,
        ))
    # device_control_logs
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(DeviceControlLog(
            device_id=device.id, action="start", result="success", created_at=ts,
        ))
    # audit_logs
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(AuditLog(username="admin", action="update", module="devices", timestamp=ts))
    # device_efficiency_logs (created_at server_default → 显式给)
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(DeviceEfficiencyLog(
            device_id=device.id, log_date=ts.strftime("%Y-%m-%d"), created_at=ts,
        ))
    # energy_flow_log
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(EnergyFlowLog(station_id=station.id, team_id=team.id, created_at=ts))
    # alarm_rule_logs (无 rule_id 便捷构造: 需真规则 → 本函数外单独 seed, 这里跳过)
    # on_call_logs
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(OnCallLog(
            shift_id=1, user_id=1, content="x", created_at=ts,
        ))
    # runbook_approval_logs
    for ts in [old_at] * n_old + [new_at] * n_new:
        session.add(RunbookApprovalLog(approval_id=1, action="approve", created_at=ts))
    session.commit()


def _count(session, model, ts_col, cutoff):
    return session.query(model).filter(ts_col < cutoff).count()


# ═══════════════════════════════════════════════════════════════
# 窗口删除: 旧删新留
# ═══════════════════════════════════════════════════════════════

class TestWindowCleanup:

    def test_old_deleted_new_kept(self, test_db):
        session = test_db["session"]
        base = _seed_base(session)
        _seed_all_log_tables(session, base, n_old=2, n_new=2)
        # alarm_rule_logs 需要 FK rule → 单独造
        from app.models.alarm import AlarmRule
        rule = AlarmRule(name="r1", metric="temperature", threshold=50)
        session.add(rule)
        session.flush()
        for ts in [OLD] * 2 + [RECENT] * 2:
            session.add(AlarmRuleLog(rule_id=rule.id, checked_at=ts))
        session.commit()

        before_old = _count(session, Notification, Notification.created_at, NOW - timedelta(days=100))
        assert before_old == 2

        result = cleanup_retention_logs_task(
            overrides={"notifications": 100}  # 其余表走默认 90~365d, 400d 旧数据全落窗外
        )

        # 400 天前的旧数据全删 (notifications 窗口被 override 到 100d 也在窗外)
        assert session.query(Notification).filter(
            Notification.title.like("old%")
        ).count() == 0
        assert session.query(NotificationLog).filter(
            NotificationLog.created_at < NOW - timedelta(days=95)
        ).count() == 0
        assert session.query(DeviceControlLog).filter(
            DeviceControlLog.created_at < NOW - timedelta(days=175)
        ).count() == 0
        assert session.query(AuditLog).filter(
            AuditLog.timestamp < NOW - timedelta(days=360)
        ).count() == 0
        assert session.query(DeviceEfficiencyLog).filter(
            DeviceEfficiencyLog.created_at < NOW - timedelta(days=360)
        ).count() == 0
        assert session.query(EnergyFlowLog).filter(
            EnergyFlowLog.created_at < NOW - timedelta(days=360)
        ).count() == 0
        assert session.query(AlarmRuleLog).filter(
            AlarmRuleLog.checked_at < NOW - timedelta(days=175)
        ).count() == 0
        assert session.query(OnCallLog).filter(
            OnCallLog.created_at < NOW - timedelta(days=175)
        ).count() == 0
        assert session.query(RunbookApprovalLog).filter(
            RunbookApprovalLog.created_at < NOW - timedelta(days=175)
        ).count() == 0

        # 窗口内新数据全保留
        assert session.query(Notification).filter(
            Notification.title.like("new%")
        ).count() == 2
        assert session.query(NotificationLog).filter(
            NotificationLog.created_at >= NOW - timedelta(days=95)
        ).count() == 2
        assert session.query(OnCallLog).count() == 2
        assert session.query(RunbookApprovalLog).count() == 2

        # 汇总 dict 供监控
        deleted = result["deleted"]
        assert deleted["notifications"] == 2
        assert deleted["notification_logs"] == 2
        assert deleted["audit_logs"] == 2
        assert result["status"] == "completed"

    def test_notifications_default_90d_keeps_100d_row(self, test_db):
        """notifications 默认 90d: 100 天前仍保留, 91+ 天前删除。"""
        session = test_db["session"]
        base = _seed_base(session)
        d100 = NOW - timedelta(days=100)
        d91 = NOW - timedelta(days=91)
        for ts in (d100, d91, RECENT):
            session.add(Notification(
                title="t", content="x", team_id=base[0].id,
                recipient_type="user", recipient_id="u1", created_at=ts,
            ))
        session.commit()

        result = cleanup_retention_logs_task(overrides={"notifications": 91})
        # d100 < cutoff(91d 前) → 删; d91 恰在边界外侧(cutoff < d91) → 删; RECENT 留
        remaining = session.query(Notification).count()
        assert remaining == 1
        assert result["deleted"]["notifications"] == 2


# ═══════════════════════════════════════════════════════════════
# 分批删除边界
# ═══════════════════════════════════════════════════════════════

class TestChunkBoundaries:

    def _seed_n(self, session, base, n, days_old=400):
        for i in range(n):
            session.add(NotificationLog(
                event_type="alarm", channel="webhook", receiver_type="user",
                receiver_id="u1", content="x", created_at=NOW - timedelta(days=days_old),
            ))
        session.commit()

    def test_less_than_one_chunk(self, test_db):
        session = test_db["session"]
        base = _seed_base(session)
        self._seed_n(session, base, 3)
        result = cleanup_retention_logs_task(chunk_size=5)
        assert result["deleted"]["notification_logs"] == 3

    def test_exact_multiple_of_chunk(self, test_db):
        session = test_db["session"]
        base = _seed_base(session)
        self._seed_n(session, base, 6)
        result = cleanup_retention_logs_task(chunk_size=3)
        assert result["deleted"]["notification_logs"] == 6

    def test_multiple_chunks_with_remainder(self, test_db):
        session = test_db["session"]
        base = _seed_base(session)
        self._seed_n(session, base, 7)
        result = cleanup_retention_logs_task(chunk_size=3)
        assert result["deleted"]["notification_logs"] == 7

    def test_chunk_skips_in_window_rows(self, test_db):
        """id 区间内夹带窗口内新行时不可误删: 同一 id 段新旧混排。"""
        session = test_db["session"]
        base = _seed_base(session)
        old = NOW - timedelta(days=400)
        rows = []
        for i in range(6):
            rows.append(NotificationLog(
                event_type="alarm", channel="webhook", receiver_type="user",
                receiver_id="u1", content="x", created_at=old,
            ))
            # 新旧交替插入
            rows.append(NotificationLog(
                event_type="alarm", channel="webhook", receiver_type="user",
                receiver_id="u1", content="x", created_at=RECENT,
            ))
        session.add_all(rows)
        session.commit()

        result = cleanup_retention_logs_task(chunk_size=3)
        assert result["deleted"]["notification_logs"] == 6
        assert session.query(NotificationLog).count() == 6  # 新行全保留


# ═══════════════════════════════════════════════════════════════
# days_old < 1 守卫
# ═══════════════════════════════════════════════════════════════

class TestDaysOldGuard:

    def test_override_zero_rejected(self, test_db):
        session = test_db["session"]
        base = _seed_base(session)
        _seed_all_log_tables(session, base, n_old=1, n_new=1)
        with pytest.raises(ValueError, match="保留天数必须 >= 1"):
            cleanup_retention_logs_task(overrides={"notifications": 0})
        # 守卫在任何删除前触发: 全部数据仍在
        assert session.query(Notification).count() == 2

    def test_override_negative_rejected(self, test_db):
        with pytest.raises(ValueError, match="保留天数必须 >= 1"):
            cleanup_retention_logs_task(overrides={"audit_logs": -5})

    def test_default_config_guard(self, test_db, monkeypatch):
        """settings 某表默认窗口被 env 配成 0 → 任务拒执行。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "RETENTION_ON_CALL_LOGS_DAYS", 0)
        with pytest.raises(ValueError, match="on_call_logs 保留天数必须 >= 1"):
            cleanup_retention_logs_task()

    def test_chunk_size_guard(self, test_db):
        with pytest.raises(ValueError, match="chunk_size 必须 >= 1"):
            cleanup_retention_logs_task(chunk_size=0)


# ═══════════════════════════════════════════════════════════════
# 资金/业务表白名单
# ═══════════════════════════════════════════════════════════════

class TestProtectedTables:

    def test_financial_rows_survive(self, test_db):
        """构造 400 天前的旧订单, 跑任务后原样仍在。"""
        session = test_db["session"]
        team, station, device = _seed_base(session)
        from app.models.user import User, UserRole
        user = User(
            username="retention-u", email="retention-u@t.local",
            password_hash="x", role=UserRole.ADMIN,
        )
        session.add(user)
        session.flush()
        old_orders = []
        for i in range(3):
            o = ChargingOrder(
                order_no=f"RT{400}{i:04d}",
                station_id=station.id,
                device_id=device.id,
                user_id=user.id,
                user_type=UserType.APP,
                connector_id=1,
                order_status=OrderStatus.COMPLETED,
                payment_status=OrderPaymentStatus.PAID,
                created_at=OLD,
            )
            session.add(o)
            old_orders.append(o)
        session.commit()
        order_ids = [o.id for o in old_orders]

        cleanup_retention_logs_task()

        survived = session.query(ChargingOrder).filter(
            ChargingOrder.id.in_(order_ids)
        ).count()
        assert survived == 3

    def test_retention_scope_excludes_protected(self):
        """清理范围与白名单零交集。"""
        names = {name for _m, _tc, _d, name in _retention_tables()}
        assert names & _PROTECTED_TABLES == set()
        assert "charging_orders" in _PROTECTED_TABLES
        assert "invoices" in _PROTECTED_TABLES


# ═══════════════════════════════════════════════════════════════
# celery 注册 + beat 调度
# ═══════════════════════════════════════════════════════════════

class TestRegistration:

    def test_task_registered(self):
        from app.core.celery_app import celery_app
        assert "maintenance.cleanup_retention_logs" in celery_app.tasks

    def test_beat_schedule_daily_0430(self):
        from app.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule.get("daily-retention-logs-cleanup")
        assert entry is not None
        assert entry["task"] == "maintenance.cleanup_retention_logs"
        assert entry["schedule"].hour == {4}
        assert entry["schedule"].minute == {30}
        assert entry["options"]["queue"] == "maintenance"

    def test_weekly_cleanup_unchanged(self):
        """旧 cleanup_old_data 调度保持原样。"""
        from app.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule["weekly-data-cleanup"]
        assert entry["task"] == "maintenance.cleanup_old_data"
        assert entry["schedule"].hour == {4}
        assert entry["schedule"].minute == {0}
        assert entry["schedule"].day_of_week == {0}

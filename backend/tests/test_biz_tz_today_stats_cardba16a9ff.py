#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5 处 UTC 日界 today 统计改业务时区 (上海日界) 回归测试 (卡 ba16a9ff)

被测:
1. app/api/v1/fleet_charging_policies.py _today_used_kwh   — 窗口类 (biz_day_bounds)
2. app/services/stats_service.py _utc_today                — 日期比较类 (func.date == 业务今天)
3. app/api/v1/dashboard.py today_new_alarms                — 窗口类
4. app/api/v1/notifications.py sent_today                  — 日期比较类
5. app/services/audit_service.py today_logs                — 日期比较类

模式对齐 tests/test_alarms.py test_today_total_uses_biz_today (卡 48bc65fe):
monkeypatch 模块内 today_in_biz_tz 固定业务今天, seed 一条 created_at=业务今天
(UTC 视角=业务昨天) 的记录, 断言仍计入 —— 证明日期基准已切业务时区。
窗口类 (1/3) 用 biz_day_bounds_utc_naive 换算边界 seed, 断言上海 00:00-08:00
(UTC 前日 16:00-24:00) 的记录计入今日窗。

已知局限 (与 alarms 相同, 本卡范围外): 日期比较类 func.date(UTC时间戳)=UTC 日,
上海 00:00-08:00 写入的记录 func.date=业务昨天, 仍漏计; 彻底修复需 DB 层时区转换。
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.tasks.tz_utils import biz_day_bounds_utc_naive

BIZ_TODAY = date(2026, 8, 7)   # 业务(上海)今天
UTC_YESTERDAY = date(2026, 8, 6)  # 同时刻的 UTC 昨天 (上海 00-08 点窗口)


# ═══════════════════════════════════════════════════════════
# 1. fleet _today_used_kwh — 窗口类 (上海日界)
# ═══════════════════════════════════════════════════════════

class TestFleetTodayUsedKwhBizDayWindow:
    def _seed(self, db_session):
        from app.models.enterprise import Enterprise
        from app.models.enterprise_vehicle import EnterpriseVehicle
        ent = Enterprise(name="日界测试企业", code="TZ_BA16", balance=0.0)
        db_session.add(ent)
        db_session.flush()
        v = EnterpriseVehicle(enterprise_id=ent.id, plate_number="沪A000TZ",
                              vin="LSVTZ000000000001")
        db_session.add(v)
        db_session.commit()
        return ent.id, v.id

    def _order(self, db_session, vid, kwh, created_at, tag):
        from app.models.charging_order import ChargingOrder, OrderStatus
        db_session.add(ChargingOrder(
            order_no=f"NO-TZ-{tag}", station_id=1, device_id=1, vehicle_id=vid,
            charged_kwh=Decimal(str(kwh)), order_status=OrderStatus.COMPLETED,
            created_at=created_at,
        ))
        db_session.commit()

    def test_shanghai_early_am_counts_today(self, client, db_session, monkeypatch):
        """上海 1/7 00:30 (UTC 1/6 16:30) 计入业务今天窗 — 旧 UTC 零点窗会漏计"""
        from app.api.v1 import fleet_charging_policies as mod
        ent_id, vid = self._seed(db_session)
        # 上海 1/7 00:30 = UTC 1/6 16:30 (UTC 视角昨天) → 业务今天
        self._order(db_session, vid, 100.0,
                    datetime(2026, 8, 6, 16, 30, tzinfo=timezone.utc), "early-am")
        # 上海 1/6 23:00 = UTC 1/6 15:00 → 业务昨天
        self._order(db_session, vid, 999.0,
                    datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc), "yest-eve")

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        used = mod._today_used_kwh(db_session, ent_id)
        assert used == 100.0

    def test_daily_limit_breaker_uses_biz_day_window(self, client, db_session, monkeypatch):
        """日限额熔断走业务日窗: 上海凌晨订单达限即拒 (旧窗错 8h 放行)"""
        from app.api.v1 import fleet_charging_policies as mod
        ent_id, vid = self._seed(db_session)
        # 上海 1/7 00:10 = UTC 1/6 16:10 已充 520 (超 500 限)
        self._order(db_session, vid, 520.0,
                    datetime(2026, 8, 6, 16, 10, tzinfo=timezone.utc), "breaker")
        db_session.add(mod.FleetChargingPolicy(
            enterprise_id=ent_id, daily_kwh_limit=500.0,
            allowed_time_slots=[], allowed_station_ids=None, enable=True))
        db_session.commit()

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        used = mod._today_used_kwh(db_session, ent_id)
        assert used == 520.0  # 达限 → check 端点 213 行熔断生效


# ═══════════════════════════════════════════════════════════
# 2. stats_service today_completed — 日期比较类
# ═══════════════════════════════════════════════════════════

class TestStatsTodayCompletedBizDay:
    def test_counts_biz_today_not_utc_today(self, test_db, monkeypatch):
        """日期基准=业务今天: finish_time 落在业务今天的 UTC 日即计入。

        seed: 上海 1/7 10:00 (UTC 1/7 02:00, func.date=业务今天)。
        旧 UTC 基准下若当前真实 UTC 日 != 2026-08-07 则该单会被漏计
        (monkeypatch 固定业务今天, UTC today 恒不等于 2026-08-07 → 证明基准已切)。
        """
        from app.core.cache import clear_memory_cache
        from app.models.workorder import WorkOrder, WorkOrderStatus
        from app.services import stats_service as mod
        from app.services.stats_service import stats_service

        clear_memory_cache()
        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        db = test_db["session"]
        # 上海 1/7 10:00 = UTC 1/7 02:00 → func.date = 业务今天
        db.add(WorkOrder(
            id="WO-biz-today", status=WorkOrderStatus.COMPLETED,
            finish_time=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
        ))
        # UTC 日 = 业务昨天的完工单不计入 (上海 1/6 18:00 = UTC 1/6 10:00)
        db.add(WorkOrder(
            id="WO-biz-yest", status=WorkOrderStatus.COMPLETED,
            finish_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
        ))
        db.commit()
        result = stats_service.get_dashboard_overview()
        assert result["workorders"]["today_completed"] == 1
        clear_memory_cache()


# ═══════════════════════════════════════════════════════════
# 3. dashboard today_new_alarms — 窗口类
# ═══════════════════════════════════════════════════════════

class TestDashboardTodayNewAlarmsBizDay:
    def test_shanghai_early_am_alarm_counted(self, client, seed_devices, monkeypatch):
        """上海 1/7 00:30 (UTC 1/6 16:30) 的新告警计入 today_new_alarms"""
        from app.api.v1 import dashboard as mod
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

        day_start, _ = biz_day_bounds_utc_naive(BIZ_TODAY)
        s = client._sesh
        dev = seed_devices["inv001"]
        s.add(Alarm(
            device_id=dev.id, station_id=dev.station_id,
            alarm_type="tz_probe", level=AlarmLevel.WARNING,
            content="日界探针", status=AlarmStatus.ACTIVE,
        ))
        s.commit()
        # 窗首 +30min: 上海 1/7 00:30 (UTC 1/6 16:30, 旧 UTC 窗外)
        s.execute(update(Alarm)
                  .where(Alarm.alarm_type == "tz_probe")
                  .values(created_at=day_start + timedelta(minutes=30)))
        s.commit()

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        r = client.get("/api/v1/dashboard/large-screen")
        assert r.status_code == 200
        assert r.json()["alarm_stats"]["today_new"] == 1
        assert r.json()["workorder_stats"]["today_new_alarms"] == 1


# ═══════════════════════════════════════════════════════════
# 4. notifications sent_today — 日期比较类
# ═══════════════════════════════════════════════════════════

class TestNotificationSentTodayBizDay:
    def test_biz_today_log_counted(self, client, db_session, monkeypatch):
        """created_at=业务今天的 UTC 日 (上海 1/7 10:00 = UTC 1/7 02:00) 计入 sent_today"""
        from app.api.v1 import notifications as mod
        from app.models.notification_config import NotificationLog
        from sqlalchemy import update as sa_update

        log = NotificationLog(
            event_type="manual", channel="sms", receiver_type="user",
            receiver_id="user:tz", subject="tz", content="tz", status="sent",
        )
        db_session.add(log)
        db_session.commit()
        # 上海 1/7 10:00 = UTC 1/7 02:00 → func.date = 业务今天
        db_session.execute(sa_update(NotificationLog)
                           .where(NotificationLog.id == log.id)
                           .values(created_at=datetime(2026, 8, 7, 2, 0)))
        db_session.commit()

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        r = client.get("/api/v1/notifications/stats")
        assert r.status_code == 200
        assert r.json()["data"]["sent_today"] == 1


# ═══════════════════════════════════════════════════════════
# 5. audit today_logs — 日期比较类
# ═══════════════════════════════════════════════════════════

class TestAuditTodayLogsBizDay:
    def test_biz_today_log_counted(self, db_session, monkeypatch):
        """timestamp=业务今天的 UTC 日 (上海 1/7 10:00 = UTC 1/7 02:00) 计入 today_logs"""
        from app.services import audit_service as mod
        from app.services.audit_service import AuditService
        from app.models.audit_log import AuditLog

        log = AuditLog(action="login", module="auth", username="tz-probe")
        db_session.add(log)
        db_session.commit()
        # 上海 1/7 10:00 = UTC 1/7 02:00 → func.date = 业务今天
        db_session.execute(update(AuditLog)
                           .where(AuditLog.id == log.id)
                           .values(timestamp=datetime(2026, 8, 7, 2, 0)))
        db_session.commit()

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        stats = AuditService().get_stats(db=db_session)
        assert stats["today_logs"] == 1

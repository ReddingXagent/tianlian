#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UTC 日桶残留三处改上海墙钟日界 回归测试 (卡 77b1ed08)

被测:
1. app/api/v1/fleet_v2g.py records 日期范围过滤 — 旧 func.date(created_at)
   (UTC 日)比较, 上海 00:00-08:00 窗口错位 8h
2. app/api/v1/predictive_maintenance.py history 日聚合分桶 — 旧
   func.date(timestamp) 桶界=上海 08:00 而非 00:00
3. app/api/v1/system_config/audit.py logs/stats 今日统计 — 旧
   datetime.now(timezone.utc).date() 取 UTC 日

模式对齐 tests/test_biz_tz_today_stats_cardba16a9ff.py:
seed 一条落库时间为 UTC 前日 16:00-24:00 (即上海 00:00-08:00) 的记录,
断言其按业务日归属 (计入业务今天/今天窗/今天桶), 证明日界已切上海墙钟。
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import update

BIZ_TODAY = date(2026, 8, 7)   # 业务(上海)今天
UTC_YESTERDAY = date(2026, 8, 6)  # 同时刻的 UTC 昨天


def _auth_headers(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    token = resp.json().get("token") or resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════
# 1. fleet_v2g records — 日期范围过滤走业务日闭开窗
# ═══════════════════════════════════════════════════════════

class TestV2GRecordsBizDayWindow:
    def _seed_enterprise(self, db_session):
        from app.models.enterprise import Enterprise
        ent = Enterprise(name="日界测试企业77b1", code="TZ_77B1", balance=0.0)
        db_session.add(ent)
        db_session.commit()
        return ent.id

    def _seed_log(self, db_session, created_at, tag):
        from app.models.v2g_dispatch import V2GDispatchLog
        db_session.add(V2GDispatchLog(
            device_id=1, dispatch_type="discharge",
            target_power_kw=50.0, actual_power_kw=48.5, status="completed",
            start_at=created_at, end_at=created_at + timedelta(hours=1),
            created_at=created_at,
        ))
        db_session.commit()

    def test_shanghai_early_am_in_biz_day_window(self, client, db_session):
        """上海 8/7 00:30 (UTC 8/6 16:30) 计入业务日 8/7 查询窗 — 旧 UTC 日过滤漏计"""
        ent_id = self._seed_enterprise(db_session)
        # 上海 8/7 00:30 = UTC 8/6 16:30 (UTC 视角昨天) → 业务今天
        self._seed_log(db_session, datetime(2026, 8, 6, 16, 30), "early-am")
        # 上海 8/6 23:00 = UTC 8/6 15:00 → 业务昨天
        self._seed_log(db_session, datetime(2026, 8, 6, 15, 0), "yest-eve")
        # 上海 8/8 00:00 = UTC 8/7 16:00 → 业务明天 (end_date 半开窗排除)
        self._seed_log(db_session, datetime(2026, 8, 7, 16, 0), "tomorrow-am")

        r = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}"
            "&start_date=2026-08-07&end_date=2026-08-07",
            headers=_auth_headers(client),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["created_at"].startswith("2026-08-06T16:30")

    def test_start_date_only_excludes_prior_biz_day(self, client, db_session):
        """仅 start_date: 上海 8/6 深夜 (UTC 8/6 15:00) 排除在 8/7 窗外"""
        ent_id = self._seed_enterprise(db_session)
        self._seed_log(db_session, datetime(2026, 8, 6, 15, 0), "yest-eve")
        self._seed_log(db_session, datetime(2026, 8, 6, 16, 30), "early-am")
        r = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}&start_date=2026-08-07",
            headers=_auth_headers(client),
        )
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1


# ═══════════════════════════════════════════════════════════
# 2. predictive_maintenance history — 日桶按上海墙钟切界
# ═══════════════════════════════════════════════════════════

class TestPredictiveHistoryBizDayBucket:
    def test_shanghai_midnight_boundary_splits_buckets(self, client, db_session):
        """上海 00:00 桶界: 窗首+30min 归今天桶, 窗首-30min 归昨天桶 (旧 UTC 界=上海 08:00 会同桶)"""
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        from app.models.telemetry import Telemetry
        from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz

        biz_today = today_in_biz_tz()
        day_start, _ = biz_day_bounds_utc_naive(biz_today)

        station = Station(name="日界测试站", code="STA_TZ_77B1", status=StationStatus.NORMAL)
        db_session.add(station)
        db_session.flush()
        device = Device(
            sn="SN-TZ-77B1", name="日界桩", code="TZ77B1",
            type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE,
            station_id=station.id, rated_power=120.0,
        )
        db_session.add(device)
        db_session.flush()

        # 上海今天 00:30 (UTC 视角业务昨天) → 业务今天桶
        db_session.add(Telemetry(
            device_id=device.id, timestamp=day_start + timedelta(minutes=30),
            battery_soc=80.0, battery_temperature=25.0, bms_alarm_word=0,
        ))
        # 上海昨天 23:30 → 业务昨天桶
        db_session.add(Telemetry(
            device_id=device.id, timestamp=day_start - timedelta(minutes=30),
            battery_soc=60.0, battery_temperature=24.0, bms_alarm_word=0,
        ))
        db_session.commit()

        r = client.get(
            f"/api/v1/predictive-maintenance/device/{device.id}/history?days=7",
            headers=_auth_headers(client),
        )
        assert r.status_code == 200, r.text
        history = r.json()["history"]
        dates = [h["date"] for h in history]
        assert dates.count(biz_today.isoformat()) == 1
        assert (biz_today - timedelta(days=1)).isoformat() in dates
        # 今天桶只含 00:30 那条
        today_bucket = next(h for h in history if h["date"] == biz_today.isoformat())
        assert today_bucket["record_count"] == 1


# ═══════════════════════════════════════════════════════════
# 3. system_config/audit stats — 今日统计走业务日窗
# ═══════════════════════════════════════════════════════════

class TestAuditStatsBizDayToday:
    def test_shanghai_early_am_counted_today(self, client, db_session, monkeypatch):
        """上海 8/7 00:30 (UTC 8/6 16:30) 的审计日志计入 today_logs — 旧 UTC 日恒漏计"""
        from app.api.v1.system_config import audit as mod
        from app.models.audit_log import AuditLog

        log = AuditLog(action="login", module="auth", username="tz-77b1")
        db_session.add(log)
        db_session.commit()
        db_session.execute(update(AuditLog)
                           .where(AuditLog.id == log.id)
                           .values(timestamp=datetime(2026, 8, 6, 16, 30)))
        db_session.commit()

        monkeypatch.setattr(mod, "today_in_biz_tz", lambda: BIZ_TODAY, raising=False)
        r = client.get("/api/v1/system-config/audit/logs/stats",
                       headers=_auth_headers(client))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["today_logs"] == 1

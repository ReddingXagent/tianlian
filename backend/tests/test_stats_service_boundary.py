#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stats_service 真实 DB 边界测试

被测: app/services/stats_service.py
设计: 用 test_db 真实 SQLite 库 seed 精确时间戳数据, 覆盖 MagicMock 无法验证的
       SQL 语义 (filter 的 == / order_by DESC 的取值), 每测试前清 @cached 缓存。
覆盖:
- 缺陷2: 健康趋势回退分支按日 func.date == 当日 (非 <= 累计)
- 缺陷3: 单日多条健康记录取最新 (created_at DESC) 而非 .first() 任取
- 缺陷4: today_completed 用 UTC 日期与 UTC 存储 finish_time 对齐 (契约固化)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.cache import clear_memory_cache
from app.models.station import Station
from app.models.device import Device, DeviceHealthRecord
from app.models.workorder import WorkOrder, WorkOrderStatus
from app.services.stats_service import stats_service

UTC = timezone.utc


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_memory_cache()
    yield
    clear_memory_cache()


def _seed_station(db, code):
    st = Station(name=code, code=code, status="normal")
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def _utc_midnight(offset_days):
    """today(UTC) + offset 天 的 00:00 UTC datetime。"""
    today = datetime.now(UTC).date()
    return datetime.combine(today + timedelta(days=offset_days), datetime.min.time(), UTC)


# ═══════════════════════════════════════════════════════════
# 缺陷2: 趋势回退分支按日 (==) 非累计 (<=)
# ═══════════════════════════════════════════════════════════

class TestHealthTrendPerDay:
    def test_scores_are_per_day_not_cumulative(self, test_db):
        db = test_db["session"]
        st = _seed_station(db, "st-cumulative")
        db.add(Device(sn="d2", name="d2", code="c2", type="pv_inverter",
                      status="online", station_id=st.id,
                      health_score=50.0, updated_at=_utc_midnight(-2)))
        db.add(Device(sn="d1", name="d1", code="c1", type="pv_inverter",
                      status="online", station_id=st.id,
                      health_score=90.0, updated_at=_utc_midnight(-1)))
        db.commit()

        trend = stats_service.get_health_trend(days=3)
        # 索引 [today-2, today-1, today]
        assert trend[0]["score"] == 50.0   # 仅 today-2 的设备
        # 仅 today-1 的设备(90); 旧代码 <= 累计会把 today-2(50) 也纳入 -> (50+90)/2=70
        assert trend[1]["score"] == 90.0
        assert trend[2]["score"] is None   # 今日无设备更新


# ═══════════════════════════════════════════════════════════
# 缺陷3: 单日多条健康记录取最新
# ═══════════════════════════════════════════════════════════

class TestHealthTrendLatestRecord:
    def test_picks_latest_when_multiple_same_day(self, test_db):
        db = test_db["session"]
        st = _seed_station(db, "st-latest")
        dev = Device(sn="d0", name="d0", code="c0", type="pv_inverter",
                     status="online", station_id=st.id, health_score=100.0)
        db.add(dev)
        db.commit()
        db.refresh(dev)
        day = _utc_midnight(-1)
        db.add(DeviceHealthRecord(device_id=dev.id, total_score=70.0, created_at=day))
        db.add(DeviceHealthRecord(device_id=dev.id, total_score=90.0,
                                  created_at=day + timedelta(hours=2)))
        db.commit()

        trend = stats_service.get_health_trend(days=2)
        # 索引 [today-1, today]; today-1 命中健康记录
        assert trend[0]["score"] == 90.0   # 取最新; 旧 .first() 无 order_by 任取可能得 70


# ═══════════════════════════════════════════════════════════
# 缺陷4: today_completed UTC 契约固化
# ═══════════════════════════════════════════════════════════

class TestTodayCompletedUtcContract:
    def test_counts_only_utc_today_finished(self, test_db):
        """today_completed 口径改业务日 (卡 ba16a9ff): seed 锚定业务今天。

        旧 seed 锚 UTC today, 上海 16:00-24:00 窗口业务日已翻日 → func.date=UTC昨天
        漏计 (日期敏感腐烂, 翻转 seed 非断言)。func.date(UTC时间戳) 仍取 UTC 日,
        故 seed 落业务今天的 UTC 日内 (func.date == 业务今天)。
        """
        from app.tasks.tz_utils import today_in_biz_tz
        db = test_db["session"]
        today = today_in_biz_tz()
        # W1: 业务今日完工 (UTC 日=业务今天) -> 计入
        db.add(WorkOrder(
            id="WO-utc-today", status=WorkOrderStatus.COMPLETED,
            finish_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=12),
        ))
        # W2: 业务昨日完工 -> 不计入
        db.add(WorkOrder(
            id="WO-utc-yest", status=WorkOrderStatus.COMPLETED,
            finish_time=datetime.combine(today - timedelta(days=1), datetime.min.time())
            + timedelta(hours=12),
        ))
        db.commit()

        result = stats_service.get_dashboard_overview()
        # finish_time 以 UTC 存储, 日期基准取业务今天, func.date 侧同为 UTC 日 -> 仅 W1
        assert result["workorders"]["today_completed"] == 1

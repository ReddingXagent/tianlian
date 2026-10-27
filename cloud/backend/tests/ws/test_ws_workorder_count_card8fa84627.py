#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试 (卡8fa84627): get_workorder_updates 样本截断统计缺陷。

原实现 query(WorkOrder).limit(20).all() 后 len() 逐条数, 工单超 20 条后
pending/processing/completed/today_new 全部封顶 20。改为 func.count 条件
聚合 (同 get_dashboard_stats 卡8035bd65 模式) 后:
  - 25 条工单 (12 pending / 8 processing / 5 completed) 计数精确;
  - 空表全零;
  - today_new 按 create_time >= 当日 UTC 零点口径, 跨 UTC 日界正确划分。

同 test_ws_offload_card8035bd65: realtime_handler 模块级 SessionLocal
import 按值绑定, 需 monkeypatch 指向测试库。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import database as db_module
import app.ws.realtime_handler as rt_mod
from app.ws.realtime_handler import RealtimeDataHandler
from app.models.workorder import WorkOrder, WorkOrderStatus


@pytest.fixture(autouse=True)
def _setup(test_db, monkeypatch):
    # 卡 a579f89e: realtime_handler 改经 db_module.SessionLocal 运行时属性读取,
    # test_db 对模块级 SessionLocal 的覆盖自动传播, 无需再 patch rt_mod
    pass


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _today_utc_midnight():
    now = _utc_now()
    return now.replace(hour=0, minute=0, second=0)


def _add(db, n, status, create_time=None):
    for i in range(n):
        db.add(WorkOrder(id=f"{status.value}-{i}", status=status, create_time=create_time))


def test_workorder_updates_empty_table_all_zero():
    result = RealtimeDataHandler().get_workorder_updates()
    assert result == {"pending": 0, "processing": 0, "completed": 0, "today_new": 0}


def test_workorder_updates_exact_counts_beyond_20():
    """25 条 (>limit 20): 旧实现封顶 20, 新实现精确 12/8/5。"""
    db = db_module.SessionLocal()
    try:
        today = _today_utc_midnight() + timedelta(hours=1)
        _add(db, 12, WorkOrderStatus.PENDING, today)
        _add(db, 8, WorkOrderStatus.PROCESSING, today)
        _add(db, 5, WorkOrderStatus.COMPLETED, today)
        db.commit()
    finally:
        db.close()

    result = RealtimeDataHandler().get_workorder_updates()
    assert result == {"pending": 12, "processing": 8, "completed": 5, "today_new": 25}


def test_workorder_updates_today_new_utc_day_boundary():
    """today_new 口径: create_time >= 当日 UTC 零点 (跨 UTC 日界)。"""
    midnight = _today_utc_midnight()
    db = db_module.SessionLocal()
    try:
        # UTC 日界两侧各一条 (同状态, 排除状态计数干扰)
        db.add(WorkOrder(id="today", status=WorkOrderStatus.PENDING,
                         create_time=midnight + timedelta(seconds=1)))
        db.add(WorkOrder(id="yesterday", status=WorkOrderStatus.PENDING,
                         create_time=midnight - timedelta(seconds=1)))
        db.commit()
        db.commit()
    finally:
        db.close()

    result = RealtimeDataHandler().get_workorder_updates()
    assert result["today_new"] == 1
    assert result["pending"] == 2

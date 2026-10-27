#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试 (卡51cdf2e4): get_dashboard_stats today_completed 口径缺陷 + manager.disconnect 空键泄漏。

原实现 wo_completed_today 仅 filter status==COMPLETED, 无日期过滤, 'today_completed'
字段实为历史完成总数。改为 finish_time >= 当日 UTC 零点 (同 get_workorder_updates
today_new 口径, 卡8fa84627) 后:
  - 昨日完成不计, 今日完成计, COMPLETED 但 finish_time=NULL 不计;
  - 空表全零。

manager.disconnect: device_subscriptions / station_connections discard 后空 set
须 del 键, 防长运行服务 dict 无限增长。

同 test_ws_workorder_count_card8fa84627: realtime_handler 模块级 SessionLocal
import 按值绑定, 需 monkeypatch 指向测试库。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import database as db_module
import app.ws.realtime_handler as rt_mod
from app.ws.realtime_handler import RealtimeDataHandler
from app.models.workorder import WorkOrder, WorkOrderStatus
from app.ws import ws_manager as manager


@pytest.fixture(autouse=True)
def _setup(test_db, monkeypatch):
    # 卡 a579f89e: realtime_handler 改经 db_module.SessionLocal 运行时属性读取,
    # test_db 对模块级 SessionLocal 的覆盖自动传播, 无需再 patch rt_mod
    pass


def _today_utc_midnight():
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    return now.replace(hour=0, minute=0, second=0)


def test_dashboard_today_completed_only_counts_today_finished():
    """今日完成=1; 昨日完成/今日pending/finish_time=NULL 的 COMPLETED 均不计。"""
    midnight = _today_utc_midnight()
    db = db_module.SessionLocal()
    try:
        db.add(WorkOrder(id="done-today", status=WorkOrderStatus.COMPLETED,
                         create_time=midnight + timedelta(hours=1),
                         finish_time=midnight + timedelta(hours=2)))
        db.add(WorkOrder(id="done-yesterday", status=WorkOrderStatus.COMPLETED,
                         create_time=midnight - timedelta(hours=5),
                         finish_time=midnight - timedelta(seconds=1)))
        db.add(WorkOrder(id="done-null-finish", status=WorkOrderStatus.COMPLETED,
                         create_time=midnight + timedelta(hours=1),
                         finish_time=None))
        db.add(WorkOrder(id="pending-today", status=WorkOrderStatus.PENDING,
                         create_time=midnight + timedelta(hours=1)))
        db.commit()
    finally:
        db.close()

    result = RealtimeDataHandler().get_dashboard_stats()
    assert result["workorders"]["today_completed"] == 1
    assert result["workorders"]["pending"] == 1


def test_dashboard_empty_table_all_zero():
    result = RealtimeDataHandler().get_dashboard_stats()
    assert result["workorders"] == {"pending": 0, "processing": 0, "today_completed": 0}


def test_manager_disconnect_cleans_empty_keys():
    """断开后空 set 键被清理, dict 不残留。"""
    manager.station_connections["st-1"] = set()
    manager.device_subscriptions["dev-1"] = set()

    class _FakeWS:
        pass

    ws = _FakeWS()
    manager.connection_metadata[ws] = {"channel": "realtime", "station_id": "st-1"}
    manager.station_connections["st-1"].add(ws)
    manager.device_subscriptions["dev-1"].add(ws)

    manager.disconnect(ws)

    assert "st-1" not in manager.station_connections
    assert "dev-1" not in manager.device_subscriptions

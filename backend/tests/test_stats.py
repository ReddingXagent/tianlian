#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据看板 Stats API 测试
总览+趋势+设备健康+工单告警统计
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup(test_db):
    pass

def test_stats_overview():
    """获取仪表盘总览"""
    resp = client.get("/api/v1/stats/overview")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data") or {}
    assert len(result) > 0

def test_health_trend():
    """获取健康度趋势"""
    resp = client.get("/api/v1/stats/health-trend?days=7")
    assert resp.status_code == 200

def test_health_trend_default():
    """获取健康度趋势(默认参数)"""
    resp = client.get("/api/v1/stats/health-trend")
    assert resp.status_code == 200

def test_health_trend_custom_days():
    """获取健康度趋势(自定义天数)"""
    resp = client.get("/api/v1/stats/health-trend?days=30")
    assert resp.status_code == 200

def test_alarm_stats():
    """获取告警统计"""
    resp = client.get("/api/v1/stats/alarm-stats?days=7")
    assert resp.status_code == 200

def test_alarm_stats_default():
    """获取告警统计(默认参数)"""
    resp = client.get("/api/v1/stats/alarm-stats")
    assert resp.status_code == 200

def test_workorder_stats():
    """获取工单统计"""
    resp = client.get("/api/v1/stats/workorder-stats?days=7")
    assert resp.status_code == 200

def test_alarm_trend():
    """获取告警趋势"""
    resp = client.get("/api/v1/stats/alarms/trend?days=7")
    assert resp.status_code == 200

def test_workorder_summary():
    """获取工单统计汇总"""
    resp = client.get("/api/v1/stats/workorders/summary?days=7")
    assert resp.status_code == 200

def test_devices_health():
    """获取设备健康度分布"""
    resp = client.get("/api/v1/stats/devices/health")
    assert resp.status_code == 200
    data = resp.json().get("data") or {}
    devices = data.get("devices") or []
    assert len(devices) > 0
    names = [d.get("name") for d in devices]
    assert "正常" in names

def test_station_rank():
    """获取站点评分排行"""
    resp = client.get("/api/v1/stats/stations/rank")
    assert resp.status_code == 200

def test_engineer_performance():
    """获取工程师绩效排名"""
    resp = client.get("/api/v1/stats/engineer-performance")
    assert resp.status_code == 200

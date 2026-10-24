#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据大屏独立展示模式 API 测试
覆盖: /dashboard/large-screen
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


# ========== 鉴权检查 ==========

def test_large_screen_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/dashboard/large-screen")
    assert resp.status_code == 401


# ========== 空数据库测试 ==========

def test_large_screen_empty():
    """空数据库下大屏端点返回格式正确"""
    token = _login()
    resp = client.get(
        "/api/v1/dashboard/large-screen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # 检查顶层字段
    for key in ("core_metrics", "health_distribution", "station_health",
                "recent_alarms", "workorder_stats", "alarm_stats",
                "device_type_stats", "timestamp"):
        assert key in data

    # 空数据库统计应为0
    assert data["core_metrics"]["total_devices"] == 0
    assert data["core_metrics"]["online_devices"] == 0
    assert data["core_metrics"]["fault_devices"] == 0
    assert data["core_metrics"]["online_rate"] == 0
    assert data["core_metrics"]["active_alarms"] == 0
    assert data["core_metrics"]["pending_workorders"] == 0

    # 健康分布应为全0
    for k in ("excellent", "good", "warning", "critical"):
        assert data["health_distribution"][k] == 0

    # 告警列表为空
    assert data["recent_alarms"] == []


def test_large_screen_with_tz_offset():
    """支持时区偏移参数"""
    token = _login()
    resp = client.get(
        "/api/v1/dashboard/large-screen?tz_offset=8",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "core_metrics" in data


# ========== 有数据测试 ==========

def test_large_screen_with_data(client, seed_users, seed_stations, seed_devices, seed_alarms):
    """有数据时大屏端点返回正确统计"""
    token = _get_token(client)
    resp = client.get(
        "/api/v1/dashboard/large-screen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # 设备统计 - 验证数据存在且格式正确
    metrics = data["core_metrics"]
    assert metrics["total_devices"] >= 4  # 至少4个设备
    assert metrics["total_stations"] >= 2  # 至少2个站点

    # 告警统计 - 验证存在性和类型
    assert isinstance(metrics["active_alarms"], int)
    assert isinstance(metrics["critical_alarms"], int)

    # 站点健康 - 验证格式
    assert len(data["station_health"]) >= 2  # 至少2个站点

    # 告警列表 - 可能为空或包含数据
    assert isinstance(data["recent_alarms"], list)

    # 验证站点健康条目格式
    for s in data["station_health"]:
        for key in ("station_id", "station_name", "health_score",
                    "device_count", "online_count", "fault_count"):
            assert key in s


def test_large_screen_type_checks(client, seed_users):
    """响应中字段类型检查"""
    token = _get_token(client)
    resp = client.get(
        "/api/v1/dashboard/large-screen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert isinstance(data["core_metrics"]["total_devices"], int)
    assert isinstance(data["core_metrics"]["online_rate"], (int, float))
    assert isinstance(data["station_health"], list)
    assert isinstance(data["recent_alarms"], list)
    assert isinstance(data["device_type_stats"], list)
    assert isinstance(data["timestamp"], str)


def _get_token(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    if r.status_code != 200:
        return ""
    inner = r.json().get("data", {})
    return inner.get("token", "")

# ========== 卡 fcfd13fd: health_score 为 None 的设备不得导致 500 ==========

def test_large_screen_none_health_score(client, seed_users, seed_stations, seed_devices):
    """设备 health_score 为 NULL（列 nullable, default 只在 INSERT 未指定时生效于 ORM,
    生产存量数据/迁移数据可为 NULL）时, 大屏聚合不得 500。"""
    from app.models.device import Device
    s = client._sesh
    # 把两个站的部分设备 health_score 置 NULL
    s.query(Device).update({Device.health_score: None}, synchronize_session=False)
    s.commit()

    token = _get_token(client)
    resp = client.get(
        "/api/v1/dashboard/large-screen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 站点健康仍然可计算（None 视为缺失, 不参与/按默认口径）
    assert isinstance(data["station_health"], list)
    assert len(data["station_health"]) >= 1


def test_ops_health_scores_none_health_score(client, seed_users, seed_stations, seed_devices):
    """ops-dashboard/health-scores 同样不得因 None health_score 500。"""
    from app.models.device import Device
    s = client._sesh
    s.query(Device).update({Device.health_score: None}, synchronize_session=False)
    s.commit()

    token = _get_token(client)
    resp = client.get(
        "/api/v1/ops-dashboard/health-scores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["stations"], list)

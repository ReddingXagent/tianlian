#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警规则 API 测试

测试 AlarmRule CRUD 端点: POST/GET/PUT/DELETE /api/v1/alarms/rules
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login(username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _create_rule(token, **overrides):
    """Helper: create an alarm rule and return the response JSON data"""
    h = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "测试规则",
        "metric": "battery_temperature",
        "operator": ">",
        "threshold": 55.0,
        "level": "warning",
        "enabled": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/alarms/rules", json=payload, headers=h)
    assert resp.status_code == 200, f"Create rule failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


# ============================
# AlarmRule CRUD 测试
# ============================

class TestAlarmRuleCRUD:
    """告警规则 CRUD 操作测试"""

    def test_create_alarm_rule(self):
        """创建告警规则"""
        token = _login()
        data = _create_rule(token)
        assert data["name"] == "测试规则"
        assert data["metric"] == "battery_temperature"
        assert data["threshold"] == 55.0
        assert data["operator"] == ">"
        assert data["level"] == "warning"
        assert data["enabled"] == True
        assert "id" in data

    def test_create_alarm_rule_with_full_fields(self):
        """创建带所有字段的告警规则"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/alarms/rules", json={
            "name": "电网电压过高告警",
            "description": "A相电压超过阈值触发",
            "device_type": "inverter",
            "metric": "grid_voltage_a",
            "operator": ">=",
            "threshold": 260.0,
            "duration": 10,
            "level": "critical",
            "alarm_template": "A相电压{value}V超过阈值{threshold}V",
            "notify_users": [1, 2, 3],
            "auto_create_workorder": True,
            "workorder_priority": "high",
            "enabled": True,
            "silence_minutes": 5,
        }, headers=h)
        assert resp.status_code == 200, f"create full failed: {resp.status_code} {resp.text}"
        d = resp.json()["data"]
        assert d["name"] == "电网电压过高告警"
        assert d["operator"] == ">="
        assert d["threshold"] == 260.0
        assert d["level"] == "critical"
        assert d["auto_create_workorder"] == True
        assert d["enabled"] == True
        assert d["silence_minutes"] == 5

    def test_list_alarm_rules(self):
        """列出告警规则"""
        token = _login()
        _create_rule(token, name="规则A", metric="pv_power_total")
        _create_rule(token, name="规则B", metric="battery_soc")
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/alarms/rules", headers=h)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert isinstance(items, list)
        assert len(items) >= 2
        rule = items[0]
        assert "id" in rule
        assert "name" in rule
        assert "metric" in rule

    def test_list_alarm_rules_filter_enabled(self):
        """按启用状态过滤告警规则"""
        token = _login()
        _create_rule(token, name="启用", enabled=True)
        _create_rule(token, name="禁用", enabled=False)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/alarms/rules?enabled=true", headers=h)
        assert resp.status_code == 200
        for r in resp.json()["data"]["items"]:
            assert r["enabled"] == True

    def test_get_alarm_rule_by_id(self):
        """获取单个告警规则详情"""
        token = _login()
        created = _create_rule(token, name="获取测试", metric="charger_power", operator="<", threshold=10.0)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get(f"/api/v1/alarms/rules/{created['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "获取测试"

    def test_get_nonexistent_alarm_rule(self):
        """获取不存在的告警规则返回404"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/alarms/rules/99999", headers=h)
        assert resp.status_code == 404

    def test_update_alarm_rule(self):
        """更新告警规则"""
        token = _login()
        created = _create_rule(token, name="更新前", metric="battery_temperature", level="info")
        h = {"Authorization": f"Bearer {token}"}
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}", json={
            "name": "更新后",
            "threshold": 60.0,
            "level": "critical",
            "enabled": False,
        }, headers=h)
        assert resp.status_code == 200, f"update failed: {resp.status_code} {resp.text}"
        d = resp.json()["data"]
        assert d["name"] == "更新后"
        assert d["threshold"] == 60.0
        assert d["level"] == "critical"
        assert d["enabled"] == False
        assert d["metric"] == "battery_temperature"  # 原字段未丢失

    def test_delete_alarm_rule(self):
        """删除告警规则"""
        token = _login()
        created = _create_rule(token, name="待删除", metric="battery_soc", operator="<", threshold=5.0)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.delete(f"/api/v1/alarms/rules/{created['id']}", headers=h)
        assert resp.status_code == 200
        resp = client.get(f"/api/v1/alarms/rules/{created['id']}", headers=h)
        assert resp.status_code == 404

    def test_toggle_alarm_rule(self):
        """切换告警规则启用/禁用"""
        token = _login()
        created = _create_rule(token, name="切换测试", enabled=True)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}/toggle", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] == False
        resp = client.put(f"/api/v1/alarms/rules/{created['id']}/toggle", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] == True

    def test_evaluate_alarm_rule(self):
        """手动评估告警规则"""
        token = _login()
        created = _create_rule(token, name="评估测试", threshold=1000.0)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.post(f"/api/v1/alarms/rules/{created['id']}/evaluate", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "triggered" in data
        assert "rule_id" in data

    def test_alarm_rule_unauthorized(self):
        """未认证用户无法访问告警规则API"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        resp = client.get("/api/v1/alarms/rules")
        assert resp.status_code in (401, 403)
        resp = client.post("/api/v1/alarms/rules", json={
            "name": "test", "metric": "test", "operator": ">", "threshold": 1.0
        })
        assert resp.status_code in (401, 403)

    def test_alarm_summary_stats(self):
        """告警统计摘要"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/alarms/stats/summary", headers=h)
        assert resp.status_code == 200
        assert "total" in resp.json()["data"]

    def test_alarm_rule_logs(self):
        """获取告警规则触发日志"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/alarms/rule-logs", headers=h)
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_rule_with_notify_users(self):
        """创建带通知用户的规则"""
        token = _login()
        data = _create_rule(token, name="通知测试", notify_users=[1, 2])
        assert data["notify_users"] == [1, 2]

    def test_create_rule_without_optional_fields(self):
        """用最少必填字段创建规则"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/alarms/rules", json={
            "name": "最小规则",
            "metric": "grid_power_total",
            "operator": ">",
            "threshold": 500.0,
        }, headers=h)
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["name"] == "最小规则"
        assert d["enabled"] == True  # 默认启用

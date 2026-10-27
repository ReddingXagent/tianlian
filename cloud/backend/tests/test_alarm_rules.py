#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警规则配置 API 测试（独立路由 /api/v1/alarm-rules）

覆盖 AlarmRule CRUD + 启用/禁用切换 + 手动评估。
与 test_alarm_rules_api.py（测 /alarms/rules 子路由）不同，本文件针对
alarm_rules.py 暴露的独立路由（前缀 /alarm-rules，含连字符）。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """覆盖模块级 SessionLocal，使 require_permission 也连测试库。"""
    pass


def _login(username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _create_rule(token, **overrides):
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
    resp = client.post("/api/v1/alarm-rules", json=payload, headers=h)
    assert resp.status_code == 200, f"Create rule failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


class TestAlarmRules:
    """告警规则 /alarm-rules 端点"""

    def test_create_alarm_rule(self):
        """创建告警规则 — 基本字段回显"""
        token = _login()
        data = _create_rule(token, name="温度告警")
        assert data["name"] == "温度告警"
        assert data["metric"] == "battery_temperature"
        assert data["threshold"] == 55.0
        assert data["operator"] == ">"
        assert data["level"] == "warning"
        assert data["enabled"] is True
        assert "id" in data

    def test_list_rules_with_filter(self):
        """列表 + enabled / device_type 过滤"""
        token = _login()
        _create_rule(token, name="启用规则", device_type="inverter", enabled=True)
        _create_rule(token, name="禁用规则", device_type="charger", enabled=False)
        h = {"Authorization": f"Bearer {token}"}

        # enabled 过滤
        resp = client.get("/api/v1/alarm-rules?enabled=true", headers=h)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["items"], list)
        for r in resp.json()["data"]["items"]:
            assert r["enabled"] is True

        # device_type 过滤
        resp = client.get("/api/v1/alarm-rules?device_type=charger", headers=h)
        assert resp.status_code == 200
        for r in resp.json()["data"]["items"]:
            assert r["device_type"] == "charger"

    def test_get_rule_detail_and_404(self):
        """详情 + 不存在返回 404"""
        token = _login()
        created = _create_rule(token, name="详情规则")
        h = {"Authorization": f"Bearer {token}"}

        resp = client.get(f"/api/v1/alarm-rules/{created['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "详情规则"

        assert client.get("/api/v1/alarm-rules/99999", headers=h).status_code == 404

    def test_update_rule(self):
        """更新规则 — 指定字段更新，未传字段保留"""
        token = _login()
        created = _create_rule(token, name="更新前", metric="battery_soc", level="info")
        h = {"Authorization": f"Bearer {token}"}
        resp = client.put(f"/api/v1/alarm-rules/{created['id']}", json={
            "name": "更新后",
            "threshold": 60.0,
            "level": "critical",
            "enabled": False,
        }, headers=h)
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["name"] == "更新后"
        assert d["threshold"] == 60.0
        assert d["level"] == "critical"
        assert d["enabled"] is False
        assert d["metric"] == "battery_soc"  # 未更新字段保留

    def test_delete_rule(self):
        """删除规则 — 删除后查询 404"""
        token = _login()
        created = _create_rule(token, name="待删除规则")
        h = {"Authorization": f"Bearer {token}"}
        assert client.delete(f"/api/v1/alarm-rules/{created['id']}", headers=h).status_code == 200
        assert client.get(f"/api/v1/alarm-rules/{created['id']}", headers=h).status_code == 404

    def test_toggle_rule(self):
        """切换启用/禁用 — admin 始终通过 require_permission('alarm:process')"""
        token = _login()
        created = _create_rule(token, name="切换规则", enabled=True)
        h = {"Authorization": f"Bearer {token}"}

        resp = client.put(f"/api/v1/alarm-rules/{created['id']}/toggle", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is False

        resp = client.put(f"/api/v1/alarm-rules/{created['id']}/toggle", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is True

    def test_evaluate_rule(self):
        """手动评估规则 — 高阈值不触发"""
        token = _login()
        created = _create_rule(token, name="评估规则", threshold=1000.0)
        h = {"Authorization": f"Bearer {token}"}
        resp = client.post(f"/api/v1/alarm-rules/{created['id']}/evaluate", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["rule_id"] == created["id"]
        assert "triggered" in data

    def test_unauthorized_access(self, anon_client):
        """未认证访问返回 401/403"""
        assert anon_client.get("/api/v1/alarm-rules").status_code in (401, 403)
        assert anon_client.post("/api/v1/alarm-rules", json={
            "name": "x", "metric": "x", "operator": ">", "threshold": 1.0,
        }).status_code in (401, 403)


# ======================================================================
# 异常路径加固 (卡 f3e5633d)
# 注意: 以下用例注入 conftest 的 client fixture (函数参数, 自带 admin token),
# 其 client._sesh 与端点 get_db 共享同一 session, 故 monkeypatch 其 commit 可被端点感知。
# ======================================================================

def test_create_rule_integrity_conflict(client, monkeypatch):
    """创建告警规则遇唯一约束冲突 → 409, 不冒泡 500。"""
    from sqlalchemy.exc import IntegrityError

    def _boom(*a, **kw):
        raise IntegrityError("simulated", {}, Exception("UNIQUE"))

    monkeypatch.setattr(client._sesh, "commit", _boom)

    resp = client.post("/api/v1/alarm-rules", json={
        "name": "冲突规则", "metric": "m", "operator": ">", "threshold": 1.0,
    })
    assert resp.status_code == 409


def test_update_rule_db_error(client, monkeypatch):
    """更新告警规则遇非约束类 DB 异常 → 500, 不泄露原始异常。"""
    # 先用正常 commit 建一条规则
    created = client.post("/api/v1/alarm-rules", json={
        "name": "待更新", "metric": "m", "operator": ">", "threshold": 1.0,
    }).json()["data"]

    def _boom(*a, **kw):
        raise RuntimeError("DB 连接断开")

    monkeypatch.setattr(client._sesh, "commit", _boom)

    resp = client.put(f"/api/v1/alarm-rules/{created['id']}", json={
        "threshold": 99.0,
    })
    assert resp.status_code == 500
    assert "DB 连接断开" not in str(resp.json().get("detail", ""))

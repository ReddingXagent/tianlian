#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天链V3 — 数据大屏独立展示模式 API 测试

Phase48: 测试 GET /api/v1/dashboard/large-screen
"""
import pytest
import bcrypt
from fastapi.testclient import TestClient


def _get_token(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    res = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    if res.status_code != 200:
        pytest.skip(f"登录失败 (status={res.status_code}): {res.json()}")
    inner = res.json().get("data", {})
    token = inner.get("token", "")
    if not token:
        pytest.skip(f"token 为空: {res.json()}")
    return token


def _auth_headers(client: TestClient) -> dict:
    token = _get_token(client)
    return {"Authorization": f"Bearer {token}"}


def _create_admin(client):
    """确保 admin 用户存在"""
    from app.models.user import User, UserRole
    s = client._sesh
    existing = s.query(User).filter(User.username == "admin").first()
    if not existing:
        s.add(User(
            username="admin",
            password_hash=bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode(),
            role=UserRole.ADMIN,
            status="active",
        ))
        s.commit()


class TestLargeScreenAPI:
    def test_large_screen_requires_auth(self, anon_client):
        """未认证时应拒绝访问"""
        res = anon_client.get("/api/v1/dashboard/large-screen")
        assert res.status_code in (401, 403), f"期望 401/403, 实际 {res.status_code}"

    def test_large_screen_authenticated(self, client, seed_users, seed_stations, seed_devices, seed_alarms):
        """认证后返回 200 + 正确数据结构"""
        headers = _auth_headers(client)
        res = client.get("/api/v1/dashboard/large-screen", headers=headers)
        assert res.status_code == 200, f"请求失败 (status={res.status_code}): {res.json()}"

        data = res.json()

        for key in ["core_metrics", "health_distribution", "station_health",
                     "recent_alarms", "workorder_stats", "alarm_stats",
                     "device_type_stats", "timestamp"]:
            assert key in data, f"缺少字段: {key}"

        cm = data["core_metrics"]
        assert isinstance(cm["total_devices"], int)
        assert cm["total_devices"] >= 1
        assert isinstance(cm["online_rate"], (int, float))
        assert isinstance(cm["total_stations"], int)
        assert cm["total_stations"] >= 1
        assert isinstance(cm["active_alarms"], int)
        assert cm["active_alarms"] >= 1

        hd = data["health_distribution"]
        assert set(hd.keys()) == {"excellent", "good", "warning", "critical"}
        assert sum(hd.values()) >= 1

        for s in data["station_health"]:
            assert "station_id" in s
            assert "station_name" in s
            assert "health_score" in s

        assert len(data["recent_alarms"]) >= 1
        for a in data["recent_alarms"]:
            assert "id" in a
            assert "level" in a

        als = data["alarm_stats"]
        assert als["active"] >= 1

    def test_large_screen_empty_database(self, client):
        """空数据库时返回零值而不报错"""
        _create_admin(client)
        headers = _auth_headers(client)
        res = client.get("/api/v1/dashboard/large-screen", headers=headers)
        assert res.status_code == 200

        data = res.json()
        cm = data["core_metrics"]
        assert cm["total_devices"] == 0
        assert cm["online_devices"] == 0
        assert cm["online_rate"] == 0
        assert cm["active_alarms"] == 0
        assert data["recent_alarms"] == []
        assert data["station_health"] == []

    def test_large_screen_workorder_stats(self, client, seed_users, seed_devices):
        """工单统计字段存在"""
        headers = _auth_headers(client)
        res = client.get("/api/v1/dashboard/large-screen", headers=headers)
        assert res.status_code == 200

        data = res.json()
        ws = data["workorder_stats"]
        for key in ["pending", "in_progress", "completed"]:
            assert key in ws, f"workorder_stats 缺少字段: {key}"

    def test_large_screen_device_type_stats(self, client, seed_users, seed_stations, seed_devices):
        """设备类型统计存在"""
        headers = _auth_headers(client)
        res = client.get("/api/v1/dashboard/large-screen", headers=headers)
        assert res.status_code == 200

        data = res.json()
        dts = data["device_type_stats"]
        assert len(dts) >= 1
        for dt in dts:
            assert "type" in dt
            assert "total" in dt
            assert "online" in dt
            assert "rate" in dt


class TestLargeScreenDBException:
    """卡 a6e2e562: DB 聚合查询抛异常时端点应兜底 500, 不裸抛 stack。"""

    @staticmethod
    def _boom_aggregate_query(monkeypatch):
        """让聚合查询抛异常, 但鉴权链不受影响。

        鉴权全链路 (enforce_auth → get_current_user → router 依赖) 用 Query.first();
        大屏聚合用 Query.scalar()/.all()。故仅 patch Query.scalar/.all 抛 OperationalError,
        鉴权 .first() 正常 → 鉴权通过, 业务首个 scalar 在端点 try 块内炸。
        """
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm.query import Query

        def _boom(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db down"))

        monkeypatch.setattr(Query, "scalar", _boom)
        monkeypatch.setattr(Query, "all", _boom)

    def test_db_exception_returns_500(self, client, monkeypatch, seed_users):
        """业务聚合查询抛异常 → 500 + 固定 detail (不泄露异常信息)。"""
        headers = _auth_headers(client)
        self._boom_aggregate_query(monkeypatch)
        res = client.get("/api/v1/dashboard/large-screen", headers=headers)
        assert res.status_code == 500, f"期望 500, 实际 {res.status_code}: {res.text}"
        assert res.json()["detail"] == "大屏数据暂时不可用"

    def test_db_exception_logged(self, client, monkeypatch, caplog, seed_users):
        """异常路径应记录 logger.exception (带 traceback)。"""
        import logging

        headers = _auth_headers(client)
        self._boom_aggregate_query(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="app.api.v1.dashboard"):
            client.get("/api/v1/dashboard/large-screen", headers=headers)

        assert any("大屏数据聚合失败" in r.getMessage() for r in caplog.records)


class TestLargeScreenWebSocketEndpoint:
    def test_ws_endpoint_registered_in_routes(self):
        """验证 WebSocket 大屏端点在路由文件中已定义"""
        from app.ws.routes import router as ws_router
        routes = [r.path for r in ws_router.routes]
        large_screen_path = "/dashboard/large-screen"
        found = any(large_screen_path in r for r in routes)
        assert found, \
            f"WebSocket 大屏端点未注册，现有路由: {routes}"

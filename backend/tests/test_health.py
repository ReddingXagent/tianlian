"""
健康检查 API 测试
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """健康检查端点测试"""

    def test_root_endpoint(self, client: TestClient):
        """根路径返回服务信息"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["status"] == "running"

    def test_health_endpoint(self, client: TestClient):
        """健康检查端点"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        # 检查统一响应结构
        if "data" in data:
            assert data["data"]["status"] == "healthy"
        else:
            assert data["status"] == "healthy"

    def test_liveness_probe(self, client: TestClient):
        """liveness 探针"""
        response = client.get("/api/v1/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "uptime_seconds" in data

    def test_livez_alias(self, client: TestClient):
        """K8s /livez 兼容端点"""
        response = client.get("/api/v1/livez")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_probe(self, client: TestClient):
        """readiness 探针"""
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        data = response.json()

        # 统一响应结构处理
        checks = data.get("checks") or data.get("data", {}).get("checks", {})
        assert "database" in checks
        assert checks["database"]["status"] == "ok"
        assert "uptime_seconds" in (data.get("data") or data)

    def test_readyz_alias(self, client: TestClient):
        """K8s /readyz 兼容端点"""
        response = client.get("/api/v1/readyz")
        assert response.status_code == 200

    def test_ping_endpoint(self, client: TestClient):
        """ping 端点"""  
        response = client.get("/api/v1/ping")
        assert response.status_code == 200

    def test_db_contains_tables(self, client):
        """验证测试数据库已正确初始化表"""
        from app.core.database import Base
        tables = Base.metadata.sorted_tables
        table_names = [t.name for t in tables]
        assert "users" in table_names, f"users not in {table_names}"
        assert "devices" in table_names, f"devices not in {table_names}"
        assert "stations" in table_names, f"stations not in {table_names}"


class TestHealthEdgeCases:
    """健康检查边界测试"""

    def test_health_no_auth_required(self, client: TestClient):
        """健康检查无需认证"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_liveness_no_auth_required(self, client: TestClient):
        """liveness 无需认证"""
        response = client.get("/api/v1/live")
        assert response.status_code == 200


class TestHealthAuthGaps:
    """安全缺口修复验证：之前零认证的路由现在要求认证 (card:17dc0e81)"""

    def test_devices_health_requires_auth(self, anon_client: TestClient):
        """GET /devices/health 未认证 → 401"""
        r = anon_client.get("/api/v1/devices/health")
        assert r.status_code in (401, 403)

    def test_pipeline_health_requires_auth(self, anon_client: TestClient):
        """GET /pipeline/health 未认证 → 401"""
        r = anon_client.get("/api/v1/pipeline/health")
        assert r.status_code in (401, 403)

    def test_pipeline_stats_requires_auth(self, anon_client: TestClient):
        """GET /pipeline/stats 未认证 → 401"""
        r = anon_client.get("/api/v1/pipeline/stats")
        assert r.status_code in (401, 403)

    def test_gateway_health_requires_auth(self, anon_client: TestClient):
        """GET /gateway/health 未认证 → 401"""
        r = anon_client.get("/api/v1/gateway/health")
        assert r.status_code in (401, 403)

    def test_cache_stats_requires_admin(self, anon_client: TestClient):
        """GET /cache/stats 未认证 → 401"""
        r = anon_client.get("/api/v1/cache/stats")
        assert r.status_code in (401, 403)

    def test_permissions_requires_auth(self, anon_client: TestClient):
        """GET /permissions 未认证 → 401"""
        r = anon_client.get("/api/v1/permissions")
        assert r.status_code in (401, 403)
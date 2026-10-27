"""
安全功能测试：CORS + 安全响应头 + 异常处理
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def test_cors_whitelist():
    """测试CORS白名单"""
    # 允许的来源
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3004",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    
    # 不允许的来源
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert "access-control-allow-origin" not in response.headers or \
           response.headers["access-control-allow-origin"] != "http://evil.com"


def test_security_headers():
    """测试安全响应头"""
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    # Strict-Transport-Security 在生产环境中通过 nginx/cdn 添加
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_error_handling_no_debug():
    """测试异常处理脱敏（模拟生产模式）"""
    # 即使出错也不暴露内部详情
    response = client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    # 不应包含堆栈信息
    assert "traceback" not in response.text.lower()

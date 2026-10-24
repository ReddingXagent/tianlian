"""
设备目录平台管理员收紧回归测试（审计 #8 / 卡 358421c5）

设备型号库 / 通信协议 / 协议解析规则 / 固件管理为平台共享目录，
写端点（共 13 个）须 platform admin；operator 级 device:edit 不再放行。
先例：protocol_instances parser-configs 收紧（卡 b10f64a8）。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 13 个写端点: (method, path, json_body)
WRITE_ENDPOINTS = [
    ("post", "/api/v1/device-library", {
        "brand": "华为", "model": "SUN2000-30KTL", "device_type": "pv"}),
    ("put", "/api/v1/device-library/1", {"brand": "华为"}),
    ("delete", "/api/v1/device-library/1", None),
    ("post", "/api/v1/device-protocols", {
        "name": "OCPP 1.6J", "code": "OCPP_16J", "type": "ocpp"}),
    ("put", "/api/v1/device-protocols/1", {"name": "OCPP 1.6J"}),
    ("delete", "/api/v1/device-protocols/1", None),
    ("post", "/api/v1/protocol-rules", {
        "protocol_id": 1, "direction": "uplink"}),
    ("put", "/api/v1/protocol-rules/1", {"message_type": "Heartbeat"}),
    ("delete", "/api/v1/protocol-rules/1", None),
    ("post", "/api/v1/gateways/firmware", {
        "version": "v9.9.9", "model": "GW-100"}),
    ("post", "/api/v1/gateways/firmware/1/release", None),
    ("put", "/api/v1/gateways/firmware/1", {"changelog": "x"}),
    ("delete", "/api/v1/gateways/firmware/1", None),
]


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    yield


def _seed_operator(test_db):
    """创建 ENGINEER（operator 级，具备 device:edit）用户"""
    from app.models.user import User, UserRole
    session = test_db["session"]
    session.add(User(
        username="eng_devcat",
        password_hash=_hash("eng123"),
        role=UserRole.ENGINEER,
        status="active",
    ))
    session.commit()
    session.close()


def _hash(password: str) -> str:
    from tests.conftest import _fast_hash
    return _fast_hash(password)


def _token(username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_operator_write_all_forbidden(test_db):
    """operator（ENGINEER）调全部 13 个写端点 → 403"""
    _seed_operator(test_db)
    token = _token("eng_devcat", "eng123")
    for method, path, body in WRITE_ENDPOINTS:
        kwargs = {"headers": _h(token)}
        if body is not None and method != "delete":
            kwargs["json"] = body
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 403, (
            f"漏洞回归: {method.upper()} {path} operator 应 403, 实际 {resp.status_code}: {resp.text}")

def test_platform_admin_write_not_forbidden(test_db):
    """platform admin（ADMIN）调全部 13 个写端点 → 非 403（放行至业务层）"""
    token = _token("admin", "admin123")
    for method, path, body in WRITE_ENDPOINTS:
        kwargs = {"headers": _h(token)}
        if body is not None and method != "delete":
            kwargs["json"] = body
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code != 403, (
            f"误伤: {method.upper()} {path} admin 不应 403, 实际 {resp.status_code}: {resp.text}")


def test_read_endpoints_unchanged(test_db):
    """GET 读端点保留现状：operator 仍可读（非 403 鉴权拒绝）"""
    _seed_operator(test_db)
    token = _token("eng_devcat", "eng123")
    for path in [
        "/api/v1/device-library",
        "/api/v1/device-protocols",
        "/api/v1/protocol-rules",
        "/api/v1/gateways/firmware",
    ]:
        resp = client.get(path, headers=_h(token))
        assert resp.status_code != 403, (
            f"读端点误伤: GET {path} 应保留现状, 实际 {resp.status_code}: {resp.text}")

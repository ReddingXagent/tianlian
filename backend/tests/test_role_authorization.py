"""
角色授权测试 (P1 安全)

验证敏感路由的角色授权 (require_role)：
- OPERATOR 访问 admin 端点 → 403
- ADMIN 访问 admin / operator 端点 → 通过 (非 401/403)
- 普通用户 (viewer) 访问 operator 端点 → 403
- OPERATOR 访问 operator 端点 → 通过

授权「拒绝」用强断言 == 403；若端点路径写错会得到 404（≠ 403），
对应「拒绝」测试自动失败 —— 从而防止路径错误导致的假绿。
"""
import bcrypt
import pytest

from app.models.user import User, UserRole


# 仅 admin 可访问的端点 (method, path) —— 各模块列表/聚合 GET，数据无关
ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/admin/supervision/configs"),
    ("GET", "/api/v1/admin/cloud-configs"),
    ("GET", "/api/v1/admin/terminals"),
    ("GET", "/api/v1/admin/interconnect/configs"),
    ("GET", "/api/v1/rbac/roles"),
    ("GET", "/api/v1/pricing/mgmt/time-slots"),
    ("GET", "/api/v1/ai-model_config"),
]

# admin / operator 可访问的端点
OPERATOR_ENDPOINTS = [
    ("GET", "/api/v1/alert-workflow/stats"),
    ("GET", "/api/v1/predictive-maintenance/dashboard"),
    ("GET", "/api/v1/fleet/v2g/plans"),
    ("GET", "/api/v1/fleet/drivers"),
    ("GET", "/api/v1/fleet/vehicles/1/maintenance"),
]


def _ensure_user(client, username, password, role):
    """在测试 DB 建用户 (若不存在)。"""
    s = client._sesh
    if not s.query(User).filter(User.username == username).first():
        s.add(User(
            username=username,
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            real_name=username,
            role=role,
            status="active",
        ))
        s.commit()


def _login_token(client, username, password):
    """登录拿 token。"""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.status_code} {r.text}"
    return r.json().get("data", {}).get("token")


@pytest.fixture
def operator_token(client):
    _ensure_user(client, "role_test_operator", "op123456", UserRole.OPERATOR)
    return _login_token(client, "role_test_operator", "op123456")


@pytest.fixture
def viewer_token(client):
    _ensure_user(client, "role_test_viewer", "view123456", UserRole.VIEWER)
    return _login_token(client, "role_test_viewer", "view123456")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ===== ADMIN 端点：OPERATOR 必须被拒 (403) =====
@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_operator_forbidden_on_admin_endpoints(client, operator_token, method, path):
    resp = client.request(method, path, headers=_auth(operator_token))
    assert resp.status_code == 403, (
        f"OPERATOR 访问 admin 端点 {method} {path} 应 403，实际 {resp.status_code}\n{resp.text}"
    )


# ===== ADMIN 端点：ADMIN 通过 =====
@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_allowed_on_admin_endpoints(client, method, path):
    # client fixture 默认注入 admin token
    resp = client.request(method, path)
    assert resp.status_code not in (401, 403), (
        f"ADMIN 访问 admin 端点 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


# ===== OPERATOR 端点：普通用户 (viewer) 必须被拒 (403) =====
@pytest.mark.parametrize("method,path", OPERATOR_ENDPOINTS)
def test_viewer_forbidden_on_operator_endpoints(client, viewer_token, method, path):
    resp = client.request(method, path, headers=_auth(viewer_token))
    assert resp.status_code == 403, (
        f"普通用户访问 operator 端点 {method} {path} 应 403，实际 {resp.status_code}\n{resp.text}"
    )


# ===== OPERATOR 端点：OPERATOR 通过 =====
@pytest.mark.parametrize("method,path", OPERATOR_ENDPOINTS)
def test_operator_allowed_on_operator_endpoints(client, operator_token, method, path):
    resp = client.request(method, path, headers=_auth(operator_token))
    assert resp.status_code not in (401, 403), (
        f"OPERATOR 访问 operator 端点 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


# ===== OPERATOR 端点：ADMIN 通过 =====
@pytest.mark.parametrize("method,path", OPERATOR_ENDPOINTS)
def test_admin_allowed_on_operator_endpoints(client, method, path):
    resp = client.request(method, path)
    assert resp.status_code not in (401, 403), (
        f"ADMIN 访问 operator 端点 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )

"""
多租户管理 API 测试
覆盖: /tenants — 租户列表、详情、创建、更新、删除、统计
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_tenant(name="测试租户", code="TENANT_001"):
    """创建测试租户，返回 tenant_id"""
    resp = client.post(
        "/api/v1/tenants",
        json={
            "name": name,
            "code": code,
            "description": "测试租户描述",
            "contact_name": "联系人",
            "contact_phone": "13800138000",
            "contact_email": "test@tenant.com",
            "max_stations": 10,
            "max_devices": 100,
            "max_users": 20,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, f"创建租户失败: {resp.text}"
    return resp.json()["data"]["id"]


# ========== 鉴权检查 ==========

def test_list_tenants_requires_auth():
    """无 token 访问租户列表应返回401"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    assert client.get("/api/v1/tenants").status_code == 401


def test_get_tenant_requires_auth():
    """无 token 访问租户详情应返回401"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    assert client.get("/api/v1/tenants/1").status_code == 401


def test_create_tenant_requires_auth():
    """无 token 创建租户应返回401或403(CSRF)"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.post("/api/v1/tenants", json={"name": "test", "code": "TEST"})
    assert resp.status_code in (401, 403)


def test_stats_requires_auth():
    """无 token 访问统计应返回401"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    assert client.get("/api/v1/tenants/stats/summary").status_code == 401


# ========== 租户列表 ==========

def test_list_tenants_empty():
    """测试空租户列表"""
    resp = client.get("/api/v1/tenants", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "items" in data["data"]
    assert data["data"]["total"] == 0


def test_list_tenants_with_pagination():
    """测试租户列表分页"""
    resp = client.get("/api/v1/tenants?page=1&page_size=10", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["page"] == 1
    assert data["data"]["page_size"] == 10


def test_list_tenants_with_status_filter():
    """测试租户状态筛选"""
    resp = client.get("/api/v1/tenants?status=active", headers=_auth_headers())
    assert resp.status_code == 200


def test_list_tenants_with_search():
    """测试租户搜索"""
    _create_tenant("搜索测试租户", "SEARCH_001")
    resp = client.get("/api/v1/tenants?search=搜索", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["total"] >= 1


def test_list_tenants_with_keyword():
    """测试租户关键字搜索"""
    _create_tenant("关键字测试租户", "KEYWORD_001")
    resp = client.get("/api/v1/tenants?keyword=关键字", headers=_auth_headers())
    assert resp.status_code == 200


# ========== 租户详情 ==========

def test_get_tenant_not_found():
    """测试获取不存在的租户"""
    resp = client.get("/api/v1/tenants/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_tenant_success():
    """测试获取租户详情成功"""
    tenant_id = _create_tenant("详情测试租户", "DETAIL_001")
    resp = client.get(f"/api/v1/tenants/{tenant_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "详情测试租户"
    assert data["code"] == "DETAIL_001"
    assert "status" in data


# ========== 创建租户 ==========

def test_create_tenant_success():
    """测试创建租户成功"""
    tenant_id = _create_tenant("创建测试租户", "CREATE_001")
    assert tenant_id is not None

    resp = client.get(f"/api/v1/tenants/{tenant_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "创建测试租户"


def test_create_tenant_duplicate_code():
    """测试创建重复编码租户"""
    _create_tenant("重复编码租户1", "DUPLICATE_001")
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "重复编码租户2", "code": "DUPLICATE_001"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_create_tenant_with_limits():
    """测试创建带配额限制的租户"""
    resp = client.post(
        "/api/v1/tenants",
        json={
            "name": "配额测试租户",
            "code": "LIMIT_001",
            "max_stations": 5,
            "max_devices": 50,
            "max_users": 10,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


# ========== 更新租户 ==========

def test_update_tenant_success():
    """测试更新租户成功"""
    tenant_id = _create_tenant("原租户名", "UPDATE_001")
    resp = client.put(
        f"/api/v1/tenants/{tenant_id}",
        json={
            "name": "新租户名",
            "description": "更新后的描述",
            "contact_name": "新联系人",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_update_tenant_not_found():
    """测试更新不存在的租户"""
    resp = client.put("/api/v1/tenants/999999", json={"name": "不存在"}, headers=_auth_headers())
    assert resp.status_code == 404


def test_update_tenant_status():
    """测试更新租户状态"""
    tenant_id = _create_tenant("状态更新租户", "STATUS_001")
    resp = client.put(
        f"/api/v1/tenants/{tenant_id}",
        json={"status": "inactive"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_update_tenant_partial():
    """测试部分更新租户"""
    tenant_id = _create_tenant("部分更新租户", "PARTIAL_001")
    resp = client.put(
        f"/api/v1/tenants/{tenant_id}",
        json={"description": "仅更新描述"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


# ========== 删除租户 ==========

def test_delete_tenant_success():
    """测试删除租户成功"""
    tenant_id = _create_tenant("待删除租户", "DELETE_001")
    resp = client.delete(f"/api/v1/tenants/{tenant_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert "删除成功" in resp.json()["message"]

    assert client.get(f"/api/v1/tenants/{tenant_id}", headers=_auth_headers()).status_code == 404


def test_delete_tenant_not_found():
    """测试删除不存在的租户"""
    resp = client.delete("/api/v1/tenants/999999", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 统计 ==========

def test_tenant_stats_summary():
    """测试租户统计摘要"""
    resp = client.get("/api/v1/tenants/stats/summary", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total" in data
    assert "active" in data
    assert "inactive" in data
    assert "suspended" in data


def test_tenant_stats_summary_with_data():
    """测试有数据时的统计"""
    _create_tenant("统计租户1", "STAT_001")
    _create_tenant("统计租户2", "STAT_002")
    resp = client.get("/api/v1/tenants/stats/summary", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2


def test_tenant_stats_detail():
    """测试租户详情统计 - Station 模型缺少 tenant_id"""
    tenant_id = _create_tenant("详情统计租户", "STAT_DET_001")
    resp = client.get(f"/api/v1/tenants/{tenant_id}/stats", headers=_auth_headers())
    assert resp.status_code == 200


def test_tenant_stats_detail_not_found():
    """测试不存在租户的详情统计 - Station 模型缺少 tenant_id"""
    resp = client.get("/api/v1/tenants/999999/stats", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 租户用户列表 (卡eb81ca13) ==========

def _test_session():
    """返回绑定测试库的 Session（conftest 已 override SessionLocal → 测试库）"""
    from app.core.database import SessionLocal
    return SessionLocal()


def _create_team_with_users(code: str, members: list):
    """创建 Team(code) 并挂成员，返回 team_id。member dict: username/real_name/role"""
    from app.models.user import Team, User, UserRole
    from app.api.v1.auth import get_password_hash
    db = _test_session()
    try:
        team = Team(name=f"团队_{code}", code=code)
        db.add(team)
        db.flush()
        for m in members:
            db.add(User(
                username=m["username"],
                password_hash=get_password_hash("test123"),
                real_name=m.get("real_name"),
                role=m.get("role", UserRole.ENGINEER),
                team_id=team.id,
                status="active",
            ))
        db.commit()
        return team.id
    finally:
        db.close()


def test_tenant_users_requires_auth():
    """无 token 访问租户用户列表应返回401"""
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/tenants/1/users").status_code == 401


def test_tenant_users_not_found():
    """租户不存在时返回404"""
    resp = client.get("/api/v1/tenants/999999/users", headers=_auth_headers())
    assert resp.status_code == 404


def test_tenant_users_returns_team_members():
    """租户用户列表按 tenant.code→Team.code 关联返回真实成员（含分页元数据）"""
    from app.models.user import UserRole
    tenant_id = _create_tenant("用户列表租户", "USERS_T001")
    _create_team_with_users("USERS_T001", [
        {"username": "admin_t01", "real_name": "管理员甲", "role": UserRole.ADMIN},
        {"username": "eng_t01", "real_name": "工程师乙", "role": UserRole.ENGINEER},
    ])
    resp = client.get(f"/api/v1/tenants/{tenant_id}/users", headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    usernames = [u["username"] for u in items]
    assert "admin_t01" in usernames and "eng_t01" in usernames
    for u in items:
        assert u["id"] and u["username"]
        assert u["role"] in ("admin", "engineer")
        assert "real_name" in u and "status" in u


def test_tenant_users_empty_when_no_team():
    """租户无关联 Team 时返回空列表而非假数据"""
    tenant_id = _create_tenant("空用户租户", "USERS_EMPTY")
    resp = client.get(f"/api/v1/tenants/{tenant_id}/users", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    assert items == []


def test_tenant_users_forbidden_for_non_admin():
    """非管理员访问租户用户列表应返回403"""
    from app.models.user import User, UserRole
    from app.api.v1.auth import get_password_hash
    db = _test_session()
    try:
        db.add(User(username="viewer_u1", password_hash=get_password_hash("test123"),
                    real_name="只读者", role=UserRole.VIEWER, status="active"))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/v1/auth/login", data={"username": "viewer_u1", "password": "test123"})
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token") or resp.json().get("data", {}).get("token")
    resp = client.get("/api/v1/tenants/1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

# ========== 审计归属 (卡 3dd8954e) ==========

def test_tenant_audit_attribution_card3dd8954e():
    """租户 create/update 审计归属真实操作用户 (卡 3dd8954e, 修 user_id=0 硬编码)"""
    from datetime import datetime
    from app.models.audit_log import AuditLog
    from app.models.user import User
    s = _test_session()
    try:
        admin = s.query(User).filter(User.username == "admin").first()
        assert admin is not None and admin.id != 0

        code = f"3DD8954E-{datetime.now().strftime('%H%M%S%f')}"
        tenant_id = _create_tenant(name="审计归属租户", code=code)

        log = (s.query(AuditLog)
               .filter(AuditLog.module == "tenants", AuditLog.action == "create",
                       AuditLog.target_id == str(tenant_id))
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "租户创建应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username

        resp = client.put(f"/api/v1/tenants/{tenant_id}",
                          json={"description": "审计归属更新"}, headers=_auth_headers())
        assert resp.status_code == 200, resp.text
        log = (s.query(AuditLog)
               .filter(AuditLog.module == "tenants", AuditLog.action == "update",
                       AuditLog.target_id == str(tenant_id))
               .order_by(AuditLog.id.desc()).first())
        assert log is not None, "租户更新应产生审计记录"
        assert log.user_id == admin.id, f"审计归属错误: user_id={log.user_id} 期望 {admin.id}"
        assert log.username == admin.username
    finally:
        s.close()

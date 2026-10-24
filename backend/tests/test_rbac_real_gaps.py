"""
真实 RBAC 缺口修复测试 (卡 a17fcf3f)

前一轮审查确认 405/431 写端点已有 require_permission; 本测试锁定本次修复的
12 条真实缺口 (alarm 规则 CRUD + 告警/模拟 + 运营写端点), 防回归:
  - viewer   打这些端点 → 403 (不持 alarm:process / operate:manage)
  - admin    打这些端点 → 非 401/403 (恒通过)
  - operator 打这些端点 → 非 401/403 (持 alarm:process / operate:manage 放行)

require_permission (app/middleware/permission.py) 内部用
`from app.core.database import SessionLocal` 查 user; conftest client fixture
已 override 模块级 SessionLocal 指向测试库 (卡 b9d16fae), 本 fixture 再保险
monkeypatch 指向同 engine。同源坑见 [[conftest-client-sessionlocal-override]]。
"""
import bcrypt
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.user import User, UserRole


@pytest.fixture
def rbac_env(client, monkeypatch):
    """client + seed viewer/operator + SessionLocal 指向测试库。

    admin 由 conftest client fixture 已 seed (admin/admin123)。
    """
    import app.core.database as db_module

    s = client._sesh
    engine = s.get_bind()

    for uname, pwd, role in [
        ("gap_viewer", "view123", UserRole.VIEWER),
        ("gap_operator", "op123", UserRole.OPERATOR),
    ]:
        if not s.query(User).filter(User.username == uname).first():
            s.add(User(
                username=uname,
                password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                real_name=uname,
                role=role,
                status="active",
            ))
    s.commit()

    # require_permission 函数内 `from app.core.database import SessionLocal`
    # 每次调用读取模块属性当前值, monkeypatch 后即指向测试库 engine。
    TestSesh = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSesh)
    yield client


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed {username}: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


# 本次修复的 12 条真实 RBAC 缺口 (method, path, json_body)
# 全部配合法 body, 确保权限检查能先于/独立于 body 校验执行 (避免 422 掩盖 403);
# 不存在的资源 id 用 999999, 权限通过后业务层自然返回 404 (非 401/403)。
REAL_GAPS = [
    # A. alarm_rules.py — 告警规则 CRUD (alarm:process)
    ("POST", "/api/v1/alarm-rules",
     {"name": "_gap_r", "metric": "temperature", "threshold": 50.0}),
    ("PUT", "/api/v1/alarm-rules/999999", {"name": "_gap_r"}),
    ("DELETE", "/api/v1/alarm-rules/999999", None),
    # B. alarms.py — 告警创建/模拟 + 规则 CRUD (alarm:process)
    ("POST", "/api/v1/alarms",
     {"device_id": 999999, "alarm_type": "_gap", "content": "gap test"}),
    ("POST", "/api/v1/alarms/simulate",
     {"device_id": "999999", "alarm_type": "_gap", "message": "gap test"}),
    ("POST", "/api/v1/alarms/rules",
     {"name": "_gap_r", "metric": "temperature", "operator": ">", "threshold": 50.0}),
    ("PUT", "/api/v1/alarms/rules/999999", {"name": "_gap_r"}),
    ("DELETE", "/api/v1/alarms/rules/999999", None),
    # C. ops_settlement.py — 日结确认 (operate:manage)
    ("PUT", "/api/v1/operate/settlement/daily/999999/confirm", None),
    # D. users_api.py — 编辑运营用户 (operate:manage)
    ("PUT", "/api/v1/operate/users/999999", {"real_name": "_gap"}),
]


# ===== viewer: 全部缺口端点必须 403 =====
@pytest.mark.parametrize("method,path,body", REAL_GAPS)
def test_viewer_forbidden_on_real_gaps(rbac_env, method, path, body):
    token = _login(rbac_env, "gap_viewer", "view123")
    resp = rbac_env.request(method, path, json=body, headers=_hdr(token))
    assert resp.status_code == 403, (
        f"viewer 写 {method} {path} 应 403, 实际 {resp.status_code}\n{resp.text}"
    )


# ===== admin: 全部缺口端点必须 非 401/403 =====
@pytest.mark.parametrize("method,path,body", REAL_GAPS)
def test_admin_allowed_on_real_gaps(rbac_env, method, path, body):
    # client fixture 默认注入 admin token
    resp = rbac_env.request(method, path, json=body)
    assert resp.status_code not in (401, 403), (
        f"admin 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


# ===== operator: alarm:process / operate:manage 持权放行 =====
@pytest.mark.parametrize("method,path,body", REAL_GAPS)
def test_operator_allowed_on_real_gaps(rbac_env, method, path, body):
    token = _login(rbac_env, "gap_operator", "op123")
    resp = rbac_env.request(method, path, json=body, headers=_hdr(token))
    assert resp.status_code not in (401, 403), (
        f"operator 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )

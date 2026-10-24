"""
路由级 require_write_permission 守卫契约测试 (卡 cbfe46f0)

背景:
vpp / tasks / charging_strategy 三模块在路由层整体挂载了
require_write_permission (app/middleware/permission.py:153, 卡 1bd3b6e2):
  - GET/HEAD/OPTIONS: 仅认证放行
  - POST/PUT/PATCH/DELETE: 委托 require_permission("<module>:manage/edit")
    admin/super_admin 恒通过; 持对应写权限的角色(operator/engineer)放行;
    viewer/auditor → 403。

因此这三模块的写端点**并非权限缺口**(test_rbac_real_gaps.py 的 12 条真实缺口
清单不含它们)。本测试固化该契约, 防止后续误删路由级 dependency 致回归:

  - viewer   写这些端点 → 403
  - admin    写这些端点 → 非 401/403 (恒通过)
  - operator 写这些端点 → 非 401/403 (持 device:edit / charging:manage / analytics:manage)

注: stats.py 仅有 GET 端点, 无写操作, 不在本测试范围。
"""
import bcrypt
import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import sessionmaker

from app.models.user import User, UserRole


@pytest.fixture
def rbac_env(client, monkeypatch):
    """client + seed viewer/operator + SessionLocal 指向测试库。

    admin 由 conftest client fixture 已 seed (admin/admin123)。
    require_permission 函数内 `from app.core.database import SessionLocal` 查 user,
    需 monkeypatch 指向测试库 (同源坑见 [[conftest-client-sessionlocal-override]])。
    """
    import app.core.database as db_module

    s = client._sesh
    engine = s.get_bind()

    for uname, pwd, role in [
        ("rwg_viewer", "view123", UserRole.VIEWER),
        ("rwg_operator", "op123", UserRole.OPERATOR),
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

    TestSesh = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSesh)

    # mock celery: tasks 写端点(submit/cancel)在权限层放行后, 业务层会连 Redis broker。
    # 测试环境无 Redis, 且 TestClient raise_server_exception=True 会把 kombu 连接异常
    # 重抛致测试报错。此处 mock 业务层 celery 调用, 隔离权限契约与 celery 基础设施。
    mock_task_func = MagicMock()
    mock_task_func.delay.return_value = MagicMock(id="rwg-task")
    mock_tasks = MagicMock()
    mock_tasks.__getitem__ = MagicMock(return_value=mock_task_func)
    monkeypatch.setattr("app.api.v1.tasks.celery_app.tasks", mock_tasks)
    monkeypatch.setattr(
        "app.api.v1.tasks.celery_app.AsyncResult",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr("app.api.v1.tasks.CELERY_AVAILABLE", True)

    yield client


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed {username}: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


# 三模块路由级守卫覆盖的代表性写端点 (method, path, json_body)。
# require_write_permission 在请求体解析前执行, 故 viewer 即使 body 非法也先得 403。
# admin/operator body 合法以避免被 422 掩盖; 不存在的资源 id 在权限通过后业务层
# 自然返回 404/400/503 (均非 401/403)。
ROUTE_WRITE_ENDPOINTS = [
    # vpp — require_write_permission("device:edit")
    ("POST", "/api/v1/vpp/stations",
     {"station_id": "RWG1", "station_name": "rwg guard"}),
    ("POST", "/api/v1/vpp/dispatch", {"mode": "auto"}),
    ("DELETE", "/api/v1/vpp/stations/__rwg_nonexist__", None),
    # tasks — require_write_permission("analytics:manage")
    ("POST", "/api/v1/tasks/submit",
     {"task_type": "health_score", "params": {}}),
    ("POST", "/api/v1/tasks/cancel/__rwg_nonexist__", None),
    # charging_strategy — require_write_permission("charging:manage")
    ("POST", "/api/v1/charging/strategy/switch", {"mode": "timed"}),
]

# 审计 #2 翻转: vpp 全模块已额外挂 require_platform_admin（进程级全局单例，
# operator 原可操作全平台 VPP）。vpp 条目 viewer→403 / admin→放行 契约不变，
# 仅 operator 不再放行 → 从 operator 放行清单剔除，
# operator→403 由 tests/api/test_vpp_platform_admin_isolation.py 覆盖。
_VPP_PLATFORM_ADMIN_ONLY = [
    ("POST", "/api/v1/vpp/stations",
     {"station_id": "RWG1", "station_name": "rwg guard"}),
    ("POST", "/api/v1/vpp/dispatch", {"mode": "auto"}),
    ("DELETE", "/api/v1/vpp/stations/__rwg_nonexist__", None),
]


@pytest.mark.parametrize("method,path,body", ROUTE_WRITE_ENDPOINTS)
def test_viewer_forbidden_on_route_write(rbac_env, method, path, body):
    """viewer 不持 device:edit / analytics:manage / charging:manage → 写必 403。"""
    token = _login(rbac_env, "rwg_viewer", "view123")
    resp = rbac_env.request(method, path, json=body, headers=_hdr(token))
    assert resp.status_code == 403, (
        f"viewer 写 {method} {path} 应 403, 实际 {resp.status_code}\n{resp.text}"
    )


@pytest.mark.parametrize("method,path,body", ROUTE_WRITE_ENDPOINTS)
def test_admin_allowed_on_route_write(rbac_env, method, path, body):
    """admin 恒通过 (client fixture 默认注入 admin token)。"""
    resp = rbac_env.request(method, path, json=body)
    assert resp.status_code not in (401, 403), (
        f"admin 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


@pytest.mark.parametrize("method,path,body", [
    e for e in ROUTE_WRITE_ENDPOINTS if e not in tuple(_VPP_PLATFORM_ADMIN_ONLY)
])
def test_operator_allowed_on_route_write(rbac_env, method, path, body):
    """operator 持 device:edit / analytics:manage / charging:manage → 放行。"""
    token = _login(rbac_env, "rwg_operator", "op123")
    resp = rbac_env.request(method, path, json=body, headers=_hdr(token))
    assert resp.status_code not in (401, 403), (
        f"operator 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )

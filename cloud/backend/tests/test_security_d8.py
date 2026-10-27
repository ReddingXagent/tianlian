"""
admin-platform-spec §2.7 安全管理 API 去模拟化 (D8)

覆盖:
- GET /security/logs: 真实 audit_logs 查询 (先建记录再查) + 分页 + action_type/时间范围过滤 + 不再返回模拟数据
- GET /security/policies, GET /security/policies/{key}, PUT /security/policies/{key}: 安全策略 CRUD
- 权限控制: 非 admin 角色对策略端点 403
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog
from app.models.security_policy import SecurityPolicy


# ── 测试辅助 ──

def _seed_audit_logs(s, *, actions=None):
    """插入若干条审计日志, 返回插入的对象列表。

    先清空 audit_logs 以排除 admin 登录(client fixture)产生记录的干扰, 获得
    精确可控的 total。该测试只关心 /logs 查询行为, 不依赖登录审计痕迹。
    """
    s.query(AuditLog).delete()
    s.commit()
    rows = []
    specs = actions or [("login", "auth"), ("login", "auth"), ("create", "devices")]
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    for i, (act, mod) in enumerate(specs):
        rows.append(AuditLog(
            username=f"secuser{i}",
            user_role="admin",
            action=act,
            module=mod,
            ip_address=f"10.20.30.{40+i}",
            result="success" if act != "create" else "success",
            detail=f"d8 test log {i}",
            timestamp=base + timedelta(minutes=i),
        ))
    s.add_all(rows)
    s.commit()
    for r in rows:
        s.refresh(r)
    return rows


def _seed_policies(s):
    """插入默认安全策略 (模拟迁移种子), 返回 dict[policy_key]->SecurityPolicy。"""
    defaults = [
        ("password", {"min_length": 8, "require_upper": True, "require_digit": True, "expire_days": 90}, "密码策略"),
        ("login", {"fail_lock_count": 5, "lock_duration_minutes": 30}, "登录策略"),
        ("session", {"session_timeout_minutes": 480, "concurrent_session_limit": 3}, "会话策略"),
        ("ip", {"whitelist": [], "blacklist": [], "enable_ip_restrict": False}, "IP 访问策略"),
    ]
    objs = {key: SecurityPolicy(policy_key=key, policy_config=cfg, description=desc, status="active")
            for key, cfg, desc in defaults}
    s.add_all(objs.values())
    s.commit()
    for o in objs.values():
        s.refresh(o)
    return objs


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """每个测试用独立 DB。"""
    pass


# ── /security/logs: 真实审计数据 ──

def test_logs_returns_real_audit_data(client):
    """删除模拟数据: /logs 返回真实 audit_logs 记录。"""
    s = client._sesh
    _seed_audit_logs(s, actions=[("login", "auth")])

    r = client.get("/api/v1/security/logs")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total"] >= 1
    # 分页字段存在
    assert "page" in data and "page_size" in data
    items = data["items"]
    assert items, "应返回真实审计记录而非空列表"
    # 真实字段对齐 AuditLog.to_dict
    assert items[0]["username"] == "secuser0"
    assert items[0]["action"] == "login"
    assert items[0]["module"] == "auth"
    # 不再含模拟数据特征 (原代码: user{i}/192.168.1.{i})
    assert items[0]["username"] != "user1"
    assert all(not (it.get("ip_address") or "").startswith("192.168.1.") for it in items)


def test_logs_action_type_filter(client):
    """action_type 过滤: 只返回对应 action。"""
    s = client._sesh
    _seed_audit_logs(s, actions=[("login", "auth"), ("create", "devices"), ("delete", "alarms")])

    r = client.get("/api/v1/security/logs?action_type=login")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert items, "action_type=login 应有结果"
    assert all(it["action"] == "login" for it in items)
    assert r.json()["data"]["total"] == len(items)


def test_logs_pagination(client):
    """分页: page/page_size 正确切分。"""
    s = client._sesh
    _seed_audit_logs(s, actions=[("login", "auth") for _ in range(5)])

    page1 = client.get("/api/v1/security/logs?page=1&page_size=2").json()["data"]
    page2 = client.get("/api/v1/security/logs?page=2&page_size=2").json()["data"]
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    # 不同页不重叠
    ids1 = {it["id"] for it in page1["items"]}
    ids2 = {it["id"] for it in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_logs_time_range_filter(client):
    """时间范围过滤: start_time/end_time 生效。"""
    s = client._sesh
    _seed_audit_logs(s, actions=[("login", "auth")])

    # 远古起始 → 仍有数据; 未来截止 → 空
    # naive ISO: 避免 aware ISO 的 +00:00 在 query string 里 + 被解析为空格 → 422
    start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    end_past = (datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None).isoformat()

    r_all = client.get(f"/api/v1/security/logs?start_time={start}")
    assert r_all.json()["data"]["total"] >= 1

    r_empty = client.get(f"/api/v1/security/logs?start_time={end_past}&end_time={end_past}")
    assert r_empty.json()["data"]["total"] == 0


# ── /security/policies: CRUD ──

def test_policies_list_admin(client):
    """admin 列出全部策略。"""
    s = client._sesh
    seeded = _seed_policies(s)

    r = client.get("/api/v1/security/policies")
    assert r.status_code == 200
    data = r.json()["data"]
    keys = {p["policy_key"] for p in data["items"]}
    assert keys == set(seeded.keys())
    # policy_config 是 dict (JSON 字段正确反序列化)
    pw = next(p for p in data["items"] if p["policy_key"] == "password")
    assert pw["policy_config"]["min_length"] == 8
    assert pw["status"] == "active"


def test_get_single_policy_and_404(client):
    """获取单个策略; 不存在返回 404。"""
    s = client._sesh
    _seed_policies(s)

    r = client.get("/api/v1/security/policies/password")
    assert r.status_code == 200
    assert r.json()["data"]["policy_key"] == "password"

    r404 = client.get("/api/v1/security/policies/nonexistent_key")
    assert r404.status_code == 404


def test_update_policy_admin(client):
    """admin 更新策略配置。"""
    s = client._sesh
    _seed_policies(s)

    r = client.put("/api/v1/security/policies/password", json={"policy_config": {"min_length": 12}})
    assert r.status_code == 200
    updated = r.json()["data"]
    assert updated["policy_config"]["min_length"] == 12
    # 落库
    s.expire_all()
    row = s.query(SecurityPolicy).filter(SecurityPolicy.policy_key == "password").first()
    assert row.policy_config["min_length"] == 12


def test_update_policy_status_validation(client):
    """非法 status 被拒。"""
    s = client._sesh
    _seed_policies(s)

    r = client.put("/api/v1/security/policies/password", json={"status": "bogus"})
    assert r.status_code in (400, 422)


def test_update_policy_404(client):
    """更新不存在的策略 404。"""
    r = client.put("/api/v1/security/policies/ghost", json={"description": "x"})
    assert r.status_code == 404


def test_update_policy_config_must_be_object(client):
    """policy_config 必须是 dict, 拒绝非法类型。"""
    s = client._sesh
    _seed_policies(s)

    r = client.put("/api/v1/security/policies/password", json={"policy_config": "not-a-dict"})
    assert r.status_code in (400, 422)


# ── 异常路径加固 (卡 f3e5633d) ──

def test_update_policy_integrity_conflict(client, monkeypatch):
    """更新策略遇唯一约束冲突 → 409, 不冒泡 500。"""
    from sqlalchemy.exc import IntegrityError

    s = client._sesh
    _seed_policies(s)

    def _boom(*a, **kw):
        raise IntegrityError("simulated", {}, Exception("UNIQUE"))

    monkeypatch.setattr(s, "commit", _boom)

    r = client.put("/api/v1/security/policies/password", json={"description": "新描述"})
    assert r.status_code == 409


def test_update_policy_audit_failure_does_not_break(client, monkeypatch):
    """策略已落库后审计日志写入失败 → 仍 200, 不让客户端误以为更新失败。"""
    s = client._sesh
    _seed_policies(s)

    from app.api.v1 import security as security_api

    def _boom(*a, **kw):
        raise RuntimeError("审计服务不可用")

    monkeypatch.setattr(security_api.audit_service, "log_crud", _boom)

    r = client.put("/api/v1/security/policies/password", json={"description": "审计容错"})
    assert r.status_code == 200


# ── 权限控制: 非 admin 403 ──

def _login(client, username, password):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_policies_require_admin(client, seed_users):
    """viewer 角色对策略端点 GET/PUT 均 403。"""
    token = _login(client, "viewer1", "view123")
    headers = {"Authorization": f"Bearer {token}"}

    r_get = client.get("/api/v1/security/policies", headers=headers)
    assert r_get.status_code == 403

    r_put = client.put(
        "/api/v1/security/policies/password",
        json={"policy_config": {"min_length": 16}},
        headers=headers,
    )
    assert r_put.status_code == 403

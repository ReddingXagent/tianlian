"""
Runbook审批端点角色层级校验测试 — 任务卡 b198e42c。

漏洞: approve/reject 端点只检查 get_current_user，从不校验
current_user.role 是否满足 approval.required_level。攻击链:
任何认证用户(默认 ENGINEER) → approve 任意 pending 审批(含 critical)
→ auto_execute_after_approval=True(默认) → _execute_approved_step
→ subprocess 主机执行命令 = 授权绕过→RCE。
RISK_TO_APPROVAL_LEVEL 只在 create 时写 required_level，执行侧废弃。

覆盖: 低级别用户 approve/reject 高级别审批 → 403；admin/platform_admin
放行；_execute_approved_step 执行前二次复核 status==approved(防重放/并发
竞态)；匿名 401(用 anon_client)。与 test_runbook_approval.py(基础 CRUD)
互补，本文件聚焦授权与执行守卫。
"""
from datetime import datetime, timedelta

import bcrypt
import pytest

from app.models.runbook_approval import RunbookApproval
from app.models.user import User, UserRole

APPROVE_URL = "/api/v1/runbook/approvals/{}/approve"
REJECT_URL = "/api/v1/runbook/approvals/{}/reject"


@pytest.fixture(scope="function")
def role_tokens(client):
    """seed 各角色用户并登录拿 token；返回 {role_key: token}。

    复用 conftest client 的 DB/app；admin 用 conftest 默认 seed 的(admin123)。
    角色覆盖审批层级体系的各档(operator/engineer/station_master/dispatcher/
    viewer/super_admin)，用以验证 ROLE_APPROVAL_LEVEL 映射与豁免逻辑。
    """
    s = client._sesh
    roles = {
        "operator":       ("rb_op",     UserRole.OPERATOR),
        "engineer":       ("rb_eng",    UserRole.ENGINEER),
        "station_master": ("rb_sm",     UserRole.STATION_MASTER),
        "dispatcher":     ("rb_disp",   UserRole.DISPATCHER),
        "viewer":         ("rb_viewer", UserRole.VIEWER),
        "super_admin":    ("rb_sadmin", UserRole.SUPER_ADMIN),
    }
    pwd = "rb123456"
    for uname, role in roles.values():
        if not s.query(User).filter(User.username == uname).first():
            s.add(User(
                username=uname,
                password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                role=role,
                status="active",
            ))
    s.commit()

    def _tok(uname):
        r = client.post("/api/v1/auth/login", data={"username": uname, "password": pwd})
        assert r.status_code == 200, f"登录失败 {uname}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    admin_r = client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "admin123"})
    assert admin_r.status_code == 200

    return {
        "operator": _tok("rb_op"),
        "engineer": _tok("rb_eng"),
        "station_master": _tok("rb_sm"),
        "dispatcher": _tok("rb_disp"),
        "viewer": _tok("rb_viewer"),
        "super_admin": _tok("rb_sadmin"),
        "admin": admin_r.json().get("data", {}).get("token") or admin_r.json().get("token"),
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _make_approval(client, **overrides):
    """直接向 conftest client 的 DB 插入一条 pending 审批，返回 id。

    auto_execute_after_approval 默认 False — approve 后不触发 subprocess，
    测试不依赖主机命令执行；执行守卫单独由 TestApprovalExecuteGuard 覆盖。
    """
    defaults = dict(
        runbook_id="RB-AUTH-001",
        alarm_id=9001,
        step_index=0,
        step_description="高危操作",
        action_type="command",
        command_preview="rm -rf /tmp/x",
        risk_level="critical",
        rollback_preview=None,
        status="pending",
        required_level="admin",
        auto_execute_after_approval=False,
        expires_at=datetime.now() + timedelta(minutes=60),
    )
    defaults.update(overrides)
    s = client._sesh
    a = RunbookApproval(**defaults)
    s.add(a)
    s.commit()
    s.refresh(a)
    return a.id


# ========== approve: 角色层级校验 ==========

class TestApproveRoleLevel:
    """approve 必须校验调用者角色层级 ≥ approval.required_level，否则 403。"""

    @pytest.mark.parametrize("role", ["engineer", "operator"])
    def test_low_role_cannot_approve_critical(self, client, role_tokens, role):
        """engineer/operator(rank1) approve critical(required=admin rank3) → 403。

        这正是 RCE 链的起点:低级别越权 approve critical → auto_execute →
        subprocess。校验必须在此拦断。
        """
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens[role]))
        assert r.status_code == 403, f"{role} approve critical 应 403, 实际 {r.status_code}: {r.text}"

    @pytest.mark.parametrize("role", ["engineer", "operator"])
    def test_low_role_cannot_approve_manager(self, client, role_tokens, role):
        """engineer/operator(rank1) approve required=manager(rank2) → 403。"""
        aid = _make_approval(client, risk_level="high", required_level="manager")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens[role]))
        assert r.status_code == 403

    def test_viewer_cannot_approve_operator_level(self, client, role_tokens):
        """viewer(rank0) approve operator(rank1) → 403（最低审批也拒）。"""
        aid = _make_approval(client, risk_level="medium", required_level="operator")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["viewer"]))
        assert r.status_code == 403

    def test_admin_can_approve_critical(self, client, role_tokens):
        """admin(rank3) approve critical(required=admin rank3) → 通过(同级)。"""
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "approved"

    def test_super_admin_exempt_critical(self, client, role_tokens):
        """super_admin 平台级豁免 → 通过(无视 required_level)。"""
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["super_admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "approved"

    def test_station_master_can_approve_manager(self, client, role_tokens):
        """站长(rank2) approve manager(rank2) → 通过(同级)。"""
        aid = _make_approval(client, risk_level="high", required_level="manager")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["station_master"]))
        assert r.status_code == 200

    def test_engineer_can_approve_operator_level(self, client, role_tokens):
        """engineer(rank1) approve operator(rank1) → 通过(同级)。"""
        aid = _make_approval(client, risk_level="medium", required_level="operator")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["engineer"]))
        assert r.status_code == 200

    def test_dispatcher_can_approve_manager(self, client, role_tokens):
        """调度员(rank2) approve manager(rank2) → 通过(同级)。"""
        aid = _make_approval(client, risk_level="high", required_level="manager")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "ok"}, headers=_h(role_tokens["dispatcher"]))
        assert r.status_code == 200

    def test_forbidden_approval_state_not_mutated(self, client, role_tokens):
        """403 拦截后审批仍 pending、approver 为空 — 越权请求不得篡改状态。"""
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(APPROVE_URL.format(aid),
                        json={"comment": "x"}, headers=_h(role_tokens["engineer"]))
        assert r.status_code == 403
        a = client._sesh.query(RunbookApproval).filter(RunbookApproval.id == aid).first()
        assert a.status == "pending"
        assert a.approver_id is None


# ========== reject: 同样的层级校验 ==========

class TestRejectRoleLevel:
    """reject 同样校验角色层级 — 低级别用户不能拒绝高级别审批。"""

    @pytest.mark.parametrize("role", ["engineer", "operator"])
    def test_low_role_cannot_reject_critical(self, client, role_tokens, role):
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(REJECT_URL.format(aid),
                        json={"reason": "no"}, headers=_h(role_tokens[role]))
        assert r.status_code == 403

    def test_viewer_cannot_reject_manager(self, client, role_tokens):
        aid = _make_approval(client, risk_level="high", required_level="manager")
        r = client.post(REJECT_URL.format(aid),
                        json={"reason": "no"}, headers=_h(role_tokens["viewer"]))
        assert r.status_code == 403

    def test_admin_can_reject_critical(self, client, role_tokens):
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(REJECT_URL.format(aid),
                        json={"reason": "no"}, headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "rejected"

    def test_super_admin_exempt_reject(self, client, role_tokens):
        aid = _make_approval(client, risk_level="critical", required_level="admin")
        r = client.post(REJECT_URL.format(aid),
                        json={"reason": "no"}, headers=_h(role_tokens["super_admin"]))
        assert r.status_code == 200


# ========== _execute_approved_step: 执行前状态守卫 ==========

class TestApprovalExecuteGuard:
    """_execute_approved_step 执行前二次复核 status==approved。

    防 approve commit 后、execute 前被并发 reject/expire 改写状态，
    仍继续执行命令(重放/竞态)。非 approved 一律跳过，不跑 subprocess。
    """

    def test_execute_skipped_when_rejected(self, client):
        from app.api.v1.runbook_approval import _execute_approved_step
        aid = _make_approval(client, status="rejected")
        approval = client._sesh.query(RunbookApproval).filter(
            RunbookApproval.id == aid).first()
        result = _execute_approved_step(approval, client._sesh)
        assert result["status"] == "skipped"
        assert "approved" in result.get("reason", "").lower()

    def test_execute_skipped_when_pending(self, client):
        from app.api.v1.runbook_approval import _execute_approved_step
        aid = _make_approval(client, status="pending")
        approval = client._sesh.query(RunbookApproval).filter(
            RunbookApproval.id == aid).first()
        result = _execute_approved_step(approval, client._sesh)
        assert result["status"] == "skipped"
        assert "approved" in result.get("reason", "").lower()


# ========== 匿名拒绝(401): 用 anon_client, 勿用 client ==========

class TestApprovalAnonymous:
    """匿名(无 token)访问审批端点 → 401。

    conftest 的 client fixture 会注入 admin token → 用 anon_client 测真匿名,
    否则假绿(任务卡明示坑)。
    """

    @pytest.mark.parametrize("path", [
        "/api/v1/runbook/approvals/pending",
        "/api/v1/runbook/approvals/history",
        "/api/v1/runbook/approvals/stats",
    ])
    def test_anon_get_401(self, anon_client, path):
        assert anon_client.get(path).status_code == 401

    def test_anon_approve_401(self, anon_client):
        r = anon_client.post("/api/v1/runbook/approvals/1/approve", json={"comment": "x"})
        assert r.status_code == 401

    def test_anon_reject_401(self, anon_client):
        r = anon_client.post("/api/v1/runbook/approvals/1/reject", json={"reason": "x"})
        assert r.status_code == 401

    def test_anon_expire_check_401(self, anon_client):
        assert anon_client.post("/api/v1/runbook/approvals/expire-check").status_code == 401

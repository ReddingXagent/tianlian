"""运营-企业充值审批 API 补全测试 (工作卡 1a810c16)

覆盖 app/api/v1/operate/enterprise_recharge.py (挂 /api/v1/operate 前缀):
- POST /operate/recharge/apply              提交充值申请 (get_current_admin 门)
- PUT  /operate/recharge/{id}/approve       审批通过 (admin 门 + 状态机)
- PUT  /operate/recharge/{id}/reject        审批拒绝 (admin 门 + 状态机)
- GET  /operate/recharge/applications       申请列表 (admin_required + team scoping)

与 tests/test_operate_enterprise_recharge.py (既有, 24 测试) 互补 —— 该文件聚焦
BUG1-6 修复族 + admin 视角状态机; 本文件补其未覆盖的真实缺口:
1. 非 admin (operator/viewer) 访问全部 4 端点 → 403 (get_current_admin / admin_required)
   —— 既有测试全用 admin client, 权限门零覆盖。
2. 审批状态机完备转换: approved 不可再 reject / rejected 不可再 approve /
   rejected 不可重复 reject (既有仅测 approved 重复 approve → 400)。
3. approve / reject 不存在申请 → 404; 列表分页参数校验。
4. 列表 team scoping: 两队各挂申请, admin 全可见 (豁免) —— 非 admin 的本队
   过滤行为由既有 tests/test_team_scoping.py 覆盖。

注: GET /applications 无 get_current_admin 门 (登录可见 + team 过滤);
   写端点 (apply/approve/reject) 走 get_current_admin → 非 admin 403。
"""
import uuid
from decimal import Decimal

import bcrypt
import pytest

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_recharge import RechargeApplication, RechargeStatus
from app.models.user import User, UserRole

RC_URL = "/api/v1/operate/recharge"


# ─── helpers (风格对齐 test_ops_invoice_request.py) ───

def _add_user(session, username, role=UserRole.OPERATOR, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_enterprise(session, *, team_id=None, name="", balance=Decimal("1000.00")):
    e = Enterprise(
        name=f"企业{name}{uuid.uuid4().hex[:4]}",
        code=f"ENT{uuid.uuid4().hex[:6].upper()}",
        balance=balance,
        status=EnterpriseStatus.ACTIVE,
        owner_team_id=team_id,
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


def _seed_application(session, *, enterprise_id, status=RechargeStatus.PENDING,
                      amount=Decimal("2000.00"), applicant="申请人甲"):
    a = RechargeApplication(
        enterprise_id=enterprise_id,
        amount=amount,
        status=status,
        remark="测试充值",
        applicant=applicant,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@pytest.fixture
def ent(client):
    """一家企业 + 本队 operator/viewer 双非 admin 身份 (真实缺口: 权限门)。"""
    s = client._sesh
    e = _seed_enterprise(s, name="RC")
    op = _add_user(s, f"rc_oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR)
    vw = _add_user(s, f"rc_viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER)
    return {
        "s": s, "ent": e, "op": op, "vw": vw,
        "op_token": _login_token(client, op.username),
        "vw_token": _login_token(client, vw.username),
    }


# ==================== 1. 非 admin 权限门 (403) ====================

class TestNonAdminForbidden:
    """全部 4 端点走 get_current_admin / @admin_required —— 非 admin 一律 403。

    operator 虽持 operate:manage (RBAC 矩阵), 但本路由族用独立 admin 门
    (充值属财务敏感操作), operator 同样被拒 —— 固化该设计意图。
    """

    def test_operator_apply_403(self, client, ent):
        r = client.post(
            f"{RC_URL}/apply",
            json={"enterprise_id": ent["ent"].id, "amount": 1000},
            headers=_auth(ent["op_token"]),
        )
        assert r.status_code == 403

    def test_operator_approve_403(self, client, ent):
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r = client.put(
            f"{RC_URL}/{a.id}/approve", json={"reason": "同意"},
            headers=_auth(ent["op_token"]),
        )
        assert r.status_code == 403

    def test_operator_reject_403(self, client, ent):
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r = client.put(
            f"{RC_URL}/{a.id}/reject", json={"reason": "材料不全"},
            headers=_auth(ent["op_token"]),
        )
        assert r.status_code == 403

    def test_operator_list_200_scoped(self, client, ent):
        """列表与写端点不同: 登录即可见 (无 get_current_admin 门), 由 team scoping 隔离。

        原 @admin_required 装饰器是纯透传标记 (无鉴权作用, 见 app/core/permissions.py),
        挂在 list 上误导「admin only」—— 已摘除 (卡 1a810c16, 行为零变化);
        非 admin 可见性由 enterprise→owner_team 过滤保证 (任务卡 ab5c5f17 设计)。
        """
        r = client.get(f"{RC_URL}/applications", headers=_auth(ent["op_token"]))
        assert r.status_code == 200

    def test_viewer_apply_403(self, client, ent):
        r = client.post(
            f"{RC_URL}/apply",
            json={"enterprise_id": ent["ent"].id, "amount": 1000},
            headers=_auth(ent["vw_token"]),
        )
        assert r.status_code == 403

    def test_anonymous_apply_401(self, anon_client):
        r = anon_client.post(f"{RC_URL}/apply", json={"enterprise_id": 1, "amount": 100})
        assert r.status_code == 401

    def test_anonymous_approve_401(self, anon_client):
        r = anon_client.put(f"{RC_URL}/1/approve", json={"reason": "x"})
        assert r.status_code == 401


# ==================== 2. 审批状态机完备转换 ====================

class TestApprovalStateMachine:
    """仅 PENDING 可审批; 任何方向二次操作 → 400 (不残留半处理状态)。"""

    def test_approved_cannot_reject(self, client, ent):
        """approved 后再 reject → 400 (资金已入账, 拒绝不可逆)。"""
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r1 = client.put(f"{RC_URL}/{a.id}/approve", json={"reason": "同意"})
        assert r1.status_code == 200
        r2 = client.put(f"{RC_URL}/{a.id}/reject", json={"reason": "反悔"})
        assert r2.status_code == 400
        assert "只能审批待审批" in r2.json()["detail"]

    def test_rejected_cannot_approve(self, client, ent):
        """rejected 后再 approve → 400 (防绕过审批记录二次入账)。"""
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r1 = client.put(f"{RC_URL}/{a.id}/reject", json={"reason": "材料不全"})
        assert r1.status_code == 200
        r2 = client.put(f"{RC_URL}/{a.id}/approve", json={"reason": "又同意"})
        assert r2.status_code == 400

    def test_rejected_cannot_reject_again(self, client, ent):
        """rejected 重复 reject → 400 (拒绝理由追加分支仅对 PENDING 可达)。"""
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r1 = client.put(f"{RC_URL}/{a.id}/reject", json={"reason": "一次"})
        assert r1.status_code == 200
        r2 = client.put(f"{RC_URL}/{a.id}/reject", json={"reason": "二次"})
        assert r2.status_code == 400

    def test_approved_balance_credited_once(self, client, ent):
        """approve 真实入账: 余额 1000 + 2000 = 3000 (admin 视角端到端)。"""
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id,
                              amount=Decimal("2000.00"))
        r = client.put(f"{RC_URL}/{a.id}/approve", json={"reason": "同意"})
        assert r.status_code == 200
        ent["s"].expire_all()
        fresh = ent["s"].query(Enterprise).filter_by(id=ent["ent"].id).first()
        assert Decimal(str(fresh.balance)) == Decimal("3000.00")

    def test_rejected_balance_unchanged(self, client, ent):
        """reject 不动余额。"""
        a = _seed_application(ent["s"], enterprise_id=ent["ent"].id)
        r = client.put(f"{RC_URL}/{a.id}/reject", json={"reason": "拒绝"})
        assert r.status_code == 200
        ent["s"].expire_all()
        fresh = ent["s"].query(Enterprise).filter_by(id=ent["ent"].id).first()
        assert Decimal(str(fresh.balance)) == Decimal("1000.00")


# ==================== 3. 404 / 参数校验 ====================

class TestNotFoundAndValidation:
    def test_approve_not_exist_404(self, client):
        r = client.put(f"{RC_URL}/999999/approve", json={"reason": "x"})
        assert r.status_code == 404

    def test_reject_not_exist_404(self, client):
        r = client.put(f"{RC_URL}/999999/reject", json={"reason": "x"})
        assert r.status_code == 404

    def test_apply_missing_enterprise_422(self, client):
        r = client.post(f"{RC_URL}/apply", json={"amount": 100})
        assert r.status_code == 422

    def test_apply_amount_as_string_coerced(self, client, ent):
        """amount 传字符串 "1500.50" → Decimal 强转成功 201 (Pydantic Decimal 宽容)。"""
        r = client.post(
            f"{RC_URL}/apply",
            json={"enterprise_id": ent["ent"].id, "amount": "1500.50"},
        )
        assert r.status_code == 201, r.text

    def test_list_invalid_page_422(self, client):
        r = client.get(f"{RC_URL}/applications", params={"page": 0})
        assert r.status_code == 422

    def test_list_invalid_page_size_422(self, client):
        r = client.get(f"{RC_URL}/applications", params={"page_size": 101})
        assert r.status_code == 422


# ==================== 4. 列表 admin 全可见 + 状态过滤 ====================

class TestListApplications:
    def test_admin_sees_all_teams(self, client, ent):
        """admin 平台级: 两队企业的申请均可见 (既有 team_scoping 测过滤, 此处测豁免)。"""
        from app.models.user import Team
        s = ent["s"]
        t1 = Team(name=f"RC队1{uuid.uuid4().hex[:4]}", code=f"R1{uuid.uuid4().hex[:4]}")
        t2 = Team(name=f"RC队2{uuid.uuid4().hex[:4]}", code=f"R2{uuid.uuid4().hex[:4]}")
        s.add_all([t1, t2]); s.commit(); s.refresh(t1); s.refresh(t2)
        e1 = _seed_enterprise(s, team_id=t1.id, name="甲")
        e2 = _seed_enterprise(s, team_id=t2.id, name="乙")
        _seed_application(s, enterprise_id=e1.id, applicant="甲申请人")
        _seed_application(s, enterprise_id=e2.id, applicant="乙申请人")
        r = client.get(f"{RC_URL}/applications")
        assert r.status_code == 200
        names = {i["applicant"] for i in r.json()["data"]["items"]}
        assert {"甲申请人", "乙申请人"} <= names

    def test_filter_by_status(self, client, ent):
        s = ent["s"]
        a1 = _seed_application(s, enterprise_id=ent["ent"].id, applicant="待审甲")
        a2 = _seed_application(s, enterprise_id=ent["ent"].id, applicant="待审乙")
        r1 = client.put(f"{RC_URL}/{a1.id}/approve", json={"reason": "同意"})
        assert r1.status_code == 200
        r = client.get(f"{RC_URL}/applications", params={"status": "pending"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert {i["applicant"] for i in items} == {"待审乙"}
        r2 = client.get(f"{RC_URL}/applications", params={"status": "approved"})
        assert {i["applicant"] for i in r2.json()["data"]["items"]} == {"待审甲"}

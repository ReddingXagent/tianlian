"""
运营-企业充值审批 API 测试

覆盖 /api/v1/operate/recharge:
- POST /recharge/apply              提交充值申请(需管理员 token)
- PUT  /recharge/{id}/approve       审批通过
- PUT  /recharge/{id}/reject        审批拒绝
- GET  /recharge/applications       申请列表

注:
- 使用模块级 TestClient(app.main.app) + autouse test_db fixture(覆盖 SessionLocal),
  与 test_operations_api 同一模式; admin 用户由 test_db seed。
- apply/approve/reject 通过 get_current_admin 鉴权, 需登录 token。
- 已知 bug: GET /applications 直接返回 ORM 对象(非空时序列化失败),
  故仅在空库场景验证该端点; approve/reject 写入未映射的 last_updated_at
  字段不影响流程(SQLAlchemy 不报错), 状态流转可正常验证。
"""
import pytest
from contextlib import contextmanager
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    # 预置真实企业(id=1, 余额1000): BUG3 修复后 approve 要求申请关联的企业必须存在,
    # 否则 500(不再静默吞)。现有 approve 测试默认 enterprise_id=1, 故 seed 之。
    from decimal import Decimal
    from app.models.enterprise import Enterprise, EnterpriseStatus
    s = test_db["session"]
    if not s.query(Enterprise).filter_by(id=1).first():
        s.add(Enterprise(
            id=1, name="测试企业A", code="ENT001",
            balance=Decimal("1000.00"), status=EnterpriseStatus.ACTIVE,
        ))
        s.commit()


def _login() -> str:
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_login()}"}


def _apply(amount=1000, enterprise_id=1) -> int:
    """提交申请, 返回 application_id"""
    r = client.post("/api/v1/operate/recharge/apply",
                    json={"enterprise_id": enterprise_id, "amount": amount, "remark": "测试充值"},
                    headers=_auth_headers())
    assert r.status_code == 201
    return r.json()["data"]["application_id"]


def _balance(ent_id: int = 1):
    """读取企业当前余额为 Decimal，供断言余额变更。

    SQLite Numeric 列返回类型随方言漂移(Decimal/float/str)，统一 Decimal(str(...)) 归一。
    """
    from decimal import Decimal
    from app.core.database import SessionLocal
    from app.models.enterprise import Enterprise
    s = SessionLocal()
    try:
        ent = s.query(Enterprise).filter_by(id=ent_id).first()
        return Decimal(str(ent.balance)) if ent and ent.balance is not None else Decimal("0")
    finally:
        s.close()


def _application_dict(app_id: int):
    """读取申请快照 dict(在 session 关闭前提取，避免 detached 访问)。"""
    from app.core.database import SessionLocal
    from app.models.enterprise_recharge import RechargeApplication
    s = SessionLocal()
    try:
        a = s.query(RechargeApplication).filter_by(id=app_id).first()
        if not a:
            return None
        return {
            "status": a.status,
            "remark": a.remark,
            "approve_reason": a.approve_reason,
            "reject_reason": a.reject_reason,
            "approver": a.approver,
        }
    finally:
        s.close()


@contextmanager
def _anon_request():
    """临时摘除模块级 client 的全局 admin token，模拟真正的匿名请求。

    conftest 的 autouse fixture `_auth_module_level_client` 会给模块级
    `client = TestClient(app)` 注入 admin Authorization 头，使绝大多数 API
    测试默认在登录态运行。但「匿名拒绝(401)」类测试若直接复用该 client，
    请求实际带 token 而被放行，永远测不出拒绝——故此类测试必须先摘除 token。
    """
    saved = client.headers.pop("Authorization", None)
    try:
        yield
    finally:
        if saved:
            client.headers["Authorization"] = saved


class TestOperateEnterpriseRecharge:
    """企业充值申请 / 审批通过 / 审批拒绝 / 列表"""

    def test_apply_recharge_success(self):
        """提交申请: 返回 pending + application_id"""
        r = client.post("/api/v1/operate/recharge/apply",
                        json={"enterprise_id": 1, "amount": 5000, "remark": "首次充值"},
                        headers=_auth_headers())
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["status"] == "pending"
        assert data["application_id"] > 0

    def test_apply_recharge_validation_error(self):
        """缺少 enterprise_id 触发 422"""
        r = client.post("/api/v1/operate/recharge/apply",
                        json={"amount": 1000},
                        headers=_auth_headers())
        assert r.status_code == 422

    def test_apply_recharge_requires_auth(self):
        """未带 token 提交申请应被鉴权拒绝(401/403)"""
        with _anon_request():
            r = client.post("/api/v1/operate/recharge/apply",
                            json={"enterprise_id": 1, "amount": 1000})
            assert r.status_code in (401, 403)

    def test_approve_recharge_requires_auth(self):
        """未带 token 审批应被鉴权拒绝(401/403)"""
        with _anon_request():
            r = client.put("/api/v1/operate/recharge/1/approve",
                           json={"approver": "admin"})
            assert r.status_code in (401, 403)

    def test_reject_recharge_requires_auth(self):
        """未带 token 拒绝应被鉴权拒绝(401/403)"""
        with _anon_request():
            r = client.put("/api/v1/operate/recharge/1/reject",
                           json={"approver": "admin"})
            assert r.status_code in (401, 403)

    def test_approve_recharge_success(self):
        """审批通过: 状态流转 approved"""
        app_id = _apply(amount=2000)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"approver": "admin", "reason": "同意"},
                       headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"] == "审批通过"

    def test_reject_recharge_success(self):
        """审批拒绝: 状态流转 rejected"""
        app_id = _apply(amount=3000)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                       json={"approver": "admin", "reason": "材料不全"},
                       headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"] == "审批拒绝"

    def test_approve_not_found(self):
        """审批不存在的申请: 404"""
        r = client.put("/api/v1/operate/recharge/999999/approve",
                       json={"approver": "admin"},
                       headers=_auth_headers())
        assert r.status_code == 404

    def test_approve_already_processed(self):
        """重复审批已处理的申请: 400"""
        app_id = _apply(amount=4000)
        client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                   json={"approver": "admin"}, headers=_auth_headers())
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"approver": "admin"}, headers=_auth_headers())
        assert r.status_code == 400

    def test_list_applications_empty(self):
        """申请列表(空库): 结构正确, items 为空"""
        r = client.get("/api/v1/operate/recharge/applications")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_applications_non_empty(self):
        """非空列表: 序列化为干净 dict(200 不500、不泄漏 ORM 内部状态) + 分页生效 [2fb8594a]"""
        # 插入 12 条，超过默认 page_size=10 —— 暴露原代码 query.all() 覆盖分页的 bug
        for _ in range(12):
            _apply(amount=1500, enterprise_id=1)
        r = client.get("/api/v1/operate/recharge/applications")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 12              # 总数正确
        assert len(data["items"]) == 10         # 分页生效(默认 page_size=10)，不再被无分页 query.all() 覆盖
        item = data["items"][0]
        assert isinstance(item, dict)
        assert "_sa_instance_state" not in item  # ORM 内部状态不泄漏
        for key in ("id", "enterprise_id", "amount", "status", "applicant"):
            assert key in item, f"缺少字段 {key}"
        assert item["enterprise_id"] == 1
        assert item["status"] == "pending"
        assert isinstance(item["amount"], (int, float))

    def test_list_applications_status_filter(self):
        """status 过滤回归: 删除原冗余覆盖后，字符串 status 过滤仍正确生效"""
        _apply(amount=1000, enterprise_id=1)
        _apply(amount=2000, enterprise_id=1)
        r = client.get("/api/v1/operate/recharge/applications?status=pending")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 2
        assert all(it["status"] == "pending" for it in data["items"])
        r2 = client.get("/api/v1/operate/recharge/applications?status=approved")
        assert r2.status_code == 200
        assert r2.json()["data"]["total"] == 0


class TestEnterpriseRechargeBugFixes:
    """BUG1-6 修复的 edge case 覆盖 (卡 0228ac86)。

    覆盖矩阵:
      BUG1 财务原子性 → 余额正确累加 / 单次合并事务 / 重复 approve 不双加 / enterprise 缺失回滚
      BUG2 amount 约束 → 零额/负额拒绝
      BUG3 enterprise 缺失 → 显式 500(不静默吞)
      BUG4 异常保护 → 异常被捕获转业务错误(见 BUG1/BUG3 断言 status_code)
      BUG5 死参数 approver → schema 不再 require / 客户端传入被忽略(取 current_user)
      BUG6 remark 覆盖 → 审批理由写独立字段(approve_reason/reject_reason)，不覆盖 remark
    """

    # ── BUG2: amount 必须 > 0 ──────────────────────────────────────────
    def test_apply_rejects_zero_amount(self):
        """amount=0 触发 422 (gt=0 约束)。"""
        r = client.post("/api/v1/operate/recharge/apply",
                        json={"enterprise_id": 1, "amount": 0, "remark": "零额"},
                        headers=_auth_headers())
        assert r.status_code == 422

    def test_apply_rejects_negative_amount(self):
        """amount<0 触发 422: 防止 approve 后从余额扣款(变提现)。"""
        r = client.post("/api/v1/operate/recharge/apply",
                        json={"enterprise_id": 1, "amount": -500, "remark": "负额"},
                        headers=_auth_headers())
        assert r.status_code == 422

    # ── BUG3 + BUG1 原子回滚: enterprise 不存在 ─────────────────────────
    def test_approve_nonexistent_enterprise_returns_500_and_keeps_pending(self):
        """enterprise 不存在: 显式 500(不静默200) + 申请保持 pending + 余额不变。

        旧代码: 先 commit 申请 APPROVED → 再查 enterprise 不存在静默跳过 → 申请 APPROVED
                但余额未更新(数据不一致, BUG1+BUG3)。修复后: 合并事务内 enterprise 缺失
                → rollback + 500, 申请与余额同生共死。
        """
        # enterprise_id=99999 不存在; SQLite FK 不强制, 可建孤儿申请
        app_id = _apply(amount=2000, enterprise_id=99999)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"reason": "同意"}, headers=_auth_headers())
        assert r.status_code == 500  # BUG3: 不再静默成功
        snap = _application_dict(app_id)
        from app.models.enterprise_recharge import RechargeStatus
        assert snap["status"] == RechargeStatus.PENDING  # BUG1: 未提前落库 APPROVED
        assert _balance(1) == Decimal("1000.00")          # 余额未变

    # ── BUG1: 余额正确累加 ─────────────────────────────────────────────
    def test_approve_increases_balance_correctly(self):
        """approve 后余额 = 原余额 + amount (quantize 0.01)。"""
        app_id = _apply(amount=2000, enterprise_id=1)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"reason": "同意"}, headers=_auth_headers())
        assert r.status_code == 200
        assert _balance(1) == Decimal("1000.00") + Decimal("2000.00")

    # ── BUG1: 合并单次事务(无中间提交点) ───────────────────────────────
    def test_approve_uses_single_atomic_commit(self):
        """approve 只 commit 一次: 申请状态与余额绑定同一事务。

        旧代码两次 commit(申请状态 + 余额各一次); 修复后合并为单次 commit。
        通过 dependency override 注入受控 session 并 spy commit 次数。
        """
        from app.core.database import get_db, SessionLocal
        from sqlalchemy.orm import Session
        from app.main import app as main_app
        app_id = _apply(amount=2000, enterprise_id=1)
        # 先取认证头: login 必须在 override 设置前完成, 否则 login 请求也走 spy_session
        # 其 commit 会被计入 calls, 污染 commit 次数断言。
        auth_headers = _auth_headers()
        real_commit = Session.commit
        calls = []
        spy_session = SessionLocal()

        def spy_commit(self_, *a, **kw):
            calls.append(1)
            return real_commit(self_)

        spy_session.commit = lambda *a, **kw: spy_commit(spy_session)
        main_app.dependency_overrides[get_db] = lambda: spy_session
        try:
            r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                           json={"reason": "同意"}, headers=auth_headers)
        finally:
            main_app.dependency_overrides.pop(get_db, None)
            spy_session.close()
        assert r.status_code == 200
        assert len(calls) == 1  # 单次 commit = 合并事务(旧代码为 2)

    # ── BUG1: 重复 approve 不双加(并发安全) ────────────────────────────
    def test_repeated_approve_does_not_double_credit(self):
        """同一申请重复 approve: 第二次 400, 余额只加一次。"""
        app_id = _apply(amount=2000, enterprise_id=1)
        r1 = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                        json={"reason": "同意"}, headers=_auth_headers())
        assert r1.status_code == 200
        r2 = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                        json={"reason": "再同意"}, headers=_auth_headers())
        assert r2.status_code == 400  # 状态守卫拦截已 APPROVED
        assert _balance(1) == Decimal("1000.00") + Decimal("2000.00")  # 仅加一次

    # ── BUG6: 审批理由不覆盖申请人 remark ──────────────────────────────
    def test_approve_preserves_remark_separates_approve_reason(self):
        """approve reason 写 approve_reason, 不覆盖申请人 remark。"""
        app_id = _apply(amount=1500, enterprise_id=1)  # _apply 固定 remark="测试充值"
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"reason": "审批同意"}, headers=_auth_headers())
        assert r.status_code == 200
        snap = _application_dict(app_id)
        assert snap["remark"] == "测试充值"        # 申请人备注保留
        assert snap["approve_reason"] == "审批同意"  # 审批理由写独立字段

    # ── BUG5: schema 删除 approver 死参数 ──────────────────────────────
    def test_approve_works_without_approver_field(self):
        """不传 approver 也能审批: schema 不再 require, 实际取 current_user。"""
        app_id = _apply(amount=1200, enterprise_id=1)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"reason": "同意"}, headers=_auth_headers())  # 无 approver
        assert r.status_code == 200

    def test_approve_ignores_client_supplied_approver(self):
        """客户端传入的 approver 被忽略, 实际审批人取 current_user。"""
        app_id = _apply(amount=1300, enterprise_id=1)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                       json={"approver": "恶意伪造人", "reason": "同意"},
                       headers=_auth_headers())
        assert r.status_code == 200
        snap = _application_dict(app_id)
        assert snap["approver"] == "admin"  # current_user.username, 非客户端传入值

class TestRejectRechargeRowLockCardDcdf24d1:
    """reject_recharge 行锁防并发终态覆盖回归 (卡 dcdf24d1)。

    背景: reject 的申请查询原为裸 .first() 无锁, 并发 approve+reject 同一申请时,
    reject 可基于 PENDING 旧快照通过校验, 在 approve 提交后把 APPROVED 覆盖为
    REJECTED → "已拒绝但钱已入账"。修复: 查询加 with_for_update()
    (PG 生效防竞态; SQLite no-op 由 status != PENDING 校验兜底)。
    """

    def test_reject_already_approved_returns_400(self):
        """① reject 非 PENDING(APPROVED) 申请: 400"""
        app_id = _apply(amount=2100)
        r1 = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                        json={"reason": "同意"}, headers=_auth_headers())
        assert r1.status_code == 200
        r2 = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                        json={"reason": "材料不全"}, headers=_auth_headers())
        assert r2.status_code == 400

    def test_reject_already_rejected_returns_400(self):
        """① reject 非 PENDING(REJECTED) 申请: 400"""
        app_id = _apply(amount=2200)
        r1 = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                        json={"reason": "材料不全"}, headers=_auth_headers())
        assert r1.status_code == 200
        r2 = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                        json={"reason": "再拒"}, headers=_auth_headers())
        assert r2.status_code == 400

    def test_reject_after_approve_keeps_approved_state_and_balance(self):
        """② approve 后再 reject 同单: 400 + 状态仍 APPROVED + 余额不被回滚"""
        app_id = _apply(amount=2300)
        r1 = client.put(f"/api/v1/operate/recharge/{app_id}/approve",
                        json={"reason": "同意"}, headers=_auth_headers())
        assert r1.status_code == 200
        r2 = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                        json={"reason": "材料不全"}, headers=_auth_headers())
        assert r2.status_code == 400
        snap = _application_dict(app_id)
        from app.models.enterprise_recharge import RechargeStatus
        assert snap["status"] == RechargeStatus.APPROVED  # 终态未被覆盖
        assert snap["reject_reason"] is None               # 未写入拒绝理由
        assert _balance(1) == Decimal("1000.00") + Decimal("2300.00")  # 入账未被破坏

    def test_reject_pending_application_succeeds(self):
        """③ 正常 reject 成功路径: 200 + 状态 REJECTED + 余额不变"""
        app_id = _apply(amount=2400)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                       json={"reason": "材料不全"}, headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"] == "审批拒绝"
        snap = _application_dict(app_id)
        from app.models.enterprise_recharge import RechargeStatus
        assert snap["status"] == RechargeStatus.REJECTED
        assert snap["reject_reason"] == "材料不全"
        assert _balance(1) == Decimal("1000.00")  # 拒绝不入账


    # ── BUG6 回归: reject reason 不覆盖 remark ─────────────────────────
    def test_reject_records_reason_without_overwriting_remark(self):
        """reject reason 写 reject_reason, 不覆盖 remark, approve_reason 保持 None。"""
        app_id = _apply(amount=1400, enterprise_id=1)
        r = client.put(f"/api/v1/operate/recharge/{app_id}/reject",
                       json={"reason": "材料不全"}, headers=_auth_headers())
        assert r.status_code == 200
        snap = _application_dict(app_id)
        assert snap["remark"] == "测试充值"
        assert snap["reject_reason"] == "材料不全"
        assert snap["approve_reason"] is None

"""工作卡 d53a2f2f — 进件状态机 mock 手动推进端点 + sub_mchid mock_ 前缀

补全卡 280c85ee 留下的两个观察项:
- 缺口①: applyment.advance() 仅有 service 层纯函数, 无 HTTP 端点 → 补 POST advance 端点
  (mock 演示用; 真实接入由IM-B异步通知驱动)
- 缺口②: mock 生成的 sub_mchid 形如真实商户号 "249...", 难以与真实返回区分 → mock_ 前缀

契约: backend/docs/contracts/user-client-contract.md §3.2 (七态状态机)
覆盖: 七态流转(AUDITING→TO_BE_SIGNED→SIGNING→FINISH) / REJECTED驳回+resubmit /
      FROZEN冻结/解冻 / 非法迁移400 / 未知code 404 / 非法event 422 / 跨团队404 /
      viewer 403 / sub_mchid mock_ 前缀 (端点层 + client 单元层)
"""
import bcrypt
import pytest

from app.services.wx_pay import applyment as ap


# ─── 测试脚手架 (与 test_wx_merchant_payment.py 同模式) ───

def _seed_team(client, name, code):
    from app.models.user import Team

    s = client._sesh
    t = Team(name=name, code=code)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _seed_operator(client, username, team, pwd="adv123456"):
    from app.models.user import User, UserRole

    s = client._sesh
    u = User(
        username=username,
        real_name=username,
        role=UserRole.OPERATOR,
        team_id=team.id,
        status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _viewer_token(client):
    from app.models.user import User, UserRole

    s = client._sesh
    if not s.query(User).filter(User.username == "adv_viewer").first():
        s.add(
            User(
                username="adv_viewer",
                real_name="只读",
                role=UserRole.VIEWER,
                status="active",
                password_hash=bcrypt.hashpw(b"view123456", bcrypt.gensalt()).decode(),
            )
        )
        s.commit()
    r = client.post(
        "/api/v1/auth/login", data={"username": "adv_viewer", "password": "view123456"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _applyment_payload(**over):
    p = {
        "merchant_type": "micro_merchant",
        "merchant_name": "李某某",
        "contact": {"name": "李某某", "phone": "139****0002"},
        "id_card": {"name": "李某某", "number": "***************002"},
        "settlement": {
            "account_type": "personal",
            "bank_name": "工商银行",
            "account_number": "************5678",
        },
        "station_ids": ["st_0002"],
    }
    p.update(over)
    return p


def _submit(client, *, headers=None, **over):
    """提交进件, 返回 business_code。"""
    r = client.post(
        "/api/v1/ops/merchants/applyment",
        json=_applyment_payload(**over),
        headers=headers,
    )
    assert r.status_code == 202, f"进件提交失败: {r.text}"
    return r.json()["data"]["business_code"]


def _advance(client, code, event, *, reject_reason=None, headers=None):
    body = {"event": event}
    if reject_reason is not None:
        body["reject_reason"] = reject_reason
    return client.post(
        f"/api/v1/ops/merchants/applyment/{code}/advance",
        json=body,
        headers=headers,
    )


# ─── advance 端点: 七态流转 ───

class TestApplymentAdvanceEndpoint:
    """卡 d53a2f2f — mock 手动推进进件状态机 HTTP 端点 (契约 §3.2 七态)。"""

    def test_normal_path_auditing_to_finish(self, client):
        code = _submit(client)
        r = _advance(client, code, "audit_pass")
        assert r.status_code == 200
        assert r.json()["data"]["applyment_state"] == "TO_BE_SIGNED"
        assert r.json()["data"]["legal_validation_url"]  # TO_BE_SIGNED 生成验证链接

        r = _advance(client, code, "validate")
        assert r.json()["data"]["applyment_state"] == "SIGNING"

        r = _advance(client, code, "finish")
        d = r.json()["data"]
        assert d["applyment_state"] == "FINISH"
        # 卡 d53a2f2f 缺口②: sub_mchid 用 mock_ 前缀
        assert d["sub_mchid"] and d["sub_mchid"].startswith("mock_")
        # FINISH → merchant_status=ACTIVE (可收款), advance 响应携带运行态
        assert d["merchant_status"] == "ACTIVE"

    def test_finish_sub_mchid_mock_prefix_via_detail(self, client):
        """进件详情查询确认 FINISH 后 sub_mchid 带 mock_ 前缀。"""
        code = _submit(client)
        for ev in ("audit_pass", "validate", "finish"):
            _advance(client, code, ev)
        d = client.get(f"/api/v1/ops/merchants/applyment/{code}").json()["data"]
        assert d["applyment_state"] == "FINISH"
        assert d["sub_mchid"] is not None
        assert d["sub_mchid"].startswith("mock_")

    def test_reject_records_reason(self, client):
        code = _submit(client)
        r = _advance(client, code, "audit_reject", reject_reason="材料不全")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["applyment_state"] == "REJECTED"
        assert d["reject_reason"] == "材料不全"

    def test_resubmit_from_rejected_back_to_auditing(self, client):
        code = _submit(client)
        _advance(client, code, "audit_reject", reject_reason="缺执照")
        r = _advance(client, code, "resubmit")
        assert r.status_code == 200
        assert r.json()["data"]["applyment_state"] == "AUDITING"

    def test_freeze_and_unfreeze(self, client):
        code = _submit(client)
        r = _advance(client, code, "freeze")
        assert r.json()["data"]["applyment_state"] == "FROZEN"
        r = _advance(client, code, "unfreeze")
        assert r.status_code == 200
        assert r.json()["data"]["applyment_state"] == "AUDITING"

    def test_freeze_from_finish_terminal(self, client):
        """FINISH 后仍可冻结 (运营封禁收款), FROZEN 为冻结终态除非 unfreeze。"""
        code = _submit(client)
        for ev in ("audit_pass", "validate", "finish"):
            _advance(client, code, ev)
        r = _advance(client, code, "freeze")
        assert r.json()["data"]["applyment_state"] == "FROZEN"


# ─── advance 端点: 错误码 ───

class TestApplymentAdvanceErrors:
    def test_illegal_transition_400(self, client):
        """AUDITING 直接 finish (跳级) → 400 非法迁移。"""
        code = _submit(client)  # 初始 AUDITING
        r = _advance(client, code, "finish")
        assert r.status_code == 400

    def test_unknown_code_404(self, client):
        r = _advance(client, "APL_NOT_EXIST", "audit_pass")
        assert r.status_code == 404

    def test_invalid_event_422(self, client):
        """非法 event 字符串 → 422 (Literal 校验)。"""
        code = _submit(client)
        r = _advance(client, code, "bogus_event")
        assert r.status_code == 422

    def test_cross_team_404(self, client):
        ta = _seed_team(client, "推进团队A", "ADVTA")
        tb = _seed_team(client, "推进团队B", "ADVTB")
        tok_a = _seed_operator(client, "adv_op_a", ta)
        tok_b = _seed_operator(client, "adv_op_b", tb)
        code = _submit(client, headers=_h(tok_a))  # A 创建 (team_id=ta)
        # B 跨团队推进 → 404 (不泄露存在性)
        r = _advance(client, code, "audit_pass", headers=_h(tok_b))
        assert r.status_code == 404
        # A 自己仍可推进
        assert _advance(client, code, "audit_pass", headers=_h(tok_a)).status_code == 200

    def test_viewer_forbidden(self, client):
        tok = _viewer_token(client)
        code = _submit(client)  # admin 创建
        r = _advance(client, code, "audit_pass", headers=_h(tok))
        assert r.status_code == 403

    def test_anon_unauthorized(self, anon_client):
        r = _advance(anon_client, "APL_ANY", "audit_pass")
        assert r.status_code == 401


# ─── 缺口②: sub_mchid mock_ 前缀 (client 单元层) ───

class TestMockSubMchidPrefix:
    """卡 d53a2f2f 缺口② — mock 生成的特约商户号带 mock_ 前缀, 与真实IM-B返回区分。"""

    def test_generate_sub_mchid_has_mock_prefix(self):
        from app.services.wx_pay.mock_client import MockWxPayClient

        sub = MockWxPayClient().generate_sub_mchid()
        assert sub.startswith("mock_")
        # 前缀后仍有数字串 (贴近真实 10 位形态), 非空占位
        digits = sub[len("mock_"):]
        assert len(digits) >= 8
        assert digits.isdigit()

    def test_generate_sub_mchid_unique(self):
        """多次生成不重复 (secrets 随机)。"""
        from app.services.wx_pay.mock_client import MockWxPayClient

        c = MockWxPayClient()
        vals = {c.generate_sub_mchid() for _ in range(20)}
        assert len(vals) == 20

    def test_advance_finish_uses_mock_prefixed_sub_mchid(self, client):
        """service 层 advance→FINISH 生成的 sub_mchid 带 mock_ 前缀 (端到端)。"""
        from app.models.merchant import ApplymentState, MerchantStatus

        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        for ev in ("audit_pass", "validate", "finish"):
            m = ap.advance(client._sesh, m, ev)
        assert m.applyment_state == ApplymentState.FINISH
        assert m.merchant_status == MerchantStatus.ACTIVE
        assert m.sub_mchid.startswith("mock_")

"""运营-特约商户进件 API 测试 (任务卡 a201d398)

覆盖 app/api/v1/operate/ops_merchants.py 四个端点 (挂 /api/v1/ops 前缀, 契约 §3):
- POST /ops/merchants/applyment                  进件提交 → 202
- GET  /ops/merchants/applyment/{business_code}  进件状态查询
- GET  /ops/merchants                            商户列表 (team scoping)
- POST /ops/merchants/applyment/{business_code}/advance  [mock] 状态机手动推进

测试维度: 进件正常流程 / 参数校验(422) / 状态查询(存在·不存在·跨team) /
列表 team scoping(同team·跨team隔离·admin豁免) / 权限门(viewer→403·匿名→401) /
状态机推进(合法·非法·FINISH 生成 sub_mchid) / wx_pay 外部调用异常保护(502)。

权限: router-level require_permission("operate:manage") —— admin 恒通过,
operator/engineer 等持 operate:manage 放行, viewer/auditor 不持 → 403。
故权限门测试用 viewer, team scoping 测试用 operator(持权限 + 有 team_id)。
"""
import uuid

import bcrypt
import pytest

from app.models.merchant import (
    Merchant,
    ApplymentState,
    MerchantStatus,
    MerchantType,
)
from app.models.user import Team, UserRole, User
from app.services.wx_pay import reset_wxpay_client_for_testing


OPS_URL = "/api/v1/ops/merchants"


# ─── helpers ───

def _add_user(session, username, role, team_id=None, password="pw123456"):
    """创建并提交用户, 返回 ORM (供 team scoping / 403 测试复用)。"""
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
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_merchant(
    session,
    *,
    team_id=None,
    state=ApplymentState.AUDITING,
    status=MerchantStatus.PENDING,
    name="测试商户",
    business_code=None,
    sub_mchid=None,
):
    """直接落一条 Merchant (绕过状态机, 模拟任意中间态), 供查询/列表/advance 测试。"""
    m = Merchant(
        business_code=business_code or f"APL_TEST_{uuid.uuid4().hex[:10].upper()}",
        team_id=team_id,
        merchant_type=MerchantType.MICRO_MERCHANT,
        merchant_name=name,
        applyment_state=state,
        merchant_status=status,
        profit_sharing_enabled=False,
        sub_mchid=sub_mchid,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


VALID_BODY = {
    "merchant_type": "micro_merchant",
    "merchant_name": "张某某",
    "contact": {"name": "张某某", "phone": "13800000001"},
    "id_card": {"name": "张某某", "number": "110101199001011234"},
    "settlement": {
        "account_type": "personal",
        "bank_name": "招商银行",
        "account_number": "6225000012345678",
    },
    "station_ids": ["st_0001"],
}


# ─── 两团队 + 两 operator 脚手架 (team scoping 复用) ───

@pytest.fixture
def two_teams(client):
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    ta = Team(name=f"MCH团队A{h}", code=f"MCHA{h}")
    tb = Team(name=f"MCH团队B{h}", code=f"MCHB{h}")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    op_a = _add_user(s, f"mch_op_a_{h}", UserRole.OPERATOR, team_id=ta.id)
    op_b = _add_user(s, f"mch_op_b_{h}", UserRole.OPERATOR, team_id=tb.id)

    return {
        "s": s,
        "ta": ta,
        "tb": tb,
        "op_a": op_a,
        "op_b": op_b,
        "token_a": _login_token(client, f"mch_op_a_{h}"),
        "token_b": _login_token(client, f"mch_op_b_{h}"),
    }


# ==================== A1. 进件正常流程 ====================

class TestSubmitApplyment:
    """POST /ops/merchants/applyment → 202 + applyment_state=AUDITING (契约 §3.1)。

    submit_applyment service 仅落 DB (无外部依赖), 直接走真实 service 端到端验证,
    覆盖 service 层 team 归属 / business_code 生成 / 字段拆分逻辑。
    """

    def test_submit_returns_202_and_auditing(self, client):
        r = client.post(f"{OPS_URL}/applyment", json=VALID_BODY)
        assert r.status_code == 202, r.text
        d = r.json()
        assert d["code"] == 0
        assert d["data"]["applyment_state"] == "AUDITING"
        assert d["data"]["business_code"].startswith("APL_")

    def test_submit_persists_record_and_team_none_for_admin(self, client):
        """admin(team_id=None) 进件 → 落库, team_id=None (平台级)。"""
        r = client.post(f"{OPS_URL}/applyment", json=VALID_BODY)
        assert r.status_code == 202
        code = r.json()["data"]["business_code"]
        m = client._sesh.query(Merchant).filter(Merchant.business_code == code).first()
        assert m is not None
        assert m.team_id is None  # admin 平台级
        assert m.applyment_state == ApplymentState.AUDITING
        assert m.merchant_status == MerchantStatus.PENDING
        assert m.merchant_type == MerchantType.MICRO_MERCHANT

    def test_submit_team_user_records_team_id(self, client, two_teams):
        """operator 进件 → merchant.team_id = operator.team_id。"""
        client.headers["Authorization"] = f"Bearer {two_teams['token_a']}"
        r = client.post(f"{OPS_URL}/applyment", json={**VALID_BODY, "merchant_name": "团队A商户"})
        assert r.status_code == 202
        code = r.json()["data"]["business_code"]
        m = client._sesh.query(Merchant).filter(Merchant.business_code == code).first()
        assert m.team_id == two_teams["ta"].id

    def test_submit_minimal_body_accepted(self, client):
        """仅 merchant_type + merchant_name (其余可选) → 202。"""
        r = client.post(
            f"{OPS_URL}/applyment",
            json={"merchant_type": "enterprise", "merchant_name": "最小商户"},
        )
        assert r.status_code == 202
        assert r.json()["data"]["applyment_state"] == "AUDITING"

    def test_submit_settlement_last4_extracted(self, client):
        """结算账号末四位落 settlement_account_last4 (列表展示用)。"""
        r = client.post(f"{OPS_URL}/applyment", json=VALID_BODY)
        code = r.json()["data"]["business_code"]
        m = client._sesh.query(Merchant).filter(Merchant.business_code == code).first()
        assert m.settlement_account_last4 == "5678"


# ==================== A2. 参数校验 (422) ====================

class TestSubmitValidation:
    """router-level require_permission 在 body 解析前执行 (admin 通过), 故 422 用 admin。"""

    def test_missing_merchant_type(self, client):
        body = {k: v for k, v in VALID_BODY.items() if k != "merchant_type"}
        r = client.post(f"{OPS_URL}/applyment", json=body)
        assert r.status_code == 422

    def test_invalid_merchant_type(self, client):
        r = client.post(
            f"{OPS_URL}/applyment", json={**VALID_BODY, "merchant_type": "unknown_type"}
        )
        assert r.status_code == 422

    def test_missing_merchant_name(self, client):
        body = {k: v for k, v in VALID_BODY.items() if k != "merchant_name"}
        r = client.post(f"{OPS_URL}/applyment", json=body)
        assert r.status_code == 422

    def test_empty_merchant_name(self, client):
        r = client.post(
            f"{OPS_URL}/applyment", json={**VALID_BODY, "merchant_name": ""}
        )
        assert r.status_code == 422


# ==================== A3. 状态查询 ====================

class TestGetApplyment:
    """GET /ops/merchants/applyment/{business_code} (契约 §3.2)。"""

    def test_get_existing_returns_detail(self, client):
        m = _seed_merchant(client._sesh, name="查询商户")
        r = client.get(f"{OPS_URL}/applyment/{m.business_code}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["business_code"] == m.business_code
        assert d["merchant_name"] == "查询商户"
        assert d["merchant_type"] == "micro_merchant"
        assert d["applyment_state"] == "AUDITING"
        assert "updated_at" in d

    def test_get_unknown_code_404(self, client):
        r = client.get(f"{OPS_URL}/applyment/APL_NOT_EXIST_9999")
        assert r.status_code == 404

    def test_get_cross_team_404(self, client, two_teams):
        """team 级用户查他 team 商户 → 404 (不泄露存在)。"""
        m = _seed_merchant(client._sesh, team_id=two_teams["ta"].id, name="A队商户")
        r = client.get(
            f"{OPS_URL}/applyment/{m.business_code}",
            headers=_auth(two_teams["token_b"]),
        )
        assert r.status_code == 404

    def test_get_same_team_ok(self, client, two_teams):
        m = _seed_merchant(client._sesh, team_id=two_teams["ta"].id, name="A队商户")
        r = client.get(
            f"{OPS_URL}/applyment/{m.business_code}",
            headers=_auth(two_teams["token_a"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["merchant_name"] == "A队商户"


# ==================== A4. 列表 team scoping ====================

class TestListMerchants:
    """GET /ops/merchants (契约 §3.3)。admin 全可见, team 级仅本 team。"""

    def test_admin_sees_all_teams(self, client, two_teams):
        _seed_merchant(client._sesh, team_id=two_teams["ta"].id, name="商户A")
        _seed_merchant(client._sesh, team_id=two_teams["tb"].id, name="商户B")
        r = client.get(OPS_URL)
        assert r.status_code == 200
        names = {i["merchant_name"] for i in r.json()["data"]["items"]}
        assert {"商户A", "商户B"} <= names
        assert r.json()["data"]["total"] >= 2

    def test_team_user_sees_only_own_team(self, client, two_teams):
        _seed_merchant(client._sesh, team_id=two_teams["ta"].id, name="商户A")
        _seed_merchant(client._sesh, team_id=two_teams["tb"].id, name="商户B")
        r = client.get(OPS_URL, headers=_auth(two_teams["token_a"]))
        assert r.status_code == 200
        names = {i["merchant_name"] for i in r.json()["data"]["items"]}
        assert "商户A" in names
        assert "商户B" not in names  # 跨 team 隔离

    def test_list_filter_by_applyment_state(self, client, two_teams):
        """applyment_state 查询参数过滤。"""
        _seed_merchant(
            client._sesh, team_id=two_teams["ta"].id, name="进行中",
            state=ApplymentState.AUDITING,
        )
        _seed_merchant(
            client._sesh, team_id=two_teams["ta"].id, name="已完成",
            state=ApplymentState.FINISH, status=MerchantStatus.ACTIVE, sub_mchid="2490000001",
        )
        r = client.get(OPS_URL, headers=_auth(two_teams["token_a"]),
                       params={"applyment_state": "FINISH"})
        assert r.status_code == 200
        names = {i["merchant_name"] for i in r.json()["data"]["items"]}
        assert names == {"已完成"}

    def test_list_item_contract_structure(self, client):
        """列表项结构对齐契约 §3.3 (settlement 嵌套 + station_ids)。"""
        _seed_merchant(
            client._sesh, name="结构验证",
            state=ApplymentState.FINISH, status=MerchantStatus.ACTIVE,
            sub_mchid="2490000001",
        )
        r = client.get(OPS_URL)
        item = r.json()["data"]["items"][0]
        for key in (
            "business_code", "merchant_name", "merchant_type", "applyment_state",
            "sub_mchid", "merchant_status", "settlement",
            "profit_sharing_enabled", "station_ids",
        ):
            assert key in item, f"列表项缺字段 {key}"
        assert set(item["settlement"]) == {"account_type", "bank_name", "account_last4"}


# ==================== A5. 权限门 ====================

class TestPermissionGate:
    """router-level require_permission('operate:manage'): viewer 不持 → 403; 匿名 → 401。

    viewer/auditor 在 ROLE_PERMISSIONS_MATRIX 不持 operate:manage; operator/engineer 持有。
    """

    @pytest.fixture
    def viewer_token(self, client):
        _add_user(client._sesh, "mch_viewer", UserRole.VIEWER)
        return _login_token(client, "mch_viewer")

    def test_viewer_submit_forbidden(self, client, viewer_token):
        r = client.post(f"{OPS_URL}/applyment", json=VALID_BODY, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_list_forbidden(self, client, viewer_token):
        r = client.get(OPS_URL, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_get_forbidden(self, client, viewer_token):
        r = client.get(f"{OPS_URL}/applyment/APL_ANY", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_advance_forbidden(self, client, viewer_token):
        r = client.post(
            f"{OPS_URL}/applyment/APL_ANY/advance",
            json={"event": "finish"},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    def test_anonymous_no_token_401(self, client):
        """无 Authorization 头 → 401 (router-level require_permission 先于 body 解析)。"""
        client.headers.pop("Authorization", None)
        r = client.post(f"{OPS_URL}/applyment", json=VALID_BODY)
        assert r.status_code == 401


# ==================== A6. advance 状态机 ====================

class TestAdvanceStateMachine:
    """POST /ops/merchants/applyment/{business_code}/advance (契约 §3.2 七态)。"""

    def test_advance_finish_generates_sub_mchid_and_active(self, client):
        """SIGNING + finish → FINISH + mock_ 前缀 sub_mchid + merchant_status=ACTIVE。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.SIGNING, name="待完成")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance", json={"event": "finish"}
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["applyment_state"] == "FINISH"
        assert d["sub_mchid"].startswith("mock_")  # mock 前缀 (卡 d53a2f2f)
        assert d["merchant_status"] == "ACTIVE"

    def test_advance_audit_pass_generates_validation_url(self, client):
        """AUDITING + audit_pass → TO_BE_SIGNED + 法人验证链接。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.AUDITING, name="审核中")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance", json={"event": "audit_pass"}
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["applyment_state"] == "TO_BE_SIGNED"
        assert d["legal_validation_url"] is not None

    def test_advance_audit_reject_records_reason(self, client):
        """AUDITING + audit_reject → REJECTED + reject_reason。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.AUDITING, name="将被驳回")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance",
            json={"event": "audit_reject", "reject_reason": "材料不全"},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["applyment_state"] == "REJECTED"
        assert d["reject_reason"] == "材料不全"

    def test_advance_illegal_transition_400(self, client):
        """AUDITING + finish (非法, 需先经 TO_BE_SIGNED→SIGNING) → 400, 状态不变。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.AUDITING, name="非法迁移")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance", json={"event": "finish"}
        )
        assert r.status_code == 400
        client._sesh.expire_all()
        fresh = client._sesh.query(Merchant).filter(Merchant.id == m.id).first()
        assert fresh.applyment_state == ApplymentState.AUDITING  # 状态未变

    def test_advance_unknown_code_404(self, client):
        r = client.post(
            f"{OPS_URL}/applyment/APL_GHOST_9999/advance", json={"event": "finish"}
        )
        assert r.status_code == 404

    def test_advance_cross_team_404(self, client, two_teams):
        m = _seed_merchant(client._sesh, team_id=two_teams["ta"].id,
                           state=ApplymentState.SIGNING, name="A队待完成")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance",
            json={"event": "finish"},
            headers=_auth(two_teams["token_b"]),
        )
        assert r.status_code == 404


# ==================== B. wx_pay 外部调用异常保护 ====================

class TestWxPayErrorProtection:
    """advance FINISH 调 client.generate_sub_mchid —— 真实接入时为IM-B外部 HTTP 调用。

    网络故障 (httpx.RequestError/TimeoutException 等) 不得冒泡为裸 500: service 层
    捕获转 WxPayError, router 映射 502; 且 DB 状态不半成品 (未 commit)。
    用 _FaultyWxPayClient 注入 generate_sub_mchid 抛异常模拟。
    """

    @pytest.fixture
    def faulty_client(self):
        from app.services.wx_pay.mock_client import MockWxPayClient

        class _Faulty(MockWxPayClient):
            def generate_sub_mchid(self):
                raise RuntimeError("模拟IM-B接口网络异常")

        reset_wxpay_client_for_testing(_Faulty())
        yield
        reset_wxpay_client_for_testing(None)  # 复位 → 下次 get 重建 Mock

    def test_advance_finish_client_failure_returns_502(self, client, faulty_client):
        """client 故障 → 502 (网关错误), 非裸 500 '服务器内部错误'。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.SIGNING, name="故障态")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance", json={"event": "finish"}
        )
        assert r.status_code == 502, r.text

    def test_advance_finish_failure_keeps_signing_state(self, client, faulty_client):
        """client 故障时事务未提交 → DB 状态保持 SIGNING (不半成品 FINISH)。"""
        m = _seed_merchant(client._sesh, state=ApplymentState.SIGNING, name="不半成品")
        r = client.post(
            f"{OPS_URL}/applyment/{m.business_code}/advance", json={"event": "finish"}
        )
        assert r.status_code == 502
        client._sesh.expire_all()
        fresh = client._sesh.query(Merchant).filter(Merchant.id == m.id).first()
        assert fresh.applyment_state == ApplymentState.SIGNING  # 未推进
        assert fresh.sub_mchid is None
        assert fresh.merchant_status == MerchantStatus.PENDING

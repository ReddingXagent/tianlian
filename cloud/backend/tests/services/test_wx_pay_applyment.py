"""wx_pay.applyment 单元测试覆盖补全 (卡 5be58a27)

被测: app/services/wx_pay/applyment.py (155 行) — 特约商户进件服务。
契约: backend/docs/contracts/user-client-contract.md §3 (特约商户进件 + 商户状态)。

覆盖矩阵 (5 个被测函数 + 1 异常类):
  transition            13 条合法迁移逐条 + 若干非法迁移返回 None
  generate_business_code APL_ + 8 位业务日 + 8 位大写 hex / 格式稳定 / 8 位 hex 校验
  _last4                正常 (>=4 位) / None / 空串 / 不足 4 位
  submit_applyment      嵌套 payload 解析落字段 / business_code 冲突重试 / 缺可选嵌套对象不爆
  advance               各合法 event 状态变更 / TO_BE_SIGNED 生成 url / REJECTED 记原因 (有/无)
                        / FINISH 成功 → sub_mchid + ACTIVE / FINISH 失败 → WxPayError 不 commit
                        / 非法迁移 → IllegalTransition
  IllegalTransition     异常可被 caller 捕获

DB 策略: submit_applyment/advance 走真实 in-memory sqlite Session (对 Merchant add/commit/
  refresh/query, 真实 DB 最稳, 独立 engine 避开全局 SessionLocal 坑); submit_applyment 的
  business_code 冲突重试用 MagicMock 测循环 (真实唯一约束 + secrets 随机难稳定触发, mock 最准)。
client 策略: patch applyment.get_wxpay_client 注入 MagicMock 控制 generate_sub_mchid 返回/抛异常
  (按模块名 patch, 避开单例污染)。

铁律: 只加测试, 不改 production。
"""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.merchant import (
    Merchant,
    ApplymentState,
    MerchantStatus,
    MerchantType,
)
from app.services.wx_pay import applyment as ap
from app.services.wx_pay.applyment import IllegalTransition
from app.services.wx_pay.client import WxPayError


# ═══════════════════════════════════════════════════════════════════════════
# 脚手架: in-memory sqlite Session (独立 engine, 不碰全局 SessionLocal)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def db():
    """仅建 Merchant 表的独立 in-memory Session。

    StaticPool + check_same_thread=False 让单连接贯穿整个 session, commit/refresh 行为
    与生产一致 (真实 query 链 + 主键回写 + unique 约束兜底)。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Merchant.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _payload(**overrides):
    """契约 §3.1 标准进件 payload (micro_merchant), 支持覆写字段。"""
    base = {
        "merchant_type": "micro_merchant",
        "merchant_name": "张某某",
        "contact": {"name": "张某某", "phone": "13800000001"},
        "id_card": {"name": "张某某", "number": "110101199001011234"},
        "settlement": {
            "account_type": "personal",
            "bank_name": "招商银行",
            "account_number": "6225880123456789",
        },
        "station_ids": ["st_0001"],
    }
    base.update(overrides)
    return base


def _merchant(db, **overrides):
    """构造一行已存在的 Merchant (advance 测试用), 默认 AUDITING/PENDING。"""
    defaults = dict(
        business_code="APL_20260807_EXIST",
        team_id=7,
        merchant_type=MerchantType.MICRO_MERCHANT,
        merchant_name="测试商户",
        applyment_state=ApplymentState.AUDITING,
        merchant_status=MerchantStatus.PENDING,
        profit_sharing_enabled=False,
    )
    defaults.update(overrides)
    m = Merchant(**defaults)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# transition — 七态迁移矩阵 (纯函数, 与 DB 无关)
# ═══════════════════════════════════════════════════════════════════════════
class TestTransition:
    """13 条合法迁移逐条 + 非法迁移返回 None。"""

    # --- 6 条业务流 ---
    def test_editing_submit_to_auditing(self):
        assert ap.transition(ApplymentState.APPLYMENT_EDITING, "submit") == ApplymentState.AUDITING

    def test_auditing_audit_pass_to_to_be_signed(self):
        assert ap.transition(ApplymentState.AUDITING, "audit_pass") == ApplymentState.TO_BE_SIGNED

    def test_auditing_audit_reject_to_rejected(self):
        assert ap.transition(ApplymentState.AUDITING, "audit_reject") == ApplymentState.REJECTED

    def test_rejected_resubmit_to_auditing(self):
        assert ap.transition(ApplymentState.REJECTED, "resubmit") == ApplymentState.AUDITING

    def test_to_be_signed_validate_to_signing(self):
        assert ap.transition(ApplymentState.TO_BE_SIGNED, "validate") == ApplymentState.SIGNING

    def test_signing_finish_to_finish(self):
        assert ap.transition(ApplymentState.SIGNING, "finish") == ApplymentState.FINISH

    # --- 6 条 freeze (任意非 FROZEN 态 → FROZEN) ---
    @pytest.mark.parametrize(
        "state",
        [
            ApplymentState.APPLYMENT_EDITING,
            ApplymentState.AUDITING,
            ApplymentState.TO_BE_SIGNED,
            ApplymentState.SIGNING,
            ApplymentState.REJECTED,
            ApplymentState.FINISH,
        ],
    )
    def test_any_state_freeze_to_frozen(self, state):
        assert ap.transition(state, "freeze") == ApplymentState.FROZEN

    # --- 1 条 unfreeze ---
    def test_frozen_unfreeze_to_auditing(self):
        assert ap.transition(ApplymentState.FROZEN, "unfreeze") == ApplymentState.AUDITING

    @pytest.mark.parametrize(
        "current,event",
        [
            # 不存在的 event
            (ApplymentState.AUDITING, "submit"),
            (ApplymentState.AUDITING, "finish"),
            (ApplymentState.SIGNING, "validate"),
            # FINISH 是终态, 无后续迁移
            (ApplymentState.FINISH, "finish"),
            (ApplymentState.FINISH, "validate"),
            # FROZEN 仅能 unfreeze, 不能直接 finish/resubmit
            (ApplymentState.FROZEN, "finish"),
            (ApplymentState.FROZEN, "resubmit"),
            (ApplymentState.FROZEN, "freeze"),
            # APPLYMENT_EDITING 仅 submit/freeze
            (ApplymentState.APPLYMENT_EDITING, "audit_pass"),
            # 未知 event
            (ApplymentState.AUDITING, "nonsense"),
            ("NOT_A_STATE", "submit"),
        ],
    )
    def test_illegal_transition_returns_none(self, current, event):
        assert ap.transition(current, event) is None


# ═══════════════════════════════════════════════════════════════════════════
# generate_business_code — APL_yyyymmdd_XXXXXXXX
# ═══════════════════════════════════════════════════════════════════════════
class TestGenerateBusinessCode:
    def test_format_prefix_and_segments(self):
        code = ap.generate_business_code()
        # APL_ + 8 位日期 + _ + 8 位大写 hex
        assert code.startswith("APL_")
        parts = code.split("_")
        assert len(parts) == 3
        assert parts[0] == "APL"
        assert len(parts[1]) == 8 and parts[1].isdigit()
        # 8 位 hex (token_hex(4) → 8 字符), 全大写
        assert len(parts[2]) == 8
        assert parts[2] == parts[2].upper()
        int(parts[2], 16)  # 确为合法 hex

    def test_uniqueness_random_suffix(self):
        codes = {ap.generate_business_code() for _ in range(200)}
        # 随机后缀, 大概率全不同 (200 个 8 位 hex 碰撞概率可忽略)
        assert len(codes) >= 199

    @patch("app.services.wx_pay.applyment.datetime")
    def test_uses_utc_business_date(self, mock_dt):
        """business_code 日期段取 UTC 当日 (datetime.now(timezone.utc))。"""
        from datetime import datetime, timezone

        fixed = datetime(2026, 8, 9, 3, 30, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed
        code = ap.generate_business_code()
        assert code == f"APL_20260809_{code.split('_')[2]}"


# ═══════════════════════════════════════════════════════════════════════════
# _last4 — 取末 4 位边界
# ═══════════════════════════════════════════════════════════════════════════
class TestLast4:
    def test_normal_four_or_more(self):
        assert ap._last4("6225880123456789") == "6789"

    def test_exactly_four(self):
        assert ap._last4("1234") == "1234"

    def test_none(self):
        assert ap._last4(None) is None

    def test_empty_string(self):
        assert ap._last4("") is None

    def test_short_string_returns_as_is(self):
        # 不足 4 位: 返回整个串 (不补零, 不报错)
        assert ap._last4("12") == "12"

    def test_non_str_numeric(self):
        # 数字入参经 str() 转换后取末 4
        assert ap._last4(123456789) == "6789"


# ═══════════════════════════════════════════════════════════════════════════
# submit_applyment — 建行 + 嵌套 payload 解析 + 冲突重试
# ═══════════════════════════════════════════════════════════════════════════
class TestSubmitApplyment:
    def test_creates_merchant_with_nested_payload_fields(self, db):
        """契约 §3.1: contact/id_card/settlement 嵌套对象拆字段落库。"""
        m = ap.submit_applyment(db, team_id=7, payload=_payload())

        assert m.id is not None
        assert m.team_id == 7
        assert m.business_code.startswith("APL_")
        assert m.merchant_type == MerchantType.MICRO_MERCHANT
        assert m.merchant_name == "张某某"
        # contact 拆字段
        assert m.contact_name == "张某某"
        assert m.contact_phone == "13800000001"
        # id_card 拆字段
        assert m.id_card_name == "张某某"
        assert m.id_card_number == "110101199001011234"
        # settlement 拆字段 + last4 派生
        assert m.settlement_account_type == "personal"
        assert m.settlement_bank_name == "招商银行"
        assert m.settlement_account_number == "6225880123456789"
        assert m.settlement_account_last4 == "6789"
        # 状态机初始态
        assert m.applyment_state == ApplymentState.AUDITING
        assert m.merchant_status == MerchantStatus.PENDING
        assert m.profit_sharing_enabled is False
        assert m.station_ids == ["st_0001"]
        # 真实落库 (query 可查回)
        assert db.query(Merchant).filter(Merchant.id == m.id).one() is not None

    def test_business_code_retry_on_collision(self):
        """business_code 极小概率冲突, while 循环重试到不冲突为止。"""
        db = MagicMock()
        # query 链: 前两次命中 (冲突), 第三次 None (放行)
        db.query.return_value.filter.return_value.first.side_effect = [
            MagicMock(),  # 第 1 次: 冲突
            MagicMock(),  # 第 2 次: 冲突
            None,         # 第 3 次: 放行
        ]

        with patch.object(ap, "generate_business_code", side_effect=["APL_D1", "APL_D2", "APL_D3"]) as gen:
            m = ap.submit_applyment(db, team_id=1, payload=_payload())

        assert gen.call_count == 3
        # 最终用第 3 个不冲突的 code
        assert m.business_code == "APL_D3"
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
        # 断言查询确实循环了 3 次
        assert db.query.return_value.filter.return_value.first.call_count == 3

    def test_business_code_first_try_no_collision(self):
        """无冲突时只生成一次, while 不进入循环体。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(ap, "generate_business_code", return_value="APL_OK") as gen:
            m = ap.submit_applyment(db, team_id=None, payload=_payload())

        assert gen.call_count == 1
        assert m.business_code == "APL_OK"
        assert m.team_id is None

    def test_missing_optional_nested_objects_does_not_crash(self, db):
        """contact/id_card/settlement 任一缺失 → 对应字段落 None, 不抛 KeyError。"""
        m = ap.submit_applyment(
            db,
            team_id=7,
            payload={"merchant_type": "enterprise", "merchant_name": "无资料商户"},
        )
        assert m.merchant_name == "无资料商户"
        assert m.merchant_type == MerchantType.ENTERPRISE
        assert m.contact_name is None
        assert m.contact_phone is None
        assert m.id_card_name is None
        assert m.id_card_number is None
        assert m.settlement_account_type is None
        assert m.settlement_bank_name is None
        assert m.settlement_account_number is None
        assert m.settlement_account_last4 is None
        assert m.station_ids is None

    def test_settlement_last4_derived_from_account_number(self, db):
        """settlement_account_last4 由 account_number 派生 (契约 §3.3 列表展示用)。"""
        payload = _payload(settlement={"account_type": "corporate", "bank_name": "工行",
                                       "account_number": "987654321"})
        m = ap.submit_applyment(db, team_id=7, payload=payload)
        assert m.settlement_account_last4 == "4321"


# ═══════════════════════════════════════════════════════════════════════════
# advance — 状态机推进 + 副作用
# ═══════════════════════════════════════════════════════════════════════════
class TestAdvance:
    def test_audit_pass_to_to_be_signed_generates_legal_url(self, db):
        m = _merchant(db, applyment_state=ApplymentState.AUDITING)
        ap.advance(db, m, "audit_pass")

        assert m.applyment_state == ApplymentState.TO_BE_SIGNED
        assert m.legal_validation_url == f"https://pay.tianlian.example/validate/{m.business_code}"

    def test_audit_reject_to_rejected_with_reason(self, db):
        m = _merchant(db, applyment_state=ApplymentState.AUDITING)
        ap.advance(db, m, "audit_reject", reject_reason="证件照模糊")

        assert m.applyment_state == ApplymentState.REJECTED
        assert m.reject_reason == "证件照模糊"

    def test_audit_reject_to_rejected_without_reason_uses_default(self, db):
        m = _merchant(db, applyment_state=ApplymentState.AUDITING)
        ap.advance(db, m, "audit_reject")  # 不传 reject_reason

        assert m.applyment_state == ApplymentState.REJECTED
        assert m.reject_reason == "审核未通过"

    def test_resubmit_rejected_back_to_auditing(self, db):
        m = _merchant(db, applyment_state=ApplymentState.REJECTED, reject_reason="旧原因")
        ap.advance(db, m, "resubmit")
        assert m.applyment_state == ApplymentState.AUDITING

    def test_validate_to_be_signed_to_signing(self, db):
        m = _merchant(db, applyment_state=ApplymentState.TO_BE_SIGNED,
                      legal_validation_url="https://old")
        ap.advance(db, m, "validate")
        assert m.applyment_state == ApplymentState.SIGNING

    @patch("app.services.wx_pay.applyment.get_wxpay_client")
    def test_finish_success_generates_sub_mchid_and_active(self, mock_get_client, db):
        """FINISH: client.generate_sub_mchid 返回 → sub_mchid 落库 + merchant_status=ACTIVE。"""
        client = MagicMock()
        client.generate_sub_mchid.return_value = "2490000001"
        mock_get_client.return_value = client

        m = _merchant(db, applyment_state=ApplymentState.SIGNING)
        ap.advance(db, m, "finish")

        assert m.applyment_state == ApplymentState.FINISH
        assert m.sub_mchid == "2490000001"
        assert m.merchant_status == MerchantStatus.ACTIVE
        client.generate_sub_mchid.assert_called_once_with()

    @patch("app.services.wx_pay.applyment.get_wxpay_client")
    def test_finish_failure_raises_wxpay_error_no_commit(self, mock_get_client, db):
        """FINISH 时 generate_sub_mchid 抛异常 → 转 WxPayError, db.commit 不执行。

        契约: "失败时下方 db.commit() 不执行" — 指事务不提交 (DB 不半成品落 sub_mchid=空 +
        ACTIVE)。注意 applyment.py:130 先改内存对象 applyment_state=FINISH 再调 client,
        故异常时内存对象状态已推进; 但因未 commit, 从 DB 重读仍是 SIGNING (事务未落)。
        """
        client = MagicMock()
        client.generate_sub_mchid.side_effect = RuntimeError("IM-B接口超时")
        mock_get_client.return_value = client

        m = _merchant(db, applyment_state=ApplymentState.SIGNING)
        merchant_id = m.id
        with patch.object(db, "commit") as mock_commit:
            with pytest.raises(WxPayError, match="生成特约商户号失败"):
                ap.advance(db, m, "finish")
            mock_commit.assert_not_called()

        # 异常未提交: sub_mchid 未生成; DB 重读仍为 SIGNING (commit 未执行, 推进未落库)
        assert m.sub_mchid is None
        db.refresh(m)
        assert m.applyment_state == ApplymentState.SIGNING
        assert m.merchant_status == MerchantStatus.PENDING
        # 隔离: 同一 DB 重查, 确无半成品行
        assert db.query(Merchant).filter(Merchant.id == merchant_id).one().sub_mchid is None

    @patch("app.services.wx_pay.applyment.get_wxpay_client")
    def test_finish_failure_preserves_cause_chain(self, mock_get_client, db):
        """WxPayError 保留原始异常链 (from exc), caller 可追溯底层网络故障。"""
        client = MagicMock()
        original = ConnectionError("connection reset")
        client.generate_sub_mchid.side_effect = original
        mock_get_client.return_value = client

        m = _merchant(db, applyment_state=ApplymentState.SIGNING)
        with pytest.raises(WxPayError) as exc_info:
            ap.advance(db, m, "finish")
        assert exc_info.value.__cause__ is original

    @pytest.mark.parametrize(
        "from_state",
        [
            ApplymentState.APPLYMENT_EDITING,
            ApplymentState.AUDITING,
            ApplymentState.TO_BE_SIGNED,
            ApplymentState.SIGNING,
            ApplymentState.REJECTED,
            ApplymentState.FINISH,
        ],
    )
    def test_freeze_any_state_to_frozen(self, db, from_state):
        m = _merchant(db, applyment_state=from_state)
        ap.advance(db, m, "freeze")
        assert m.applyment_state == ApplymentState.FROZEN

    def test_unfreeze_frozen_to_auditing(self, db):
        m = _merchant(db, applyment_state=ApplymentState.FROZEN)
        ap.advance(db, m, "unfreeze")
        assert m.applyment_state == ApplymentState.AUDITING

    def test_illegal_transition_raises(self, db):
        """非法迁移 → IllegalTransition (caller 映射 400), 状态不变。"""
        m = _merchant(db, applyment_state=ApplymentState.AUDITING)
        original_state = m.applyment_state
        with pytest.raises(IllegalTransition, match="非法迁移"):
            ap.advance(db, m, "finish")  # AUDITING 不能直接 finish
        assert m.applyment_state == original_state

    def test_illegal_transition_unknown_event(self, db):
        m = _merchant(db, applyment_state=ApplymentState.SIGNING)
        with pytest.raises(IllegalTransition):
            ap.advance(db, m, "submit")

    @patch("app.services.wx_pay.applyment.get_wxpay_client")
    def test_finish_does_not_touch_reject_reason_or_url(self, mock_get_client, db):
        """FINISH 仅设 sub_mchid + ACTIVE, 不动 legal_validation_url / reject_reason。"""
        client = MagicMock()
        client.generate_sub_mchid.return_value = "2490000002"
        mock_get_client.return_value = client

        m = _merchant(
            db,
            applyment_state=ApplymentState.SIGNING,
            legal_validation_url="https://pay.tianlian.example/validate/APL_20260807_EXIST",
            reject_reason=None,
        )
        ap.advance(db, m, "finish")
        assert m.legal_validation_url == "https://pay.tianlian.example/validate/APL_20260807_EXIST"
        assert m.reject_reason is None

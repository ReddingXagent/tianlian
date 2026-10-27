"""
退款链路财务边界安全测试 (工作卡 aa88371f / 卡 75134a82)

覆盖 5 个缺陷的修复契约 (aa88371f):
1. 部分退款 complete → PARTIAL (累计退款 < 实付); 累计 ≥ 实付 → REFUNDED
2. reject 恢复退款前 payment_status 快照 (PARTIAL 原状恢复, 不硬编码升级 PAID)
3. reviewer_id 取 token(user.id), body.reviewer_id 废弃
4. 并发审批: 乐观锁条件 UPDATE, 重复审批/拒绝/完成 → 409
5. complete 调用 wx_pay 退款 + 记录渠道退款号 channel_refund_no

累计退款额度 (卡 75134a82): 剩余可退 = paid − Σ(PENDING+APPROVED+REFUNDED),
create/approve/complete 三层校验, 防跨笔累计超退渠道金额。
"""
import pytest
from decimal import Decimal

from fastapi import HTTPException

from app.api.v1.order_fees import (
    create_refund, approve_refund, reject_refund, complete_refund,
    RefundRequest, RefundReview,
)
from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.user import User, UserRole
from app.services.wx_pay import (
    reset_wxpay_client_for_testing, MockWxPayClient,
)

# 直接函数调用绕过路由: user=_ADMIN 固定 id=1, 可确定 reviewer_id 落库值。
_ADMIN = User(id=1, username="admin", role=UserRole.ADMIN, status="active")


def _paid_order(session, order_no, paid=Decimal("100"), status=OrderPaymentStatus.PAID):
    """种子一笔已完成订单, 指定实付额与支付状态。"""
    order = ChargingOrder(
        order_no=order_no,
        station_id=1, device_id=1, user_id=1,
        charged_kwh=Decimal("50"),
        total_amount=paid, paid_amount=paid,
        payment_status=status,
        order_status=OrderStatus.COMPLETED,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def _only_refund_id(session, order_id, status=None):
    """取订单下(指定状态)的退款记录 id。"""
    q = session.query(RefundRecord).filter(RefundRecord.order_id == order_id)
    if status is not None:
        q = q.filter(RefundRecord.status == status)
    return q.first().id


# ═══════════════════════════════════════════════════════
# 缺陷 1: 部分退款状态流转
# ═══════════════════════════════════════════════════════

class TestPartialRefundStatus:
    """complete 按 累计退款 vs 实付 判定 PARTIAL / REFUNDED。"""

    def test_partial_refund_yields_partial(self, test_db):
        """部分退款 complete → PARTIAL (不 REFUNDED)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-PART-001", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=40, reason="部分退款"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(reviewer_id=999), db=session, user=_ADMIN)
        complete_refund(order.id, rid, db=session, user=_ADMIN)

        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PARTIAL

    def test_full_refund_yields_refunded(self, test_db):
        """全额退款 complete → REFUNDED。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-FULL-001", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=100, reason="全额退款"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, rid, db=session, user=_ADMIN)

        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED

    def test_multiple_partials_accumulate_to_refunded(self, test_db):
        """两笔部分退款累计达实付 → 第二笔 complete 后 REFUNDED。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-ACC-001", paid=Decimal("100"))

        # 第一笔 40 → PARTIAL
        create_refund(order.id, RefundRequest(refund_amount=40, reason="第一笔"),
                      db=session, user=_ADMIN)
        r1 = _only_refund_id(session, order.id)
        approve_refund(order.id, r1, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r1, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PARTIAL

        # 第二笔 60 → 累计 100 → REFUNDED (PARTIAL 仍允许发起退款)
        create_refund(order.id, RefundRequest(refund_amount=60, reason="第二笔"),
                      db=session, user=_ADMIN)
        r2 = _only_refund_id(session, order.id, status=RefundStatus.PENDING)
        approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r2, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED

    def test_exact_paid_amount_is_refunded(self, test_db):
        """累计退款 == 实付 → REFUNDED (边界 ≥)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-EQ-001", paid=Decimal("99.99"))

        create_refund(order.id, RefundRequest(refund_amount=99.99, reason="恰好"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, rid, db=session, user=_ADMIN)

        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED


# ═══════════════════════════════════════════════════════
# 缺陷 2: reject 恢复退款前 payment_status 快照
# ═══════════════════════════════════════════════════════

class TestRejectRestoresSnapshot:
    """reject 恢复 create_refund 时快照的 prev_payment_status。"""

    def test_reject_from_paid_restores_paid(self, test_db):
        """PAID → REFUNDING → reject → PAID。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-RP-001", status=OrderPaymentStatus.PAID)
        create_refund(order.id, RefundRequest(refund_amount=30, reason="测试"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDING

        reject_refund(order.id, rid, RefundReview(reviewer_id=999, reject_reason="不批"),
                      db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PAID

    def test_reject_from_partial_restores_partial(self, test_db):
        """PARTIAL → REFUNDING → reject → PARTIAL (核心: 不升级为 PAID)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-RP-002", status=OrderPaymentStatus.PARTIAL)
        create_refund(order.id, RefundRequest(refund_amount=20, reason="部分后退款"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDING

        reject_refund(order.id, rid, RefundReview(reviewer_id=999, reject_reason="不批"),
                      db=session, user=_ADMIN)
        session.refresh(order)
        # 修复前: 硬编码恢复 PAID (bug); 修复后: 恢复快照 PARTIAL
        assert order.payment_status == OrderPaymentStatus.PARTIAL

    def test_snapshot_prev_payment_status_recorded(self, test_db):
        """create_refund 落库 prev_payment_status 快照。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-SNAP-001", status=OrderPaymentStatus.PARTIAL)
        create_refund(order.id, RefundRequest(refund_amount=20, reason="快照"),
                      db=session, user=_ADMIN)
        refund = session.query(RefundRecord).filter_by(order_id=order.id).first()
        assert refund.prev_payment_status == OrderPaymentStatus.PARTIAL.value


# ═══════════════════════════════════════════════════════
# 缺陷 3: reviewer_id 取 token(user.id) 非 body
# ═══════════════════════════════════════════════════════

class TestReviewerFromToken:
    """reviewer_id 落库取自 user.id, body.reviewer_id 被忽略。"""

    def test_approve_reviewer_id_from_token(self, test_db):
        """body.reviewer_id=999, 落库 reviewer_id == user.id。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-REV-001")
        create_refund(order.id, RefundRequest(refund_amount=30, reason="审批人"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)

        resp = approve_refund(order.id, rid, RefundReview(reviewer_id=999),
                              db=session, user=_ADMIN)
        assert resp["data"]["reviewer_id"] == _ADMIN.id
        assert resp["data"]["reviewer_id"] != 999

    def test_reject_reviewer_id_from_token(self, test_db):
        session = test_db["session"]
        order = _paid_order(session, "RS-REV-002")
        create_refund(order.id, RefundRequest(refund_amount=30, reason="拒绝人"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        resp = reject_refund(order.id, rid, RefundReview(reviewer_id=888, reject_reason="x"),
                             db=session, user=_ADMIN)
        assert resp["data"]["reviewer_id"] == _ADMIN.id


# ═══════════════════════════════════════════════════════
# 缺陷 4: 并发审批 (乐观锁条件 UPDATE)
# ═══════════════════════════════════════════════════════

class TestConcurrentApproval:
    """状态机推进走 WHERE status=<期望> 的条件 UPDATE, 败者 409。"""

    def test_double_approve_second_conflict(self, test_db):
        """顺序二次审批 → 第二次 409 (PENDING 已被改)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CONC-001")
        create_refund(order.id, RefundRequest(refund_amount=30, reason="并发"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)

        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        with pytest.raises(HTTPException) as exc:
            approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        assert exc.value.status_code == 409

    def test_double_reject_second_conflict(self, test_db):
        session = test_db["session"]
        order = _paid_order(session, "RS-CONC-002")
        create_refund(order.id, RefundRequest(refund_amount=30, reason="并发拒"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        reject_refund(order.id, rid, RefundReview(reviewer_id=1, reject_reason="x"),
                      db=session, user=_ADMIN)
        with pytest.raises(HTTPException) as exc:
            reject_refund(order.id, rid, RefundReview(reviewer_id=1, reject_reason="y"),
                          db=session, user=_ADMIN)
        assert exc.value.status_code == 409

    def test_double_complete_second_conflict(self, test_db):
        """二次 complete → 第二次失败 (REFUNDED 不可再 complete)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CONC-003")
        create_refund(order.id, RefundRequest(refund_amount=100, reason="并发完成"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, rid, db=session, user=_ADMIN)
        with pytest.raises(HTTPException) as exc:
            complete_refund(order.id, rid, db=session, user=_ADMIN)
        assert exc.value.status_code in (400, 409)

    def test_approve_not_found_returns_404(self, test_db):
        """不存在的 refund → 404 (不与 409 混淆)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CONC-004")
        with pytest.raises(HTTPException) as exc:
            approve_refund(order.id, 999999, RefundReview(), db=session, user=_ADMIN)
        assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════
# 缺陷 5: complete 调用 wx_pay 退款 + 记录渠道退款号
# ═══════════════════════════════════════════════════════

class TestChannelRefund:
    """complete 经 wx_pay/refund 发起渠道退款, 落库 channel_refund_no。"""

    def test_complete_records_channel_refund_no(self, test_db):
        """complete 后 channel_refund_no 非空。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CH-001")
        create_refund(order.id, RefundRequest(refund_amount=100, reason="渠道"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, rid, db=session, user=_ADMIN)

        refund = session.query(RefundRecord).filter_by(id=rid).first()
        assert refund.channel_refund_no
        assert isinstance(refund.channel_refund_no, str)

    def test_complete_invokes_wx_refund_client(self, test_db):
        """complete 调用 wx_pay client.refund, 金额按分换算。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CH-002")
        create_refund(order.id, RefundRequest(refund_amount=12.34, reason="spy"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)

        calls = []

        class _Spy(MockWxPayClient):
            def refund(self, **kwargs):
                calls.append(kwargs)
                return super().refund(**kwargs)

        spy = _Spy()
        reset_wxpay_client_for_testing(spy)
        try:
            complete_refund(order.id, rid, db=session, user=_ADMIN)
        finally:
            reset_wxpay_client_for_testing(None)

        assert len(calls) == 1
        # 12.34 元 → 1234 分
        assert calls[0]["refund_amount_fen"] == 1234
        refund = session.query(RefundRecord).filter_by(id=rid).first()
        assert refund.channel_refund_no

    def test_complete_channel_failure_returns_502_and_keeps_approved(self, test_db):
        """卡 692b3df7: 渠道退款异常 → complete 抛 502, 退款状态保持 APPROVED 可重试。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CH-FAIL-001")
        create_refund(order.id, RefundRequest(refund_amount=30, reason="渠道挂"),
                      db=session, user=_ADMIN)
        rid = _only_refund_id(session, order.id)
        approve_refund(order.id, rid, RefundReview(), db=session, user=_ADMIN)

        class _Boom(MockWxPayClient):
            def refund(self, **kwargs):
                raise Exception("IM-B网络故障")

        reset_wxpay_client_for_testing(_Boom())
        try:
            with pytest.raises(HTTPException) as exc:
                complete_refund(order.id, rid, db=session, user=_ADMIN)
            assert exc.value.status_code == 502
        finally:
            reset_wxpay_client_for_testing(None)

        # 渠道失败不推进状态: 仍 APPROVED, 可重试 complete; 未落 channel_refund_no
        refund = session.query(RefundRecord).filter_by(id=rid).first()
        assert refund.status == RefundStatus.APPROVED
        assert not refund.channel_refund_no


# ═══════════════════════════════════════════════════════
# 卡 75134a82: 累计退款额度 (剩余可退)
# ═══════════════════════════════════════════════════════

class TestCumulativeRefundLimit:
    """剩余可退 = paid − Σ(PENDING+APPROVED+REFUNDED); 三层校验防累计超退。"""

    def test_second_refund_exceeding_remaining_rejected_400(self, test_db):
        """复现路径: 首笔 80 完成后, 二笔 80 超剩余可退 20 → 400 (修复前通过)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CUM-001", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=80, reason="第一笔"),
                      db=session, user=_ADMIN)
        r1 = _only_refund_id(session, order.id)
        approve_refund(order.id, r1, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r1, db=session, user=_ADMIN)

        with pytest.raises(HTTPException) as exc:
            create_refund(order.id, RefundRequest(refund_amount=80, reason="第二笔超退"),
                          db=session, user=_ADMIN)
        assert exc.value.status_code == 400
        # 文案须区分于单笔超额 ("超过实付金额"): 报剩余可退
        assert "剩余可退" in exc.value.detail
        assert "实付" not in exc.value.detail

    def test_second_refund_within_remaining_succeeds(self, test_db):
        """首笔 80 完成后, 二笔 20 合法 → 成功; 累计 100 → REFUNDED。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CUM-002", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=80, reason="第一笔"),
                      db=session, user=_ADMIN)
        r1 = _only_refund_id(session, order.id)
        approve_refund(order.id, r1, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r1, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PARTIAL

        create_refund(order.id, RefundRequest(refund_amount=20, reason="第二笔"),
                      db=session, user=_ADMIN)
        r2 = _only_refund_id(session, order.id, status=RefundStatus.PENDING)
        approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r2, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED

    def test_remaining_boundary_exact(self, test_db):
        """边界: 二笔恰等于剩余可退 → 通过 (不误拦合法边界)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CUM-005", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=79.99, reason="第一笔"),
                      db=session, user=_ADMIN)
        r1 = _only_refund_id(session, order.id)
        approve_refund(order.id, r1, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r1, db=session, user=_ADMIN)

        # 剩余可退恰 20.01, 二笔 20.01 → 通过
        create_refund(order.id, RefundRequest(refund_amount=20.01, reason="边界二笔"),
                      db=session, user=_ADMIN)
        r2 = _only_refund_id(session, order.id, status=RefundStatus.PENDING)
        approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r2, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED

    def test_pending_and_approved_occupy_remaining(self, test_db):
        """在途占用: PENDING/APPROVED 均计入占用口径 (订单 PARTIAL 放行 create, 由额度拦截)。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CUM-003", paid=Decimal("100"))

        # 构造现场: 首笔 80 已 REFUNDED (订单 PARTIAL), 另有一笔在途 PENDING 15
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("80"),
            reason="已退", status=RefundStatus.REFUNDED,
        ))
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("15"),
            reason="在途", status=RefundStatus.PENDING,
        ))
        session.commit()
        order.payment_status = OrderPaymentStatus.PARTIAL
        session.commit()

        # 剩余可退 = 100 - 80 - 15 = 5; 申请 10 → 400
        with pytest.raises(HTTPException) as exc:
            create_refund(order.id, RefundRequest(refund_amount=10, reason="超在途占用"),
                          db=session, user=_ADMIN)
        assert exc.value.status_code == 400
        assert "剩余可退" in exc.value.detail

    def test_rejected_releases_remaining(self, test_db):
        """REJECTED 不占用: 拒绝后额度释放, 新申请可用原额度。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CUM-004", paid=Decimal("100"))

        create_refund(order.id, RefundRequest(refund_amount=80, reason="将被拒"),
                      db=session, user=_ADMIN)
        r1 = _only_refund_id(session, order.id)
        reject_refund(order.id, r1, RefundReview(reject_reason="不批"), db=session, user=_ADMIN)

        # 拒绝后 80 已释放, 剩余可退恢复 100
        create_refund(order.id, RefundRequest(refund_amount=100, reason="全额重申"),
                      db=session, user=_ADMIN)
        r2 = _only_refund_id(session, order.id, status=RefundStatus.PENDING)
        approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        complete_refund(order.id, r2, db=session, user=_ADMIN)
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED


class TestApproveCumulativeLimit:
    """审批时复核剩余可退 (PENDING→APPROVED 间隙额度可能被其它退款消耗)。"""

    def test_approve_exceeding_remaining_400(self, test_db):
        """间隙消耗: 一笔已 REFUNDED 80 后, 竞态遗留的 PENDING 80 审批 → 400 保持 PENDING。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-APR-001", paid=Decimal("100"))

        # 现场构造: 首笔 80 已 REFUNDED (订单 PARTIAL); 另一笔 PENDING 80 是
        # check-then-act 竞态/历史数据遗留 (create 校验上线前双双通过)。
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("80"),
            reason="已退", status=RefundStatus.REFUNDED,
        ))
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("80"),
            reason="竞态遗留", status=RefundStatus.PENDING,
            prev_payment_status="paid",
        ))
        session.commit()
        order.payment_status = OrderPaymentStatus.REFUNDING
        session.commit()
        r2 = session.query(RefundRecord).filter(
            RefundRecord.order_id == order.id,
            RefundRecord.reason == "竞态遗留",
        ).first().id

        # 审批复核: 80 > 剩余可退 20 → 400, 保持 PENDING 可人工处理
        with pytest.raises(HTTPException) as exc:
            approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        assert exc.value.status_code == 400
        assert "剩余可退" in exc.value.detail

        refund = session.query(RefundRecord).filter_by(id=r2).first()
        assert refund.status == RefundStatus.PENDING

    def test_approve_symmetric_total_check_400(self, test_db):
        """审批口径对称: 无先完成记录时, 合计 160 > paid 100 → 先审的一笔也 400。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-APR-002", paid=Decimal("100"))

        for reason in ("对称甲", "对称乙"):
            session.add(RefundRecord(
                order_id=order.id, user_id=1, refund_amount=Decimal("80"),
                reason=reason, status=RefundStatus.PENDING,
                prev_payment_status="paid",
            ))
        session.commit()
        order.payment_status = OrderPaymentStatus.REFUNDING
        session.commit()

        def _rid(reason):
            return session.query(RefundRecord).filter(
                RefundRecord.order_id == order.id,
                RefundRecord.reason == reason,
            ).first().id

        r1, r2 = _rid("对称甲"), _rid("对称乙")

        # 审甲: 甲自身 PENDING 80 + 乙 PENDING 80, 合计 160 > 100 → 400
        with pytest.raises(HTTPException) as exc:
            approve_refund(order.id, r1, RefundReview(), db=session, user=_ADMIN)
        assert exc.value.status_code == 400

        # 甲转 REJECTED 释放额度后, 乙单独审批: 合计 80 ≤ 100 → 通过
        reject_refund(order.id, r1, RefundReview(reject_reason="先拒甲"),
                      db=session, user=_ADMIN)
        resp = approve_refund(order.id, r2, RefundReview(), db=session, user=_ADMIN)
        assert resp["data"]["status"] == "approved"


class TestCompleteCumulativeLimit:
    """complete 打款前最后防线: 渠道金额复核, 不足 → 400 保持 APPROVED。"""

    def test_complete_exceeding_remaining_400_keeps_approved(self, test_db):
        """打款前复核: 另一笔已 REFUNDED 80 后, 本笔 APPROVED 80 完成 → 400 保持 APPROVED。"""
        session = test_db["session"]
        order = _paid_order(session, "RS-CMP-001", paid=Decimal("100"))

        # 现场构造: 首笔 80 已 REFUNDED; 本笔 APPROVED 80 是审批后、打款前的
        # 竞态/历史遗留 (审批时额度充足, 打款前被其它退款消耗)。
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("80"),
            reason="已退", status=RefundStatus.REFUNDED,
        ))
        session.add(RefundRecord(
            order_id=order.id, user_id=1, refund_amount=Decimal("80"),
            reason="打款前在途", status=RefundStatus.APPROVED,
            prev_payment_status="paid",
        ))
        session.commit()
        order.payment_status = OrderPaymentStatus.REFUNDING
        session.commit()
        r2 = session.query(RefundRecord).filter(
            RefundRecord.order_id == order.id,
            RefundRecord.reason == "打款前在途",
        ).first().id

        # 打款前复核: 80 > 剩余可退 20 → 400, 不调渠道不推进状态, 可人工处理
        with pytest.raises(HTTPException) as exc:
            complete_refund(order.id, r2, db=session, user=_ADMIN)
        assert exc.value.status_code == 400
        assert "剩余可退" in exc.value.detail

        refund = session.query(RefundRecord).filter_by(id=r2).first()
        assert refund.status == RefundStatus.APPROVED
        assert not refund.channel_refund_no  # 未调渠道

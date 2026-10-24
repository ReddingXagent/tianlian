"""enterprise_balance_service 单元测试 — 预储值消耗闭环

纯逻辑测试, DB/order/enterprise 用 MagicMock 隔离。覆盖:
- check_balance_available: 透支边界 (>=), None 余额/额度兜底
- InsufficientBalanceError: 属性与消息
- deduct_on_order_complete: 零额跳过 / 正常扣减+流水 / 透支拒绝 / None 兜底
- get_low_balance_enterprises: 固定阈值 vs 默认额度线 / 排序 / float 转换 / 空结果
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.charging_order import OrderPaymentStatus
from app.models.enterprise_transaction import TransactionType
from app.services.enterprise_balance_service import (
    EnterpriseDeletedError,
    InsufficientBalanceError,
    check_balance_available,
    deduct_on_order_complete,
    get_low_balance_enterprises,
)


def _enterprise(balance=None, credit_limit=None, eid=1, name="车队A", code="E001"):
    ent = MagicMock()
    ent.id = eid
    ent.name = name
    ent.code = code
    ent.balance = balance
    ent.credit_limit = credit_limit
    return ent


def _order(paid_amount=None, order_no="ORD-1", vehicle_id=99):
    order = MagicMock()
    order.paid_amount = paid_amount
    order.order_no = order_no
    order.vehicle_id = vehicle_id
    order.payment_status = OrderPaymentStatus.UNPAID
    return order


def _db(locked_ent, locked_order=None):
    """MagicMock db: 配置 query 链让 with_for_update().first() 返回 locked_ent。

    deduct 加固后对企业行做 SELECT...FOR UPDATE 重读 (TOCTOU 修复),
    纯逻辑单元测试需 mock 该锁查询返回传入 enterprise。
    订单行锁链为 with_for_update().populate_existing().first() (卡 3b56a825 T-3 弹),
    不配置时 locked_order 为裸 MagicMock, order 被替换成 MagicMock → paid_amount
    比较抛 TypeError; 默认返回 None 即保留调用方传入的内存 order 快照。
    """
    db = MagicMock()
    locked = db.query.return_value.filter.return_value.with_for_update.return_value
    locked.first.return_value = locked_ent
    locked.populate_existing.return_value.first.return_value = locked_order
    return db


# ═══════════════════════════════════════════
# check_balance_available
# ═══════════════════════════════════════════

class TestCheckBalance:
    def test_sufficient_balance(self):
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        assert check_balance_available(ent, Decimal("30.00")) is True

    def test_exactly_at_credit_limit_is_allowed(self):
        # balance - amount == -credit_limit → >= 成立 → 允许
        ent = _enterprise(balance=Decimal("0.00"), credit_limit=Decimal("50.00"))
        assert check_balance_available(ent, Decimal("50.00")) is True

    def test_beyond_credit_limit_rejected(self):
        ent = _enterprise(balance=Decimal("0.00"), credit_limit=Decimal("50.00"))
        assert check_balance_available(ent, Decimal("50.01")) is False

    def test_none_balance_treated_as_zero(self):
        ent = _enterprise(balance=None, credit_limit=Decimal("10.00"))
        assert check_balance_available(ent, Decimal("10.00")) is True
        assert check_balance_available(ent, Decimal("10.01")) is False

    def test_none_credit_limit_treated_as_zero(self):
        ent = _enterprise(balance=Decimal("5.00"), credit_limit=None)
        assert check_balance_available(ent, Decimal("5.00")) is True
        assert check_balance_available(ent, Decimal("5.01")) is False


# ═══════════════════════════════════════════
# InsufficientBalanceError
# ═══════════════════════════════════════════

class TestInsufficientError:
    def test_attributes_stored(self):
        err = InsufficientBalanceError(
            enterprise_id=7,
            balance=Decimal("10.00"),
            credit_limit=Decimal("5.00"),
            required=Decimal("20.00"),
        )
        assert err.enterprise_id == 7
        assert err.balance == Decimal("10.00")
        assert err.credit_limit == Decimal("5.00")
        assert err.required == Decimal("20.00")

    def test_message_contains_key_info(self):
        err = InsufficientBalanceError(1, Decimal("10"), Decimal("5"), Decimal("20"))
        msg = str(err)
        assert "1" in msg
        assert "可用" in msg


# ═══════════════════════════════════════════
# deduct_on_order_complete
# ═══════════════════════════════════════════

class TestDeduct:
    def test_zero_amount_skips_deduct_but_writes_zero_tx(self):
        order = _order(paid_amount=Decimal("0.00"))
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        db = _db(ent)  # 配置订单行锁链, locked_order=None 保留内存 order
        result = deduct_on_order_complete(db, order, ent)
        # 零额路径: 写金额为0的 CONSUME 流水 (审计痕迹), 返回该流水
        assert result is not None
        assert result.amount == Decimal("0.00")
        assert order.payment_status == OrderPaymentStatus.PAID
        db.flush.assert_called_once()
        db.add.assert_called_once()
        # 余额不变
        assert ent.balance == Decimal("100.00")

    def test_none_amount_treated_as_zero(self):
        order = _order(paid_amount=None)
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        db = _db(ent)  # 配置订单行锁链, locked_order=None 保留内存 order
        result = deduct_on_order_complete(db, order, ent)
        # None → 0, 同零额: 写 0 流水 (审计痕迹)
        assert result is not None
        assert result.amount == Decimal("0.00")
        assert order.payment_status == OrderPaymentStatus.PAID
        db.add.assert_called_once()

    def test_normal_deduct_creates_transaction(self):
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"), eid=8)
        db = _db(ent)
        order = _order(paid_amount=Decimal("30.00"), order_no="ORD-X", vehicle_id=42)
        tx = deduct_on_order_complete(db, order, ent)
        # 余额扣减并保留 2 位小数
        assert ent.balance == Decimal("70.00")
        # 订单标记已支付
        assert order.payment_status == OrderPaymentStatus.PAID
        # 写入流水
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.enterprise_id == 8
        assert added.vehicle_id == 42
        assert added.type == TransactionType.CONSUME
        assert added.amount == Decimal("30.00")
        assert added.balance_after == Decimal("70.00")
        assert added.order_id == "ORD-X"
        assert "ORD-X" in added.remark
        db.flush.assert_called_once()

    def test_deduct_quantizes_to_two_decimals(self):
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        db = _db(ent)
        order = _order(paid_amount=Decimal("33.333"))
        deduct_on_order_complete(db, order, ent)
        # (100 - 33.333).quantize(0.01) == 66.67
        assert ent.balance == Decimal("66.67")

    # ─────────────────────────────────────────────────────────────
    # 财务边界缺陷修复 (缺陷2/缺陷3)
    # ─────────────────────────────────────────────────────────────

    def test_zero_amount_writes_zero_consume_transaction(self):
        """缺陷2(零额结算无审计痕迹): amount<=0 分支必须写金额为0的 CONSUME 流水。

        buggy 行为: 零额直接标 PAID 后 return None, 不写 EnterpriseTransaction,
        导致零额订单在账户流水中无迹可循(对账缺口)。
        """
        order = _order(paid_amount=Decimal("0.00"), order_no="ORD-Z", vehicle_id=77)
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"), eid=5)
        db = _db(ent)  # 配置订单行锁链, locked_order=None 保留内存 order
        result = deduct_on_order_complete(db, order, ent)
        # 订单标记已支付
        assert order.payment_status == OrderPaymentStatus.PAID
        # 余额不变
        assert ent.balance == Decimal("100.00")
        # 必须写流水(金额为0)
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.enterprise_id == 5
        assert added.vehicle_id == 77
        assert added.type == TransactionType.CONSUME
        assert added.amount == Decimal("0.00")
        assert added.balance_after == Decimal("100.00")
        assert added.order_id == "ORD-Z"
        assert "零额" in added.remark

    def test_amount_quantized_consistent_with_balance_after(self):
        """缺陷3(流水精度不一致): amount 入库前须 quantize(0.01), 与 balance_after 口径一致。

        buggy 行为: balance_after 经 quantize(0.01), 而 amount 原样入库。
        paid_amount=33.333 时流水 amount=33.333 (3位), balance_after=66.67 (2位) → 口径不一。
        """
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        db = _db(ent)
        order = _order(paid_amount=Decimal("33.333"), order_no="ORD-Q")
        deduct_on_order_complete(db, order, ent)
        added = db.add.call_args[0][0]
        # amount 已 quantize 到 2 位, 与 balance_after 同精度
        assert added.amount == Decimal("33.33")
        assert added.balance_after == Decimal("66.67")
        # 反推守恒: balance_after + amount == 原余额(两位精度)
        assert added.balance_after + added.amount == Decimal("100.00")

    def test_insufficient_raises_and_balance_unchanged(self):
        ent = _enterprise(balance=Decimal("10.00"), credit_limit=Decimal("5.00"), eid=3)
        db = _db(ent)
        order = _order(paid_amount=Decimal("100.00"))
        with pytest.raises(InsufficientBalanceError) as exc:
            deduct_on_order_complete(db, order, ent)
        assert exc.value.enterprise_id == 3
        assert ent.balance == Decimal("10.00")  # 未扣减
        db.add.assert_not_called()
        # 异常前订单未被标记 PAID
        assert order.payment_status == OrderPaymentStatus.UNPAID

    def test_deduct_into_overdraft_within_limit(self):
        # 余额 10 + 额度 50 → 可用 60; 扣 60 落到 -50 == -credit_limit → 允许
        ent = _enterprise(balance=Decimal("10.00"), credit_limit=Decimal("50.00"))
        db = _db(ent)
        order = _order(paid_amount=Decimal("60.00"))
        tx = deduct_on_order_complete(db, order, ent)
        assert tx is not None
        assert ent.balance == Decimal("-50.00")

    def test_none_balance_deducts_from_zero(self):
        ent = _enterprise(balance=None, credit_limit=Decimal("100.00"))
        db = _db(ent)
        order = _order(paid_amount=Decimal("20.00"))
        deduct_on_order_complete(db, order, ent)
        # 0 - 20 = -20
        assert ent.balance == Decimal("-20.00")

    # ─────────────────────────────────────────────────────────────
    # 资金安全加固 (缺陷1/缺陷2)
    # ─────────────────────────────────────────────────────────────

    def test_already_paid_is_idempotent_noop(self):
        """缺陷1(重复结算双扣 P0): 订单已 PAID → 幂等跳过, 不扣减/不写流水/不动 DB。

        复现: settle 端点重复调用(重试/重复 webhook/sessions.py 与 orders.py 双端点同单)。
        守卫须在函数最前面, 行锁查询之前即返回, 杜绝双扣与重复 CONSUME 流水。
        """
        db = MagicMock()
        order = _order(paid_amount=Decimal("30.00"))
        order.payment_status = OrderPaymentStatus.PAID  # 重复结算: 订单已支付
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        result = deduct_on_order_complete(db, order, ent)
        assert result is None
        assert ent.balance == Decimal("100.00")  # 余额未动
        db.add.assert_not_called()                # 不写流水
        db.flush.assert_not_called()              # 不触碰 DB(含行锁查询)
        db.query.assert_not_called()              # 守卫在行锁查询之前

    def test_deleted_enterprise_lock_none_raises(self):
        """缺陷2(删除竞态静默丢扣): 行锁查询返回 None(企业行被删) → raise, 不得静默继续。

        buggy 行为: locked=None 时继续对 stale 对象赋值 balance, 订单照标 PAID。
        """
        db = _db(None)  # with_for_update().first() -> None (企业行已不存在)
        order = _order(paid_amount=Decimal("30.00"))
        ent = _enterprise(balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        with pytest.raises(EnterpriseDeletedError):
            deduct_on_order_complete(db, order, ent)
        # 订单未被标 PAID(白嫖防护)
        assert order.payment_status == OrderPaymentStatus.UNPAID
        # 未写流水
        db.add.assert_not_called()


# ═══════════════════════════════════════════
# get_low_balance_enterprises
# ═══════════════════════════════════════════

class TestLowBalance:
    def _db_with(self, enterprises):
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = enterprises
        return db, q

    def test_fixed_threshold_filter(self):
        ent = _enterprise(balance=Decimal("30.00"), credit_limit=Decimal("0.00"))
        db, q = self._db_with([ent])
        res = get_low_balance_enterprises(db, threshold=Decimal("100.00"))
        assert len(res) == 1
        assert res[0]["id"] == 1
        assert res[0]["balance"] == 30.0
        assert res[0]["available_balance"] == 30.0

    def test_default_threshold_uses_credit_limit(self):
        ent = _enterprise(balance=Decimal("10.00"), credit_limit=Decimal("50.00"))
        db, q = self._db_with([ent])
        res = get_low_balance_enterprises(db)  # 无 threshold
        assert res[0]["credit_limit"] == 50.0
        assert res[0]["available_balance"] == 60.0  # balance + credit

    def test_result_fields_and_float_conversion(self):
        ent = _enterprise(
            balance=Decimal("12.50"), credit_limit=Decimal("7.25"),
            eid=2, name="车队B", code="E002",
        )
        db, q = self._db_with([ent])
        res = get_low_balance_enterprises(db, threshold=Decimal("100"))
        item = res[0]
        assert item["id"] == 2
        assert item["name"] == "车队B"
        assert item["code"] == "E002"
        assert item["balance"] == 12.5
        assert item["credit_limit"] == 7.25
        assert item["available_balance"] == pytest.approx(19.75)

    def test_none_balance_and_credit_default_to_zero(self):
        ent = _enterprise(balance=None, credit_limit=None)
        db, q = self._db_with([ent])
        res = get_low_balance_enterprises(db, threshold=Decimal("100"))
        assert res[0]["balance"] == 0.0
        assert res[0]["credit_limit"] == 0.0
        assert res[0]["available_balance"] == 0.0

    def test_empty_result(self):
        db, q = self._db_with([])
        assert get_low_balance_enterprises(db, threshold=Decimal("100")) == []

    def test_orders_by_balance_asc_called(self):
        ent = _enterprise(balance=Decimal("1.00"))
        db, q = self._db_with([ent])
        get_low_balance_enterprises(db, threshold=Decimal("100"))
        q.order_by.assert_called_once()

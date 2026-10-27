#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结算幂等守卫陈旧快照竞态回归测试 (卡 76fac6cc T-3 弹)。

缺陷: deduct_on_order_complete 的幂等守卫读调用方传入的内存 order 快照,
且订单无行锁 → 并发双 complete 同一订单时, 双方均在对方提交前读到非 PAID
快照, 守卫形同虚设 → 双扣企业余额 + 双 CONSUME 流水。

修复: 企业行锁获锁后, 对订单以 with_for_update().populate_existing()
重查并重新执行幂等守卫 (对齐 T-1/T-2 弹惯例: enterprises.py:231 /
fleet_drivers._lock_account)。SQLite 下 with_for_update 为 no-op, 靠
populate_existing 的强制重读保证库内最新状态参与判断。
"""
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  确保所有表注册
from app.core.database import Base
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
from app.services import enterprise_balance_service
from app.services.enterprise_balance_service import (
    EnterpriseDeletedError,
    deduct_on_order_complete,
)


@pytest.fixture
def two_sessions():
    """两个独立 engine/session 模拟并发双 complete 的两份陈旧快照。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    s1, s2 = factory(), factory()
    yield s1, s2
    s1.close()
    s2.close()
    engine.dispose()


def _seed(s, paid_amount="30.00", balance="100.00"):
    ent = Enterprise(
        name="陈旧快照测试企业", code="STALE-GUARD-ENT",
        status=EnterpriseStatus.ACTIVE,
        balance=Decimal(balance), credit_limit=Decimal("0.00"),
    )
    s.add(ent)
    s.flush()
    order = ChargingOrder(
        order_no="SO-STALE-0001",
        station_id=1,
        device_id=1,
        paid_amount=Decimal(paid_amount),
        payment_status=OrderPaymentStatus.UNPAID,
    )
    s.add(order)
    s.commit()
    return ent, order


class TestStaleSnapshotIdempotentGuard:
    def test_second_call_with_stale_snapshot_skips(self, two_sessions):
        """两个 session 各持非 PAID 快照依次结算: 第二次必须幂等跳过。"""
        s1, s2 = two_sessions
        ent1, order1 = _seed(s1)
        ent2 = s2.query(Enterprise).filter_by(code="STALE-GUARD-ENT").one()
        order2 = s2.query(ChargingOrder).filter_by(order_no="SO-STALE-0001").one()
        # 两份快照均非 PAID (模拟并发窗口内各自读取)
        assert order1.payment_status != OrderPaymentStatus.PAID
        assert order2.payment_status != OrderPaymentStatus.PAID

        tx1 = deduct_on_order_complete(s1, order1, ent1)
        s1.commit()
        assert tx1 is not None

        tx2 = deduct_on_order_complete(s2, order2, ent2)
        s2.commit()
        assert tx2 is None  # 重查后已 PAID → 幂等返回

        s1.expire_all()
        ent = s1.query(Enterprise).filter_by(code="STALE-GUARD-ENT").one()
        assert ent.balance == Decimal("70.00")  # 仅扣一次
        txs = (
            s1.query(EnterpriseTransaction)
            .filter(EnterpriseTransaction.order_id == "SO-STALE-0001")
            .all()
        )
        assert len(txs) == 1
        assert txs[0].type == TransactionType.CONSUME
        assert txs[0].amount == Decimal("30.00")

    def test_zero_amount_order_idempotent(self, two_sessions):
        """零额订单第二次结算同样幂等: 零额流水只写一条。"""
        s1, s2 = two_sessions
        ent1, order1 = _seed(s1, paid_amount="0.00", balance="50.00")
        ent2 = s2.query(Enterprise).filter_by(code="STALE-GUARD-ENT").one()
        order2 = s2.query(ChargingOrder).filter_by(order_no="SO-STALE-0001").one()

        tx1 = deduct_on_order_complete(s1, order1, ent1)
        s1.commit()
        assert tx1 is not None
        assert tx1.amount == Decimal("0.00")

        tx2 = deduct_on_order_complete(s2, order2, ent2)
        s2.commit()
        assert tx2 is None

        s1.expire_all()
        txs = (
            s1.query(EnterpriseTransaction)
            .filter(EnterpriseTransaction.order_id == "SO-STALE-0001")
            .all()
        )
        assert len(txs) == 1
        ent = s1.query(Enterprise).filter_by(code="STALE-GUARD-ENT").one()
        assert ent.balance == Decimal("50.00")  # 零额不动余额

    def test_enterprise_deleted_does_not_mark_paid(self, two_sessions):
        """EnterpriseDeletedError 路径订单不得标 PAID (回归)。"""
        s1, _ = two_sessions
        ent, order = _seed(s1)
        s1.delete(ent)
        s1.commit()

        with pytest.raises(EnterpriseDeletedError):
            deduct_on_order_complete(s1, order, ent)

        fresh = s1.query(ChargingOrder).filter_by(order_no="SO-STALE-0001").one()
        assert fresh.payment_status == OrderPaymentStatus.UNPAID

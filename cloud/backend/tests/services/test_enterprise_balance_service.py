# -*- coding: utf-8 -*-
"""
企业预储值余额服务测试 - 覆盖率 ≥70%

被测: app/services/enterprise_balance_service.py
  (check_balance_available 纯函数 + deduct_on_order_complete /
   get_low_balance_enterprises DB 写读)

设计: 纯函数直断; DB 函数走 test_db 真实 SQLite。
本 service 全部接受 db 参数注入, 无模块级 SessionLocal 按值绑定坑。
涉及资金: 透支边界 / 金额量化 / 流水落库 / 订单 PAID 状态机全覆盖。

覆盖:
- check_balance_available  充足/边界(等于透支线 True)/超出/零金额/None余额/None额度
- deduct_on_order_complete  正常扣减+CONSUME流水+PAID / amount=0创建零额审计流水 / paid_amount=None /
                            透支raise InsufficientBalanceError(字段正确+不改余额订单) /
                            balance=None按0 / 金额量化2位
- get_low_balance_enterprises  默认阈值(balance<credit_limit) / 固定threshold /
                            asc排序 / INACTIVE过滤 / available_balance / None余额 / 空
"""
import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.services.enterprise_balance_service import (
    check_balance_available,
    deduct_on_order_complete,
    get_low_balance_enterprises,
    InsufficientBalanceError,
    EnterpriseDeletedError,
)
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
from app.models.charging_order import ChargingOrder, OrderPaymentStatus


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _ent(db, **kw):
    e = Enterprise(
        name=kw.get("name", "E"),
        code=kw.get("code", "C"),
        balance=kw.get("balance", Decimal("100.00")),
        credit_limit=kw.get("credit_limit", Decimal("0.00")),
        status=kw.get("status", EnterpriseStatus.ACTIVE),
    )
    db.add(e)
    return e


def _order(db, **kw):
    o = ChargingOrder(
        order_no=kw.get("order_no", "ORD-1"),
        station_id=1,
        device_id=1,
        user_id=1,
        paid_amount=kw.get("paid_amount", Decimal("10.00")),
        payment_status=kw.get("payment_status", OrderPaymentStatus.UNPAID),
        vehicle_id=kw.get("vehicle_id", None),
    )
    db.add(o)
    return o


# ═══════════════════════════════════════════════════════════════
# check_balance_available
# ═══════════════════════════════════════════════════════════════

class TestCheckBalanceAvailable:

    @staticmethod
    def _mock(balance, credit=Decimal("0.00")):
        e = MagicMock()
        e.balance = balance
        e.credit_limit = credit
        return e

    def test_sufficient(self):
        assert check_balance_available(self._mock(Decimal("100.00")), Decimal("30")) is True

    def test_exact_overdraft_boundary(self):
        # balance - amount == -credit_limit -> 边界含, 返回 True
        assert check_balance_available(
            self._mock(Decimal("10.00"), Decimal("20.00")), Decimal("30.00")
        ) is True

    def test_exceeds_overdraft(self):
        # 10 - 31 = -21 < -20 -> False
        assert check_balance_available(
            self._mock(Decimal("10.00"), Decimal("20.00")), Decimal("31.00")
        ) is False

    def test_zero_amount(self):
        # 0 - 0 = 0 >= 0 -> True
        assert check_balance_available(self._mock(Decimal("0.00")), Decimal("0.00")) is True

    def test_none_balance_defaults_zero(self):
        # 0 - 5 = -5 >= -10 -> True
        assert check_balance_available(
            self._mock(None, Decimal("10.00")), Decimal("5.00")
        ) is True

    def test_none_credit_defaults_zero(self):
        # 0 - 1 = -1 >= 0 -> False
        assert check_balance_available(
            self._mock(Decimal("0.00"), None), Decimal("1.00")
        ) is False


# ═══════════════════════════════════════════════════════════════
# deduct_on_order_complete
# ═══════════════════════════════════════════════════════════════

class TestDeductOnOrderComplete:

    def test_normal_deduct(self, test_db):
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("30.00"), order_no="ORD-NORMAL")
        db.commit()

        tx = deduct_on_order_complete(db, o, e)
        db.commit()

        assert tx is not None
        assert tx.type == TransactionType.CONSUME
        assert tx.amount == Decimal("30.00")
        assert tx.balance_after == Decimal("70.00")
        assert tx.order_id == "ORD-NORMAL"
        assert tx.enterprise_id == e.id
        assert "ORD-NORMAL" in tx.remark
        # 余额扣减
        assert e.balance == Decimal("70.00")
        # 订单标记 PAID
        assert o.payment_status == OrderPaymentStatus.PAID
        # 流水落库
        assert db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count() == 1

    def test_zero_amount_creates_audit_trail(self, test_db):
        """零额订单: 余额不扣减, 但创建 amount=0 的 CONSUME 审计流水。

        意图(见 deduct_on_order_complete 文档): 零额结算须在账户流水中留痕,
        否则对账时出现"订单 PAID 却无对应流水"的缺口。故返回值不是 None
        (None 仅留给"订单已 PAID 幂等跳过"), 而是一条金额为 0 的 CONSUME 流水。
        """
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"))
        o = _order(db, paid_amount=Decimal("0.00"), order_no="ORD-ZERO")
        db.commit()

        tx = deduct_on_order_complete(db, o, e)

        assert tx is not None
        assert tx.type == TransactionType.CONSUME
        assert tx.amount == Decimal("0.00")
        # 余额未动 (扣减前=扣减后)
        assert e.balance == Decimal("100.00")
        assert tx.balance_after == Decimal("100.00")
        # 订单标记 PAID
        assert o.payment_status == OrderPaymentStatus.PAID
        # 审计流水落库 (1 条 amount=0 的 CONSUME)
        assert db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count() == 1

    def test_none_paid_amount_treated_as_zero(self, test_db):
        """paid_amount=None 视为 0: 同零额, 创建 amount=0 审计流水而非返回 None。"""
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"))
        o = _order(db, paid_amount=None, order_no="ORD-NONE")
        db.commit()

        tx = deduct_on_order_complete(db, o, e)

        assert tx is not None
        assert tx.type == TransactionType.CONSUME
        assert tx.amount == Decimal("0.00")
        assert tx.balance_after == Decimal("100.00")
        assert o.payment_status == OrderPaymentStatus.PAID
        # 余额未动
        assert e.balance == Decimal("100.00")
        assert db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count() == 1

    def test_insufficient_raises(self, test_db):
        db = test_db["session"]
        e = _ent(db, balance=Decimal("10.00"), credit_limit=Decimal("5.00"))
        o = _order(db, paid_amount=Decimal("30.00"), order_no="ORD-OVER")
        db.commit()

        with pytest.raises(InsufficientBalanceError) as exc:
            deduct_on_order_complete(db, o, e)

        err = exc.value
        assert err.enterprise_id == e.id
        assert err.balance == Decimal("10.00")
        assert err.credit_limit == Decimal("5.00")
        assert err.required == Decimal("30.00")
        # 透支时余额未动, 订单未 PAID
        assert e.balance == Decimal("10.00")
        assert o.payment_status == OrderPaymentStatus.UNPAID
        assert db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count() == 0

    def test_balance_none_treated_as_zero(self, test_db):
        db = test_db["session"]
        e = _ent(db, balance=None, credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("5.00"), order_no="ORD-NB")
        db.commit()

        with pytest.raises(InsufficientBalanceError):
            deduct_on_order_complete(db, o, e)

    def test_quantize_two_places(self, test_db):
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"))
        o = _order(db, paid_amount=Decimal("30.00"), order_no="ORD-Q")
        db.commit()
        # 重设为需量化的金额并落库: deduct 获锁后以 with_for_update().populate_existing()
        # 重读订单 (卡 3b56a825 T-3 弹), 金额以库内最新值为准, 未提交的内存改动会被刷新
        o.paid_amount = Decimal("30.125")
        db.commit()

        deduct_on_order_complete(db, o, e)
        db.commit()
        # 100 - 30.125 = 69.875 -> quantize ROUND_HALF_EVEN -> 69.88
        assert e.balance == Decimal("69.88")

    # ─────────────────────────────────────────────────────────────
    # 并发与异常路径 (资金安全加固)
    # ─────────────────────────────────────────────────────────────

    def test_concurrent_deduction_race_condition(self, test_db):
        """并发扣减同一企业: 验证不会双扣 (TOCTOU 修复)。

        余额 100 + 信用 0, 两线程各扣 80 -> 仅一次成功, 另一次拒绝。
        生产 PostgreSQL 下 deduct 内 SELECT...FOR UPDATE 锁行串行化并发;
        SQLite 无行锁语义, 这里在 barrier 后用 BEGIN IMMEDIATE 开启写事务,
        等价模拟 PG 行锁 (第二个写事务阻塞至第一个 commit, deduct 重读到最新余额)。
        """
        SessionLocal = test_db["SessionLocal"]
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        db.commit()
        eid = e.id
        db.close()  # 释放主连接, 让并发线程独占

        results = {"ok": 0, "insuf": 0, "other": []}
        barrier = threading.Barrier(2)

        def worker(order_no):
            s = SessionLocal()
            try:
                s.execute(text("PRAGMA busy_timeout=30000"))
                o = _order(s, paid_amount=Decimal("80.00"), order_no=order_no)
                s.commit()
                barrier.wait()  # 两线程同步, 同时发起扣减
                s.execute(text("BEGIN IMMEDIATE"))  # 模拟 PG FOR UPDATE 串行化
                ent = s.query(Enterprise).filter(Enterprise.id == eid).first()
                tx = deduct_on_order_complete(s, o, ent)
                s.commit()
                if tx:
                    results["ok"] += 1
            except InsufficientBalanceError:
                s.rollback()
                results["insuf"] += 1
            except Exception as ex:
                try:
                    s.rollback()
                except Exception:
                    pass
                results["other"].append(f"{type(ex).__name__}:{str(ex)[:60]}")
            finally:
                s.close()

        threads = [
            threading.Thread(target=worker, args=("ORD-RA-A",)),
            threading.Thread(target=worker, args=("ORD-RA-B",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 无未预期异常, 恰好一次成功一次余额不足 -> 未发生双扣
        assert results["other"] == [], f"未预期异常: {results['other']}"
        assert results["ok"] == 1, f"应恰好一次扣减成功, 实际 {results}"
        assert results["insuf"] == 1, f"应恰好一次余额不足, 实际 {results}"

        # 资金守恒: 余额只扣了一次, 仅一笔流水
        chk = SessionLocal()
        try:
            ent = chk.query(Enterprise).filter(Enterprise.id == eid).first()
            ntx = chk.query(EnterpriseTransaction).filter_by(enterprise_id=eid).count()
            assert ent.balance == Decimal("20.00"), f"最终余额应为 20.00, 实际 {ent.balance}"
            assert ntx == 1, f"应仅 1 笔 CONSUME 流水, 实际 {ntx}"
        finally:
            chk.close()

    def test_deduct_db_failure_rollback(self, test_db, monkeypatch):
        """flush 失败时: rollback 被调用且原始异常 re-raise (保留异常类型)。"""
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("10.00"), order_no="ORD-DBFAIL")
        db.commit()

        # spy rollback, 验证 deduct 内 except 分支调用它
        rollback_calls = []
        real_rollback = db.rollback

        def spy_rollback(*args, **kwargs):
            rollback_calls.append(True)
            return real_rollback(*args, **kwargs)

        monkeypatch.setattr(db, "rollback", spy_rollback)

        # mock flush 抛异常 (主分支末尾的 db.flush)
        def flush_boom(*args, **kwargs):
            raise RuntimeError("flush boom")

        monkeypatch.setattr(db, "flush", flush_boom)

        # 原始异常类型保留向上抛
        with pytest.raises(RuntimeError, match="flush boom"):
            deduct_on_order_complete(db, o, e)

        assert len(rollback_calls) == 1, "flush 失败应触发一次 db.rollback()"

    def test_deduct_acquires_row_lock(self, test_db):
        """显式断言 deduct 对企业行发起 SELECT...FOR UPDATE。

        并发测试在 SQLite 下无法独立保护此行 (无 FOR UPDATE 语义, 移除仍通过),
        故用 mock 锁定锁查询存在, 防止未来误删 with_for_update 导致 TOCTOU 回归。
        真正的行级串行化由生产 PostgreSQL 提供。
        """
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("10.00"), order_no="ORD-LOCK")
        db.commit()

        # 构造链式 mock query, 让 with_for_update().first() 返回真实 enterprise
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q          # .filter(...) -> mock_q
        mock_q.with_for_update.return_value = mock_q  # .with_for_update() -> mock_q
        mock_q.first.return_value = e                 # .first() -> 真实 e (走扣减逻辑)

        original_query = db.query

        def query_intercept(*args, **kwargs):
            # 仅拦截 Enterprise 行锁查询, 其余放行真实 session
            if args and args[0] is Enterprise:
                return mock_q
            return original_query(*args, **kwargs)

        with patch.object(db, "query", side_effect=query_intercept):
            tx = deduct_on_order_complete(db, o, e)

        mock_q.with_for_update.assert_called_once(), \
            "deduct 必须对 enterprise 行发起 with_for_update() 行锁查询"
        assert tx is not None

    # ─────────────────────────────────────────────────────────────
    # 资金安全加固 (缺陷1 重复结算幂等 / 缺陷2 删除竞态静默丢扣)
    # ─────────────────────────────────────────────────────────────

    def test_repeat_settlement_idempotent_single_deduction(self, test_db):
        """缺陷1(资金安全 P0): 订单已 PAID 后重复调用 deduct 不得二次扣减、不得重复流水。

        复现: sessions.py 与 orders.py 双端点对同一单触发结算, 或重试/重复 webhook 回调。
        资金守恒不变量: 余额仅扣一次(100-30=70), CONSUME 流水仅 1 笔。
        """
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("30.00"), order_no="ORD-IDEM")
        db.commit()

        # 第一次结算: 正常扣减 + 流水 + 标 PAID
        tx1 = deduct_on_order_complete(db, o, e)
        db.commit()
        assert tx1 is not None
        assert tx1.amount == Decimal("30.00")
        assert o.payment_status == OrderPaymentStatus.PAID

        # 第二次结算(订单已 PAID): 幂等跳过
        tx2 = deduct_on_order_complete(db, o, e)
        db.commit()
        assert tx2 is None

        # 资金守恒: 余额仅扣一次, 流水仅 1 笔
        db.expire_all()
        ent_chk = db.query(Enterprise).filter(Enterprise.id == e.id).first()
        assert ent_chk.balance == Decimal("70.00"), (
            f"重复结算不得双扣, 余额应为 70.00, 实际 {ent_chk.balance}"
        )
        ntx = db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count()
        assert ntx == 1, f"重复结算不得重复流水, 应 1 笔, 实际 {ntx}"

    def test_deleted_enterprise_race_raises_not_silent_loss(self, test_db):
        """缺陷2(营收漏损): 结算前企业行被删 → with_for_update().first()=None。

        buggy 行为: 继续对 stale 对象赋值 balance, flush 的 UPDATE 匹配 0 行静默丢失,
        订单却照标 PAID → 白嫖充电。
        修复契约: locked is None → raise EnterpriseDeletedError, 订单不得标 PAID, 不写流水。
        (expire_on_commit=True 下真删除会触发 ObjectDeletedError 重载, 故用 mock 锁查询落空
        精确锁定 locked=None 分支的守卫契约。)
        """
        from unittest.mock import patch
        db = test_db["session"]
        e = _ent(db, balance=Decimal("100.00"), credit_limit=Decimal("0.00"))
        o = _order(db, paid_amount=Decimal("30.00"), order_no="ORD-DELRACE")
        db.commit()

        # 行锁查询落空: 企业行已不存在(模拟结算前被另一事务删除)
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.with_for_update.return_value = mock_q
        mock_q.first.return_value = None
        original_query = db.query

        def intercept(*a, **kw):
            if a and a[0] is Enterprise:
                return mock_q
            return original_query(*a, **kw)

        raised = False
        with patch.object(db, "query", side_effect=intercept):
            try:
                deduct_on_order_complete(db, o, e)
            except EnterpriseDeletedError:
                raised = True

        assert raised, "企业行被删(locked=None)必须 raise, 不得静默丢扣"
        # 白嫖防护: 订单不得被标 PAID
        assert o.payment_status == OrderPaymentStatus.UNPAID
        # 不得写入流水
        db.rollback()
        assert db.query(EnterpriseTransaction).filter_by(enterprise_id=e.id).count() == 0


# ═══════════════════════════════════════════════════════════════
# get_low_balance_enterprises
# ═══════════════════════════════════════════════════════════════

class TestGetLowBalanceEnterprises:

    def test_default_threshold_balance_below_credit(self, test_db):
        db = test_db["session"]
        _ent(db, name="low", code="L1", balance=Decimal("5.00"), credit_limit=Decimal("50.00"))
        _ent(db, name="ok", code="O1", balance=Decimal("200.00"), credit_limit=Decimal("50.00"))
        db.commit()

        result = get_low_balance_enterprises(db)

        assert len(result) == 1
        assert result[0]["name"] == "low"
        assert result[0]["balance"] == 5.0
        assert result[0]["credit_limit"] == 50.0
        assert result[0]["available_balance"] == 55.0

    def test_fixed_threshold(self, test_db):
        db = test_db["session"]
        _ent(db, name="a", code="A", balance=Decimal("10.00"), credit_limit=Decimal("1000.00"))
        _ent(db, name="b", code="B", balance=Decimal("80.00"), credit_limit=Decimal("0.00"))
        db.commit()

        # threshold=50: balance < 50 -> 仅 a
        result = get_low_balance_enterprises(db, threshold=Decimal("50"))
        assert [r["name"] for r in result] == ["a"]

    def test_sorted_by_balance_asc(self, test_db):
        db = test_db["session"]
        _ent(db, name="hi", code="H", balance=Decimal("40.00"), credit_limit=Decimal("1000.00"))
        _ent(db, name="lo", code="L", balance=Decimal("5.00"), credit_limit=Decimal("1000.00"))
        _ent(db, name="mid", code="M", balance=Decimal("20.00"), credit_limit=Decimal("1000.00"))
        db.commit()

        result = get_low_balance_enterprises(db)
        assert [r["balance"] for r in result] == [5.0, 20.0, 40.0]

    def test_inactive_excluded(self, test_db):
        db = test_db["session"]
        _ent(db, name="act", code="AC", balance=Decimal("5.00"), credit_limit=Decimal("50.00"),
             status=EnterpriseStatus.ACTIVE)
        _ent(db, name="ina", code="IN", balance=Decimal("1.00"), credit_limit=Decimal("50.00"),
             status=EnterpriseStatus.INACTIVE)
        db.commit()

        result = get_low_balance_enterprises(db)
        assert [r["name"] for r in result] == ["act"]

    def test_none_balance_handled(self, test_db):
        db = test_db["session"]
        _ent(db, name="nb", code="NB", balance=None, credit_limit=Decimal("50.00"))
        db.commit()

        result = get_low_balance_enterprises(db)
        assert len(result) == 1
        assert result[0]["balance"] == 0.0
        assert result[0]["available_balance"] == 50.0

    def test_empty(self, test_db):
        db = test_db["session"]
        db.commit()
        assert get_low_balance_enterprises(db) == []

    def test_amounts_no_float_precision_tail(self, test_db):
        """[卡79f610a3] 序列化边界精度不变量: balance/credit_limit/available_balance
        三项 float 不得带长浮点尾。

        get_low_balance_enterprises 返回 dict 时 Decimal→float(序列化边界)。本测试锁定
        不变量: 每个金额 v 必须满足 v == round(v, 2)。取 float 算术下会塌成长尾的组合
        (0.10+0.20 → 0.30000000000000004) 最大化回归保护——一旦序列化层 round 兜底被移除/
        旁路, 或上游 Numeric 列降级为 float, 此处即 RED。
        """
        db = test_db["session"]
        _ent(db, name="prec", code="P", balance=Decimal("0.10"), credit_limit=Decimal("0.20"))
        db.commit()

        result = get_low_balance_enterprises(db)
        assert len(result) == 1
        row = result[0]

        def _no_tail(v):
            return v == round(v, 2)

        assert _no_tail(row["balance"]), row["balance"]
        assert _no_tail(row["credit_limit"]), row["credit_limit"]
        assert _no_tail(row["available_balance"]), row["available_balance"]

        # 精确到 2 位, 且不等于 float 算术泄漏形式
        assert row["available_balance"] == 0.30
        assert row["available_balance"] != 0.1 + 0.2  # 0.30000000000000004 != 0.30

    # ─────────────────────────────────────────────────────────────
    # 序列化精度: float() → round(x, 2) 防长浮点尾数 (卡79f610a3)
    # ─────────────────────────────────────────────────────────────

    def test_float_rounding_prevents_long_tail(self, test_db):
        """脏数据场景: balance/credit 携带浮点残留(别处 float 写入或 REAL 存储精度丢失
        进 Numeric 列后读回的长尾 Decimal), float() 直转会序列化出长浮点尾数。

        修复: float(round(x, 2)) 在序列化边界截断到 2 位金额。
        balance=0.30000000000000004(0.1+0.2 残留), credit=19.999999999999996,
        sum=20.299999999999997 —— 全部带长尾, 修复后期望干净值。
        """
        db = test_db["session"]
        _ent(
            db,
            name="dirty",
            code="D1",
            balance=Decimal("0.30000000000000004"),
            credit_limit=Decimal("19.999999999999996"),
        )
        db.commit()

        result = get_low_balance_enterprises(db)
        assert len(result) == 1
        row = result[0]
        # 修复前: 0.30000000000000004 / 19.999999999999996 / 20.299999999999997 (长尾)
        assert row["balance"] == 0.3
        assert row["credit_limit"] == 20.0
        assert row["available_balance"] == 20.3

    def test_float_fields_are_two_decimal_clean(self, test_db):
        """通用不变式: 三个金额字段序列化后必为 2 位精度, 无长浮点尾数。

        round(v, 2) == v 对携带长尾的 float 为 False (如 0.30000000000000004),
        对干净金额恒 True。覆盖 balance/credit/available_balance 三字段。
        """
        db = test_db["session"]
        _ent(
            db,
            name="d1", code="C1",
            balance=Decimal("0.30000000000000004"),
            credit_limit=Decimal("19.999999999999996"),
        )
        _ent(
            db,
            name="d2", code="C2",
            balance=Decimal("3.333"),  # 多位小数 -> 序列化应截到 3.33
            credit_limit=Decimal("10.00"),  # > balance 以满足默认低余额过滤(balance<credit_limit)
        )
        db.commit()

        for row in get_low_balance_enterprises(db):
            for field in ("balance", "credit_limit", "available_balance"):
                v = row[field]
                assert round(v, 2) == v, (
                    f"{field}={v!r} 携带长浮点尾数, 应为 2 位精度干净金额"
                )
        # d2 的 balance 多位小数被截到 3.33
        d2 = next(r for r in get_low_balance_enterprises(db) if r["name"] == "d2")
        assert d2["balance"] == 3.33

    # ─────────────────────────────────────────────────────────────
    # 资金安全加固 (缺陷3 低余额 NULL 盲区 — 监控静默失效)
    # ─────────────────────────────────────────────────────────────

    def test_null_balance_and_credit_flagged_via_coalesce(self, test_db):
        """缺陷3(监控静默失效): 真实 NULL 下 `balance < credit_limit` 走三值逻辑被排除。

        ORM 的 default=0 强转使常规 ORM 写入不会产生 NULL, 故先 ORM 插入(确保 status
        以 SAEnum 的 NAME 形式正确落库), 再用原始 UPDATE 把 balance/credit_limit 置 NULL,
        复现迁移/原始SQL/未来旁路写入场景。修复(coalesce)后:
        - NULLBAL   balance=NULL(语义0) < credit_limit=50  → 须进清单
        - NULLCRED  balance=-5            < credit_limit=NULL(语义0) → 须进清单
        buggy 下两者均被 `NULL < x` 的 unknown 三值逻辑静默排除。
        """
        db = test_db["session"]
        # ORM 插入(status 正确落库), balance 给非0占位
        _ent(db, name="NULLBAL", code="NB", balance=Decimal("1.00"), credit_limit=Decimal("50.00"))
        _ent(db, name="NULLCRED", code="NC", balance=Decimal("-5.00"), credit_limit=Decimal("10.00"))
        _ent(db, name="NORMAL_LOW", code="NL", balance=Decimal("3.00"), credit_limit=Decimal("50.00"))
        db.commit()
        # 原始 UPDATE 强制写真实 NULL (绕过 ORM default=0 强转)
        db.execute(text("UPDATE enterprises SET balance=NULL WHERE code='NB'"))
        db.execute(text("UPDATE enterprises SET credit_limit=NULL WHERE code='NC'"))
        db.commit()
        db.expire_all()

        names = {r["name"] for r in get_low_balance_enterprises(db)}
        assert "NORMAL_LOW" in names
        assert "NULLBAL" in names, (
            "balance=NULL(语义0元) < credit_limit=50 须被预警, 不得被三值逻辑静默排除"
        )
        assert "NULLCRED" in names, (
            "balance=-5 < credit_limit=NULL(语义0) 须被预警, 不得被三值逻辑静默排除"
        )

    def test_null_balance_flagged_under_fixed_threshold(self, test_db):
        """缺陷3 threshold 分支同样不得因 balance=NULL 静默排除。

        固定阈值 50: balance=NULL(语义0) < 50 → 须命中。buggy 下 `NULL < 50` 被排除。
        """
        db = test_db["session"]
        _ent(db, name="NULLBAL_TH", code="NT", balance=Decimal("1.00"), credit_limit=Decimal("100.00"))
        db.commit()
        db.execute(text("UPDATE enterprises SET balance=NULL WHERE code='NT'"))
        db.commit()
        db.expire_all()

        names = {r["name"] for r in get_low_balance_enterprises(db, threshold=Decimal("50.00"))}
        assert "NULLBAL_TH" in names, (
            "threshold 分支: balance=NULL(语义0) < 50 须命中, 不得被三值逻辑静默排除"
        )

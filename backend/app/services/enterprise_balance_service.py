"""
企业预储值余额服务 - 预储值消耗闭环

核心功能:
1. deduct_on_order_complete  订单完成 → 原子扣减 balance → 写 EnterpriseTransaction 流水
2. check_balance_available   透支保护: balance - amount >= -credit_limit
3. get_low_balance_enterprises  低余额车队清单 (余额 < 阈值)
"""
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
from app.models.charging_order import ChargingOrder, OrderPaymentStatus

# 金额精度: 所有入库金额(流水 amount / balance_after)统一两位小数, 杜绝精度口径不一。
_AMOUNT_QUANT = Decimal("0.01")

# 纯预付车队低余额兜底预警线: credit_limit=0 时, 余额 <= 此线即视为低余额。
# 默认阈值 `balance < credit_limit` 在 credit_limit=0 时退化为 balance<0,
# 而透支保护保证 balance 不会低于 0 → 纯预付车队余额耗尽(balance==0)仍不预警,
# 形成监控盲区。此绝对线兜底该场景。
LOW_BALANCE_FALLBACK = Decimal("0.00")


class InsufficientBalanceError(Exception):
    """余额不足且超出透支额度"""
    def __init__(self, enterprise_id: int, balance: Decimal, credit_limit: Decimal, required: Decimal):
        self.enterprise_id = enterprise_id
        self.balance = balance
        self.credit_limit = credit_limit
        self.required = required
        super().__init__(
            f"企业 {enterprise_id} 余额不足: 余额={balance}, 信用额度={credit_limit}, "
            f"需要={required}, 可用={balance + credit_limit}"
        )


class EnterpriseDeletedError(Exception):
    """结算时企业账户行已不存在 (删除竞态)

    with_for_update 锁查询返回 None: 结算前企业行被另一事务删除。
    必须中断事务回滚 (订单不得标 PAID), 严禁对 stale 对象继续赋值——
    否则 flush 的 UPDATE 匹配 0 行静默丢失扣款, 订单却照标 PAID → 白嫖充电。
    """
    def __init__(self, enterprise_id: int):
        self.enterprise_id = enterprise_id
        super().__init__(
            f"企业账户 {enterprise_id} 不存在(可能已被删除), 余额扣减中止"
        )


def check_balance_available(
    enterprise: Enterprise,
    amount: Decimal,
) -> bool:
    """检查扣减后余额是否在透支额度内

    Args:
        enterprise: 企业账户 ORM 对象
        amount: 需要扣减的金额

    Returns:
        True if balance - amount >= -credit_limit
    """
    balance = enterprise.balance or Decimal("0.00")
    credit_limit = enterprise.credit_limit or Decimal("0.00")
    return (balance - amount) >= (-credit_limit)


def deduct_on_order_complete(
    db: Session,
    order: ChargingOrder,
    enterprise: Enterprise,
) -> Optional[EnterpriseTransaction]:
    """订单完成时原子扣减企业余额并写流水

    事务步骤（调用方负责传入有效 session）:
    0. 幂等守卫: 订单已 PAID → 直接跳过 (杜绝重复结算双扣)
    1. 行锁重读企业账户; locked=None(企业被删) → 中断 (杜绝静默丢扣/白嫖)
    2. 检查透支额度
    3. 扣减 enterprise.balance
    4. 写 EnterpriseTransaction (type=CONSUME)
    5. 标记订单 payment_status = PAID

    Args:
        db: SQLAlchemy Session
        order: 已完成的充电订单
        enterprise: 关联的企业账户

    Returns:
        创建的 EnterpriseTransaction 对象(含金额为0的零额结算流水), 或 None（订单已 PAID 幂等跳过）

    Raises:
        InsufficientBalanceError: 余额不足且超出透支额度
        EnterpriseDeletedError: 结算时企业账户行已不存在 (删除竞态)
    """
    # 0. 幂等守卫: 重复结算(sessions/orders 双端点同单、重试、重复 webhook)时
    #    订单已 PAID → 直接返回, 杜绝二次扣减与重复 CONSUME 流水 (资金安全 P0)。
    if order.payment_status == OrderPaymentStatus.PAID:
        return None

    try:
        # 1. 行锁: SELECT ... FOR UPDATE 串行化同一企业的并发扣减,
        #    消除 check_balance_available 与扣减之间的 TOCTOU 窗口(双扣/超额透支)。
        #    生产 PostgreSQL 下真正锁行; SQLite 下为 no-op, 并发安全由调用方事务隔离保证。
        #    同一 session 内 identity map 保证返回的即是传入 enterprise 本身。
        locked = db.query(Enterprise).filter(
            Enterprise.id == enterprise.id
        ).with_for_update().first()
        if locked is None:
            # 删除竞态: 结算前企业行被另一事务删除。继续对 stale 对象赋值会让
            # flush 的 UPDATE 匹配 0 行静默丢失扣款, 而订单却照标 PAID → 白嫖充电。
            # 必须中断: 事务回滚, 订单不得标 PAID (营收漏损防护)。
            raise EnterpriseDeletedError(enterprise_id=enterprise.id)
        enterprise = locked

        # 1.5 订单行锁重查 + 幂等守卫二次执行 (卡 76fac6cc T-3 弹):
        #    开头的守卫读的是调用方传入的内存快照——并发双 complete 同一订单时,
        #    两个调用方都在对方提交前读到非 PAID 快照, 守卫形同虚设 → 双扣余额+双流水。
        #    获企业锁后以 with_for_update().populate_existing() 重查订单, 强制重发
        #    SELECT 刷新 identity-map 陈旧快照(对照 enterprises._PUT锁/fleet_drivers._lock_account),
        #    基于库内最新状态重新判断: 已 PAID → 幂等返回 None。
        locked_order = db.query(ChargingOrder).filter(
            ChargingOrder.id == order.id
        ).with_for_update().populate_existing().first()
        if locked_order is not None:
            order = locked_order
        if order.payment_status == OrderPaymentStatus.PAID:
            return None

        amount = order.paid_amount or Decimal("0.00")
        if amount <= 0:
            # 金额为零: 不扣减余额, 但标记订单已支付, 并写金额为0的 CONSUME 流水
            # (审计痕迹: 零额订单须在账户流水中可追溯, 否则对账缺口)。
            order.payment_status = OrderPaymentStatus.PAID  # type: ignore
            current_balance = enterprise.balance or Decimal("0.00")
            tx = EnterpriseTransaction(
                enterprise_id=enterprise.id,
                vehicle_id=order.vehicle_id,
                type=TransactionType.CONSUME,
                amount=Decimal("0.00"),
                balance_after=current_balance.quantize(_AMOUNT_QUANT),
                order_id=order.order_no,
                remark=f"充电订单零额结算 {order.order_no}",
            )
            db.add(tx)
            try:
                db.flush()
            except Exception:
                db.rollback()
                raise
            return tx

        # 2. 透支检查 (持锁后基于最新余额判断)
        if not check_balance_available(enterprise, amount):
            raise InsufficientBalanceError(
                enterprise_id=enterprise.id,
                balance=enterprise.balance or Decimal("0.00"),
                credit_limit=enterprise.credit_limit or Decimal("0.00"),
                required=amount,
            )

        # 3. 扣减余额
        current_balance = enterprise.balance or Decimal("0.00")
        new_balance = (current_balance - amount).quantize(_AMOUNT_QUANT)
        enterprise.balance = new_balance

        # 4. 写流水 (amount 同样 quantize, 与 balance_after 口径一致, 杜绝精度不一)
        tx = EnterpriseTransaction(
            enterprise_id=enterprise.id,
            vehicle_id=order.vehicle_id,
            type=TransactionType.CONSUME,
            amount=amount.quantize(_AMOUNT_QUANT),
            balance_after=new_balance,
            order_id=order.order_no,
            remark=f"充电订单结算 {order.order_no}",
        )
        db.add(tx)

        # 5. 标记订单支付状态
        order.payment_status = OrderPaymentStatus.PAID  # type: ignore

        db.flush()
        return tx
    except (InsufficientBalanceError, EnterpriseDeletedError):
        # 检查阶段抛出 (透支/企业被删), 尚无写操作, 无需 rollback (调用方负责事务清理)
        raise
    except Exception:
        # DB 写操作失败: 回滚已暂存变更, 保留原始异常类型向上抛
        db.rollback()
        raise


def get_low_balance_enterprises(
    db: Session,
    threshold: Optional[Decimal] = None,
    team_id: Optional[int] = None,
) -> List[dict]:
    """查询余额低于阈值的车队清单

    默认阈值为各企业自身 credit_limit（余额 < credit_limit 视为低余额预警）。
    传入 threshold 则使用固定阈值（余额 < threshold）。

    NULL 语义: balance/credit_limit 为 NULL 时按 0 比较 (func.coalesce),
    避免 SQL 三值逻辑 (NULL < x → unknown) 将该行静默排除——
    balance=NULL (语义 0 元) 的企业须能被预警, 而非永久沉默。

    Args:
        db: SQLAlchemy Session
        threshold: 可选, 固定预警阈值
        team_id: 可选, 团队 scope (卡 5219a206); 非 None 时仅返回
            Enterprise.owner_team_id == team_id 的企业, None 表示全量(平台级)

    Returns:
        [{id, name, code, balance, credit_limit, available_balance}, ...]
    """
    query = db.query(Enterprise).filter(
        Enterprise.status == EnterpriseStatus.ACTIVE
    )
    if team_id is not None:
        query = query.filter(Enterprise.owner_team_id == team_id)

    # coalesce 兜底 NULL → 0: 杜绝三值逻辑静默排除 NULL 余额/额度行 (监控失效防护)
    if threshold is not None:
        # 显式阈值: 余额 < threshold, 行为不变
        query = query.filter(func.coalesce(Enterprise.balance, 0) < threshold)
    else:
        # 默认: 余额 < credit_limit 即为低余额(可用资金低于信用额度线)。
        # 兜底: credit_limit=0 的纯预付车队, 该条件退化为 balance<0, 而透支保护
        # 保证 balance 不会低于 0 → 余额耗尽(balance==0)仍不预警, 形成盲区。
        # 追加绝对线兜底: balance <= LOW_BALANCE_FALLBACK 也视为低余额。
        query = query.filter(
            or_(
                func.coalesce(Enterprise.balance, 0) < func.coalesce(Enterprise.credit_limit, 0),
                func.coalesce(Enterprise.balance, 0) <= LOW_BALANCE_FALLBACK,
            )
        )

    enterprises = query.order_by(Enterprise.balance.asc()).all()

    result = []
    for ent in enterprises:
        balance = ent.balance or Decimal("0.00")
        credit = ent.credit_limit or Decimal("0.00")
        result.append({
            "id": ent.id,
            "name": ent.name,
            "code": ent.code,
            "balance": float(round(balance, 2)),
            "credit_limit": float(round(credit, 2)),
            "available_balance": float(round(balance + credit, 2)),
        })
    return result

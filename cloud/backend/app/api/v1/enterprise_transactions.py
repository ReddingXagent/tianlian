"""
企业资金池交易管理 API - Phase43 车队管理

功能:
- GET  /api/v1/enterprises/{enterprise_id}/transactions —— 交易列表
- POST /api/v1/enterprises/{enterprise_id}/transactions —— 充值/消费
"""
import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import assert_enterprise_team_access
from app.models.user import User
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])

logger = logging.getLogger(__name__)


# ========== Schemas ==========

class TransactionCreateRequest(BaseModel):
    type: Literal["recharge", "consume", "refund"]  # recharge / consume / refund
    amount: float = Field(..., ge=0)
    vehicle_id: Optional[int] = None
    order_id: Optional[str] = None
    remark: Optional[str] = None


# ========== Helpers ==========

def _tx_to_dict(tx: EnterpriseTransaction) -> dict:
    return {
        "id": tx.id,
        "enterprise_id": tx.enterprise_id,
        "vehicle_id": tx.vehicle_id,
        "type": tx.type.value if tx.type else None,
        "amount": float(tx.amount) if tx.amount else 0,
        "balance_after": float(tx.balance_after) if tx.balance_after else 0,
        "order_id": tx.order_id,
        "remark": tx.remark,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


# ========== API Endpoints ==========

@router.get("", summary="获取企业交易列表")
def list_enterprise_transactions(
    enterprise_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取企业交易流水列表"""
    try:
        # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业交易；越权/不存在 → 404。
        assert_enterprise_team_access(db, enterprise_id, user)

        query = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.enterprise_id == enterprise_id
        )
        total = query.count()
        items = query.order_by(EnterpriseTransaction.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        return paginated_response(
            items=[_tx_to_dict(tx) for tx in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_enterprise_transactions 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("", summary="创建交易")
def create_enterprise_transaction(
    enterprise_id: int,
    data: TransactionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建交易并更新企业余额"""
    try:
        # team scoping（任务卡 ab5c5f17）：非 admin 仅可为本 team 企业创建交易；越权/不存在 → 404。
        # assert 返回 Enterprise ORM，复用替代手动查询+404。
        enterprise = assert_enterprise_team_access(db, enterprise_id, user)

        # 校验交易类型
        if data.type not in ("recharge", "consume", "refund"):
            raise HTTPException(status_code=400, detail="无效的交易类型，仅支持 recharge/consume/refund")

        # 卡601149f8: 负数金额 = 资金安全漏洞(consume 负数凭空造钱/recharge 负数抽干余额),
        # 充值/消费/退款三类统一要求 amount > 0(照抄 fleet_drivers 卡0020305d 范式)
        amount = Decimal(str(data.amount))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="交易金额必须大于0")

        # 卡601149f8: 企业行加行锁(PG 真锁行, SQLite no-op), 持锁后重读余额再计算,
        # 封堵并发创建交易的 lost update
        from app.models.enterprise import Enterprise
        locked = db.query(Enterprise).filter(Enterprise.id == enterprise_id).with_for_update().first()
        if locked is not None:
            enterprise = locked
        current_balance = enterprise.balance if enterprise.balance else Decimal("0.00")

        # 卡4d3ea0ed: order_id 非空时按 (enterprise_id, type, order_id) 幂等去重(资金安全)。
        # 企业行锁已串行化同企业写入, 持锁后重查即可; DB 层 uq_et_enterprise_type_order
        # 部分唯一索引兜底并发漏网, IntegrityError 时回查确认后统一 409。
        if data.order_id:
            dup = (
                db.query(EnterpriseTransaction.id)
                .filter(
                    EnterpriseTransaction.enterprise_id == enterprise_id,
                    EnterpriseTransaction.type == TransactionType(data.type),
                    EnterpriseTransaction.order_id == data.order_id,
                )
                .first()
            )
            if dup is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"重复的交易: type={data.type} order_id={data.order_id} 已存在",
                )

        # 计算新余额(口径 quantize 0.01)
        tx_type = TransactionType(data.type)
        if data.type == "recharge":
            new_balance = current_balance + amount
        elif data.type == "refund":
            new_balance = current_balance + amount
        else:  # consume
            new_balance = current_balance - amount
            # 卡601149f8: 透支防线, 语义对齐 enterprise_balance_service.check_balance_available
            # (不 import 该服务内部函数, 就地下判): new_balance >= -(credit_limit or 0)
            credit_limit = enterprise.credit_limit or Decimal("0.00")
            if new_balance < -credit_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"余额不足: 余额={current_balance}, 信用额度={credit_limit}, 本次需扣减={amount}",
                )
        new_balance = new_balance.quantize(Decimal("0.01"))

        # 创建交易记录
        tx = EnterpriseTransaction(
            enterprise_id=enterprise_id,
            vehicle_id=data.vehicle_id,
            type=tx_type,
            amount=amount,
            balance_after=new_balance,
            order_id=data.order_id,
            remark=data.remark,
        )
        db.add(tx)

        # 更新企业余额
        enterprise.balance = new_balance

        # 卡4d3ea0ed: DB 层 uq_et_enterprise_type_order 兜底并发竞态 → rollback 后 409
        from sqlalchemy.exc import IntegrityError
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"重复的交易: type={data.type} order_id={data.order_id} 已存在",
            )
        db.refresh(tx)

        return success_response(_tx_to_dict(tx), message=f"{data.type} 交易创建成功")
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("create_enterprise_transaction 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

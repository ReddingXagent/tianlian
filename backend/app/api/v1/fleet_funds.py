"""
企业资金账户管理 API - 对齐前端 Fleet FundAccount 契约

挂载前缀 /fleet/funds (见 api/v1/__init__.py), 实际路径:
- GET    /api/v1/fleet/funds             账户列表(企业筛选 + 分页)
- POST   /api/v1/fleet/funds             创建账户
- GET    /api/v1/fleet/funds/{id}        账户详情
- PUT    /api/v1/fleet/funds/{id}        更新账户
- DELETE /api/v1/fleet/funds/{id}        删除账户
"""
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.enterprise import Enterprise
from app.models.fund_pool import (
    FundPool, FundPoolTransaction, FundAccountStatus,
    FundTransactionType, FundTransactionStatus,
)
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])


# ─── Schemas ───

class FundCreateRequest(BaseModel):
    enterprise_id: Optional[int] = Field(None, description="所属企业ID; 不传则建无企业账户")
    enterprise_name: Optional[str] = Field(None, description="企业名称; 传 enterprise_id 时以企业表为准自动回填")
    account_name: str = Field(..., min_length=1, max_length=100, description="账户名称")
    account_type: str = Field("运营账户", max_length=50, description="账户类型")
    balance: float = Field(0.0, ge=0.0, description="初始余额(元)")
    status: Literal["active", "frozen", "inactive"] = Field("active", description="账户状态 active/frozen/inactive")
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    currency: str = Field("¥", max_length=10, description="币种符号")
    description: Optional[str] = None


class FundUpdateRequest(BaseModel):
    enterprise_id: Optional[int] = None
    enterprise_name: Optional[str] = None
    account_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_type: Optional[str] = None
    balance: Optional[float] = Field(None, ge=0.0)
    status: Optional[Literal["active", "frozen", "inactive"]] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    currency: Optional[str] = None
    description: Optional[str] = None


# ─── Helpers ───

def _fund_to_dict(f: FundPool) -> dict:
    return {
        "id": f.id,
        "enterprise_id": f.enterprise_id,
        "enterprise_name": f.enterprise_name,
        "account_name": f.account_name,
        "account_type": f.account_type,
        "balance": float(f.balance) if f.balance is not None else 0.0,
        "status": f.status.value if f.status else None,
        "bank_name": f.bank_name,
        "bank_account": f.bank_account,
        "currency": f.currency,
        "description": f.description,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _resolve_status(value: Optional[str], fallback: FundAccountStatus) -> FundAccountStatus:
    if value is None:
        return fallback
    try:
        return FundAccountStatus(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法账户状态: {value}")


def _get_or_404(db: Session, fund_id: int) -> FundPool:
    fund = db.query(FundPool).filter(FundPool.id == fund_id).first()
    if not fund:
        raise HTTPException(status_code=404, detail="资金账户不存在")
    return fund


TWO_PLACES = Decimal("0.01")


def _txn_to_dict(t: FundPoolTransaction) -> dict:
    return {
        "id": t.id,
        "transaction_type": t.transaction_type.value if t.transaction_type else None,
        "amount": float(t.amount) if t.amount is not None else None,
        "balance_before": float(t.balance_before) if t.balance_before is not None else None,
        "balance_after": float(t.balance_after) if t.balance_after is not None else None,
        "status": t.status.value if t.status else None,
        "remark": t.remark,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _record_txn(
    db: Session,
    fund_id: int,
    transaction_type: FundTransactionType,
    amount: Decimal,
    balance_before: Decimal,
    balance_after: Decimal,
    operator: str,
) -> None:
    """余额变动流水落库 (卡 20fb69d6: 资金审计闭环, 复用司机/企业账户必写流水范式)。"""
    db.add(FundPoolTransaction(
        fund_pool_id=fund_id,
        transaction_type=transaction_type,
        amount=amount.quantize(TWO_PLACES),
        balance_before=balance_before.quantize(TWO_PLACES),
        balance_after=balance_after.quantize(TWO_PLACES),
        status=FundTransactionStatus.SUCCESS,
        remark=f"手动调账, 操作人: {operator}",
    ))


# ─── Endpoints ───

@router.get("", summary="获取企业资金账户列表")
def list_funds(
    enterprise_id: Optional[int] = Query(None, description="企业ID筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取资金账户列表, 支持按企业筛选 (卡 45166947: 缺省时 team 兜底过滤)。"""
    query = db.query(FundPool)
    scope = team_scope(current_user)
    if scope is not None:
        # 团队级用户缺省 enterprise_id 时按企业归属 team 兜底过滤;
        # outerjoin+filter 使无归属企业(enterprise_id NULL)的孤儿账户对团队级用户不可见
        query = query.outerjoin(Enterprise, Enterprise.id == FundPool.enterprise_id).filter(
            Enterprise.owner_team_id == scope
        )
    if enterprise_id is not None:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = query.filter(FundPool.enterprise_id == enterprise_id)

    total = query.count()
    items = (
        query.order_by(FundPool.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_fund_to_dict(f) for f in items], total, page, page_size)


@router.post("", summary="创建企业资金账户")
def create_fund(
    data: FundCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建资金账户。传 enterprise_id 时校验企业存在并自动回填企业名称。"""
    enterprise_name = data.enterprise_name
    if data.enterprise_id is not None:
        ent = assert_enterprise_team_access(db, data.enterprise_id, current_user)
        enterprise_name = ent.name  # 以企业表为准

    fund = FundPool(
        enterprise_id=data.enterprise_id,
        enterprise_name=enterprise_name,
        account_name=data.account_name,
        account_type=data.account_type,
        balance=Decimal(str(data.balance)),
        status=_resolve_status(data.status, FundAccountStatus.ACTIVE),
        bank_name=data.bank_name,
        bank_account=data.bank_account,
        currency=data.currency,
        description=data.description,
    )
    db.add(fund)
    db.flush()  # 拿 fund.id 供流水外键
    init_balance = Decimal(str(data.balance)).quantize(Decimal("0.01"))
    if init_balance > 0:
        _record_txn(
            db, fund.id, FundTransactionType.RECHARGE,
            amount=init_balance,
            balance_before=Decimal("0.00"),
            balance_after=init_balance,
            operator=current_user.username,
        )
    db.commit()
    db.refresh(fund)
    return success_response(_fund_to_dict(fund), message="资金账户创建成功")


@router.get("/{fund_id}", summary="获取资金账户详情")
def get_fund(
    fund_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个资金账户详情。"""
    fund = _get_or_404(db, fund_id)
    if fund.enterprise_id is not None:
        assert_enterprise_team_access(db, fund.enterprise_id, current_user)
    return success_response(_fund_to_dict(fund))


@router.put("/{fund_id}", summary="更新企业资金账户")
def update_fund(
    fund_id: int,
    data: FundUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新资金账户, 仅覆盖传入字段。"""
    fund = _get_or_404(db, fund_id)
    if fund.enterprise_id is not None:
        assert_enterprise_team_access(db, fund.enterprise_id, current_user)

    if data.enterprise_id is not None:
        ent = assert_enterprise_team_access(db, data.enterprise_id, current_user)
        fund.enterprise_id = data.enterprise_id
        fund.enterprise_name = ent.name
    if data.enterprise_name is not None:
        fund.enterprise_name = data.enterprise_name
    if data.account_name is not None:
        fund.account_name = data.account_name
    if data.account_type is not None:
        fund.account_type = data.account_type
    if data.balance is not None:
        # 行锁: SELECT ... FOR UPDATE 串行化并发直写, 防止读-改-写丢更新(lost update)。
        # 生产 PostgreSQL 下真正锁行; SQLite 下为 no-op。populate_existing 刷新陈旧快照
        # (对照 fleet_drivers._lock_account / enterprise_balance_service.deduct)。
        locked = (
            db.query(FundPool)
            .filter(FundPool.id == fund_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if locked is None:
            raise HTTPException(status_code=404, detail="资金账户不存在")
        fund = locked
        balance_before = (fund.balance or Decimal("0.00")).quantize(Decimal("0.01"))
        balance_after = Decimal(str(data.balance)).quantize(Decimal("0.01"))
        fund.balance = balance_after
        if balance_after != balance_before:
            _record_txn(
                db, fund.id,
                FundTransactionType.RECHARGE if balance_after > balance_before else FundTransactionType.CONSUME,
                amount=abs(balance_after - balance_before),
                balance_before=balance_before,
                balance_after=balance_after,
                operator=current_user.username,
            )
    if data.status is not None:
        fund.status = _resolve_status(data.status, fund.status)
    if data.bank_name is not None:
        fund.bank_name = data.bank_name
    if data.bank_account is not None:
        fund.bank_account = data.bank_account
    if data.currency is not None:
        fund.currency = data.currency
    if data.description is not None:
        fund.description = data.description

    db.commit()
    db.refresh(fund)
    return success_response(_fund_to_dict(fund), message="资金账户更新成功")


@router.delete("/{fund_id}", summary="删除企业资金账户")
def delete_fund(
    fund_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除资金账户。仅零余额且零流水的干净账户可删, 保护审计账本 (卡 971fb88b)。"""
    fund = _get_or_404(db, fund_id)
    if fund.enterprise_id is not None:
        assert_enterprise_team_access(db, fund.enterprise_id, current_user)

    # 账本完整性优先 (对齐 delete_enterprise 卡 21205721): 存在流水或非零余额
    # 时拒绝删除, 避免 ORM cascade 静默清空审计流水
    txn_count = (
        db.query(FundPoolTransaction)
        .filter(FundPoolTransaction.fund_pool_id == fund_id)
        .count()
    )
    if (fund.balance or Decimal("0.00")) != Decimal("0.00"):
        raise HTTPException(
            status_code=409,
            detail="该资金账户余额非零，禁止删除；请先将余额清零",
        )
    if txn_count > 0:
        raise HTTPException(
            status_code=409,
            detail="该资金账户存在交易流水，禁止删除；请先完成对账清算",
        )

    db.delete(fund)
    db.commit()
    return action_response(message="资金账户删除成功")


@router.get("/{fund_id}/transactions", summary="获取资金账户交易流水")
def list_fund_transactions(
    fund_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取资金账户的流水列表, 按 id 倒序分页 (卡 971fb88b)。"""
    fund = _get_or_404(db, fund_id)
    if fund.enterprise_id is not None:
        assert_enterprise_team_access(db, fund.enterprise_id, current_user)

    query = db.query(FundPoolTransaction).filter(
        FundPoolTransaction.fund_pool_id == fund_id
    )
    total = query.count()
    items = (
        query.order_by(FundPoolTransaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response(
        items=[_txn_to_dict(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )

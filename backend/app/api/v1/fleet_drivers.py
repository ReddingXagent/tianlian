"""
车队司机管理 API - Phase44 司机管理

功能:
- GET    /api/v1/fleet/drivers               —— 司机列表（支持企业过滤）
- POST   /api/v1/fleet/drivers               —— 创建司机
- GET    /api/v1/fleet/drivers/{driver_id}   —— 司机详情
- PUT    /api/v1/fleet/drivers/{driver_id}   —— 更新司机
- DELETE /api/v1/fleet/drivers/{driver_id}   —— 删除司机
- GET    /api/v1/fleet/drivers/{driver_id}/account          —— 账户信息
- POST   /api/v1/fleet/drivers/{driver_id}/account/recharge —— 账户充值
- GET    /api/v1/fleet/drivers/{driver_id}/transactions     —— 交易流水
- POST   /api/v1/fleet/drivers/{driver_id}/transactions     —— 创建交易（消费/退款）
"""
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.core.database import get_db
from app.core.iso_utils import parse_iso8601_or_400
from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import require_role, get_current_user
from app.models.enterprise import Enterprise
from app.core.response import success_response, paginated_response, action_response
from app.models.fleet_driver import (
    FleetDriver, FleetDriverAccount, FleetDriverTransaction,
    DriverStatus, LicenseType, AccountStatus, DriverTransactionType,
)
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_role("admin", "operator"))])


# ========== Schemas ==========

class DriverCreateRequest(BaseModel):
    enterprise_id: int
    name: str = Field(..., max_length=100)
    phone: str
    license_no: str = Field(..., max_length=50)
    license_type: str = "C1"
    assigned_vehicle_id: Optional[int] = None
    hire_date: Optional[str] = None  # ISO date string


class DriverUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = None
    license_no: Optional[str] = None
    license_type: Optional[str] = None
    assigned_vehicle_id: Optional[int] = None
    hire_date: Optional[str] = None
    status: Optional[Literal["active", "inactive", "suspended", "terminated"]] = None


class AccountRechargeRequest(BaseModel):
    amount: float = Field(..., ge=0)
    remark: Optional[str] = None


class TransactionCreateRequest(BaseModel):
    type: Literal["consume", "refund"]  # 充值走专用 recharge 接口
    amount: float = Field(..., ge=0)
    related_order_id: Optional[str] = None
    remark: Optional[str] = None


# ========== Helpers ==========

def _driver_to_dict(d: FleetDriver, include_account: bool = False) -> dict:
    data = {
        "id": d.id,
        "enterprise_id": d.enterprise_id,
        "name": d.name,
        "phone": d.phone,
        "license_no": d.license_no,
        "license_type": d.license_type.value if d.license_type else "C1",
        "assigned_vehicle_id": d.assigned_vehicle_id,
        "hire_date": d.hire_date.isoformat() if d.hire_date else None,
        "status": d.status.value if d.status else "active",
        "total_charge_kwh": float(d.total_charge_kwh) if d.total_charge_kwh else 0.0,
        "total_spent": float(d.total_spent) if d.total_spent else 0.0,
        "rating": float(d.rating) if d.rating else 5.0,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }
    if include_account and d.account:
        data["account"] = _account_to_dict(d.account)
    return data


def _account_to_dict(a: FleetDriverAccount) -> dict:
    return {
        "id": a.id,
        "driver_id": a.driver_id,
        "balance": float(a.balance) if a.balance else 0.0,
        "status": a.status.value if a.status else "active",
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _tx_to_dict(tx: FleetDriverTransaction) -> dict:
    return {
        "id": tx.id,
        "account_id": tx.account_id,
        "type": tx.type.value if tx.type else None,
        "amount": float(tx.amount) if tx.amount else 0.0,
        "balance_after": float(tx.balance_after) if tx.balance_after else 0.0,
        "related_order_id": tx.related_order_id,
        "remark": tx.remark,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


def _get_or_404(db: Session, driver_id: int) -> FleetDriver:
    driver = db.query(FleetDriver).filter(FleetDriver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="司机不存在")
    return driver


def _ensure_account(db: Session, driver: FleetDriver) -> FleetDriverAccount:
    """获取司机账户，如果不存在则自动创建"""
    if not driver.account:
        account = FleetDriverAccount(
            driver_id=driver.id,
            balance=Decimal("0.00"),
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        db.commit()
        db.refresh(driver)
    return driver.account


def _lock_account(db: Session, account_id: int) -> FleetDriverAccount:
    """行锁获取账户并刷新快照（卡 0020305d 并发竞态加固）。

    余额读改写必须经 with_for_update() 行锁后基于最新值计算（对照基准
    enterprise_balance_service.deduct_on_order_complete）；populate_existing
    强制重发 SELECT 刷新 session 内陈旧 identity-map 快照，杜绝
    并发事务早先读过的旧余额参与计算（丢更新/双花透支）。
    SQLite 下 with_for_update 为 no-op，靠 populate_existing 的强制重读
    保证快照新鲜。
    """
    return (
        db.query(FleetDriverAccount)
        .filter(FleetDriverAccount.id == account_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def _lock_driver(db: Session, driver_id: int) -> FleetDriver:
    """行锁获取司机并刷新快照（total_spent 累加同窗口丢更新，卡 0020305d）。"""
    return (
        db.query(FleetDriver)
        .filter(FleetDriver.id == driver_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


# ========== API Endpoints ==========

@router.get("", summary="获取司机列表")
def list_drivers(
    enterprise_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取车队司机列表，支持按企业过滤 (卡 45166947: 缺省时 team 兜底过滤)"""
    query = db.query(FleetDriver)
    scope = team_scope(current_user)
    if scope is not None:
        # 团队级用户缺省 enterprise_id 时按企业归属 team 兜底过滤, 杜绝全表裸查越权
        query = query.join(Enterprise, Enterprise.id == FleetDriver.enterprise_id).filter(
            Enterprise.owner_team_id == scope
        )
    if enterprise_id is not None:
        assert_enterprise_team_access(db, enterprise_id, current_user)
        query = query.filter(FleetDriver.enterprise_id == enterprise_id)

    total = query.count()
    items = query.order_by(FleetDriver.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return paginated_response(
        items=[_driver_to_dict(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", summary="创建司机")
def create_driver(
    data: DriverCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建车队司机，同时自动创建司机账户"""
    assert_enterprise_team_access(db, data.enterprise_id, current_user)

    # 校验驾照类型
    try:
        license_type = LicenseType(data.license_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的驾照类型: {data.license_type}")

    # 检查驾驶证号唯一性
    existing = db.query(FleetDriver).filter(
        FleetDriver.license_no == data.license_no
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"驾驶证号 {data.license_no} 已存在")

    # 解析入职日期
    hire_date = None
    if data.hire_date:
        hire_date = parse_iso8601_or_400(data.hire_date, "hire_date 格式无效，需 ISO 8601")

    driver = FleetDriver(
        enterprise_id=data.enterprise_id,
        name=data.name,
        phone=data.phone,
        license_no=data.license_no,
        license_type=license_type,
        assigned_vehicle_id=data.assigned_vehicle_id,
        hire_date=hire_date,
        status=DriverStatus.ACTIVE,
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)

    # 自动创建司机账户
    account = FleetDriverAccount(
        driver_id=driver.id,
        balance=Decimal("0.00"),
        status=AccountStatus.ACTIVE,
    )
    db.add(account)
    db.commit()
    db.refresh(driver)

    return success_response(_driver_to_dict(driver, include_account=True), message="司机创建成功")


@router.get("/{driver_id}", summary="获取司机详情")
def get_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取司机详细信息"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)
    return success_response(_driver_to_dict(driver, include_account=True))


@router.put("/{driver_id}", summary="更新司机信息")
def update_driver(
    driver_id: int,
    data: DriverUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新司机信息"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)

    if data.name is not None:
        driver.name = data.name
    if data.phone is not None:
        driver.phone = data.phone
    if data.license_no is not None:
        # 检查唯一性
        dup = db.query(FleetDriver).filter(
            FleetDriver.license_no == data.license_no,
            FleetDriver.id != driver_id,
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"驾驶证号 {data.license_no} 已存在")
        driver.license_no = data.license_no
    if data.license_type is not None:
        try:
            driver.license_type = LicenseType(data.license_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的驾照类型: {data.license_type}")
    if data.assigned_vehicle_id is not None:
        driver.assigned_vehicle_id = data.assigned_vehicle_id
    if data.hire_date is not None:
        driver.hire_date = parse_iso8601_or_400(data.hire_date, "hire_date 格式无效，需 ISO 8601")
    if data.status is not None:
        try:
            driver.status = DriverStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {data.status}")

    db.commit()
    db.refresh(driver)
    return success_response(_driver_to_dict(driver, include_account=True), message="司机信息更新成功")


@router.delete("/{driver_id}", summary="删除司机")
def delete_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除司机。仅零余额且零流水的干净司机可删, 保护审计账本 (卡 97a891bc)。"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)

    # 账本完整性优先 (对齐 delete_fund 卡 971fb88b): 存在余额或流水时拒绝删除,
    # 避免 ORM cascade 静默清空账户余额与 FleetDriverTransaction 审计流水
    account = driver.account
    if account is not None:
        if (account.balance or Decimal("0.00")) > Decimal("0.00"):
            raise HTTPException(
                status_code=409,
                detail="该司机账户余额非零，禁止删除；请先将余额清零",
            )
        txn_count = (
            db.query(FleetDriverTransaction)
            .filter(FleetDriverTransaction.account_id == account.id)
            .count()
        )
        if txn_count > 0:
            raise HTTPException(
                status_code=409,
                detail="该司机存在账户交易流水，禁止删除；请先完成对账清算",
            )
    # 卡 97a891bc 同族：考勤 driver_id NOT NULL 无 ondelete，删司机前显式清理
    from app.services.fk_cascade import purge_driver_children
    purge_driver_children(db, driver_id)

    db.delete(driver)
    db.commit()
    return action_response(message="司机删除成功")


# ========== 账户管理 ==========

@router.get("/{driver_id}/account", summary="获取司机账户信息")
def get_driver_account(
    driver_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取司机个人账户信息"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)
    account = _ensure_account(db, driver)
    return success_response(_account_to_dict(account))


@router.post("/{driver_id}/account/recharge", summary="司机账户充值")
def recharge_account(
    driver_id: int,
    data: AccountRechargeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """司机账户充值"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)
    account = _ensure_account(db, driver)

    if account.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="账户已被冻结或关闭，无法充值")

    amount = Decimal(str(data.amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于0")

    # 卡0020305d: 行锁+刷新快照后基于最新余额累加, 封堵并发充值丢更新
    account = _lock_account(db, account.id)
    new_balance = (account.balance or Decimal("0.00")) + amount
    account.balance = new_balance

    tx = FleetDriverTransaction(
        account_id=account.id,
        type=DriverTransactionType.RECHARGE,
        amount=amount,
        balance_after=new_balance,
        remark=data.remark or "账户充值",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    return success_response(_tx_to_dict(tx), message="充值成功")


# ========== 交易管理 ==========

@router.get("/{driver_id}/transactions", summary="获取司机交易流水")
def list_driver_transactions(
    driver_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取司机账户的交易流水列表"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)
    account = _ensure_account(db, driver)

    query = db.query(FleetDriverTransaction).filter(
        FleetDriverTransaction.account_id == account.id
    )
    total = query.count()
    items = query.order_by(FleetDriverTransaction.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return paginated_response(
        items=[_tx_to_dict(tx) for tx in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{driver_id}/transactions", summary="创建司机交易")
def create_driver_transaction(
    driver_id: int,
    data: TransactionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建司机交易（消费/退款），自动更新余额"""
    driver = _get_or_404(db, driver_id)
    assert_enterprise_team_access(db, driver.enterprise_id, current_user)
    account = _ensure_account(db, driver)

    if account.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="账户已被冻结或关闭，无法交易")

    if data.type not in ("consume", "refund"):
        raise HTTPException(status_code=400, detail="仅支持 consume/refund 类型（充值请用 /account/recharge）")

    amount = Decimal(str(data.amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="交易金额必须大于0")

    # 卡0020305d: 行锁+刷新快照后持锁复查余额, 封堵检查-扣减 TOCTOU 双花
    account = _lock_account(db, account.id)
    current_balance = account.balance or Decimal("0.00")

    if data.type == "consume":
        new_balance = current_balance - amount
        if new_balance < 0:
            raise HTTPException(status_code=400, detail="余额不足")
    else:  # refund
        new_balance = current_balance + amount

    tx_type = DriverTransactionType(data.type)
    account.balance = new_balance

    tx = FleetDriverTransaction(
        account_id=account.id,
        type=tx_type,
        amount=amount,
        balance_after=new_balance,
        related_order_id=data.related_order_id,
        remark=data.remark,
    )
    db.add(tx)

    # 更新司机累计消费（卡0020305d: 行锁+刷新快照, 同窗口内更新封堵丢更新）
    if data.type == "consume":
        driver = _lock_driver(db, driver_id)
        driver.total_spent = (driver.total_spent or Decimal("0.00")) + amount

    db.commit()
    db.refresh(tx)

    return success_response(_tx_to_dict(tx), message=f"{data.type} 交易创建成功")

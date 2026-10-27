"""
企业充值审批 API - 运营+车队管理
POST /api/v1/operate/recharge/apply - 创建充值申请
PUT /api/v1/operate/recharge/{id}/approve - 审批通过
PUT /api/v1/operate/recharge/{id}/reject - 审批拒绝
GET /api/v1/operate/recharge/applications - 获取申请列表
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.database import get_db
from app.core.response import success_response
from app.models.enterprise_recharge import RechargeApplication, RechargeStatus
from app.models.enterprise import Enterprise
from app.core.security import get_current_admin
from app.core.permissions import admin_required
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


class RechargeApplicationCreate(BaseModel):
    enterprise_id: int = Field(..., description="企业ID")
    amount: Decimal = Field(..., gt=0, description="申请金额(元), 必须大于0")
    remark: Optional[str] = Field(None, description="备注")
    applicant: Optional[str] = Field(None, description="申请人")

    @property
    def base_fields(self):
        return ["enterprise_id", "amount", "remark", "applicant"]


class RechargeApplicationApprove(BaseModel):
    # 审批人由 current_user 提供, 不再要求客户端传入(原 approver 为死参数, 卡 0228ac86 BUG5)。
    reason: Optional[str] = Field(None, description="审批理由或拒绝原因")


class RechargeApplicationResponse(RechargeApplicationCreate):
    id: int
    status: RechargeStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


@router.get("/recharge/applications", summary="企业充值申请列表")
def list_recharge_applications(
    status: Optional[str] = Query(None, description="过滤状态: pending/approved/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取充值申请（admin 全可见；团队级仅本 team 企业）"""
    try:
        query = db.query(RechargeApplication)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 企业的申请（经 enterprise→owner_team）。
        if not is_platform_admin(user):
            query = query.join(Enterprise, RechargeApplication.enterprise_id == Enterprise.id) \
                         .filter(Enterprise.owner_team_id == user.team_id)
        if status:
            query = query.filter(RechargeApplication.status == status)

        total = query.count()
        # status 过滤已在上方 query 上叠加；此处仅分页 + 序列化为 dict。
        # 原 bug [2fb8594a]：上方已分页，下方又用无分页 query.all() 覆盖 → 分页失效；
        # 且 items 为 ORM 对象直接进响应 → 隐式序列化（历史曾 500、泄漏内部状态）。
        items = query.order_by(RechargeApplication.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
    except Exception as e:
        logger.error("查询企业充值申请列表失败: %s", e)
        raise HTTPException(status_code=500, detail="查询申请列表失败, 请稍后重试")

    return success_response({
        "items": [a.to_dict() for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/recharge/apply", status_code=status.HTTP_201_CREATED, summary="提交充值申请")
def create_recharge_application(
    data: RechargeApplicationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    """提交企业充值申请"""
    try:
        # 创建申请记录
        application = RechargeApplication(
            status=RechargeStatus.PENDING,
            applicant=current_user.username,
            created_at=datetime.now(timezone.utc)
        )

        # 设置传入参数
        application.enterprise_id = data.enterprise_id
        application.amount = data.amount
        application.remark = data.remark or ""
        application.applicant = current_user.username

        db.add(application)
        db.commit()
        db.refresh(application)
    except Exception as e:
        db.rollback()
        logger.error("提交企业充值申请失败(enterprise_id=%s): %s", data.enterprise_id, e)
        raise HTTPException(status_code=500, detail="提交充值申请失败, 请稍后重试")

    return success_response({
        "id": application.id,
        "message": "充值申请已提交，等待审批",
        "status": "pending",
        "application_id": application.id
    })


@router.put("/recharge/{id}/approve", status_code=status.HTTP_200_OK, summary="审批通过")
@admin_required
def approve_recharge(
    id: int,
    data: RechargeApplicationApprove,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    """审批通过

    财务安全(BUG1, 卡 0228ac86): 申请状态变更与企业余额更新绑定在同一事务内单次 commit,
    消除旧代码"先 commit 申请 APPROVED 再更新余额"两次 commit 间崩溃导致的不一致中间态;
    企业行加 with_for_update() 行锁(PG 生效, SQLite no-op)防并发 lost update。
    """
    # 卡601149f8: 申请行加 with_for_update() 行锁(PG 防并发双审批——两个审批并发均过
    # PENDING 检查导致同一笔申请双重入账, 企业行锁只保证余额算术串行不防重复入账;
    # SQLite no-op, 由下方 status != PENDING 校验兜底)。范式照抄 order_fees.complete_refund 卡aa88371f。
    application = db.query(RechargeApplication).filter_by(id=id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在")

    if application.status != RechargeStatus.PENDING:
        raise HTTPException(status_code=400, detail="只能审批待审批的申请")

    try:
        # BUG6: 审批理由写独立字段 approve_reason, 不覆盖申请人 remark
        application.status = RechargeStatus.APPROVED
        application.approver = current_user.username
        application.updated_at = datetime.now(timezone.utc)
        reason = (data.reason or "").strip()
        application.approve_reason = reason or None

        # BUG1: 企业行加行锁(PG 生效), 与申请状态同事务
        enterprise = db.query(Enterprise).filter_by(id=application.enterprise_id).with_for_update().first()
        # BUG3: enterprise 不存在显式报错(旧代码静默吞, 返回成功但余额未更新)
        if not enterprise:
            db.rollback()
            logger.error("充值申请 %s 关联的企业 %s 不存在, 无法充值", id, application.enterprise_id)
            raise HTTPException(status_code=500, detail="申请关联的企业账户不存在, 无法完成充值")

        # BUG1: 余额更新与申请状态在同一事务单次 commit (精度 quantize 0.01)
        current_balance = Decimal(str(enterprise.balance or 0))
        enterprise.balance = (current_balance + Decimal(str(application.amount))).quantize(Decimal("0.01"))

        db.commit()
        db.refresh(application)
        db.refresh(enterprise)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("审批通过充值申请 %s 失败: %s", id, e)
        raise HTTPException(status_code=500, detail="审批处理失败, 请稍后重试")

    return success_response("审批通过")


@router.put("/recharge/{id}/reject", status_code=status.HTTP_200_OK, summary="审批拒绝")
@admin_required
def reject_recharge(
    id: int,
    data: RechargeApplicationApprove,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin)
):
    """审批拒绝"""
    # 卡dcdf24d1: 申请行加 with_for_update() 行锁(PG 防并发 approve/reject 竞态——
    # 无锁读可基于 PENDING 旧快照通过校验, 在 approve 提交(APPROVED+余额入账)后
    # 把终态覆盖为 REJECTED, 造成"已拒绝但钱已入账"的对账不一致;
    # SQLite no-op, 由下方 status != PENDING 校验兜底)。范式照抄同文件 approve_recharge 卡601149f8。
    application = db.query(RechargeApplication).filter_by(id=id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在")

    if application.status != RechargeStatus.PENDING:
        raise HTTPException(status_code=400, detail="只能审批待审批的申请")

    try:
        # 更新状态
        application.status = RechargeStatus.REJECTED
        application.approver = current_user.username
        application.updated_at = datetime.now(timezone.utc)
        reason = (data.reason or "").strip()
        if application.reject_reason:
            application.reject_reason += f" [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}] {reason}"
        else:
            application.reject_reason = reason or None

        db.commit()
        db.refresh(application)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("审批拒绝充值申请 %s 失败: %s", id, e)
        raise HTTPException(status_code=500, detail="审批处理失败, 请稍后重试")

    return success_response("审批拒绝")

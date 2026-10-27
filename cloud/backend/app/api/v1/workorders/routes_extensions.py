"""工单扩展端点 — 签到 / 支援 / 备件 / 评价 / 一站式验收
(从原 workorders.py 拆出, 卡 1ed83abf)。team scoping (任务卡 ed509541) 原样保留。
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.spare_part import SparePartInventory
from app.models.user import User
from app.models.workorder import (
    WorkOrder,
    WorkOrderCheckin,
    WorkOrderLog,
    WorkOrderRating,
    WorkOrderSparePart,
    WorkOrderStatus,
    WorkOrderSupportRequest,
)
from app.services.audit_service import audit_service

from .helpers import _broadcast_wo, _check_workorder_team, _serialize_rating
from .router import router
from .schemas import (
    WorkOrderAcceptanceSchema,
    WorkOrderCheckinSchema,
    WorkOrderRateSchema,
    WorkOrderSparePartSchema,
    WorkOrderSupportSchema,
    _ACTIVE_STATUSES,
    _DONE_STATUSES,
)


# ========== 扩展端点：签到 / 支援 / 备件 / 评价 ==========

@router.post("/{workorder_id}/checkin")
def checkin_workorder(workorder_id: str, data: WorkOrderCheckinSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """到场签到 — GPS 坐标 + 照片URL + 备注（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    if order.status not in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=f"工单当前状态不允许签到: {order.status.value}")

    rec = WorkOrderCheckin(
        order_id=order.id,
        latitude=data.latitude, longitude=data.longitude,
        address=data.address, note=data.note, photo_url=data.photo_url,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return success_response({
        "id": rec.id, "order_id": rec.order_id,
        "latitude": rec.latitude, "longitude": rec.longitude,
        "address": rec.address, "note": rec.note, "photo_url": rec.photo_url,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }, message="签到成功")


@router.post("/{workorder_id}/support")
def support_workorder(workorder_id: str, data: WorkOrderSupportSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """申请支援 — 远程协助 / 高级工程师协助（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    if order.status not in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=f"工单当前状态不允许申请支援: {order.status.value}")

    rec = WorkOrderSupportRequest(
        order_id=order.id,
        target_engineer_id=data.target_engineer_id,
        reason=data.reason, remote=data.remote,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return success_response({
        "id": rec.id, "order_id": rec.order_id,
        "target_engineer_id": rec.target_engineer_id,
        "reason": rec.reason, "remote": rec.remote, "status": rec.status,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }, message="支援请求已提交")


@router.post("/{workorder_id}/spare-parts")
def spare_parts_workorder(workorder_id: str, data: WorkOrderSparePartSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """申请/记录备件 — 名称/型号/数量/说明

    库存联动 (maint-spec §2.2): 按 (part_name, part_model) 匹配 spare_parts_inventory，
    命中则扣减 available_quantity；可用量不足返回 409；未登记的备件放行（仅记录领用）。
    team scoping（任务卡 ed509541）：跨团队 → 404。
    """
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    if order.status not in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=f"工单当前状态不允许申请备件: {order.status.value}")

    # 库存联动: 命中台账则扣减，不足则阻断；未登记备件放行
    # 行锁+持锁复查 (卡 78bffa57): 扣减与 spare_parts outbound 同一竞态,
    # with_for_update() + populate_existing() 防并发超扣/丢更新
    # (SQLite 下 no-op, 对照 spare_parts._lock_part_or_404)。
    inv = (
        db.query(SparePartInventory)
        .filter(
            SparePartInventory.part_name == data.part_name,
            SparePartInventory.part_model == data.part_model,
        )
        .with_for_update()
        .populate_existing()
        .first()
    )
    if inv:
        if (inv.available_quantity or 0) < data.quantity:
            raise HTTPException(
                status_code=409,
                detail=(f"库存不足: {data.part_name}({data.part_model}) "
                        f"当前可用 {inv.available_quantity}, 需 {data.quantity}"),
            )
        inv.available_quantity = inv.available_quantity - data.quantity

    rec = WorkOrderSparePart(
        order_id=order.id,
        part_name=data.part_name, part_model=data.part_model,
        quantity=data.quantity, reason=data.reason,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return success_response({
        "id": rec.id, "order_id": rec.order_id,
        "part_name": rec.part_name, "part_model": rec.part_model,
        "quantity": rec.quantity, "reason": rec.reason, "status": rec.status,
        "inventory_deducted": inv is not None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }, message="备件申请已提交")


@router.post("/{workorder_id}/rate")
def rate_workorder(workorder_id: str, data: WorkOrderRateSchema, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """验收评价 — 响应速度/维修质量/服务态度 三维星级 + 评语（仅已完成工单可评价，且每单一次；team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, current_user)
    if order.status not in _DONE_STATUSES:
        raise HTTPException(status_code=409, detail=f"工单未完成，暂不可评价: {order.status.value}")

    rec = WorkOrderRating(
        order_id=order.id,
        response_rating=data.response_rating,
        quality_rating=data.quality_rating,
        attitude_rating=data.attitude_rating,
        comment=data.comment,
        user_id=current_user.id,  # 记录评价人(maint-spec §2.2)
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该工单已评价，不可重复评价")
    db.refresh(rec)
    avg = round((rec.response_rating + rec.quality_rating + rec.attitude_rating) / 3, 2)
    return success_response({
        "id": rec.id, "order_id": rec.order_id,
        "response_rating": rec.response_rating,
        "quality_rating": rec.quality_rating,
        "attitude_rating": rec.attitude_rating,
        "average_rating": avg,
        "comment": rec.comment,
        "user_id": rec.user_id,
        "verifier_id": rec.verifier_id,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }, message="评价已提交")


# ========== 验收记录：一站式验收 + 查询 ==========

@router.get("/{workorder_id}/acceptance")
def get_workorder_acceptance(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """查询验收+评价记录（合并 verify 信息 + rating）— maint-spec §2.2（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    rating = db.query(WorkOrderRating).filter(WorkOrderRating.order_id == order.id).first()
    return success_response({
        "verify": {
            "verifier_id": order.verifier_id,
            "verify_time": order.verify_time.isoformat() if order.verify_time else None,
            "status": order.status.value if order.status else None,
        },
        "rating": _serialize_rating(rating) if rating else None,
    })


@router.post("/{workorder_id}/acceptance")
def submit_workorder_acceptance(
    workorder_id: str,
    data: WorkOrderAcceptanceSchema,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """站长一站式验收 — 提交评分+评语，同时完成验收状态变更(maint-spec §2.2)。

    - reject=False(默认): 验收通过 → status=completed + verify_time + 创建评分记录
    - reject=True: 驳回回退 → status=processing，不创建评分
    仅 PENDING_VERIFY 工单可执行；向后兼容独立 /verify /rate 端点。
    team scoping（任务卡 ed509541）：跨团队 → 404。
    """
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, current_user)
    if order.status != WorkOrderStatus.PENDING_VERIFY:
        raise HTTPException(status_code=400, detail=f"工单当前不允许验收: {order.status.value}")

    uid = current_user.id
    order.verifier_id = uid
    order.update_time = datetime.now(timezone.utc)

    # 驳回：回退到处理中，不创建评分
    if data.reject:
        order.status = WorkOrderStatus.PROCESSING
        db.commit()
        db.refresh(order)
        db.add(WorkOrderLog(
            order_id=str(order.id), action='rejected', user_id=uid,
            description=f"站长验收驳回: {data.comment or ''}",
        ))
        db.commit()
        try:
            audit_service.log_crud(
                user_id=uid, username=current_user.username,
                action="update", module="workorders",
                target_id=workorder_id, target_desc=f"验收驳回:工单{workorder_id}",
            )
        except Exception:
            pass
        _broadcast_wo(db, 'rejected', {'id': order.id, 'status': 'processing', 'reason': data.comment or ''})
        return success_response({
            'status': order.status.value,
            'verifier_id': order.verifier_id,
            'rating': None,
        }, message='验收已驳回')

    # 通过：进入已完成 + 创建评分
    order.status = WorkOrderStatus.COMPLETED
    order.verify_time = datetime.now(timezone.utc)
    rec = WorkOrderRating(
        order_id=order.id,
        response_rating=data.response_rating,
        quality_rating=data.quality_rating,
        attitude_rating=data.attitude_rating,
        comment=data.comment,
        user_id=uid,            # 评价人
        verifier_id=uid,        # 验收人
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该工单已评价，不可重复评价")
    db.refresh(order)
    db.refresh(rec)
    db.add(WorkOrderLog(
        order_id=str(order.id), action='verified', user_id=uid,
        description="站长验收通过并评价",
    ))
    db.commit()
    try:
        audit_service.log_crud(
            user_id=uid, username=current_user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"验收通过并评价:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'verified', {'id': order.id, 'status': 'completed'})
    return success_response({
        'status': order.status.value,
        'verify_time': order.verify_time.isoformat() if order.verify_time else None,
        'verifier_id': order.verifier_id,
        'rating': _serialize_rating(rec),
    }, message='验收完成')

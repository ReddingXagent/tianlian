"""
车队概览 API - Phase43 车队管理

功能:
- GET /api/v1/fleet/overview?enterprise_id=1 —— 车队概览
  包含: 企业信息(含信用额度) / 车辆总数 / 车辆状态分布 / 累计充电 / 累计消费 /
        V2G总收益 / 碳减排总量 / 最近交易
"""
import logging
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.enterprise_transaction import EnterpriseTransaction
from app.models.fleet_v2g import FleetV2GRevenue
from app.models.carbon_emission import CarbonReductionRecord
from app.models.user import User
from app.services.enterprise_balance_service import get_low_balance_enterprises

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/overview", summary="车队概览")
def fleet_overview(
    enterprise_id: int = Query(..., description="企业ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取车队概览数据"""
    try:
        enterprise = assert_enterprise_team_access(db, enterprise_id, current_user)

        # ─── 车辆统计 ───
        total_vehicles = db.query(func.count(EnterpriseVehicle.id)).filter(
            EnterpriseVehicle.enterprise_id == enterprise_id
        ).scalar() or 0

        # 车辆状态分布（按 EnterpriseVehicleStatus 分组计数）
        status_rows = db.query(
            EnterpriseVehicle.status,
            func.count(EnterpriseVehicle.id),
        ).filter(
            EnterpriseVehicle.enterprise_id == enterprise_id
        ).group_by(EnterpriseVehicle.status).all()

        vehicle_status_distribution = {}
        for status_val, count in status_rows:
            key = status_val.value if hasattr(status_val, "value") else str(status_val)
            vehicle_status_distribution[key] = count

        # ─── 累计充电度数 / 消费金额 ───
        total_charged_kwh = db.query(
            func.coalesce(func.sum(EnterpriseTransaction.amount), 0)
        ).filter(
            EnterpriseTransaction.enterprise_id == enterprise_id,
            EnterpriseTransaction.type == "consume"
        ).scalar() or Decimal("0")

        total_spent = float(total_charged_kwh)

        # ─── V2G 总收益 ───
        total_v2g_revenue = db.query(
            func.coalesce(func.sum(FleetV2GRevenue.total_revenue), 0)
        ).filter(
            FleetV2GRevenue.enterprise_id == enterprise_id
        ).scalar() or Decimal("0")

        # ─── 碳减排总量 (kgCO2) ───
        total_carbon_reduction_kg = db.query(
            func.coalesce(func.sum(CarbonReductionRecord.carbon_reduction_kg), 0)
        ).filter(
            CarbonReductionRecord.enterprise_id == enterprise_id
        ).scalar() or Decimal("0")

        # ─── 最近交易 ───
        recent_transactions = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.enterprise_id == enterprise_id
        ).order_by(EnterpriseTransaction.id.desc()).limit(5).all()

        def _tx_to_dict(tx):
            return {
                "id": tx.id,
                "type": tx.type.value if tx.type else None,
                "amount": float(tx.amount) if tx.amount else 0,
                "balance_after": float(tx.balance_after) if tx.balance_after else 0,
                "order_id": tx.order_id,
                "remark": tx.remark,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }

        # ─── 信用额度 & 余额 ───
        credit_limit = float(enterprise.credit_limit) if enterprise.credit_limit else 0.0
        balance = float(enterprise.balance) if enterprise.balance else 0.0

        return success_response({
            "enterprise": {
                "id": enterprise.id,
                "name": enterprise.name,
                "code": enterprise.code,
                "balance": balance,
                "credit_limit": credit_limit,
                "credit_balance": balance + credit_limit,  # 可用额度 = 余额 + 信用额度
                "status": enterprise.status.value if enterprise.status else "active",
            },
            "total_vehicles": total_vehicles,
            "vehicle_status_distribution": vehicle_status_distribution,
            "total_charged_kwh": float(total_charged_kwh),
            "total_spent": total_spent,
            "total_v2g_revenue": float(total_v2g_revenue),
            "total_carbon_reduction_kg": float(total_carbon_reduction_kg),
            "recent_transactions": [_tx_to_dict(tx) for tx in recent_transactions],
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("fleet_overview 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/balance-warning", summary="低余额车队清单")
def fleet_balance_warning(
    threshold: Optional[float] = Query(None, description="固定预警阈值(元)，不传则按各企业 credit_limit 判定"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取余额低于阈值的车队清单

    - 不传 threshold: 返回余额 < credit_limit 的企业（可用资金低于信用线）
    - 传 threshold: 返回余额 < threshold 的企业

    每条记录包含: id, name, code, balance, credit_limit, available_balance
    按余额升序排列。
    """
    try:
        thresh = Decimal(str(threshold)) if threshold is not None else None
        items = get_low_balance_enterprises(
            db, threshold=thresh, team_id=team_scope(current_user)
        )
        return success_response({
            "items": items,
            "total": len(items),
            "threshold": threshold,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("fleet_balance_warning 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

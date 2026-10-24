"""卡 089b01b2 — C端积分薄路由 (端侧路径, 无 /business 前缀).

- GET /points  当前用户积分余额 + 最近记录

鉴权: get_current_end_user; 运营 token / 匿名 → 401.
余额: 最新 PointsRecord.balance_after (无记录 → 0); 记录按时间倒序.
"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.business_end_user_auth import get_current_end_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.end_user import EndUser
from app.models.points import PointsRecord
from app.services.wx_pay import response as rsp

router = APIRouter()


def _record_to_dict(r: PointsRecord) -> dict:
    return {
        "record_id": r.id,
        "record_type": r.record_type.value if r.record_type else None,
        "points": r.points,
        "balance_after": r.balance_after,
        "description": r.description,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/points", summary="积分余额与记录 (端侧)")
@limiter.limit("60/minute")
def list_points(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """余额取最新一条 balance_after; 记录按 created_at 倒序 (同刻 id 兜底).
    分页口径同契约 §8.6 vehicles: page 默认1, page_size 默认20 最大100."""
    query = db.query(PointsRecord).filter(PointsRecord.user_id == end_user.id)
    total = query.count()
    latest = (
        db.query(PointsRecord)
        .filter(PointsRecord.user_id == end_user.id)
        .order_by(PointsRecord.id.desc())
        .first()
    )
    balance = latest.balance_after if latest is not None else 0
    records = (
        query.order_by(PointsRecord.created_at.desc(), PointsRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rsp.ok({
        "balance": balance,
        "records": [_record_to_dict(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    })

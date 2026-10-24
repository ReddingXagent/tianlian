"""C端用户收藏场站 API (用户端契约§8 P2 §8.7, 卡 36396f29).

挂 /business 前缀:
- GET    /business/favorites                    收藏列表 (含场站摘要, 分页, 新收藏在前)
- POST   /business/favorites                    收藏 (幂等: 已收藏返回 already=true + 原 favorite_id)
- DELETE /business/favorites/{station_id}       取消收藏 (幂等: 本就没有返回 deleted=false)

认证/隔离: 同 §8.6 (get_current_end_user, 仅本人收藏可见)。
场站摘要参照契约§1 轻量字段; 场站被物理删除时 station=null (收藏行保留)。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.business import _safe_enum_val
from app.api.v1.business_end_user_auth import get_current_end_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.end_user import EndUser
from app.models.end_user_favorite import EndUserFavorite
from app.models.station import Station
from app.services.wx_pay import response as rsp

router = APIRouter()


class FavoriteCreateRequest(BaseModel):
    station_id: int


def _station_summary(station: Station) -> dict:
    """契约§8.7 场站摘要 (§1 轻量口径)."""
    return {
        "id": station.id,
        "name": station.name,
        "address": station.address,
        "city": station.city,
        "status": _safe_enum_val(station.status, "normal"),
        "total_power": station.total_power,
        "gun_count": station.gun_count,
    }


@router.get("/favorites", summary="收藏场站列表 (契约§8.7)")
@limiter.limit("60/minute")
def list_favorites(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    q = db.query(EndUserFavorite).filter(EndUserFavorite.end_user_id == end_user.id)
    total = q.count()
    favorites = (
        q.order_by(EndUserFavorite.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    station_map = {}
    station_ids = {f.station_id for f in favorites}
    if station_ids:
        for st in db.query(Station).filter(Station.id.in_(station_ids)).all():
            station_map[st.id] = st

    items = [
        {
            "favorite_id": f.id,
            "station_id": f.station_id,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "station": (
                _station_summary(station_map[f.station_id])
                if f.station_id in station_map
                else None
            ),
        }
        for f in favorites
    ]
    return rsp.ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/favorites", summary="收藏场站 (契约§8.7, 幂等)")
@limiter.limit("60/minute")
def create_favorite(
    request: Request,
    body: FavoriteCreateRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    if db.get(Station, body.station_id) is None:
        raise HTTPException(404, "场站不存在")

    favorite = (
        db.query(EndUserFavorite)
        .filter(
            EndUserFavorite.end_user_id == end_user.id,
            EndUserFavorite.station_id == body.station_id,
        )
        .first()
    )
    already = favorite is not None
    if not already:
        favorite = EndUserFavorite(
            end_user_id=end_user.id,
            station_id=body.station_id,
        )
        db.add(favorite)
        try:
            db.commit()
        except IntegrityError:
            # 并发双击竞态: 预检查漏检, INSERT 撞 uq_end_user_favorite_station
            # 兜底 (卡 d74344ed)。全 rollback 而非 savepoint (SQLite + pysqlite
            # 的 SAVEPOINT 在 IntegrityError 后状态清理不可靠), 回查取并发方
            # 落库的原收藏行 → 契约§8.7 幂等语义 already:true; 其他约束冲突
            # 仍走全局兜底不吞错。
            db.rollback()
            favorite = (
                db.query(EndUserFavorite)
                .filter(
                    EndUserFavorite.end_user_id == end_user.id,
                    EndUserFavorite.station_id == body.station_id,
                )
                .first()
            )
            if favorite is None:
                raise
            already = True
        else:
            db.refresh(favorite)

    return rsp.ok(
        {
            "favorite_id": favorite.id,
            "station_id": body.station_id,
            "already": already,
        }
    )


@router.delete("/favorites/{station_id}", summary="取消收藏 (契约§8.7, 幂等)")
@limiter.limit("60/minute")
def delete_favorite(
    request: Request,
    station_id: int,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    deleted = (
        db.query(EndUserFavorite)
        .filter(
            EndUserFavorite.end_user_id == end_user.id,
            EndUserFavorite.station_id == station_id,
        )
        .delete()
    )
    db.commit()
    return rsp.ok({"station_id": station_id, "deleted": bool(deleted)})

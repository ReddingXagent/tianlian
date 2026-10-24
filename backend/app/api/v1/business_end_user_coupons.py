"""卡 089b01b2 — C端优惠券薄路由 (端侧路径, 无 /business 前缀).

- GET  /coupons       可用券列表 (active + 在窗口 + 有库存)
- POST /coupons/claim  领取 (扣库存 + CouponUsage 落库)

鉴权: get_current_end_user; 运营 token / 匿名 → 401.
归属: CouponUsage.user_id == end_user.id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select as sqlalchemy_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.business_end_user_auth import get_current_end_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.coupon import Coupon, CouponStatus, CouponUsage
from app.models.end_user import EndUser
from app.services.wx_pay import response as rsp

router = APIRouter()


class ClaimRequest(BaseModel):
    coupon_id: int = Field(..., ge=1)


def _coupon_to_dict(c: Coupon) -> dict:
    return {
        "coupon_id": c.id,
        "name": c.name,
        "coupon_type": c.coupon_type.value if c.coupon_type else None,
        "face_value": float(c.face_value) if c.face_value is not None else None,
        "min_order_amount": (
            float(c.min_order_amount) if c.min_order_amount is not None else None
        ),
        "valid_days": c.valid_days,
    }


def _to_naive_utc(dt: datetime) -> datetime:
    """aware → naive UTC; naive 原样。兼容 SQLite 丢 tzinfo (生产 PG 保留 tz)。"""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


@router.get("/coupons", summary="可用优惠券列表 (端侧)")
@limiter.limit("60/minute")
def list_coupons(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """可用券: is_active + 当前在发放窗口 + 有库存 (契约 §8 口径).
    分页口径同契约 §8.6 vehicles: page 默认1, page_size 默认20 最大100."""
    now = datetime.now(timezone.utc)
    query = db.query(Coupon).filter(
        Coupon.is_active.is_(True),
        Coupon.start_time <= now,
        Coupon.end_time >= now,
        Coupon.remaining_stock > 0,
    )
    total = query.count()
    items = (
        query.order_by(Coupon.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rsp.ok({
        "items": [_coupon_to_dict(c) for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/coupons/claim", summary="领取优惠券 (端侧)")
@limiter.limit("60/minute")
def claim(
    request: Request,
    body: ClaimRequest,
    end_user: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """领取: 存在 → 404; 不可用(停用/越窗) → 409 NOT_AVAILABLE;
    超限领 → 409 LIMIT_REACHED; 无库存 → 409 OUT_OF_STOCK; 成功扣库存 + 落库.

    并发安全 (卡 6e698559): 券行 with_for_update() 行锁内完成
    per_user_limit 检查 + 库存 CAS 扣减 + insert (PG 下同券领取串行化)。
    SQLite 下行锁 no-op, 由库存 CAS 取得 RESERVED 写锁后的二次复检兜底:
    本会话持写锁后重查 ACTIVE 已领数, 必见并发方已提交的记录 → 409 不落库。"""
    coupon = _lock_coupon(db, body.coupon_id)
    if coupon is None:
        raise HTTPException(404, "COUPON_NOT_FOUND")

    now = datetime.now(timezone.utc)
    # 可用性: 启用 + 在发放窗口 (SQLite 读回 naive, 统一 naive UTC 比较)
    start = _to_naive_utc(coupon.start_time)
    end = _to_naive_utc(coupon.end_time)
    if not coupon.is_active or not (start <= _to_naive_utc(now) <= end):
        raise HTTPException(409, "COUPON_NOT_AVAILABLE")

    # 每人限领 (status=ACTIVE 的已领数)
    if coupon.per_user_limit is not None and (
        _active_claimed(db, coupon.id, end_user.id) >= coupon.per_user_limit
    ):
        raise HTTPException(409, "COUPON_LIMIT_REACHED")

    # 库存: CAS 扣减 (filter remaining_stock>0 抗并发双击, 卡 d74344ed 模式)
    updated = (
        db.query(Coupon)
        .filter(
            Coupon.id == coupon.id,
            Coupon.remaining_stock > 0,
        )
        .update({Coupon.remaining_stock: Coupon.remaining_stock - 1})
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(409, "COUPON_OUT_OF_STOCK")

    # 二次复检 per_user_limit (独立连接): 本会话已持 SQLite RESERVED 写锁
    # (PG 下锁自 _lock_coupon 起生效), 并发领取此刻无法再提交; 新连接重读
    # 已提交的 ACTIVE 记录, 若并发方已领满 → 409 回滚, 封死 check-then-act
    # 超领窗口。
    if coupon.per_user_limit is not None and (
        _active_claimed_fresh(db, coupon.id, end_user.id) >= coupon.per_user_limit
    ):
        db.rollback()
        raise HTTPException(409, "COUPON_LIMIT_REACHED")
    db.refresh(coupon)

    expires_at = now + timedelta(days=coupon.valid_days)
    code, usage = _build_usage(coupon, end_user.id, expires_at)
    db.add(usage)
    try:
        db.commit()
    except IntegrityError:
        # coupon_code unique 冲突 (uuid 极低概率) → 换码重试一次
        db.rollback()
        code, usage = _build_usage(coupon, end_user.id, expires_at)
        db.add(usage)
        db.commit()
    db.refresh(usage)
    return rsp.ok({
        "coupon_id": coupon.id,
        "coupon_code": code,
        "expires_at": expires_at.isoformat(),
    })


def _lock_coupon(db: Session, coupon_id: int) -> Coupon | None:
    """行锁获取券并刷新快照 (卡 6e698559 领取并发超领加固)。

    per_user_limit 检查 (统计 ACTIVE CouponUsage) 与 insert 之间原为
    check-then-act, 并发双击会超领。领取全程持券行 with_for_update() 行锁
    (对照 fleet_drivers._lock_account), PG 下同券领取串行化, 检查+扣减+落库
    同临界区; populate_existing 强制重发 SELECT 刷新 session 内陈旧快照。
    SQLite 下 with_for_update 为 no-op, 由库存 CAS (RESERVED 写锁) 后的
    二次复检兜底 (见 claim 内注释)。
    """
    return (
        db.query(Coupon)
        .filter(Coupon.id == coupon_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def _active_claimed(db: Session, coupon_id: int, user_id: int) -> int:
    """该用户当前 status=ACTIVE 的已领张数 (per_user_limit 口径)。"""
    return (
        db.query(CouponUsage)
        .filter(
            CouponUsage.coupon_id == coupon_id,
            CouponUsage.user_id == user_id,
            CouponUsage.status == CouponStatus.ACTIVE,
        )
        .count()
    )


def _active_claimed_fresh(db: Session, coupon_id: int, user_id: int) -> int:
    """独立连接统计 ACTIVE 已领数 (卡 6e698559 二次复检专用)。

    本会话事务自首个读起即持 SQLite SHARED 快照, 锁内同会话重查看不到并发方
    已提交的记录; 须开新连接重读。新连接能看到并发方已提交数据 (RESERVED
    写锁不阻塞读者), 且看不到本会话未提交的扣减, 口径即「并发方已领数」。
    连接用后即关, 不留事务。用 CouponUsage.__table__ 表达式而非裸 SQL 字符串:
    status 列为 SAEnum, SQLite 存对象名/PG 存 value, 裸字符串硬编码任一侧
    都会静默查空 (卡 674bb77e 枚举存储坑)。
    """
    stmt = (
        sqlalchemy_select(func.count())
        .select_from(CouponUsage.__table__)
        .where(
            CouponUsage.__table__.c.coupon_id == coupon_id,
            CouponUsage.__table__.c.user_id == user_id,
            CouponUsage.__table__.c.status == CouponStatus.ACTIVE,
        )
    )
    conn = db.get_bind().connect()
    try:
        return int(conn.execute(stmt).scalar() or 0)
    finally:
        conn.close()


def _build_usage(coupon: Coupon, end_user_id: int, expires_at: datetime):
    code = f"CPN-{uuid.uuid4().hex[:12].upper()}"
    usage = CouponUsage(
        coupon_id=coupon.id,
        user_id=end_user_id,
        user_type="end_user",
        coupon_code=code,
        status=CouponStatus.ACTIVE,
        expires_at=expires_at,
    )
    return code, usage

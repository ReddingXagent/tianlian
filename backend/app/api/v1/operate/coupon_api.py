"""
优惠券管理 API - P0 运营核心补齐
POST   /api/v1/operate/coupon              — 创建优惠券
GET    /api/v1/operate/coupon              — 优惠券列表
GET    /api/v1/operate/coupon/{id}         — 优惠券详情
PUT    /api/v1/operate/coupon/{id}         — 更新优惠券
DELETE /api/v1/operate/coupon/{id}         — 删除优惠券
POST   /api/v1/operate/coupon/distribute   — 发放优惠券
GET    /api/v1/operate/coupon/batches      — 发放批次列表
POST   /api/v1/operate/coupon/redeem       — 核销优惠券
GET    /api/v1/operate/coupon/stats        — 优惠券统计
GET    /api/v1/operate/coupon/usages       — 使用记录
"""
import logging
import uuid
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, update
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.charging_order import ChargingOrder
from app.models.coupon import Coupon, CouponBatch, CouponUsage, CouponType, CouponStatus
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import require_platform_admin, is_platform_admin
from app.services.wx_pay import response as rsp

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# ── Pydantic Schemas ──

class CouponCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    coupon_type: CouponType = CouponType.FIXED
    face_value: float = Field(..., ge=0)
    min_order_amount: Optional[float] = Field(0.0, ge=0)
    max_discount_amount: Optional[float] = Field(None, ge=0)
    applicable_user_types: Optional[str] = None
    applicable_stations: Optional[str] = None
    total_stock: int = Field(..., ge=0)
    per_user_limit: int = Field(1, ge=0)
    valid_days: int = 30
    start_time: datetime
    end_time: datetime
    is_active: bool = True
    description: Optional[str] = None

class CouponUpdate(BaseModel):
    name: Optional[str] = None
    coupon_type: Optional[CouponType] = None
    face_value: Optional[float] = Field(None, ge=0)
    min_order_amount: Optional[float] = Field(None, ge=0)
    max_discount_amount: Optional[float] = Field(None, ge=0)
    applicable_user_types: Optional[str] = None
    applicable_stations: Optional[str] = None
    total_stock: Optional[int] = Field(None, ge=0)
    per_user_limit: Optional[int] = Field(None, ge=0)
    valid_days: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None

class CouponDistribute(BaseModel):
    coupon_id: int
    quantity: int = Field(..., ge=1)
    user_type: Optional[str] = None
    user_ids: Optional[str] = None
    batch_name: Optional[str] = "优惠券发放"

class CouponRedeem(BaseModel):
    coupon_code: str = Field(..., min_length=1)
    order_id: int
    # ge=0: 负订单金额会使 FREE_CHARGE/PERCENTAGE 券算出负抵扣原样落库 (卡 0044a439)
    order_amount: float = Field(..., ge=0)

# ── 固定路径路由（必须在 /coupon/{coupon_id} 参数化路由之前定义）──


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """naive DateTime 列读出后补 UTC（与 redeem 路径既有约定一致）。"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _coupon_distribute_window_error(coupon: Coupon, now: datetime) -> Optional[str]:
    """发放窗口校验（卡 73d52e60）: now 须落在 [start_time, end_time] 闭区间内。

    返回错误文案；窗口内返回 None。start/end 为 naive 时按 UTC 解释（域内约定）。
    """
    start = _as_utc(coupon.start_time)
    end = _as_utc(coupon.end_time)
    if start and now < start:
        return f"发放未开始，开始时间 {start.strftime('%Y-%m-%d %H:%M')}"
    if end and now > end:
        return f"发放已结束，结束时间 {end.strftime('%Y-%m-%d %H:%M')}"
    return None


def _coupon_update_window_error(obj: Coupon, updates: dict) -> Optional[str]:
    """更新窗口校验（卡 ea373b3a）: 合并后的 start_time ≤ end_time，否则可造反向/永久窗口券。

    合并语义：PUT 是部分更新（exclude_unset），只改单边时与存量另一边合并判定，
    单独校验请求体或单独校验存量都拦不住"改 end 早于存量 start"这类组合。
    start == end 合法（零宽闭区间，与发放侧闭区间语义一致）。风格与
    _coupon_distribute_window_error 同构：返回文案或 None。
    """
    start = updates.get("start_time", obj.start_time)
    end = updates.get("end_time", obj.end_time)
    if start is not None and end is not None and _as_utc(start) > _as_utc(end):
        return (f"发放窗口非法：开始时间 {start.strftime('%Y-%m-%d %H:%M')} "
                f"晚于结束时间 {end.strftime('%Y-%m-%d %H:%M')}")
    return None


@router.get("/coupon/stats", summary="优惠券统计")
def coupon_stats(db: Session = Depends(get_db)):
    try:
        total_coupons = db.query(func.count(Coupon.id)).scalar() or 0
        total_stock = db.query(func.coalesce(func.sum(Coupon.total_stock), 0)).scalar() or 0
        total_remaining = db.query(func.coalesce(func.sum(Coupon.remaining_stock), 0)).scalar() or 0
        total_distributed = db.query(func.count(CouponUsage.id)).scalar() or 0
        total_used = db.query(func.count(CouponUsage.id)).filter(CouponUsage.status == CouponStatus.USED).scalar() or 0
        total_discount = db.query(func.coalesce(func.sum(CouponUsage.discount_amount), 0)).filter(CouponUsage.status == CouponStatus.USED).scalar() or 0

        return success_response({
            "total_coupons": total_coupons,
            "total_stock": int(total_stock),
            "remaining_stock": int(total_remaining),
            "total_distributed": total_distributed,
            "total_used": total_used,
            "usage_rate": round(total_used / total_distributed * 100, 1) if total_distributed > 0 else 0,
            "total_discount_amount": float(total_discount),
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("优惠券统计查询失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/coupon/usages", summary="优惠券使用记录")
def coupon_usages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        q = db.query(CouponUsage)
        # team scoping（任务卡 ab5c5f17）：优惠券本体为平台级配置（读对登录用户可见）；
        # 使用记录按领取用户归属过滤，非 admin 仅返回本 team 用户的领券记录（经 user→team）。
        if not is_platform_admin(user):
            q = q.join(User, CouponUsage.user_id == User.id).filter(User.team_id == user.team_id)
        # 过期派生与 status 过滤协同（卡 73d52e60）：派生在响应层（见下），status=expired
        # 须同时命中"DB 已翻转 EXPIRED"与"ACTIVE 但已过期"两类记录，否则列表显示 expired
        # 却筛不出来，读出语义自相矛盾。故该分支 SQL 层拉宽为 in_(ACTIVE, EXPIRED)，
        # 再在响应层按派生状态二次过滤（total 为拉宽后计数，分页语义不变）。
        filter_expired = status == CouponStatus.EXPIRED.value
        if filter_expired:
            q = q.filter(CouponUsage.status.in_([CouponStatus.ACTIVE, CouponStatus.EXPIRED]))
        elif status:
            q = q.filter(CouponUsage.status == status)
        if user_id is not None:
            q = q.filter(CouponUsage.user_id == user_id)
        total = q.count()
        items = q.order_by(CouponUsage.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        now = datetime.now(timezone.utc)
        data = []
        for i in items:
            row = {c.name: str(getattr(i, c.name)) if isinstance(getattr(i, c.name), datetime) else getattr(i, c.name) for c in i.__table__.columns}
            # 过期派生（卡 73d52e60）：DB status=ACTIVE 但 expires_at 已过 → 响应层显示 expired。
            # 刻意不回写 DB：GET 读端点携带 UPDATE 会与并行核销竞态（USED 被 flipped 成 EXPIRED），
            # 且翻转为持久 EXPIRED 的职责在 redeem 懒检查路径（既有行为），此处只保证读出语义正确。
            if row["status"] == CouponStatus.ACTIVE.value:
                _exp = _as_utc(i.expires_at)
                if _exp and _exp < now:
                    row["status"] = CouponStatus.EXPIRED.value
            if filter_expired and row["status"] != CouponStatus.EXPIRED.value:
                continue
            data.append(row)
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("优惠券使用记录查询失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/coupon/batches", summary="优惠券发放批次列表")
def list_coupon_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    coupon_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(CouponBatch)
        if coupon_id is not None:
            q = q.filter(CouponBatch.coupon_id == coupon_id)
        total = q.count()
        items = q.order_by(CouponBatch.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: str(getattr(i, c.name)) if isinstance(getattr(i, c.name), datetime) else getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("优惠券发放批次列表查询失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post("/coupon/distribute", summary="发放优惠券")
def distribute_coupons(body: CouponDistribute, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        coupon = db.query(Coupon).filter(Coupon.id == body.coupon_id).first()
        if not coupon:
            raise HTTPException(404, "优惠券不存在")
        if not coupon.is_active:
            raise HTTPException(400, "该优惠券已停用")
        # 发放窗口 enforcement（卡 73d52e60）：窗口外的券即使启用也禁止发放
        _win_err = _coupon_distribute_window_error(coupon, datetime.now(timezone.utc))
        if _win_err:
            raise HTTPException(400, _win_err)
        if coupon.remaining_stock < body.quantity:
            raise HTTPException(400, f"库存不足，剩余 {coupon.remaining_stock} 张")

        # 生成券码并发放: quantity 为发放总张数(前端契约), 轮流分配到 user_ids 目标池
        # (留空则发放给 user_id=0)。库存已按 quantity 扣减, 发放数必须与之严格一致,
        # 否则库存与 CouponUsage 数量脱钩造成营销资产虚耗。
        target_uids = [int(uid.strip()) for uid in body.user_ids.split(",") if uid.strip()] if body.user_ids else [0]

        # per_user_limit enforce（卡 ea373b3a）: None/0 = 不限，否则单用户领取数不超限。
        # 整批判定而非逐张判定——部分超限整批拒绝，避免库存扣减与实际发放数脱钩
        # （与 quantity 一致性约束同源）。应用层计数而非 DB 约束：distribute 是低频
        # 运营端点，且限领是 (coupon_id, user_id) 聚合语义，DB 行级约束无法承载。
        limit = coupon.per_user_limit or 0
        if limit > 0:
            held = dict(
                db.query(CouponUsage.user_id, func.count(CouponUsage.id))
                .filter(CouponUsage.coupon_id == coupon.id,
                        CouponUsage.user_id.in_(target_uids))
                .group_by(CouponUsage.user_id)
                .all()
            )
            # 分配预演与下发循环同构（i % len(target_uids) 轮流）, 保证判定的
            # "将分得数"与实际落库完全一致
            alloc = Counter()
            for i in range(body.quantity):
                alloc[target_uids[i % len(target_uids)]] += 1
            for uid, cnt in alloc.items():
                total_after = held.get(uid, 0) + cnt
                if total_after > limit:
                    raise HTTPException(
                        400, f"用户 {uid} 领取数量将达 {total_after} 张，超出每人限领 {limit} 张"
                    )

        # 创建批次
        batch = CouponBatch(
            coupon_id=coupon.id,
            batch_name=body.batch_name,
            quantity=body.quantity,
            user_type=body.user_type,
            user_ids=body.user_ids,
        )
        db.add(batch)
        db.flush()

        # 扣减库存 (卡 674bb77e): 与 redeem 同类 check-then-act 竞态 —— 旧写法
        # `coupon.remaining_stock -= q` 以读到的旧值绝对覆盖, 并发双方同过库存检查后
        # 后提交者覆盖前者 → 丢更新, 库存只扣一份、券发两份。改原子相对 CAS:
        # WHERE remaining_stock >= q 保证不超发; 相对扣减 (-= q 于 DB 侧) 保证任意
        # 提交交错下终值正确。败者 rowcount==0 → 整批 rollback, 沿用既有 400 文案。
        decremented = (
            db.query(Coupon)
            .filter(Coupon.id == coupon.id, Coupon.remaining_stock >= body.quantity)
            .update(
                {Coupon.remaining_stock: Coupon.remaining_stock - body.quantity},
                synchronize_session=False,
            )
        )
        if decremented == 0:
            db.rollback()
            db.refresh(coupon)
            raise HTTPException(400, f"库存不足，剩余 {coupon.remaining_stock} 张")

        created = []
        expires_at = datetime.now(timezone.utc) + timedelta(days=coupon.valid_days)
        for i in range(body.quantity):
            uid = target_uids[i % len(target_uids)]
            code = f"CPN-{uuid.uuid4().hex[:12].upper()}"
            usage = CouponUsage(
                coupon_id=coupon.id,
                batch_id=batch.id,
                user_id=uid,
                user_type=body.user_type,
                coupon_code=code,
                status=CouponStatus.ACTIVE,
                expires_at=expires_at,
            )
            db.add(usage)
            created.append(code)

        db.commit()
        return success_response({"batch_id": batch.id, "count": len(created), "codes": created[:10]}, "发放成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("发放优惠券失败 coupon_id=%s", body.coupon_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post("/coupon/redeem", summary="核销优惠券")
def redeem_coupon(body: CouponRedeem, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        usage = db.query(CouponUsage).filter(CouponUsage.coupon_code == body.coupon_code).first()
        if not usage:
            raise HTTPException(404, "券码不存在")
        if usage.status != CouponStatus.ACTIVE:
            raise HTTPException(400, f"优惠券状态: {usage.status.value}")
        _expires_at = usage.expires_at
        if _expires_at and _expires_at.tzinfo is None:
            _expires_at = _expires_at.replace(tzinfo=timezone.utc)
        if _expires_at and _expires_at < datetime.now(timezone.utc):
            usage.status = CouponStatus.EXPIRED
            db.commit()
            raise HTTPException(400, "优惠券已过期")

        coupon = db.query(Coupon).filter(Coupon.id == usage.coupon_id).first()

        # 订单归属校验 (卡 5f7fa7ba): 不变量为【订单归属持券人】——redeem 是运营端点,
        # 当前用户是 admin 不持 C 端券, 故对照 usage.user_id 而非请求方。
        # 不存在/非本人 → 契约 §6 统一 biz_error 10004 (200 防枚举), 同构 business_orders._get_own_order。
        order = db.query(ChargingOrder).filter(ChargingOrder.id == body.order_id).first()
        if order is None or order.user_id != usage.user_id:
            return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)

        if coupon and coupon.min_order_amount and body.order_amount < float(coupon.min_order_amount):
            raise HTTPException(400, f"订单金额不满足最低消费 ¥{coupon.min_order_amount}")

        # 计算抵扣金额
        if coupon:
            if coupon.coupon_type == CouponType.FIXED:
                discount = float(coupon.face_value)
            elif coupon.coupon_type == CouponType.PERCENTAGE:
                discount = body.order_amount * float(coupon.face_value)
            elif coupon.coupon_type == CouponType.FREE_CHARGE:
                discount = body.order_amount
            else:
                discount = 0.0
            if coupon.max_discount_amount and discount > float(coupon.max_discount_amount):
                discount = float(coupon.max_discount_amount)
        else:
            discount = 0.0

        # CAS 守卫 (卡 674bb77e): 读-判-写之间存在并发窗口, 双请求可同过 status==ACTIVE
        # 检查后双双落 USED → 双核销双抵扣。SQLite 下 with_for_update 是 no-op (整库单写锁,
        # 无行锁语义), 挡不住该窗口; 故用条件 UPDATE 原子守卫: WHERE 带 status='active',
        # rowcount==0 即说明并发方(或懒翻转路径)已改状态, 回查实际状态返回既有 400 语义。
        now = datetime.now(timezone.utc)
        result = db.execute(
            update(CouponUsage)
            .where(
                CouponUsage.id == usage.id,
                CouponUsage.status == CouponStatus.ACTIVE,
            )
            .values(
                status=CouponStatus.USED,
                order_id=body.order_id,
                discount_amount=round(discount, 2),
                used_at=now,
            )
        )
        if result.rowcount == 0:
            db.rollback()
            db.refresh(usage)
            raise HTTPException(400, f"优惠券状态: {usage.status.value}")
        db.commit()

        return success_response({
            "coupon_code": body.coupon_code,
            "discount_amount": round(discount, 2),
            "order_id": body.order_id,
        }, "核销成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("核销优惠券失败 coupon_code=%s", body.coupon_code)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ── Coupon CRUD ──

@router.post("/coupon", summary="创建优惠券")
def create_coupon(body: CouponCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        data = body.model_dump()
        data["remaining_stock"] = data["total_stock"]
        obj = Coupon(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "优惠券创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建优惠券失败 name=%s", body.name)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/coupon", summary="优惠券列表")
def list_coupons(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    coupon_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(Coupon)
        if is_active is not None:
            q = q.filter(Coupon.is_active == is_active)
        if coupon_type:
            q = q.filter(Coupon.coupon_type == coupon_type)
        total = q.count()
        items = q.order_by(Coupon.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: str(getattr(i, c.name)) if isinstance(getattr(i, c.name), datetime) else getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("优惠券列表查询失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ── 参数化路由（必须在固定路径 /coupon/xxx 路由之后）──

@router.get("/coupon/{coupon_id}", summary="优惠券详情")
def get_coupon(coupon_id: int, db: Session = Depends(get_db)):
    try:
        obj = db.query(Coupon).filter(Coupon.id == coupon_id).first()
        if not obj:
            raise HTTPException(404, "优惠券不存在")
        return success_response({c.name: str(getattr(obj, c.name)) if isinstance(getattr(obj, c.name), datetime) else getattr(obj, c.name) for c in obj.__table__.columns})
    except HTTPException:
        raise
    except Exception:
        logger.exception("优惠券详情查询失败 coupon_id=%s", coupon_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put("/coupon/{coupon_id}", summary="更新优惠券")
def update_coupon(coupon_id: int, body: CouponUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(Coupon).filter(Coupon.id == coupon_id).first()
        if not obj:
            raise HTTPException(404, "优惠券不存在")
        updates = body.model_dump(exclude_unset=True)
        # 窗口合法性校验（卡 ea373b3a）: 合并后 start≤end，防止 update 造反向/永久窗口券
        _win_err = _coupon_update_window_error(obj, updates)
        if _win_err:
            raise HTTPException(400, _win_err)
        for k, v in updates.items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新优惠券失败 coupon_id=%s", coupon_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.delete("/coupon/{coupon_id}", summary="删除优惠券")
def delete_coupon(coupon_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(Coupon).filter(Coupon.id == coupon_id).first()
        if not obj:
            raise HTTPException(404, "优惠券不存在")
        db.delete(obj)
        db.commit()
        return success_response(None, "已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除优惠券失败 coupon_id=%s", coupon_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")

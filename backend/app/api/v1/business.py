"""用户端支付 API (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §2 (支付)
端点 (挂 /business 前缀):
- POST /business/payments/prepay   统一下单 → wx.requestPayment 五字段
- POST /business/payments/notify   IM-B回调 (外部, 白名单豁免认证, IM-B签名校验)
- GET  /business/orders/{order_id} 订单/支付状态查询

认证: prepay/orders 走 C 端用户 token (get_current_user); notify 是IM-B→云端外部回调,
靠 is_public_path 白名单豁免 enforce_auth, IM-B签名/解密在 service 层 (mock 阶段放宽)。
响应: 用户端云端契约统一 code=0 (契约 §6)。
"""
import logging
import math
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.api.v1.auth import get_current_user
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.station import Station, StationStatus
from app.models.user import User
from app.services.tenant_brand_service import branding_for_tenant, branding_map
from app.services.wx_pay import payment
from app.services.wx_pay import response as rsp

logger = logging.getLogger(__name__)
router = APIRouter()
stations_router = APIRouter()

# 契约 §1 缓存: 场站响应(含 branding)端侧可缓存 5 分钟
STATION_CACHE_CONTROL = "public, max-age=300"


class PrepayRequest(BaseModel):
    order_id: str = Field(..., description="业务订单号 (ChargingOrder.order_no)")
    openid: str = Field(..., description="用户 openid")
    scene: Literal["miniprogram", "app"] = Field(
        "miniprogram", description="miniprogram=小程序 appid / app=移动应用 appid"
    )


def _prepay_impl(db: Session, order: ChargingOrder, openid: str, scene: str):
    """prepay 核心逻辑 (终态守卫 + 统一下单 + 异常映射), 供 /business/payments/prepay
    与 C端 POST /charging-orders/{id}/pay 复用 (卡 089b01b2)。

    归属校验由调用方完成: 运营端点用 user.id, C端薄路由用 end_user.id
    (契约 §8.5 end_user_id ↔ ChargingOrder.user_id 映射)。
    """
    # 契约 §2.1 (卡 2c49e61f): 订单终态守卫 —— cancelled/failed 不可再发起支付。
    # 注: completed 不拦 —— 后付费模型下充电完成后仍需 prepay 支付。
    if order.order_status in (OrderStatus.CANCELLED, OrderStatus.FAILED):
        return rsp.biz_error(rsp.CODE_ORDER_CLOSED)
    # TODO(切真实IM-B): 当前 mock 阶段沿用传入 openid; 接入真实IM-B服务商后,
    # openid 必须从用户记录取, 禁止信任端侧传入值 (防伪造支付主体)。
    try:
        five = payment.prepay(
            db, order_id=order.order_no, openid=openid, scene=scene
        )
        return rsp.ok(five)
    except payment.SubMerchantFrozen:
        # 子商户冻结 (merchant_status=FROZEN) → code!=0
        return rsp.biz_error(rsp.CODE_SUB_MCH_FROZEN)
    except payment.OrderAlreadyPaid:
        # 订单已支付, 拒绝重复下单 (工作卡 16209d26)
        return rsp.biz_error(rsp.CODE_ORDER_ALREADY_PAID)
    except payment.SubMerchantNotReady:
        # 子商户未就绪 (进件未 FINISH / merchant_status=PENDING) → code!=0
        return rsp.biz_error(rsp.CODE_SUB_MCH_NOT_READY)
    except HTTPException:
        raise
    except Exception:
        logger.exception("prepay 异常 order_id=%s", order.order_no)
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.post("/payments/prepay", summary="统一下单 (返回 wx.requestPayment 五字段)")
@limiter.limit("30/minute")
def prepay(
    request: Request,
    body: PrepayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """服务商统一下单, 端侧拿到 data 原样传入 wx.requestPayment (契约 §2.1)。"""
    # 安全 (卡 031faccd): 调用 payment.prepay 前先校验订单归属当前登录用户。
    # 订单不存在 / 非本人订单统一回 ORDER_NOT_FOUND —— 不泄露订单存在性 (防枚举)。
    order = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no == body.order_id)
        .first()
    )
    if order is None or order.user_id != user.id:
        return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)
    return _prepay_impl(db, order, body.openid, body.scene)


@router.post("/payments/notify", summary="IM-B支付回调 (IM-B→云端)")
async def payments_notify(request: Request, db: Session = Depends(get_db)):
    """IM-B加密通知, 验签解密后更新订单状态 (契约 §2.2)。

    非用户端接口: enforce_auth 经 is_public_path 白名单豁免, 靠IM-B签名校验自证
    (mock 阶段 verify_and_decrypt_notify 放宽)。回调幂等 (重复不重复落 PAID)。

    安全 (卡 7669b9b1): mock 客户端不验签, 公开回调 = 伪造面 (伪造 SUCCESS 报文
    → 0 元购电)。mock 模式且非开发环境 (DEBUG=False) 时拒绝处理 —— 复用
    config 的 DEBUG/ENVIRONMENT, 不新增配置项; 真实回调必须配 WX_PAY_MODE=real。
    """
    settings = get_settings()
    if settings.WX_PAY_MODE == "mock" and not settings.DEBUG:
        logger.warning(
            "payments_notify 拒绝处理: WX_PAY_MODE=mock 且非 DEBUG 环境, "
            "公开回调可被伪造 (卡 7669b9b1); 请配置 WX_PAY_MODE=real"
        )
        return JSONResponse(
            status_code=503,
            content={"code": "FAIL", "message": "支付回调服务不可用"},
        )
    try:
        raw = await request.body()
        result = payment.handle_notify(db, raw, dict(request.headers))
        return result
    except Exception:
        logger.exception("payments_notify 异常")
        return {"code": "FAIL", "message": "内部错误"}


@router.get("/orders/{order_id}", summary="订单/支付状态查询")
@limiter.limit("60/minute")
def get_order(
    request: Request,
    order_id: str,
    detail: Optional[str] = Query(
        None, description="传 full 返回 §7.7 完整明细; 默认 §2.3 轻量支付查询"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """订单查询 (契约 §2.3 轻量 / §7.7 完整明细)。

    - 默认 (无 detail): §2.3 支付状态轻量查询 —— payment_status/transaction_id/paid_at。
      无支付记录 → UNPAID 占位 (业务订单可能存在但未发起支付)。
    - ?detail=full: §7.7 完整明细 —— 充电 + 费用完整信息 (金额分); 仅返回本人订单。
    """
    if detail == "full":
        # §7.7 完整明细
        from app.api.v1.business_orders import order_full_detail
        from app.models.charging_order import ChargingOrder
        order = (
            db.query(ChargingOrder)
            .filter(ChargingOrder.order_no == order_id)
            .first()
        )
        if order is None or order.user_id != user.id:
            # 卡 418a675a: 业务错误统一 biz_error (不泄露订单存在性)
            return rsp.biz_error(rsp.CODE_ORDER_NOT_FOUND)
        return rsp.ok(order_full_detail(db, order))

    # §2.3 轻量查询归属校验 (卡 b9518748): 仅本人订单返回真实支付信息。
    # 不存在 / 非本人订单 → 一律 UNPAID 占位, 与"无支付记录"行为一致, 不泄露订单存在性。
    from app.models.charging_order import ChargingOrder

    order = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no == order_id)
        .first()
    )
    if order is None or order.user_id != user.id:
        return rsp.ok(
            {
                "order_id": order_id,
                "payment_status": "UNPAID",
                "transaction_id": None,
                "paid_at": None,
            }
        )

    info = payment.get_order_payment(db, order_id)
    if info is None:
        return rsp.ok(
            {
                "order_id": order_id,
                "payment_status": "UNPAID",
                "transaction_id": None,
                "paid_at": None,
            }
        )
    return rsp.ok(info)


# =====================================================================
# 契约 §1 — C端场站入口 (GET /business/stations, GET /business/stations/{id})
# 工作卡 5300ccc2
#
# 与管理侧 /stations 的区别:
# - 鉴权: 仅 get_current_user (C端只读), 不挂 require_write_permission("station:edit")
# - 可见性: 不按 caller team 隔离 —— C端用户跨运营商浏览全部公开场站
# - 信封: code=0 (契约 §6 用户端云端契约), 非管理侧 code=200
# - 字段: C端公开视图, 剥离运维内部字段(operator_id/team_id/total_cost/
#         total_devices/health_score/时间戳); 保留 tenant_id(契约 §1.1 示例字段)
# =====================================================================


def _safe_enum_val(v, default="normal"):
    """安全取枚举值, 兼容 DB 中不在枚举范围的旧数据。"""
    if v is None:
        return default
    if hasattr(v, "value"):
        return v.value
    return str(v)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """球面距离(km)。SQLite 无 GIS, nearby 模式在 Python 侧算。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    # clamp 到 [0, 1]: 对跖点附近浮点 round-off 可能使 a 略超 1.0, 导致 asin(sqrt(a))
    # 抛 ValueError (与 dispatch_engine.py 同一公式保持一致)。
    a = min(1.0, max(0.0, a))
    return 2 * r * math.asin(math.sqrt(a))


def _station_to_public_dict(
    station: Station,
    branding: Optional[dict] = None,
    distance_km: Optional[float] = None,
) -> dict:
    """C端场站公开视图 + branding (契约 §1)。

    branding: 详情传全量 / 列表传轻量, 由调用方用 branding_for_tenant/branding_map 解析。
    distance_km: 仅 nearby 列表携带, 普通列表/详情为 None(不输出)。
    """
    data = {
        "id": station.id,
        "name": station.name,
        "tenant_id": station.tenant_id,
        "code": station.code,
        "province": station.province,
        "city": station.city,
        "district": station.district,
        "address": station.address,
        "lat": station.lat,
        "lon": station.lon,
        "operator_name": station.operator_name,
        "total_power": station.total_power,
        "gun_count": station.gun_count,
        "parking_spots": station.parking_spots,
        "station_type": station.station_type,
        "venue_type": station.venue_type,
        "status": _safe_enum_val(station.status, "normal"),
    }
    if branding is not None:
        data["branding"] = branding
    if distance_km is not None:
        data["distance_km"] = round(distance_km, 2)
    return data


@stations_router.get("/stations", summary="C端场站列表 (含轻量 branding)")
def business_list_stations(
    response: Response,
    lat: Optional[float] = Query(None, description="纬度, 配合 lon 按 nearby 过滤排序"),
    lon: Optional[float] = Query(None, description="经度, 配合 lat 按 nearby 过滤排序"),
    radius: Optional[float] = Query(None, description="附近半径(km), 需与 lat/lon 同传"),
    keyword: Optional[str] = Query(None, description="名称/地址关键词"),
    city: Optional[str] = Query(None, description="城市过滤"),
    status: Optional[str] = Query(None, description="状态: normal/maintenance/closed/active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """C端只读: 全部公开场站(不按 team 隔离, 跨运营商浏览)。

    契约 §1: 列表响应携带轻量版 branding(operator_name/theme_color + source);
    Cache-Control: public, max-age=300。lat+lon 同传时进入 nearby 模式(按距离过滤排序,
    附 distance_km; 无坐标场站在 nearby 模式下不返回)。
    """
    response.headers["Cache-Control"] = STATION_CACHE_CONTROL

    query = db.query(Station)
    if status:
        try:
            query = query.filter(Station.status == StationStatus(status))
        except ValueError:
            pass
    if keyword:
        query = query.filter(
            Station.name.contains(keyword) | Station.address.contains(keyword)
        )
    if city:
        query = query.filter(Station.city == city)

    nearby_mode = lat is not None and lon is not None

    if nearby_mode:
        # SQLite 无 GIS: SQL 取候选 → Python 侧算距离过滤排序 → 分页
        candidates = query.all()
        enriched: list[tuple[float, Station]] = []
        for st in candidates:
            if st.lat is None or st.lon is None:
                continue  # nearby 模式排除无坐标场站
            try:
                d = _haversine_km(lat, lon, st.lat, st.lon)
            except (ValueError, OverflowError):
                # 坐标异常(浮点 round-off/非法值)算不出距离 → 跳过该站, 不让整体 500
                logger.warning(
                    "nearby 距离计算异常, 跳过 station_id=%s lat=%s lon=%s",
                    st.id, st.lat, st.lon, exc_info=True,
                )
                continue
            if radius is not None and d > radius:
                continue
            enriched.append((d, st))
        enriched.sort(key=lambda x: x[0])
        total = len(enriched)
        page_slice = enriched[(page - 1) * page_size : page * page_size]
        bmap = branding_map(db, [st.tenant_id for _, st in page_slice], lightweight=True)
        items = [
            _station_to_public_dict(st, branding=bmap.get(st.tenant_id), distance_km=d)
            for d, st in page_slice
        ]
    else:
        total = query.count()
        page_items = (
            query.order_by(Station.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        bmap = branding_map(db, [s.tenant_id for s in page_items], lightweight=True)
        items = [
            _station_to_public_dict(st, branding=bmap.get(st.tenant_id))
            for st in page_items
        ]

    return rsp.ok(
        {"items": items, "total": total, "page": page, "page_size": page_size}
    )


@stations_router.get("/stations/{station_id}", summary="C端场站详情 (含全量 branding)")
def business_get_station(
    station_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """C端只读: 单场站详情 + 全量 branding (契约 §1.1)。

    无 team 隔离: 任意公开场站均可查(不存在 → 404)。branding 全量(operator_name/
    logo_url/service_phone/theme_color + source), 租户未配置 → 天链默认品牌(source=default)。
    """
    response.headers["Cache-Control"] = STATION_CACHE_CONTROL
    station = db.query(Station).filter(Station.id == station_id).first()
    if station is None:
        # 卡 418a675a: 业务错误统一 biz_error (契约 §6)
        return rsp.biz_error(rsp.CODE_STATION_NOT_FOUND)
    branding = branding_for_tenant(db, station.tenant_id, lightweight=False)
    return rsp.ok(_station_to_public_dict(station, branding=branding))

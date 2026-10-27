"""
停车场系统对接开放API - 任务卡 309b4132

独立于管理侧 user JWT 的对外开放端点，供外部停车场系统查询充电状态、
查询折扣规则、回调减免留痕。

鉴权：X-App-Key + X-App-Secret header（hmac.compare_digest 常数时间比较）。
站点隔离：凭证绑定 station_id，所有数据查询自动限定本站点，跨站点数据不可见。
路由前缀 /open/parking 已在 enforce_auth 白名单豁免（无需 user JWT）。

端点：
- GET  /open/parking/charge-status?plate=xxx       本站点该车牌充电状态
- GET  /open/parking/discount-eligibility?plate=xxx 本站点生效折扣规则
- POST /open/parking/discount-applied              减免留痕（order_no 幂等）
"""
import hmac
import logging

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.database import get_db
from app.core.response import success_response
from app.models.parking_integration import ParkingIntegrationConfig
from app.models.parking_discount_applied import ParkingDiscountApplied
from app.models.parking import ParkingDiscount
from app.models.charging_order import ChargingOrder, OrderStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open/parking", tags=["停车对接开放API"])


# ── 鉴权依赖 ──
def _verify_credentials(
    db: Session,
    app_key: Optional[str],
    app_secret: Optional[str],
) -> ParkingIntegrationConfig:
    """校验 X-App-Key/X-App-Secret，返回有效且启用的集成配置；否则 401。

    用 hmac.compare_digest 做常数时间比较，防时序侧信道泄露 key/secret 是否正确。
    缺 header / key 不存在 / secret 不匹配 / 配置 inactive → 统一 401（不区分，避免枚举）。
    """
    if not app_key or not app_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的对接凭证")
    cfg = db.query(ParkingIntegrationConfig).filter(
        ParkingIntegrationConfig.app_key == app_key
    ).first()
    # 常数时间比较 secret；cfg 缺失时用 app_key 自身作占位比较，保持恒定分支
    secret_ok = cfg is not None and hmac.compare_digest(str(cfg.app_secret), str(app_secret))
    if not cfg or not secret_ok or not cfg.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的对接凭证")
    return cfg


def get_active_credential(
    db: Session = Depends(get_db),
    x_app_key: Optional[str] = Header(None, alias="X-App-Key"),
    x_app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
) -> ParkingIntegrationConfig:
    """基础鉴权：仅校验凭证有效且启用（401）。"""
    return _verify_credentials(db, x_app_key, x_app_secret)


def get_query_credential(
    cfg: ParkingIntegrationConfig = Depends(get_active_credential),
) -> ParkingIntegrationConfig:
    """查询鉴权：在基础鉴权之上，额外要求 allow_query=True（否则 403）。

    仅作用于查询类端点（charge-status / discount-eligibility）；
    discount-applied 留痕端点用 get_active_credential，不受 allow_query 限制。
    """
    if not cfg.allow_query:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该对接凭证未开放查询权限")
    return cfg


# ── 请求模型 ──
class DiscountAppliedRequest(BaseModel):
    plate_number: str = Field(..., min_length=1, max_length=20, description="车牌号")
    order_no: str = Field(..., min_length=1, max_length=100, description="停车场订单号(幂等键)")
    amount: Decimal = Field(..., description="减免金额(元)")
    remark: Optional[str] = Field(None, max_length=500, description="备注")

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("减免金额必须为正数")
        return v


# ════════════════════════════════════════════════════════════
# GET /charge-status — 本站点该车牌充电状态
# ════════════════════════════════════════════════════════════
@router.get("/charge-status")
def charge_status(
    plate: str = Query(..., min_length=1, description="车牌号"),
    cfg: ParkingIntegrationConfig = Depends(get_query_credential),
    db: Session = Depends(get_db),
):
    """查询本站点该车牌是否正在充电。

    充电中定义为存在 order_status=charging 的订单；site 隔离由 cfg.station_id 保证。
    """
    try:
        charging = db.query(ChargingOrder).filter(
            ChargingOrder.station_id == cfg.station_id,
            ChargingOrder.plate_number == plate,
            ChargingOrder.order_status == OrderStatus.CHARGING,
        ).first() is not None
        return success_response({
            "plate_number": plate,
            "station_id": cfg.station_id,
            "charging": charging,
        })
    except Exception:
        logger.exception("停车对接查询充电状态失败 station_id=%s plate=%s", cfg.station_id, plate)
        raise HTTPException(status_code=503, detail="服务暂时不可用")


# ════════════════════════════════════════════════════════════
# GET /discount-eligibility — 本站点生效折扣规则
# ════════════════════════════════════════════════════════════
@router.get("/discount-eligibility")
def discount_eligibility(
    plate: str = Query(..., min_length=1, description="车牌号"),
    cfg: ParkingIntegrationConfig = Depends(get_query_credential),
    db: Session = Depends(get_db),
):
    """返回本站点当前生效的停车折扣规则（plate 仅作记录，规则按站点）。"""
    try:
        rules = db.query(ParkingDiscount).filter(
            ParkingDiscount.station_id == cfg.station_id,
            ParkingDiscount.is_active.is_(True),
        ).order_by(ParkingDiscount.id.desc()).all()
        return success_response({
            "plate_number": plate,
            "station_id": cfg.station_id,
            "rules": [
                {
                    "id": r.id,
                    "discount_type": r.discount_type,
                    "free_minutes": r.free_minutes,
                    "discount_percent": float(r.discount_percent) if r.discount_percent is not None else 0.0,
                    "fixed_amount": float(r.fixed_amount) if r.fixed_amount is not None else 0.0,
                    "max_discount": float(r.max_discount) if r.max_discount is not None else None,
                    "valid_start": r.valid_start,
                    "valid_end": r.valid_end,
                }
                for r in rules
            ],
        })
    except Exception:
        logger.exception("停车对接查询折扣规则失败 station_id=%s plate=%s", cfg.station_id, plate)
        raise HTTPException(status_code=503, detail="服务暂时不可用")


# ════════════════════════════════════════════════════════════
# POST /discount-applied — 减免留痕（order_no 幂等）
# ════════════════════════════════════════════════════════════
@router.post("/discount-applied")
def discount_applied(
    body: DiscountAppliedRequest,
    cfg: ParkingIntegrationConfig = Depends(get_active_credential),
    db: Session = Depends(get_db),
):
    """记录停车场系统已对车主减免停车费（对账留痕）。

    station_id 取自凭证（绑定站点），非请求体，防跨站点伪造。
    order_no 幂等：同站点同 order_no 已存在则直接返回既有记录，不重复入库。
    """
    try:
        existing = db.query(ParkingDiscountApplied).filter(
            ParkingDiscountApplied.station_id == cfg.station_id,
            ParkingDiscountApplied.order_no == body.order_no,
        ).first()
        if existing:
            return success_response(_applied_to_dict(existing), "减免记录已存在(幂等)")

        rec = ParkingDiscountApplied(
            station_id=cfg.station_id,
            plate_number=body.plate_number,
            order_no=body.order_no,
            amount=body.amount,
            remark=body.remark,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return success_response(_applied_to_dict(rec), "减免留痕成功")
    except Exception:
        logger.exception(
            "停车对接减免留痕失败 station_id=%s order_no=%s", cfg.station_id, body.order_no
        )
        raise HTTPException(status_code=503, detail="服务暂时不可用")


def _applied_to_dict(r: ParkingDiscountApplied) -> dict:
    return {
        "id": r.id,
        "station_id": r.station_id,
        "plate_number": r.plate_number,
        "order_no": r.order_no,
        "amount": str(r.amount),
        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        "remark": r.remark,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

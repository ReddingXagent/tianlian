"""
管理后台 - 互联互通对接 API (SPEC §2.5)

- /admin/interconnect/configs   平台接入配置 CRUD + 联调测试
- /admin/interconnect/orders    导流订单查询 + 手动录入
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import require_role
from app.core.response import success_response, paginated_response
from app.models.admin_interconnect import (
    InterconnectConfig, InterconnectOrder,
    PLATFORM_CODES, AUTH_TYPES, CONFIG_STATUS, ORDER_STATUS,
)

router = APIRouter(dependencies=[Depends(require_role("admin"))])


# ========== Schemas ==========

class ConfigCreate(BaseModel):
    platform_name: str = Field(..., max_length=100, description="平台名称")
    platform_code: str = Field(..., max_length=50, description="平台编码 huawei/sgcc/csg/teld/other")
    api_base_url: str = Field(..., max_length=500, description="API接入地址")
    auth_type: Literal["apikey", "oauth"] = Field("apikey", description="认证方式 apikey/oauth")
    auth_params: Optional[dict] = Field(None, description="认证参数")
    revenue_share_ratio: Decimal = Field(Decimal("0.0000"), description="我方分成比例 0.7=70%")
    data_sync_interval: int = Field(300, description="同步间隔(秒)")
    status: Literal["active", "inactive"] = Field("active", description="状态 active/inactive")
    remark: Optional[str] = None


class ConfigUpdate(BaseModel):
    platform_name: Optional[str] = None
    platform_code: Optional[str] = None
    api_base_url: Optional[str] = None
    auth_type: Optional[Literal["apikey", "oauth"]] = None
    auth_params: Optional[dict] = None
    revenue_share_ratio: Optional[Decimal] = None
    data_sync_interval: Optional[int] = None
    status: Optional[Literal["active", "inactive"]] = None
    remark: Optional[str] = None


class OrderCreate(BaseModel):
    platform_id: int
    platform_code: str = Field(..., max_length=50)
    outer_order_id: str = Field(..., max_length=100)
    outer_user_id: Optional[str] = None
    station_id: Optional[str] = None
    device_id: Optional[str] = None
    charge_energy_kwh: Decimal = Field(Decimal("0.00"), ge=0)
    total_amount: Decimal = Field(Decimal("0.00"), ge=0)
    our_share: Decimal = Decimal("0.00")
    partner_share: Decimal = Decimal("0.00")
    status: Literal["synced", "settled", "conflict"] = "synced"


# ========== Helpers ==========

def _dump(v: Any) -> Optional[str]:
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _load(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _config_to_dict(c: InterconnectConfig) -> dict:
    return {
        "id": c.id,
        "platform_name": c.platform_name,
        "platform_code": c.platform_code,
        "api_base_url": c.api_base_url,
        "auth_type": c.auth_type,
        "auth_params": _load(c.auth_params),
        "revenue_share_ratio": float(c.revenue_share_ratio) if c.revenue_share_ratio is not None else 0,
        "data_sync_interval": c.data_sync_interval,
        "status": c.status,
        "remark": c.remark,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _order_to_dict(o: InterconnectOrder) -> dict:
    return {
        "id": o.id,
        "platform_id": o.platform_id,
        "platform_code": o.platform_code,
        "outer_order_id": o.outer_order_id,
        "outer_user_id": o.outer_user_id,
        "station_id": o.station_id,
        "device_id": o.device_id,
        "charge_energy_kwh": float(o.charge_energy_kwh) if o.charge_energy_kwh is not None else 0,
        "total_amount": float(o.total_amount) if o.total_amount is not None else 0,
        "our_share": float(o.our_share) if o.our_share is not None else 0,
        "partner_share": float(o.partner_share) if o.partner_share is not None else 0,
        "status": o.status,
        "synced_at": o.synced_at.isoformat() if o.synced_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# ========== 配置 CRUD ==========

@router.get("/configs", summary="互联互通平台配置列表")
def list_configs(
    platform_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="按平台名称模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(InterconnectConfig)
    if platform_code:
        q = q.filter(InterconnectConfig.platform_code == platform_code)
    if status:
        q = q.filter(InterconnectConfig.status == status)
    if keyword:
        q = q.filter(InterconnectConfig.platform_name.like(f"%{keyword}%"))

    total = q.count()
    items = q.order_by(InterconnectConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_config_to_dict(c) for c in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/configs", summary="新增互联互通平台配置")
def create_config(data: ConfigCreate, db: Session = Depends(get_db)):
    if data.platform_code not in PLATFORM_CODES:
        raise HTTPException(400, f"platform_code 取值: {PLATFORM_CODES}")
    if data.auth_type not in AUTH_TYPES:
        raise HTTPException(400, f"auth_type 取值: {AUTH_TYPES}")
    if data.status not in CONFIG_STATUS:
        raise HTTPException(400, f"status 取值: {CONFIG_STATUS}")

    cfg = InterconnectConfig(
        platform_name=data.platform_name,
        platform_code=data.platform_code,
        api_base_url=data.api_base_url,
        auth_type=data.auth_type,
        auth_params=_dump(data.auth_params),
        revenue_share_ratio=data.revenue_share_ratio,
        data_sync_interval=data.data_sync_interval,
        status=data.status,
        remark=data.remark,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return success_response(_config_to_dict(cfg), message="平台配置已创建")


@router.get("/configs/{config_id}", summary="平台配置详情")
def get_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.query(InterconnectConfig).filter(InterconnectConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "平台配置不存在")
    return success_response(_config_to_dict(cfg))


@router.put("/configs/{config_id}", summary="更新平台配置")
def update_config(config_id: int, data: ConfigUpdate, db: Session = Depends(get_db)):
    cfg = db.query(InterconnectConfig).filter(InterconnectConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "平台配置不存在")

    payload = data.model_dump(exclude_unset=True)
    if "platform_code" in payload and payload["platform_code"] not in PLATFORM_CODES:
        raise HTTPException(400, f"platform_code 取值: {PLATFORM_CODES}")
    if "auth_type" in payload and payload["auth_type"] not in AUTH_TYPES:
        raise HTTPException(400, f"auth_type 取值: {AUTH_TYPES}")
    if "status" in payload and payload["status"] not in CONFIG_STATUS:
        raise HTTPException(400, f"status 取值: {CONFIG_STATUS}")

    for k, v in payload.items():
        if k == "auth_params":
            cfg.auth_params = _dump(v)
        else:
            setattr(cfg, k, v)

    db.commit()
    db.refresh(cfg)
    return success_response(_config_to_dict(cfg), message="平台配置已更新")


@router.delete("/configs/{config_id}", summary="删除平台配置")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.query(InterconnectConfig).filter(InterconnectConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "平台配置不存在")
    db.delete(cfg)
    db.commit()
    return success_response({"id": config_id}, message="平台配置已删除")


@router.post("/configs/{config_id}/test", summary="联调测试(模拟)")
def test_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.query(InterconnectConfig).filter(InterconnectConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(404, "平台配置不存在")
    # 模拟联调: 校验地址可达 + 认证可用
    ok = cfg.api_base_url.startswith("http")
    return success_response({
        "config_id": cfg.id,
        "platform_name": cfg.platform_name,
        "reachable": ok,
        "auth_ok": ok,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }, message="联调测试完成" if ok else "联调测试失败")


# ========== 订单查询 ==========

@router.get("/orders", summary="互联互通订单列表")
def list_orders(
    platform_id: Optional[int] = Query(None),
    platform_code: Optional[str] = Query(None, description="来源平台筛选"),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="外部订单号模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(InterconnectOrder)
    if platform_id is not None:
        q = q.filter(InterconnectOrder.platform_id == platform_id)
    if platform_code:
        q = q.filter(InterconnectOrder.platform_code == platform_code)
    if status:
        q = q.filter(InterconnectOrder.status == status)
    if keyword:
        q = q.filter(InterconnectOrder.outer_order_id.like(f"%{keyword}%"))

    total = q.count()
    items = q.order_by(InterconnectOrder.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_order_to_dict(o) for o in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/orders/{order_id}", summary="订单详情")
def get_order(order_id: int, db: Session = Depends(get_db)):
    o = db.query(InterconnectOrder).filter(InterconnectOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    return success_response(_order_to_dict(o))


@router.post("/orders", summary="手动录入导流订单")
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    cfg = db.query(InterconnectConfig).filter(InterconnectConfig.id == data.platform_id).first()
    if not cfg:
        raise HTTPException(404, "平台配置不存在")
    if data.platform_code not in PLATFORM_CODES:
        raise HTTPException(400, f"platform_code 取值: {PLATFORM_CODES}")
    if data.status not in ORDER_STATUS:
        raise HTTPException(400, f"status 取值: {ORDER_STATUS}")

    o = InterconnectOrder(
        platform_id=data.platform_id,
        platform_code=data.platform_code,
        outer_order_id=data.outer_order_id,
        outer_user_id=data.outer_user_id,
        station_id=data.station_id,
        device_id=data.device_id,
        charge_energy_kwh=data.charge_energy_kwh,
        total_amount=data.total_amount,
        our_share=data.our_share,
        partner_share=data.partner_share,
        status=data.status,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return success_response(_order_to_dict(o), message="订单已录入")

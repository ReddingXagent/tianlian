"""
管理后台 - 边缘网关 SN 平台化管理 API (任务卡 e940c9f4)

平台提供方同时提供边缘网关硬件, 其 SN 在平台管理界面操作管理。
本模块面向"硬件发货台账"生命周期 (inventory → shipped → bound → online → decommissioned),
与运行态的 /gateways (Gateway online/offline/fault 设备表) 正交。

端点 (全 require_platform_admin):
- POST /admin/edge-gateways/generate        批量生成 SN 入库 (status=inventory)
- GET  /admin/edge-gateways                 库存列表 (status/batch 筛选 + 分页)
- POST /admin/edge-gateways/{sn}/ship       出库/发货 (inventory/shipped/bound → shipped)
- POST /admin/edge-gateways/{sn}/bind       绑定场站 (校验站点存在, → bound)
- POST /admin/edge-gateways/{sn}/unbind     解绑 (→ inventory)
- POST /admin/edge-gateways/{sn}/online     网关接入钩子 (→ online + last_online_at)
- POST /admin/edge-gateways/{sn}/decommission 退役 (任意态 → decommissioned)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.edge_gateway import (
    EdgeGateway,
    EDGE_GATEWAY_STATUS_INVENTORY,
    EDGE_GATEWAY_STATUS_SHIPPED,
    EDGE_GATEWAY_STATUS_BOUND,
    EDGE_GATEWAY_STATUS_ONLINE,
    EDGE_GATEWAY_STATUS_DECOMMISSIONED,
    EDGE_GATEWAY_STATUS_VALUES,
)
from app.models.station import Station
from app.services.code_generator import CodeGenerator

router = APIRouter(
    prefix="/admin/edge-gateways",
    dependencies=[Depends(require_platform_admin)],
)


# ==================== Schemas ====================

class SNGenerateRequest(BaseModel):
    count: int = Field(10, ge=1, le=1000, description="生成数量 1-1000")
    region: str = Field("HN", description="区域码, 如 HN(河南)/GD(广东)")
    batch: Optional[str] = Field(None, description="批次号, 便于按批追溯")


class BindRequest(BaseModel):
    station_id: int = Field(..., ge=1, description="绑定场站 ID")


class OnlineRequest(BaseModel):
    firmware_version: Optional[str] = Field(None, description="上报的固件版本")


# ==================== Helpers ====================

def _to_dict(eg: EdgeGateway) -> dict:
    return {
        "id": eg.id,
        "sn": eg.sn,
        "batch": eg.batch,
        "status": eg.status,
        "station_id": eg.station_id,
        "firmware_version": eg.firmware_version,
        "last_online_at": eg.last_online_at.isoformat() if eg.last_online_at else None,
        "created_at": eg.created_at.isoformat() if eg.created_at else None,
    }


def _get_by_sn(db: Session, sn: str) -> EdgeGateway:
    eg = db.execute(select(EdgeGateway).where(EdgeGateway.sn == sn)).scalar_one_or_none()
    if eg is None:
        raise HTTPException(status_code=404, detail=f"网关 SN 不存在: {sn}")
    return eg


def _assert_station_exists(db: Session, station_id: int) -> None:
    """绑定前校验站点存在, 不存在 → 404 (与 conftest 既有 404 契约一致)。"""
    exists = db.execute(
        select(func.count()).select_from(Station).where(Station.id == station_id)
    ).scalar_one()
    if not exists:
        raise HTTPException(status_code=404, detail=f"场站不存在: {station_id}")


# ==================== SN 生成 ====================

@router.post("/generate", summary="批量生成边缘网关 SN 入库")
def generate_sn(req: SNGenerateRequest, db: Session = Depends(get_db)):
    """批量生成 SN 并入库, status=inventory。

    复用 CodeGenerator.generate_gateway_sn (G 类 9 位: G + 区域码(2) + 序号(6))。
    逐个生成 + 入库置于同一事务, 统一 commit, 保证序列自增与 EdgeGateway 行原子落库。
    """
    try:
        sns = []
        now = datetime.now(timezone.utc)
        for _ in range(req.count):
            sn = CodeGenerator.generate_gateway_sn(region=req.region, db=db)
            db.add(EdgeGateway(
                sn=sn,
                batch=req.batch,
                status=EDGE_GATEWAY_STATUS_INVENTORY,
                created_at=now,
            ))
            sns.append(sn)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return success_response({"sn_list": sns, "count": len(sns)}, message="SN 生成成功")


# ==================== 列表 ====================

@router.get("", summary="边缘网关库存列表")
def list_edge_gateways(
    status: Optional[str] = Query(None, description="状态筛选 inventory/shipped/bound/online/decommissioned"),
    batch: Optional[str] = Query(None, description="批次号精确筛选"),
    keyword: Optional[str] = Query(None, description="按 SN 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if status is not None and status not in EDGE_GATEWAY_STATUS_VALUES:
        raise HTTPException(status_code=400, detail=f"非法状态值: {status}")

    stmt = select(EdgeGateway)
    if status:
        stmt = stmt.where(EdgeGateway.status == status)
    if batch:
        stmt = stmt.where(EdgeGateway.batch == batch)
    if keyword:
        stmt = stmt.where(EdgeGateway.sn.like(f"%{keyword}%"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(EdgeGateway.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return paginated_response(
        items=[_to_dict(r) for r in rows],
        total=total, page=page, page_size=page_size,
    )


# ==================== 状态流转 ====================

@router.post("/{sn}/ship", summary="出库/发货 (inventory/shipped/bound → shipped)")
def ship(sn: str, db: Session = Depends(get_db)):
    eg = _get_by_sn(db, sn)
    if eg.status == EDGE_GATEWAY_STATUS_DECOMMISSIONED:
        raise HTTPException(status_code=400, detail="已退役的网关不可出库")
    eg.status = EDGE_GATEWAY_STATUS_SHIPPED
    db.commit()
    db.refresh(eg)
    return success_response(_to_dict(eg), message="已出库")


@router.post("/{sn}/bind", summary="绑定场站 (校验站点存在, → bound)")
def bind(sn: str, req: BindRequest, db: Session = Depends(get_db)):
    eg = _get_by_sn(db, sn)
    if eg.status == EDGE_GATEWAY_STATUS_DECOMMISSIONED:
        raise HTTPException(status_code=400, detail="已退役的网关不可绑定")
    _assert_station_exists(db, req.station_id)
    eg.status = EDGE_GATEWAY_STATUS_BOUND
    eg.station_id = req.station_id
    db.commit()
    db.refresh(eg)
    return success_response(_to_dict(eg), message="已绑定场站")


@router.post("/{sn}/unbind", summary="解绑场站 (→ inventory)")
def unbind(sn: str, db: Session = Depends(get_db)):
    eg = _get_by_sn(db, sn)
    if eg.station_id is None:
        raise HTTPException(status_code=400, detail="该网关未绑定场站, 无需解绑")
    if eg.status == EDGE_GATEWAY_STATUS_DECOMMISSIONED:
        raise HTTPException(status_code=400, detail="已退役的网关不可解绑")
    eg.status = EDGE_GATEWAY_STATUS_INVENTORY
    eg.station_id = None
    db.commit()
    db.refresh(eg)
    return success_response(_to_dict(eg), message="已解绑")


@router.post("/{sn}/online", summary="网关接入钩子 (首次/重连 → online + last_online_at)")
def online(sn: str, req: Optional[OnlineRequest] = None, db: Session = Depends(get_db)):
    """网关首次连上平台 → status=online + last_online_at 更新。

    留接口: 实际由网关 MQTT/WS 接入层调用, body 可缺省 (网关上线未必带固件版本)。
    这里提供管理触发入口, firmware_version 可选上报。
    """
    eg = _get_by_sn(db, sn)
    if eg.status == EDGE_GATEWAY_STATUS_DECOMMISSIONED:
        raise HTTPException(status_code=400, detail="已退役的网关不可上线")
    eg.status = EDGE_GATEWAY_STATUS_ONLINE
    eg.last_online_at = datetime.now(timezone.utc)
    if req and req.firmware_version:
        eg.firmware_version = req.firmware_version
    db.commit()
    db.refresh(eg)
    return success_response(_to_dict(eg), message="网关已上线")


@router.post("/{sn}/decommission", summary="退役 (任意态 → decommissioned)")
def decommission(sn: str, db: Session = Depends(get_db)):
    eg = _get_by_sn(db, sn)
    eg.status = EDGE_GATEWAY_STATUS_DECOMMISSIONED
    db.commit()
    db.refresh(eg)
    return success_response(_to_dict(eg), message="网关已退役")

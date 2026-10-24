"""数字孪生可视化 API - 3D 设备模型配置 + 场景聚合。

字段契约以 frontend/src/pages/DigitalTwin/hooks/useDigitalTwin.ts 为唯一真相：
- DigitalTwinModel: 展开式字段 (scale_x/y/z, position_x/y/z, rotation_x/y/z,
  color_primary/secondary/accent, animations, status_mapping)，与 ORM model 列一一对应。
- DigitalTwinScene: {station_id, name, scene_config(JSON)}。
- DigitalTwinDataPoint: {device_id, param_key, display_name, ...}。
- GET /realtime: 前端 getRealtime 期望 {station, scene, devices:[{device, digital_twin_config}]}；
  遥测数值前端走 /telemetry/device/{id}/latest 独立轮询，故本接口不查 telemetry。

N+1 修复: /realtime 与 /scenes/{id}/layout 对 digital_twin_config 采用 device_id IN(...)
批量加载（O(1)），而非逐设备查询。
"""
import logging
from typing import Literal, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import paginated_response
from app.models.digital_twin import (
    DigitalTwinModel, DigitalTwinScene, DigitalTwinDataPoint, ThreeDModelType,
)
from app.models.device import Device, DeviceType
from app.models.station import Station
from app.models.user import User
from app.api.deps import get_current_user, is_platform_admin
from app.middleware.permission import require_write_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["数字孪生"], dependencies=[Depends(require_write_permission("device:edit"))])


# ─── 字段映射辅助 ───

# Device.type → ThreeDModelType 推断（init-default 为站点设备批量建默认孪生配置）
_DEVICE_TYPE_TO_MODEL = {
    DeviceType.PV_INVERTER: ThreeDModelType.SOLAR_INVERTER,
    DeviceType.BATTERY_INVERTER: ThreeDModelType.BATTERY_INVERTER,
    DeviceType.PCS: ThreeDModelType.PCS,
    DeviceType.BATTERY: ThreeDModelType.BATTERY_RACK,
    DeviceType.CHARGER_DC: ThreeDModelType.CHARGER_DC,
    DeviceType.CHARGER_AC: ThreeDModelType.CHARGER_AC,
    DeviceType.V2G_CHARGER: ThreeDModelType.CHARGER_DC,
    DeviceType.METER: ThreeDModelType.METER,
    DeviceType.GATEWAY: ThreeDModelType.GATEWAY,
}


def _coerce_model_type(value: Optional[str]) -> Optional[ThreeDModelType]:
    """前端传 string → 校验为合法 ThreeDModelType；非法值 400。"""
    if value is None:
        return None
    try:
        return ThreeDModelType(value)
    except ValueError:
        legal = [t.value for t in ThreeDModelType]
        raise HTTPException(
            status_code=400,
            detail=f"非法 model_type '{value}'，合法值: {legal}",
        )


# DigitalTwinDataPoint.visual_type 合法值（与 ORM 列注释一致）
_VALID_VISUAL_TYPES = ("color", "scale", "position", "animation", "text")


def _coerce_visual_type(value: Optional[str]) -> Optional[str]:
    """校验 visual_type 为合法值；非法值 400（与 _coerce_model_type 风格一致）。

    visual_type 在 ORM 层是 String(30) 自由字符串，故在此做入口校验，
    不改 schema。None 视为未传（走列默认 color）。"""
    if value is None:
        return None
    if value not in _VALID_VISUAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"非法 visual_type '{value}'，合法值: {list(_VALID_VISUAL_TYPES)}",
        )
    return value


def _model_to_dict(m: DigitalTwinModel) -> dict:
    """ORM → 前端契约字典（展开式字段，enum 转 value）。"""
    return {
        "id": m.id,
        "device_id": m.device_id,
        "model_type": m.model_type.value if m.model_type else None,
        "scale_x": m.scale_x,
        "scale_y": m.scale_y,
        "scale_z": m.scale_z,
        "position_x": m.position_x,
        "position_y": m.position_y,
        "position_z": m.position_z,
        "rotation_x": m.rotation_x,
        "rotation_y": m.rotation_y,
        "rotation_z": m.rotation_z,
        "color_primary": m.color_primary,
        "color_secondary": m.color_secondary,
        "color_accent": m.color_accent,
        "animations": m.animations,
        "status_mapping": m.status_mapping,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _scene_to_dict(s: DigitalTwinScene) -> dict:
    return {
        "id": s.id,
        "station_id": s.station_id,
        "name": s.name,
        "scene_config": s.scene_config,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _data_point_to_dict(dp: DigitalTwinDataPoint) -> dict:
    return {
        "id": dp.id,
        "device_id": dp.device_id,
        "param_key": dp.param_key,
        "display_name": dp.display_name,
        "unit": dp.unit,
        "visual_type": dp.visual_type,
        "normal_range": dp.normal_range,
        "warn_range": dp.warn_range,
        "danger_range": dp.danger_range,
        "normal_color": dp.normal_color,
        "warn_color": dp.warn_color,
        "danger_color": dp.danger_color,
        "animation_config": dp.animation_config,
        "show_value": dp.show_value,
        "show_unit": dp.show_unit,
        "decimal_places": dp.decimal_places,
        "created_at": dp.created_at,
        "updated_at": dp.updated_at,
    }


def _device_to_dict(d: Device) -> dict:
    """Device → 前端 DeviceData.device 契约字段。"""
    return {
        "id": d.id,
        "name": d.name,
        "type": d.type.value if d.type else None,
        "status": d.status.value if d.status else None,
        "health_score": d.health_score,
        "model": d.model,
        "location": d.location,
        "last_heartbeat": d.last_heartbeat,
        "total_run_hours": d.total_run_hours,
        "total_generation_kwh": d.total_generation_kwh,
        "total_charge_kwh": d.total_charge_kwh,
    }


def _load_configs_by_device_ids(db: Session, device_ids: List[int]) -> dict:
    """批量按 device_id 加载孪生配置（IN 查询，O(1)），返回 {device_id: DigitalTwinModel}。"""
    if not device_ids:
        return {}
    rows = db.query(DigitalTwinModel).filter(
        DigitalTwinModel.device_id.in_(device_ids)
    ).all()
    return {r.device_id: r for r in rows}


# ─── 团队归属校验（任务卡 1f13817b）───
# 孪生配置本身无 team_id 列，归属经 device→station→team 间接判定；
# scene 直接带 station_id。admin/super_admin 平台级豁免。跨团队一律 404
# （不泄露资源存在），与 is_platform_admin / assert_station_team_access 同源。

def _device_team_id(db: Session, device_id: int):
    """device → station.team_id（经 join，单次查询）；device/station 不存在 → None。"""
    row = (
        db.query(Station.team_id)
        .join(Device, Device.station_id == Station.id)
        .filter(Device.id == device_id)
        .first()
    )
    return row[0] if row else None


def _station_team_id(db: Session, station_id: int):
    """station → team_id；不存在 → None。"""
    row = db.query(Station.team_id).filter(Station.id == station_id).first()
    return row[0] if row else None


def _check_device_team(db: Session, device_id: int, user: User, msg: str = "设备不存在") -> None:
    """校验 device 经 station 归属本 team；admin 豁免；不匹配/不存在 → 404。"""
    if is_platform_admin(user):
        return
    team_id = _device_team_id(db, device_id)
    if team_id is None or user.team_id is None or team_id != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _check_station_team(db: Session, station_id: int, user: User, msg: str = "站点不存在") -> None:
    """校验 station 归属本 team；admin 豁免；不匹配/不存在 → 404。"""
    if is_platform_admin(user):
        return
    team_id = _station_team_id(db, station_id)
    if team_id is None or user.team_id is None or team_id != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


# ─── Schemas（请求校验，字段对齐 ORM 展开式列）───

class ModelCreate(BaseModel):
    device_id: int
    model_type: str
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    scale_z: Optional[float] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_x: Optional[float] = None
    rotation_y: Optional[float] = None
    rotation_z: Optional[float] = None
    color_primary: Optional[str] = None
    color_secondary: Optional[str] = None
    color_accent: Optional[str] = None
    animations: Optional[dict] = None
    status_mapping: Optional[dict] = None


class ModelUpdate(BaseModel):
    model_type: Optional[str] = None
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    scale_z: Optional[float] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_x: Optional[float] = None
    rotation_y: Optional[float] = None
    rotation_z: Optional[float] = None
    color_primary: Optional[str] = None
    color_secondary: Optional[str] = None
    color_accent: Optional[str] = None
    animations: Optional[dict] = None
    status_mapping: Optional[dict] = None


class SceneCreate(BaseModel):
    station_id: int
    name: str
    scene_config: dict = {}


class SceneUpdate(BaseModel):
    name: Optional[str] = None
    scene_config: Optional[dict] = None


class DataPointCreate(BaseModel):
    device_id: int
    param_key: str = Field(..., max_length=100)
    display_name: str = Field(..., max_length=100)
    unit: str = Field("", max_length=20)
    visual_type: str = "color"
    normal_range: Optional[dict] = None
    warn_range: Optional[dict] = None
    danger_range: Optional[dict] = None
    normal_color: Optional[str] = None
    warn_color: Optional[str] = None
    danger_color: Optional[str] = None
    animation_config: Optional[dict] = None
    show_value: Optional[bool] = None
    show_unit: Optional[bool] = None
    decimal_places: Optional[int] = None


class DataPointUpdate(BaseModel):
    param_key: Optional[str] = None
    display_name: Optional[str] = None
    unit: Optional[str] = None
    visual_type: Optional[str] = None
    normal_range: Optional[dict] = None
    warn_range: Optional[dict] = None
    danger_range: Optional[dict] = None
    normal_color: Optional[str] = None
    warn_color: Optional[str] = None
    danger_color: Optional[str] = None
    animation_config: Optional[dict] = None
    show_value: Optional[bool] = None
    show_unit: Optional[bool] = None
    decimal_places: Optional[int] = None


# ─── Models CRUD ───

@router.get("/models")
def list_models(
    device_id: Optional[int] = Query(None),
    station_id: Optional[int] = Query(None),
    model_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出孪生模型配置。station_id 过滤经 Device join（model 本身无 station_id 列）。

    team scoping: 非 admin 仅返回本 team 设备的配置（经 device→station→team）。
    """
    q = db.query(DigitalTwinModel)
    if station_id or not is_platform_admin(user):
        q = q.join(Device, DigitalTwinModel.device_id == Device.id)
    if not is_platform_admin(user):
        q = q.join(Station, Device.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if device_id:
        q = q.filter(DigitalTwinModel.device_id == device_id)
    if station_id:
        q = q.filter(Device.station_id == station_id)
    if model_type:
        q = q.filter(DigitalTwinModel.model_type == _coerce_model_type(model_type))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_model_to_dict(m) for m in items], total, page, page_size)


@router.post("/models", status_code=201)
def create_model(
    data: ModelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_device_team(db, data.device_id, user)  # 不存在/跨团队 → 404
    if db.query(DigitalTwinModel).filter(DigitalTwinModel.device_id == data.device_id).first():
        raise HTTPException(409, "该设备已存在孪生配置")
    payload = data.model_dump(exclude_unset=False)
    payload["model_type"] = _coerce_model_type(data.model_type)
    model = DigitalTwinModel(**payload)
    try:
        db.add(model)
        db.commit()
        db.refresh(model)
    except Exception:
        db.rollback()
        logger.exception("创建孪生模型配置失败 device_id=%s", data.device_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _model_to_dict(model)


@router.get("/models/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model = db.query(DigitalTwinModel).filter(DigitalTwinModel.id == model_id).first()
    if not model:
        raise HTTPException(404, "模型不存在")
    _check_device_team(db, model.device_id, user, "模型不存在")
    return _model_to_dict(model)


@router.put("/models/{model_id}")
def update_model(
    model_id: int, data: ModelUpdate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    model = db.query(DigitalTwinModel).filter(DigitalTwinModel.id == model_id).first()
    if not model:
        raise HTTPException(404, "模型不存在")
    _check_device_team(db, model.device_id, user, "模型不存在")
    updates = data.model_dump(exclude_unset=True)
    if "model_type" in updates:
        updates["model_type"] = _coerce_model_type(updates["model_type"])
    for k, v in updates.items():
        setattr(model, k, v)
    try:
        db.commit()
        db.refresh(model)
    except Exception:
        db.rollback()
        logger.exception("更新孪生模型配置失败 model_id=%s", model_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _model_to_dict(model)


@router.delete("/models/{model_id}")
def delete_model(
    model_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    model = db.query(DigitalTwinModel).filter(DigitalTwinModel.id == model_id).first()
    if not model:
        raise HTTPException(404, "模型不存在")
    _check_device_team(db, model.device_id, user, "模型不存在")
    try:
        db.delete(model)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("删除孪生模型配置失败 model_id=%s", model_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return {"message": "已删除"}


# ─── Scenes CRUD ───

@router.get("/scenes")
def list_scenes(
    station_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    q = db.query(DigitalTwinScene)
    if not is_platform_admin(user):
        q = q.join(Station, DigitalTwinScene.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if station_id:
        q = q.filter(DigitalTwinScene.station_id == station_id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_scene_to_dict(s) for s in items], total, page, page_size)


@router.post("/scenes", status_code=201)
def create_scene(
    data: SceneCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _check_station_team(db, data.station_id, user)  # 不存在/跨团队 → 404
    scene = DigitalTwinScene(**data.model_dump())
    try:
        db.add(scene)
        db.commit()
        db.refresh(scene)
    except Exception:
        db.rollback()
        logger.exception("创建孪生场景失败 station_id=%s", data.station_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _scene_to_dict(scene)


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    scene = db.query(DigitalTwinScene).filter(DigitalTwinScene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    _check_station_team(db, scene.station_id, user, "场景不存在")
    return _scene_to_dict(scene)


@router.put("/scenes/{scene_id}")
def update_scene(
    scene_id: int, data: SceneUpdate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    scene = db.query(DigitalTwinScene).filter(DigitalTwinScene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    _check_station_team(db, scene.station_id, user, "场景不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(scene, k, v)
    try:
        db.commit()
        db.refresh(scene)
    except Exception:
        db.rollback()
        logger.exception("更新孪生场景失败 scene_id=%s", scene_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _scene_to_dict(scene)


@router.delete("/scenes/{scene_id}")
def delete_scene(
    scene_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    scene = db.query(DigitalTwinScene).filter(DigitalTwinScene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    _check_station_team(db, scene.station_id, user, "场景不存在")
    try:
        db.delete(scene)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("删除孪生场景失败 scene_id=%s", scene_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return {"message": "已删除"}


# ─── Data Points CRUD ───

@router.get("/data-points")
def list_data_points(
    device_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    q = db.query(DigitalTwinDataPoint)
    if not is_platform_admin(user):
        q = q.join(Device, DigitalTwinDataPoint.device_id == Device.id) \
             .join(Station, Device.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if device_id:
        q = q.filter(DigitalTwinDataPoint.device_id == device_id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_data_point_to_dict(dp) for dp in items], total, page, page_size)


@router.post("/data-points", status_code=201)
def create_data_point(
    data: DataPointCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    _check_device_team(db, data.device_id, user)  # 不存在/跨团队 → 404
    payload = data.model_dump()
    payload["visual_type"] = _coerce_visual_type(data.visual_type) or "color"
    dp = DigitalTwinDataPoint(**payload)
    try:
        db.add(dp)
        db.commit()
        db.refresh(dp)
    except Exception:
        db.rollback()
        logger.exception("创建孪生数据映射失败 device_id=%s", data.device_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _data_point_to_dict(dp)


@router.put("/data-points/{dp_id}")
def update_data_point(
    dp_id: int, data: DataPointUpdate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    dp = db.query(DigitalTwinDataPoint).filter(DigitalTwinDataPoint.id == dp_id).first()
    if not dp:
        raise HTTPException(404, "数据映射不存在")
    _check_device_team(db, dp.device_id, user, "数据映射不存在")
    updates = data.model_dump(exclude_unset=True)
    if "visual_type" in updates:
        updates["visual_type"] = _coerce_visual_type(updates["visual_type"]) or "color"
    for k, v in updates.items():
        setattr(dp, k, v)
    try:
        db.commit()
        db.refresh(dp)
    except Exception:
        db.rollback()
        logger.exception("更新孪生数据映射失败 dp_id=%s", dp_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return _data_point_to_dict(dp)


@router.delete("/data-points/{dp_id}")
def delete_data_point(
    dp_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    dp = db.query(DigitalTwinDataPoint).filter(DigitalTwinDataPoint.id == dp_id).first()
    if not dp:
        raise HTTPException(404, "数据映射不存在")
    _check_device_team(db, dp.device_id, user, "数据映射不存在")
    try:
        db.delete(dp)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("删除孪生数据映射失败 dp_id=%s", dp_id)
        raise HTTPException(status_code=500, detail="内部错误")
    return {"message": "已删除"}


# ─── Realtime（前端 getRealtime 契约：{station, scene, devices}）───

@router.get("/realtime")
def get_realtime_data(
    station_id: Optional[int] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """聚合站点 + 场景 + 设备(含孪生配置)。

    前端 useDigitalTwin.getRealtime 消费此结构；遥测数值前端走
    /telemetry/device/{id}/latest 独立轮询，故本接口不查 telemetry。

    station_id 提供但站点不存在 → 404（与 /scenes/{id}/layout 一致）；
    station_id 缺省 → 返回 {station:null, scene:null, devices:[]}。

    N+1 修复: 设备孪生配置用 device_id IN(...) 一次性批量加载，
    查询数 O(1)，不随设备数线性增长。
    """
    station = None
    scene = None
    devices_out = []

    if station_id:
        s = db.query(Station).filter(Station.id == station_id).first()
        if not s:
            raise HTTPException(404, "站点不存在")
        if not is_platform_admin(user) and (
            s.team_id is None or user.team_id is None or s.team_id != user.team_id
        ):
            raise HTTPException(404, "站点不存在")
        station = {"id": s.id, "name": s.name, "address": s.address}

        sc = db.query(DigitalTwinScene) \
            .filter(DigitalTwinScene.station_id == station_id) \
            .order_by(DigitalTwinScene.updated_at.desc()) \
            .first()
        if sc:
            scene = _scene_to_dict(sc)

        devs = db.query(Device).filter(Device.station_id == station_id).all()
        configs = _load_configs_by_device_ids(db, [d.id for d in devs])
        for d in devs:
            cfg = configs.get(d.id)
            devices_out.append({
                "device": _device_to_dict(d),
                "digital_twin_config": _model_to_dict(cfg) if cfg else None,
            })

    return {"station": station, "scene": scene, "devices": devices_out}


# ─── Scene Layout（场景 + 其站点设备孪生模型）───

@router.get("/scenes/{scene_id}/layout")
def get_scene_layout(
    scene_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """获取场景布局：场景配置 + 该站点全部设备孪生模型（批量加载，避免 N+1）。"""
    scene = db.query(DigitalTwinScene).filter(DigitalTwinScene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    _check_station_team(db, scene.station_id, user, "场景不存在")
    devs = db.query(Device).filter(Device.station_id == scene.station_id).all()
    configs = _load_configs_by_device_ids(db, [d.id for d in devs])
    return {
        "scene": _scene_to_dict(scene),
        "models": [_model_to_dict(c) for c in configs.values()],
    }


# ─── Init Default（为站点初始化默认场景 + 设备孪生配置）───

@router.post("/init-default")
def init_default_scene(
    station_id: int = Query(..., description="为目标站点初始化默认数字孪生"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """为站点初始化默认场景；若站点设备尚无孪生配置，按设备类型批量生成默认配置。"""
    _check_station_team(db, station_id, user)  # 先校验归属，再做幂等返回（防跨团队泄露存在）
    existing = db.query(DigitalTwinScene) \
        .filter(DigitalTwinScene.station_id == station_id).first()
    if existing:
        return {"message": "默认场景已存在", "scene_id": existing.id, "models_count": 0}

    if not db.query(Station).filter(Station.id == station_id).first():
        raise HTTPException(404, "站点不存在")

    scene = DigitalTwinScene(
        station_id=station_id,
        name="光储充全景",
        scene_config={
            "background": "#0a0a1a",
            "ambient_light": 0.5,
            "camera": {"position": [15, 10, 18], "fov": 50},
        },
    )
    try:
        db.add(scene)
        db.flush()

        # 为站点尚无配置的设备批量建默认孪生配置（按 device type 推断 model_type）
        devs = db.query(Device).filter(Device.station_id == station_id).all()
        configs = _load_configs_by_device_ids(db, [d.id for d in devs])
        created = 0
        for d in devs:
            if d.id in configs:
                continue
            mtype = _DEVICE_TYPE_TO_MODEL.get(d.type, ThreeDModelType.GATEWAY)
            db.add(DigitalTwinModel(device_id=d.id, model_type=mtype))
            created += 1

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("初始化默认孪生场景失败 station_id=%s", station_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(scene)
    return {
        "message": "默认场景初始化成功",
        "scene_id": scene.id,
        "models_count": created,
    }

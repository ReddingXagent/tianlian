"""设备管理 API - 真实数据库版 + 健康度计算（拆分为子路由包）。

原 ``app/api/v1/devices.py``（1006 行）按域拆分为同包子模块；本包 ``__init__``
按原文件端点声明顺序聚合各子模块 router，并保留两类必须内联的端点：

1. 被单测 patch 的端点（``control_device`` / ``get_maintenance_due`` /
   ``run_maintenance_check``）——它们引用的 ``DeviceControlService`` /
   ``DeviceControlLog`` / ``maintenance_schedule_checker`` 仍绑定在本命名空间，
   故 ``patch("app.api.v1.devices.X")`` 行为不变。
2. 集合根空 path 端点（``GET ""`` list_devices / ``POST ""`` create_device）——
   FastAPI 不允许以空 prefix ``include_router`` 一个含空 path 路由的子 router，
   故直接装饰在被 v1 带 ``prefix="/devices"`` 消费的本 router 上（与原文件形态一致）。

端点集合、router 级鉴权依赖（``get_current_user`` +
``require_write_permission("device:edit")``）均不变；注册顺序除 create_device
（原 #5）归并到集合根（与 list_devices 同组）外，其余端点相对顺序不变，且各路由
path/method 互不重叠，匹配行为零变化。``app.api.v1.devices.router`` 导入路径保持
向后兼容。

子模块：crud / health / maintenance_plan / config；共享定义见 ``_shared``。
"""
import secrets

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, resolve_team_filter
from app.models.device import Device, DeviceType, DeviceStatus, ProvisionStatus, ProtocolType
from app.models.device_control_log import DeviceControlLog
from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger
from app.models.station import Station
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.device_control_service import DeviceControlService
from app.services.maintenance_schedule import maintenance_schedule_checker
from app.core.response import success_response, error_response, paginated_response

from ._shared import logger, _check_device_team, _check_device_maintenance_access, _ROUTER_DEPENDENCIES
from . import crud, health, maintenance_plan, config, firmware


class DeviceCreate(BaseModel):
    sn: Optional[str] = None  # SN码=出厂序列号(铭牌唯一); 无SN场景(任务卡 1256e7fa)缺省自动生成 TLLN-<站点code前4位>-<6位hex>
    code: Optional[str] = None  # 设备编码=平台自定义业务码; 缺省时自动生成(2026-10-09 丁哥语义修正)
    name: str
    type: Literal[
        "charger_dc", "charger_ac", "v2g_charger", "pv_inverter",
        "battery_inverter", "pcs", "battery", "meter", "gateway",
    ] = "charger_dc"
    station_id: Optional[str] = None
    rated_power: Optional[float] = None
    gun_count: Optional[int] = None
    # 2026-10-09 丁哥：设备总览表单联动设备库（品牌/型号/通讯协议）
    manufacturer: Optional[str] = None   # 设备品牌（联动设备库 DeviceLibrary.brand）
    model: Optional[str] = None          # 设备型号（联动设备库 DeviceLibrary.model）
    protocol_type: Optional[str] = None  # 通讯协议（ProtocolType 枚举值）

_VALID_PROTOCOLS = {"modbus_rtu", "mqtt", "modbus_tcp", "can", "opcua", "ykc", "szbus"}


class DeviceControlRequest(BaseModel):
    """设备控制请求"""
    action: str = Field(..., max_length=50)
    parameter: Optional[str] = None  # 参数名（用于 set_param）
    value: Optional[Any] = None  # 参数值（用于 set_param）
    reset_type: Optional[str] = "soft"  # 软复位/硬复位（用于 restart）


# 设备类型 -> (遥测模型, 当前功率字段, 累计电量字段)
# v2g_charger 归入充电桩表；meter/gateway 无遥测表，不在此映射中
_DEVICE_TELEMETRY_MAP = [
    ({"pv_inverter"}, TelemetryPV, "grid_power_total", "total_generation"),
    ({"battery_inverter", "pcs", "battery"}, TelemetryBattery, "grid_power_total", "total_discharge"),
    ({"charger_dc", "charger_ac", "v2g_charger"}, TelemetryCharger, "charger_power", "charger_kwh"),
]


def _build_latest_telemetry_summary(db: Session, devices: list) -> dict:
    """按设备类型分表，用窗口函数一次性取每个设备最新一条遥测的 power/total_energy。

    每张表只发一次 SQL（row_number 取每个 device_id 下 timestamp 最新一行），
    避免循环内逐设备查询导致的 N+1。
    返回 {device_id: {"power": float|None, "total_energy": float|None}}。
    """
    summary: dict = {}
    for types, model, power_field, energy_field in _DEVICE_TELEMETRY_MAP:
        ids = [d.id for d in devices if (d.type.value if d.type else None) in types]
        if not ids:
            continue
        rn_col = func.row_number().over(
            partition_by=model.device_id,
            order_by=model.timestamp.desc(),
        ).label("rn")
        subq = (
            db.query(
                model.device_id.label("did"),
                getattr(model, power_field).label("pwr"),
                getattr(model, energy_field).label("eng"),
                rn_col,
            )
            .filter(model.device_id.in_(ids))
            .subquery()
        )
        rows = db.query(subq.c.did, subq.c.pwr, subq.c.eng).filter(subq.c.rn == 1).all()
        for did, pwr, eng in rows:
            summary[did] = {
                "power": float(pwr) if pwr is not None else None,
                "total_energy": float(eng) if eng is not None else None,
            }
    return summary


# USING get_db FROM app.core.database

router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


# ── 集合根路由：GET "" / POST "" 必须直接定义在本 router 上（见模块 docstring）。
# #1 GET "" — list_devices
@router.get("")
def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    team_id: Optional[int] = Query(None, description="按团队过滤（卡 2285f54a：admin 可指定任意团队；团队级用户仅限本团队，他团队 403）"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取设备列表。

    team scoping（任务卡 ed509541）：非 admin 仅返回本 team 设备（经 station→team）。
    可选 ``team_id`` 查询参数（卡 2285f54a）：admin 可按任意团队过滤，团队级
    用户仅允许显式指定本团队——供 Tenants TeamDataView 设备 Tab 使用。
    移除原 ``@cached`` —— 其 key 不含 user.team_id，跨用户同 URL 会命中同一缓存串数据
    （与 stations.py list 同源决策，安全优先）。
    """
    query = db.query(Device)
    scope_team = resolve_team_filter(db, user, team_id)
    if scope_team is not None:
        query = query.join(Station, Device.station_id == Station.id) \
                     .filter(Station.team_id == scope_team)
    elif not is_platform_admin(user):
        query = query.join(Station, Device.station_id == Station.id) \
                     .filter(Station.team_id == user.team_id)
    if station_id:
        query = query.filter(Device.station_id == station_id)
    if type:
        query = query.filter(Device.type == type)
    if status:
        query = query.filter(Device.status == status)

    total = query.count()
    # 按添加顺序倒序：最新添加的设备排在最上面（与站点列表同策略, 2026-10-09 丁哥要求）
    devices = (
        query.order_by(Device.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 批量取站点名（2026-10-09 丁哥: 设备详情展示所属站点）
    station_ids = list({d.station_id for d in devices if d.station_id})
    smap = {}
    if station_ids:
        for s in db.query(Station.id, Station.name).filter(Station.id.in_(station_ids)).all():
            smap[s.id] = s.name

    # 批量实时计算利用率（2026-10-09 丁哥: 24h 内充电功率>0.5kW 采样点占比; 无遥测返回库值）
    dev_ids = [d.id for d in devices]
    umap = {}
    if dev_ids:
        try:
            rows = db.execute(
                text("SELECT device_id, "
                     "COUNT(*) FILTER (WHERE charger_power > 0.5)::float / NULLIF(COUNT(*), 0) "
                     "FROM telemetry_charger "
                     "WHERE timestamp > now() - interval '24 hours' "
                     "AND device_id = ANY(:ids) GROUP BY device_id"),
                {"ids": dev_ids},
            ).all()
            umap = {r[0]: round(r[1] * 100, 1) for r in rows}
        except Exception:
            pass

    # 一次性取本页设备的最新遥测摘要（power/total_energy），按类型分表，无 N+1
    telemetry_summary = _build_latest_telemetry_summary(db, devices)

    # 序列化设备
    device_dicts = [{
        'id': d.id,
        'sn': d.sn,
        'code': d.code,
        'name': d.name,
        'type': d.type.value if d.type else 'charger_dc',
        'station_id': d.station_id,
        'station_name': smap.get(d.station_id),
        'utilization_rate': umap.get(d.id, d.utilization_rate),
        'status': d.status.value if d.status else 'offline',
        'health_score': d.health_score,
        'rated_power': d.rated_power,
        'gun_count': d.gun_count,
        'manufacturer': d.manufacturer,
        'model': d.model,
        'protocol_type': d.protocol_type.value if d.protocol_type else None,
        'power': telemetry_summary.get(d.id, {}).get('power'),
        'total_energy': telemetry_summary.get(d.id, {}).get('total_energy'),
        # 入网状态（任务卡 b26e8e60 §3）：unprovisioned/provisioning/online
        'provision_status': d.provision_status.value if d.provision_status else 'unprovisioned',
    } for d in devices]

    return paginated_response(device_dicts, total, page, page_size)


# #5(原) POST "" — create_device（与 list_devices 同为集合根，归并到此）
@router.post("")
def create_device(data: DeviceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建设备。

    team scoping（任务卡 ed509541）：device 归属经 station 间接判定。
    - 非 admin：必须指定本 team 站点（station_id），不得落到无 team 的 DEFAULT 站点；
      指定他团站点 → 404（不泄露存在）。
    - admin：保留原逻辑（未传 station_id 时自动建/用 DEFAULT 站点）。

    自助闭环（任务卡 1256e7fa）：
    - sn 缺省 → 自动生成 ``TLLN-<station_code前4位>-<6位hex大写>``；
    - 创建后生成接入凭证（charge_box_id/mqtt_username/mqtt_password/auth_token），
      provision_status=provisioning；
    - 凭证明文仅在本次响应返回一次（DB 存 mqtt_password/auth_token 供网关校验）。
    """
    if is_platform_admin(user):
        # admin 保留原默认站点逻辑
        if data.station_id:
            station = db.query(Station).filter(Station.id == int(data.station_id)).first()
            if station is None:
                raise HTTPException(status_code=404, detail="站点不存在")
        else:
            from app.models.station import StationStatus
            station = db.query(Station).filter(Station.code == "DEFAULT").first()
            if not station:
                station = Station(name="默认电站", code="DEFAULT", address="系统默认", status=StationStatus.NORMAL)
                db.add(station)
                db.flush()
    else:
        # 团队级用户：必须显式指定属本团队的站点
        if not data.station_id:
            raise HTTPException(status_code=400, detail="需指定本团队站点 station_id")
        station = db.query(Station).filter(Station.id == int(data.station_id)).first()
        if station is None or station.team_id is None or station.team_id != user.team_id:
            raise HTTPException(status_code=404, detail="站点不存在")
    station_id = station.id

    # sn 缺省：TLLN-<station_code前4位大写>-<6位hex大写>（如 TLLN-SH01-A3F8B2）
    sn = data.sn
    if not sn:
        prefix = (station.code or "DEFA")[:4].upper()
        sn = f"TLLN-{prefix}-{secrets.token_hex(3).upper()}"

    # 设备编码缺省: 平台自定义码可留空 → 从SN派生(取后12位), 无SN时 CL-短码
    if not data.code:
        data.code = (sn[-12:] if sn and len(sn) >= 8 else f"CL-{secrets.token_hex(3).upper()}")

    # 接入凭证（OCPP chargeBoxId 默认=sn；MQTT 用户名取 sn 前12位；密码/令牌一次性下发）
    mqtt_password = secrets.token_urlsafe(24)
    auth_token = secrets.token_urlsafe(16)

    if data.protocol_type is not None and data.protocol_type not in _VALID_PROTOCOLS:
        raise HTTPException(status_code=400, detail=f"不支持的通讯协议: {data.protocol_type}")

    device = Device(
        sn=sn,
        code=data.code,
        name=data.name,
        type=DeviceType(data.type),
        station_id=station_id,
        rated_power=data.rated_power,
        gun_count=data.gun_count,
        manufacturer=data.manufacturer,
        model=data.model,
        protocol_type=ProtocolType(data.protocol_type) if data.protocol_type else None,
        status=DeviceStatus.ONLINE,
        provision_status=ProvisionStatus.PROVISIONING,
        charge_box_id=sn,
        mqtt_username=f"gw-{sn[:12]}",
        mqtt_password=mqtt_password,
        auth_token=auth_token,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    audit_service.log_crud(user.id, user.username, "create", "devices", str(device.id))
    return success_response({
        'id': device.id,
        'sn': device.sn,
        'code': device.code,
        'name': device.name,
        'type': device.type.value if device.type else 'charger_dc',
        'station_id': device.station_id,
        'status': device.status.value if device.status else 'offline',
        'health_score': device.health_score,
        'rated_power': device.rated_power,
        'gun_count': device.gun_count,
        'provision_status': device.provision_status.value if device.provision_status else 'unprovisioned',
        # 接入凭证：仅此次返回明文，后续不可再取（mqtt_password/auth_token 不在详情接口暴露）
        'credentials': {
            'charge_box_id': device.charge_box_id,
            'mqtt_username': device.mqtt_username,
            'mqtt_password': mqtt_password,
            'auth_token': auth_token,
        },
    }, "设备已创建，接入凭证仅此次返回，请妥善保存")


# ── 集合级静态路由：必须声明在 /{device_id} 参数路由之前，
#    否则 GET /maintenance-due 会被 /{device_id}（str converter）捕获 → 422（死路由）。
# #2 GET /maintenance-due
@router.get("/maintenance-due")
def get_maintenance_due(
    days_ahead: int = Query(30, ge=1, le=90, description="提前检查天数"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取即将到期/已过期的维护计划列表。
    返回未来 N 天内需要维护的设备，按到期时间排序。

    team scoping（任务卡 ed509541）：非 admin 仅返回本 team 站点的设备。
    """
    try:
        results = maintenance_schedule_checker.get_upcoming_maintenance(
            db, days_ahead=days_ahead
        )
        if not is_platform_admin(user):
            own_station_ids = {
                sid for (sid,) in db.query(Station.id)
                .filter(Station.team_id == user.team_id).all()
            }
            results = [r for r in results if r.get("station_id") in own_station_ids]
        # 分类统计
        stats = {
            "overdue": sum(1 for r in results if r["status"] == "overdue"),
            "soon": sum(1 for r in results if r["status"] == "soon"),
            "warning": sum(1 for r in results if r["status"] == "warning"),
            "upcoming": sum(1 for r in results if r["status"] == "upcoming"),
        }
        return success_response({
            "items": results,
            "total": len(results),
            "stats": stats,
        })
    except Exception as e:
        logger.error("获取维护到期设备列表失败: %s", e)
        raise HTTPException(status_code=500, detail="查询失败")


# #3 POST /run-maintenance-check
@router.post("/run-maintenance-check")
def run_maintenance_check(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    手动触发维护计划到期检查（立即执行）。
    返回检查结果和生成的告警列表。

    team scoping（任务卡 ed509541）：非 admin 仅返回本 team 站点的结果
    （service 全量检查的副作用不在本层拦截，已由 RBAC 限制运维角色调用）。
    """
    try:
        results = maintenance_schedule_checker.check_maintenance_schedule(db)
        if not is_platform_admin(user):
            own_station_ids = {
                sid for (sid,) in db.query(Station.id)
                .filter(Station.team_id == user.team_id).all()
            }
            results = [r for r in results if r.get("station_id") in own_station_ids]
        db.commit()
        return success_response({
            "checked_devices": len(results),
            "results": results,
        }, f"维护计划检查完成，发现 {len(results)} 个需关注的设备")
    except Exception as e:
        db.rollback()
        logger.error("手动维护计划检查失败: %s", e)
        raise HTTPException(status_code=500, detail="检查失败")


# #4 GET /{device_id} + #6 PUT /{device_id}
router.include_router(crud.router)
# #7,8,9,10 health×3 + efficiency
router.include_router(health.router)
# #11,12,13 maintenance-plan get/put + maintenance-records
router.include_router(maintenance_plan.router)
# 固件升级 (OTA) 三端点 (卡 43b26421): /{device_id}/firmware* 为字面量后缀,
# 与 GET /{device_id} 无通配冲突, 注册顺序不影响匹配
router.include_router(firmware.router)


# #14 POST /{device_id}/control
#
# 卡52f731ac 说明: 此端点为 async (须 await DeviceControlService 的适配器 IO),
# 但 DeviceControlService 的同步 DB 契约被 tests/test_device_control.py 的 15+ 单元
# 测试锁死 (mock db.query...first / db.commit.assert_called_once), 无法改用 AsyncSession。
# 故采用与 `def` 端点等价的手段: 端点自身的同步 DB 操作提取为模块级 helper, 经
# run_in_threadpool 卸载到线程池, 不阻塞事件循环; 端点函数体内不含同步 db.query/commit。
# DeviceControlService 的内部单次 PK 查询仍随其 async 方法在事件循环上 (微秒级, 本地
# SQLite), 真正耗时的适配器 IO 已正确 await。详见 helpers。
def _lookup_control_device(db: Session, device_id: int):
    """按主键取设备 (sync helper, 供线程池调用)。"""
    return db.query(Device).filter(Device.id == device_id).first()


def _log_szbus_control(db: Session, device_id: int, device_name: str,
                        action: str, gun_no: int, success: bool, message: str,
                        operator_id: int, operator_name: str) -> None:
    """SZBUS 桩控制日志 (sync helper)。"""
    control_log = DeviceControlLog(
        device_id=device_id,
        device_name=device_name,
        action=action,
        parameter="gun_no",
        value=str(gun_no),
        params={"action": action, "gun_no": gun_no, "channel": "szbus_0x31_0x32"},
        result="success" if success else "failed",
        message=message,
        operator=operator_name,
        operator_id=operator_id,
    )
    db.add(control_log)
    db.commit()


def _create_v2g_dispatch_record(
    db: Session, device_id: int, device_name: str,
    action: str, parameter, value, dispatch_type: str, target_power: float,
    operator_id: int = 0, operator_name: str = "admin",
) -> dict:
    """写 V2G 调度日志 + 常规控制日志 + 审计, 返回响应体字段 (sync helper)。"""
    from app.models.v2g_dispatch import V2GDispatchLog
    now = datetime.now(timezone.utc)
    v2g_log = V2GDispatchLog(
        device_id=device_id,
        dispatch_type=dispatch_type,
        target_power_kw=target_power,
        actual_power_kw=0.0,
        status="pending",
        start_at=now,
    )
    db.add(v2g_log)
    control_log = DeviceControlLog(
        device_id=device_id,
        device_name=device_name,
        action=action,
        parameter=parameter,
        value=str(value) if value else None,
        params={"action": action, "dispatch_type": dispatch_type, "target_power_kw": target_power},
        result="success",
        message=f"V2G模式切换成功: {action} → {dispatch_type} @ {target_power} kW",
        operator="admin",
        operator_id=0,
    )
    db.add(control_log)
    audit_service.log_crud(operator_id, operator_name, "v2g_control", "devices", str(device_id), {
        "action": action,
        "dispatch_type": dispatch_type,
        "target_power_kw": target_power,
    })
    db.commit()
    db.refresh(v2g_log)
    return {
        "dispatch_log_id": v2g_log.id,
        "device_id": device_id,
        "dispatch_type": dispatch_type,
        "target_power_kw": target_power,
        "status": "pending",
        "created_at": v2g_log.created_at.isoformat() if v2g_log.created_at else None,
    }


def _persist_control_log(db: Session, device_id: int, device_name: str, data: "DeviceControlRequest", result: dict) -> None:
    """持久化标准充电桩控制日志 (sync helper)。"""
    control_log = DeviceControlLog(
        device_id=device_id,
        device_name=device_name,
        action=data.action,
        parameter=data.parameter,
        value=str(data.value) if data.value else None,
        params={"action": data.action, "parameter": data.parameter, "value": data.value, "reset_type": data.reset_type},
        result="success" if result.get("success") else "failed",
        message=result.get("error") if not result.get("success") else f"控制成功: {data.action}",
        operator="admin",
        operator_id=0,
    )
    db.add(control_log)
    db.commit()


def _persist_control_log_failed(db: Session, device_id: int, device_name, data: "DeviceControlRequest", err: Exception) -> None:
    """记录失败的控制日志 (sync helper)。"""
    control_log = DeviceControlLog(
        device_id=device_id,
        device_name=device_name,
        action=data.action,
        parameter=data.parameter,
        value=str(data.value) if data.value else None,
        result="failed",
        message=str(err),
        operator="admin",
        operator_id=0,
    )
    db.add(control_log)
    db.commit()


@router.post("/{device_id}/control")
async def control_device(
    device_id: int,
    data: DeviceControlRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """设备控制 - 启动/停止/重启/参数设置/急停

    支持的 action:
    - start: 启动设备
    - stop: 停止设备
    - restart: 重启设备 (reset_type: soft/hard)
    - set_param: 设置参数 (parameter: 参数名, value: 参数值)
    - emergency_stop: 急停

    team scoping（任务卡 ed509541）：跨团队 → 404（先于类型校验，不泄露存在）。

    运维分离 (卡 00d7d49a): 鉴权改用 _check_device_maintenance_access —— 在原
    OPS_COMPANY 自运维语义之上, 额外放行持有 active grant 的 MAINTENANCE_TEAM
    (scope 允许 control); monitoring_only scope → 404。
    """
    # 同步 DB 操作经线程池卸载 (见上方卡52f731ac说明), 端点体不含 db.query/commit
    device = await run_in_threadpool(_lookup_control_device, db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    await run_in_threadpool(_check_device_maintenance_access, db, device_id, user)

    # 只允许充电桩类型设备控制
    if device.type not in [DeviceType.CHARGER_DC, DeviceType.CHARGER_AC, DeviceType.V2G_CHARGER]:
        raise HTTPException(status_code=400, detail="仅支持充电桩设备控制")

    # ── V2G 充电桩模式切换 ──
    if device.type == DeviceType.V2G_CHARGER:
        valid_v2g_actions = {"charge_mode", "discharge_mode", "standby_mode"}
        invalid_standard_actions = {"start", "stop", "restart", "set_param", "emergency_stop"}

        if data.action in invalid_standard_actions:
            raise HTTPException(
                status_code=400,
                detail=f"V2G充电桩不支持标准控制action '{data.action}'，请使用: {', '.join(sorted(valid_v2g_actions))}",
            )

        if data.action not in valid_v2g_actions:
            raise HTTPException(status_code=400, detail=f"不支持的V2G action: {data.action}")

        # 将 V2G 模式映射为 dispatch_type
        mode_map = {
            "charge_mode": "charge",
            "discharge_mode": "discharge",
            "standby_mode": "standby",
        }
        dispatch_type = mode_map[data.action]
        target_power = float(data.value) if data.value is not None else 0.0

        v2g_resp = await run_in_threadpool(
            _create_v2g_dispatch_record,
            db, device_id, device.name, data.action, data.parameter, data.value, dispatch_type, target_power,
            operator_id=user.id, operator_name=user.username,
        )
        return success_response(v2g_resp, f"V2G模式切换成功: {data.action}")
    # ── SZBUS 充电桩: 走 szbus 网关真实下发 (2026-10-10 丁哥: 控制键无效修复) ──
    # 根因: DeviceControlService 走 Modbus 适配器体系(为逆变器/边缘网关设计),
    # SZBUS 桩无适配器 → 命令到不了桩。此处绕过 adapter, 直连 szbus 网关 0x31/0x32。
    _proto = getattr(device.protocol_type, "value", device.protocol_type) if device.protocol_type else None
    if str(_proto).lower() == "szbus":
        gun_no = int(data.parameter) if (data.parameter and str(data.parameter).isdigit()) else 1
        if data.action == "start":
            from app.gateway.szbus import _gateway as _szbus_gw
            if _szbus_gw is None:
                raise HTTPException(status_code=409, detail="SZBUS 网关未运行")
            sent = await _szbus_gw.remote_start(device.sn, user=user.username, gun_no=gun_no)
            msg = f"0x31 启动指令已下发(枪{gun_no}), 待桩响应" if sent else "桩离线, 启动指令未发出"
            await run_in_threadpool(_log_szbus_control, db, device_id, device.name,
                                    "start", gun_no, sent, msg, user.id, user.username)
            if sent:
                return success_response({"action": "start", "gun_no": gun_no, "channel": "szbus"}, msg)
            raise HTTPException(status_code=409, detail=msg)
        if data.action in ("stop", "emergency_stop"):
            from app.gateway.szbus import _gateway as _szbus_gw
            if _szbus_gw is None:
                raise HTTPException(status_code=409, detail="SZBUS 网关未运行")
            sent = await _szbus_gw.remote_stop(device.sn, user=user.username, gun_no=gun_no)
            act = "stop" if data.action == "stop" else "emergency_stop(停充)"
            msg = f"0x32 停止指令已下发(枪{gun_no}), 待桩响应" if sent else "桩离线, 停止指令未发出"
            await run_in_threadpool(_log_szbus_control, db, device_id, device.name,
                                    data.action, gun_no, sent, msg, user.id, user.username)
            if sent:
                return success_response({"action": data.action, "gun_no": gun_no, "channel": "szbus"}, msg)
            raise HTTPException(status_code=409, detail=msg)
        if data.action == "restart":
            raise HTTPException(status_code=400, detail="SZBUS 协议无设备重启命令(仅支持 0x31 启动/0x32 停止/0x51 远程升级)")
        if data.action == "set_param":
            raise HTTPException(status_code=400, detail="SZBUS 参数下发请使用「参数配置」(0x12 工作参数/0x13 运营参数/0x16 计费模板)")

    # ── 标准充电桩控制 ──

    service = DeviceControlService(db)

    try:
        if data.action == "start":
            # 启动充电桩 - 寄存器 1024 = 0x01
            command = {"register": 1024, "value": 0x01, "type": "start"}
            result = await service.send_control(device_id, command)

        elif data.action == "stop":
            # 停止充电桩 - 寄存器 1024 = 0x00
            command = {"register": 1024, "value": 0x00, "type": "stop"}
            result = await service.send_control(device_id, command)

        elif data.action == "restart":
            # 重启设备
            result = await service.reset_device(device_id, data.reset_type)

        elif data.action == "set_param":
            # 设置参数
            if not data.parameter:
                raise HTTPException(status_code=400, detail="set_param 需要 parameter 字段")
            result = await service.set_parameter(device_id, data.parameter, data.value)

        elif data.action == "emergency_stop":
            # 急停
            result = await service.emergency_stop(device_id)

        else:
            raise HTTPException(status_code=400, detail=f"不支持的 action: {data.action}")

        # 记录审计日志
        audit_service.log_crud(user.id, user.username, "control", "devices", str(device_id), {
            "action": data.action,
            "parameter": data.parameter,
            "value": data.value,
            "result": result.get("success", False),
        })

        # 持久化控制日志
        await run_in_threadpool(_persist_control_log, db, device_id, device.name, data, result)

        if result.get("success"):
            return success_response(result, f"设备控制成功: {data.action}")
        else:
            return error_response(400, f"设备控制失败: {result.get('error', '未知错误')}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设备控制异常: {e}")
        # 记录失败日志
        try:
            await run_in_threadpool(_persist_control_log_failed, db, device_id, device.name, data, e)
        except Exception as log_err:
            logger.error(f"记录控制日志失败: {log_err}")
        return error_response(500, "设备控制异常")


# #15,16,17,18 control-history + config get/put + delete
router.include_router(config.router)

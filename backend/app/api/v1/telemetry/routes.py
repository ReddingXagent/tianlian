"""
遥测数据采集 API 路由 — 天链V2 Phase1 改造 / Phase3 TDengine 双模式查询

原 app/api/v1/telemetry.py(1105行) 按职责拆分而来(卡 61109a8a)。
本模块定义 router 与全部 HTTP 端点; 模型/辅助/查询分别拆至同级子模块。

Features:
- 根据设备类型自动路由到对应专表
- 批量上报接口(Core bulk insert)
- 复合索引优化查询 / 场站概览批量取数(消除 N+1)
- TDENGINE_ENABLED=true: 查询走 TDengine; false: 走 SQLAlchemy
"""
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import get_db
from app.core.response import success_response, error_response, action_response
from app.core.timing_log import emit_write_timing
from app.core.timing import timing_start_dep, timing_end_auth_dep
# 网关鉴权(节流 + TTL 缓存 + get_current_gateway_or_user dep) 抽离至 auth_throttle(卡 4c8120a6)。
from app.core.auth_throttle import get_current_gateway_or_user
from app.models.telemetry import Telemetry  # 向后兼容旧表
from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger
from app.models.device import Device
from app.models.station import Station
from app.models.user import User
from app.api.deps import assert_device_team_access, assert_station_team_access

from .models import TelemetryReportLegacy, TelemetryBatchReport
from .helpers import (
    MAX_BATCH_SIZE,
    _get_telemetry_reader,
    get_region_from_header,
    get_pod_from_header,
    route_to_telemetry_table,
    create_telemetry_record,
    insert_telemetry_rows_with_fallback,
)
from .queries import _fetch_latest_telemetry_by_station

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== 单条遥测数据上报 ==========

@router.post("/report", dependencies=[Depends(get_current_gateway_or_user)])
def report_telemetry(
    data: TelemetryReportLegacy,
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    pod_id: str = Depends(get_pod_from_header)
):
    """
    设备遥测数据上报 - Phase1 改造

    根据设备类型自动路由到对应专表:
    - pv_inverter -> TelemetryPV
    - battery_inverter/pcs/battery -> TelemetryBattery
    - charger_dc/charger_ac -> TelemetryCharger
    - 其他 -> Telemetry (向后兼容)

    协议适配:
    - 逆变器Modbus:电网/逆变/电池/PV数据
    - 充电桩MQTT:充电桩状态/BMS数据
    - PCS Modbus:PCS状态数据
    """
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 创建遥测记录并路由到正确的表
    telemetry = create_telemetry_record(device, data, region_id, pod_id, db)
    db.add(telemetry)
    db.commit()
    db.refresh(telemetry)

    # 确定使用的表类型
    table_type = "legacy" if isinstance(telemetry, Telemetry) else \
                 "pv" if isinstance(telemetry, TelemetryPV) else \
                 "battery" if isinstance(telemetry, TelemetryBattery) else "charger"

    return action_response(
        success=True,
        message="遥测数据上报成功",
        data={
            "device_id": data.device_id,
            "timestamp": str(telemetry.timestamp),
            "table_type": table_type,
            "region_id": region_id,
            "pod_id": pod_id
        }
    )


# ========== 批量遥测数据上报 ==========

@router.post(
    "/batch-report",
    dependencies=[
        Depends(timing_start_dep),
        Depends(get_current_gateway_or_user),
        Depends(timing_end_auth_dep),
    ],
)
def batch_report_telemetry(
    data: TelemetryBatchReport,
    request: Request,
    db: Session = Depends(get_db),
    header_region: str = Depends(get_region_from_header),
    header_pod: str = Depends(get_pod_from_header),
):
    """
    批量遥测数据上报 - Phase1 新增

    接收数组,批量写入,提升效率

    Features:
    - 支持多条数据一次性上报
    - 自动按设备类型分流到对应表
    - 使用批量insert减少数据库IO
    - Phase1: 增加数据量上限校验(防止内存溢出和超时)
    """
    # 卡 f78a8e44: 起点与 auth 结束点由 marker dep 写入 request.state(auth 在
    # dependencies 阶段执行, 先于函数体), 此处读出供请求级 timing 分段计算。
    t_start = request.state.timing_start
    t_auth_end = request.state.timing_auth_end

    def _emit_early() -> None:
        """提前返回(空/超限)路径: insert/commit 段记 0, 仍输出一条 timing 日志。"""
        now = time.perf_counter()
        emit_write_timing(
            "telemetry/batch-report", len(data.records),
            auth_ms=(t_auth_end - t_start) * 1000,
            parse_ms=(now - t_auth_end) * 1000,
            insert_ms=0.0,
            commit_ms=0.0,
            total_ms=(now - t_start) * 1000,
        )

    if not data.records:
        _emit_early()
        return error_response(400, "数据列表不能为空")

    # Phase1: 数据量上限校验
    if len(data.records) > MAX_BATCH_SIZE:
        _emit_early()
        return error_response(
            400, f"批量数据上限{MAX_BATCH_SIZE}条,当前{len(data.records)}条"
        )

    # 使用 header 或 body 中的 region/pod
    region_id = data.region_id or header_region
    pod_id = data.pod_id or header_pod

    # 预加载所有设备(避免多次查询)
    device_ids = [r.device_id for r in data.records]
    devices = {d.id: d for d in db.query(Device).filter(Device.id.in_(device_ids)).all()}

    # 预校验: 连同 station 一起校验存在性, 隔离孤儿设备(场站被硬删而设备未清理)。
    # 防 TelemetryPV/Battery/Charger.station_id(nullable=False + FK→stations.id) FK 违约
    # 连坐同批健康记录(P1 data-safety): 单事务整批回滚 → 网关侧遥测静默丢失。
    candidate_station_ids = {d.station_id for d in devices.values()}
    valid_station_ids: set = set()
    if candidate_station_ids:
        valid_station_ids = {
            sid for (sid,) in db.query(Station.id).filter(
                Station.id.in_(candidate_station_ids)
            ).all()
        }

    # 分流记录到不同表(收集 dict 列表, 供 Core bulk insert)
    pv_rows = []
    battery_rows = []
    charger_rows = []
    legacy_rows = []

    stats = {
        "pv": 0,
        "battery": 0,
        "charger": 0,
        "legacy": 0,
        "errors": []
    }

    # 缓存每个设备的目标模型类, 避免逐条 route 查表
    device_model_cache: Dict[int, type] = {}

    for record_data in data.records:
        device = devices.get(record_data.device_id)
        if not device:
            stats["errors"].append(f"设备 {record_data.device_id} 不存在")
            continue

        # 孤儿设备(场站被硬删): 跳过该记录并记 errors, 不连坐同批其他记录。
        # 毒源详见上方 valid_station_ids 注释 —— 在写入前过滤, 从源头消除 FK 违约。
        if device.station_id not in valid_station_ids:
            stats["errors"].append(
                f"设备 {device.id} 的场站 {device.station_id} 不存在(孤儿设备),跳过"
            )
            logger.warning(
                "telemetry batch-report 跳过孤儿设备 device_id=%s station_id=%s",
                device.id, device.station_id,
            )
            continue

        model_class = device_model_cache.get(device.id)
        if model_class is None:
            model_class = route_to_telemetry_table(device, db)
            device_model_cache[device.id] = model_class

        data_dict = record_data.dict(exclude_none=True)
        data_dict["station_id"] = device.station_id

        if model_class != Telemetry:
            data_dict["region_id"] = region_id
            data_dict["pod_id"] = pod_id

        # 按目标表有效列过滤,避免通用 schema 的跨表字段(如 charger_voltage
        # 路由到 TelemetryPV)触发 TypeError 导致整批写入失败
        valid_columns = {c.key for c in model_class.__table__.columns}
        data_dict = {k: v for k, v in data_dict.items() if k in valid_columns}

        # 仅收集 rows; 实际落库数在写入后回填 stats(整批失败逐条 fallback 时
        # 健康记录落库、毒记录隔离, 实际数可能少于收集数)。
        if model_class == TelemetryPV:
            pv_rows.append(data_dict)
        elif model_class == TelemetryBattery:
            battery_rows.append(data_dict)
        elif model_class == TelemetryCharger:
            charger_rows.append(data_dict)
        else:
            legacy_rows.append(data_dict)

    # Core bulk insert: 绕过 ORM unit-of-work, 相比 add_all 实测 ~6x(卡 96593abe)。
    # SQLite WAL 单 writer 下, 显著缩短写锁持有时长, 缓解并发慢请求。
    # bulk_insert_mappings 不回填 ORM 实例属性(id/server_default 由 DB 填充),
    # 但本端点响应仅依赖 stats 计数, 不消费插入后的对象, 故请求响应契约不变。
    # P1 data-safety: 改 4 表统一单事务为按表分段提交 + 整批失败逐条 fallback,
    # 隔离毒记录(FK/约束违反)防连坐健康记录; 失败日志带 device_id 便于定位。
    # 卡 f78a8e44: 分段测时 — insert(bulk_insert_mappings) / commit(db.commit)。
    t_insert_start = time.perf_counter()
    total_insert_ms = 0.0
    total_commit_ms = 0.0
    for _model, _rows, _key in (
        (TelemetryPV, pv_rows, "pv"),
        (TelemetryBattery, battery_rows, "battery"),
        (TelemetryCharger, charger_rows, "charger"),
        (Telemetry, legacy_rows, "legacy"),
    ):
        _ok, _ins_ms, _com_ms = insert_telemetry_rows_with_fallback(
            db, _model, _rows, stats, _key,
        )
        stats[_key] = _ok
        total_insert_ms += _ins_ms
        total_commit_ms += _com_ms
    t_commit_end = time.perf_counter()

    total_success = stats["pv"] + stats["battery"] + stats["charger"] + stats["legacy"]

    # parse 段含 Pydantic body 校验(函数体之前完成) + 设备/station 预载 + 分流构建 rows。
    emit_write_timing(
        "telemetry/batch-report", len(data.records),
        auth_ms=(t_auth_end - t_start) * 1000,
        parse_ms=(t_insert_start - t_auth_end) * 1000,
        insert_ms=total_insert_ms,
        commit_ms=total_commit_ms,
        total_ms=(t_commit_end - t_start) * 1000,
    )

    return action_response(
        success=True,
        message=f"批量上报成功,共 {total_success} 条",
        data={
            "total_received": len(data.records),
            "total_success": total_success,
            "stats": stats,
            "region_id": region_id,
            "pod_id": pod_id
        }
    )


# ========== 查询接口 ==========

@router.get("/device/{device_id}/latest")
def get_latest_telemetry(
    device_id: int,
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    caller=Depends(get_current_gateway_or_user),
):
    """获取设备最新遥测数据 - Phase1 + Phase3 双模式

    自动查询对应专表,如果找不到则 fallback 到旧表
    TDengine 模式下使用 TDengineWriter 查询,SQLAlchemy 模式下使用 ORM 查询
    """
    # team scoping（任务卡 e1f0e6d5）：仅用户态校验 device 归属；网关（dict）豁免。
    if isinstance(caller, User):
        assert_device_team_access(db, device_id, caller)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # Phase3: 尝试 TDengine 查询
    td_reader = _get_telemetry_reader()
    if td_reader:
        # 确定表类型
        model_class = route_to_telemetry_table(device, db)
        table_type = "pv" if model_class == TelemetryPV else \
                     "battery" if model_class == TelemetryBattery else \
                     "charger" if model_class == TelemetryCharger else "legacy"

        # TDengine 查询最新数据
        if table_type != "legacy":
            latest_data = td_reader.query_latest(device_id, table_type)
            if latest_data:
                result = {
                    "device_id": device_id,
                    "timestamp": str(latest_data.get("ts", "")),
                    "table_type": table_type,
                }
                # 添加主要字段
                if "grid_power_total" in latest_data:
                    result["grid_power_total"] = latest_data["grid_power_total"]
                if "battery_soc" in latest_data:
                    result["battery_soc"] = latest_data["battery_soc"]
                if "charger_power" in latest_data:
                    result["charger_power"] = latest_data["charger_power"]
                if "region_id" in latest_data:
                    result["region_id"] = latest_data["region_id"]

                logger.debug(f"[Telemetry] TDengine 查询设备 {device_id} 最新数据")
                return success_response(result)
        # TDengine 查询失败或旧表,fallback 到 SQLAlchemy

    # SQLAlchemy 查询(默认或 fallback)
    model_class = route_to_telemetry_table(device, db)

    # 查询最新数据(带 region 过滤)
    query = db.query(model_class).filter(model_class.device_id == device_id)

    # 如果是新表,添加 region 过滤
    if model_class != Telemetry and hasattr(model_class, 'region_id'):
        query = query.filter(model_class.region_id == region_id)

    telemetry = query.order_by(desc(model_class.timestamp)).first()

    # 如果新表没数据,fallback 到旧表(向后兼容)
    if not telemetry and model_class != Telemetry:
        telemetry = db.query(Telemetry).filter(
            Telemetry.device_id == device_id
        ).order_by(desc(Telemetry.timestamp)).first()

    if not telemetry:
        raise HTTPException(status_code=404, detail="无遥测数据")

    # 构建响应
    result = {
        "device_id": telemetry.device_id,
        "timestamp": str(telemetry.timestamp),
        "table_type": "pv" if isinstance(telemetry, TelemetryPV) else \
                      "battery" if isinstance(telemetry, TelemetryBattery) else \
                      "charger" if isinstance(telemetry, TelemetryCharger) else "legacy",
    }

    # 添加主要字段
    if hasattr(telemetry, 'grid_power_total'):
        result["grid_power_total"] = telemetry.grid_power_total
    if hasattr(telemetry, 'battery_soc'):
        result["battery_soc"] = telemetry.battery_soc
    if hasattr(telemetry, 'charger_power'):
        result["charger_power"] = telemetry.charger_power
    if hasattr(telemetry, 'region_id'):
        result["region_id"] = telemetry.region_id
    if hasattr(telemetry, 'pod_id'):
        result["pod_id"] = telemetry.pod_id

    logger.debug(f"[Telemetry] SQLAlchemy 查询设备 {device_id} 最新数据")
    return success_response(result)


@router.get("/device/{device_id}/history")
def get_telemetry_history(
    device_id: int,
    hours: int = Query(24, ge=1, le=720, description="查询最近N小时(边界1~720)"),
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    caller=Depends(get_current_gateway_or_user),
):
    """获取设备遥测历史数据 - Phase1 + Phase3 双模式

    TDengine 模式下使用 TDengineWriter 查询，SQLAlchemy 模式下使用复合索引查询
    """
    # team scoping（任务卡 e1f0e6d5）：仅用户态校验 device 归属；网关（dict）豁免。
    if isinstance(caller, User):
        assert_device_team_access(db, device_id, caller)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    model_class = route_to_telemetry_table(device, db)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Phase3: 尝试 TDengine 查询
    td_reader = _get_telemetry_reader()
    if td_reader and model_class != Telemetry:
        # 确定表类型
        table_type = "pv" if model_class == TelemetryPV else \
                     "battery" if model_class == TelemetryBattery else "charger"

        # TDengine 查询历史数据
        records_data = td_reader.query_range(device_id, table_type, since, datetime.now(timezone.utc), limit=1000)
        if records_data:
            logger.debug(f"[Telemetry] TDengine 查询设备 {device_id} 历史数据: {len(records_data)} 条")
            return success_response({
                "device_id": device_id,
                "hours": hours,
                "count": len(records_data),
                "region_id": region_id,
                "mode": "tdengine"
            })
        # TDengine 查询失败，fallback 到 SQLAlchemy

    # SQLAlchemy 查询（默认或 fallback）
    # 使用复合索引查询
    query = db.query(model_class).filter(
        model_class.device_id == device_id,
        model_class.timestamp >= since
    )

    # 新表添加 region 过滤（利用复合索引）
    if model_class != Telemetry and hasattr(model_class, 'region_id'):
        query = query.filter(model_class.region_id == region_id)

    # 使用复合索引排序
    records = query.order_by(desc(model_class.timestamp)).limit(1000).all()

    # Fallback 到旧表
    if not records and model_class != Telemetry:
        records = db.query(Telemetry).filter(
            Telemetry.device_id == device_id,
            Telemetry.timestamp >= since
        ).order_by(desc(Telemetry.timestamp)).limit(1000).all()

    logger.debug(f"[Telemetry] SQLAlchemy 查询设备 {device_id} 历史数据: {len(records)} 条")
    return success_response({
        "device_id": device_id,
        "hours": hours,
        "count": len(records),
        "region_id": region_id,
        "mode": "sqlalchemy"
    })


@router.get("/device/{device_id}/stats")
def get_telemetry_stats(
    device_id: int,
    hours: int = Query(24, ge=1, le=720, description="统计最近N小时(边界1~720)"),
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    caller=Depends(get_current_gateway_or_user),
):
    """获取设备遥测统计数据(平均值/最大值/最小值)- Phase1 改造"""
    # team scoping（任务卡 e1f0e6d5）：仅用户态校验 device 归属；网关（dict）豁免。
    if isinstance(caller, User):
        assert_device_team_access(db, device_id, caller)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    model_class = route_to_telemetry_table(device, db)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # 根据设备类型选择统计字段
    if model_class == TelemetryPV:
        stats = db.query(
            func.avg(model_class.grid_voltage_a).label('avg_voltage_a'),
            func.max(model_class.grid_voltage_a).label('max_voltage_a'),
            func.min(model_class.grid_voltage_a).label('min_voltage_a'),
            func.avg(model_class.grid_power_total).label('avg_power'),
            func.max(model_class.grid_power_total).label('max_power'),
            func.avg(model_class.pv_power_total).label('avg_pv_power'),
            func.max(model_class.pv_power_total).label('max_pv_power'),
            func.avg(model_class.internal_temperature).label('avg_temp'),
            func.max(model_class.internal_temperature).label('max_temp'),
        ).filter(
            model_class.device_id == device_id,
            model_class.timestamp >= since,
            model_class.region_id == region_id
        ).first()

        return success_response({
            "device_id": device_id,
            "hours": hours,
            "table_type": "pv",
            "stats": {
                "grid": {
                    "avg_voltage_a": float(stats.avg_voltage_a or 0),
                    "max_voltage_a": float(stats.max_voltage_a or 0),
                    "min_voltage_a": float(stats.min_voltage_a or 0),
                    "avg_power": float(stats.avg_power or 0),
                    "max_power": float(stats.max_power or 0),
                },
                "pv": {
                    "avg_power": float(stats.avg_pv_power or 0),
                    "max_power": float(stats.max_pv_power or 0),
                },
                "thermal": {
                    "avg_temp": float(stats.avg_temp or 0),
                    "max_temp": float(stats.max_temp or 0),
                }
            }
        })

    elif model_class == TelemetryBattery:
        stats = db.query(
            func.avg(model_class.battery_soc).label('avg_soc'),
            func.max(model_class.battery_soc).label('max_soc'),
            func.avg(model_class.battery_power).label('avg_power'),
            func.max(model_class.battery_power).label('max_power'),
            func.avg(model_class.battery_temperature).label('avg_temp'),
            func.max(model_class.battery_temperature).label('max_temp'),
            func.avg(model_class.internal_temperature).label('avg_internal_temp'),
        ).filter(
            model_class.device_id == device_id,
            model_class.timestamp >= since,
            model_class.region_id == region_id
        ).first()

        return success_response({
            "device_id": device_id,
            "hours": hours,
            "table_type": "battery",
            "stats": {
                "battery": {
                    "avg_soc": float(stats.avg_soc or 0),
                    "max_soc": float(stats.max_soc or 0),
                    "avg_power": float(stats.avg_power or 0),
                    "max_power": float(stats.max_power or 0),
                    "avg_temp": float(stats.avg_temp or 0),
                    "max_temp": float(stats.max_temp or 0),
                },
                "thermal": {
                    "avg_internal_temp": float(stats.avg_internal_temp or 0),
                }
            }
        })

    elif model_class == TelemetryCharger:
        stats = db.query(
            func.avg(model_class.charger_power).label('avg_power'),
            func.max(model_class.charger_power).label('max_power'),
            func.avg(model_class.charger_soc).label('avg_soc'),
            # charger_kwh 是累计电能表快照(单调递增), SUM 会把同一计数器翻 N 倍;
            # MAX-MIN = 末值-首值 = 窗口净增量 (卡 6e80d5d6)
            (func.max(model_class.charger_kwh) - func.min(model_class.charger_kwh)).label('total_kwh'),
            func.avg(model_class.internal_temperature).label('avg_temp'),
            func.max(model_class.internal_temperature).label('max_temp'),
        ).filter(
            model_class.device_id == device_id,
            model_class.timestamp >= since,
            model_class.region_id == region_id
        ).first()

        return success_response({
            "device_id": device_id,
            "hours": hours,
            "table_type": "charger",
            "stats": {
                "charger": {
                    "avg_power": float(stats.avg_power or 0),
                    "max_power": float(stats.max_power or 0),
                    "avg_soc": float(stats.avg_soc or 0),
                    "total_kwh": float(stats.total_kwh or 0),
                },
                "thermal": {
                    "avg_temp": float(stats.avg_temp or 0),
                    "max_temp": float(stats.max_temp or 0),
                }
            }
        })

    else:
        # 向后兼容旧表
        stats = db.query(
            func.avg(Telemetry.grid_voltage_a).label('avg_voltage_a'),
            func.max(Telemetry.grid_voltage_a).label('max_voltage_a'),
            func.avg(Telemetry.grid_power_total).label('avg_power'),
            func.avg(Telemetry.battery_soc).label('avg_soc'),
        ).filter(
            Telemetry.device_id == device_id,
            Telemetry.timestamp >= since
        ).first()

        return success_response({
            "device_id": device_id,
            "hours": hours,
            "table_type": "legacy",
            "stats": {
                "grid": {
                    "avg_voltage_a": float(stats.avg_voltage_a or 0),
                    "avg_power": float(stats.avg_power or 0),
                },
                "battery": {
                    "avg_soc": float(stats.avg_soc or 0),
                }
            }
        })


@router.get("/station/{station_id}/overview")
def get_station_telemetry_overview(
    station_id: int,
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    caller=Depends(get_current_gateway_or_user),
):
    """获取场站所有设备遥测概览 - Phase1 改造

    使用新的 station_id 字段优化查询。
    性能优化（卡 0e7deb3d）：原实现循环内每设备各发 1~2 条 latest 查询（含 legacy
    fallback），N 设备 ≈ N~2N 条 SQL；现按目标表分组批量取，查询数与设备数解耦
    （≤ 2 条/表，与 N 无关）。响应 shape/字段/排序与原实现完全一致。
    """
    # team scoping（任务卡 e1f0e6d5）：仅用户态校验 station 归属；网关（dict）豁免。
    if isinstance(caller, User):
        assert_station_team_access(db, station_id, caller)
    devices = db.query(Device).filter(Device.station_id == station_id).all()

    latest_by_device = _fetch_latest_telemetry_by_station(db, devices, station_id, region_id)

    overview = []
    for device in devices:
        model_class = route_to_telemetry_table(device, db)
        latest = latest_by_device.get(device.id)

        # device_id 所有模型都有; station_id 仅 v2 模型有, legacy Telemetry 表无此列
        telemetry_data = {
            "timestamp": latest.timestamp if latest else None,
            "power": None,
            "soc": None,
            "temperature": None,
        }

        if latest:
            if hasattr(latest, 'grid_power_total') and latest.grid_power_total:
                telemetry_data["power"] = latest.grid_power_total
            elif hasattr(latest, 'charger_power') and latest.charger_power:
                telemetry_data["power"] = latest.charger_power

            if hasattr(latest, 'battery_soc') and latest.battery_soc:
                telemetry_data["soc"] = latest.battery_soc
            elif hasattr(latest, 'charger_soc') and latest.charger_soc:
                telemetry_data["soc"] = latest.charger_soc

            if hasattr(latest, 'internal_temperature') and latest.internal_temperature:
                telemetry_data["temperature"] = latest.internal_temperature

        overview.append({
            "device_id": device.id,
            "device_name": device.name,
            "device_type": device.type.value,
            "status": device.status.value,
            "latest_telemetry": telemetry_data,
            "region_id": region_id if model_class != Telemetry else None,
        })

    return success_response({
        "station_id": station_id,
        "device_count": len(devices),
        "overview": overview,
        "region_id": region_id
    })


# ========== 模拟数据生成(测试用)==========

@router.post("/device/{device_id}/simulate")
def simulate_telemetry(
    device_id: int,
    hours: int = Query(1, ge=1, le=72, description="生成最近N小时模拟数据(边界1~72)"),
    interval_seconds: int = Query(60, ge=1, le=3600, description="数据间隔秒数(边界1~3600)"),
    db: Session = Depends(get_db),
    region_id: str = Depends(get_region_from_header),
    pod_id: str = Depends(get_pod_from_header),
    caller=Depends(get_current_gateway_or_user),
):
    """
    生成模拟遥测数据(用于测试)- Phase1 改造

    根据设备类型生成不同的数据,并写入对应专表
    """
    import random

    # team scoping（任务卡 e1f0e6d5）：仅用户态校验 device 归属；网关（dict）豁免。
    if isinstance(caller, User):
        assert_device_team_access(db, device_id, caller)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    model_class = route_to_telemetry_table(device, db)
    records = []
    now = datetime.now(timezone.utc)

    for i in range(hours * 3600 // interval_seconds):
        timestamp = now - timedelta(seconds=i * interval_seconds)

        # 根据设备类型生成数据
        if model_class == TelemetryPV:
            record = TelemetryPV(
                device_id=device_id,
                station_id=device.station_id,
                timestamp=timestamp,
                region_id=region_id,
                pod_id=pod_id,
                grid_voltage_a=220 + random.uniform(-10, 10),
                grid_voltage_b=220 + random.uniform(-10, 10),
                grid_voltage_c=220 + random.uniform(-10, 10),
                grid_frequency=50 + random.uniform(-0.5, 0.5),
                grid_power_total=random.uniform(5, 20),
                grid_power_factor=0.99 + random.uniform(-0.02, 0),
                pv1_voltage=400 + random.uniform(-20, 20),
                pv1_current=10 + random.uniform(-2, 2),
                pv1_power=4 + random.uniform(-0.5, 1),
                pv2_voltage=400 + random.uniform(-20, 20),
                pv2_current=10 + random.uniform(-2, 2),
                pv2_power=4 + random.uniform(-0.5, 1),
                pv_power_total=8 + random.uniform(-1, 2),
                internal_temperature=40 + random.uniform(-5, 10),
                daily_generation=random.uniform(0, 50),
            )
        elif model_class == TelemetryCharger:
            record = TelemetryCharger(
                device_id=device_id,
                station_id=device.station_id,
                timestamp=timestamp,
                region_id=region_id,
                pod_id=pod_id,
                charger_voltage=400 + random.uniform(-20, 20),
                charger_current=50 + random.uniform(-10, 10),
                charger_power=20 + random.uniform(-5, 5),
                charger_soc=random.uniform(20, 90),
                charger_kwh=random.uniform(0, 30),
                gun_status=random.choice([0, 1, 2]),
                gun_temperature=35 + random.uniform(-5, 10),
                internal_temperature=45 + random.uniform(-5, 15),
            )
        elif model_class == TelemetryBattery:
            record = TelemetryBattery(
                device_id=device_id,
                station_id=device.station_id,
                timestamp=timestamp,
                region_id=region_id,
                pod_id=pod_id,
                battery_voltage=400 + random.uniform(-20, 20),
                battery_current=random.uniform(-50, 50),
                battery_power=random.uniform(-20, 20),
                battery_soc=random.uniform(20, 95),
                battery_soh=95 + random.uniform(-5, 2),
                battery_temperature=30 + random.uniform(-5, 10),
                daily_charge=random.uniform(0, 20),
                daily_discharge=random.uniform(0, 20),
            )
        else:
            # 旧表
            record = Telemetry(
                device_id=device_id,
                timestamp=timestamp,
                internal_temperature=40 + random.uniform(-10, 20),
            )

        records.append(record)

    # 批量插入
    db.add_all(records)
    db.commit()

    table_type = "pv" if model_class == TelemetryPV else \
                 "battery" if model_class == TelemetryBattery else \
                 "charger" if model_class == TelemetryCharger else "legacy"

    return action_response(
        success=True,
        message="模拟数据生成成功",
        data={
            "device_id": device_id,
            "hours": hours,
            "records_created": len(records),
            "interval_seconds": interval_seconds,
            "table_type": table_type,
            "region_id": region_id,
            "pod_id": pod_id
        }
    )

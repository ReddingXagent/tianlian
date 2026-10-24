"""
遥测数据辅助函数与配置

原 app/api/v1/telemetry.py(1105行) 按职责拆分而来(卡 61109a8a)。
提供: 批量上限配置、TDengine 查询路由、请求头解析、设备类型→遥测表路由与记录构建。
"""
import os
import time
import logging
from typing import Optional, Any, Dict, List, Tuple

from fastapi import Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tdengine import is_tdengine_available
from app.models.telemetry import Telemetry  # 向后兼容旧表
from app.models.telemetry_v2 import (
    TelemetryPV, TelemetryBattery, TelemetryCharger,
    get_telemetry_model_by_device_type
)
from app.models.device import Device

logger = logging.getLogger(__name__)

# Phase3: TDengine Writer (提供查询方法)
try:
    from app.services.tdengine_writer import TDengineWriter
    TDENGINE_QUERY_AVAILABLE = True
except ImportError:
    TDengineWriter = None
    TDENGINE_QUERY_AVAILABLE = False


# ========== 配置常量 ==========
MAX_BATCH_SIZE = int(os.getenv("BATCH_MAX_SIZE", "500"))  # Phase1: 批量上报上限,默认500条


# ========== Phase3: 查询路由函数 ==========
def _get_telemetry_reader() -> Optional[TDengineWriter]:
    """根据配置返回对应的查询器

    Returns:
        TDengineWriter 如果启用且可用,否则返回 None (走 SQLAlchemy)
    """
    if settings.TDENGINE_ENABLED and TDENGINE_QUERY_AVAILABLE and is_tdengine_available():
        return TDengineWriter()
    return None


# ========== 辅助函数 ==========

def get_region_from_header(region_id: Optional[str] = Header(None, alias="X-Region-ID")) -> str:
    """从请求头获取region_id,默认'default'"""
    return region_id or "default"


def get_pod_from_header(pod_id: Optional[str] = Header(None, alias="X-Pod-ID")) -> str:
    """从请求头获取pod_id,默认'pod-01'"""
    return pod_id or "pod-01"


def route_to_telemetry_table(device: Device, db: Session) -> type:
    """根据设备类型路由到对应的遥测表

    Args:
        device: 设备对象
        db: 数据库会话

    Returns:
        对应的遥测模型类
    """
    model_class = get_telemetry_model_by_device_type(device.type.value)
    if model_class:
        return model_class
    # 向后兼容:使用旧 Telemetry 表
    return Telemetry


def create_telemetry_record(device: Device, data: BaseModel, region_id: str, pod_id: str, db: Session) -> Any:
    """创建遥测记录并路由到正确的表

    Args:
        device: 设备对象
        data: 遥测数据
        region_id: 区域标识
        pod_id: Pod标识
        db: 数据库会话

    Returns:
        创建的遥测记录对象
    """
    model_class = route_to_telemetry_table(device, db)

    # 构建数据字典，仅保留目标模型支持的字段
    data_dict = data.dict(exclude_none=True)
    valid_columns = {c.name for c in model_class.__table__.columns}
    data_dict = {k: v for k, v in data_dict.items() if k in valid_columns}
    # 旧 Telemetry 表无 station_id 列, 注入前校验, 否则 Telemetry(**data_dict) 抛 TypeError → 500 (卡 418bbeac)
    if "station_id" in valid_columns:
        data_dict["station_id"] = device.station_id

    # 如果是新表,添加区域路由字段
    if model_class != Telemetry:
        data_dict["region_id"] = region_id
        data_dict["pod_id"] = pod_id

    # 创建记录
    record = model_class(**data_dict)
    return record


def insert_telemetry_rows_with_fallback(
    db: Session,
    model_class: type,
    rows: List[Dict[str, Any]],
    stats: Dict[str, Any],
    table_name: str,
) -> Tuple[int, float, float]:
    """单表批量写入遥测记录, 整批失败则逐条 fallback 隔离毒记录。

    原实现 4 表 bulk_insert_mappings 后统一 commit, 整批单事务无隔离 —— 任一记录触发
    约束违反(FK/NOT NULL/类型)即整批回滚 500, 网关侧健康设备遥测被同批毒记录连坐丢失
    (每批最多 MAX_BATCH_SIZE 条)。本 helper 改为单表整批提交, 失败时逐条重试隔离毒记录,
    最大化健康记录落库率; 失败路径 logger.error 携带 device_id 列表便于运维定位毒源。

    Args:
        db: 数据库会话
        model_class: 目标遥测模型类
        rows: 已按目标表有效列过滤的 dict 行列表(每行含 device_id, 供日志定位)
        stats: 统计字典, 单条失败时 append 明细到 stats["errors"]
        table_name: 表别名(pv/battery/charger/legacy), 仅用于日志

    Returns:
        (成功落库条数, insert 累计耗时 ms, commit 累计耗时 ms)
    """
    if not rows:
        return 0, 0.0, 0.0

    insert_ms = 0.0
    commit_ms = 0.0

    def _bulk_commit(mappings: List[Dict[str, Any]]) -> None:
        nonlocal insert_ms, commit_ms
        t0 = time.perf_counter()
        db.bulk_insert_mappings(model_class, mappings)
        t1 = time.perf_counter()
        db.commit()
        t2 = time.perf_counter()
        insert_ms += (t1 - t0) * 1000
        commit_ms += (t2 - t1) * 1000

    try:
        _bulk_commit(rows)
        return len(rows), insert_ms, commit_ms
    except Exception:
        # 整批失败: 回滚已 flush 的语句, 降级逐条重试, 隔离毒记录防连坐。
        db.rollback()
        logger.error(
            "telemetry batch-report %s 整批写入失败, 降级逐条隔离毒记录, device_ids=%s",
            table_name,
            [r.get("device_id") for r in rows],
            exc_info=True,
        )
        success = 0
        for row in rows:
            try:
                _bulk_commit([row])
                success += 1
            except Exception as e:
                db.rollback()
                dev_id = row.get("device_id")
                stats["errors"].append(f"设备 {dev_id} 写入失败: {type(e).__name__}")
                logger.error(
                    "telemetry batch-report %s 逐条写入失败 device_id=%s err=%s",
                    table_name, dev_id, e,
                )
        return success, insert_ms, commit_ms

"""
遥测数据查询辅助 — 批量 latest 取数

原 app/api/v1/telemetry.py(1105行) 按职责拆分而来(卡 61109a8a)。
消除逐设备 latest 查询的 N+1: 按目标表分组, 窗口函数取每设备最新一行主键后批量回表。
"""
from typing import Dict, List, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.telemetry import Telemetry
from .helpers import route_to_telemetry_table


def _latest_rows_for_devices(
    db: Session, model_class: type, device_ids: List[int],
    station_id: int, region_id: str,
) -> Dict[int, Any]:
    """批量取每个设备最新一条遥测记录（实体），消除逐设备 latest 查询的 N+1。

    每张表 2 条 SQL：① 窗口函数 row_number() 取每设备 timestamp 最新一行的主键；
    ② IN 一次取回实体。legacy Telemetry 表无 station_id/region_id 列，仅按 device_id
    过滤（与原逐设备实现一致）。返回 {device_id: 最新记录实体}，无数据的设备不出现。
    与 devices.py:_build_latest_telemetry_summary 同源窗口函数写法。
    """
    if not device_ids:
        return {}
    rn_col = func.row_number().over(
        partition_by=model_class.device_id,
        order_by=model_class.timestamp.desc(),
    ).label("rn")
    q = (
        db.query(
            model_class.id.label("row_id"),
            model_class.device_id.label("did"),
            rn_col,
        )
        .filter(model_class.device_id.in_(device_ids))
    )
    # device_id 所有模型都有；station_id/region_id 仅 v2 模型有，legacy Telemetry 表无此列
    if model_class != Telemetry:
        q = q.filter(model_class.station_id == station_id)
        if hasattr(model_class, "region_id"):
            q = q.filter(model_class.region_id == region_id)
    subq = q.subquery()
    pk_rows = db.query(subq.c.row_id, subq.c.did).filter(subq.c.rn == 1).all()
    if not pk_rows:
        return {}
    rows = db.query(model_class).filter(
        model_class.id.in_([r.row_id for r in pk_rows])
    ).all()
    return {row.device_id: row for row in rows}


def _fetch_latest_telemetry_by_station(
    db: Session, devices: list, station_id: int, region_id: str,
) -> Dict[int, Any]:
    """按目标表分组设备，每表批量取最新一条；v2 专表未命中的设备统一批量走 legacy fallback。

    route_to_telemetry_table 是纯设备类型→模型映射（不查 DB），故按它分组。
    """
    groups: Dict[type, List[int]] = {}
    for d in devices:
        groups.setdefault(route_to_telemetry_table(d, db), []).append(d.id)

    latest_by_device: Dict[int, Any] = {}
    for model_class, ids in groups.items():
        latest_by_device.update(
            _latest_rows_for_devices(db, model_class, ids, station_id, region_id)
        )

    # v2 专表未命中的设备，统一批量走 legacy Telemetry fallback（与原逐设备 fallback 等价）
    legacy_missing = [
        d.id for d in devices
        if route_to_telemetry_table(d, db) != Telemetry and d.id not in latest_by_device
    ]
    if legacy_missing:
        latest_by_device.update(
            _latest_rows_for_devices(db, Telemetry, legacy_missing, station_id, region_id)
        )
    return latest_by_device

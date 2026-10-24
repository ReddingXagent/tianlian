"""V2G 运营（车网互动）— 概览与车辆资源池 (2026-10-09 丁哥需求)

V2G (Vehicle-to-Grid) 双向充电: 车辆低谷充电 / 高峰放电卖给电网。
本模块提供运营侧 V2G 概览与资源池数据; 放电订单随交易模型扩展接入。
"""
import logging
import math
import re
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.user import User
from app.core.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/overview")
def v2g_overview(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """V2G 运营概览: 双向桩规模 + 车辆资源池规模."""
    base = db.query(Device).filter(Device.type == DeviceType.V2G_CHARGER)
    total = base.count()
    online = base.filter(Device.status.in_([DeviceStatus.ONLINE, DeviceStatus.CHARGING])).count()
    charging = base.filter(Device.status == DeviceStatus.CHARGING).count()
    fault = base.filter(Device.status == DeviceStatus.FAULT).count()

    # 车辆资源池(企业车辆)
    from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
    vq = db.query(EnterpriseVehicle)
    vehicles_total = vq.count()
    vehicles_active = vq.filter(EnterpriseVehicle.status == EnterpriseVehicleStatus.ACTIVE).count() \
        if hasattr(EnterpriseVehicleStatus, "ACTIVE") else vehicles_total

    return success_response({
        "piles": {"total": total, "online": online, "charging": charging, "fault": fault,
                  "online_rate": round(online / total * 100, 1) if total else 0},
        "vehicles": {"total": vehicles_total, "active": vehicles_active},
        # 峰谷套利参考(运营策略展示用; 接入计费模板后由配置驱动)
        "strategy_hint": "低谷时段充电、高峰时段放电, 套利空间=峰谷价差-双向损耗-服务费",
    }, "V2G概览")


@router.get("/vehicles")
def v2g_vehicles(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
                 keyword: Optional[str] = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """V2G 车辆资源池列表(企业车辆/VIN)."""
    from app.models.enterprise_vehicle import EnterpriseVehicle
    q = db.query(EnterpriseVehicle)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(EnterpriseVehicle.plate_number.like(like)
                     | EnterpriseVehicle.vin.like(like)
                     | EnterpriseVehicle.driver_name.like(like))
    total = q.count()
    rows = q.order_by(EnterpriseVehicle.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    items = [{
        "id": r.id,
        "plate_number": r.plate_number,
        "vin": r.vin,
        "driver_name": r.driver_name,
        "driver_phone": r.driver_phone,
        "status": getattr(getattr(r, "status", None), "value", str(r.status)) if r.status else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return success_response({"items": items, "total": total, "page": page,
                             "page_size": page_size}, "V2G车辆资源池")


# ========== V2G 放电价配置(2026-10-09 丁哥: 放电价需要可设置) ==========

import json as _json
import os as _os
import tempfile as _tempfile
from pathlib import Path as _Path

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_PRICING_LOCK = threading.Lock()

_PRICING_FILE = _Path(__file__).resolve().parents[4] / "data" / "v2g_pricing.json"
_PRICING_DEFAULT = {
    "periods": [
        {"name": "谷时", "start": "00:00", "end": "08:00", "price": 0.30, "kind": "buy"},
        {"name": "平时", "start": "08:00", "end": "18:00", "price": 0.70, "kind": "buy"},
        {"name": "峰时", "start": "18:00", "end": "22:00", "price": 1.10, "kind": "sell"},
        {"name": "尖峰", "start": "19:00", "end": "21:00", "price": 1.35, "kind": "sell"},
    ]
}


def _read_pricing() -> dict:
    try:
        if _PRICING_FILE.exists():
            data = _json.loads(_PRICING_FILE.read_text())
            if isinstance(data.get("periods"), list) and data["periods"]:
                return data
            # 旧格式(谷/平/峰/尖固定字段) → 迁移为自定义时段结构
            if any(k in data for k in ("valley", "flat", "peak", "sharp")):
                data["periods"] = [
                    {"name": "谷时", "start": "00:00", "end": "08:00", "price": float(data.get("valley", 0.30)), "kind": "buy"},
                    {"name": "平时", "start": "08:00", "end": "18:00", "price": float(data.get("flat", 0.70)), "kind": "buy"},
                    {"name": "峰时", "start": "18:00", "end": "22:00", "price": float(data.get("peak", 1.10)), "kind": "sell"},
                    {"name": "尖峰", "start": "19:00", "end": "21:00", "price": float(data.get("sharp", 1.35)), "kind": "sell"},
                ]
                return data
    except Exception as e:
        logger.warning("读取V2G放电价配置失败: %s", e)
    return _json.loads(_json.dumps(_PRICING_DEFAULT))


@router.get("/pricing")
def v2g_pricing_get(user: User = Depends(get_current_user)):
    """V2G 峰谷放电价配置(元/度)."""
    return success_response(_read_pricing(), "V2G放电价")


@router.put("/pricing")
def v2g_pricing_set(body: dict, user: User = Depends(get_current_user),
                    _: None = Depends(require_permission("system:config"))):
    """设置 V2G 峰谷电价(自定义时段): {periods: [{name, start, end, price, kind}]}.

    kind: buy=购电(充电成本) / sell=放电(V2G卖电收益); 价格 0~10 元/度。
    """
    from datetime import datetime, timezone as _tz
    periods = body.get("periods")
    if not isinstance(periods, list) or not periods:
        raise HTTPException(status_code=422, detail="periods 不能为空")
    clean = []
    for i, p in enumerate(periods):
        try:
            name = str(p.get("name") or f"时段{i+1}")[:50]
            start = str(p.get("start") or "")
            end = str(p.get("end") or "")
            if not _TIME_RE.match(start) or not _TIME_RE.match(end):
                raise ValueError
            price = round(float(p.get("price")), 4)
            if not math.isfinite(price):
                raise ValueError
            kind = str(p.get("kind") or "")
            if kind not in ("buy", "sell"):
                raise ValueError
            if price < 0 or price > 10:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"时段{i+1} 数据无效(名称/起止HH:MM/价格0~10/kind须buy|sell)")
        clean.append({"name": name, "start": start, "end": end, "price": price, "kind": kind})
    # 时段拓扑: 同时段两两不重叠 (start < end, 不支持跨午夜)
    spans = sorted((p["start"], p["end"], p["name"]) for p in clean)
    for (s1, e1, n1), (s2, e2, n2) in zip(spans, spans[1:]):
        if s2 < e1:
            raise HTTPException(status_code=422,
                                detail=f"时段重叠: {n1}({s1}-{e1}) 与 {n2}({s2}-{e2})")
    cur = _read_pricing()
    cur["periods"] = clean
    cur["updated_by"] = str(user.username)
    cur["updated_at"] = datetime.now(_tz.utc).isoformat()
    _PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 原子写: 临时文件 + os.replace, 加锁防并发 PUT 竞态
    with _PRICING_LOCK:
        fd, tmp_path = _tempfile.mkstemp(dir=str(_PRICING_FILE.parent),
                                         suffix=".tmp", text=True)
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(cur, f, ensure_ascii=False, indent=2)
            _os.replace(tmp_path, _PRICING_FILE)
        except BaseException:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass
            raise
    return success_response(cur, "V2G电价已保存")

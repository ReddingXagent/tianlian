"""
实时监控 API

卡 ddff009c: 废弃 random 假值, 接入真实 Telemetry 聚合。
- realtime: 每设备最新 Telemetry.grid_power_total 求和; todayConsumption 参考
  卡 36c6b919 口径 (charger_kwh 累计差值, 无则 avg(grid_power_total)×时长回退);
  efficiency 复用 analytics._calculate_device_efficiency 按设备类型分派。
- history: 按 start_time/end_time 真查询 Telemetry, 小时 bucket avg。
时间口径: 落库 naive-UTC (与 tz_utils 统一口径一致)。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, team_scope
from app.api.v1.analytics.efficiency import _calculate_device_efficiency
from app.core.response import success_response
from app.models.device import Device
from app.models.station import Station
from app.models.telemetry import Telemetry
from app.models.user import User
from app.tasks.tz_utils import biz_day_bounds_utc_naive, now_in_biz_tz

router = APIRouter(dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)


def _utc_naive(dt: datetime) -> datetime:
    """任意 datetime 归一为 UTC-naive (落库口径)。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_time_param(value: str, name: str) -> datetime:
    try:
        return _utc_naive(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"{name} 格式非法, 应为 ISO 8601"
        )


@router.get("/realtime", dependencies=[Depends(get_current_user)])
def get_realtime_data(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取实时监控数据 (真实 Telemetry 聚合, 空库返回全 0)"""
    try:
        day_start, _ = biz_day_bounds_utc_naive(now_in_biz_tz().date())
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        # ── 团队范围 (卡 dc4e094b): 团队级用户仅本 team 站点设备; admin 全量 ──
        tid = team_scope(user)
        device_q = db.query(Device)
        if tid is not None:
            device_q = device_q.join(Station, Device.station_id == Station.id).filter(
                Station.team_id == tid
            )
        devices = device_q.order_by(Device.id).all()
        total_power = 0.0
        power_trend = 0.0
        grid_import = 0.0
        grid_export = 0.0
        today_generation = 0.0
        today_consumption = 0.0
        device_items = []
        efficiencies: List[float] = []

        # ── 卡 11f7d020: 批量预取, 消除 N+1 ──
        device_ids = [d.id for d in devices]

        # 批量1: 每设备最新 2 条遥测整行 (窗口函数 rn<=2, 参照 devices/__init__.py 范式)
        recent_map: dict = {}  # device_id -> [latest, prev] (Telemetry 整行)
        if device_ids:
            rn_col = func.row_number().over(
                partition_by=Telemetry.device_id,
                order_by=Telemetry.timestamp.desc(),
            ).label("rn")
            subq = (
                db.query(Telemetry.id.label("tid"), rn_col)
                .filter(Telemetry.device_id.in_(device_ids))
                .subquery()
            )
            rows_recent = (
                db.query(Telemetry)
                .join(subq, Telemetry.id == subq.c.tid)
                .filter(subq.c.rn <= 2)
                .order_by(Telemetry.device_id, Telemetry.timestamp.desc())
                .all()
            )
            for t in rows_recent:
                recent_map.setdefault(t.device_id, []).append(t)

        # 批量2: 今日窗口遥测行 — 效率口径需逐行序列 (soc/pf 逐项均值), 单查询替代每设备一查;
        # 能耗仅取首末值 (首末非空 charger_kwh 差 / grid 均值×首末时间跨度), 不再逐设备发查询
        today_map: dict = {}  # device_id -> 今日行列表 (ts asc)
        if device_ids:
            rows_today = (
                db.query(Telemetry)
                .filter(
                    Telemetry.device_id.in_(device_ids),
                    Telemetry.timestamp >= day_start,
                    Telemetry.timestamp <= now_naive,
                )
                .order_by(Telemetry.device_id, Telemetry.timestamp.asc())
                .all()
            )
            for t in rows_today:
                today_map.setdefault(t.device_id, []).append(t)

        for device in devices:
            recent = recent_map.get(device.id)
            if not recent:
                continue
            latest, prev = recent[0], (recent[1] if len(recent) > 1 else None)

            power = latest.grid_power_total or 0.0
            total_power += power
            if power > 0:
                grid_import += power
            else:
                grid_export += abs(power)
            if prev is not None and prev.grid_power_total is not None:
                power_trend += power - prev.grid_power_total

            today_rows = today_map.get(device.id)
            if not today_rows:
                today_rows = [latest]

            today_generation += latest.daily_generation or 0.0

            # 能耗: 卡 36c6b919 口径 — charger_kwh 累计差值优先 (首末非空值差, 不加载全天明细)
            kwh_values = [t.charger_kwh for t in today_rows if t.charger_kwh is not None]
            if kwh_values:
                today_consumption += max(0.0, kwh_values[-1] - kwh_values[0])
            else:
                grid_values = [
                    t.grid_power_total for t in today_rows if t.grid_power_total is not None
                ]
                if grid_values:
                    avg_power = sum(grid_values) / len(grid_values)
                    hours = max(
                        0.0,
                        (today_rows[-1].timestamp - today_rows[0].timestamp).total_seconds() / 3600,
                    )
                    today_consumption += avg_power * hours

            efficiencies.append(_calculate_device_efficiency(today_rows, device))
            device_items.append({
                "id": device.id,
                "name": device.name,
                "type": device.device_type,
                "power": power,
                "status": device.status.value if device.status else "offline",
            })

        efficiency = (
            sum(efficiencies) / len(efficiencies) if efficiencies else 0.0
        )

        return success_response({
            "totalPower": round(total_power, 2),
            "powerTrend": round(power_trend, 2),
            "todayGeneration": round(today_generation, 2),
            "todayConsumption": round(today_consumption, 2),
            "gridImport": round(grid_import, 2),
            "gridExport": round(grid_export, 2),
            "efficiency": round(min(100.0, max(0.0, efficiency)), 2),
            "update_time": datetime.now(timezone.utc).isoformat(),
            "devices": device_items,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_realtime_data 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/history")
def get_history_data(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取历史监控数据 (Telemetry 小时 bucket avg, 默认 24h 窗)"""
    try:
        end = _parse_time_param(end_time, "end_time") if end_time else (
            datetime.now(timezone.utc).replace(tzinfo=None)
        )
        start = _parse_time_param(start_time, "start_time") if start_time else (
            end - timedelta(hours=24)
        )
        if end <= start:
            return success_response({"data": [], "total_records": 0})

        # ── 团队范围 (卡 dc4e094b): 团队级用户仅本 team 设备遥测; admin 全量 ──
        tid = team_scope(user)
        rows_q = db.query(Telemetry).filter(
            Telemetry.timestamp >= start, Telemetry.timestamp < end
        )
        if tid is not None:
            # 先取本 team device_ids 再 IN 过滤 (避免 Telemetry→Device→Station 双 join 歧义)
            scoped_device_ids = [
                row[0] for row in
                db.query(Device.id)
                .join(Station, Device.station_id == Station.id)
                .filter(Station.team_id == tid)
                .all()
            ]
            rows_q = rows_q.filter(Telemetry.device_id.in_(scoped_device_ids))
        # LIMIT 保护: 防超大时间窗口拖库 (聚合口径为小时 bucket, 上限足够覆盖)
        rows = rows_q.order_by(Telemetry.timestamp.asc()).limit(50000).all()
        if not rows:
            return success_response({"data": [], "total_records": 0})

        buckets = {}
        for t in rows:
            if t.timestamp is None:
                continue
            key = t.timestamp.replace(minute=0, second=0, microsecond=0)
            buckets.setdefault(key, []).append(t)

        data = []
        for key in sorted(buckets):
            group = buckets[key]
            def _avg(attr: str) -> float:
                values = [getattr(t, attr) for t in group if getattr(t, attr) is not None]
                return round(sum(values) / len(values), 2) if values else 0.0
            data.append({
                "time": key.isoformat(),
                "power": _avg("grid_power_total"),
                "generation": _avg("pv_power_total"),
                "consumption": _avg("charger_power"),
            })

        return success_response({"data": data, "total_records": len(data)})
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_history_data 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

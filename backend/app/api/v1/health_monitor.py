"""
健康度监控 API

端点:
  - GET  /health/devices          设备健康聚合概览(overall/rankings/evaluations/abnormal)
  - GET  /health/trend/{device_id} 设备健康度趋势 (DeviceHealthRecord 真实序列)
  - POST /health/calculate/{device_id} 计算设备健康度 (基于近期 Telemetry)

卡 6bc6f3f1: 废弃 random/硬编码假值。
- trend: DeviceHealthRecord.created_at 序列, 空返回 []; dimensions 取最新记录,
  无记录时各维度 null。
- calculate: 电气安全←电压偏差+功率因数, 热稳定性←温度/功率负载率,
  通信←telemetry 覆盖率; 取不到的维度 null 且 data_source 标注 no_telemetry;
  总分=可得维度加权(各维度 0-100 加权平均, 权重相等); 结果写 DeviceHealthRecord。
  无任何 telemetry 的设备: 落一条 comm_score 低位记录(契约: 不报 422 ——
  巡检场景需要"通信缺失"可视化而非请求失败, 聚合端点 /devices 读同一张表)。
时间口径: naive-UTC。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.response import success_response
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_device_team_access
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.models.device import Device, DeviceHealthRecord, DeviceStatus
from app.models.station import Station
from app.models.telemetry import Telemetry

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("analytics:manage"))])

# 健康分级阈值
HEALTHY_THRESHOLD = 80.0   # >= 健康
WARNING_THRESHOLD = 60.0   # [60, 80) 警告; <60 异常

# calculate 评估窗口
CALC_WINDOW = timedelta(hours=24)
CALC_EXPECTED_INTERVAL = timedelta(minutes=5)
# 额定电压参考值 (V) —— 电压偏差评分基准
NOMINAL_VOLTAGE = 230.0


def _status_of(score: float) -> str:
    """分数 -> 状态(normal/warning/critical)"""
    if score >= HEALTHY_THRESHOLD:
        return "normal"
    if score >= WARNING_THRESHOLD:
        return "warning"
    return "critical"


def _score_of(device: Device) -> float:
    return float(device.health_score) if device.health_score is not None else 0.0


def _abnormal_indicators(device: Device, score: float) -> list:
    indicators = []
    if device.status == DeviceStatus.FAULT:
        indicators.append("设备故障")
    if device.status == DeviceStatus.OFFLINE:
        indicators.append("设备离线")
    if score < WARNING_THRESHOLD:
        indicators.append(f"健康度偏低({score:.0f}分)")
    return indicators or ["健康度异常"]


def _suggestion_of(device: Device) -> str:
    if device.status == DeviceStatus.FAULT:
        return "设备处于故障状态，建议立即检修并安排维护"
    if device.status == DeviceStatus.OFFLINE:
        return "设备离线，建议检查通信链路与供电"
    return "健康度偏低，建议加强巡检并安排预防性维护"


@router.get("/devices")
def get_health_devices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """设备健康聚合概览

    返回:
      - overall:      全局概览(总数/健康/警告/异常/待评估/平均分)
      - rankings:     设备健康排名 {best: Top10, worst: Top10}
      - evaluations:  最近健康评估列表(DeviceHealthRecord 最近 20 条)
      - abnormal:     异常设备列表(health_score < 60)
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅本 team 设备（device→station→team）。
    # 多段 DB 聚合查询 → 兜底 500, 不泄露原始异常 (卡 a45c4f83)
    try:
        dev_q = db.query(Device)
        if not is_platform_admin(user):
            dev_q = dev_q.join(Station, Device.station_id == Station.id, isouter=True).filter(
                Station.team_id == user.team_id
            )
        devices = dev_q.all()

        # 站点名称映射
        station_ids = {d.station_id for d in devices if d.station_id is not None}
        station_map = {}
        if station_ids:
            stations = db.query(Station).filter(Station.id.in_(station_ids)).all()
            station_map = {s.id: s.name for s in stations}

        scored = [(_score_of(d), d, station_map.get(d.station_id, "")) for d in devices]
        scores = [s for s, _, _ in scored]
        total = len(scores)
        average_score = round(sum(scores) / total, 1) if total else 0.0

        overall = {
            "totalDevices": total,
            "healthyCount": sum(1 for s in scores if s >= HEALTHY_THRESHOLD),
            "warningCount": sum(1 for s in scores if WARNING_THRESHOLD <= s < HEALTHY_THRESHOLD),
            "criticalCount": sum(1 for s in scores if s < WARNING_THRESHOLD),
            "pendingEval": sum(1 for _, d, _ in scored if d.status == DeviceStatus.OFFLINE),
            "overallScore": average_score,
        }

        def _brief(score, device, station_name):
            return {
                "id": device.id,
                "deviceName": device.name,
                "code": device.code,
                "type": device.type.value if device.type else None,
                "stationName": station_name,
                "score": round(score, 1),
                "status": _status_of(score),
            }

        best_sorted = sorted(scored, key=lambda x: x[0], reverse=True)
        worst_sorted = sorted(scored, key=lambda x: x[0])
        rankings = {
            "best": [_brief(s, d, st) for s, d, st in best_sorted[:10]],
            "worst": [_brief(s, d, st) for s, d, st in worst_sorted[:10]],
        }

        # 最近健康评估(DeviceHealthRecord 最近 20 条)
        eval_rows = (
            db.query(DeviceHealthRecord, Device, Station)
            .join(Device, DeviceHealthRecord.device_id == Device.id)
            .outerjoin(Station, Device.station_id == Station.id)
            .order_by(DeviceHealthRecord.created_at.desc())
            .limit(20)
            .all()
        )
        evaluations = []
        for rec, dev, st in eval_rows:
            score = float(rec.total_score) if rec.total_score is not None else 0.0
            evaluations.append({
                "id": rec.id,
                "deviceId": dev.id,
                "deviceName": dev.name,
                "stationName": st.name if st else "",
                "score": round(score, 1),
                "evaluator": "系统",
                "evalDate": rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else "",
                "issues": [],
                "status": _status_of(score),
                "dimensions": {
                    "electrical_safety": rec.electrical_safe_score,
                    "thermal_stability": rec.thermal_score,
                    "communication": rec.comm_score,
                    "power_quality": rec.power_quality_score,
                    "mechanical_life": rec.mechanical_score,
                },
            })

        # 异常设备(health_score < 60)
        abnormal = []
        for score, d, st in scored:
            if score < WARNING_THRESHOLD:
                abnormal.append({
                    "id": d.id,
                    "deviceName": d.name,
                    "stationName": st,
                    "score": round(score, 1),
                    "abnormalIndicators": _abnormal_indicators(d, score),
                    "suggestion": _suggestion_of(d),
                })
    except Exception:
        logger.exception("设备健康聚合概览查询失败 user_id=%s", getattr(user, "id", None))
        raise HTTPException(status_code=500, detail="设备健康概览查询失败")

    return success_response({
        "overall": overall,
        "rankings": rankings,
        "evaluations": evaluations,
        "abnormal": abnormal,
    })


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _clamp_score(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def _score_electrical(rows: List[Telemetry]) -> Optional[int]:
    """电气安全: 电压偏差(偏离额定±10%内满分线性衰减) + 功率因数(≥0.95 满分)。"""
    voltages = [
        v for t in rows
        for v in (t.grid_voltage_a, t.grid_voltage_b, t.grid_voltage_c)
        if v is not None
    ]
    factors = [t.grid_power_factor for t in rows if t.grid_power_factor is not None]
    if not voltages and not factors:
        return None
    volt_score = 100.0
    if voltages:
        max_dev = max(abs(v - NOMINAL_VOLTAGE) / NOMINAL_VOLTAGE for v in voltages)
        volt_score = max(0.0, 100.0 - (max_dev / 0.10) * 100.0)
    pf_score = 100.0
    if factors:
        min_pf = max(0.0, min(factors))
        pf_score = max(0.0, min(100.0, min_pf / 0.95 * 100.0))
    if voltages and factors:
        return _clamp_score(volt_score * 0.5 + pf_score * 0.5)
    return _clamp_score(volt_score if voltages else pf_score)


def _score_thermal(rows: List[Telemetry], rated_power: Optional[float]) -> Optional[int]:
    """热稳定性: 温度(≤50℃满分, ≥90℃ 0分线性) + 功率负载率(≤80% 满分线性)。"""
    temps = [
        v for t in rows
        for v in (t.gun_temperature, t.internal_temperature, t.inv_temperature)
        if v is not None
    ]
    loads: List[float] = []
    if rated_power and rated_power > 0:
        powers = [abs(t.grid_power_total) for t in rows
                  if t.grid_power_total is not None]
        if powers:
            loads = [p / rated_power for p in powers]
    if not temps and not loads:
        return None
    temp_score = 100.0
    if temps:
        max_t = max(temps)
        temp_score = max(0.0, min(100.0, (90.0 - max_t) / (90.0 - 50.0) * 100.0))
    load_score = 100.0
    if loads:
        max_load = max(loads)
        load_score = max(0.0, min(100.0, (1.2 - max_load) / (1.2 - 0.8) * 100.0))
    if temps and loads:
        return _clamp_score(temp_score * 0.5 + load_score * 0.5)
    return _clamp_score(temp_score if temps else load_score)


def _score_comm(rows: List[Telemetry], window: timedelta) -> Optional[int]:
    """通信可靠性: 窗口内采样覆盖率 (条数×标称间隔 / 窗口时长, 上限 100)。"""
    if not rows:
        return None
    expected = window / CALC_EXPECTED_INTERVAL
    coverage = len(rows) / expected if expected > 0 else 0.0
    return _clamp_score(coverage * 100.0)


def _dims_payload(electrical, thermal, comm, power_quality, mechanical) -> Dict[str, Optional[int]]:
    return {
        "electrical_safety": electrical,
        "thermal_stability": thermal,
        "communication": comm,
        "power_quality": power_quality,
        "mechanical_life": mechanical,
    }


@router.get("/trend/{device_id}")
def get_health_trend(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """设备健康度趋势 (DeviceHealthRecord.created_at 序列, 空返回 [])"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 设备；越权/不存在 → 404。
    try:
        assert_device_team_access(db, device_id, user)
        records = (
            db.query(DeviceHealthRecord)
            .filter(DeviceHealthRecord.device_id == device_id)
            .order_by(DeviceHealthRecord.created_at.asc())
            .limit(30)
            .all()
        )
        trend = [
            {
                "date": rec.created_at.strftime("%Y-%m-%d") if rec.created_at else "",
                "health": round(float(rec.total_score), 1) if rec.total_score is not None else None,
            }
            for rec in records
        ]
        latest = records[-1] if records else None
        if latest is not None:
            dimensions = _dims_payload(
                latest.electrical_safe_score, latest.thermal_score,
                latest.comm_score, latest.power_quality_score, latest.mechanical_score,
            )
        else:
            dimensions = _dims_payload(None, None, None, None, None)
    except HTTPException:
        raise
    except Exception:
        logger.exception("设备健康趋势查询失败 device_id=%s", device_id)
        raise HTTPException(status_code=500, detail="设备健康趋势查询失败")
    return success_response({
        "device_id": device_id,
        "trend": trend,
        "dimensions": dimensions,
    })


@router.post("/calculate/{device_id}")
def calculate_health(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """计算设备健康度 (基于近 24h Telemetry, 结果写 DeviceHealthRecord)

    契约: 无任何 telemetry 的设备不返回随机值, 落一条 comm_score 低位记录 ——
    巡检场景需要"通信缺失"可视化(聚合端点 /devices 读同一张表), 422 会让
    批量巡检中断, 故选低分落库而非报错。mechanical/power_quality 无遥测
    数据源, 恒为 null 并在 data_source 说明。
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可计算本 team 设备；越权/不存在 → 404。
    try:
        assert_device_team_access(db, device_id, user)
        device = db.query(Device).filter(Device.id == device_id).first()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = now - CALC_WINDOW
        rows = (
            db.query(Telemetry)
            .filter(
                Telemetry.device_id == device_id,
                Telemetry.timestamp >= window_start,
                Telemetry.timestamp <= now,
            )
            .order_by(Telemetry.timestamp.asc())
            .all()
        )
        rated = float(device.rated_power) if (
            device is not None and device.rated_power is not None
        ) else None

        data_source: Dict[str, str] = {}
        if not rows:
            # 无任何遥测: 通信缺失 → 低位记录
            electrical = thermal = None
            comm = 30
            data_source = {k: "no_telemetry" for k in
                           ("electrical_safety", "thermal_stability")}
            data_source["communication"] = "no_telemetry_low_score"
        else:
            electrical = _score_electrical(rows)
            thermal = _score_thermal(rows, rated)
            comm = _score_comm(rows, CALC_WINDOW)
            data_source = {
                "electrical_safety": "telemetry" if electrical is not None else "no_data",
                "thermal_stability": "telemetry" if thermal is not None else "no_data",
                "communication": "telemetry",
            }
        data_source.setdefault("power_quality", "no_data")
        data_source.setdefault("mechanical_life", "no_data")

        scores = [s for s in (electrical, thermal, comm) if s is not None]
        total = round(sum(scores) / len(scores), 1) if scores else 0.0

        record = DeviceHealthRecord(
            device_id=device_id,
            electrical_safe_score=electrical,
            thermal_score=thermal,
            comm_score=comm,
            power_quality_score=None,
            mechanical_score=None,
            total_score=total,
        )
        db.add(record)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("设备健康度计算失败 device_id=%s", device_id)
        raise HTTPException(status_code=500, detail="设备健康度计算失败")
    return success_response({
        "device_id": device_id,
        "health": total,
        "calculated_at": now.isoformat() + "Z",
        "dimensions": _dims_payload(electrical, thermal, comm, None, None),
        "data_source": data_source,
    })

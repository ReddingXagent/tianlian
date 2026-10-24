"""设备健康度 + 效率端点（拆分自原 devices.py）。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.device import Device, DeviceHealthRecord
from app.models.user import User
from app.services.health_engine import health_engine
from app.core.response import success_response

from ._shared import logger, _check_device_team, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class HealthData(BaseModel):
    insulation_resistance: float = 10.0
    leakage_current: float = 5.0
    temperature: float = 45.0
    voltage: float = 220.0
    current: float = 32.0
    comm_success_rate: float = 98.0
    plug_count: int = 500
    ground_fault: bool = False
    temp_rise_rate: float = 1.0
    current_thd: float = 5.0
    gun_temperature: float = 35.0


@router.post("/{device_id}/health")
def calculate_health(device_id: int, data: HealthData, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """计算设备健康度（team scoping：跨团队 → 404）"""
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, device_id, user)

        # 计算健康度
        device_data = data.dict()
        total_score, dimension_scores = health_engine.calculate_health_score(
            device_data, device_type=device.type.value
        )

        # 更新设备健康度
        device.health_score = total_score
        db.commit()

        # 记录健康度历史
        record = DeviceHealthRecord(
            device_id=device_id,
            electrical_safe_score=int(dimension_scores['electrical']),
            thermal_score=int(dimension_scores['thermal']),
            comm_score=int(dimension_scores['communication']),
            power_quality_score=int(dimension_scores['power_quality']),
            mechanical_score=int(dimension_scores['mechanical']),
            total_score=total_score,
        )
        db.add(record)

        # 检查是否需要生成告警
        alarm_data = health_engine.generate_alarm(device_id, total_score, dimension_scores)

        db.commit()

        return success_response({
            'device_id': device_id,
            'total_score': total_score,
            'dimension_scores': dimension_scores,
            'alarm': alarm_data,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("calculate_health 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/{device_id}/health")
def get_device_health(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取设备健康度详情（team scoping：跨团队 → 404）"""
    from app.services.health import health_service

    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, device_id, user)

        health_info = health_service.get_device_health(device_id, db)
        if not health_info:
            raise HTTPException(status_code=404, detail="设备不存在")

        return success_response(health_info)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_device_health 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/{device_id}/health/history")
def get_health_history(device_id: int, days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取健康度历史（team scoping：跨团队 → 404）"""
    from datetime import timedelta
    try:
        _check_device_team(db, device_id, user)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        records = db.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == device_id,
            DeviceHealthRecord.created_at >= since
        ).order_by(DeviceHealthRecord.created_at.desc()).all()

        # 序列化记录
        record_dicts = [{
            'id': r.id,
            'device_id': r.device_id,
            'electrical_safe_score': r.electrical_safe_score,
            'thermal_score': r.thermal_score,
            'comm_score': r.comm_score,
            'power_quality_score': r.power_quality_score,
            'mechanical_score': r.mechanical_score,
            'total_score': r.total_score,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in records]

        return success_response(record_dicts)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_health_history 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

@router.get("/{device_id}/efficiency")
def get_device_efficiency(device_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    返回设备的利用率、充电效率、发电效率 + 历史趋势

    team scoping：跨团队 → 404。
    """
    from datetime import timedelta
    from app.models.device_efficiency_log import DeviceEfficiencyLog

    try:
        dev = db.query(Device).filter(Device.id == int(device_id)).first()
        if not dev:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, int(device_id), user)

        # 获取最近30天的效率日志
        since = datetime.now(timezone.utc) - timedelta(days=30)
        logs = (
            db.query(DeviceEfficiencyLog)
            .filter(
                DeviceEfficiencyLog.device_id == int(device_id),
                DeviceEfficiencyLog.recorded_at >= since,
            )
            .order_by(DeviceEfficiencyLog.recorded_at.asc())
            .all()
        )

        def _build_trend(metric_type: str):
            return [
                {
                    "date": l.recorded_at.strftime("%Y-%m-%d") if l.recorded_at else "",
                    "value": round(float(l.metric_value), 1),
                }
                for l in logs
                if l.metric_type == metric_type
            ]

        def _latest_value(metric_type: str):
            matching = [l for l in logs if l.metric_type == metric_type]
            return round(float(matching[-1].metric_value), 1) if matching else None

        return success_response({
            "device_id": device_id,
            "device_name": dev.name,
            "device_code": dev.code,
            "device_type": dev.type.value if dev.type else "unknown",
            "utilization": {
                "current": round(float(dev.utilization_rate or 0), 1),
                "trend": _build_trend("utilization"),
            },
            "charge_efficiency": {
                "current": _latest_value("charge"),
                "trend": _build_trend("charge"),
            },
            "generation_efficiency": {
                "current": _latest_value("generation"),
                "pv_pr": round(float(dev.pv_pr_ratio or 0), 4) if dev.pv_pr_ratio else None,
                "trend": _build_trend("generation"),
            },
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_device_efficiency 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

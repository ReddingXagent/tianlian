"""
预测性维护 API 路由
Phase10 - 基于LSTM的设备故障预测
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone

from app.core.database import get_db, get_async_db
from app.api.deps import assert_device_team_access, assert_device_team_access_async, is_platform_admin
from app.api.v1.auth import get_current_user, require_role
from app.services.predictive_maintenance import get_service
from app.services.predictive_maintenance.lstm_predictor import format_prediction_for_display
from app.models.device import Device
from app.models.station import Station
from app.models.telemetry import Telemetry
from app.models.user import User
from app.tasks.tz_utils import now_in_biz_tz

router = APIRouter(tags=["预测性维护"], dependencies=[Depends(require_role("admin", "operator"))])

logger = logging.getLogger(__name__)


def _biz_wall_ts_expr(col, db):
    """UTC-naive 落库时间戳列 → 业务时区墙钟 SQL 表达式 (卡 77b1ed08)。

    供 func.date() 分桶取业务日标签: 时间戳加业务时区 UTC 偏移后取 date,
    上海 00:00-08:00 (UTC 前日 16:00-24:00) 的遥测归业务次日桶。
    SQLite 用 datetime() 修饰符, PostgreSQL 用 interval 加法。
    """
    offset = now_in_biz_tz().utcoffset() or timedelta(0)
    secs = int(offset.total_seconds())
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return col + text(f"interval '{secs} seconds'")
    return func.datetime(col, f"+{secs} seconds")


# ============ Pydantic Schemas ============

class PredictionRequest(BaseModel):
    device_id: int
    hours: int = Field(24, ge=1, le=720)  # 使用最近多少小时的数据 (卡 1abf2c01: 防 timedelta 溢出 500)

class BatchPredictionRequest(BaseModel):
    device_ids: List[int]
    hours: int = Field(24, ge=1, le=720)

class TrainRequest(BaseModel):
    device_id: int
    days: int = Field(30, ge=1, le=365, description="使用多少天的历史数据训练")

class PredictionResponse(BaseModel):
    device_id: int
    device_name: str
    prediction_time: str
    failure_probability: float
    failure_probability_display: str
    risk_level: str
    risk_emoji: str
    health_trend: str
    trend_emoji: str
    rul_hours: Optional[float]
    rul_display: str
    anomaly_score: float
    key_indicators: List[dict]
    recommended_actions: List[str]
    confidence: float

class DashboardResponse(BaseModel):
    total_devices: int
    predicted_devices: int
    risk_summary: dict
    predictions: List[PredictionResponse]
    model_status: dict

class TrainingResponse(BaseModel):
    device_id: int
    status: str
    framework: str
    epochs: int
    final_loss: float
    samples: int


# ============ API Endpoints ============

@router.get("/dashboard", summary="预测性维护仪表盘")
async def get_dashboard(db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    """获取预测性维护仪表盘数据

    注：移除原 @cached(ttl=60) —— cache key 不含 user.team_id，跨用户同 URL 会串数据
    （任务卡 1c19b59a team scoping，同 stations.list_stations 治理）。
    """
    service = get_service()

    # 获取设备（team scoping：非 admin 仅本 team 设备）
    dev_stmt = select(Device)
    if not is_platform_admin(current_user):
        dev_stmt = dev_stmt.outerjoin(Station, Station.id == Device.station_id)\
                           .where(Station.team_id == current_user.team_id)
    devices = (await db.execute(dev_stmt)).scalars().all()
    device_ids = [d.id for d in devices]

    # ── Phase47: 批量获取遥测数据, 避免 N+1 ──
    # 卡 e0dcffcb: LIMIT 下推 SQL —— row_number() 窗口函数取每设备 timestamp desc 前100条,
    # 替代全量载入后 Python 截断（设备数×采样密度增长时内存线性膨胀）。
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    telemetry_map = {}
    if device_ids:  # 空 device_ids 短路, 防 in_([]) 全表语义/警告
        rn = func.row_number().over(
            partition_by=Telemetry.device_id,
            order_by=Telemetry.timestamp.desc(),
        ).label("rn")
        subq = select(Telemetry, rn).where(
            Telemetry.device_id.in_(device_ids),
            Telemetry.timestamp >= cutoff,
        ).subquery()
        aliased_t = aliased(Telemetry, subq)
        telemetry_rows = (await db.execute(
            select(aliased_t).where(subq.c.rn <= 100)
        )).scalars().all()
        for t in telemetry_rows:
            telemetry_map.setdefault(t.device_id, []).append(t)
    
    predictions = []
    risk_summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    
    for device in devices:
        try:
            telemetry = telemetry_map.get(device.id, [])
            
            if not telemetry:
                continue
            
            # 转换为字典列表
            data = [_telemetry_to_dict(t) for t in telemetry]
            
            result = await service.predict_failure(device.id, data, device.name)
            
            formatted = format_prediction_for_display(result)
            predictions.append(PredictionResponse(**formatted))
            risk_summary[result.risk_level] = risk_summary.get(result.risk_level, 0) + 1
        except Exception:
            # 跳过预测失败的设备（聚合场景），但绝不静默：记录日志供排查
            logger.exception("dashboard 设备 %s(%s) 预测失败，已跳过", device.id, device.name)
    
    model_status = service.get_model_status()
    
    return DashboardResponse(
        total_devices=len(devices),
        predicted_devices=len(predictions),
        risk_summary=risk_summary,
        predictions=predictions,
        model_status=model_status
    )


@router.post("/predict", summary="预测设备故障")
async def predict_device(request: PredictionRequest, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    """预测指定设备的故障概率"""
    # team scoping（任务卡 1c19b59a）：设备归属校验前置，跨团队 → 404。
    await assert_device_team_access_async(db, request.device_id, current_user)
    service = get_service()

    # 验证设备存在
    device = (await db.execute(
        select(Device).where(Device.id == request.device_id)
    )).scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {request.device_id} not found")

    # 获取历史遥测数据
    cutoff = datetime.now(timezone.utc) - timedelta(hours=request.hours)
    telemetry = (await db.execute(
        select(Telemetry).where(
            Telemetry.device_id == device.id,
            Telemetry.timestamp >= cutoff,
        ).order_by(Telemetry.timestamp.asc())
    )).scalars().all()

    if not telemetry:
        raise HTTPException(status_code=404, detail="No telemetry data found for this device")
    
    data = [_telemetry_to_dict(t) for t in telemetry]
    
    result = await service.predict_failure(device.id, data, device.name)
    
    return PredictionResponse(**format_prediction_for_display(result))


@router.post("/batch-predict", summary="批量预测")
async def batch_predict(request: BatchPredictionRequest, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    """批量预测多个设备的故障概率

    注：移除原 @cached(ttl=30) —— cache key 不含 user.team_id，跨用户同 request 会串数据
    （任务卡 1c19b59a team scoping）。
    """
    service = get_service()

    # ── Phase47: 批量查询设备和遥测数据（team scoping：非 admin 仅本 team 设备）──
    dev_stmt = select(Device).where(Device.id.in_(request.device_ids))
    if not is_platform_admin(current_user):
        dev_stmt = dev_stmt.outerjoin(Station, Station.id == Device.station_id)\
                           .where(Station.team_id == current_user.team_id)
    devices = (await db.execute(dev_stmt)).scalars().all()
    device_map = {d.id: d for d in devices}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=request.hours)
    telemetry_rows = (await db.execute(
        select(Telemetry).where(
            Telemetry.device_id.in_(request.device_ids),
            Telemetry.timestamp >= cutoff,
        ).order_by(Telemetry.timestamp.asc())
    )).scalars().all()

    telemetry_map = {}
    for t in telemetry_rows:
        telemetry_map.setdefault(t.device_id, []).append(t)
    
    results = []
    for device_id in request.device_ids:
        device = device_map.get(device_id)
        if not device:
            continue
        telemetry = telemetry_map.get(device_id, [])
        if not telemetry:
            continue
        data = [_telemetry_to_dict(t) for t in telemetry]
        try:
            result = await service.predict_failure(device.id, data, device.name)
            results.append(PredictionResponse(**format_prediction_for_display(result)))
        except Exception:
            logger.exception("batch-predict 设备 %s 预测失败", device_id)
            results.append({
                "device_id": device_id,
                "device_name": device.name,
                "error": "prediction failed",
            })
    
    return results


@router.post("/train", summary="训练模型")
async def train_model(request: TrainRequest, db: AsyncSession = Depends(get_async_db), current_user: User = Depends(get_current_user)):
    """训练指定设备的预测模型"""
    # team scoping（任务卡 1c19b59a）：设备归属校验前置，跨团队 → 404。
    await assert_device_team_access_async(db, request.device_id, current_user)
    service = get_service()

    device = (await db.execute(
        select(Device).where(Device.id == request.device_id)
    )).scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {request.device_id} not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=request.days)
    telemetry = (await db.execute(
        select(Telemetry).where(
            Telemetry.device_id == device.id,
            Telemetry.timestamp >= cutoff,
        ).order_by(Telemetry.timestamp.asc())
    )).scalars().all()

    if len(telemetry) < 50:
        raise HTTPException(
            status_code=400, 
            detail=f"Not enough data for training. Need at least 50 records, got {len(telemetry)}"
        )
    
    data = [_telemetry_to_dict(t) for t in telemetry]
    result = await service.train_device_model(device.id, data)
    
    return TrainingResponse(
        device_id=device.id,
        status=result['status'],
        framework=result['framework'],
        epochs=result['epochs'],
        final_loss=result['final_loss'],
        samples=result['samples']
    )


@router.get("/model-status", summary="模型状态")
async def get_model_status():
    """获取所有预测模型的状态"""
    service = get_service()
    return service.get_model_status()


@router.get("/device/{device_id}/history", summary="预测历史")
def get_prediction_history(
    device_id: int,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取设备的历史预测记录"""
    # team scoping（任务卡 1c19b59a）：设备归属校验前置，跨团队 → 404。
    assert_device_team_access(db, device_id, current_user)
    # 验证设备
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 返回模拟历史数据（实际应从prediction_history表查询）
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # 卡 7c1c396d: 按日聚合下推 SQL（GROUP BY date + avg/count/sum），
    # 不再全量物化 ORM 行后用 Python 聚合 —— 分钟级遥测 90 天可达数万行。
    # 卡 77b1ed08: 分桶边界按业务时区(上海)墙钟日界切 (参照卡 20cb47ed
    # energy_report): 时间戳先加业务 UTC 偏移再取 date, 上海 00:00-08:00
    # (UTC 前日 16:00-24:00) 的遥测归业务次日桶, 而非 UTC 日桶。
    day_expr = func.date(_biz_wall_ts_expr(Telemetry.timestamp, db))
    daily_rows = db.query(
        day_expr.label('day'),
        func.avg(Telemetry.battery_soc).label('avg_soc'),
        func.avg(Telemetry.battery_temperature).label('avg_temp'),
        func.avg(Telemetry.battery_soh).label('avg_soh'),
        func.sum(case((Telemetry.bms_alarm_word > 0, 1), else_=0)).label('anomaly_count'),
        func.count(Telemetry.id).label('total_count'),
    ).filter(
        Telemetry.device_id == device_id,
        Telemetry.timestamp >= cutoff
    ).group_by(day_expr).order_by(day_expr.asc()).all()

    history = []
    for row in daily_rows:
        history.append({
            'date': row.day if isinstance(row.day, str) else row.day.strftime('%Y-%m-%d'),
            'avg_soc': float(row.avg_soc) if row.avg_soc is not None else None,
            'avg_temperature': float(row.avg_temp) if row.avg_temp is not None else None,
            'avg_soh': float(row.avg_soh) if row.avg_soh is not None else None,
            'anomaly_rate': row.anomaly_count / max(row.total_count, 1),
            'record_count': row.total_count,
        })

    return {
        'device_id': device_id,
        'device_name': device.name,
        'period_days': days,
        'history': history
    }


def _telemetry_to_dict(t: Telemetry) -> dict:
    """将Telemetry ORM对象转为字典"""
    return {
        'device_id': t.device_id,
        'timestamp': t.timestamp.isoformat() if t.timestamp else None,
        'battery_soc': t.battery_soc,
        'battery_soh': t.battery_soh,
        'battery_temperature': t.battery_temperature,
        'battery_voltage': t.battery_voltage,
        'battery_current': t.battery_current,
        'battery_power': t.battery_power,
        'grid_voltage_a': t.grid_voltage_a,
        'grid_voltage_b': t.grid_voltage_b,
        'grid_voltage_c': t.grid_voltage_c,
        'grid_current_a': t.grid_current_a,
        'grid_current_b': t.grid_current_b,
        'grid_current_c': t.grid_current_c,
        'grid_frequency': t.grid_frequency,
        'grid_power_total': t.grid_power_total,
        'grid_power_factor': t.grid_power_factor,
        'inv_temperature': t.inv_temperature,
        'internal_temperature': t.internal_temperature,
        'pv_temperature': t.pv_temperature,
        'charger_power': t.charger_power,
        'charger_voltage': t.charger_voltage,
        'charger_current': t.charger_current,
        'gun_temperature': t.gun_temperature,
        'bms_alarm_word': t.bms_alarm_word,
        'bms_alarm_word2': t.bms_alarm_word2,
        'system_status': t.system_status,
        'run_time': t.run_time,
    }

"""
智能诊断 API - 设备故障诊断和维修建议
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.database import get_db
from app.models.device import Device, DeviceStatus, DeviceType, DeviceHealthRecord
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.workorder import WorkOrder, WorkOrderStatus
from app.models.station import Station
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin, assert_device_team_access, assert_station_team_access
from app.models.user import User
from app.core.response import success_response
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])

# 风险等级排序映射：用显式等级比较替代字符串 max()（任务 3f243177）。
# 字符串 max 走字典序，max("low","high")=="low"（'l'>'h'），导致风险永不升级。
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# ========== Schema ==========

class DiagnosisRequest(BaseModel):
    """诊断请求"""
    device_id: int
    include_history: bool = True  # 是否包含历史数据

class DiagnosisResult(BaseModel):
    """诊断结果"""
    device_id: int
    device_name: str
    device_sn: str
    device_type: str
    station_name: str
    overall_health: float
    diagnosis_time: str
    
    # 五维度评分
    scores: dict
    
    # 诊断分析
    analysis: List[dict]
    
    # 风险等级
    risk_level: str  # low/medium/high/critical
    
    # 维修建议
    recommendations: List[dict]
    
    # 预测故障
    predicted_failures: List[dict]
    
    # 维修成本预估
    estimated_cost: dict
    
    # 历史工单统计
    workorder_stats: dict
    
    # 历史告警统计
    alarm_stats: dict

class BatchDiagnosisRequest(BaseModel):
    """批量诊断请求"""
    station_id: Optional[int] = None
    device_type: Optional[str] = None
    min_health_score: Optional[float] = None

class BatchDiagnosisResult(BaseModel):
    """批量诊断结果"""
    total_devices: int
    healthy_devices: int
    warning_devices: int
    fault_devices: int
    critical_devices: int
    avg_health_score: float
    top_issues: List[dict]
    devices: List[DiagnosisResult]

# ========== 数据库依赖 ==========

# USING get_db FROM app.core.database

# ========== 诊断规则库 ==========

DIAGNOSIS_RULES = {
    # 电气安全诊断规则
    "electrical": {
        "critical": [
            {"condition": "electrical_safe_score < 60", "issue": "电气安全严重风险", "action": "立即停机检查"},
            {"condition": "alarm_level == 'critical' and alarm_type == 'electrical'", "issue": "电气故障告警", "action": "紧急维修"},
        ],
        "warning": [
            {"condition": "electrical_safe_score < 80", "issue": "电气安全需关注", "action": "安排巡检"},
            {"condition": "alarm_count > 3", "issue": "多次电气告警", "action": "排查隐患"},
        ],
    },
    # 热稳定性诊断规则
    "thermal": {
        "critical": [
            {"condition": "thermal_score < 50", "issue": "温度异常严重", "action": "检查散热系统"},
        ],
        "warning": [
            {"condition": "thermal_score < 70", "issue": "温度偏高", "action": "清洁散热器"},
        ],
    },
    # 通信诊断规则
    "communication": {
        "critical": [
            {"condition": "comm_score < 40", "issue": "通信中断", "action": "检查网络连接"},
            {"condition": "device_status == 'offline'", "issue": "设备离线", "action": "检查网关和网络"},
        ],
        "warning": [
            {"condition": "comm_score < 60", "issue": "通信不稳定", "action": "检查信号强度"},
        ],
    },
    # 电能质量诊断规则
    "power_quality": {
        "critical": [
            {"condition": "power_quality_score < 50", "issue": "电能质量严重异常", "action": "检查供电系统"},
        ],
        "warning": [
            {"condition": "power_quality_score < 70", "issue": "电能质量下降", "action": "检测电压电流"},
        ],
    },
    # 机械寿命诊断规则
    "mechanical": {
        "critical": [
            {"condition": "mechanical_score < 40", "issue": "机械部件老化", "action": "更换老化部件"},
        ],
        "warning": [
            {"condition": "mechanical_score < 60", "issue": "机械磨损", "action": "润滑保养"},
        ],
    },
}

# 设备类型特定诊断
DEVICE_TYPE_DIAGNOSIS = {
    "charger_dc": {
        "issues": ["充电模块故障", "连接器磨损", "散热系统异常", "通信模块故障"],
        "cost_range": {"minor": 500, "medium": 2000, "major": 5000},
    },
    "charger_ac": {
        "issues": ["充电接口故障", "控制板异常", "接地不良"],
        "cost_range": {"minor": 300, "medium": 1500, "major": 3000},
    },
    "pv_inverter": {
        "issues": ["逆变器效率下降", "MPPT异常", "绝缘阻抗低", "风扇故障"],
        "cost_range": {"minor": 800, "medium": 5000, "major": 15000},
    },
    "battery": {
        "issues": ["电池衰减", "BMS异常", "温度异常", "充放电异常"],
        "cost_range": {"minor": 1000, "medium": 10000, "major": 50000},
    },
    "meter": {
        "issues": ["计量误差", "通信故障", "接线松动"],
        "cost_range": {"minor": 200, "medium": 800, "major": 2000},
    },
    "gateway": {
        "issues": ["网络中断", "数据采集异常", "固件故障"],
        "cost_range": {"minor": 100, "medium": 500, "major": 1000},
    },
}

# ========== 诊断 API ==========

@router.post("/device")
def diagnose_device(
    data: DiagnosisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单个设备智能诊断

    分析维度：
    1. 健康度五维度评分分析
    2. 历史告警统计分析
    3. 历史工单统计分析
    4. 规则库诊断推理
    5. 风险等级评估
    6. 维修建议生成
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可诊断本 team 设备；越权/不存在 → 404。
    try:
        assert_device_team_access(db, data.device_id, user)
        # 获取设备
        device = db.query(Device).filter(Device.id == data.device_id).first()
    
        station = db.query(Station).filter(Station.id == device.station_id).first()
    
        # 获取最新健康记录
        health_record = db.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == device.id
        ).order_by(desc(DeviceHealthRecord.created_at)).first()
    
        # 获取告警统计（卡 d9076d31：count 下推 SQL，替代全量 ORM 载入）
        alarm_total = db.query(func.count(Alarm.id)).filter(Alarm.device_id == device.id).scalar() or 0
        alarm_active = db.query(func.count(Alarm.id)).filter(
            Alarm.device_id == device.id, Alarm.status == AlarmStatus.ACTIVE
        ).scalar() or 0
        alarm_critical = db.query(func.count(Alarm.id)).filter(
            Alarm.device_id == device.id, Alarm.status == AlarmStatus.ACTIVE, Alarm.level == AlarmLevel.CRITICAL
        ).scalar() or 0

        # 获取工单统计（同上 count 下推）
        wo_total = db.query(func.count(WorkOrder.id)).filter(WorkOrder.device_id == device.id).scalar() or 0
        wo_pending = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.device_id == device.id,
            WorkOrder.status.in_([WorkOrderStatus.PENDING, WorkOrderStatus.PROCESSING]),
        ).scalar() or 0
        wo_completed = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.device_id == device.id, WorkOrder.status == WorkOrderStatus.COMPLETED
        ).scalar() or 0
    
        # 五维度评分
        scores = {
            "electrical_safe": health_record.electrical_safe_score if health_record else 100,
            "thermal": health_record.thermal_score if health_record else 100,
            "communication": health_record.comm_score if health_record else 100,
            "power_quality": health_record.power_quality_score if health_record else 100,
            "mechanical": health_record.mechanical_score if health_record else 100,
        }
    
        # 诊断分析
        analysis = []
        risk_level = "low"
    
        # 检查设备状态
        if device.status == DeviceStatus.FAULT:
            analysis.append({
                "category": "设备状态",
                "issue": "设备处于故障状态",
                "severity": "critical",
                "score": 0,
            })
            risk_level = "critical"
        elif device.status == DeviceStatus.OFFLINE:
            analysis.append({
                "category": "设备状态",
                "issue": "设备离线",
                "severity": "high",
                "score": scores["communication"],
            })
            if _RISK_ORDER["high"] > _RISK_ORDER[risk_level]:
                risk_level = "high"
    
        # 应用诊断规则
        for category, rules in DIAGNOSIS_RULES.items():
            score_key = {
                "electrical": "electrical_safe",
                "thermal": "thermal",
                "communication": "communication",
                "power_quality": "power_quality",
                "mechanical": "mechanical",
            }.get(category, category)
        
            score = scores.get(score_key, 100)
        
            # 检查严重规则
            for rule in rules.get("critical", []):
                if score < 60:
                    analysis.append({
                        "category": category,
                        "issue": rule["issue"],
                        "severity": "critical",
                        "score": score,
                        "action": rule["action"],
                    })
                    risk_level = "critical"
        
            # 检查警告规则
            for rule in rules.get("warning", []):
                if score < 80 and score >= 60:
                    analysis.append({
                        "category": category,
                        "issue": rule["issue"],
                        "severity": "warning",
                        "score": score,
                        "action": rule["action"],
                    })
                    if _RISK_ORDER["medium"] > _RISK_ORDER[risk_level]:
                        risk_level = "medium"
    
        # 检查活跃告警
        if alarm_active > 0:
            alarm_analysis = {
                "category": "告警",
                "issue": f"存在 {alarm_active} 个活跃告警",
                "severity": "high" if alarm_critical > 0 else "warning",
                "count": alarm_active,
                "critical_count": alarm_critical,
            }
            analysis.append(alarm_analysis)
            if alarm_critical > 0:
                risk_level = "critical"
    
        # 生成维修建议
        recommendations = []
        for item in analysis:
            if item.get("action"):
                recommendations.append({
                    "priority": "high" if item["severity"] in ["critical", "high"] else "medium",
                    "category": item["category"],
                    "action": item["action"],
                    "reason": item["issue"],
                })
    
        # 添加预防性维护建议
        if device.last_maintenance:
            days_since = (datetime.now(timezone.utc).date() - device.last_maintenance).days
            if days_since > 30:
                recommendations.append({
                    "priority": "medium",
                    "category": "预防性维护",
                    "action": "安排定期巡检维护",
                    "reason": f"已 {days_since} 天未维护",
                })
    
        # 预测故障
        predicted_failures = []
        device_type_info = DEVICE_TYPE_DIAGNOSIS.get(device.type.value, {})
        for issue in device_type_info.get("issues", []):
            # 根据健康度预测故障概率
            if device.health_score < 80:
                predicted_failures.append({
                    "type": issue,
                    "probability": "高" if device.health_score < 60 else "中",
                    "preventive_action": f"预防性检查 {issue}",
                })
    
        # 维修成本预估
        cost_range = device_type_info.get("cost_range", {"minor": 500, "medium": 2000, "major": 5000})
        if risk_level == "critical":
            estimated_cost = {"min": cost_range["major"], "max": cost_range["major"] * 2}
        elif risk_level == "high":
            estimated_cost = {"min": cost_range["medium"], "max": cost_range["major"]}
        else:
            estimated_cost = {"min": cost_range["minor"], "max": cost_range["medium"]}
    
        return success_response({
            "device_id": device.id,
            "device_name": device.name,
            "device_sn": device.sn,
            "device_type": device.type.value,
            "station_name": station.name if station else "未知",
            "overall_health": device.health_score or 100.0,
            "diagnosis_time": str(datetime.now(timezone.utc)),
        
            # 五维度评分
            "scores": scores,
        
            # 诊断分析
            "analysis": analysis,
        
            # 风险等级
            "risk_level": risk_level,
        
            # 维修建议
            "recommendations": recommendations,
        
            # 预测故障
            "predicted_failures": predicted_failures,
        
            # 维修成本预估
            "estimated_cost": estimated_cost,
        
            # 历史工单统计
            "workorder_stats": {
                "total": wo_total,
                "pending": wo_pending,
                "completed": wo_completed,
            },

            # 历史告警统计
            "alarm_stats": {
                "total": alarm_total,
                "active": alarm_active,
                "critical": alarm_critical,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("diagnose_device 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

@router.post("/batch")
def diagnose_batch(
    data: BatchDiagnosisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量诊断 - 站点或设备类型级别

    快速评估多设备健康状态，生成整体诊断报告
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅本 team 设备；station_id 越权 → 404。
    try:
        if not is_platform_admin(user):
            if data.station_id:
                assert_station_team_access(db, data.station_id, user)
        query = db.query(Device)

        # 筛选条件
        if data.station_id:
            query = query.filter(Device.station_id == data.station_id)
        if data.device_type:
            query = query.filter(Device.type == DeviceType(data.device_type))
        if data.min_health_score:
            query = query.filter(Device.health_score <= data.min_health_score)
        if not is_platform_admin(user):
            query = query.join(Station, Device.station_id == Station.id, isouter=True).filter(
                Station.team_id == user.team_id
            )
    
        devices = query.all()
    
        # 统计
        healthy = len([d for d in devices if d.health_score >= 90])
        warning = len([d for d in devices if d.health_score >= 70 and d.health_score < 90])
        fault = len([d for d in devices if d.health_score >= 50 and d.health_score < 70])
        critical = len([d for d in devices if d.health_score < 50])
    
        avg_health = sum([d.health_score or 100 for d in devices]) / len(devices) if devices else 100
    
        # 收集主要问题（卡 0e7deb3d 性能优化）：原实现逐不健康设备 count active 告警，
        # K 个不健康设备 = K 条 SQL；改为一条 GROUP BY 批量取，结果 shape/排序不变。
        top_issues = []
        unhealthy = [d for d in devices if d.health_score and d.health_score < 80]
        if unhealthy:
            alarm_counts = dict(
                db.query(Alarm.device_id, func.count(Alarm.id))
                .filter(
                    Alarm.device_id.in_([d.id for d in unhealthy]),
                    Alarm.status == AlarmStatus.ACTIVE,
                )
                .group_by(Alarm.device_id)
                .all()
            )
        else:
            alarm_counts = {}
        for device in unhealthy:
            active_alarms = alarm_counts.get(device.id, 0)
            if active_alarms > 0:
                top_issues.append({
                    "device_name": device.name,
                    "health_score": device.health_score,
                    "alarm_count": active_alarms,
                    "status": device.status.value,
                })

        # 按健康度排序
        top_issues = sorted(top_issues, key=lambda x: x["health_score"])[:10]
    
        return success_response({
            "total_devices": len(devices),
            "healthy_devices": healthy,
            "warning_devices": warning,
            "fault_devices": fault,
            "critical_devices": critical,
            "avg_health_score": round(avg_health, 1),
            "top_issues": top_issues,
            "summary": {
                "health_rate": round(healthy / len(devices) * 100, 1) if devices else 100,
                "risk_devices": warning + fault + critical,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("diagnose_batch 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

@router.get("/health-trend/{device_id}")
def get_health_trend(
    device_id: int,
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取设备健康度趋势

    用于可视化展示健康度变化
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 设备；越权/不存在 → 404。
    try:
        assert_device_team_access(db, device_id, user)
        device = db.query(Device).filter(Device.id == device_id).first()
    
        # 获取最近记录
        records = db.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == device_id,
            DeviceHealthRecord.created_at >= datetime.now(timezone.utc) - timedelta(days=days)
        ).order_by(DeviceHealthRecord.created_at).all()
    
        trend_data = []
        for record in records:
            trend_data.append({
                "date": str(record.created_at.date()),
                "total_score": record.total_score,
                "electrical": record.electrical_safe_score,
                "thermal": record.thermal_score,
                "communication": record.comm_score,
                "power_quality": record.power_quality_score,
                "mechanical": record.mechanical_score,
            })
    
        return success_response({
            "device_id": device_id,
            "device_name": device.name,
            "trend_data": trend_data,
            "summary": {
                "start_score": trend_data[0]["total_score"] if trend_data else 100,
                "end_score": trend_data[-1]["total_score"] if trend_data else device.health_score,
                "change": trend_data[-1]["total_score"] - trend_data[0]["total_score"] if len(trend_data) > 1 else 0,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_health_trend 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

@router.get("/station-summary/{station_id}")
def station_diagnosis_summary(
    station_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """站点诊断摘要

    快速查看站点整体健康状态和需要关注的设备
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 站点；越权/不存在 → 404。
    # assert 返回 Station ORM，复用替代手动查询+404。
    try:
        station = assert_station_team_access(db, station_id, user)
    
        devices = db.query(Device).filter(Device.station_id == station_id).all()
    
        # 统计各类型设备健康度
        type_health = {}
        for device in devices:
            if device.type.value not in type_health:
                type_health[device.type.value] = {"total": 0, "avg_health": 0, "devices": []}
            type_health[device.type.value]["total"] += 1
            type_health[device.type.value]["avg_health"] += device.health_score or 100
            type_health[device.type.value]["devices"].append({
                "id": device.id,
                "name": device.name,
                "health_score": device.health_score,
                "status": device.status.value,
            })
    
        # 计算平均值
        for type_name in type_health:
            type_health[type_name]["avg_health"] = round(
                type_health[type_name]["avg_health"] / type_health[type_name]["total"], 1
            )
    
        # 告警统计
        active_alarms = db.query(Alarm).filter(
            Alarm.station_id == station_id,
            Alarm.status == AlarmStatus.ACTIVE
        ).count()
    
        # 工单统计
        pending_workorders = db.query(WorkOrder).filter(
            WorkOrder.station_id == station_id,
            WorkOrder.status.in_([WorkOrderStatus.PENDING, WorkOrderStatus.PROCESSING])
        ).count()
    
        return success_response({
            "station_id": station_id,
            "station_name": station.name,
            "total_devices": len(devices),
            "type_health": type_health,
            "active_alarms": active_alarms,
            "pending_workorders": pending_workorders,
            "overall_health": round(sum([d.health_score or 100 for d in devices]) / len(devices), 1) if devices else 100,
            "risk_devices": [
                {"id": d.id, "name": d.name, "health_score": d.health_score, "status": d.status.value}
                for d in devices if d.health_score and d.health_score < 80
            ],
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("station_diagnosis_summary 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

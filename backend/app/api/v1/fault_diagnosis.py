"""
故障码诊断 API - 基于光储充设备协议分析
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import (
    is_platform_admin,
    assert_station_team_access,
    assert_alarm_team_access,
    require_platform_admin,
)
from app.models.user import User
from app.models.fault_code import FaultCode, RepairGuide

logger = logging.getLogger(__name__)
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.station import Station
from app.core.response import success_response, paginated_response, action_response

router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])

# USING get_db FROM app.core.database

# ========== 故障码查询 ==========

@router.get("/fault-codes")
def list_fault_codes(
    device_type: Optional[str] = None,
    fault_category: Optional[str] = None,
    fault_level: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    查询故障码知识库
    
    支持按设备类型、故障分类、等级筛选
    """
    query = db.query(FaultCode).filter(FaultCode.enabled == True)
    
    if device_type:
        query = query.filter(FaultCode.device_type == device_type)
    if fault_category:
        query = query.filter(FaultCode.fault_category == fault_category)
    if fault_level:
        query = query.filter(FaultCode.fault_level == fault_level)
    if keyword:
        query = query.filter(
            FaultCode.fault_name.contains(keyword) | 
            FaultCode.fault_description.contains(keyword)
        )
    
    total = query.count()
    fault_codes = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return paginated_response(
        items=[
            {
                "fault_code": fc.fault_code,
                "fault_name": fc.fault_name,
                "fault_description": fc.fault_description,
                "device_type": fc.device_type,
                "fault_category": fc.fault_category.value if fc.fault_category else None,
                "fault_level": fc.fault_level.value if fc.fault_level else None,
                "response_time_minutes": fc.response_time_minutes,
                "auto_stop": fc.auto_stop,
                "remote_fixable": fc.remote_fixable,
                "possible_causes": fc.possible_causes,
                "diagnosis_steps": fc.diagnosis_steps,
                "repair_suggestions": fc.repair_suggestions,
            }
            for fc in fault_codes
        ],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/fault-codes/{fault_code}")
def get_fault_code_detail(
    fault_code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取故障码详细信息
    
    包含：故障描述、可能原因、诊断步骤、修复建议、修复指南
    """
    fc = db.query(FaultCode).filter(FaultCode.fault_code == fault_code).first()
    if not fc:
        raise HTTPException(status_code=404, detail="故障码不存在")
    
    # 获取关联修复指南
    guides = db.query(RepairGuide).filter(
        RepairGuide.fault_code_id == fc.id,
        RepairGuide.enabled == True
    ).all()
    
    return success_response({
        "fault_code": fc.fault_code,
        "fault_name": fc.fault_name,
        "fault_description": fc.fault_description,
        "device_type": fc.device_type,
        "fault_category": fc.fault_category.value if fc.fault_category else None,
        "fault_level": fc.fault_level.value if fc.fault_level else None,
        "modbus_address": fc.modbus_address,
        "mqtt_code": fc.mqtt_code,
        
        # 诊断信息
        "possible_causes": fc.possible_causes or [],
        "diagnosis_steps": fc.diagnosis_steps or [],
        "repair_suggestions": fc.repair_suggestions or [],
        
        # 响应要求
        "response_time_minutes": fc.response_time_minutes,
        "auto_stop": fc.auto_stop,
        "remote_fixable": fc.remote_fixable,
        
        # 统计
        "occurrence_count": fc.occurrence_count,
        "avg_repair_time_minutes": fc.avg_repair_time_minutes,
        
        # 修复指南
        "repair_guides": [
            {
                "id": g.id,
                "title": g.title,
                "estimated_time_minutes": g.estimated_time_minutes,
                "difficulty_level": g.difficulty_level,
                "required_tools": g.required_tools,
                "success_rate": g.success_rate,
            }
            for g in guides
        ]
    })

# ========== 故障诊断 ==========

class AlarmDiagnosisRequest(BaseModel):
    """告警诊断请求"""
    alarm_id: int

@router.post("/alarm-diagnosis")
def diagnose_alarm(
    data: AlarmDiagnosisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    告警故障诊断

    根据告警的故障码，匹配故障知识库，生成诊断建议

    基于光储充设备协议分析：
    - 逆变器Modbus故障码（0x01-0xD4）
    - 充电桩MQTT故障码（0x01XX-0x08XX）
    - PCS故障码
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可诊断本 team 告警；越权/不存在 → 404。
    assert_alarm_team_access(db, data.alarm_id, user)
    alarm = db.query(Alarm).filter(Alarm.id == data.alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    device = db.query(Device).filter(Device.id == alarm.device_id).first()
    
    # 匹配故障码
    fault_code_record = None
    if alarm.fault_code:
        fault_code_record = db.query(FaultCode).filter(
            FaultCode.fault_code == alarm.fault_code
        ).first()
    
    # 如果没找到精确匹配，尝试根据设备类型和告警类型推断
    if not fault_code_record and device:
        # 查找同类设备的类似故障
        similar_faults = db.query(FaultCode).filter(
            FaultCode.device_type == device.type.value,
            FaultCode.enabled == True
        ).limit(5).all()
    
    diagnosis_result = {
        "alarm_id": alarm.id,
        "device_id": alarm.device_id,
        "device_name": device.name if device else None,
        "device_type": device.type.value if device else None,
        "alarm_level": alarm.level.value,
        "fault_code": alarm.fault_code,
        "fault_source": alarm.fault_source,
        "content": alarm.content,
    }
    
    if fault_code_record:
        diagnosis_result.update({
            "matched": True,
            "fault_name": fault_code_record.fault_name,
            "fault_description": fault_code_record.fault_description,
            "fault_level": fault_code_record.fault_level.value,
            "response_time_minutes": fault_code_record.response_time_minutes,
            "auto_stop": fault_code_record.auto_stop,
            "remote_fixable": fault_code_record.remote_fixable,
            
            # 诊断建议
            "possible_causes": fault_code_record.possible_causes or [],
            "diagnosis_steps": fault_code_record.diagnosis_steps or [],
            "repair_suggestions": fault_code_record.repair_suggestions or [],
            
            # 自动生成诊断结果
            "diagnosis_summary": f"{fault_code_record.fault_name}，{fault_code_record.fault_description}",
        })
        
        # 更新告警的诊断信息
        alarm.diagnosis_result = diagnosis_result["diagnosis_summary"]
        alarm.remote_fixable = fault_code_record.remote_fixable
        db.commit()
        
    else:
        diagnosis_result.update({
            "matched": False,
            "message": "未找到匹配的故障码，请人工诊断",
            "similar_faults": [
                {
                    "fault_code": sf.fault_code,
                    "fault_name": sf.fault_name,
                }
                for sf in (similar_faults if 'similar_faults' in dir() else [])
            ]
        })
    
    return success_response(diagnosis_result)

@router.post("/quick-diagnosis")
def quick_diagnosis(
    fault_code: str = Query(..., description="故障编码"),
    device_type: str = Query(..., description="设备类型"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    快速故障诊断
    
    输入故障码和设备类型，快速获取诊断建议
    
    示例：
    - fault_code=0x7E, device_type=inverter → BMS通信异常诊断
    - fault_code=0x0601, device_type=charger → 充电桩BMS通信异常诊断
    """
    fc = db.query(FaultCode).filter(
        FaultCode.fault_code == fault_code,
        FaultCode.device_type == device_type
    ).first()
    
    if not fc:
        # 尝试模糊匹配
        fc = db.query(FaultCode).filter(
            FaultCode.fault_code == fault_code
        ).first()
    
    if not fc:
        raise HTTPException(
            status_code=404, 
            detail=f"未找到故障码 {fault_code} 的诊断信息"
        )
    
    return success_response({
        "fault_code": fc.fault_code,
        "fault_name": fc.fault_name,
        "fault_level": fc.fault_level.value,
        "fault_category": fc.fault_category.value if fc.fault_category else None,
        
        # 快速诊断
        "quick_diagnosis": {
            "possible_causes": fc.possible_causes[:3] if fc.possible_causes else [],  # 前3个原因
            "first_action": fc.repair_suggestions[0] if fc.repair_suggestions else "请查阅维修手册",
            "response_time": f"{fc.response_time_minutes} 分钟内响应",
            "need_stop": fc.auto_stop,
            "can_remote_fix": fc.remote_fixable,
        },
        
        # 详细诊断步骤
        "diagnosis_steps": fc.diagnosis_steps or [],
        
        # 修复建议
        "repair_suggestions": fc.repair_suggestions or [],
    })

# ========== 远程修复尝试 ==========

class RemoteFixRequest(BaseModel):
    """远程修复请求"""
    alarm_id: int
    fix_type: str  # reset/param_adjust/reboot/firmware_upgrade

@router.post("/remote-fix-attempt")
def attempt_remote_fix(
    data: RemoteFixRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    远程修复尝试

    对于标记为 remote_fixable=True 的故障，尝试远程修复

    支持的修复类型：
    - reset: 软件复位（通信模块/控制单元）
    - param_adjust: 参数调整（功率/电压/频率阈值）
    - reboot: 远程重启（安全条件下）
    - firmware_upgrade: 固件升级（OTA）

    基于协议：
    - Modbus 0x06/0x10 写寄存器控制
    - MQTT 0x4000-0x5FFF 设置类型消息
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可对本 team 告警远程修复；越权/不存在 → 404。
    assert_alarm_team_access(db, data.alarm_id, user)
    alarm = db.query(Alarm).filter(Alarm.id == data.alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    if not alarm.remote_fixable:
        raise HTTPException(
            status_code=400, 
            detail="该故障不支持远程修复，需现场处理"
        )
    
    device = db.query(Device).filter(Device.id == alarm.device_id).first()
    
    # 根据修复类型生成修复指令
    fix_instructions = {
        "reset": {
            "description": "软件复位",
            "modbus_command": "写寄存器 1024 = 0x01（复位指令）",
            "mqtt_message": "0x4001（复位控制消息）",
            "success_criteria": "设备重启后状态恢复正常",
        },
        "param_adjust": {
            "description": "参数调整",
            "example": "调整保护阈值（如过压阈值从260V调整为270V）",
            "modbus_command": "写寄存器 1026-1035（控制参数区）",
            "mqtt_message": "0x4000系列（参数设置消息）",
            "success_criteria": "参数调整后故障不再触发",
        },
        "reboot": {
            "description": "远程重启",
            "modbus_command": "写寄存器 1024 = 0x02（重启指令）",
            "mqtt_message": "0x4002（重启控制消息）",
            "success_criteria": "设备重启成功，故障清除",
            "warning": "需确保设备安全状态下重启",
        },
        "firmware_upgrade": {
            "description": "固件升级",
            "steps": [
                "1. 检查当前固件版本",
                "2. 上传新固件",
                "3. 触发升级指令",
                "4. 等待升级完成（约5-10分钟）",
                "5. 验证新版本",
            ],
            "modbus_command": "USB状态寄存器（地址1-4）",
            "mqtt_message": "通过MQTT下发固件包",
            "success_criteria": "固件版本更新，功能正常",
        },
    }
    
    if data.fix_type not in fix_instructions:
        raise HTTPException(status_code=400, detail="不支持的修复类型")
    
    # 更新告警状态
    alarm.remote_fix_attempted = True
    alarm.remote_fix_result = f"尝试 {data.fix_type}，等待验证"
    db.commit()
    
    return success_response({
        "alarm_id": alarm.id,
        "device_id": device.id,
        "device_name": device.name,
        "device_type": device.type.value,
        "fix_type": data.fix_type,
        "fix_instructions": fix_instructions[data.fix_type],
        "protocol_type": device.protocol_type.value if device.protocol_type else None,
        "device_address": device.device_address,
        "tcu_address": device.tcu_address,
        
        "message": "远程修复指令已生成，请通过设备网关下发",
        "next_step": "等待设备响应，验证修复效果",
    })

# ========== 统计分析 ==========

@router.get("/fault-statistics")
def get_fault_statistics(
    station_id: Optional[int] = None,
    device_type: Optional[str] = None,
    days: int = Query(30, ge=1, le=90, description="统计最近N天"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    故障统计分析

    统计故障发生频率、类型分布、修复效率
    """
    from datetime import timedelta

    # team scoping（任务卡 ab5c5f17）：非 admin 仅本 team 告警；station_id 越权 → 404。
    if not is_platform_admin(user):
        if station_id:
            assert_station_team_access(db, station_id, user)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = db.query(Alarm).filter(Alarm.created_at >= since)

    if station_id:
        query = query.filter(Alarm.station_id == station_id)
    if not is_platform_admin(user):
        query = query.join(Station, Alarm.station_id == Station.id, isouter=True).filter(
            Station.team_id == user.team_id
        )

    alarms = query.all()
    
    # 按故障码统计
    fault_code_stats = {}
    for alarm in alarms:
        code = alarm.fault_code or "unknown"
        if code not in fault_code_stats:
            fault_code_stats[code] = {"count": 0, "alarms": []}
        fault_code_stats[code]["count"] += 1
        fault_code_stats[code]["alarms"].append(alarm.id)
    
    # 按故障源统计
    fault_source_stats = {}
    for alarm in alarms:
        source = alarm.fault_source or "unknown"
        if source not in fault_source_stats:
            fault_source_stats[source] = 0
        fault_source_stats[source] += 1
    
    # 按等级统计
    level_stats = {}
    for alarm in alarms:
        level = alarm.level.value
        if level not in level_stats:
            level_stats[level] = 0
        level_stats[level] += 1
    
    # 修复效率
    processed = [a for a in alarms if a.status.value == "processed"]
    avg_repair_time = 0
    if processed:
        repair_times = []
        for a in processed:
            if a.handled_at and a.created_at:
                repair_times.append((a.handled_at - a.created_at).total_seconds() / 60)
        avg_repair_time = sum(repair_times) / len(repair_times) if repair_times else 0
    
    # 远程修复成功率
    remote_fix_attempts = [a for a in alarms if a.remote_fix_attempted]
    remote_fix_success = len([a for a in remote_fix_attempts if a.status.value == "processed"])
    
    return success_response({
        "total_alarms": len(alarms),
        "days": days,
        "fault_code_distribution": dict(sorted(
            fault_code_stats.items(), 
            key=lambda x: x[1]["count"], 
            reverse=True
        )[:10]),  # 前10个高频故障码
        "fault_source_distribution": fault_source_stats,
        "level_distribution": level_stats,
        "repair_statistics": {
            "processed_count": len(processed),
            "avg_repair_time_minutes": round(avg_repair_time, 1),
            "remote_fix_attempts": len(remote_fix_attempts),
            "remote_fix_success_rate": f"{remote_fix_success}/{len(remote_fix_attempts)}" if remote_fix_attempts else "无",
        }
    })

# ========== 初始化故障码 ==========

@router.post("/init-fault-codes")
def init_fault_codes_db(
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """
    初始化故障码知识库
    
    导入基于协议分析的故障码数据
    """
    from app.data.fault_codes_init import init_fault_codes
    
    try:
        init_fault_codes(db)
        return action_response(success=True, message="故障码知识库初始化成功")
    except Exception as e:
        logger.exception("故障码知识库初始化失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")
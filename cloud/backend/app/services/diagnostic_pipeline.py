#!/Users/xxx/.openclaw/workspace/projects/tianlian-v3/backend/venv/bin/python3
"""
诊断流水线编排器 - 故障自动触发诊断流程

触发流程:
1. 告警创建 → trigger_auto_diagnosis(alarm_id)
2. 远程读取设备日志 (模拟)
3. AI 分析日志
4. 匹配知识库故障码
5. 存入诊断记录
6. 更新告警的诊断结果
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.station import Station
from app.models.fault_code import FaultCode
from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus
from app.services.ai_diagnosis import analyze_with_fallback
from app.services.device_log_simulator import DeviceLogSimulator
from app.services.runbook_engine import execute_runbook_for_alarm

logger = logging.getLogger(__name__)


def _dictify(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns} if obj else {}


def trigger_diagnosis(
    alarm_id: int,
    trigger_type: str = "auto",
    db: Optional[Session] = None
) -> Dict:
    """
    触发诊断流水线
    
    1. 获取告警信息
    2. 获取设备信息
    3. 远程读取设备日志 (模拟)
    4. AI 分析日志
    5. 匹配知识库
    6. 存储诊断记录
    7. 更新告警
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()
    
    try:
        # 1. 获取告警
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            raise ValueError(f"告警 {alarm_id} 不存在")
        
        # 2. 获取设备信息
        device = db.query(Device).filter(Device.id == alarm.device_id).first()
        if not device:
            raise ValueError(f"设备 {alarm.device_id} 不存在")
        
        station = db.query(Station).filter(Station.id == (alarm.station_id or device.station_id)).first()
        
        device_info = dict(_dictify(device))
        if station:
            device_info["station_name"] = station.name
        else:
            device_info["station_name"] = "未知站点"
        device_info["type_name"] = device_info.get("device_type", device_info.get("type", "未知"))
        
        # 3. 读取设备日志 (模拟)
        fault_code = alarm.fault_code or device_info.get("fault_code") or "0x01"
        device_type = "inverter" if device_info.get("type_name", "").lower() in ["inverter", "逆变器", "pcs"] else "charger"
        
        logs = DeviceLogSimulator.get_logs_for_alarm(
            device_type=device_type,
            fault_code=fault_code,
            fault_name=alarm.alarm_type
        )
        
        # 4. 创建诊断记录
        record = AIDiagnosisRecord(
            alarm_id=alarm_id,
            device_id=device.id,
            station_id=alarm.station_id or device.station_id,
            status=DiagnosisStatus.RUNNING,
            trigger_type=trigger_type,
            log_source="remote",
            raw_log="\n".join(logs),
        )
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(record)
        
        # 5. AI 分析日志
        fault_context = {
            "level": alarm.level.value if hasattr(alarm.level, 'value') else alarm.level,
            "content": alarm.content,
            "fault_code": fault_code,
            "fault_source": alarm.fault_source or fault_code,
            "created_at": alarm.created_at.isoformat() if alarm.created_at else None
        }
        
        analysis = analyze_with_fallback(device_info, logs, fault_context)
        
        # 6. 更新诊断记录
        if analysis["success"]:
            result = analysis["result"]
            record.status = DiagnosisStatus.COMPLETED
            record.fault_type = result.get("fault_type")
            record.fault_location = result.get("fault_location")
            record.root_cause = result.get("root_cause")
            record.severity = result.get("severity")
            record.confidence = result.get("confidence")
            record.immediate_actions = result.get("immediate_actions")
            record.repair_suggestions = result.get("repair_suggestions")
            record.preventive_measures = result.get("preventive_measures")
            record.remote_fixable = result.get("remote_fixable", False)
            
            # 匹配知识库
            matched = _match_fault_code(db, result.get("fault_type", ""), result.get("fault_location", ""), device_type)
            if matched:
                record.matched_fault_code = matched["fault_code"]
                record.matched_fault_name = matched["fault_name"]
        else:
            record.status = DiagnosisStatus.FAILED
            record.error_message = analysis.get("error")
        
        record.raw_ai_response = analysis.get("raw_response")
        record.duration_ms = analysis.get("duration_ms")
        record.completed_at = datetime.now(timezone.utc)
        
        # 7. 更新告警的诊断结果
        if analysis["success"]:
            alarm.diagnosis_result = analysis["result"].get("root_cause", "")
            alarm.repair_suggestion = "\n".join(analysis["result"].get("repair_suggestions", []))
            alarm.remote_fixable = analysis["result"].get("remote_fixable", False)
        
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(record)
        
        # 8. 触发Runbook自动化修复 (Phase9 #53)
        runbook_result = None
        if analysis["success"]:
            try:
                runbook_result = execute_runbook_for_alarm(
                    alarm_id=alarm_id,
                    diagnosis_result=analysis["result"],
                    device_info=device_info,
                    db=db,
                )
                logger.info("Runbook执行完成: %s, 状态:%s", runbook_result.get('runbook_id'), runbook_result.get('status'))
            except Exception as rb_e:
                logger.error("Runbook执行失败: %s", str(rb_e))
                runbook_result = {"error": str(rb_e)}
        
        logger.info("诊断完成: 告警#%s, 记录#%s, 耗时%dms", alarm_id, record.id, analysis.get('duration_ms', 0))
        
        result = {
            "success": True,
            "record_id": record.id,
            "model_used": analysis.get("model_used"),
            "duration_ms": analysis.get("duration_ms"),
        }
        if runbook_result:
            result["runbook"] = runbook_result
        return result
        
    except Exception as e:
        logger.error("诊断失败: 告警#%s, 错误: %s", alarm_id, str(e))
        # 业务校验异常 (主动 raise 的 ValueError, 如告警/设备不存在) 透传受控消息;
        # 未知异常脱敏防泄露 (cc2272b84)
        if isinstance(e, ValueError):
            return {"success": False, "error": str(e)}
        return {
            "success": False,
            "error": "服务内部错误，请稍后重试",
        }
    finally:
        if own_db:
            db.close()


def _match_fault_code(db: Session, fault_type: str, fault_location: str, device_type: str) -> Optional[Dict]:
    """在知识库中匹配故障码"""
    try:
        fault_codes = db.query(FaultCode).filter(
            FaultCode.enabled == True,
            FaultCode.device_type == device_type
        ).all()
        
        best_match = None
        best_score = 0
        
        for fc in fault_codes:
            score = 0
            name = fc.fault_name or ""
            desc = fc.fault_description or ""
            causes = " ".join(fc.possible_causes or [])
            suggestions = " ".join(fc.repair_suggestions or [])
            
            search_text = f"{name} {desc} {causes} {suggestions}"
            
            # 简单的关键词匹配
            if fault_type and fault_type in search_text:
                score += 3
            if fault_location and fault_location in search_text:
                score += 2
            
            if score > best_score:
                best_score = score
                best_match = {
                    "fault_code": fc.fault_code,
                    "fault_name": fc.fault_name,
                }
        
        if best_score >= 2:
            return best_match
        return None
        
    except Exception:
        return None


def trigger_auto_diagnosis(alarm_id: int) -> Dict:
    """告警自动触发诊断（由告警创建时调用）"""
    return trigger_diagnosis(alarm_id, trigger_type="auto")
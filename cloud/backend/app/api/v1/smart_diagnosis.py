"""
智能诊断 API - 故障诊断和推荐方案
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin, assert_device_team_access
from app.models.user import User
from app.models.device import Device
from app.models.knowledge import KnowledgeArticle
from app.models.station import Station
from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
from app.core.response import success_response, paginated_response
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["智能故障诊断"], dependencies=[Depends(require_write_permission("healing:manage"))])

# ========== Schema ==========

class DiagnosisRequest(BaseModel):
    """诊断请求"""
    device_id: Optional[int] = None
    fault_desc: str  # 故障描述
    fault_keywords: Optional[List[str]] = None  # 用户提供的故障关键词

class DiagnosisResult(BaseModel):
    """诊断结果"""
    success: bool
    fault_type: str  # 故障类型
    fault_level: str  # 故障级别
    possible_causes: List[str]  # 可能原因
    recommended_actions: List[str]  # 推荐处理步骤
    related_articles: List[dict]  # 相关知识库文章
    auto_create_workorder: bool  # 是否建议自动创建工单
    confidence: float  # 诊断置信度

class FaultKeywords(BaseModel):
    """故障关键词"""
    keywords: List[str]

# ========== 数据库依赖 ==========

# USING get_db FROM app.core.database

# ========== 故障关键词库 ==========

FAULT_KEYWORDS_MAP = {
    # 通信故障
    "通信": {
        "type": "通信故障",
        "level": "warning",
        "causes": ["网络连接异常", "信号不稳定", "设备通信模块故障", "网线松动"],
        "actions": ["检查网络连接", "重启设备", "检查网线接口", "联系网络运维"],
    },
    "离线": {
        "type": "通信故障",
        "level": "critical",
        "causes": ["设备断网", "电源故障", "通信模块损坏", "网络中断"],
        "actions": ["检查设备电源", "检查网络连接", "重启设备", "联系技术支持"],
    },
    "连接": {
        "type": "通信故障",
        "level": "warning",
        "causes": ["网络不稳定", "连接超时", "设备响应慢"],
        "actions": ["检查网络质量", "重启设备", "优化网络配置"],
    },
    
    # 电气故障
    "电压": {
        "type": "电气异常",
        "level": "warning",
        "causes": ["电压不稳定", "供电异常", "设备过压/欠压"],
        "actions": ["检查供电电压", "检查设备电压监测", "调整供电配置"],
    },
    "电流": {
        "type": "电气异常",
        "level": "warning",
        "causes": ["电流过大", "负载异常", "设备故障"],
        "actions": ["检查负载情况", "检查设备电流监测", "降低负载"],
    },
    "功率": {
        "type": "电气异常",
        "level": "info",
        "causes": ["功率波动", "输出不稳定", "设备效率下降"],
        "actions": ["检查功率输出", "检查设备运行状态", "优化运行参数"],
    },
    
    # 设备故障
    "故障": {
        "type": "设备故障",
        "level": "warning",
        "causes": ["设备运行异常", "硬件故障", "软件故障", "参数配置错误"],
        "actions": ["查看设备日志", "检查设备状态", "重启设备", "联系技术支持"],
    },
    "异常": {
        "type": "设备故障",
        "level": "warning",
        "causes": ["设备行为异常", "参数偏离正常范围", "传感器误报"],
        "actions": ["检查设备参数", "校准传感器", "重启设备"],
    },
    "损坏": {
        "type": "设备故障",
        "level": "critical",
        "causes": ["硬件损坏", "设备老化", "外力损伤", "质量问题"],
        "actions": ["更换损坏部件", "联系维修工程师", "记录损坏情况"],
    },
    "停机": {
        "type": "设备故障",
        "level": "critical",
        "causes": ["设备意外停机", "电源故障", "过热保护", "故障停机"],
        "actions": ["检查停机原因", "检查设备电源", "检查设备温度", "重启设备"],
    },
    
    # 充电桩特定故障
    "充电": {
        "type": "充电异常",
        "level": "warning",
        "causes": ["充电枪连接异常", "充电功率异常", "充电停止", "充电超时"],
        "actions": ["检查充电枪连接", "检查充电功率", "重启充电桩", "检查充电参数"],
    },
    "无法启动": {
        "type": "充电异常",
        "level": "warning",
        "causes": ["充电桩无法启动充电", "充电枪未连接", "车辆通信异常", "充电桩故障"],
        "actions": ["检查充电枪连接", "检查车辆状态", "重启充电桩", "联系技术支持"],
    },
    "充电慢": {
        "type": "充电异常",
        "level": "info",
        "causes": ["充电功率低", "设备老化", "电压不稳定", "车辆限制"],
        "actions": ["检查充电功率", "检查设备状态", "优化充电参数", "检查车辆充电限制"],
    },
    
    # 逆变器特定故障
    "逆变器": {
        "type": "逆变器故障",
        "level": "warning",
        "causes": ["逆变器运行异常", "功率输出异常", "温度过高", "电网异常"],
        "actions": ["检查逆变器状态", "检查功率输出", "检查温度", "检查电网状态"],
    },
    "发电": {
        "type": "逆变器故障",
        "level": "info",
        "causes": ["发电量下降", "光照不足", "设备老化", "配置错误"],
        "actions": ["检查光照条件", "检查设备状态", "检查配置参数", "清洁光伏板"],
    },
    
    # 储能特定故障
    "电池": {
        "type": "储能故障",
        "level": "warning",
        "causes": ["电池电压异常", "电池温度异常", "电池容量下降", "电池老化"],
        "actions": ["检查电池电压", "检查电池温度", "检查电池容量", "联系技术支持"],
    },
    "储能": {
        "type": "储能故障",
        "level": "warning",
        "causes": ["储能系统异常", "充放电异常", "电池组故障", "PCS故障"],
        "actions": ["检查储能系统状态", "检查充放电情况", "检查电池组", "检查PCS"],
    },
    
    # 温度故障
    "温度": {
        "type": "温度异常",
        "level": "warning",
        "causes": ["设备温度过高", "散热异常", "环境温度过高", "传感器故障"],
        "actions": ["检查设备温度", "检查散热系统", "改善环境通风", "校准温度传感器"],
    },
    "过热": {
        "type": "温度异常",
        "level": "critical",
        "causes": ["设备严重过热", "散热系统故障", "负载过大", "环境温度过高"],
        "actions": ["立即停机降温", "检查散热系统", "降低负载", "改善通风"],
    },
    
    # 显示故障
    "显示": {
        "type": "显示异常",
        "level": "info",
        "causes": ["显示屏故障", "显示内容异常", "连接异常"],
        "actions": ["检查显示屏连接", "重启设备", "检查显示配置"],
    },
    "屏幕": {
        "type": "显示异常",
        "level": "info",
        "causes": ["屏幕故障", "显示异常", "触摸屏失灵"],
        "actions": ["检查屏幕连接", "重启设备", "更换显示屏"],
    },
}

# ========== 智能诊断 API ==========

@router.post("/analyze")
def analyze_fault(
    data: DiagnosisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """智能故障诊断

    流程:
    1. 分析故障描述，提取关键词
    2. 匹配故障关键词库
    3. 查询相关知识库文章
    4. 生成诊断报告和推荐方案
    """
    # team scoping（任务卡 ab5c5f17）：指定设备时非 admin 仅可诊断本 team 设备；越权/不存在 → 404。
    try:
        if data.device_id:
            assert_device_team_access(db, data.device_id, user)
        fault_desc = data.fault_desc.lower()
    
        # 提取故障关键词
        matched_keywords = []
        for keyword, info in FAULT_KEYWORDS_MAP.items():
            if keyword in fault_desc:
                matched_keywords.append({
                    "keyword": keyword,
                    "info": info,
                })
    
        if not matched_keywords:
            # 未匹配到关键词，返回通用诊断
            return success_response({
                "success": True,
                "fault_type": "未知故障",
                "fault_level": "warning",
                "possible_causes": ["需要进一步现场检查", "故障描述不够具体", "可能是新型故障"],
                "recommended_actions": [
                    "现场检查设备状态",
                    "查看设备运行日志",
                    "联系技术支持",
                    "创建检修工单",
                ],
                "related_articles": [],
                "auto_create_workorder": True,
                "confidence": 0.3,
                "message": "未能识别具体故障类型，建议现场检查",
            })
    
        # 合并匹配结果
        fault_levels = [k["info"]["level"] for k in matched_keywords]
    
        # 选择最高级别的故障
        level_priority = {"critical": 3, "warning": 2, "info": 1}
        selected_level = max(fault_levels, key=lambda x: level_priority.get(x, 0))
    
        # 合并原因和处理步骤
        all_causes = []
        all_actions = []
        for match in matched_keywords:
            all_causes.extend(match["info"]["causes"])
            all_actions.extend(match["info"]["actions"])
    
        # 去重
        possible_causes = list(set(all_causes))[:5]  # 最多返回5个原因
        recommended_actions = list(set(all_actions))[:5]  # 最多返回5个处理步骤
    
        # 查询相关知识库文章
        search_keywords = matched_keywords[0]["keyword"] if matched_keywords else fault_desc[:10]
        related_articles = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.title.contains(search_keywords) | 
            KnowledgeArticle.content.contains(search_keywords)
        ).limit(5).all()
    
        articles_data = [
            {
                "id": article.id,
                "title": article.title,
                "category": getattr(article, 'category', '未知分类'),
                "summary": article.content[:100] + "..." if len(article.content) > 100 else article.content,
                "views": getattr(article, 'views', 0),
            }
            for article in related_articles
        ]
    
        # 计算置信度
        confidence = min(len(matched_keywords) * 0.2 + 0.4, 0.95)
    
        # 判断是否需要自动创建工单
        auto_create_workorder = selected_level in ["critical", "warning"]
    
        # 如果提供了设备ID，查询设备信息
        device_info = None
        if data.device_id:
            device = db.query(Device).filter(Device.id == data.device_id).first()
            if device:
                device_info = {
                    "id": device.id,
                    "name": device.name,
                    "type": device.type.value,
                    "status": device.status.value,
                }
    
        return success_response({
            "success": True,
            "fault_type": matched_keywords[0]["info"]["type"] if matched_keywords else "未知故障",
            "fault_level": selected_level,
            "possible_causes": possible_causes,
            "recommended_actions": recommended_actions,
            "related_articles": articles_data,
            "auto_create_workorder": auto_create_workorder,
            "confidence": confidence,
            "matched_keywords": [k["keyword"] for k in matched_keywords],
            "device_info": device_info,
            "message": f"诊断完成，识别到 {len(matched_keywords)} 个故障关键词",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analyze_fault 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

# ========== 快速诊断并创建工单 ==========

@router.post("/diagnose-and-repair")
def diagnose_and_repair(
    data: DiagnosisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """诊断并自动创建工单

    流程:
    1. 智能诊断故障
    2. 如果建议创建工单，自动创建
    3. 返回诊断结果和工单信息
    """
    # team scoping（任务卡 ab5c5f17）：指定设备时非 admin 仅可对本 team 设备诊断并建单；越权/不存在 → 404。
    try:
        if data.device_id:
            assert_device_team_access(db, data.device_id, user)
        # 先进行诊断（直调函数拿到的是 success_response 信封，业务字段在 data 下）
        diagnosis_result = analyze_fault(data, db, user)
        diagnosis_result = diagnosis_result.get("data", diagnosis_result) if isinstance(diagnosis_result, dict) else diagnosis_result

        # 如果建议创建工单，自动创建
        workorder_info = None
        if diagnosis_result.get("auto_create_workorder") and data.device_id:
            device = db.query(Device).filter(Device.id == data.device_id).first()
            if device:
                # 生成工单号
                now = datetime.now(timezone.utc)
                wo_id = f"WO-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
            
                # 创建工单
                workorder = WorkOrder(
                    id=wo_id,
                    fault_desc=data.fault_desc,
                    type=WorkOrderType.REPAIR,
                    level=WorkOrderLevel(diagnosis_result["fault_level"]),
                    station_id=device.station_id,
                    device_id=device.id,
                    status=WorkOrderStatus.PENDING,
                    creator_id=user.id,
                )
                db.add(workorder)
                db.commit()
                db.refresh(workorder)
            
                workorder_info = {
                    "workorder_id": wo_id,
                    "status": "pending",
                    "message": "已自动创建工单，等待工程师处理",
                }
    
        return success_response({
            **diagnosis_result,
            "workorder": workorder_info,
            "message": "诊断完成" + ("，已自动创建工单" if workorder_info else ""),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("diagnose_and_repair 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

# ========== 故障关键词查询 ==========

@router.get("/keywords")
def list_fault_keywords(user: User = Depends(get_current_user)):
    """获取故障关键词列表"""
    try:
        keywords = [
            {
                "keyword": k,
                "type": info["type"],
                "level": info["level"],
            }
            for k, info in FAULT_KEYWORDS_MAP.items()
        ]
    
        return success_response({
            "keywords": keywords,
            "total": len(keywords),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_fault_keywords 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

# ========== 历史诊断记录查询 ==========

@router.get("/history")
def list_diagnosis_history(
    device_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询历史诊断记录"""
    try:
        from app.models.ai_diagnosis import AIDiagnosisRecord

        query = db.query(AIDiagnosisRecord)
        if device_id:
            query = query.filter(AIDiagnosisRecord.device_id == device_id)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅本 team 设备的诊断记录（device→station→team）。
        if not is_platform_admin(user):
            query = (
                query.join(Device, AIDiagnosisRecord.device_id == Device.id, isouter=True)
                .join(Station, Device.station_id == Station.id, isouter=True)
                .filter(Station.team_id == user.team_id)
            )
        query = query.order_by(AIDiagnosisRecord.created_at.desc())
    
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
    
        result = []
        for item in items:
            result.append({
                'id': item.id,
                'device_id': item.device_id,
                'device_name': item.device_name if hasattr(item, 'device_name') else None,
                'station_id': item.station_id if hasattr(item, 'station_id') else None,
                'diagnosis_type': item.diagnosis_type if hasattr(item, 'diagnosis_type') else 'smart',
                'status': item.status.value if hasattr(item.status, 'value') else str(item.status),
                'summary': item.summary if hasattr(item, 'summary') else None,
                'fault_codes': item.fault_codes if hasattr(item, 'fault_codes') else [],
                'recommendations': item.recommendations if hasattr(item, 'recommendations') else [],
                'confidence': item.confidence if hasattr(item, 'confidence') else None,
                'created_at': item.created_at.isoformat() if item.created_at else None,
            })
    
        return paginated_response(
            items=result,
            total=total,
            page=page,
            page_size=page_size
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_diagnosis_history 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

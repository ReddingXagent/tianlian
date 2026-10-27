"""
扫码报修 API - 扫码识别和快速报修
"""
from fastapi import APIRouter, HTTPException, Depends, Query
import logging
logger = logging.getLogger(__name__)
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
import qrcode
import os
import uuid

from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin
from app.models.user import User
from app.core.database import get_db
from app.models.device import Device
from app.models.device_qrcode import DeviceQRCode
from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
from app.models.station import Station
from app.core.response import success_response, paginated_response, action_response

router = APIRouter()

# ========== Schema ==========

class ScanRequest(BaseModel):
    """扫码请求"""
    qr_code: str = Field(..., max_length=200)

class ScanResult(BaseModel):
    """扫码结果"""
    success: bool
    device_id: int
    device_sn: str
    device_name: str
    device_type: str
    device_status: str
    station_id: int
    station_name: str
    station_address: str
    health_score: float
    last_maintenance: Optional[str]
    qr_code: str

class QuickRepairRequest(BaseModel):
    """快速报修请求"""
    device_id: int
    fault_desc: str
    fault_level: str = "warning"  # info/warning/critical
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    attachments: Optional[list] = None  # 照片/视频URL列表

class QuickRepairResult(BaseModel):
    """快速报修结果"""
    success: bool
    workorder_id: str
    device_name: str
    station_name: str
    fault_desc: str
    status: str
    create_time: str
    message: str

class QRCodeGenerateRequest(BaseModel):
    """生成二维码请求"""
    device_id: int
    notes: Optional[str] = None

class QRCodeGenerateResult(BaseModel):
    """生成二维码结果"""
    success: bool
    qr_code: str
    qr_image_url: str
    device_id: int
    device_name: str

# ========== 数据库依赖 ==========

# USING get_db FROM app.core.database

# ========== 扫码识别 API ==========

@router.post("/device")
def scan_device(data: ScanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """扫码识别设备 (需认证, 卡b1b04cda: 收紧为登录用户)

    支持多种方式:
    1. 扫二维码获取 qr_code
    2. 手动输入设备编码 code
    3. 手动输入设备序列号 sn
    """
    qr_code = data.qr_code.strip()
    # 扫码报修已收紧认证: 登录用户可达, 审计 user (卡b1b04cda, 取代旧匿名设计 卡69acc93c)
    logger.info("scan_device 扫码识别: qr_code=%s user=%s (需认证)", qr_code, getattr(user, "username", None))
    
    # 1. 尝试通过二维码查找
    qrcode_record = db.query(DeviceQRCode).filter(
        DeviceQRCode.qr_code == qr_code,
        DeviceQRCode.is_active == True
    ).first()
    
    if qrcode_record:
        device = db.query(Device).filter(Device.id == qrcode_record.device_id).first()
        if device:
            # 团队归属校验 (卡8cd026b7): 跨队设备不泄露存在性, 也不累计扫码统计
            _check_device_team(db, device.id, user, msg="未找到设备，请检查二维码或设备编码是否正确")
            # 更新扫码统计
            qrcode_record.scan_count += 1
            qrcode_record.last_scan_time = datetime.now(timezone.utc)
            db.commit()
            
            # 获取站点信息
            station = db.query(Station).filter(Station.id == device.station_id).first()
            
            return success_response({
                "success": True,
                "device_id": device.id,
                "device_sn": device.sn,
                "device_name": device.name,
                "device_type": device.type.value,
                "device_status": device.status.value,
                "station_id": device.station_id,
                "station_name": station.name if station else "未知站点",
                "station_address": station.address if station else "",
                "health_score": device.health_score or 100.0,
                "last_maintenance": str(device.last_maintenance) if device.last_maintenance else None,
                "qr_code": qr_code,
            })
    
    # 2. 尝试通过设备编码查找
    device = db.query(Device).filter(Device.code == qr_code).first()
    if device:
        _check_device_team(db, device.id, user, msg="未找到设备，请检查二维码或设备编码是否正确")  # 卡8cd026b7
        station = db.query(Station).filter(Station.id == device.station_id).first()
        return success_response({
            "success": True,
            "device_id": device.id,
            "device_sn": device.sn,
            "device_name": device.name,
            "device_type": device.type.value,
            "device_status": device.status.value,
            "station_id": device.station_id,
            "station_name": station.name if station else "未知站点",
            "station_address": station.address if station else "",
            "health_score": device.health_score or 100.0,
            "last_maintenance": str(device.last_maintenance) if device.last_maintenance else None,
            "qr_code": qr_code,
        })
    
    # 3. 尝试通过序列号查找
    device = db.query(Device).filter(Device.sn == qr_code).first()
    if device:
        _check_device_team(db, device.id, user, msg="未找到设备，请检查二维码或设备编码是否正确")  # 卡8cd026b7
        station = db.query(Station).filter(Station.id == device.station_id).first()
        return success_response({
            "success": True,
            "device_id": device.id,
            "device_sn": device.sn,
            "device_name": device.name,
            "device_type": device.type.value,
            "device_status": device.status.value,
            "station_id": device.station_id,
            "station_name": station.name if station else "未知站点",
            "station_address": station.address if station else "",
            "health_score": device.health_score or 100.0,
            "last_maintenance": str(device.last_maintenance) if device.last_maintenance else None,
            "qr_code": qr_code,
        })
    
    # 未找到设备
    raise HTTPException(status_code=404, detail="未找到设备，请检查二维码或设备编码是否正确")

# ========== 快速报修 API ==========

@router.post("/quick-repair")
def quick_repair(data: QuickRepairRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键快速报修 (需认证, 卡b1b04cda: 收紧为登录用户)

    流程:
    1. 验证设备存在
    2. 创建报修工单 (创建人=认证用户)
    3. 自动派单（可选）
    4. 返回工单信息
    """
    # 扫码报修已收紧认证: 登录用户可达, 创建人以认证用户追溯 (卡b1b04cda, 取代旧匿名设计 卡69acc93c)
    logger.info(
        "quick_repair 报修请求: device_id=%s level=%s contact=%s user=%s (需认证)",
        data.device_id, data.fault_level, data.contact_phone, getattr(user, "username", None),
    )
    # 验证设备
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    # 团队归属校验 (卡8cd026b7): 不允许为他队设备建单触发派单
    _check_device_team(db, device.id, user)

    station = db.query(Station).filter(Station.id == device.station_id).first()
    
    # 生成工单号
    now = datetime.now(timezone.utc)
    wo_id = f"WO-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
    
    # 创建工单
    workorder = WorkOrder(
        id=wo_id,
        fault_desc=data.fault_desc,
        type=WorkOrderType.REPAIR,
        level=WorkOrderLevel(data.fault_level),
        station_id=device.station_id,
        device_id=device.id,
        status=WorkOrderStatus.PENDING,
        creator_id=user.id,  # 认证用户作为工单创建人 (卡b1b04cda)
        attachments=data.attachments,
    )
    db.add(workorder)
    db.commit()
    db.refresh(workorder)
    
    # 自动派单逻辑
    try:
        from app.services.dispatch_engine import dispatch_engine
        from app.models.user import User, UserRole
        engineers = db.query(User).filter(User.role == UserRole.ENGINEER).all()
        if engineers and station:
            station_loc = {'lat': station.latitude or 31.23, 'lon': station.longitude or 121.47}
            workorder_data = {
                'device_type': device.type.value if device else 'unknown',
                'level': data.fault_level,
                'required_parts': [],
            }
            engineer_list = []
            for eng in engineers:
                engineer_list.append({
                    'id': eng.id,
                    'name': eng.real_name or eng.username,
                    'status': 'active',
                    'location': {'lat': eng.latitude or 31.23, 'lon': eng.longitude or 121.47},
                    'skills': [],
                    'current_load': db.query(WorkOrder).filter(
                        WorkOrder.assignee_id == eng.id,
                        WorkOrder.status.in_(['pending', 'processing'])
                    ).count(),
                })
            result = dispatch_engine.calculate_best_engineer(workorder_data, engineer_list, station_loc)
            if result and result.get('engineer_id'):
                workorder.assignee_id = result['engineer_id']
                workorder.status = WorkOrderStatus.ACCEPTED
                db.commit()
    except Exception as e:
        logger.warning("自动派单失败，工单保持待派状态: %s", e)
    
    return action_response(success=True, message="报修成功！工单号：{wo_id}，请等待工程师处理", data={
        "workorder_id": wo_id,
        "device_name": device.name,
        "station_name": station.name if station else "未知站点",
        "fault_desc": data.fault_desc,
        "status": "pending",
        "create_time": str(now),
    })

# ========== 二维码管理 API ==========
# 归属路径（卡 fd236172）：device_qrcode 无 team_id，经 device→station 两跳确定 team。
# 非 admin 仅可见/操作本 team 设备的二维码；未挂站点设备归属无法判定，归平台 admin。

def _device_team_id(db: Session, device_id: int):
    """返回设备所属 team_id；device/station 不存在或未挂站点 → None。"""
    row = db.execute(
        text(
            "SELECT s.team_id FROM devices d "
            "JOIN stations s ON d.station_id = s.id WHERE d.id = :id"
        ),
        {"id": device_id},
    ).first()
    return row[0] if row else None


def _check_device_team(db: Session, device_id: int, user: User, msg: str = "设备不存在"):
    """二维码管理端点归属校验：admin 豁免；非 admin 仅本 team 设备，否则 404。"""
    if is_platform_admin(user):
        return
    tid = _device_team_id(db, device_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)



@router.post("/qrcode/generate")
def generate_qrcode(data: QRCodeGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """生成设备二维码 (需认证, 卡020e44db: 二维码管理不属扫码报修匿名场景)
    
    流程:
    1. 检查设备是否已有二维码
    2. 生成唯一二维码标识
    3. 生成二维码图片
    4. 存储到数据库
    """
    # 检查设备
    _check_device_team(db, data.device_id, user)  # 卡 fd236172: 团队归属校验
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 检查是否已有二维码
    existing = db.query(DeviceQRCode).filter(DeviceQRCode.device_id == data.device_id).first()
    if existing:
        # 更新状态
        existing.is_active = True
        existing.notes = data.notes
        db.commit()
        return success_response({
            "success": True,
            "qr_code": existing.qr_code,
            "qr_image_url": existing.qr_image_path or "",
            "device_id": device.id,
            "device_name": device.name,
            "message": "设备已有二维码，已重新激活",
        })
    
    # 生成二维码标识
    qr_code = f"TL-{device.code or device.sn}-{uuid.uuid4().hex[:8]}"
    
    # 生成二维码图片
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_code)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 保存图片
    qr_dir = "/tmp/tianlian_qrcodes"
    os.makedirs(qr_dir, exist_ok=True)
    qr_image_path = f"{qr_dir}/{qr_code}.png"
    img.save(qr_image_path)
    
    # 存储到数据库
    qrcode_record = DeviceQRCode(
        device_id=device.id,
        qr_code=qr_code,
        qr_image_path=qr_image_path,
        is_active=True,
        notes=data.notes,
    )
    db.add(qrcode_record)
    db.commit()
    db.refresh(qrcode_record)
    
    return success_response({
        "success": True,
        "qr_code": qr_code,
        "qr_image_url": qr_image_path,
        "device_id": device.id,
        "device_name": device.name,
        "message": "二维码生成成功",
    })

@router.get("/qrcode/{device_id}")
def get_device_qrcode(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取设备二维码 (需认证, 卡020e44db; 卡fd236172: 补团队归属校验)"""
    _check_device_team(db, device_id, user)
    qrcode_record = db.query(DeviceQRCode).filter(
        DeviceQRCode.device_id == device_id,
        DeviceQRCode.is_active == True
    ).first()
    
    if not qrcode_record:
        raise HTTPException(status_code=404, detail="设备未生成二维码")
    
    device = db.query(Device).filter(Device.id == device_id).first()
    
    return success_response({
        "success": True,
        "qr_code": qrcode_record.qr_code,
        "qr_image_url": qrcode_record.qr_image_path,
        "device_id": device.id,
        "device_name": device.name,
        "scan_count": qrcode_record.scan_count,
        "last_scan_time": str(qrcode_record.last_scan_time) if qrcode_record.last_scan_time else None,
    })

@router.get("/qrcodes")
def list_qrcodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取二维码列表 (需认证, 卡020e44db; 卡fd236172: 非admin叠加team过滤)"""
    query = db.query(DeviceQRCode)

    if not is_platform_admin(user):
        # 团队级用户仅见本 team（device.station.team_id）设备的二维码
        query = query.filter(
            DeviceQRCode.device_id.in_(
                db.query(Device.id).join(Station, Device.station_id == Station.id)
                .filter(Station.team_id == user.team_id)
            )
        )

    if device_id:
        query = query.filter(DeviceQRCode.device_id == device_id)
    
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    # 获取设备信息（批量 IN 加载，避免逐条 N+1 查 Device）
    device_ids = {item.device_id for item in items}
    device_map = {
        d.id: d for d in db.query(Device).filter(Device.id.in_(device_ids)).all()
    } if device_ids else {}
    result = []
    for item in items:
        device = device_map.get(item.device_id)
        result.append({
            "id": item.id,
            "qr_code": item.qr_code,
            "device_id": item.device_id,
            "device_name": device.name if device else "未知设备",
            "device_sn": device.sn if device else "",
            "scan_count": item.scan_count,
            "is_active": item.is_active,
            "created_at": str(item.created_at),
        })
    
    return paginated_response(
        items=result,
        total=total,
        page=page,
        page_size=page_size
    )

@router.delete("/qrcode/{device_id}")
def delete_qrcode(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除/禁用设备二维码 (需认证, 卡69acc93c: 二维码管理不属扫码报修匿名场景; 卡fd236172: 补团队归属校验)"""
    _check_device_team(db, device_id, user)
    qrcode_record = db.query(DeviceQRCode).filter(DeviceQRCode.device_id == device_id).first()
    
    if not qrcode_record:
        raise HTTPException(status_code=404, detail="设备二维码不存在")
    
    qrcode_record.is_active = False
    db.commit()
    
    return action_response(success=True, message="二维码已禁用")
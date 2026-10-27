"""
设备通信协议管理 API (admin-platform-spec §2.4)

功能:
- 通信协议 CRUD(OCPP/Modbus/MQTT/HTTP/自定义): 协议定义 + 数据点映射
- 协议解析规则 CRUD(上行 parse_rule / 下行 encode_rule)
- 搜索、分页、详情、按 protocol_id 过滤规则
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Literal, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.device_protocols import DeviceProtocol, ProtocolRule
from app.core.response import success_response, paginated_response, action_response
from app.api.deps import get_current_user, require_platform_admin
from app.middleware.permission import require_write_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["设备协议管理"], dependencies=[Depends(require_write_permission("device:edit"))])
rules_router = APIRouter(tags=["协议解析规则"], dependencies=[Depends(require_write_permission("device:edit"))])


# ========== Schemas ==========

class DeviceProtocolCreate(BaseModel):
    name: str
    code: str
    type: Literal["ocpp", "modbus", "mqtt", "http", "custom"]  # ocpp / modbus / mqtt / http / custom
    version: Optional[str] = None
    protocol_definition: Optional[dict] = None
    data_point_mappings: Optional[list] = None

class DeviceProtocolUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[Literal["ocpp", "modbus", "mqtt", "http", "custom"]] = None
    version: Optional[str] = None
    protocol_definition: Optional[dict] = None
    data_point_mappings: Optional[list] = None
    status: Optional[Literal["active", "inactive"]] = None

class ProtocolRuleCreate(BaseModel):
    protocol_id: int
    direction: Literal["uplink", "downlink"]  # uplink / downlink
    message_type: Optional[str] = None
    parse_rule: Optional[dict] = None
    encode_rule: Optional[dict] = None

class ProtocolRuleUpdate(BaseModel):
    direction: Optional[Literal["uplink", "downlink"]] = None
    message_type: Optional[str] = None
    parse_rule: Optional[dict] = None
    encode_rule: Optional[dict] = None
    status: Optional[Literal["active", "inactive"]] = None


def _protocol_to_dict(item: DeviceProtocol) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "code": item.code,
        "type": item.type,
        "version": item.version,
        "protocol_definition": item.protocol_definition,
        "data_point_mappings": item.data_point_mappings,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _rule_to_dict(rule: ProtocolRule) -> dict:
    return {
        "id": rule.id,
        "protocol_id": rule.protocol_id,
        "direction": rule.direction,
        "message_type": rule.message_type,
        "parse_rule": rule.parse_rule,
        "encode_rule": rule.encode_rule,
        "status": rule.status,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


# ========== 协议 Endpoints ==========

@router.get("", summary="获取通信协议列表")
def list_device_protocols(
    type: Optional[str] = None,
    keyword: Optional[str] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取通信协议列表，支持按类型过滤和分页搜索"""
    try:
        q = db.query(DeviceProtocol)
        if type:
            q = q.filter(DeviceProtocol.type == type)

        search_term = keyword or search
        if search_term:
            like = f"%{search_term}%"
            q = q.filter(
                DeviceProtocol.name.ilike(like) | DeviceProtocol.code.ilike(like)
            )

        total = q.count()
        items = (
            q.order_by(DeviceProtocol.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            items=[_protocol_to_dict(i) for i in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询通信协议列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post("", summary="创建通信协议", dependencies=[Depends(require_platform_admin)])
def create_device_protocol(
    data: DeviceProtocolCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """创建新的通信协议"""
    try:
        item = DeviceProtocol(
            name=data.name,
            code=data.code,
            type=data.type,
            version=data.version,
            protocol_definition=data.protocol_definition,
            data_point_mappings=data.data_point_mappings,
            status="active",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return success_response(_protocol_to_dict(item), message="设备协议创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建通信协议失败 code=%s", data.code)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/{item_id}", summary="获取通信协议详情")
def get_device_protocol(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取通信协议详情（含解析规则）"""
    try:
        item = db.query(DeviceProtocol).filter(DeviceProtocol.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="设备协议不存在")
        data = _protocol_to_dict(item)
        data["rules"] = [_rule_to_dict(r) for r in item.rules]
        return success_response(data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询通信协议详情失败 item_id=%s", item_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put("/{item_id}", summary="更新通信协议", dependencies=[Depends(require_platform_admin)])
def update_device_protocol(
    item_id: int,
    data: DeviceProtocolUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """更新通信协议"""
    try:
        item = db.query(DeviceProtocol).filter(DeviceProtocol.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="设备协议不存在")

        changed = False
        for field in [
            "name", "code", "type", "version",
            "protocol_definition", "data_point_mappings", "status",
        ]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(item, field, val)
                changed = True

        if not changed:
            return action_response(message="无需更新")

        db.commit()
        db.refresh(item)
        return action_response(message="设备协议更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新通信协议失败 item_id=%s", item_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.delete("/{item_id}", summary="删除通信协议", dependencies=[Depends(require_platform_admin)])
def delete_device_protocol(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """删除通信协议（级联删除其解析规则）"""
    try:
        item = db.query(DeviceProtocol).filter(DeviceProtocol.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="设备协议不存在")

        db.delete(item)  # ORM cascade=all, delete-orphan → 规则一并删除
        db.commit()
        return action_response(message="设备协议删除成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除通信协议失败 item_id=%s", item_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ========== 协议解析规则 Endpoints ==========

@rules_router.get("", summary="获取协议解析规则列表")
def list_protocol_rules(
    protocol_id: Optional[int] = None,
    direction: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取协议解析规则列表，支持按 protocol_id / direction 过滤"""
    try:
        q = db.query(ProtocolRule)
        if protocol_id is not None:
            q = q.filter(ProtocolRule.protocol_id == protocol_id)
        if direction:
            q = q.filter(ProtocolRule.direction == direction)

        total = q.count()
        items = (
            q.order_by(ProtocolRule.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            items=[_rule_to_dict(r) for r in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询协议解析规则列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@rules_router.post("", summary="创建协议解析规则", dependencies=[Depends(require_platform_admin)])
def create_protocol_rule(
    data: ProtocolRuleCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """创建协议解析规则（protocol_id 必须存在）"""
    try:
        proto = db.query(DeviceProtocol).filter(
            DeviceProtocol.id == data.protocol_id
        ).first()
        if not proto:
            raise HTTPException(status_code=404, detail="设备协议不存在")

        rule = ProtocolRule(
            protocol_id=data.protocol_id,
            direction=data.direction,
            message_type=data.message_type,
            parse_rule=data.parse_rule,
            encode_rule=data.encode_rule,
            status="active",
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return success_response(_rule_to_dict(rule), message="协议规则创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建协议解析规则失败 protocol_id=%s", data.protocol_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@rules_router.put("/{rule_id}", summary="更新协议解析规则", dependencies=[Depends(require_platform_admin)])
def update_protocol_rule(
    rule_id: int,
    data: ProtocolRuleUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """更新协议解析规则"""
    try:
        rule = db.query(ProtocolRule).filter(ProtocolRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="协议规则不存在")

        changed = False
        for field in ["direction", "message_type", "parse_rule", "encode_rule", "status"]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(rule, field, val)
                changed = True

        if not changed:
            return action_response(message="无需更新")

        db.commit()
        db.refresh(rule)
        return action_response(message="协议规则更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新协议解析规则失败 rule_id=%s", rule_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@rules_router.delete("/{rule_id}", summary="删除协议解析规则", dependencies=[Depends(require_platform_admin)])
def delete_protocol_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """删除协议解析规则"""
    try:
        rule = db.query(ProtocolRule).filter(ProtocolRule.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="协议规则不存在")

        db.delete(rule)
        db.commit()
        return action_response(message="协议规则删除成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除协议解析规则失败 rule_id=%s", rule_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")

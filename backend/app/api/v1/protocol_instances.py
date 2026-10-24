"""
协议实例管理 API - 网关实例、解析器配置、连接状态

功能:
- 网关实例 CRUD（运行态网关实例，含协议配置）
- 解析器配置（关联设备类型 → 协议适配器 → 解析 Schema）
- 连接状态仪表板（实时连接状态监控）
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any, Literal
from datetime import datetime, timezone
import json
from pydantic import BaseModel

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.api.deps import get_current_user, is_platform_admin
from app.middleware.permission import require_write_permission
from app.models.user import User
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["协议实例管理"], dependencies=[Depends(require_write_permission("device:edit"))])


# 协议实例归属路径（任务卡 ed509541）：protocol_instances 表无 team_id 列、
# gateway_id 可空，需经 gateway→station 三跳确定 team。非 admin 仅可见/操作
# 绑定到本 team 网关的实例；gateway_id 为空的实例无法判定归属，归平台 admin。
_INSTANCE_TEAM_FROM = (
    "protocol_instances pi "
    "JOIN gateways g ON pi.gateway_id = g.id "
    "JOIN stations s ON g.station_id = s.id"
)


def _instance_team_id(db: Session, instance_id: int):
    """返回实例所属 team_id；无 gateway / 网关无 station / 不存在 → None。"""
    row = db.execute(
        text(f"SELECT s.team_id FROM {_INSTANCE_TEAM_FROM} WHERE pi.id = :id"),
        {"id": instance_id},
    ).first()
    return row[0] if row else None


def _check_instance_team(db: Session, instance_id: int, user: User, msg: str = "协议实例不存在"):
    """详情/写端点归属校验：admin 豁免；非 admin 仅本 team 实例，否则 404。"""
    if is_platform_admin(user):
        return
    tid = _instance_team_id(db, instance_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _gateway_team_id_sql(db: Session, gateway_id: int):
    """返回网关所属 station 的 team_id；网关/站点缺失 → None。"""
    row = db.execute(
        text("SELECT s.team_id FROM gateways g JOIN stations s ON g.station_id = s.id WHERE g.id = :id"),
        {"id": gateway_id},
    ).first()
    return row[0] if row else None


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符 % 和 _，keyword 搜索按字面匹配（防通配符枚举）。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _iso(v):
    """安全 ISO 格式化: 兼容 datetime 对象和 SQLite 返回的字符串"""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return v.isoformat()


# ========== Schemas ==========

class ProtocolInstanceCreate(BaseModel):
    name: str
    protocol_type: Literal["modbus_rtu", "mqtt", "rest"]  # modbus_rtu, mqtt, rest
    gateway_id: Optional[int] = None
    device_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}  # 协议特定配置
    parser_schema: Optional[str] = None  # 使用的解析Schema
    description: Optional[str] = None

class ProtocolInstanceUpdate(BaseModel):
    name: Optional[str] = None
    protocol_type: Optional[Literal["modbus_rtu", "mqtt", "rest"]] = None
    gateway_id: Optional[int] = None
    device_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    parser_schema: Optional[str] = None
    status: Optional[Literal["running", "stopped", "error"]] = None
    description: Optional[str] = None

class ParserConfigCreate(BaseModel):
    name: str
    device_type: str
    protocol: Literal["modbus_rtu", "mqtt", "rest"]
    parser_schema: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}
    description: Optional[str] = None

class ParserConfigUpdate(BaseModel):
    name: Optional[str] = None
    protocol: Optional[Literal["modbus_rtu", "mqtt", "rest"]] = None
    parser_schema: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: Optional[Literal["active", "inactive"]] = None
    description: Optional[str] = None


# ========== 网关实例管理 ==========

@router.get("/protocol-instances", summary="获取协议实例列表")
def list_protocol_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    protocol_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """获取协议实例列表"""
    try:
        conditions = ["1=1"]
        params = {}

        if protocol_type:
            conditions.append("protocol_type = :protocol_type")
            params["protocol_type"] = protocol_type
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if keyword:
            conditions.append("(name LIKE :keyword ESCAPE '\\' OR protocol_type LIKE :keyword ESCAPE '\\')")
            params["keyword"] = f"%{_escape_like(keyword)}%"
        if not is_platform_admin(user):
            conditions.append(
                "EXISTS (SELECT 1 FROM gateways g JOIN stations s ON g.station_id = s.id "
                "WHERE g.id = protocol_instances.gateway_id AND s.team_id = :team_id)"
            )
            params["team_id"] = user.team_id

        where = " AND ".join(conditions)
        count_result = db.execute(
            text(f"SELECT COUNT(*) FROM protocol_instances WHERE {where}"), params
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = db.execute(
            text(f"SELECT * FROM protocol_instances WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"),
            {**params, "limit": page_size, "offset": offset}
        )

        items = []
        for row in result:
            items.append({
                "id": row.id,
                "name": row.name,
                "protocol_type": row.protocol_type,
                "gateway_id": row.gateway_id,
                "device_type": row.device_type,
                "config": row.config,
                "parser_schema": row.parser_schema,
                "status": row.status,
                "connection_status": row.connection_status,
                "last_connected": _iso(row.last_connected),
                "description": row.description,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            })

        return paginated_response(items=items, total=total, page=page, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_protocol_instances 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/protocol-instances/{instance_id}", summary="获取协议实例详情")
def get_protocol_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """获取协议实例详情"""
    try:
        result = db.execute(
            text("SELECT * FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="协议实例不存在")
        _check_instance_team(db, instance_id, user)

        return success_response({
            "id": row.id,
            "name": row.name,
            "protocol_type": row.protocol_type,
            "gateway_id": row.gateway_id,
            "device_type": row.device_type,
            "config": row.config,
            "parser_schema": row.parser_schema,
            "status": row.status,
            "connection_status": row.connection_status,
            "last_connected": _iso(row.last_connected),
            "description": row.description,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/protocol-instances", summary="创建协议实例")
def create_protocol_instance(
    data: ProtocolInstanceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """创建协议实例"""
    try:
        if not is_platform_admin(user):
            if data.gateway_id is None:
                raise HTTPException(status_code=400, detail="必须绑定本团队网关")
            gtid = _gateway_team_id_sql(db, data.gateway_id)
            if gtid is None or user.team_id is None or gtid != user.team_id:
                raise HTTPException(status_code=404, detail="网关不存在")
        result = db.execute(text(
            """INSERT INTO protocol_instances (name, protocol_type, gateway_id, device_type, config, parser_schema, description)
           VALUES (:name, :protocol_type, :gateway_id, :device_type, :config, :parser_schema, :description)
           RETURNING id""",
        ), {
            "name": data.name,
            "protocol_type": data.protocol_type,
            "gateway_id": data.gateway_id,
            "device_type": data.device_type,
            "config": json.dumps(data.config, ensure_ascii=False),
            "parser_schema": data.parser_schema,
            "description": data.description,
        })
        item_id = result.scalar()
        db.commit()
        return success_response({"id": item_id, "name": data.name}, message="协议实例创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/protocol-instances/{instance_id}", summary="更新协议实例")
def update_protocol_instance(
    instance_id: int,
    data: ProtocolInstanceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """更新协议实例"""
    try:
        check = db.execute(
            text("SELECT id FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        if not check.first():
            raise HTTPException(status_code=404, detail="协议实例不存在")
        _check_instance_team(db, instance_id, user)

        updates = []
        params = {"id": instance_id}
        for field in ["name", "protocol_type", "gateway_id", "device_type", "config", "parser_schema", "status", "description"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = :{field}")
                if field == "config" and isinstance(val, dict):
                    val = json.dumps(val, ensure_ascii=False)
                params[field] = val

        if not updates:
            return action_response(message="无需更新")

        db.execute(
            text(f"UPDATE protocol_instances SET {', '.join(updates)} WHERE id = :id"), params
        )
        db.commit()
        return action_response(message="协议实例更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/protocol-instances/{instance_id}", summary="删除协议实例")
def delete_protocol_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """删除协议实例"""
    try:
        check = db.execute(
            text("SELECT id FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        if not check.first():
            raise HTTPException(status_code=404, detail="协议实例不存在")
        _check_instance_team(db, instance_id, user)

        db.execute(
            text("DELETE FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        db.commit()
        return action_response(message="协议实例已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/protocol-instances/{instance_id}/connect", summary="连接协议实例")
def connect_protocol_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """建立连接（模拟）"""
    try:
        check = db.execute(
            text("SELECT id, name FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        row = check.first()
        if not row:
            raise HTTPException(status_code=404, detail="协议实例不存在")
        _check_instance_team(db, instance_id, user)

        now = datetime.now(timezone.utc)
        db.execute(
            text("UPDATE protocol_instances SET connection_status = 'connected', last_connected = :now, status = 'running' WHERE id = :id"),
            {"id": instance_id, "now": now}
        )
        db.commit()
        return action_response(message=f"协议实例 {row.name} 已连接")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("connect_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/protocol-instances/{instance_id}/disconnect", summary="断开协议实例")
def disconnect_protocol_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """断开连接（模拟）"""
    try:
        check = db.execute(
            text("SELECT id, name FROM protocol_instances WHERE id = :id"), {"id": instance_id}
        )
        row = check.first()
        if not row:
            raise HTTPException(status_code=404, detail="协议实例不存在")
        _check_instance_team(db, instance_id, user)

        db.execute(
            text("UPDATE protocol_instances SET connection_status = 'disconnected', status = 'stopped' WHERE id = :id"),
            {"id": instance_id}
        )
        db.commit()
        return action_response(message=f"协议实例 {row.name} 已断开")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("disconnect_protocol_instance 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ========== 解析器配置管理 ==========

@router.get("/parser-configs", summary="获取解析器配置列表")
def list_parser_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    protocol: Optional[str] = None,
    device_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """获取解析器配置列表"""
    try:
        conditions = ["1=1"]
        params = {}

        if protocol:
            conditions.append("protocol = :protocol")
            params["protocol"] = protocol
        if device_type:
            conditions.append("device_type = :device_type")
            params["device_type"] = device_type
        if keyword:
            conditions.append("(name LIKE :keyword ESCAPE '\\' OR device_type LIKE :keyword ESCAPE '\\')")
            params["keyword"] = f"%{_escape_like(keyword)}%"

        where = " AND ".join(conditions)
        count_result = db.execute(
            text(f"SELECT COUNT(*) FROM parser_configs WHERE {where}"), params
        )
        total = count_result.scalar()

        offset = (page - 1) * page_size
        result = db.execute(
            text(f"SELECT * FROM parser_configs WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"),
            {**params, "limit": page_size, "offset": offset}
        )

        items = []
        for row in result:
            items.append({
                "id": row.id,
                "name": row.name,
                "device_type": row.device_type,
                "protocol": row.protocol,
                "parser_schema": row.parser_schema,
                "config": row.config,
                "status": row.status,
                "description": row.description,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            })

        return paginated_response(items=items, total=total, page=page, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_parser_configs 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/parser-configs", summary="创建解析器配置")
def create_parser_config(
    data: ParserConfigCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """创建解析器配置（parser_configs 为平台级共享模板，仅平台管理员可写）"""
    try:
        if not is_platform_admin(user):
            raise HTTPException(status_code=403, detail="仅平台管理员可管理解析器配置")
        params = data.dict()
        if isinstance(params.get("config"), dict):
            params["config"] = json.dumps(params["config"], ensure_ascii=False)
        result = db.execute(text(
            """INSERT INTO parser_configs (name, device_type, protocol, parser_schema, config, description)
           VALUES (:name, :device_type, :protocol, :parser_schema, :config, :description)
           RETURNING id""",
        ), params)
        item_id = result.scalar()
        db.commit()
        return success_response({"id": item_id, "name": data.name}, message="解析器配置创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_parser_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/parser-configs/{config_id}", summary="更新解析器配置")
def update_parser_config(
    config_id: int,
    data: ParserConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """更新解析器配置（parser_configs 为平台级共享模板，仅平台管理员可写）"""
    try:
        if not is_platform_admin(user):
            raise HTTPException(status_code=403, detail="仅平台管理员可管理解析器配置")
        check = db.execute(
            text("SELECT id FROM parser_configs WHERE id = :id"), {"id": config_id}
        )
        if not check.first():
            raise HTTPException(status_code=404, detail="解析器配置不存在")

        updates = []
        params = {"id": config_id}
        for field in ["name", "protocol", "parser_schema", "config", "status", "description"]:
            val = getattr(data, field, None)
            if val is not None:
                updates.append(f"{field} = :{field}")
                if field == "config" and isinstance(val, dict):
                    val = json.dumps(val, ensure_ascii=False)
                params[field] = val

        if not updates:
            return action_response(message="无需更新")

        db.execute(
            text(f"UPDATE parser_configs SET {', '.join(updates)} WHERE id = :id"), params
        )
        db.commit()
        return action_response(message="解析器配置更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_parser_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/parser-configs/{config_id}", summary="删除解析器配置")
def delete_parser_config(
    config_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """删除解析器配置（parser_configs 为平台级共享模板，仅平台管理员可写）"""
    try:
        if not is_platform_admin(user):
            raise HTTPException(status_code=403, detail="仅平台管理员可管理解析器配置")
        check = db.execute(
            text("SELECT id FROM parser_configs WHERE id = :id"), {"id": config_id}
        )
        if not check.first():
            raise HTTPException(status_code=404, detail="解析器配置不存在")

        db.execute(text("DELETE FROM parser_configs WHERE id = :id"), {"id": config_id})
        db.commit()
        return action_response(message="解析器配置已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_parser_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ========== 连接状态仪表板 ==========

@router.get("/connection-dashboard", summary="获取连接状态仪表板数据")
def get_connection_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """获取连接状态仪表板数据"""
    # team 过滤（任务卡 ed509541）：非 admin 仅统计本 team 实例
    try:
        if is_platform_admin(user):
            team_clause = ""
            team_params = {}
        else:
            team_clause = (
                "AND EXISTS (SELECT 1 FROM gateways g JOIN stations s ON g.station_id = s.id "
                "WHERE g.id = protocol_instances.gateway_id AND s.team_id = :team_id)"
            )
            team_params = {"team_id": user.team_id}

        # 汇总统计
        stats = {}
    
        total_result = db.execute(
            text(f"SELECT COUNT(*) FROM protocol_instances WHERE 1=1 {team_clause}"), team_params
        )
        stats["total"] = total_result.scalar()

        for status in ["running", "stopped", "error"]:
            r = db.execute(
                text(f"SELECT COUNT(*) FROM protocol_instances WHERE status = :status {team_clause}"),
                {**team_params, "status": status}
            )
            stats[status] = r.scalar()

        for conn_status in ["connected", "disconnected", "connecting"]:
            r = db.execute(
                text(f"SELECT COUNT(*) FROM protocol_instances WHERE connection_status = :cs {team_clause}"),
                {**team_params, "cs": conn_status}
            )
            stats[conn_status] = r.scalar()

        # 按协议类型统计
        type_stats = db.execute(
            text(f"SELECT protocol_type, COUNT(*) as cnt FROM protocol_instances WHERE 1=1 {team_clause} GROUP BY protocol_type"),
            team_params
        ).all()
        stats["by_protocol"] = {row.protocol_type: row.cnt for row in type_stats}

        # 最近连接记录
        recent = db.execute(
            text(f"SELECT id, name, protocol_type, connection_status, last_connected FROM protocol_instances WHERE last_connected IS NOT NULL {team_clause} ORDER BY last_connected DESC LIMIT 10"),
            team_params
        ).all()

        recent_connections = []
        for row in recent:
            recent_connections.append({
                "id": row.id,
                "name": row.name,
                "protocol_type": row.protocol_type,
                "connection_status": row.connection_status,
                "last_connected": _iso(row.last_connected),
            })

        # 可用解析器数量
        parser_count = db.execute(text("SELECT COUNT(*) FROM parser_configs WHERE status = 'active'")).scalar()

        # 已注册协议适配器数量
        protocol_count = db.execute(
            text(f"SELECT COUNT(DISTINCT protocol_type) FROM protocol_instances WHERE 1=1 {team_clause}"),
            team_params
        ).scalar()

        return success_response({
            "stats": stats,
            "recent_connections": recent_connections,
            "parser_count": parser_count,
            "protocol_count": protocol_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_connection_dashboard 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

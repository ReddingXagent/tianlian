"""
WebSocket 消息格式标准化
统一消息结构
"""
from datetime import datetime, timezone
from typing import Optional, Any, Dict, Literal
from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """统一WebSocket消息格式"""
    
    type: Literal[
        "connected",
        "disconnected",
        "data",
        "error",
        "heartbeat",
        "subscribe",
        "unsubscribe",
        "subscribed",
        "unsubscribed",
        "initial_data",
        "update",
        "notification"
    ] = Field(..., description="消息类型")
    
    channel: Literal[
        "realtime",
        "digital_twin",
        "dashboard",
        "alerts",
        "workorders",
        "devices",
        "station",
        "device",
        "fleet_queue",
        "fleet_v2g",
        "large_screen"
    ] = Field(..., description="频道名称")
    
    payload: Optional[Dict[str, Any]] = Field(default=None, description="消息数据")
    
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="时间戳(ISO8601)"
    )
    
    id: Optional[str] = Field(default=None, description="消息唯一ID(可选)")
    
    # 扩展字段(用于特定场景)
    station_id: Optional[int] = Field(default=None, description="站点ID(数字孪生)")
    device_id: Optional[int] = Field(default=None, description="设备ID(数字孪生)")
    message: Optional[str] = Field(default=None, description="文本消息(连接/错误等)")


class SubscribeMessage(BaseModel):
    """订阅消息"""
    type: Literal["subscribe"] = "subscribe"
    channel: str
    target_id: Optional[int] = None  # 站点ID或设备ID


class HeartbeatMessage(BaseModel):
    """心跳消息"""
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ErrorWebSocketMessage(BaseModel):
    """错误消息"""
    type: Literal["error"] = "error"
    channel: str
    error_code: str
    error_message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# 消息工厂函数
def create_connected_message(channel: str, message: str = "WebSocket连接成功", **extra) -> WebSocketMessage:
    """创建连接成功消息"""
    return WebSocketMessage(
        type="connected",
        channel=channel,
        message=message,
        payload={"status": "connected"},
        **extra
    )


def create_data_message(channel: str, payload: Dict[str, Any], **extra) -> WebSocketMessage:
    """创建数据消息"""
    return WebSocketMessage(
        type="data",
        channel=channel,
        payload=payload,
        **extra
    )


def create_error_message(channel: str, error_code: str, error_message: str) -> WebSocketMessage:
    """创建错误消息"""
    return WebSocketMessage(
        type="error",
        channel=channel,
        payload={
            "error_code": error_code,
            "error_message": error_message
        },
        message=error_message
    )


def create_heartbeat_message() -> WebSocketMessage:
    """创建心跳消息"""
    return WebSocketMessage(
        type="heartbeat",
        channel="realtime",
        payload={"ping": "pong"}
    )
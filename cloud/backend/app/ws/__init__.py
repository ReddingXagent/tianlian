"""
WebSocket 统一模块
标准化路由前缀: /ws/v1/
统一消息格式和连接管理
"""
from app.ws.manager import WebSocketManager
from app.ws.schemas import WebSocketMessage

# 导出统一管理器实例
ws_manager = WebSocketManager()

__all__ = ["ws_manager", "WebSocketMessage"]
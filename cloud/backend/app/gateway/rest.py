"""
REST API 协议适配器 - 对接第三方平台

支持标准的 RESTful API 接入，用于集成第三方能源管理系统、云平台等。
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from .base import ProtocolAdapter

logger = logging.getLogger(__name__)


class RESTAdapter(ProtocolAdapter):
    """
    REST API 协议适配器
    
    适用场景：第三方平台对接（如云平台、能源管理系统）
    
    特点：
        - 标准 HTTP/HTTPS 协议
        - 支持 GET/POST/PUT/DELETE
        - 支持认证（Token、Basic Auth、OAuth2）
        - 支持数据格式转换（JSON/XML）
    """
    
    protocol_type = "rest"
    
    def __init__(
        self,
        base_url: str = "https://api.example.com",
        api_key: Optional[str] = None,
        auth_type: str = "token",
        timeout_seconds: int = 30,
        retry_count: int = 3
    ):
        """
        初始化 REST 适配器
        
        Args:
            base_url: API 基础 URL
            api_key: API 密钥（可选）
            auth_type: 认证类型（token/basic/oauth2）
            timeout_seconds: 超时时间（秒）
            retry_count: 重试次数
        """
        self.base_url = base_url
        self.api_key = api_key
        self.auth_type = auth_type
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.connected = False
        
    async def connect(self) -> bool:
        """
        建立 API 连接（验证认证）
        
        Returns:
            bool: 连接是否成功
        """
        logger.info("连接 REST API: %s", self.base_url)
        # 实际实现需要使用 httpx 或 aiohttp
        self.connected = True
        return True
    
    async def disconnect(self) -> bool:
        """断开连接（清理认证状态）"""
        self.connected = False
        return True
    
    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """
        读取设备数据
        
        Args:
            device_address: 设备ID或API路径标识
            
        Returns:
            Dict[str, Any]: 遥测数据
        """
        if not self.connected:
            await self.connect()
        
        # 模拟 REST API 数据获取
        telemetry = {
            "device_id": device_address,
            "power": 100.0,
            "voltage": 380.0,
            "current": 26.3,
            "status": "running",
            "timestamp": datetime.now(timezone.utc),
        }
        return telemetry
    
    async def write_command(self, device_address: int, command: Dict) -> bool:
        """
        写入控制指令
        
        Args:
            device_address: 设备ID
            command: 控制指令字典
            
        Returns:
            bool: 指令是否成功下发
        """
        if not self.connected:
            await self.connect()
        
        logger.info("发送 REST 控制: 设备%s, 命令: %s", device_address, command)
        return True
    
    async def fetch_endpoint(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        获取 API 端点数据
        
        Args:
            endpoint: API 端点路径（如 "/devices/1/data"）
            params: 查询参数
            
        Returns:
            Dict[str, Any]: API 返回数据
        """
        # 实际实现需要使用 httpx 或 aiohttp
        logger.debug("获取端点: %s, 参数: %s", endpoint, params)
        return {"data": {}, "status": "ok"}
    
    async def post_endpoint(self, endpoint: str, data: Dict) -> Dict[str, Any]:
        """
        向 API 端点发送数据
        
        Args:
            endpoint: API 端点路径
            data: 发送数据
            
        Returns:
            Dict[str, Any]: API 返回结果
        """
        logger.debug("发送端点: %s, 数据: %s", endpoint, data)
        return {"status": "success"}
    
    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """解析故障码（REST API 通常直接返回故障码）"""
        return None
    
    def _build_headers(self) -> Dict[str, str]:
        """
        构建 HTTP 请求头
        
        Returns:
            Dict[str, str]: 请求头字典
        """
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.auth_type == "token" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_type == "basic" and self.api_key:
            headers["Authorization"] = f"Basic {self.api_key}"
        
        return headers
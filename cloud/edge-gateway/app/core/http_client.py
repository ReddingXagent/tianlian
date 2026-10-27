"""
天链 V3 边缘网关 - HTTP 客户端（对接云端 API）
"""
import httpx
from typing import Optional, Dict, Any
from app.core.config import config
from app.core.logging import logger


class CloudAPIClient:
    """云端 API 客户端"""

    def __init__(self):
        self.base_url = config.cloud.api_base.rstrip("/")
        self.api_key = config.cloud.api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def post(self, path: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST 请求"""
        try:
            client = await self._get_client()
            resp = await client.post(path, json=data)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"云端 API 请求失败 [{path}]: {e}")
            return None
        except Exception as e:
            logger.error(f"云端 API 请求异常 [{path}]: {e}")
            return None

    async def get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """GET 请求"""
        try:
            client = await self._get_client()
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"云端 API 请求失败 [{path}]: {e}")
            return None
        except Exception as e:
            logger.error(f"云端 API 请求异常 [{path}]: {e}")
            return None

    async def check_connectivity(self) -> bool:
        """检查云端连通性"""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# 全局客户端实例
cloud_client = CloudAPIClient()

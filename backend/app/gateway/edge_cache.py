"""
边缘缓存机制 - 本地遥测数据缓存，支持 TTL 过期和 LRU 淘汰

功能：
    - 按设备地址缓存最近遥测数据
    - TTL 过期自动失效
    - LRU 淘汰策略（最大条目数限制）
    - 批量写入（write_batch）
    - 缓存命中率统计
    - 异步安全（asyncio.Lock）

使用场景：
    - 网关断连时返回最后已知数据
    - 减少高频轮询的重复读取
    - 边缘计算本地数据源

Author: TianLian V3 Team
"""
from typing import Dict, Any, Optional, List, Tuple
from collections import OrderedDict
import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)


class EdgeCache:
    """
    边缘遥测数据缓存

    特性：
        - TTL 过期：超过 ttl_seconds 的数据自动失效
        - LRU 淘汰：超过 max_entries 时淘汰最久未访问条目
        - 批量操作：write_batch / read_batch
        - 统计信息：命中率、条目数、淘汰数

    Usage:
        >>> cache = EdgeCache(ttl_seconds=30, max_entries=1000)
        >>> cache.put("device:1", {"voltage": 220.5, "current": 10.0})
        >>> data = cache.get("device:1")  # {"voltage": 220.5, ...}
        >>> cache.get("device:999")  # None (未命中)
    """

    def __init__(
        self,
        ttl_seconds: float = 30.0,
        max_entries: int = 1000,
        name: str = "default",
    ):
        """
        初始化边缘缓存

        Args:
            ttl_seconds: 缓存条目存活时间（秒），0 表示永不过期
            max_entries: 最大缓存条目数（LRU 淘汰阈值）
            name: 缓存实例名称（用于日志和统计）
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.name = name

        # 核心存储：OrderedDict 实现 LRU
        self._store: OrderedDict[str, Tuple[float, Dict[str, Any]]] = OrderedDict()

        # 异步锁: 延迟创建, 见 _lock 属性(Python<3.10 在无运行 loop 的线程
        # 中构造 asyncio.Lock() 会抛 RuntimeError, 故不在 __init__ 直接 new)
        self._lock_instance: Optional[asyncio.Lock] = None

        # 统计信息
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0
        self._writes: int = 0
        self._expirations: int = 0

    @property
    def _lock(self) -> asyncio.Lock:
        """
        延迟创建 asyncio.Lock。

        Python<3.10 下 ``asyncio.Lock()`` 在构造时即调用 ``get_event_loop()``
        绑定事件循环; 若在 ``__init__`` 中直接构造, 当实例由无运行 loop 的线程
        (例如经 ``get_edge_cache()`` 工厂在并发 worker 线程中首次创建) 触发时,
        会抛 ``RuntimeError: There is no current event loop in thread``。

        延迟到首次 ``async with self._lock`` 才构造 —— 该访问必然发生在协程内
        (有运行 loop), 既兼容 3.9 测试环境, 又绑定到实际运行的 loop。
        3.10+ 的 ``asyncio.Lock`` 本就是 lazy, 行为一致。
        """
        if self._lock_instance is None:
            self._lock_instance = asyncio.Lock()
        return self._lock_instance

    # ── 公共 API ─────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存条目

        Args:
            key: 缓存键（如 "device:1"、"gateway:SN001"）

        Returns:
            Optional[Dict[str, Any]]: 缓存数据，过期或不存在返回 None
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            timestamp, data = entry

            # TTL 检查
            if self.ttl_seconds > 0 and self._is_expired(timestamp):
                del self._store[key]
                self._expirations += 1
                self._misses += 1
                return None

            # LRU: 移到末尾（最近访问）
            self._store.move_to_end(key)
            self._hits += 1
            return data.copy()  # 返回副本防止外部修改

    async def put(self, key: str, data: Dict[str, Any]) -> None:
        """
        写入缓存条目

        Args:
            key: 缓存键
            data: 要缓存的数据字典
        """
        async with self._lock:
            # 检查容量限制
            if key not in self._store and len(self._store) >= self.max_entries:
                self._evict_one()

            self._store[key] = (time.monotonic(), data.copy())
            self._store.move_to_end(key)
            self._writes += 1

    async def delete(self, key: str) -> bool:
        """
        删除缓存条目

        Args:
            key: 缓存键

        Returns:
            bool: 是否成功删除
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """
        检查缓存条目是否存在且未过期

        Args:
            key: 缓存键

        Returns:
            bool: 是否存在
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            timestamp, _ = entry
            if self.ttl_seconds > 0 and self._is_expired(timestamp):
                del self._store[key]
                self._expirations += 1
                return False
            return True

    async def get_or_fetch(
        self,
        key: str,
        fetcher,
        *args,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存，未命中时调用 fetcher 获取并缓存

        Args:
            key: 缓存键
            fetcher: 异步获取函数，签名为 async def fetcher(*args, **kwargs) -> Dict
            *args: 传递给 fetcher 的位置参数
            **kwargs: 传递给 fetcher 的关键字参数

        Returns:
            Optional[Dict[str, Any]]: 数据
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        try:
            data = await fetcher(*args, **kwargs)
            if data:
                await self.put(key, data)
            return data
        except Exception as e:
            logger.error("EdgeCache[%s] fetch failed for key=%s: %s", self.name, key, e)
            return None

    # ── 批量操作 ─────────────────────────────────────────────

    async def read_batch(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        批量读取缓存

        Args:
            keys: 缓存键列表

        Returns:
            Dict[str, Optional[Dict]]: 键 -> 数据（或 None）
        """
        results = {}
        for key in keys:
            results[key] = await self.get(key)
        return results

    async def write_batch(self, entries: Dict[str, Dict[str, Any]]) -> None:
        """
        批量写入缓存

        Args:
            entries: 键 -> 数据字典
        """
        async with self._lock:
            for key, data in entries.items():
                if key not in self._store and len(self._store) >= self.max_entries:
                    self._evict_one()
                self._store[key] = (time.monotonic(), data.copy())
                self._store.move_to_end(key)
                self._writes += 1

    # ── 维护操作 ─────────────────────────────────────────────

    async def clear(self) -> int:
        """
        清空缓存

        Returns:
            int: 清除的条目数
        """
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    async def expire_stale(self) -> int:
        """
        主动清理过期条目

        Returns:
            int: 清理的条目数
        """
        if self.ttl_seconds <= 0:
            return 0

        async with self._lock:
            now = time.monotonic()
            expired_keys = [
                key for key, (ts, _) in self._store.items()
                if self._is_expired(ts, now=now)
            ]
            for key in expired_keys:
                del self._store[key]
            self._expirations += len(expired_keys)
            return len(expired_keys)

    # ── 统计信息 ─────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict: 统计信息字典
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "name": self.name,
            "size": len(self._store),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 2),
            "writes": self._writes,
            "evictions": self._evictions,
            "expirations": self._expirations,
        }

    def size(self) -> int:
        """获取当前缓存条目数"""
        return len(self._store)

    def keys(self) -> List[str]:
        """获取所有缓存键（快照）"""
        return list(self._store.keys())

    # ── 内部方法 ─────────────────────────────────────────────

    def _is_expired(self, timestamp: float, now: Optional[float] = None) -> bool:
        """检查时间戳是否过期"""
        if now is None:
            now = time.monotonic()
        return (now - timestamp) > self.ttl_seconds

    def _evict_one(self) -> None:
        """淘汰最久未访问的条目（LRU）"""
        if self._store:
            key, _ = self._store.popitem(last=False)
            self._evictions += 1
            logger.debug("EdgeCache[%s] evicted: %s", self.name, key)


# ── 全局缓存实例工厂 ─────────────────────────────────────────

_cache_instances: Dict[str, EdgeCache] = {}
# 工厂层锁: 保护 _cache_instances 的 check-then-act, 防止并发构造重复实例 (TOCTOU)。
# (EdgeCache 自身的 asyncio.Lock 只保证协程内并发安全, 无法跨线程串行化工厂调用。)
_cache_lock = threading.Lock()


def get_edge_cache(
    name: str = "default",
    ttl_seconds: float = 30.0,
    max_entries: int = 1000,
) -> EdgeCache:
    """
    获取或创建命名边缘缓存实例

    Args:
        name: 缓存名称
        ttl_seconds: TTL（秒）
        max_entries: 最大条目数

    Returns:
        EdgeCache: 缓存实例
    """
    # 双重检查锁: 先无锁快查 (命中即直接返回, 避免热路径抢锁);
    # 未命中再持锁, 持锁后复查以防另一线程刚刚构造完毕。
    if name not in _cache_instances:
        with _cache_lock:
            if name not in _cache_instances:
                _cache_instances[name] = EdgeCache(
                    ttl_seconds=ttl_seconds,
                    max_entries=max_entries,
                    name=name,
                )
    return _cache_instances[name]


def reset_edge_caches() -> None:
    """重置所有缓存实例（用于测试）"""
    with _cache_lock:
        _cache_instances.clear()

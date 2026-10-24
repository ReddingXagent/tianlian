"""
缓存服务 - Redis + 内存二级缓存

架构:
1. 优先 Redis (分布式)
2. Redis 不可用时降级到进程内 TTL 缓存
3. 所有 key 自动加 tianlian: 前缀
4. 缓存失败不影响正常功能

Phase34:
- 添加内存 TTL 缓存层 (functools.lru_cache + 手动 TTL)
- 添加 @cached_page / @cached 装饰器
- 支持 TTL 30-60s 热数据
"""
import redis
import json
import os
import time
import hashlib
import logging
import threading
from typing import Optional, Any, Callable, Dict, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

PREFIX = "tianlian:"

# ─── 内存 TTL 缓存 ───
# _MEMORY_CACHE 是模块级共享 dict, FastAPI 同步端点在 threadpool 中并发执行会同时读写它,
# 故所有读写/迭代/删除必须纳入 _MEMORY_CACHE_LOCK 临界区。用 RLock 而非 Lock:
# _memory_set 在锁内会调 _evict_stale, 后者也需进同一把锁 → 必须可重入, 否则自死锁。
# 临界区内只做纯 dict 操作, 慢 IO (Redis) 一律留在锁外 (见 cached 装饰器 / CacheService.get/set,
# 它们调用本层 _memory_* —— 锁粒度在 _memory_* 内部, Redis 调用在它们之外)。
_MEMORY_CACHE: Dict[str, Tuple[float, Any]] = {}  # key -> (expiry_ts, value)
_MEMORY_CACHE_LOCK = threading.RLock()
_MEMORY_CACHE_ENABLED = True


def _memory_get(key: str) -> Optional[Any]:
    """内存缓存读取 (自动过期)。线程安全: 读 + 过期删除纳入临界区;
    过期删除用 pop(key, None) —— 多线程同时命中过期条目时不再抛 KeyError。"""
    if not _MEMORY_CACHE_ENABLED:
        return None
    with _MEMORY_CACHE_LOCK:
        entry = _MEMORY_CACHE.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if expiry < time.time():
            _MEMORY_CACHE.pop(key, None)
            return None
        return value


def _memory_set(key: str, value: Any, ttl: int) -> None:
    """内存缓存写入。线程安全: 写入 + 定期清理纳入临界区。"""
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE[key] = (time.time() + ttl, value)
        # 定期清理过期条目 (每 100 次写入)。临界区内调 _evict_stale, 靠 RLock 可重入不死锁。
        if len(_MEMORY_CACHE) > 1000:
            _evict_stale()


def _memory_delete(key: str) -> None:
    """内存缓存删除。线程安全。"""
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE.pop(key, None)


def _memory_delete_pattern(pattern: str) -> int:
    """删除匹配模式的内存缓存 (简单前缀匹配)。线程安全: 先 snapshot key 再删,
    迭代期间并发修改不再抛 'dictionary changed size during iteration'。"""
    prefix = f"{PREFIX}{pattern}".rstrip("*")
    with _MEMORY_CACHE_LOCK:
        keys = [k for k in _MEMORY_CACHE if k.startswith(prefix)]
        for k in keys:
            _MEMORY_CACHE.pop(k, None)
        return len(keys)


def _evict_stale() -> None:
    """清理过期条目。线程安全: 先 snapshot 再删。
    预期在 _MEMORY_CACHE_LOCK 内调用 (RLock 可重入, _memory_set 锁内调用本函数)。"""
    now = time.time()
    with _MEMORY_CACHE_LOCK:
        # 先 list() snapshot, 避免迭代 items() 期间并发修改抛 'dictionary changed size'
        stale = [k for k, (exp, _) in _MEMORY_CACHE.items() if exp < now]
        for k in stale:
            _MEMORY_CACHE.pop(k, None)


def clear_memory_cache() -> None:
    """清空内存缓存 (调试用)。线程安全。"""
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE.clear()


# ─── 缓存装饰器 ───

def cached(ttl: int = 30):
    """
    函数级缓存装饰器 (内存 + Redis 双级)
    自动根据函数名和参数生成 cache key

    用法:
        @cached(ttl=30)
        def list_devices(page: int, page_size: int, ...):
            ...

    TTL 建议:
        - 设备/站点列表: 30s
        - dashboard/统计: 60s
        - 写操作自动清除缓存
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成唯一 cache key
            sig = hashlib.md5(
                json.dumps((func.__name__, args, kwargs), sort_keys=True, default=str).encode()
            ).hexdigest()
            cache_key = f"func:{func.__module__}.{func.__name__}:{sig}"

            # 先查内存
            mem_val = _memory_get(cache_key)
            if mem_val is not None:
                return mem_val

            # 再查 Redis
            if CacheService._instance and CacheService._instance.enabled:
                try:
                    redis_val = CacheService._instance.get_json(cache_key)
                    if redis_val is not None:
                        # 回填内存缓存
                        _memory_set(cache_key, redis_val, ttl)
                        return redis_val
                except Exception:
                    pass

            # 执行原函数
            result = func(*args, **kwargs)

            # 写入缓存
            try:
                # 写入内存
                _memory_set(cache_key, result, ttl)
                # 写入 Redis
                if CacheService._instance and CacheService._instance.enabled:
                    CacheService._instance.set_json(cache_key, result, expire=ttl)
            except Exception as e:
                logger.debug("缓存写入失败 (不影响功能): %s", e)

            return result
        return wrapper
    return decorator


class CacheService:
    _instance: Optional['CacheService'] = None

    def __init__(self):
        CacheService._instance = self
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            # socket_connect_timeout/socket_timeout 必须显式设置 (redis-py 默认 None=无超时):
            # 本 CacheService 在模块级 `cache = CacheService()` 即构造, 无超时下 ping()
            # 遇网络黑洞(TCP 建连成功但 Redis 无响应)永久 hang → 全应用启动卡死;
            # 运行期 get/set/delete 无超时则永不抛 → except 降级路径形同虚设, Redis 停顿
            # 时所有命中缓存的请求全链路无限 hang。3s 与 health.check_redis / MQTT 健康检查口径一致。
            self.client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self.client.ping()
            self.enabled = True
            logger.info("Redis 缓存已启用: %s", url.split("@")[-1] if "@" in url else url)
        except Exception as e:
            logger.warning("Redis 连接失败，降级为内存缓存: %s", e)
            self.client = None
            self.enabled = False

    def _key(self, key: str) -> str:
        return f"{PREFIX}{key}"

    def get(self, key: str) -> Optional[str]:
        # 先查内存
        mem_val = _memory_get(key)
        if mem_val is not None:
            return mem_val if isinstance(mem_val, str) else json.dumps(mem_val, ensure_ascii=False, default=str)

        if not self.enabled:
            return None
        try:
            val = self.client.get(self._key(key))
            if val is not None:
                # 回填内存缓存 (默认 TTL 30s)
                _memory_set(key, val, 30)
            return val
        except Exception as e:
            logger.warning("Cache get error: %s", e)
            return None

    def set(self, key: str, value: str, expire: int = 30) -> bool:
        # 写入内存
        _memory_set(key, value, expire)
        if not self.enabled:
            return False
        try:
            return self.client.setex(self._key(key), expire, value)
        except Exception as e:
            logger.warning("Cache set error: %s", e)
            return False

    def get_json(self, key: str) -> Optional[Any]:
        val = self.get(key)
        if val:
            try:
                return json.loads(val) if isinstance(val, str) else val
            except Exception:
                return None
        return None

    def set_json(self, key: str, value: Any, expire: int = 30) -> bool:
        return self.set(key, json.dumps(value, ensure_ascii=False, default=str), expire)

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            _memory_delete(k)
        if not self.enabled:
            return count
        try:
            full_keys = [self._key(k) for k in keys]
            return self.client.delete(*full_keys)
        except Exception as e:
            logger.warning("Cache delete error: %s", e)
            return count

    def delete_pattern(self, pattern: str) -> int:
        removed = _memory_delete_pattern(pattern)
        if not self.enabled:
            return removed
        try:
            full_pattern = self._key(pattern)
            # 卡片 b9b1c588: KEYS 是 O(N) 阻塞全库扫描, 单线程 Redis 上会卡住所有
            # 请求; scan_iter 增量游标分批扫描, 语义相同 (返回匹配 key 列表)。
            keys = list(self.client.scan_iter(full_pattern))
            if keys:
                return self.client.delete(*keys) + removed
            return removed
        except Exception as e:
            logger.warning("Cache delete_pattern error: %s", e)
            return removed


cache = CacheService()
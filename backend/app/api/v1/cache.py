"""
缓存统计 API
"""
from fastapi import APIRouter, Depends
from app.core.response import success_response
from app.api.deps import require_platform_admin
from app.api.v1.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/stats")
async def get_cache_stats(user=Depends(require_platform_admin)):
    """获取缓存统计

    卡 c3763bf5: CacheService 的 Redis 属性名是 ``client`` (无 ``redis`` 属性),
    旧 hasattr(cache,'redis') 恒 False → Redis 统计路径永不执行, 降级路径返回
    伪造 mock 值 (87.5/128/2.4)。现改为: enabled+client 走真实 client.info();
    降级诚实化 —— backend='memory', hit_rate=None (无命中数据不伪造),
    total_keys 取进程内 _MEMORY_CACHE 条数 (锁内快照), used_memory_mb 取进程 RSS。
    """
    from app.core import cache as cache_module

    try:
        if cache_module.cache.enabled and cache_module.cache.client:
            info = cache_module.cache.client.info()
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            stats = {
                "hit_rate": float(hits / total * 100) if total > 0 else None,
                "total_keys": sum(db.get("keys", 0) for db in info.get("keyspace", {}).values()),
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "backend": "redis",
            }
            return success_response(stats)
    except Exception:
        pass

    # 降级: 进程内内存缓存, 诚实无 Redis 命中统计
    used_memory_mb = None
    try:
        import resource
        used_memory_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 2)
    except Exception:
        pass
    with cache_module._MEMORY_CACHE_LOCK:
        total_keys = len(cache_module._MEMORY_CACHE)
    stats = {
        "hit_rate": None,
        "total_keys": total_keys,
        "used_memory_mb": used_memory_mb,
        "backend": "memory",
    }
    return success_response(stats)
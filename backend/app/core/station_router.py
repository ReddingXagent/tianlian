"""
全局场站路由模块 - StationRouter

功能:
1. 根据 station_id 或 device_id 查询归属的 Pod
2. 路由表存储在 Redis（生产）或本地字典（单Pod模式）
3. 支持管理员手动注册/修改路由

架构:
- 单Pod模式: local_only=True, 所有路由指向本地
- 多Pod模式: 通过 Redis 存储路由表

Phase 2: 矩阵路由层

卡片 b9b1c588 (TTL+心跳): 四类 Redis 键 (station:route / pod:{id}:stations /
region:{id}:stations / pod:registry) 写入时统一带 ROUTE_TTL 过期, 防止 Pod 崩溃后
路由表残留脏数据。本模块不启动常驻后台线程续租 (避免测试不确定性) —— 存活的
Pod 必须由外部调用方定期调 renew()/renew_pod() 心跳续租, 超过 TTL 未续租的
路由条目视为该 Pod 已下线, 自动失效。
"""
import os
import json
import logging
import time
import threading
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Redis Key 前缀
REDIS_PREFIX = "tianlian:route:"
KEY_STATION_ROUTE = "station:route:{station_id}"  # 单场站路由
KEY_POD_STATIONS = "pod:{pod_id}:stations"         # Pod 下场站集合
KEY_REGION_STATIONS = "region:{region_id}:stations"  # 区域下场站集合
KEY_POD_REGISTRY = "pod:registry:{pod_id}"         # Pod 注册信息

# 卡片 b9b1c588: 路由键 TTL (秒)。存活 Pod 通过 renew/renew_pod 心跳续租,
# 超时未续租即失效 —— 常量集中定义, 四类键共用同一租期。
ROUTE_TTL = 300


class StationRouter:
    """
    全局场站路由模块
    
    单Pod模式: 所有路由指向本地 (local_only=True)
    多Pod模式: 通过 Redis 存储路由表
    
    用法:
        router = StationRouter(local_only=True)  # 单Pod
        router = StationRouter(redis_client=redis)  # 多Pod
        
        pod = router.route_station(station_id)  # 查询
        router.register(station_id, "pod-02", "south-china")  # 注册
    """
    
    def __init__(
        self,
        local_only: bool = True,
        redis_client: Optional[Any] = None,
        pod_id: str = "pod-01",
        region_id: str = "default",
        endpoint: str = "http://localhost:8000"
    ):
        """
        初始化路由器
        
        Args:
            local_only: 是否单Pod模式（默认True）
            redis_client: Redis 客户端（多Pod模式必需）
            pod_id: 本 Pod 的 ID
            region_id: 本 Pod 所属区域
            endpoint: 本 Pod 的访问地址
        """
        self.local_only = local_only
        self.redis = redis_client
        self.pod_id = pod_id
        self.region_id = region_id
        self.endpoint = endpoint
        
        # 单Pod模式：使用本地字典缓存
        self._local_routes: Dict[int, Dict[str, str]] = {}

        # local_only 分支本地字典的并发保护: register/unregister/list 互斥, 防止
        # dict check-then-act KeyError 与迭代中 size 变更竞态 (FastAPI 同步端点在
        # threadpool 并发调用本路由; 多Pod走 Redis 自身原子, 无需此锁)。RLock 以便
        # 未来持锁调用内部 helper 时不自死锁。
        self._lock = threading.RLock()
        
        # 本 Pod 信息
        self._local_pod_info = {
            "pod_id": pod_id,
            "region_id": region_id,
            "endpoint": endpoint,
        }
        
        if local_only:
            logger.info(
                "StationRouter 初始化: 单Pod模式 (pod_id=%s, region_id=%s)",
                pod_id, region_id
            )
        else:
            if redis_client is None:
                logger.warning("多Pod模式但未提供 Redis 客户端，将降级为单Pod模式")
                self.local_only = True
            else:
                logger.info(
                    "StationRouter 初始化: 多Pod模式 (pod_id=%s, Redis已连接)",
                    pod_id
                )
    
    def _get_redis_key(self, key_template: str, **kwargs) -> str:
        """生成 Redis key"""
        return f"{REDIS_PREFIX}{key_template.format(**kwargs)}"
    
    def _default_route(self) -> Dict[str, str]:
        """返回默认本地路由"""
        return {
            "pod_id": self.pod_id,
            "region_id": self.region_id,
            "endpoint": self.endpoint,
        }
    
    def route_station(self, station_id: int) -> Dict[str, str]:
        """
        查询 station_id 归属的 pod_id + region_id
        
        Args:
            station_id: 场站 ID
            
        Returns:
            {"pod_id": "pod-01", "region_id": "default", "endpoint": "http://..."}
            
        单Pod模式: 直接返回本地信息
        多Pod模式: 从 Redis 查询，找不到时返回本地
        """
        if self.local_only:
            # 单Pod模式：直接返回本地
            return self._default_route()
        
        # 多Pod模式：从 Redis 查询
        try:
            key = self._get_redis_key(KEY_STATION_ROUTE, station_id=station_id)
            route_json = self.redis.get(key)
            
            if route_json:
                route = json.loads(route_json)
                logger.debug("场站 %d 路由: pod=%s, region=%s", 
                            station_id, route["pod_id"], route["region_id"])
                return route
            
            # 未找到路由：返回本地（兜底）
            logger.warning("场站 %d 未找到路由，使用本地 Pod", station_id)
            return self._default_route()
            
        except Exception as e:
            logger.error("查询场站路由失败: %s, 降级为本地", e)
            return self._default_route()
    
    def route_device(self, device_id: int, station_id: Optional[int] = None) -> Dict[str, str]:
        """
        查询设备归属的 Pod（通过 station_id 间接查）
        
        Args:
            device_id: 设备 ID
            station_id: 可选的场站 ID（如果已知可避免额外查询）
            
        Returns:
            {"pod_id": "pod-01", "region_id": "default", "endpoint": "http://..."}
        """
        # 设备归属于场站，通过场站路由
        if station_id:
            return self.route_station(station_id)
        
        # 未提供 station_id 时，返回本地（实际需要通过 DB 查询 station_id）
        # 这里提供接口，调用者需先查询设备所属场站
        logger.debug("设备 %d 路由查询: 未提供 station_id，返回本地", device_id)
        return self._default_route()
    
    def register(
        self,
        station_id: int,
        pod_id: str,
        region_id: str,
        endpoint: Optional[str] = None
    ) -> bool:
        """
        注册/更新场站路由
        
        Args:
            station_id: 场站 ID
            pod_id: 目标 Pod ID
            region_id: 目标区域 ID
            endpoint: Pod 访问地址（可选，自动从 Pod 注册表获取）
            
        Returns:
            True 成功, False 失败
        """
        route_data = {
            "pod_id": pod_id,
            "region_id": region_id,
            "endpoint": endpoint or f"http://{pod_id}:8000",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        if self.local_only:
            # 单Pod模式：存入本地字典 (临界区: 与 unregister/list 互斥, 防 dict size 变更竞态)
            with self._lock:
                self._local_routes[station_id] = route_data
            logger.info("场站 %d 路由注册(本地): pod=%s", station_id, pod_id)
            return True
        
        # 多Pod模式：写入 Redis
        try:
            # 1. 写入场站路由 (带 TTL, 见模块 docstring 心跳约定)
            key_route = self._get_redis_key(KEY_STATION_ROUTE, station_id=station_id)
            self.redis.set(key_route, json.dumps(route_data), ex=ROUTE_TTL)

            # 2. 添加到 Pod 场站集合
            key_pod_stations = self._get_redis_key(KEY_POD_STATIONS, pod_id=pod_id)
            self.redis.sadd(key_pod_stations, str(station_id))
            self.redis.expire(key_pod_stations, ROUTE_TTL)

            # 3. 添加到区域场站集合
            key_region_stations = self._get_redis_key(KEY_REGION_STATIONS, region_id=region_id)
            self.redis.sadd(key_region_stations, str(station_id))
            self.redis.expire(key_region_stations, ROUTE_TTL)
            
            logger.info("场站 %d 路由注册(Redis): pod=%s, region=%s", 
                       station_id, pod_id, region_id)
            return True
            
        except Exception as e:
            logger.error("场站路由注册失败: %s", e)
            return False
    
    def unregister(self, station_id: int) -> bool:
        """
        移除场站路由
        
        Args:
            station_id: 场站 ID
            
        Returns:
            True 成功, False 失败
        """
        if self.local_only:
            # 单Pod模式：从本地字典删除 (原子 pop + 临界区: 防 check-then-act KeyError 竞态)
            with self._lock:
                removed = self._local_routes.pop(station_id, None) is not None
            if removed:
                logger.info("场站 %d 路由移除(本地)", station_id)
            return True
        
        # 多Pod模式：从 Redis 删除
        try:
            # 先获取当前路由信息
            route = self.route_station(station_id)
            pod_id = route.get("pod_id")
            region_id = route.get("region_id")
            
            # 1. 删除场站路由
            key_route = self._get_redis_key(KEY_STATION_ROUTE, station_id=station_id)
            self.redis.delete(key_route)
            
            # 2. 从 Pod 场站集合移除
            if pod_id:
                key_pod_stations = self._get_redis_key(KEY_POD_STATIONS, pod_id=pod_id)
                self.redis.srem(key_pod_stations, str(station_id))
            
            # 3. 从区域场站集合移除
            if region_id:
                key_region_stations = self._get_redis_key(KEY_REGION_STATIONS, region_id=region_id)
                self.redis.srem(key_region_stations, str(station_id))
            
            logger.info("场站 %d 路由移除(Redis)", station_id)
            return True
            
        except Exception as e:
            logger.error("场站路由移除失败: %s", e)
            return False
    
    def list_by_pod(self, pod_id: str) -> List[int]:
        """
        列出某个 Pod 下的所有场站
        
        Args:
            pod_id: Pod ID
            
        Returns:
            station_id 列表
        """
        if self.local_only:
            # 单Pod模式：从本地字典筛选 (锁内取 keys 快照, 防 register/unregister 并发改 size)
            if pod_id == self.pod_id:
                with self._lock:
                    return list(self._local_routes.keys())
            return []
        
        # 多Pod模式：从 Redis Set 获取
        try:
            key_pod_stations = self._get_redis_key(KEY_POD_STATIONS, pod_id=pod_id)
            station_ids = self.redis.smembers(key_pod_stations)
            return [int(sid) for sid in station_ids if sid]
        except Exception as e:
            logger.error("查询 Pod 场站列表失败: %s", e)
            return []
    
    def list_by_region(self, region_id: str) -> List[int]:
        """
        列出某个区域下的所有场站
        
        Args:
            region_id: 区域 ID
            
        Returns:
            station_id 列表
        """
        if self.local_only:
            # 单Pod模式：从本地字典筛选 (锁内取 keys 快照, 防 register/unregister 并发改 size)
            if region_id == self.region_id:
                with self._lock:
                    return list(self._local_routes.keys())
            return []
        
        # 多Pod模式：从 Redis Set 获取
        try:
            key_region_stations = self._get_redis_key(KEY_REGION_STATIONS, region_id=region_id)
            station_ids = self.redis.smembers(key_region_stations)
            return [int(sid) for sid in station_ids if sid]
        except Exception as e:
            logger.error("查询区域场站列表失败: %s", e)
            return []
    
    def renew(
        self,
        station_id: Optional[int] = None,
        pod_id: Optional[str] = None,
        region_id: Optional[str] = None
    ) -> int:
        """
        心跳续租: 重置指定路由键的 TTL 为 ROUTE_TTL (卡片 b9b1c588)

        只对实际存在的键续租 (expire 对不存在键返回 False 不计), 避免心跳
        把早已下线的 Pod 键复活。本模块不启动后台线程, 由存活 Pod 的外部
        心跳调度定期调用。

        Args:
            station_id: 续租该场站的路由键 + 其归属 pod/region 集合键
            pod_id: 续租该 Pod 的场站集合键
            region_id: 续租该区域的场站集合键

        Returns:
            成功续租的键数量
        """
        if self.local_only:
            return 0  # 本地字典无 TTL 概念

        renewed = 0
        keys = set()
        try:
            if station_id is not None:
                keys.add(self._get_redis_key(KEY_STATION_ROUTE, station_id=station_id))
            if pod_id:
                keys.add(self._get_redis_key(KEY_POD_STATIONS, pod_id=pod_id))
            if region_id:
                keys.add(self._get_redis_key(KEY_REGION_STATIONS, region_id=region_id))

            for key in keys:
                if self.redis.expire(key, ROUTE_TTL):
                    renewed += 1
            return renewed
        except Exception as e:
            logger.error("路由键续租失败: %s", e)
            return renewed

    def renew_pod(self, pod_id: str) -> bool:
        """
        心跳续租: 重置 Pod 注册键的 TTL (卡片 b9b1c588)

        Returns:
            True 续租成功, False 键不存在或失败
        """
        if self.local_only:
            return False
        try:
            key = self._get_redis_key(KEY_POD_REGISTRY, pod_id=pod_id)
            return bool(self.redis.expire(key, ROUTE_TTL))
        except Exception as e:
            logger.error("Pod 注册键续租失败: %s", e)
            return False

    def register_pod(
        self,
        pod_id: str,
        region_id: str,
        endpoint: str,
        version: str = "3.0.0",
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        注册 Pod 信息（用于跨 Pod 发现）
        
        Args:
            pod_id: Pod ID
            region_id: 区域 ID
            endpoint: 访问地址
            version: 版本号
            metadata: 其他元数据
            
        Returns:
            True 成功, False 失败
        """
        pod_info = {
            "pod_id": pod_id,
            "region_id": region_id,
            "endpoint": endpoint,
            "version": version,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata or {},
        }
        
        if self.local_only:
            logger.warning("单Pod模式不支持 Pod 注册")
            return False
        
        try:
            key = self._get_redis_key(KEY_POD_REGISTRY, pod_id=pod_id)
            self.redis.set(key, json.dumps(pod_info), ex=ROUTE_TTL)
            logger.info("Pod %s 注册成功: endpoint=%s", pod_id, endpoint)
            return True
        except Exception as e:
            logger.error("Pod 注册失败: %s", e)
            return False
    
    def get_pod_info(self, pod_id: str) -> Optional[Dict]:
        """
        获取 Pod 注册信息
        
        Args:
            pod_id: Pod ID
            
        Returns:
            Pod 信息字典，未找到返回 None
        """
        if self.local_only:
            if pod_id == self.pod_id:
                return self._local_pod_info
            return None
        
        try:
            key = self._get_redis_key(KEY_POD_REGISTRY, pod_id=pod_id)
            pod_json = self.redis.get(key)
            if pod_json:
                return json.loads(pod_json)
            return None
        except Exception as e:
            logger.error("获取 Pod 信息失败: %s", e)
            return None
    
    def list_all_pods(self) -> List[Dict]:
        """
        列出所有已注册的 Pod
        
        Returns:
            Pod 信息列表
        """
        if self.local_only:
            return [self._local_pod_info]
        
        try:
            # 扫描所有 pod:registry:* keys
            # 卡片 b9b1c588: scan_iter 增量游标替代 KEYS, 避免 O(N) 阻塞单线程 Redis
            pattern = self._get_redis_key("pod:registry:*")
            keys = list(self.redis.scan_iter(pattern))
            pods = []
            for key in keys:
                pod_json = self.redis.get(key)
                if pod_json:
                    pods.append(json.loads(pod_json))
            return pods
        except Exception as e:
            logger.error("列出所有 Pod 失败: %s", e)
            return [self._local_pod_info]


# 全局单例（延迟初始化）
# DCL 双检锁: FastAPI 同步端点(pod_routes/cross_pod)在 threadpool 中并发调用
# get_station_router(), 无锁的 check-then-act 会让多线程各自构造、实例分裂。
# 样板: app/services/ai_model_config.py 的 AIModelManager.__new__。
_router_instance: Optional[StationRouter] = None
_router_lock = threading.Lock()


def get_station_router() -> StationRouter:
    """
    获取全局 StationRouter 实例
    
    从环境变量读取配置:
    - POD_LOCAL_ONLY: 是否单Pod模式（默认 true）
    - POD_ID: 本 Pod ID（默认 pod-01）
    - REGION_ID: 区域 ID（默认 default）
    - POD_ENDPOINT: 访问地址（默认 http://localhost:8000）
    """
    global _router_instance

    if _router_instance is None:
        with _router_lock:
            # 双重检查: 拿锁期间可能已被其他线程构造, 避免重复实例化
            if _router_instance is None:
                local_only = os.getenv("POD_LOCAL_ONLY", "true").lower() == "true"
                pod_id = os.getenv("POD_ID", "pod-01")
                region_id = os.getenv("REGION_ID", "default")
                endpoint = os.getenv("POD_ENDPOINT", "http://localhost:8000")

                redis_client = None
                if not local_only:
                    # 多Pod模式：尝试连接 Redis
                    try:
                        from app.core.cache import cache
                        if cache.enabled:
                            redis_client = cache.client
                    except Exception:
                        pass

                _router_instance = StationRouter(
                    local_only=local_only,
                    redis_client=redis_client,
                    pod_id=pod_id,
                    region_id=region_id,
                    endpoint=endpoint
                )

    return _router_instance


def init_station_router(
    local_only: bool = True,
    redis_client: Optional[Any] = None,
    pod_id: str = "pod-01",
    region_id: str = "default",
    endpoint: str = "http://localhost:8000"
) -> StationRouter:
    """
    手动初始化全局 StationRouter
    
    用于在应用启动时显式配置路由器
    """
    global _router_instance
    with _router_lock:
        _router_instance = StationRouter(
            local_only=local_only,
            redis_client=redis_client,
            pod_id=pod_id,
            region_id=region_id,
            endpoint=endpoint
        )
        return _router_instance
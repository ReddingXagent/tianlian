"""
虚拟电厂(VPP)调度优化服务 — 包入口

原 app/services/vpp/dispatch_optimizer.py(1138行) 按职责拆为子模块(卡 61109a8a):
- models.py      : 数据模型与枚举
- optimizer.py   : VPPOptimizer 调度优化算法
- coordinator.py : MultiStationCoordinator 多站点协同调度器

本 __init__ 重导出全部公共符号, 保持
`from app.services.vpp.dispatch_optimizer import X` / `import app.services.vpp.dispatch_optimizer as m`
两类导入路径完全不变。

⚠️ 单例状态 (_coordinator / _lock / get_vpp_coordinator) 必须定义在本 __init__:
测试 monkeypatch.setattr(dispatch_optimizer, "_coordinator", None) 与
get_vpp_coordinator() 的 `global _coordinator` 都绑定本模块命名空间;
若挪到子模块, monkeypatch 改的是包属性, 而 global 读的是子模块属性, 二者脱钩 → 单例失效。
"""
import threading
import logging
from typing import Optional

from .models import (
    ResourceType,
    DispatchMode,
    GridSignalType,
    GridSignal,
    StationStatus,
    ResourceCapability,
    DispatchCommand,
    DispatchPlan,
)
from .optimizer import VPPOptimizer
from .coordinator import MultiStationCoordinator

__all__ = [
    'ResourceType',
    'DispatchMode',
    'GridSignalType',
    'GridSignal',
    'StationStatus',
    'ResourceCapability',
    'DispatchCommand',
    'DispatchPlan',
    'VPPOptimizer',
    'MultiStationCoordinator',
    'get_vpp_coordinator',
]

logger = logging.getLogger("vpp")


# ─── 单例 ───

_coordinator: Optional[MultiStationCoordinator] = None
_lock = threading.Lock()

def get_vpp_coordinator() -> MultiStationCoordinator:
    """获取VPP调度器单例"""
    global _coordinator
    if _coordinator is None:
        with _lock:
            if _coordinator is None:
                _coordinator = MultiStationCoordinator()
                # 模拟数据开关: VPP_SIMULATE!=0 时加载 (卡 1b2f4cc4)
                # 生产环境设 VPP_SIMULATE=0 关闭, 避免模拟站点污染真实调度
                from app.core.config import settings
                if settings.VPP_SIMULATE != "0":
                    _coordinator.simulate_station_data(count=5)
                    logger.info("VPP调度器已启动, 已加载模拟站点数据")
                else:
                    logger.info("VPP调度器已启动 (生产模式, 模拟数据已关闭)")
    return _coordinator

"""
权限装饰器模块

卡 885878ca1 把 169 个无 await 的 async 端点转为同步 def (FastAPI 自动丢进线程池,
不再阻塞事件循环)。admin_required 原写死 async wrapper + `await func`, 对这些同步
端点会 `await` 一个普通 dict 返回值 → TypeError: object dict can't be used in
'await' expression (见 operate/recharge approve|reject)。改为按 func 是否协程自适应,
async/def 两类端点都能正确包装。
"""
import inspect
from functools import wraps


def admin_required(func):
    """装饰器：要求管理员权限（配合 get_current_admin 使用）。

    自适应同步/异步端点: async def → async wrapper(await); def → 同步 wrapper(直返)。
    实际鉴权由 get_current_admin 依赖完成, 此装饰器为标记 + 透传。
    """
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return sync_wrapper

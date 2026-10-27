"""
卡片 411936df: SoftTimeLimitExceeded 统一入口。

task_soft_time_limit=300 抛出的 SoftTimeLimitExceeded 是 Exception 子类,
会被任务体内宽 `except Exception` 吞掉 → 软超时失效 → 跑满 600s 硬杀 →
task_reject_on_worker_lost 重投 → 从头重跑 → agent_memory 重复 finding。

约定: 所有包裹任务主循环/逐站/逐租户循环的宽 except 站点, 一律前置

    except SoftTimeLimitExceeded:
        raise

KeyboardInterrupt/SystemExit 非 Exception 子类, 原语义不受影响。
"""
from celery.exceptions import SoftTimeLimitExceeded

__all__ = ["SoftTimeLimitExceeded"]

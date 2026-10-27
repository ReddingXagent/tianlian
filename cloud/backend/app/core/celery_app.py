"""
Celery 异步任务配置
Phase 4 - 天链V3 异步任务框架
"""
import os
import logging

logger = logging.getLogger(__name__)

# Celery Broker URL - 优先环境变量，fallback到Redis默认
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# 尝试导入Celery，如果失败则提供mock实现
try:
    from celery import Celery
    from celery.schedules import crontab
    CELERY_AVAILABLE = True
except ImportError:
    logger.warning("Celery未安装，异步任务功能将不可用")
    CELERY_AVAILABLE = False
    Celery = None
    crontab = None

if CELERY_AVAILABLE:
    celery_app = Celery(
        "tianlian_v3",
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=[
            "app.tasks.settlement_tasks",
            "app.tasks.analytics_tasks",
            "app.tasks.maintenance_tasks",
            "app.tasks.carbon_tasks",
            "app.tasks.energy_tasks",
            "app.tasks.agent_patrol",
            "app.tasks.fleet_alert_tasks",
        ],
    )

    # Celery 配置
    celery_app.conf.update(
        # 序列化
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",

        # 时区
        timezone="Asia/Shanghai",
        enable_utc=True,

        # 任务结果过期时间（1小时）
        result_expires=3600,

        # 并发
        worker_concurrency=4,
        worker_prefetch_multiplier=2,

        # 任务超时
        task_soft_time_limit=300,  # 5分钟软超时
        task_time_limit=600,       # 10分钟硬超时

        # 自动发现任务模块
        task_routes={
            "app.tasks.analytics_tasks.*": {"queue": "analytics"},
            "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
            "app.tasks.fleet_alert_tasks.*": {"queue": "maintenance"},
        },

        # 默认队列
        task_default_queue="default",

        # 重试策略
        task_acks_late=True,
        task_reject_on_worker_lost=True,

        # Celery Beat 定时任务配置
        beat_schedule={
            # 每天凌晨3点生成健康报告
            "daily-health-report": {
                "task": "analytics.batch_health_report",
                "schedule": crontab(hour=3, minute=0),
                "args": (),  # 所有站点
                "options": {"expires": 77760, "queue": "analytics"},
            },
            # 每周日凌晨4点清理旧数据
            "weekly-data-cleanup": {
                "task": "maintenance.cleanup_old_data",
                "schedule": crontab(hour=4, minute=0, day_of_week=0),
                "args": (30,),  # 清理30天前的数据
                "options": {"expires": 544320, "queue": "maintenance"},
            },
            # 每日凌晨4:30数据保留清理 (卡 0364c10e): 高增长日志表按窗口过期。
            # 与 weekly-data-cleanup (周日04:00) 错峰 30 分钟, 避免并发写放大。
            "daily-retention-logs-cleanup": {
                "task": "maintenance.cleanup_retention_logs",
                "schedule": crontab(hour=4, minute=30),
                "args": (),
                "options": {"expires": 77760, "queue": "maintenance"},
            },
            # 每小时检查预测性维护
            "hourly-fault-prediction": {
                "task": "maintenance.batch_predict_faults",
                "schedule": crontab(minute=30),  # 每小时30分执行
                "args": (),
                "options": {"expires": 3240, "queue": "maintenance"},
            },
            # 每日凌晨2点: 碳减排日聚合
            "carbon-daily-aggregate": {
                "task": "carbon.daily_aggregate",
                "schedule": crontab(hour=2, minute=0),
                "args": (),
                "options": {"expires": 77760, "queue": "default"},
            },
            # 每月1日凌晨3点: 碳减排月度汇总
            "carbon-monthly-summary": {
                "task": "carbon.monthly_summary",
                "schedule": crontab(hour=3, minute=0, day_of_month=1),
                "args": (),
                "options": {"expires": 2332800, "queue": "default"},
            },
            # 每日凌晨1点: 运营日结
            "settlement-daily": {
                "task": "settlement.daily",
                "schedule": crontab(hour=1, minute=0),
                "args": (),
                "options": {"expires": 77760, "queue": "default"},
            },
            # 每日凌晨1:30: 支付对账
            "settlement-reconcile": {
                "task": "settlement.reconcile",
                "schedule": crontab(hour=1, minute=30),
                "args": (),
                "options": {"expires": 77760, "queue": "default"},
            },
            # 每日凌晨2:30: 营收日报聚合(补前一天 revenue_daily)
            "revenue-daily-aggregate": {
                "task": "analytics.aggregate_revenue_daily",
                "schedule": crontab(hour=2, minute=30),
                "args": (),
                "options": {"expires": 77760, "queue": "analytics"},
            },
            # 每日凌晨2:40: 站点日报指标聚合(补前一天 station_daily_metrics)
            "station-daily-metrics-aggregate": {
                "task": "analytics.aggregate_station_daily_metrics",
                "schedule": crontab(hour=2, minute=40),
                "args": (),
                "options": {"expires": 77760, "queue": "analytics"},
            },
            # 每15min: 光储充能量调度 (多策略仲裁 + 能量流落库)
            "energy-dispatch-cycle": {
                "task": "energy.dispatch_cycle",
                "schedule": crontab(minute="*/15"),
                "args": (),
                "options": {"expires": 840, "queue": "default"},
            },
            # 每5min: 僵尸 pending 订单清理 (RemoteStart 无 StartTransaction 确认 → 超时取消, 契约 §7.1)
            "stale-pending-order-cleanup": {
                "task": "maintenance.cleanup_stale_pending_orders",
                "schedule": crontab(minute="*/5"),
                "args": (),
                "options": {"expires": 240, "queue": "maintenance"},
            },
            # 每5min: 智能体运维巡检 (设备离线/储能SOC/桩功率) — 全租户
            "agent-patrol-maintenance": {
                "task": "agent.patrol.maintenance_all",
                "schedule": crontab(minute="*/5"),
                "args": (),
                "options": {"expires": 240, "queue": "maintenance"},
            },
            # 每5min: 车队告警规则扫描 (低电量/异常充电/超时占桩) — 有启用规则的企业 (卡 49aafa24)
            "fleet-alert-scan": {
                "task": "fleet.scan_fleet_alerts",
                "schedule": crontab(minute="*/5"),
                "args": (),
                "options": {"expires": 240, "queue": "maintenance"},
            },
            # 每10min: 智能体运营巡检 (异常订单/低余额车队/配置缺失) — 全租户
            "agent-patrol-operations": {
                "task": "agent.patrol.operations_all",
                "schedule": crontab(minute="*/10"),
                "args": (),
                "options": {"expires": 540, "queue": "default"},
            },
            # 每30min: 智能体平台巡检 (API健康/磁盘/Celery队列) — 平台级
            "agent-patrol-platform": {
                "task": "agent.patrol.platform",
                "schedule": crontab(minute="*/30"),
                "args": (),
                "options": {"expires": 1620, "queue": "default"},
            },
        },
    )

    # 自动发现任务
    celery_app.autodiscover_tasks(["app.tasks"])
else:
    # Mock celery_app当Celery未安装
    class MockCeleryApp:
        """Mock Celery App for graceful degradation"""
        def __init__(self, *args, **kwargs):
            self.tasks = {}
        
        def AsyncResult(self, task_id):
            return MockAsyncResult(task_id)
        
        class MockAsyncResult:
            def __init__(self, task_id):
                self.id = task_id
                self.status = "UNAVAILABLE"
                self.result = None
            def ready(self):
                return False
            def successful(self):
                return False
            def revoke(self, terminate=False):
                pass
    
    celery_app = MockCeleryApp()


def get_celery_status() -> dict:
    """获取Celery worker状态"""
    if not CELERY_AVAILABLE:
        return {
            "status": "unavailable",
            "error": "Celery未安装，请运行: pip install celery",
            "broker_url": CELERY_BROKER_URL.split("@")[-1] if "@" in CELERY_BROKER_URL else CELERY_BROKER_URL,
        }
    
    try:
        inspector = celery_app.control.inspect()
        active = inspector.active()
        stats = inspector.stats()
        return {
            "status": "running" if stats else "no_workers",
            "active_tasks": sum(len(v) for v in (active or {}).values()) if active else 0,
            "workers": list((stats or {}).keys()),
            "broker_url": CELERY_BROKER_URL.split("@")[-1] if "@" in CELERY_BROKER_URL else CELERY_BROKER_URL,
        }
    except Exception as e:
        logger.warning("获取Celery状态失败: %s", e)
        return {"status": "unavailable", "error": str(e)}

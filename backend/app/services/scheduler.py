"""
定时任务调度器 - 健康度监控 + 告警升级扫描 + 维护计划检查
Phase35: 增加告警升级扫描任务(每5分钟)
Phase: 增加维护计划到期检查(每1小时)
"""
import schedule
import time
import threading
import logging
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.services.health_monitor import health_monitor
from app.services.alarm_rule_service import evaluate_all_rules, scan_and_escalate
from app.services.maintenance_schedule import maintenance_schedule_checker

logger = logging.getLogger(__name__)


class HealthScheduler:
    """健康度定时任务调度器"""

    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 30  # minutes
        self.check_interval = 30  # minutes

    def run_escalation_scan(self):
        """执行告警升级扫描（每5分钟）"""
        try:
            result = scan_and_escalate()
            if result:
                logger.info("[告警升级扫描] %d 个告警已升级", len(result))
        except Exception as e:
            logger.error("[告警升级扫描] 失败: %s", e)

    def run_maintenance_check(self):
        """执行维护计划到期检查（每1小时）"""
        try:
            result = maintenance_schedule_checker.check_maintenance_schedule()
            if result:
                logger.info("[维护计划检查] %d 个设备需要关注", len(result))
        except Exception as e:
            logger.error("[维护计划检查] 失败: %s", e)

    def run_health_check(self):
        """执行健康检查 + 告警规则评估任务"""
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        logger.info("[定时任务] %s 开始", ts)
        db = SessionLocal()
        try:
            # 1. 计算健康度
            results = health_monitor.calculate_all_health(db)
            logger.info("[定时任务] 更新了 %d 个设备健康度", len(results))

            # 2. 检查健康告警并创建工单
            alarms = health_monitor.check_and_create_alarms(db)
            if alarms:
                logger.info("[定时任务] 创建了 %d 个告警和工单", len(alarms))
                for a in alarms:
                    logger.info("  - %s: %.1f%% -> %s", a['device'], a['score'], a['workorder_id'])

            # 3. 评估告警规则
            rule_results = evaluate_all_rules()
            triggered = [r for r in rule_results if r.get('triggered')]
            if triggered:
                for tr in triggered:
                    devices = tr.get('devices', [])
                    logger.info("[告警规则] %s: 触发 %d 台设备", tr['rule_name'], len(devices))

            # 4. 告警升级扫描
            self.run_escalation_scan()
        except Exception as e:
            logger.error("[定时任务] 错误: %s", str(e))
            return None
        finally:
            db.close()
        logger.info("[定时任务] %s 完成", ts)
        return True

    def start(self, interval_minutes=30):
        """启动定时任务"""
        if self.running:
            logger.info("[定时任务] 调度器已在运行")
            return

        # 防御性清理：避免历史注册残留导致 run_pending 双倍触发
        schedule.clear()

        self.running = True

        # 设置定时任务
        schedule.every(interval_minutes).minutes.do(self.run_health_check)
        schedule.every(5).minutes.do(self.run_escalation_scan)
        schedule.every(60).minutes.do(self.run_maintenance_check)  # 每小时检查维护到期

        # 立即执行一次
        self.run_health_check()
        self.run_maintenance_check()  # 启动时立即检查一次维护计划

        # 启动调度线程
        def run_scheduler():
            logger.info("[定时任务] 启动调度器，每 %d 分钟执行一次健康检查", interval_minutes)
            logger.info("[定时任务] 告警升级扫描每5分钟执行一次")
            while self.running:
                schedule.run_pending()
                time.sleep(30)  # 每30秒检查一次（提高调度精度）

        self.thread = threading.Thread(target=run_scheduler, daemon=True)
        self.thread.start()
        logger.info("[定时任务] 调度器已启动")

    def stop(self):
        """停止定时任务"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        schedule.clear()  # 清除全局注册，防止 start→stop→start 双倍注册
        logger.info("[定时任务] 调度器已停止")


# 全局实例
health_scheduler = HealthScheduler()


def start_health_scheduler(interval_minutes=30):
    """启动健康度定时任务"""
    health_scheduler.start(interval_minutes)


def stop_health_scheduler():
    """停止健康度定时任务"""
    health_scheduler.stop()


if __name__ == '__main__':
    # 测试运行
    start_health_scheduler(interval_minutes=5)
    try:
        time.sleep(600)  # 运行10分钟
    except KeyboardInterrupt:
        stop_health_scheduler()
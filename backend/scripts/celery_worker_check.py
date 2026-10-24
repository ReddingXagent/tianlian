#!/usr/bin/env python
"""
Celery Worker 验证脚本
Phase 5 - 测试Redis连接和Worker启动
"""
import os
import sys
import logging

# 设置环境变量（云端配置）
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_redis_connection():
    """检查Redis连接"""
    try:
        import redis
        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        
        # 解析Redis URL
        if broker_url.startswith("redis://"):
            parts = broker_url.replace("redis://", "").split("/")
            host_port = parts[0].split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 6379
            db = int(parts[1]) if len(parts) > 1 else 0
            
            r = redis.Redis(host=host, port=port, db=db, socket_connect_timeout=5)
            r.ping()
            logger.info(f"✅ Redis连接成功: {host}:{port}/{db}")
            return True
    except ImportError:
        logger.error("❌ Redis库未安装: pip install redis")
        return False
    except Exception as e:
        logger.error(f"❌ Redis连接失败: {e}")
        return False


def check_celery_available():
    """检查Celery是否可用"""
    try:
        from celery import Celery
        logger.info("✅ Celery已安装")
        return True
    except ImportError:
        logger.error("❌ Celery未安装: pip install celery")
        return False


def start_worker():
    """启动Celery Worker"""
    if not check_redis_connection():
        logger.error("Redis连接失败，无法启动Worker")
        return False
    
    if not check_celery_available():
        logger.error("Celery未安装，无法启动Worker")
        return False
    
    try:
        from app.core.celery_app import celery_app
        
        logger.info("启动Celery Worker...")
        logger.info("队列: default, analytics, maintenance")
        logger.info("并发: 4 workers")
        
        # 启动命令（在实际环境中通过命令行执行）
        # celery -A app.core.celery_app worker --loglevel=info --queues=default,analytics,maintenance
        
        logger.info("✅ Celery Worker配置就绪")
        logger.info("启动命令: celery -A app.core.celery_app worker --loglevel=info")
        return True
    except Exception as e:
        logger.error(f"❌ Worker启动失败: {e}")
        return False


def test_task_submission():
    """测试任务提交"""
    try:
        from app.core.celery_app import celery_app, CELERY_AVAILABLE
        
        if not CELERY_AVAILABLE:
            logger.warning("Celery不可用，无法测试任务提交")
            return False
        
        # 获取Worker状态
        inspector = celery_app.control.inspect()
        stats = inspector.stats()
        
        if stats:
            logger.info(f"✅ Worker运行中: {list(stats.keys())}")
            return True
        else:
            logger.warning("⚠️ 无活跃Worker，请先启动Worker")
            return False
    except Exception as e:
        logger.error(f"❌ 任务测试失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("Celery Worker 验证脚本")
    logger.info("=" * 50)
    
    # 1. 检查Redis
    redis_ok = check_redis_connection()
    
    # 2. 检查Celery
    celery_ok = check_celery_available()
    
    # 3. 检查Worker状态
    if redis_ok and celery_ok:
        test_task_submission()
    
    # 4. 提供启动指南
    logger.info("\n" + "=" * 50)
    logger.info("启动指南:")
    logger.info("=" * 50)
    logger.info("1. 确保Redis运行: redis-server")
    logger.info("2. 启动Worker: celery -A app.core.celery_app worker --loglevel=info")
    logger.info("3. 启动Beat(定时任务): celery -A app.core.celery_app beat --loglevel=info")
    logger.info("4. 监控: celery -A app.core.celery_app flower")
    logger.info("\n云端部署:")
    logger.info("CELERY_BROKER_URL=redis://demo.example.com:6379/0")
    logger.info("CELERY_RESULT_BACKEND=redis://demo.example.com:6379/1")
    
    return redis_ok and celery_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
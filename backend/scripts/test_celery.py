#!/usr/bin/env python
"""
Celery Worker 验证脚本
Phase 5 - 测试Redis连接和Worker启动
"""
import os
import sys

# 设置环境变量
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")


def check_redis():
    """检查Redis连接"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=5)
        r.ping()
        print("OK Redis connection: localhost:6379")
        return True
    except ImportError:
        print("ERROR Redis library not installed: pip install redis")
        return False
    except Exception as e:
        print(f"ERROR Redis connection failed: {e}")
        return False


def check_celery():
    """检查Celery是否可用"""
    try:
        from celery import Celery
        print("OK Celery installed")
        return True
    except ImportError:
        print("ERROR Celery not installed: pip install celery")
        return False


def check_worker_status():
    """检查Worker状态"""
    try:
        from app.core.celery_app import celery_app, CELERY_AVAILABLE
        
        if not CELERY_AVAILABLE:
            print("WARN Celery not available")
            return False
        
        inspector = celery_app.control.inspect()
        stats = inspector.stats()
        
        if stats:
            print(f"OK Workers running: {list(stats.keys())}")
            return True
        else:
            print("WARN No active workers")
            return False
    except Exception as e:
        print(f"ERROR Worker check failed: {e}")
        return False


def print_startup_guide():
    """打印启动指南"""
    print("\n" + "=" * 50)
    print("Celery Worker Startup Guide")
    print("=" * 50)
    print("1. Start Redis: redis-server")
    print("2. Start Worker:")
    print("   celery -A app.core.celery_app worker --loglevel=info")
    print("3. Start Beat (scheduled tasks):")
    print("   celery -A app.core.celery_app beat --loglevel=info")
    print("4. Monitor with Flower:")
    print("   celery -A app.core.celery_app flower")
    print("\nCloud deployment:")
    print("CELERY_BROKER_URL=redis://demo.example.com:6379/0")
    print("CELERY_RESULT_BACKEND=redis://demo.example.com:6379/1")


def main():
    print("=" * 50)
    print("Celery Worker Validation")
    print("=" * 50)
    
    redis_ok = check_redis()
    celery_ok = check_celery()
    
    if redis_ok and celery_ok:
        check_worker_status()
    
    print_startup_guide()
    
    return redis_ok and celery_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
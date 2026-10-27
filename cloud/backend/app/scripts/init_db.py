"""
数据库迁移脚本 - 创建基于光储充协议分析的新表

运行方式：
1. 如果使用 Alembic: alembic revision --autogenerate -m "add telemetry and fault code tables"
2. 如果直接初始化: python -m app.scripts.init_db
"""
from app.core.database import Base, engine
from app.models import *
import logging

logger = logging.getLogger(__name__)

def init_new_tables():
    """
    初始化新表
    
    创建表：
    - telemetry：遥测数据表
    - fault_codes：故障码知识库
    - diagnosis_rules：诊断规则
    - repair_guides：修复指南
    """
    try:
        # 创建所有新表（不删除已有表）
        Base.metadata.create_all(
            bind=engine,
            tables=[
                Telemetry.__table__,
                FaultCode.__table__,
                DiagnosisRule.__table__,
                RepairGuide.__table__,
            ]
        )
        logger.info("新表创建成功")
        return True
    except Exception as e:
        logger.error("创建表失败: %s", str(e))
        return False

def drop_new_tables():
    """
    删除新表（用于测试/重置）
    
    注意：会删除数据！
    """
    try:
        Base.metadata.drop_all(
            bind=engine,
            tables=[
                Telemetry.__table__,
                FaultCode.__table__,
                DiagnosisRule.__table__,
                RepairGuide.__table__,
            ]
        )
        logger.info("新表已删除")
        return True
    except Exception as e:
        logger.error("删除表失败: %s", str(e))
        return False

def check_tables_exist():
    """检查表是否存在"""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    tables = inspector.get_table_names()
    
    new_tables = ["telemetry", "fault_codes", "diagnosis_rules", "repair_guides"]
    
    result = {}
    for table in new_tables:
        result[table] = table in tables
    
    return result

if __name__ == "__main__":
    import sys
    
    logger.info("=" * 50)
    logger.info("天链V3数据库迁移工具")
    logger.info("=" * 50)
    
    # 检查表状态
    logger.info("检查表状态:")
    status = check_tables_exist()
    for table, exists in status.items():
        logger.info("  %s: %s", table, "存在" if exists else "不存在")
    
    # 如果有参数
    if len(sys.argv) > 1:
        action = sys.argv[1]
        
        if action == "init":
            logger.info("创建新表...")
            if init_new_tables():
                logger.info("创建成功")
            else:
                logger.error("创建失败")
        
        elif action == "drop":
            logger.info("删除新表...")
            if drop_new_tables():
                logger.info("删除成功")
            else:
                logger.error("删除失败")
        
        elif action == "reset":
            logger.info("重置（删除后重建）...")
            drop_new_tables()
            init_new_tables()
            logger.info("重置完成")
        
        elif action == "init_fault_codes":
            logger.info("初始化故障码数据...")
            from app.core.database import SessionLocal
            from app.data.fault_codes_init import init_fault_codes
            
            db = SessionLocal()
            try:
                init_fault_codes(db)
                logger.info("故障码初始化成功")
            except Exception as e:
                logger.error("故障码初始化失败: %s", str(e))
            finally:
                db.close()
    
    else:
        logger.info("可用命令:")
        logger.info("  python init_db.py init        - 创建新表")
        logger.info("  python init_db.py drop        - 删除新表")
        logger.info("  python init_db.py reset       - 重置新表")
        logger.info("  python init_db.py init_fault_codes - 初始化故障码数据")
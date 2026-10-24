"""
数据库迁移脚本 - 编码重构方案二

添加:
- teams.code 字段
- code_sequences 表
"""
from sqlalchemy import create_engine, text
import os

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'app.db')
ENGINE_URL = f"sqlite:///{DB_PATH}"

def migrate():
    """执行数据库迁移"""
    engine = create_engine(ENGINE_URL)
    
    print(f"开始迁移: {ENGINE_URL}")
    
    with engine.connect() as conn:
        # 1. 检查 teams 表是否已有 code 字段
        try:
            result = conn.execute(text("PRAGMA table_info(teams)"))
            columns = [row[1] for row in result]
            
            if 'code' not in columns:
                print("添加 teams.code 字段...")
                conn.execute(text("ALTER TABLE teams ADD COLUMN code VARCHAR(20)"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_code ON teams(code)"))
                print("✓ teams.code 字段已添加")
            else:
                print("✓ teams.code 字段已存在")
        except Exception as e:
            print(f"teams表检查失败: {e}")
        
        # 2. 创建 code_sequences 表
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS code_sequences (
                    key VARCHAR(32) PRIMARY KEY,
                    current_value BIGINT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_code_sequences_key ON code_sequences(key)"))
            print("✓ code_sequences 表已创建")
        except Exception as e:
            print(f"code_sequences表创建失败: {e}")
        
        conn.commit()
    
    print("迁移完成!")

if __name__ == "__main__":
    migrate()
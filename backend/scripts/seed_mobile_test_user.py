#!/usr/bin/env python
"""
移动端联调测试账号种子脚本（幂等）

创建/确保两个移动端联调测试账号存在：
  - mobile_test     / Tianlian2026!   角色 ADMIN     状态 active   (管理员/监控 APP)
  - mobile_operator / Tianlian2026!   角色 OPERATOR  状态 active   (工程师 APP)

幂等：账号已存在时不重复创建，仅按需校正密码/角色/状态，重复运行安全。
连库走 app.core.database.SessionLocal（继承 .env 的 DB_TYPE / DATABASE_URL），
独立运行：

    python scripts/seed_mobile_test_user.py

注意：脚本只 seed 数据，假设目标库的 users 表已通过 Alembic 迁移存在。
"""
import sys
from pathlib import Path

# 允许从 scripts/ 目录直接 python 执行：把 backend/ 加入 sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import bcrypt  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


# 联调账号清单（单一真相源，测试与脚本对齐时复制此结构）
MOBILE_TEST_USERS = [
    {
        "username": "mobile_test",
        "password": "Tianlian2026!",
        "real_name": "移动端联调-管理员",
        "role": UserRole.ADMIN,
        "status": "active",
    },
    {
        "username": "mobile_operator",
        "password": "Tianlian2026!",
        "real_name": "移动端联调-运维",
        "role": UserRole.OPERATOR,
        "status": "active",
    },
]


def hash_password(plain: str) -> str:
    """bcrypt 哈希，与 app.api.v1.auth.get_password_hash 及 conftest 种子一致。"""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def upsert_user(session, spec: dict) -> str:
    """按 username upsert，返回 'created' 或 'updated'。"""
    user = session.query(User).filter(User.username == spec["username"]).first()
    if user is None:
        session.add(User(
            username=spec["username"],
            password_hash=hash_password(spec["password"]),
            real_name=spec["real_name"],
            role=spec["role"],
            status=spec["status"],
        ))
        session.commit()
        return "created"

    # 已存在：校正关键字段（保证脚本重复运行后账号始终可用）
    user.password_hash = hash_password(spec["password"])
    user.role = spec["role"]
    user.status = spec["status"]
    if spec["real_name"]:
        user.real_name = spec["real_name"]
    session.commit()
    return "updated"


def main() -> int:
    session = SessionLocal()
    try:
        for spec in MOBILE_TEST_USERS:
            action = upsert_user(session, spec)
            role_val = spec["role"].value if hasattr(spec["role"], "value") else spec["role"]
            print(
                f"[OK] {spec['username']:<16} role={role_val:<10} "
                f"status={spec['status']:<8} password={spec['password']} ({action})"
            )
        print(f"\n共 {len(MOBILE_TEST_USERS)} 个移动端联调账号已就绪。")
        return 0
    except Exception as exc:  # pragma: no cover - 脚本错误以非零退出
        print(f"[FAIL] seed 失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())

"""
登录失败锁定机制测试 (D8 爆破防护, spec admin§2.1)

规则:
- 连续5次密码错误 → 锁定 15 分钟 (locked_until = now + 15min), 期间登录返回 423
- 锁定过期 (now >= locked_until) 自动解锁, 走正常流程
- 密码正确 → 清空失败计数与锁定, 记录 last_login_ip
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models.user import User

USERNAME = "admin"
CORRECT_PWD = "admin123"
WRONG_PWD = "definitely-wrong-password"


def _login(client: TestClient, password: str):
    return client.post(
        "/api/v1/auth/login",
        data={"username": USERNAME, "password": password},
    )


class TestAuthLockout:
    """登录失败锁定机制"""

    def test_lockout_after_5_failures(self, client: TestClient, db_session):
        """连续5次错误密码 → 第6次返回423 (账户已锁定)"""
        # 前 5 次错误密码: 每次均 401; 第 5 次触发锁定 (fail_count 归零, locked_until 置值)
        for i in range(5):
            r = _login(client, WRONG_PWD)
            assert r.status_code == 401, f"第{i + 1}次错误密码应返回401, got {r.status_code}: {r.text}"

        # 第 6 次: 账户已被锁定 → 423
        r = _login(client, WRONG_PWD)
        assert r.status_code == 423, f"锁定后应返回423, got {r.status_code}: {r.text}"
        assert "锁定" in r.json().get("detail", "")

    def test_lockout_blocks_even_correct_password(self, client: TestClient, db_session):
        """锁定期间即便密码正确也返回423 (防止锁定后继续试探)"""
        for _ in range(5):
            _login(client, WRONG_PWD)
        # 锁定后用正确密码仍被拒
        r = _login(client, CORRECT_PWD)
        assert r.status_code == 423, f"锁定期间正确密码也应423, got {r.status_code}: {r.text}"

    def test_lockout_expires(self, client: TestClient, db_session):
        """locked_until 设为过去时间 → 锁定过期自动解锁, 正常登录"""
        user = db_session.query(User).filter(User.username == USERNAME).first()
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        r = _login(client, CORRECT_PWD)
        assert r.status_code == 200, f"锁定过期后应正常登录, got {r.status_code}: {r.text}"

    def test_success_resets_counter(self, client: TestClient, db_session):
        """失败3次后成功登录 → fail_count 归零, locked_until 清空"""
        user = db_session.query(User).filter(User.username == USERNAME).first()
        for _ in range(3):
            _login(client, WRONG_PWD)
        db_session.refresh(user)
        assert user.login_fail_count == 3, "3次错误后计数应为3"

        r = _login(client, CORRECT_PWD)
        assert r.status_code == 200
        db_session.refresh(user)
        assert user.login_fail_count == 0, "成功登录后计数应归零"
        assert user.locked_until is None, "成功登录后应清空锁定"

    def test_last_login_ip_recorded(self, client: TestClient, db_session):
        """成功登录后 last_login_ip 非空"""
        user = db_session.query(User).filter(User.username == USERNAME).first()
        user.last_login_ip = None
        db_session.commit()

        r = _login(client, CORRECT_PWD)
        assert r.status_code == 200
        db_session.refresh(user)
        assert user.last_login_ip, "成功登录后应记录 last_login_ip"

    def test_lockout_audit_log(self, client: TestClient, db_session, caplog):
        """达到5次失败触发锁定时, 有 WARNING 级审计日志"""
        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                _login(client, WRONG_PWD)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(USERNAME in r.getMessage() for r in warnings), (
            "触发锁定应产生含用户名的 WARNING 日志, "
            f"实际记录: {[(r.levelname, r.getMessage()) for r in caplog.records]}"
        )

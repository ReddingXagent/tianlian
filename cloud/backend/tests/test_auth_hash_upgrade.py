"""
存量无盐 SHA256 密码 hash 透明升级 — 回归测试 (卡 9e9c519e)

生产 users 表存在遗留的无盐 SHA256 (64位hex) 快hash, 可被 GPU/彩虹表爆破。
登录端点在命中遗留 hash 成功认证后, 应一次性用 bcrypt 重哈希写回, 并保持
登录响应结构不变; verify_password 的 sha256 比较须常量时间。

参照 tests/test_auth.py 的 fixture / 客户端用法。
"""
import hashlib

from fastapi.testclient import TestClient

from app.models.user import User, UserRole


LEGACY_PASSWORD = "legacy_pass_123"


def _sha256_hex(password: str) -> str:
    """与 app/api/v1/auth.py 中遗留逻辑一致的 sha256 hex (小写)。"""
    return hashlib.sha256(password.encode()).hexdigest()


def _make_legacy_user(db_session, username: str) -> User:
    """手工造一个 64 位 hex 无盐 SHA256 hash 的遗留用户。"""
    user = User(
        username=username,
        password_hash=_sha256_hex(LEGACY_PASSWORD),
        real_name=username,
        role=UserRole.ENGINEER,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    # 前置断言: 确实是遗留快hash, 非 bcrypt
    assert len(user.password_hash) == 64
    assert not user.password_hash.startswith("$2")
    return user


def _reload(db_session, username: str) -> User:
    """expire 后重查, 强制走 DB 读取, 证明变更已持久化 (非内存假象)。"""
    db_session.expire_all()
    return db_session.query(User).filter(User.username == username).first()


class TestSha256TransparentUpgrade:
    """登录触发的 SHA256 → bcrypt 透明升级。"""

    def test_legacy_sha256_login_upgrades_to_bcrypt(self, client: TestClient, db_session):
        """① 遗留 sha256 用户登录 200, 且登录后 DB hash 变为 $2 前缀。"""
        user = _make_legacy_user(db_session, "legacy_upgrade_user")

        resp = client.post("/api/v1/auth/login", data={
            "username": user.username,
            "password": LEGACY_PASSWORD,
        })
        assert resp.status_code == 200, f"legacy login failed: {resp.text}"

        upgraded = _reload(db_session, user.username)
        assert upgraded is not None
        assert upgraded.password_hash.startswith("$2"), (
            f"hash 未升级为 bcrypt: {upgraded.password_hash}"
        )
        assert upgraded.password_hash != _sha256_hex(LEGACY_PASSWORD)

    def test_bcrypt_user_hash_not_rewritten(self, client: TestClient, seed_users, db_session):
        """② bcrypt 用户登录行为不变, hash 不被改写。"""
        before = _reload(db_session, "admin").password_hash
        assert before.startswith("$2")

        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200, resp.text

        after = _reload(db_session, "admin").password_hash
        assert after == before, "bcrypt 用户 hash 不应被改写"
        assert after.startswith("$2")

    def test_legacy_sha256_wrong_password_401(self, client: TestClient, db_session):
        """③ 遗留 sha256 用户错密码 401, 且不触发升级。"""
        user = _make_legacy_user(db_session, "legacy_wrong_pw_user")

        resp = client.post("/api/v1/auth/login", data={
            "username": user.username,
            "password": "totally_wrong_password",
        })
        assert resp.status_code == 401

        still_legacy = _reload(db_session, user.username)
        assert not still_legacy.password_hash.startswith("$2"), "错密码不应升级 hash"

    def test_bcrypt_wrong_password_401(self, client: TestClient, seed_users):
        """③ bcrypt 用户错密码 401。"""
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "definitely_not_admin_pw",
        })
        assert resp.status_code == 401

    def test_upgraded_user_can_login_again(self, client: TestClient, db_session):
        """④ 透明升级后, 用同一密码再登录仍 200 (此时走 bcrypt 路径)。"""
        user = _make_legacy_user(db_session, "legacy_relogin_user")

        # 第一次登录: sha256 命中 → 升级为 bcrypt
        r1 = client.post("/api/v1/auth/login", data={
            "username": user.username,
            "password": LEGACY_PASSWORD,
        })
        assert r1.status_code == 200, r1.text
        assert _reload(db_session, user.username).password_hash.startswith("$2")

        # 第二次登录: 同一密码, 现走 bcrypt 路径, 仍应成功
        r2 = client.post("/api/v1/auth/login", data={
            "username": user.username,
            "password": LEGACY_PASSWORD,
        })
        assert r2.status_code == 200, r2.text

        # 第二次登录不应再次改写 hash (已是 bcrypt, 稳定)
        h_after_first = _reload(db_session, user.username).password_hash
        r3 = client.post("/api/v1/auth/login", data={
            "username": user.username,
            "password": LEGACY_PASSWORD,
        })
        assert r3.status_code == 200, r3.text
        h_after_third = _reload(db_session, user.username).password_hash
        assert h_after_first == h_after_third, "bcrypt hash 升级后应稳定, 不应每次登录变化"


class TestVerifyPasswordConstantTime:
    """verify_password 行为正确性 (常量时间比较 + 大小写归一化)。"""

    def test_sha256_match_lower(self):
        from app.api.v1.auth import verify_password
        assert verify_password(LEGACY_PASSWORD, _sha256_hex(LEGACY_PASSWORD)) is True

    def test_sha256_match_upper_normalized(self):
        """大小写归一化: 存储为大写 hex 的 sha256 仍应命中 (保持兼容)。"""
        from app.api.v1.auth import verify_password
        assert verify_password(LEGACY_PASSWORD, _sha256_hex(LEGACY_PASSWORD).upper()) is True

    def test_sha256_mismatch(self):
        from app.api.v1.auth import verify_password
        assert verify_password(LEGACY_PASSWORD, _sha256_hex("a_different_password")) is False

    def test_bcrypt_path_still_works(self):
        import bcrypt
        from app.api.v1.auth import verify_password
        h = bcrypt.hashpw(LEGACY_PASSWORD.encode(), bcrypt.gensalt()).decode()
        assert verify_password(LEGACY_PASSWORD, h) is True
        assert verify_password("wrong", h) is False

"""
auth 模块安全契约与辅助函数单测 (卡 42d650f5)

覆盖 app/api/v1/auth.py 中此前无直接单测的纯函数与安全路径:
  - verify_password: SHA256 / bcrypt 双路径 + 大小写归一化 + 异常容错 (互补
    test_auth_hash_upgrade 的端点级升级行为, 此处聚焦安全契约边界)
  - create_access_token: 正常生成 / 自定义 exp / 过期拒绝
  - generate_reset_token / verify_reset_token: 5 分钟 exp 边界 + 有效/过期/篡改三分支
  - require_role: 角色门拒绝 / admin 旁路 / enum 角色
  - is_public_path: 精确匹配 / 前缀匹配 / 无前缀
  - 短信验证码: 密码学安全随机源 (secrets 而非 MT19937 random) + 6 位范围

端点级流程 (登录/注册/短信全链路/限流/锁定) 已由 test_auth*.py 覆盖, 此处不重复。
generate_reset_token / verify_reset_token 当前无 app 内调用方, 但作为已导出的安全
契约 helper, 锁定其边界行为防未来误接。
"""
import asyncio
import hashlib
import inspect
import types
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.jwt_utils import decode_token, get_active_secret_key
from app.api.v1 import auth as auth_module
from app.api.v1.auth import (
    create_access_token,
    generate_reset_token,
    get_password_hash,
    is_public_path,
    require_role,
    verify_password,
    verify_reset_token,
)
from app.models.user import UserRole


# ─── verify_password ───
class TestVerifyPasswordSecurity:
    """verify_password 安全契约 (互补 test_auth_hash_upgrade 的端点升级测试)。"""

    def test_sha256_legacy_correct(self):
        sha = hashlib.sha256(b"secret123").hexdigest()
        assert verify_password("secret123", sha) is True

    def test_sha256_uppercase_storage_normalized(self):
        """卡 9e9c519e 回归: 遗留大写 hex 存储仍应命中 (常量时间比较 + 归一化)。"""
        sha = hashlib.sha256(b"secret123").hexdigest().upper()
        assert verify_password("secret123", sha) is True

    def test_sha256_wrong_password(self):
        sha = hashlib.sha256(b"secret123").hexdigest()
        assert verify_password("not-the-password", sha) is False

    def test_bcrypt_correct_and_wrong(self):
        h = get_password_hash("mypass")
        assert h.startswith("$2")
        assert verify_password("mypass", h) is True
        assert verify_password("wrongpass", h) is False

    def test_bcrypt_tampered_hash_returns_false(self):
        """篡改过的 $2 hash 无法校验通过, 应回 False 而非抛异常 (fail-closed)。"""
        h = get_password_hash("mypass")
        tampered = h[:-2] + ("aa" if not h.endswith("aa") else "bb")
        assert verify_password("mypass", tampered) is False

    def test_unknown_hash_scheme_returns_false(self):
        """非 sha256 (hex 不匹配) 也非 $2 前缀 → 直接 False, 不抛。"""
        assert verify_password("anything", "plaintext-or-other-scheme") is False


# ─── create_access_token ───
class TestCreateAccessToken:
    def test_generates_decodable_token(self):
        token = create_access_token(data={"sub": "alice", "user_id": 7})
        payload = decode_token(token)
        assert payload["sub"] == "alice"
        assert payload["user_id"] == 7
        assert "exp" in payload
        # 默认 exp 应在未来
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()

    def test_custom_expires_delta_honored(self):
        token = create_access_token(
            data={"sub": "bob"},
            expires_delta=timedelta(seconds=10),
        )
        payload = decode_token(token)
        now = datetime.now(timezone.utc).timestamp()
        # 自定义 10s 窗口: exp 应在 (now, now+60] (留余量)
        assert now < payload["exp"] <= now + 60

    def test_expired_token_rejected(self):
        from jwt.exceptions import ExpiredSignatureError

        token = create_access_token(
            data={"sub": "ghost"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ExpiredSignatureError):
            decode_token(token)


# ─── generate_reset_token / verify_reset_token ───
class TestResetToken:
    def test_roundtrip(self):
        token = generate_reset_token("13800138000", sms_record_id=42)
        assert verify_reset_token(token) == {"phone": "13800138000", "sms_id": 42}

    def test_generated_token_exp_is_five_minutes(self):
        """文档契约: 有效期 5 分钟 (JWT exp 截断为整秒, 留 ±2s 余量)。"""
        before = datetime.now(timezone.utc)
        token = generate_reset_token("13900000000", sms_record_id=1)
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta = (exp - before).total_seconds()
        assert 298 <= delta <= 302

    def test_exp_boundary_valid_just_inside(self):
        """边界前 (exp 尚在未来 2s): 仍有效。"""
        token = jwt_encode_reset(exp_delta=timedelta(seconds=2))
        assert verify_reset_token(token)["phone"] == "138"

    def test_exp_boundary_expired_just_outside(self):
        """边界后 (exp 已过 1s): 过期 → 400「重置令牌已过期」。"""
        token = jwt_encode_reset(exp_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException) as exc:
            verify_reset_token(token)
        assert exc.value.status_code == 400
        assert "过期" in exc.value.detail

    def test_tampered_signature_rejected(self):
        """非可信密钥签名 → DecodeError → 400「无效的重置令牌」。"""
        token = jwt.encode(
            {"sub": "138", "sms_id": 1, "purpose": "password_reset",
             "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
            "wrong-secret-key-not-in-use",
            algorithm=settings.ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc:
            verify_reset_token(token)
        assert exc.value.status_code == 400
        assert "无效" in exc.value.detail

    def test_wrong_purpose_rejected(self):
        """purpose != password_reset → 400「无效的重置令牌」(防 access token 复用)。"""
        token = jwt.encode(
            {"sub": "138", "sms_id": 1, "purpose": "login",
             "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
            get_active_secret_key(),
            algorithm=settings.ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc:
            verify_reset_token(token)
        assert exc.value.status_code == 400
        assert "无效" in exc.value.detail


def jwt_encode_reset(exp_delta: timedelta) -> str:
    """用 active key 签一个 password_reset purpose 的 token, exp = now + exp_delta。"""
    return jwt.encode(
        {"sub": "138", "sms_id": 1, "purpose": "password_reset",
         "exp": datetime.now(timezone.utc) + exp_delta},
        get_active_secret_key(),
        algorithm=settings.ALGORITHM,
    )


# ─── require_role ───
class TestRequireRole:
    """require_role 角色门 (直接驱动内部 check_role 协程, 覆盖拒绝/旁路)。"""

    @staticmethod
    def _user(role) -> types.SimpleNamespace:
        return types.SimpleNamespace(role=role, username="x", id=1)

    @staticmethod
    def _call(roles, user):
        check = require_role(*roles)
        return asyncio.run(check(user))

    def test_matching_role_passes(self):
        u = self._user("engineer")
        assert self._call(("engineer",), u) is u

    def test_admin_always_passes_when_not_listed(self):
        """ADMIN 角色始终旁路, 即使不在允许列表。"""
        u = self._user("admin")
        assert self._call(("engineer",), u) is u

    def test_super_admin_always_passes(self):
        u = self._user("super_admin")
        assert self._call(("engineer",), u) is u

    def test_wrong_role_rejected_403(self):
        u = self._user("viewer")
        with pytest.raises(HTTPException) as exc:
            self._call(("engineer",), u)
        assert exc.value.status_code == 403

    def test_enum_role_member_resolves(self):
        """UserRole(str, Enum) 成员经 isinstance(str) 分支正确解析。"""
        u = self._user(UserRole.ENGINEER)
        assert self._call(("engineer",), u) is u

    def test_case_insensitive_role_match(self):
        u = self._user("Engineer")
        assert self._call(("ENGINEER",), u) is u


# ─── is_public_path ───
class TestIsPublicPath:
    @pytest.mark.parametrize("path", [
        "/api/v1/auth/login",        # 精确
        "/api/v1/auth/sms/send",     # 精确
        "/api/v1/auth/password-reset",
        "/api/v1/auth/refresh",
        "/api/v1/health",            # 精确 (健康检查)
        "/api/v1/livez",
        "/api/v1/ping",
        "/api/v1/scan/anything",     # 前缀
        "/api/v1/telemetry",         # 前缀
        "/api/v1/pod/register",      # 前缀
        "/api/v1/cross/query",       # 前缀
        "/api/v1/alert-webhook",     # 前缀
    ])
    def test_public_paths(self, path):
        assert is_public_path(path) is True

    @pytest.mark.parametrize("path", [
        "/api/v1/auth/me",      # /auth/* 仅部分精确白名单, me 非公开
        "/api/v1/users",
        "/api/v1/devices/123",
        "/api/v1/business/stations",
        "/api/v1/business/payments/notify-is-not-this",  # 精确路径不在, 仅 notify 公开
    ])
    def test_non_public_paths(self, path):
        assert is_public_path(path) is False

    def test_strips_api_prefix(self):
        """不带 /api/v1 前缀也能判 (rel 回退原样)。"""
        assert is_public_path("/auth/login") is True
        assert is_public_path("/scan/x") is True
        assert is_public_path("/users") is False


# ─── 短信验证码: 密码学安全随机源 ───
class TestSmsCodeSecurity:
    def test_source_uses_secrets_not_random(self):
        """源码级守卫: sms 验证码必须用 secrets (CSPRNG), 不得用 random (MT19937)。"""
        source = inspect.getsource(auth_module)
        assert "import secrets" in source
        assert "secrets.randbelow" in source
        assert "random.randint" not in source

    def test_generated_code_is_six_digits_in_range(self, client, db_session):
        """生成的验证码为 6 位纯数字, 落在 [100000, 999999] (与原 random 范围等价)。"""
        from app.models.sms_verification import SmsVerificationCode

        phone = "13700420001"
        resp = client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "login"})
        assert resp.status_code == 200, resp.text
        rec = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0,
        ).first()
        assert rec is not None, "验证码应已落库"
        code = rec.code
        assert len(code) == 6
        assert code.isdigit()
        assert 100000 <= int(code) <= 999999

"""密码 >72 字节 bcrypt 5.0 防御 (卡 d827fd9a)

bcrypt 5.0.0 的 hashpw/checkpw 对 >72 字节密码抛 ValueError → 注册/改密 500。
入口防御: get_password_hash/verify_password + 各 schema pydantic validator
统一 400, 错误消息含「密码长度超过72字节限制」, 禁止静默截断。
"""
import pytest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.api.v1.auth import (
    BCRYPT_MAX_PASSWORD_BYTES,
    check_password_byte_length,
    get_password_hash,
    verify_password,
)


# ─── 边界构造 ────────────────────────────────────────────────────────────────
P_72_ASCII = "a" * 72            # 恰好 72 字节 → 通过
P_73_ASCII = "a" * 73            # 73 字节 → 拒绝
P_24_HAN = "密" * 24             # 24 汉字 × 3B = 72 字节 → 通过
P_25_HAN = "密" * 25             # 25 汉字 × 3B = 75 字节 → 拒绝 (字符数 25 < 73)


# ─── 单元: 共享校验 helper + 哈希/校验守卫 ───────────────────────────────────
class TestByteLengthHelpers:
    def test_72_ascii_passes(self):
        assert check_password_byte_length(P_72_ASCII) == P_72_ASCII

    def test_24_han_exactly_72_bytes_passes(self):
        assert check_password_byte_length(P_24_HAN) == P_24_HAN

    def test_73_ascii_rejected_400(self):
        with pytest.raises(HTTPException) as e:
            check_password_byte_length(P_73_ASCII)
        assert e.value.status_code == 400
        assert "密码长度超过72字节限制" in e.value.detail

    def test_25_han_75_bytes_rejected_multibyte_not_charcount(self):
        # 字符数仅 25, 但 UTF-8 字节 75 > 72 —— 证明校验是字节级而非字符级
        with pytest.raises(HTTPException) as e:
            check_password_byte_length(P_25_HAN)
        assert e.value.status_code == 400
        assert "密码长度超过72字节限制" in e.value.detail

    def test_get_password_hash_rejects_over_limit(self):
        with pytest.raises(HTTPException) as e:
            get_password_hash(P_25_HAN)
        assert e.value.status_code == 400
        assert "密码长度超过72字节限制" in e.value.detail

    def test_get_password_hash_accepts_72_bytes_roundtrip(self):
        h = get_password_hash(P_24_HAN)
        assert h.startswith("$2")
        assert verify_password(P_24_HAN, h) is True

    def test_verify_password_bcrypt_over_limit_400(self):
        h = get_password_hash("short")
        with pytest.raises(HTTPException) as e:
            verify_password(P_25_HAN, h)
        assert e.value.status_code == 400

    def test_verify_password_72_bytes_ok(self):
        h = get_password_hash(P_72_ASCII)
        assert verify_password(P_72_ASCII, h) is True
        assert verify_password("wrong", h) is False

    def test_no_silent_truncation(self):
        # 若静默截断, 72 字节密码的 hash 用 73 字节密码也能验过 —— 必须防御
        h = get_password_hash(P_72_ASCII)
        with pytest.raises(HTTPException):
            verify_password(P_73_ASCII, h)


# ─── 集成: 4 条写路径全返回 400 ──────────────────────────────────────────────
class TestRegisterPathTooLong:
    def test_auth_register_25_han_400(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "pwlen_user1",
            "password": P_25_HAN,
            "real_name": "长度测试",
            "role": "technician",
        })
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_auth_register_73_ascii_400(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "pwlen_user2",
            "password": P_73_ASCII,
            "real_name": "长度测试",
            "role": "technician",
        })
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_auth_register_24_han_boundary_200(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "pwlen_user3",
            "password": P_24_HAN,
            "real_name": "边界通过",
            "role": "technician",
        })
        assert r.status_code == 200, r.text

    def test_auth_register_72_ascii_boundary_200(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "pwlen_user4",
            "password": P_72_ASCII,
            "real_name": "边界通过",
            "role": "technician",
        })
        assert r.status_code == 200, r.text


class TestPasswordResetPath:
    def _seed_reset_code(self, client):
        """为 admin 手机号种一条有效 reset 验证码, 返回 code。"""
        from app.models.sms_verification import SmsVerificationCode
        code = "123456"
        s = SmsVerificationCode(
            phone="13800000000",
            code=code,
            purpose="reset",
            used=0,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        client._sesh.add(s)
        client._sesh.commit()
        # 绑定 admin 手机号 (admin 由 conftest 模板种入)
        from app.models.user import User
        admin = client._sesh.query(User).filter(User.username == "admin").first()
        admin.phone = "13800000000"
        client._sesh.commit()
        return code

    def test_password_reset_75_bytes_400_not_500(self, client):
        code = self._seed_reset_code(client)
        r = client.post("/api/v1/auth/password-reset", json={
            "phone": "13800000000",
            "code": code,
            "new_password": P_25_HAN,
        })
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_password_reset_73_ascii_400(self, client):
        code = self._seed_reset_code(client)
        r = client.post("/api/v1/auth/password-reset", json={
            "phone": "13800000000",
            "code": code,
            "new_password": P_73_ASCII,
        })
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())


class TestEngineerCreatePath:
    def test_engineer_create_25_han_400(self, client):
        r = client.post("/api/v1/engineers", json={
            "name": "长密码工程师",
            "password": P_25_HAN,
            "level": "junior",
        })
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_engineer_create_24_han_boundary_ok(self, client):
        r = client.post("/api/v1/engineers", json={
            "name": "边界工程师",
            "password": P_24_HAN,
            "level": "junior",
        })
        assert r.status_code in (200, 201), r.text


class TestEnterpriseRegisterPath:
    def _payload(self, password):
        return {
            "company_name": "长密码企业有限公司",
            "credit_code": "91330100MA27X8971K",
            "contact_name": "联系人",
            "contact_phone": "13900001111",
            "password": password,
            "agreed_to_terms": True,
        }

    def test_enterprise_register_25_han_400(self, anon_client):
        r = anon_client.post(
            "/api/v1/auth/register/enterprise", json=self._payload(P_25_HAN)
        )
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_enterprise_register_73_ascii_400(self, anon_client):
        r = anon_client.post(
            "/api/v1/auth/register/enterprise", json=self._payload(P_73_ASCII)
        )
        assert r.status_code == 400
        assert "密码长度超过72字节限制" in str(r.json())

    def test_enterprise_register_24_han_boundary_not_500(self, anon_client):
        r = anon_client.post(
            "/api/v1/auth/register/enterprise", json=self._payload(P_24_HAN)
        )
        # 边界值须通过长度防御 (可能因其他业务校验 4xx, 但绝不能 500)
        assert r.status_code != 500, r.text

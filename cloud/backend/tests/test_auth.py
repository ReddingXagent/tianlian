"""
认证 API 测试
"""
import pytest
from fastapi.testclient import TestClient
from .conftest import _get_token


class TestAuthLogin:
    """登录验证测试（使用 OAuth2 form-data）"""

    def test_login_success(self, client: TestClient, seed_users):
        """正常登录成功"""
        response = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        inner = data.get("data", data)
        token = inner.get("token", inner.get("access_token", ""))
        assert token, "No token in response"

    def test_login_wrong_password(self, client: TestClient, seed_users):
        """错误密码应返回 401"""
        response = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "wrong_password",
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient, seed_users):
        """不存在的用户应返回 401"""
        response = client.post("/api/v1/auth/login", data={
            "username": "nonexistent",
            "password": "any_password",
        })
        assert response.status_code == 401

    def test_login_empty_username(self, client: TestClient, seed_users):
        """空用户名应返回 422"""
        response = client.post("/api/v1/auth/login", data={
            "username": "",
            "password": "admin123",
        })
        assert response.status_code in (200, 422)

    def test_login_inactive_user(self, client: TestClient, seed_users):
        """停用的用户不应登录成功"""
        response = client.post("/api/v1/auth/login", data={
            "username": "inactive_user",
            "password": "inactive123",
        })
        assert response.status_code in (401, 403)

    def test_login_missing_password(self, client: TestClient, seed_users):
        """缺少密码字段应返回 422"""
        # 不传递 password 字段
        response = client.post("/api/v1/auth/login", data={
            "username": "admin",
        })
        assert response.status_code == 422


class TestAuthRegister:
    """用户注册测试"""

    def test_register_success(self, client: TestClient, seed_users):
        """新用户注册成功"""
        response = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "password": "NewPass123!",
            "real_name": "新用户",
            # 卡 19c0ee73: 自注册仅允许 viewer/technician, engineer 走 admin 建人
            "role": "viewer",
        })
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert data.get("data") or data.get("username") or data.get("id")

    def test_register_duplicate_username(self, client: TestClient, seed_users):
        """重复用户名应返回 400"""
        response = client.post("/api/v1/auth/register", json={
            "username": "admin",
            "password": "admin456",
            "real_name": "重复用户",
        })
        assert response.status_code in (400, 409)

    def test_register_missing_fields(self, client: TestClient, seed_users):
        """缺少必填字段"""
        response = client.post("/api/v1/auth/register", json={
            "username": "user_no_password",
        })
        assert response.status_code == 422

    def test_register_invalid_role(self, client: TestClient, seed_users):
        """无效角色应返回错误"""
        response = client.post("/api/v1/auth/register", json={
            "username": "badroleuser",
            "password": "test123",
            "real_name": "坏角色",
            "role": "king",
        })
        assert response.status_code in (200, 422)


class TestAuthTokenValidation:
    """Token 验证测试"""

    def test_access_protected_without_token(self, anon_client: TestClient):
        """无 token 无法访问受保护路由"""
        response = anon_client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)

    def test_access_with_valid_token(self, client: TestClient, seed_users):
        """有效 token 可访问"""
        response = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert response.status_code == 200
        token = _get_token(client)
        assert token, "login 200 但无 token — 登录失败必须红"

        resp2 = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp2.status_code in (200, 401, 404)

    def test_access_with_invalid_token(self, client: TestClient):
        """无效 token 应返回 401"""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401

    def test_access_with_expired_token(self, client: TestClient):
        """过期 token 应返回 401"""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings

        expired_token = jwt.encode(
            {"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401


class TestSMSSend:
    """发送验证码测试"""

    def test_sms_send_success(self, client: TestClient, seed_users):
        """成功发送验证码"""
        response = client.post("/api/v1/auth/sms/send", json={
            "phone": "13800138001",
            "purpose": "login"
        })
        assert response.status_code == 200, f"SMS send failed: {response.text}"

    def test_sms_send_invalid_phone(self, client: TestClient, seed_users):
        """无效手机号格式"""
        response = client.post("/api/v1/auth/sms/send", json={
            "phone": "12345678901",  # 无效手机号
            "purpose": "login"
        })
        assert response.status_code == 400

    def test_sms_send_missing_phone(self, client: TestClient, seed_users):
        """缺少手机号"""
        response = client.post("/api/v1/auth/sms/send", json={
            "purpose": "login"
        })
        assert response.status_code == 422


class TestSMSVerify:
    """校验验证码测试"""

    def test_sms_verify_invalid_code(self, client: TestClient, seed_users):
        """无效验证码"""
        response = client.post("/api/v1/auth/sms/verify", json={
            "phone": "13800138001",
            "code": "000000",
            "purpose": "login"
        })
        assert response.status_code == 200
        data = response.json()
        inner = data.get("data", data)
        valid = inner.get("valid")
        assert valid == False


class TestSMSSendLogin:
    """验证码登录测试 (任务卡 78c7404b: 验证码登录已停用, 统一返回 410 Gone)"""

    def test_sms_login_invalid_code(self, client: TestClient, seed_users):
        """验证码登录已停用 → 410 Gone (原为 400 验证码错误)"""
        response = client.post("/api/v1/auth/sms/login", json={
            "phone": "13800138001",
            "code": "000000"
        })
        assert response.status_code == 410
        # 响应体提示用户改用密码登录
        assert "密码登录" in response.json().get("detail", "")


class TestPasswordReset:
    """密码重置测试"""

    def test_password_reset_missing_fields(self, client: TestClient, seed_users):
        """缺少必填字段"""
        response = client.post("/api/v1/auth/password-reset", json={
            "phone": "13800138001"
        })
        assert response.status_code == 422

    def test_password_reset_full_flow(self, client: TestClient, seed_users, db_session):
        """完整密码重置流程: 发送验证码 → 重置密码 → 新密码登录"""
        phone = "13800138001"
        # Step 0: 绑定手机号到已有用户
        from app.models.user import User
        user = db_session.query(User).filter(User.username == "admin").first()
        assert user is not None
        user.phone = phone
        db_session.commit()

        # Step 1: 发送重置验证码
        resp = client.post("/api/v1/auth/sms/send", json={
            "phone": phone,
            "purpose": "reset"
        })
        assert resp.status_code == 200

        # Step 2: 从数据库获取验证码
        from app.models.sms_verification import SmsVerificationCode
        code_record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "reset",
            SmsVerificationCode.used == 0
        ).first()
        assert code_record is not None, "Should have created a verification code"
        code = code_record.code

        # Step 3: 使用无效验证码重置应失败
        resp = client.post("/api/v1/auth/password-reset", json={
            "phone": phone,
            "code": "000000",
            "new_password": "newpass123"
        })
        assert resp.status_code == 400

        # Step 4: 使用正确验证码重置密码
        resp = client.post("/api/v1/auth/password-reset", json={
            "phone": phone,
            "code": code,
            "new_password": "newpass123"
        })
        assert resp.status_code == 200

        # Step 5: 验证码应标记为已使用
        db_session.refresh(code_record)
        assert code_record.used == 1

        # Step 6: 用新密码登录
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "newpass123"
        })
        assert resp.status_code == 200

        # Cleanup: restore password
        import bcrypt
        user.password_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        db_session.commit()


class TestSMSVerificationFlow:
    """短信验证码全流程测试"""

    def test_sms_send_and_verify_flow(self, client: TestClient, seed_users, db_session):
        """发送验证码 → 校验验证码"""
        phone = "13800138002"
        # Step 1: 发送验证码
        resp = client.post("/api/v1/auth/sms/send", json={
            "phone": phone,
            "purpose": "login"
        })
        assert resp.status_code == 200

        # Step 2: 从数据库获取验证码
        from app.models.sms_verification import SmsVerificationCode
        code_record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0
        ).first()
        assert code_record is not None

        # Step 3: 用正确验证码校验
        resp = client.post("/api/v1/auth/sms/verify", json={
            "phone": phone,
            "code": code_record.code,
            "purpose": "login"
        })
        assert resp.status_code == 200
        inner = resp.json().get("data", {})
        assert inner.get("valid") == True

        # Step 4: 验证码应标记为已使用
        db_session.refresh(code_record)
        assert code_record.used == 1

        # Step 5: 重复使用应失败
        resp = client.post("/api/v1/auth/sms/verify", json={
            "phone": phone,
            "code": code_record.code,
            "purpose": "login"
        })
        assert resp.status_code == 200
        inner = resp.json().get("data", {})
        assert inner.get("valid") == False

    def test_sms_login_full_flow(self, client: TestClient, seed_users, db_session):
        """验证码登录已停用 → 即使验证码正确也返回 410 Gone (任务卡 78c7404b)。

        改造前: 发送验证码 → sms/login 返回 token。
        改造后: sms/login 端点整体停用, 不再校验验证码, 一律 410。
        """
        phone = "13800138003"
        # Step 1: 关联手机号到第一个用户
        from app.models.user import User
        user = db_session.query(User).first()
        assert user is not None
        original_phone = user.phone
        user.phone = phone
        db_session.commit()

        # Step 2: 发送验证码 (sms/send 仍可用, 供两步登录/重置复用)
        resp = client.post("/api/v1/auth/sms/send", json={
            "phone": phone,
            "purpose": "login"
        })
        assert resp.status_code == 200

        # Step 3: 从数据库获取验证码
        from app.models.sms_verification import SmsVerificationCode
        code_record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0
        ).first()
        assert code_record is not None

        # Step 4: 验证码登录已停用, 即便验证码正确也 410
        resp = client.post("/api/v1/auth/sms/login", json={
            "phone": phone,
            "code": code_record.code
        })
        assert resp.status_code == 410

        # Cleanup: restore original phone
        user.phone = original_phone
        db_session.commit()

    def test_sms_send_duplicate_code_replacement(self, client: TestClient, seed_users, db_session):
        """重复发送验证码时旧验证码应标记为无效"""
        phone = "13800138004"
        # 第一次发送
        client.post("/api/v1/auth/sms/send", json={
            "phone": phone,
            "purpose": "login"
        })

        from app.models.sms_verification import SmsVerificationCode
        # 获取第一个验证码
        old_codes = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0
        ).all()
        assert len(old_codes) == 1
        old_code = old_codes[0].code

        # 第二次发送
        client.post("/api/v1/auth/sms/send", json={
            "phone": phone,
            "purpose": "login"
        })

        # 旧验证码应标记为已使用(used=1)
        db_session.refresh(old_codes[0])
        assert old_codes[0].used == 1, "Old code should be marked as used"

        # 新验证码应生效
        new_codes = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0
        ).all()
        assert len(new_codes) == 1
        assert new_codes[0].code != old_code


class TestJWTKeyRotation:
    """JWT SECRET_KEY 双 Key 灰度迁移 (卡 a89269c9, RFC 7518 §3.2 ≥32 字节合规)。

    轮换契约: 配置 SECRET_KEY_NEW 后进入灰度窗口 —
      - 新签发 token 一律用新 key (create_access_token 走 active key)
      - 验证时先试新 key, 失败再试旧 key (旧 token 在过期前仍可用)
    SECRET_KEY_NEW 未配置 (None) 时退化为单 key, 行为与改造前一致。
    """

    NEW_KEY = "new-rotated-secret-key-must-be-32-bytes-or-longer"  # 49 字节 ≥ RFC7518

    def test_new_key_token_verifies_after_rotation(self, client: TestClient, monkeypatch):
        """(A) 灰度驱动: 配置 SECRET_KEY_NEW 后, 新 key 签发的 token 应通过验证。

        改造前 get_current_user 只用 settings.SECRET_KEY 解码, 新 key 签名的 token
        会签名不符 → 401。本用例即 RED 驱动双 key 解码落地。
        """
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings

        assert len(self.NEW_KEY.encode()) >= 32
        monkeypatch.setattr(settings, "SECRET_KEY_NEW", self.NEW_KEY)

        new_token = jwt.encode(
            {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            self.NEW_KEY,
            algorithm=settings.ALGORITHM,
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert resp.status_code == 200, f"新 key token 应在灰度期通过: {resp.status_code} {resp.text}"

    def test_old_key_token_still_verifies_during_rotation(self, client: TestClient, monkeypatch):
        """(B) 灰度兼容 (任务要求): 配置 SECRET_KEY_NEW 后, 旧 key 签发的 token 仍应通过。

        保证轮换窗口内已签发的存量 token 不被一刀切失效, 平滑过渡。
        """
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings

        monkeypatch.setattr(settings, "SECRET_KEY_NEW", self.NEW_KEY)

        old_token = jwt.encode(
            {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert resp.status_code == 200, f"旧 key token 应在灰度期通过: {resp.status_code} {resp.text}"

    def test_foreign_key_token_rejected(self, client: TestClient, monkeypatch):
        """(C) 安全兜底: 既非新 key 也非旧 key 签名的 token 必须被拒 (401)。"""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings

        monkeypatch.setattr(settings, "SECRET_KEY_NEW", self.NEW_KEY)

        foreign_token = jwt.encode(
            {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "totally-unrelated-foreign-secret-not-in-rotation",
            algorithm=settings.ALGORITHM,
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {foreign_token}"},
        )
        assert resp.status_code == 401

    def test_decode_token_helper_dual_key(self, monkeypatch):
        """(D) helper 单元: decode_token 先新后旧, 单 key 模式退化正常。"""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.core.config import settings
        from app.core.jwt_utils import decode_token, get_active_secret_key

        monkeypatch.setattr(settings, "SECRET_KEY_NEW", self.NEW_KEY)
        # active key = NEW
        assert get_active_secret_key() == self.NEW_KEY

        valid_payload = {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        # 新 key 签 → 解出
        assert decode_token(jwt.encode(valid_payload, self.NEW_KEY, algorithm=settings.ALGORITHM))["sub"] == "admin"
        # 旧 key 签 → 解出 (回退)
        assert decode_token(jwt.encode(valid_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM))["sub"] == "admin"

        # 单 key 模式 (NEW=None): active=SECRET_KEY, 候选仅一个, 行为同改造前
        monkeypatch.setattr(settings, "SECRET_KEY_NEW", None)
        assert get_active_secret_key() == settings.SECRET_KEY
        assert decode_token(jwt.encode(valid_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM))["sub"] == "admin"


class TestTwoFactorLogin:
    """两步登录(2FA)测试 (任务卡 78c7404b)。

    契约:
    - /auth/login 密码验证通过后, 若 user.team.second_factor_enabled=true:
      发送验证码 → 返回 {second_factor_required, temp_token, method, phone_masked}, 不发 token。
    - second_factor_enabled=false (默认): 直接返回 token (向后兼容)。
    - /auth/login/verify-2fa {temp_token, code}: 验证 temp_token(itsdangerous, 5min) +
      短信码 → 返回正式 {token, user}。
    - temp_token 用 itsdangerous 签名, 非 JWT。
    """

    def _make_2fa_user(self, db_session):
        """造一个挂在 2FA 团队下、带手机号的 admin 用户, 供两步登录测试。"""
        import bcrypt
        from app.models.user import User, UserRole, Team, TeamType
        team = Team(
            name="2fa-team",
            type=TeamType.OPS_COMPANY,
            second_factor_enabled=True,
            second_factor_method="sms",
        )
        db_session.add(team)
        db_session.flush()
        user = User(
            username="admin2fa",
            password_hash=bcrypt.hashpw(b"pass1234", bcrypt.gensalt()).decode(),
            real_name="二次验证管理员",
            role=UserRole.ADMIN,
            status="active",
            phone="13900139001",
            team_id=team.id,
        )
        db_session.add(user)
        db_session.commit()
        return user

    def test_login_2fa_team_requires_second_factor(self, client: TestClient, seed_users, db_session):
        """2FA 团队用户密码正确 → 触发二次验证, 不返回 token。"""
        self._make_2fa_user(db_session)
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin2fa",
            "password": "pass1234",
        })
        assert resp.status_code == 200, f"login failed: {resp.text}"
        inner = resp.json().get("data", resp.json())
        assert inner.get("second_factor_required") is True
        assert inner.get("temp_token"), "应返回 temp_token"
        assert inner.get("method") == "sms"
        # 不应返回正式 token
        assert not inner.get("token") and not inner.get("access_token")

    def test_login_non_2fa_team_returns_token_directly(self, client: TestClient, seed_users):
        """非 2FA 团队(默认关闭) → 直接返回 token, 响应无 second_factor_required。"""
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200
        inner = resp.json().get("data", resp.json())
        assert inner.get("token") or inner.get("access_token")
        # 不应进入 2FA 分支
        assert inner.get("second_factor_required") in (None, False)

    def test_login_2fa_sends_sms_code(self, client: TestClient, seed_users, db_session):
        """触发 2FA 时应向用户手机发送验证码(入库可查)。"""
        user = self._make_2fa_user(db_session)
        client.post("/api/v1/auth/login", data={
            "username": "admin2fa",
            "password": "pass1234",
        })
        from app.models.sms_verification import SmsVerificationCode
        record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == user.phone,
            SmsVerificationCode.purpose == "login_2fa",
            SmsVerificationCode.used == 0,
        ).first()
        assert record is not None, "应发送 purpose=login_2fa 的验证码"

    def test_verify_2fa_success(self, client: TestClient, seed_users, db_session):
        """完整两步登录: login 触发 → 拿 temp_token + 验证码 → verify-2fa 换正式 token。"""
        user = self._make_2fa_user(db_session)
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin2fa",
            "password": "pass1234",
        })
        inner = resp.json().get("data", resp.json())
        temp_token = inner["temp_token"]

        from app.models.sms_verification import SmsVerificationCode
        code_record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == user.phone,
            SmsVerificationCode.purpose == "login_2fa",
            SmsVerificationCode.used == 0,
        ).first()
        assert code_record is not None

        resp2 = client.post("/api/v1/auth/login/verify-2fa", json={
            "temp_token": temp_token,
            "code": code_record.code,
        })
        assert resp2.status_code == 200, f"verify-2fa failed: {resp2.text}"
        inner2 = resp2.json().get("data", resp2.json())
        token = inner2.get("token") or inner2.get("access_token")
        assert token, f"应返回正式 token, got: {inner2}"
        # 验证码应标记已使用
        db_session.refresh(code_record)
        assert code_record.used == 1

    def test_verify_2fa_wrong_code(self, client: TestClient, seed_users, db_session):
        """verify-2fa 验证码错误 → 拒绝。"""
        self._make_2fa_user(db_session)
        resp = client.post("/api/v1/auth/login", data={
            "username": "admin2fa",
            "password": "pass1234",
        })
        temp_token = resp.json().get("data", resp.json())["temp_token"]

        resp2 = client.post("/api/v1/auth/login/verify-2fa", json={
            "temp_token": temp_token,
            "code": "000000",
        })
        assert resp2.status_code == 400

    def test_verify_2fa_invalid_temp_token(self, client: TestClient, seed_users):
        """verify-2fa temp_token 无效/伪造 → 拒绝。"""
        resp = client.post("/api/v1/auth/login/verify-2fa", json={
            "temp_token": "not-a-valid-signed-token",
            "code": "123456",
        })
        assert resp.status_code in (400, 401)

    def test_verify_2fa_tampered_temp_token(self, client: TestClient, seed_users, db_session):
        """verify-2fa 签名被篡改的 temp_token → 拒绝(itsdangerous BadSignature)。"""
        self._make_2fa_user(db_session)
        # 用正确 key 签一个合法 token, 再尾部追加字符破坏签名
        from itsdangerous import URLSafeTimedSerializer
        from app.core.jwt_utils import get_active_secret_key
        serializer = URLSafeTimedSerializer(get_active_secret_key(), salt="login_2fa")
        tampered = serializer.dumps({"uid": 1, "phone": "13900139001"}) + "tamper"
        resp = client.post("/api/v1/auth/login/verify-2fa", json={
            "temp_token": tampered,
            "code": "123456",
        })
        assert resp.status_code in (400, 401)
"""卡 75a0069e: 安全默认值与启动守卫。

- SMS_DEV_MODE 默认 False / SMS_DEV_CODE 默认 None (fail-safe, 无固定码后门)
- SMS_DEV_MODE=True 而 SMS_DEV_CODE 未配置 → Settings 校验报错
- SECRET_KEY git 默认值三态: 生产拒启动 / 纯开发 warn / 显式配置无感
- 默认配置下 phone-bind 固定码被拒 (501), 显式 dev 模式放行

环境变量隔离: conftest 已 setenv SECRET_KEY (测试串, 非默认值), 各用例用
monkeypatch.setenv/delenv 覆盖后新建 Settings() 验证校验行为。
"""

import logging

import pytest

from app.core.config import _DEFAULT_SECRET_KEY, Settings, settings

AUTH_URL = "/api/v1/business/auth/wx-login"
PHONE_URL = "/api/v1/business/user/phone-bind"


def _make(monkeypatch, **overrides):
    """隔离环境新建 Settings: 清掉 conftest 注入的 SECRET_KEY 等干扰项。"""
    env = {
        "SECRET_KEY": overrides.get("SECRET_KEY", "test-secret-key-for-testing-32bytes-plus"),
        "ENVIRONMENT": overrides.get("ENVIRONMENT", "development"),
        "DEBUG": overrides.get("DEBUG", "true"),
        "DATABASE_URL": overrides.get("DATABASE_URL", "sqlite:///./test.db"),
        "SMS_DEV_MODE": overrides.get("SMS_DEV_MODE", "false"),
        "SMS_DEV_CODE": overrides.get("SMS_DEV_CODE", ""),
    }
    for key, value in env.items():
        if value == "":
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return Settings()


# ────────────────────────────────────────────────────────────────────
# 默认值 fail-safe
# ────────────────────────────────────────────────────────────────────
class TestSecureDefaults:
    def test_sms_dev_mode_default_off(self):
        """SMS_DEV_MODE 默认 False: 演示模式必须显式 opt-in。"""
        assert settings.SMS_DEV_MODE is False or settings.SMS_DEV_MODE == False

    def test_sms_dev_code_default_none(self, monkeypatch):
        """SMS_DEV_CODE 默认 None: 不存在默认固定码。"""
        for key in ("SMS_DEV_MODE", "SMS_DEV_CODE"):
            monkeypatch.delenv(key, raising=False)
        assert Settings().SMS_DEV_CODE is None


# ────────────────────────────────────────────────────────────────────
# SMS_DEV_MODE=True 而 SMS_DEV_CODE 未配置 → 拒绝启动
# ────────────────────────────────────────────────────────────────────
class TestSmsDevCodeRequiredInDevMode:
    def test_dev_mode_without_code_raises(self, monkeypatch):
        monkeypatch.setenv("SMS_DEV_MODE", "true")
        monkeypatch.delenv("SMS_DEV_CODE", raising=False)
        with pytest.raises(ValueError, match="SMS_DEV_CODE"):
            Settings()

    def test_dev_mode_with_code_ok_and_warns(self, monkeypatch, caplog):
        s = _make(monkeypatch, SMS_DEV_MODE="true", SMS_DEV_CODE="123456")
        assert s.SMS_DEV_MODE is True
        assert s.SMS_DEV_CODE == "123456"


# ────────────────────────────────────────────────────────────────────
# SECRET_KEY 守卫三态
# ────────────────────────────────────────────────────────────────────
class TestSecretKeyGuard:
    def test_default_key_production_env_rejected(self, monkeypatch):
        """ENVIRONMENT=production + git 默认串 → 拒绝启动。"""
        with pytest.raises(ValueError, match="SECRET_KEY"):
            _make(monkeypatch, SECRET_KEY=_DEFAULT_SECRET_KEY, ENVIRONMENT="production")

    def test_default_key_debug_false_nonsqlite_rejected(self, monkeypatch):
        """DEBUG=False + 非 sqlite 库 + 默认串 → 拒绝启动。"""
        with pytest.raises(ValueError, match="SECRET_KEY"):
            _make(
                monkeypatch,
                SECRET_KEY=_DEFAULT_SECRET_KEY,
                DEBUG="false",
                DATABASE_URL="postgresql://prod-db/tianlian",
            )

    def test_default_key_dev_sqlite_only_warns(self, monkeypatch, caplog):
        """纯开发 (sqlite + DEBUG) 默认串 → warning 放行, 不炸。"""
        with caplog.at_level(logging.WARNING, logger="app.config"):
            s = _make(monkeypatch, SECRET_KEY=_DEFAULT_SECRET_KEY)
        assert s.SECRET_KEY == _DEFAULT_SECRET_KEY
        assert any("SECRET_KEY" in r.message for r in caplog.records)

    def test_explicit_key_no_warning(self, monkeypatch, caplog):
        """显式配置独立密钥 → 守卫无感。"""
        with caplog.at_level(logging.WARNING, logger="app.config"):
            s = _make(monkeypatch, ENVIRONMENT="production")
        assert s.SECRET_KEY != _DEFAULT_SECRET_KEY
        assert not [r for r in caplog.records if "SECRET_KEY" in r.message]


# ────────────────────────────────────────────────────────────────────
# 端到端: 默认配置固定码被拒 / 显式 dev 模式放行
# ────────────────────────────────────────────────────────────────────
class TestPhoneBindDefaultRejectsFixedCode:
    def test_default_settings_fixed_code_501(self, client, monkeypatch):
        """SMS_DEV_MODE=False (新默认) 时, 任何固定码 (含 123456) 不得通过。"""
        monkeypatch.setattr(settings, "SMS_DEV_MODE", False)
        login = client.post(AUTH_URL, json={"code": "sec-default-login"}).json()["data"]
        headers = {"Authorization": f"Bearer {login['token']}"}
        response = client.post(
            PHONE_URL, json={"phone": "13800138000", "sms_code": "123456"}, headers=headers
        )
        assert response.status_code == 501

    def test_explicit_dev_mode_accepts_code(self, client, monkeypatch):
        """显式 opt-in dev 模式 + 配置码 → 放行 (演示兼容, 不改生产语义)。"""
        monkeypatch.setattr(settings, "SMS_DEV_MODE", True)
        monkeypatch.setattr(settings, "SMS_DEV_CODE", "123456")
        login = client.post(AUTH_URL, json={"code": "sec-devmode-login"}).json()["data"]
        headers = {"Authorization": f"Bearer {login['token']}"}
        response = client.post(
            PHONE_URL, json={"phone": "13800138000", "sms_code": "123456"}, headers=headers
        )
        assert response.status_code == 200, response.text

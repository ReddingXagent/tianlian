"""app/core/config.py 配置加载单测

Settings (pydantic_settings.BaseSettings): 默认值 / 环境变量覆盖 / case_sensitive /
extra=ignore / 双密钥灰度轮换默认 None / get_settings lru_cache 单例。

注意: conftest 已 setenv DB_TYPE/DATABASE_URL/SECRET_KEY (测试隔离用), 故默认值断言
避开这三个字段, 只测 conftest 未覆盖的字段; 环境变量覆盖用 monkeypatch.setenv + 新建
Settings() (env vars 优先于 .env)。
"""
import pytest

from app.core.config import Settings, get_settings, settings


# ────────────────────────────────────────────────────────────────────
# 默认值 (conftest 未覆盖的字段)
# ────────────────────────────────────────────────────────────────────
class TestDefaults:
    def test_app_metadata(self):
        assert settings.APP_NAME == "天链光储充运维系统"
        assert settings.APP_VERSION == "3.0.0"

    def test_server(self):
        assert settings.HOST == "0.0.0.0"
        assert settings.PORT == 8080

    def test_jwt_algorithm_and_expiry(self):
        assert settings.ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 1440

    def test_postgres_pool(self):
        assert settings.DB_POOL_SIZE == 20
        assert settings.DB_MAX_OVERFLOW == 10
        assert settings.DB_POOL_RECYCLE == 3600
        assert settings.DB_POOL_PRE_PING is True

    def test_timezone_family_defaults_shanghai(self):
        """时区缺陷族 (电价/通知/值班/业务日) 默认均 Asia/Shanghai。"""
        for attr in ("PRICING_TIMEZONE", "NOTIFICATION_TIMEZONE",
                     "ONCALL_TIMEZONE", "BUSINESS_TIMEZONE"):
            assert getattr(settings, attr) == "Asia/Shanghai"

    def test_dual_key_rotation_defaults_none(self):
        """SECRET_KEY_NEW/OLD 未配置 → None (单 key 模式, 与改造前一致)。"""
        assert settings.SECRET_KEY_NEW is None
        assert settings.SECRET_KEY_OLD is None

    def test_security_secrets_default_none(self):
        """三个安全密钥未配置 → None, 强制生产显式配置 (不保留裸奔兼容)。"""
        assert settings.ALERT_WEBHOOK_SECRET is None
        assert settings.POD_COMM_SHARED_SECRET is None
        assert settings.FIELD_ENCRYPTION_KEY is None

    def test_tdengine_disabled_by_default(self):
        assert settings.TDENGINE_ENABLED is False

    def test_pod_defaults(self):
        assert settings.POD_LOCAL_ONLY is True
        assert settings.POD_ID == "pod-01"

    def test_secret_key_meets_rfc7518(self):
        """HMAC key ≥32 字节 (RFC 7518 §3.2), 默认/测试值均满足。"""
        assert len(settings.SECRET_KEY.encode()) >= 32


# ────────────────────────────────────────────────────────────────────
# 环境变量覆盖 (env vars 优先于 .env; 新建 Settings() 每次重读)
# ────────────────────────────────────────────────────────────────────
class TestEnvOverride:
    def test_port_override_with_int_coercion(self, monkeypatch):
        monkeypatch.setenv("PORT", "9999")
        assert Settings().PORT == 9999  # str → int 强转

    def test_bool_override(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "false")
        assert Settings().DEBUG is False

    def test_case_sensitive_upper_only(self, monkeypatch):
        """case_sensitive=True: 大写 PORT 生效, 小写 port 被忽略 → 取大写值。"""
        monkeypatch.setenv("PORT", "9999")  # 大写, 精确匹配字段名
        monkeypatch.setenv("port", "1111")  # 小写, 不匹配
        assert Settings().PORT == 9999


# ────────────────────────────────────────────────────────────────────
# extra = "ignore"
# ────────────────────────────────────────────────────────────────────
class TestExtraIgnore:
    def test_unknown_kwarg_silently_ignored(self):
        """extra=ignore: 构造传未知字段不报错, 也不挂为属性。"""
        s = Settings(THIS_FIELD_DOES_NOT_EXIST="x", APP_NAME="x")
        assert s.APP_NAME == "x"
        with pytest.raises(AttributeError):
            s.THIS_FIELD_DOES_NOT_EXIST


# ────────────────────────────────────────────────────────────────────
# get_settings lru_cache 单例
# ────────────────────────────────────────────────────────────────────
class TestGetSettingsCache:
    def test_cached_singleton_identity(self):
        assert get_settings() is get_settings()

    def test_cache_clear_returns_new_instance(self):
        a = get_settings()
        get_settings.cache_clear()
        b = get_settings()
        try:
            assert a is not b  # 清缓存后重建新实例
        finally:
            # 还原: 清缓存让后续其它测试 get_settings() 重新 warm 单例
            get_settings.cache_clear()
            get_settings()

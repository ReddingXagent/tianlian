"""卡 5f1c5f45: C端短信验证码硬编码守卫 —— SMS_DEV_MODE/SMS_DEV_CODE 配置化.

mock code 不得再硬编码在路由模块; 非 dev 模式下 phone-bind 直接 501,
任何固定码不得通过校验。
"""

import app.api.v1.business_end_user_auth as mod
from app.core.config import settings

AUTH_URL = "/api/v1/business/auth/wx-login"
PHONE_URL = "/api/v1/business/user/phone-bind"


def _body(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()["code"] == 0
    return response.json()["data"]


def _login_headers(client):
    login = _body(client.post(AUTH_URL, json={"code": "sms-guard-code"}))
    return {"Authorization": f"Bearer {login['token']}"}


def test_no_hardcoded_mock_code_in_module():
    """mock code 移入 settings, 路由模块不得残留硬编码验证码。

    卡 75a0069e: SMS_DEV_MODE 默认改 False / SMS_DEV_CODE 默认 None,
    不再断言默认开 (fail-safe)。此处只验证模块无硬编码。
    """
    assert not hasattr(mod, "_MOCK_SMS_CODE")


def test_dev_mode_accepts_configured_code(client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMS_DEV_MODE", True)
    monkeypatch.setattr(settings, "SMS_DEV_CODE", "123456")
    headers = _login_headers(client)

    import logging

    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        data = _body(
            client.post(
                PHONE_URL,
                json={"phone": "13800138000", "sms_code": "123456"},
                headers=headers,
            )
        )
    assert data["phone"] == "13800138000"
    # 审计痕迹: warning 含脱敏手机号, 不含完整号码
    assert any("SMS_DEV_MODE" in r.message for r in caplog.records)
    joined = " ".join(r.message for r in caplog.records)
    assert "13800138000" not in joined
    assert "138****8000" in joined


def test_dev_mode_wrong_code_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "SMS_DEV_MODE", True)
    monkeypatch.setattr(settings, "SMS_DEV_CODE", "123456")
    headers = _login_headers(client)

    response = client.post(
        PHONE_URL,
        json={"phone": "13800138000", "sms_code": "654321"},
        headers=headers,
    )
    assert response.status_code == 422


def test_non_dev_mode_returns_501_even_with_code(client, monkeypatch):
    monkeypatch.setattr(settings, "SMS_DEV_MODE", False)
    headers = _login_headers(client)

    response = client.post(
        PHONE_URL,
        json={"phone": "13800138000", "sms_code": "123456"},
        headers=headers,
    )
    assert response.status_code == 501

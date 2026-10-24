"""C端契约§8 端点限流加固测试 (卡 b7270c63)

C端 7 文件原 0 @limiter 装饰器, 直接暴露公网 (用户小程序直连), 可被刷
IM-B code2session 外呼 / 刷充电启动 / 刷券库存。本文件给每个被装饰端点
验证超限 → 429。

模式参照 test_business_rate_limit.py 的 enable_rate_limit fixture:
  conftest 默认 RATE_LIMIT_ENABLED=false (TestClient 同 IP 会撞限流误红),
  本文件每用例 monkeypatch limiter.enabled=True 并补 SlowAPI handler。
  limiter.reset() 清内存计数残留, 用例间隔离。

触发策略: 用「有效 body / 路径 → 端点函数执行 → 业务级响应 (200/404/409)」
而非 Pydantic 422 —— slowapi 装饰器在端点函数内消耗配额, 422 发生在函数
执行前的请求解析, 不计数; 故必须让端点函数跑起来。业务级错误也计数, 且
不污染状态机 (用不存在的资源 / 重复幂等键)。

额度参照运营侧: auth login 20/min、prepay 30/min、orders 读 60/min。
"""
import pytest
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter

AUTH = "/api/v1/business/auth/wx-login"
CHARGING = "/api/v1/charging-orders"
COUPONS = "/api/v1/coupons"
POINTS = "/api/v1/points"
BRANDING = "/api/v1/tenants/1/branding"
VEHICLES = "/api/v1/business/vehicles"
FAVORITES = "/api/v1/business/favorites"


# ─── helpers ───

def _login(client, code):
    r = client.post(AUTH, json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def enable_rate_limit(client: TestClient, monkeypatch):
    """开启 limiter 并为 conftest app 补齐 SlowAPI handler (RateLimitExceeded → 429)。

    复用 test_business_rate_limit.py 的既定模式。每用例前 reset 清内存计数残留。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    yield
    limiter.reset()


# =====================================================================
# auth: POST /auth/wx-login — 20/min (外呼IM-B code2session, mock 模式 200)
# =====================================================================

def test_wx_login_rate_limit_429(client, enable_rate_limit):
    """wx-login 限流 20/min: 第 21 次 429。同 code → 同 mock 用户, 幂等不污染。"""
    payload = {"code": "rate-wx"}
    codes = [client.post(AUTH, json=payload).status_code for _ in range(21)]
    assert all(c != 429 for c in codes[:20]), f"前 20 次不应限流, 实际: {codes}"
    assert codes[20] == 429, f"第 21 次应 429, 实际: {codes}"


# =====================================================================
# charging: start-by-sn / pay / complete — 30/min (刷充电启动/支付/完成)
# =====================================================================

def test_start_by_sn_rate_limit_429(client, enable_rate_limit):
    """start-by-sn 30/min: 第 31 次 429。不存在 sn → DEVICE_NOT_FOUND (200) 也计数。"""
    token = _login(client, "rl-sbs")
    headers = _headers(token)
    payload = {"sn": "NON_EXISTENT_SN"}
    codes = [
        client.post(f"{CHARGING}/start-by-sn", json=payload, headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


def test_pay_rate_limit_429(client, enable_rate_limit):
    """pay 30/min: 第 31 次 429。不存在订单 → ORDER_NOT_FOUND (200) 也计数。"""
    token = _login(client, "rl-pay")
    headers = _headers(token)
    payload = {"openid": "oX", "scene": "miniprogram"}
    codes = [
        client.post(f"{CHARGING}/TL_NOT_EXIST/pay", json=payload, headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


def test_complete_rate_limit_429(client, enable_rate_limit):
    """complete 30/min: 第 31 次 429。不存在订单 → ORDER_NOT_FOUND (200) 也计数。"""
    token = _login(client, "rl-cmp")
    headers = _headers(token)
    codes = [
        client.post(f"{CHARGING}/TL_NOT_EXIST/complete", headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


# =====================================================================
# coupons: GET /coupons — 60/min (只读, 无分页全量返回); POST /coupons/claim — 60/min (刷券库存)
#  (卡 2e6772bb: GET /coupons 原漏 @limiter, 端侧路径补齐)
# =====================================================================

def test_coupons_list_rate_limit_429(client, enable_rate_limit):
    """GET /coupons 60/min: 第 61 次 429 (只读高频轮询, 无分页全量查询)。"""
    token = _login(client, "rl-clist")
    headers = _headers(token)
    codes = [client.get(COUPONS, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_claim_rate_limit_429(client, enable_rate_limit):
    """claim 60/min: 第 61 次 429。不存在 coupon_id → 404 也计数, 不扣库存。"""
    token = _login(client, "rl-claim")
    headers = _headers(token)
    payload = {"coupon_id": 999999}
    codes = [
        client.post(f"{COUPONS}/claim", json=payload, headers=headers).status_code
        for _ in range(61)
    ]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


# =====================================================================
# points: GET /points — 60/min (只读)
# =====================================================================

def test_points_rate_limit_429(client, enable_rate_limit):
    """points 60/min: 第 61 次 429 (只读高频轮询)。"""
    token = _login(client, "rl-pts")
    headers = _headers(token)
    codes = [client.get(POINTS, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


# =====================================================================
# branding: GET /tenants/{id}/branding — 60/min (只读公开, 匿名可访问)
# =====================================================================

def test_branding_rate_limit_429(client, enable_rate_limit):
    """branding 60/min: 第 61 次 429 (公开端点, 无需 token)。"""
    codes = [client.get(BRANDING).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


# =====================================================================
# vehicles: list 60/min (读); create/delete/set-default 30/min (写)
# =====================================================================

def test_vehicles_list_rate_limit_429(client, enable_rate_limit):
    """list 60/min: 第 61 次 429 (只读)。"""
    token = _login(client, "rl-vlist")
    headers = _headers(token)
    codes = [client.get(VEHICLES, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_vehicles_create_rate_limit_429(client, enable_rate_limit):
    """create 30/min: 第 31 次 429。同车牌 → 首次 200, 后续 409 重复, 均计数不污染。"""
    token = _login(client, "rl-vcreate")
    headers = _headers(token)
    payload = {"plate_number": "京RATE"}
    codes = [
        client.post(VEHICLES, json=payload, headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


def test_vehicles_delete_rate_limit_429(client, enable_rate_limit):
    """delete 30/min: 第 31 次 429。不存在的 vehicle_id → 404 也计数。"""
    token = _login(client, "rl-vdel")
    headers = _headers(token)
    codes = [
        client.delete(f"{VEHICLES}/999999", headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


def test_vehicles_set_default_rate_limit_429(client, enable_rate_limit):
    """set-default 30/min: 第 31 次 429。不存在的 vehicle_id → 404 也计数。"""
    token = _login(client, "rl-vdef")
    headers = _headers(token)
    codes = [
        client.patch(f"{VEHICLES}/999999/default", headers=headers).status_code
        for _ in range(31)
    ]
    assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
    assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


# =====================================================================
# favorites: list/create/delete — 60/min (端点统一 60/min)
# =====================================================================

def test_favorites_list_rate_limit_429(client, enable_rate_limit):
    """list 60/min: 第 61 次 429 (只读)。"""
    token = _login(client, "rl-flist")
    headers = _headers(token)
    codes = [client.get(FAVORITES, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_favorites_create_rate_limit_429(client, enable_rate_limit):
    """create 60/min: 第 61 次 429。不存在 station_id → 404 也计数, 不落库。"""
    token = _login(client, "rl-fcreate")
    headers = _headers(token)
    payload = {"station_id": 999999}
    codes = [
        client.post(FAVORITES, json=payload, headers=headers).status_code
        for _ in range(61)
    ]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_favorites_delete_rate_limit_429(client, enable_rate_limit):
    """delete 60/min: 第 61 次 429。幂等删除不存在收藏 → 200 deleted=false 也计数。"""
    token = _login(client, "rl-fdel")
    headers = _headers(token)
    codes = [
        client.delete(f"{FAVORITES}/999999", headers=headers).status_code
        for _ in range(61)
    ]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


# =====================================================================
# business_end_user_auth 剩余 5 端点 (卡 18c396ec):
# me 读/写 60/min; phone-bind 20/min (短信外呼); devices/token 写/删 60/min
# =====================================================================

ME = "/api/v1/business/user/me"
PHONE_BIND = "/api/v1/business/user/phone-bind"
DEVICE_TOKEN = "/api/v1/business/devices/token"


def test_get_me_rate_limit_429(client, enable_rate_limit):
    """GET me 60/min: 第 61 次 429 (只读高频轮询)。"""
    token = _login(client, "rl-gme")
    headers = _headers(token)
    codes = [client.get(ME, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_patch_me_rate_limit_429(client, enable_rate_limit):
    """PATCH me 60/min: 第 61 次 429。空 body → 200 幂等不污染。"""
    token = _login(client, "rl-pme")
    headers = _headers(token)
    codes = [client.patch(ME, json={}, headers=headers).status_code for _ in range(61)]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_phone_bind_rate_limit_429(client, enable_rate_limit, monkeypatch):
    """phone-bind 20/min: 第 21 次 429。错验证码 → 422 业务级响应也计数。"""
    token = _login(client, "rl-pbind")
    headers = _headers(token)
    # 卡 75a0069e: SMS_DEV_MODE 默认 False, 显式开启保证前 20 次得到 422 业务响应
    # (monkeypatch 用例级隔离, 避免直接改全局 settings 污染后续用例)
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "SMS_DEV_MODE", True)
    monkeypatch.setattr(_settings, "SMS_DEV_CODE", "123456")
    payload = {"phone": "13800009999", "sms_code": "000000"}
    codes = [
        client.post(PHONE_BIND, json=payload, headers=headers).status_code
        for _ in range(21)
    ]
    assert all(c != 429 for c in codes[:20]), f"前 20 次不应限流, 实际: {codes}"
    assert codes[20] == 429, f"第 21 次应 429, 实际: {codes}"


def test_register_device_token_rate_limit_429(client, enable_rate_limit):
    """devices/token POST 60/min: 第 61 次 429。同 token 重复注册幂等不污染。"""
    token = _login(client, "rl-dtok")
    headers = _headers(token)
    payload = {"platform": "ios", "device_token": "rl-token-x"}
    codes = [
        client.post(DEVICE_TOKEN, json=payload, headers=headers).status_code
        for _ in range(61)
    ]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"


def test_delete_device_token_rate_limit_429(client, enable_rate_limit):
    """devices/token DELETE 60/min: 第 61 次 429。幂等删除 → 200 也计数。"""
    token = _login(client, "rl-dtdel")
    headers = _headers(token)
    payload = {"platform": "android"}
    codes = [
        client.request("DELETE", DEVICE_TOKEN, json=payload, headers=headers).status_code
        for _ in range(61)
    ]
    assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
    assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"

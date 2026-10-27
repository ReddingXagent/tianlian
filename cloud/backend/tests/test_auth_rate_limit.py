"""认证防爆破加固测试 (卡 8db307c9 D2-hardening + 卡 58de8a68 D2跟进)

覆盖:
  ① /login 限流 20/min per real IP — 同 IP 连续 21 次, 第 21 次被限流 (429)
  ② 短信验证码 5 次错误后 attempts 锁定, 正确码也失效
  ③ main.app 中间件栈含 SlowAPIMiddleware (default_limits 全局生效前提)
  ④ XFF 独立计数: 两个不同 X-Forwarded-For IP 各自独立限流 (卡 58de8a68)
  ⑤ POST /users 建用户密码为 bcrypt ($2前缀), 非无盐SHA256 (卡 58de8a68)
"""
import pytest
from fastapi.testclient import TestClient

from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.rate_limit import limiter
from app.models.sms_verification import SmsVerificationCode


def test_login_rate_limit_returns_429_on_21st(client: TestClient, monkeypatch):
    """① 限流开启: 同 IP 连续 21 次 /login, 第 21 次返回 429 (20/min per real IP)。

    conftest 默认关闭限流 (RATE_LIMIT_ENABLED=false); 本测试临时开启 limiter,
    并为 conftest 构造的 app 补齐 SlowAPI 三件套 (state.limiter / 异常 handler /
    装饰器自检), 使 RateLimitExceeded → 429。
    """
    # 清同进程内存计数残留, 保证本测试从 0 开始计数
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)  # 测试结束自动恢复

    # conftest app 未挂 SlowAPI 中间件; 装饰器自检 + handler 使超限返回 429
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    codes = []
    for _ in range(21):
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        codes.append(r.status_code)

    assert codes[:20] == [200] * 20, f"前 20 次应放行 (200), 实际: {codes}"
    assert codes[20] == 429, f"第 21 次应被限流 (429), 实际: {codes}"


def test_sms_verify_locks_after_5_wrong_attempts(client: TestClient, seed_users, db_session):
    """② 验证码连续 5 次错误后 attempts=5; 第 6 次用正确码也失效 (锁定 used=1)。"""
    phone = "13800138099"
    resp = client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "login"})
    assert resp.status_code == 200

    code_record = (
        db_session.query(SmsVerificationCode)
        .filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "login",
            SmsVerificationCode.used == 0,
        )
        .first()
    )
    assert code_record is not None, "发送验证码后应有一条未使用记录"
    correct_code = code_record.code

    # 连续 5 次错误码 → 每次 valid=False, attempts 递增
    for i in range(5):
        r = client.post(
            "/api/v1/auth/sms/verify",
            json={"phone": phone, "code": "000000", "purpose": "login"},
        )
        assert r.status_code == 200
        assert r.json().get("data", {}).get("valid") is False, f"第 {i+1} 次错误码应 invalid"

    db_session.refresh(code_record)
    assert code_record.attempts == 5, f"5 次错误后 attempts 应=5, 实际 {code_record.attempts}"

    # 第 6 次用正确码 → 已锁定 (attempts>=5), 仍失效; 记录标记 used=1
    r = client.post(
        "/api/v1/auth/sms/verify",
        json={"phone": phone, "code": correct_code, "purpose": "login"},
    )
    assert r.status_code == 200
    assert r.json().get("data", {}).get("valid") is False, "锁定后正确码也应失效"
    db_session.refresh(code_record)
    assert code_record.used == 1, "锁定后验证码应标记 used=1"


def test_sms_verify_rate_limit_returns_429_on_21st(client: TestClient, monkeypatch):
    """②b /sms/verify 补挂 login 限流 (卡 c671ffc7): 同 IP 连续 21 次, 第 21 次 429。

    修复前该端点无 @limiter.limit, 可无限速爆破验证码; 修复后与 /login 同限流键。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)  # 测试结束自动恢复
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    payload = {"phone": "13900139000", "code": "000000", "purpose": "login"}
    codes = [
        client.post("/api/v1/auth/sms/verify", json=payload).status_code
        for _ in range(21)
    ]

    assert codes[:20] == [200] * 20, f"前 20 次应放行 (200), 实际: {codes}"
    assert codes[20] == 429, f"第 21 次应被限流 (429), 实际: {codes}"


def test_main_app_has_slowapi_middleware():
    """③ main.app 中间件栈含 SlowAPIMiddleware (使 default_limits 全局生效)。"""
    from app.main import app

    classes = [m.cls for m in app.user_middleware]
    assert SlowAPIMiddleware in classes, (
        f"main.app 应挂载 SlowAPIMiddleware, 实际中间件: "
        f"{[c.__name__ for c in classes]}"
    )


def test_xff_ips_have_independent_rate_limits(client: TestClient, monkeypatch):
    """④ XFF 独立计数: 两个不同 X-Forwarded-For IP 各自独立限流。

    修复前 key_func=get_remote_address, nginx 下全站共享 127.0.0.1 → 误锁;
    修复后 key_func=get_real_ip 读 XFF 首段, 不同真实 IP 独立计数。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # IP-A 发 20 次 (打满 20/min 配额)
    for _ in range(20):
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )

    # IP-A 第 21 次 → 429
    r_a = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert r_a.status_code == 429, f"IP-A 第 21 次应 429, 实际 {r_a.status_code}"

    # IP-B 第 1 次 → 200 (独立计数, 不受 IP-A 影响)
    r_b = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )
    assert r_b.status_code == 200, (
        f"IP-B 第 1 次应 200 (独立计数), 实际 {r_b.status_code} — "
        f"限流 key 未按 XFF 区分 IP"
    )


def test_create_user_uses_bcrypt_hash(client: TestClient, seed_users, db_session):
    """⑤ POST /users 建用户密码为 bcrypt ($2前缀), 非无盐SHA256。

    修复前 users.py 用 hashlib.sha256 (64位hex), 与 auth.py 透明升级矛盾;
    修复后统一 get_password_hash (bcrypt, $2b$ 前缀)。
    """
    from app.models.user import User

    r = client.post(
        "/api/v1/users",
        json={"username": "bcrypt_test_user", "password": "TestPass123", "role": "engineer"},
    )
    assert r.status_code == 200, f"建用户应 200, 实际 {r.status_code}: {r.text}"

    user = db_session.query(User).filter(User.username == "bcrypt_test_user").first()
    assert user is not None, "建用户后 DB 应有记录"
    assert user.password_hash.startswith("$2"), (
        f"密码 hash 应为 bcrypt ($2前缀), 实际: {user.password_hash[:20]}..."
    )
    # 反向验证: 不是 SHA256 (64位hex)
    assert len(user.password_hash) != 64 or not all(
        c in "0123456789abcdef" for c in user.password_hash
    ), "密码 hash 不应为无盐 SHA256 (64位hex)"


def test_register_rate_limit_returns_429_on_6th(client: TestClient, monkeypatch):
    """/register 限流 5/min per real IP (卡 d8fff697)。

    装饰器在端点函数前执行: 前 5 次消耗配额 (无论端点返回 200 创建成功
    还是 400 用户名重复), 第 6 次超 5/min 上限被拦 (429)。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    codes = []
    for _ in range(6):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": "rate_limit_register_user",
                "password": "NewPass123!",
                "real_name": "限流测试用户",
                "role": "engineer",
            },
        )
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:5]), (
        f"前 5 次不应触发限流 (5/min), 实际: {codes}"
    )
    assert codes[5] == 429, f"第 6 次应被限流 (429), 实际: {codes}"


def test_forgot_password_rate_limit_returns_429_on_6th(client: TestClient, monkeypatch):
    """/forgot-password 限流 5/min per real IP (卡 56712a04)。

    修复前该未认证写端点仅受全局 1000/min 兜底, 可高频刷满
    password_reset_requests 表; 修复后与 /register 同档 5/min。
    装饰器先于端点执行: 前 5 次 (无论账号存在与否) 消耗配额, 第 6 次 429。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    codes = []
    for _ in range(6):
        r = client.post(
            "/api/v1/auth/forgot-password",
            json={"account": "rate_limit_probe_user"},
        )
        codes.append(r.status_code)

    assert all(c != 429 for c in codes[:5]), (
        f"前 5 次不应触发限流 (5/min), 实际: {codes}"
    )
    assert codes[5] == 429, f"第 6 次应被限流 (429), 实际: {codes}"


def test_sms_send_rate_limit_returns_429_on_2nd(client: TestClient, monkeypatch):
    """/sms/send 限流 1/min per real IP (卡 d8fff697)。

    短信验证码为高成本/易被滥用端点 (短信轰炸), 配额收紧到 1/min。
    第 2 次请求即被拦 (429), 且与手机号无关 — per real IP 而非 per phone。
    """
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    client.app.state.limiter = limiter
    client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    r1 = client.post(
        "/api/v1/auth/sms/send",
        json={"phone": "13800138100", "purpose": "login"},
    )
    # 第 2 次用不同手机号, 证明按 real IP 而非 phone 限流
    r2 = client.post(
        "/api/v1/auth/sms/send",
        json={"phone": "13800138101", "purpose": "login"},
    )

    assert r1.status_code != 429, f"第 1 次应放行, 实际 {r1.status_code}"
    assert r2.status_code == 429, (
        f"第 2 次应被限流 (1/min per IP), 实际 {r2.status_code}"
    )

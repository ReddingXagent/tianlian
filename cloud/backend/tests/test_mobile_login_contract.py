"""
移动端联调 login 契约测试

固化 POST /api/v1/auth/login 的契约，供移动端(猴王)联调对齐：

  1. Content-Type 必须 application/x-www-form-urlencoded
     body: username=xxx&password=xxx
     发 JSON body 会被 OAuth2PasswordRequestForm 拒绝 → 422（标准 FastAPI 行为）

  2. 成功响应 200，统一格式 {code, message, data, timestamp}，
     其中 data.token 为 JWT（注意：字段名是 `token`，不是 `access_token`；
     也不含 `token_type` / `expires_in`，refresh 端点才有 access_token 三件套）。

  3. 拿到 token 后，带 Bearer 访问受保护资源 GET /api/v1/devices → 200。

  4. 无 token 访问受保护资源 → 401（全局 enforce_auth 兜底）。

login 端点契约正确（OAuth2 标准），本测试只做行为固化，不改 API。
"""
import bcrypt
from fastapi.testclient import TestClient

from app.models.user import User, UserRole

MOBILE_USERNAME = "mobile_test"
MOBILE_PASSWORD = "Tianlian2026!"


def _seed_mobile_user(session) -> None:
    """在测试 DB 中确保 mobile_test 用户存在（与 scripts/seed_mobile_test_user.py 对齐）。"""
    user = session.query(User).filter(User.username == MOBILE_USERNAME).first()
    pwd_hash = bcrypt.hashpw(MOBILE_PASSWORD.encode(), bcrypt.gensalt()).decode()
    if user is None:
        session.add(User(
            username=MOBILE_USERNAME,
            password_hash=pwd_hash,
            real_name="移动端联调-管理员",
            role=UserRole.ADMIN,
            status="active",
        ))
    else:
        user.password_hash = pwd_hash
        user.role = UserRole.ADMIN
        user.status = "active"
    session.commit()


def _login_form(client: TestClient):
    """以 form-encoded 方式登录（正确契约）。"""
    return client.post(
        "/api/v1/auth/login",
        data={"username": MOBILE_USERNAME, "password": MOBILE_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


class TestMobileLoginContract:
    """移动端 login 契约（form-encoded + token 字段 + 受保护资源）。"""

    def test_form_login_returns_token(self, client: TestClient, db_session):
        """form-encoded 登录成功并返回 data.token。"""
        _seed_mobile_user(db_session)

        resp = _login_form(client)

        assert resp.status_code == 200, f"form 登录应成功: {resp.status_code} {resp.text}"
        data = resp.json().get("data", {})
        # 真实契约：data.token。兼容性兜底 access_token 以防未来调整，但不依赖它。
        token = data.get("token") or data.get("access_token")
        assert token, f"登录响应缺少 token: {data}"

    def test_json_body_login_rejected_as_422(self, client: TestClient, db_session):
        """JSON body 登录应返回 422 —— 文档化 OAuth2 form 契约。

        移动端早期用 JSON body 收到 422 即由此触发：login 依赖
        OAuth2PasswordRequestForm（form 解析），JSON 无法提供 form 字段。
        """
        _seed_mobile_user(db_session)

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": MOBILE_USERNAME, "password": MOBILE_PASSWORD},
        )

        assert resp.status_code == 422, (
            f"JSON body 登录应被拒绝为 422，实际: {resp.status_code} {resp.text}"
        )

    def test_token_accesses_devices(self, client: TestClient, db_session):
        """mobile_test 登录拿 token 后，GET /api/v1/devices 返回 200。"""
        _seed_mobile_user(db_session)

        resp = _login_form(client)
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        token = data.get("token") or data.get("access_token")
        assert token

        # 用新登录的 token（覆盖 client 默认的 admin token）访问受保护资源
        resp_devices = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_devices.status_code == 200, (
            f"带 token 访问 /devices 应 200，实际: {resp_devices.status_code} {resp_devices.text}"
        )

    def test_no_token_devices_rejected_401(self, anon_client: TestClient):
        """无 token 访问 GET /api/v1/devices 应返回 401。"""
        resp = anon_client.get("/api/v1/devices")
        assert resp.status_code == 401, (
            f"无 token 访问受保护资源应 401，实际: {resp.status_code} {resp.text}"
        )

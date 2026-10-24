"""
SSL证书端点全端点 admin 门禁 + 参数校验测试 — 任务卡 55f8d345。

漏洞: app/api/v1/ssl_certificates.py 全部端点(读+写)仅 Depends(get_current_user)，
无角色校验。普通团队用户可: 删除证书、触发 certbot 在主机执行
(--nginx 动主机 nginx 配置)、滥用 Let's Encrypt 速率配额。

覆盖:
- 普通用户(engineer/operator/viewer)读写全端点 → 403(大圣拍板: 证书属平台
  基础设施, 读端点一并收紧 admin only)
- admin/super_admin → 200(certbot 后台任务 mock, 只测权限+参数层)
- 非法域名(空格/;/$(/路径穿越/..) → 422; 非法 email → 422; 非法 san → 422;
  合法域名对照 → 200(确认非误伤)
- 匿名(无 token) → 401(用 anon_client, 勿用模块级 client —— conftest autouse
  会注入 admin token 导致假绿, 本轮刚确认的坑)

与 test_ssl_certificates.py(admin 登录态 CRUD)互补, 本文件聚焦授权与参数门禁。
认证层(401)由 test_auth_enforcement.py 全端点兜底扫描。
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import bcrypt
import pytest

from app.models.ssl_certificate import SSLCertificate
from app.models.user import User, UserRole


# ========== fixtures ==========

@pytest.fixture(scope="function")
def role_tokens(client):
    """seed 各角色用户并登录拿 token; 返回 {role_key: token}。

    admin 用 conftest 默认 seed 的(admin123)。角色覆盖团队级各档
    (engineer/operator/viewer)与平台级(super_admin), 用以验证
    require_platform_admin 的收紧与豁免。
    """
    s = client._sesh
    roles = {
        "engineer":    ("ssl_eng",    UserRole.ENGINEER),
        "operator":    ("ssl_op",     UserRole.OPERATOR),
        "viewer":      ("ssl_viewer", UserRole.VIEWER),
        "super_admin": ("ssl_sadmin", UserRole.SUPER_ADMIN),
    }
    pwd = "ssl123456"
    for uname, role in roles.values():
        if not s.query(User).filter(User.username == uname).first():
            s.add(User(
                username=uname,
                password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                role=role,
                status="active",
            ))
    s.commit()

    def _tok(uname):
        r = client.post("/api/v1/auth/login", data={"username": uname, "password": pwd})
        assert r.status_code == 200, f"登录失败 {uname}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    admin_r = client.post("/api/v1/auth/login",
                          data={"username": "admin", "password": "admin123"})
    assert admin_r.status_code == 200

    return {
        "engineer": _tok("ssl_eng"),
        "operator": _tok("ssl_op"),
        "viewer": _tok("ssl_viewer"),
        "super_admin": _tok("ssl_sadmin"),
        "admin": admin_r.json().get("data", {}).get("token") or admin_r.json().get("token"),
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _call(client, method, url, body, headers):
    """统一请求入口: body=None 走无体请求(DELETE/GET), 否则 json 提交。"""
    if body is None:
        return client.request(method, url, headers=headers)
    return client.request(method, url, json=body, headers=headers)


def _create_cert(client, **overrides):
    """直接向 conftest client 的 DB 插入一条证书, 返回 domain。"""
    defaults = dict(
        domain=f"auth-{datetime.now().strftime('%H%M%S%f')}.example.com",
        email="admin@test.com",
        status="active",
        auto_renew=True,
        renew_days_before=30,
        not_after=datetime.now(timezone.utc) + timedelta(days=90),
    )
    defaults.update(overrides)
    s = client._sesh
    c = SSLCertificate(**defaults)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c.domain


# 写端点(进 certbot / 改库): method, url, body。body 用合法值, 避免 422 干扰 403。
WRITE_ENDPOINTS = [
    ("POST",   "/api/v1/ssl/certificates",
        {"domain": "evil.example.com", "email": "admin@evil.com"}),
    ("POST",   "/api/v1/ssl/certificates/any.example.com/renew",
        {"domain": "any.example.com", "staging": False}),
    ("PUT",    "/api/v1/ssl/certificates/any.example.com/config",
        {"auto_renew": False, "renew_days_before": 14}),
    ("DELETE", "/api/v1/ssl/certificates/any.example.com", None),
    ("POST",   "/api/v1/ssl/auto-renew", None),
]

# 读端点(已收紧 admin only)
READ_ENDPOINTS = [
    ("GET", "/api/v1/ssl/certificates", None),
    ("GET", "/api/v1/ssl/certificates/any.example.com", None),
    ("GET", "/api/v1/ssl/health-check", None),
]


# ========== 越权: 普通用户写端点 → 403 ==========

class TestWriteForbidden:
    """证书属平台基础设施: 普通用户不得申请/续期/改配置/删除/触发自动续期。

    require_platform_admin 在端点函数体前执行, 故即便资源不存在也先 403
    (不泄露存在), 与 404 区分。
    """

    @pytest.mark.parametrize("role", ["engineer", "operator", "viewer"])
    @pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
    def test_write_forbidden(self, client, role_tokens, role, method, url, body):
        r = _call(client, method, url, body, _h(role_tokens[role]))
        assert r.status_code == 403, (
            f"{role} {method} {url} 应 403, 实际 {r.status_code}: {r.text}")


# ========== 越权: 普通用户读端点 → 403(已收紧) ==========

class TestReadForbidden:
    """读端点(列表/详情/健康检查)一并收紧 admin only — 大圣拍板。"""

    @pytest.mark.parametrize("role", ["engineer", "operator", "viewer"])
    @pytest.mark.parametrize("method,url,body", READ_ENDPOINTS)
    def test_read_forbidden(self, client, role_tokens, role, method, url, body):
        r = _call(client, method, url, body, _h(role_tokens[role]))
        assert r.status_code == 403, (
            f"{role} {method} {url} 应 403, 实际 {r.status_code}: {r.text}")


# ========== admin / super_admin 放行 → 200 ==========

class TestAdminAllowed:
    """admin/super_admin 通过门禁; certbot 后台任务 mock, 只验权限层。"""

    def test_admin_list(self, client, role_tokens):
        assert client.get("/api/v1/ssl/certificates",
                          headers=_h(role_tokens["admin"])).status_code == 200

    def test_admin_health(self, client, role_tokens):
        assert client.get("/api/v1/ssl/health-check",
                          headers=_h(role_tokens["admin"])).status_code == 200

    def test_admin_get_detail(self, client, role_tokens):
        domain = _create_cert(client)
        r = client.get(f"/api/v1/ssl/certificates/{domain}",
                       headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["domain"] == domain

    def test_admin_request(self, client, role_tokens):
        with patch("app.api.v1.ssl_certificates._async_request_cert") as m:
            r = client.post("/api/v1/ssl/certificates",
                            json={"domain": "new.example.com", "email": "admin@new.com"},
                            headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["domain"] == "new.example.com"
        assert "task_id" in r.json()
        # 后台任务由 BackgroundTasks 在响应后执行(mock 已拦)
        m.assert_called_once()

    def test_admin_renew(self, client, role_tokens):
        domain = _create_cert(client)
        with patch("app.api.v1.ssl_certificates._async_renew_cert"):
            r = client.post(f"/api/v1/ssl/certificates/{domain}/renew",
                            json={"domain": domain, "staging": True},
                            headers=_h(role_tokens["admin"]))
        assert r.status_code == 200

    def test_admin_update_config(self, client, role_tokens):
        domain = _create_cert(client)
        r = client.put(f"/api/v1/ssl/certificates/{domain}/config",
                       json={"auto_renew": False, "renew_days_before": 14},
                       headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["auto_renew"] is False

    def test_admin_delete(self, client, role_tokens):
        domain = _create_cert(client)
        r = client.delete(f"/api/v1/ssl/certificates/{domain}",
                          headers=_h(role_tokens["admin"]))
        assert r.status_code == 200

    def test_admin_auto_renew(self, client, role_tokens):
        # 建 needs_renewal 证书(not_after 已过), 验证 mock 被调用 + 权限放行
        _create_cert(client, not_after=datetime.now(timezone.utc) - timedelta(days=1))
        with patch("app.api.v1.ssl_certificates._async_renew_cert") as m:
            r = client.post("/api/v1/ssl/auto-renew", headers=_h(role_tokens["admin"]))
        assert r.status_code == 200
        assert r.json()["needs_renewal"] >= 1
        m.assert_called_once()

    def test_super_admin_exempt(self, client, role_tokens):
        """super_admin 平台级豁免 → 通过(与 is_platform_admin 同源)。"""
        with patch("app.api.v1.ssl_certificates._async_request_cert"):
            r = client.post("/api/v1/ssl/certificates",
                            json={"domain": "super.example.com", "email": "admin@super.com"},
                            headers=_h(role_tokens["super_admin"]))
        assert r.status_code == 200

    def test_forbidden_request_no_mutation(self, client, role_tokens):
        """403 拦截后不落库 — 普通用户的越权申请不得创建证书记录。"""
        s = client._sesh
        before = s.query(SSLCertificate).filter(
            SSLCertificate.domain == "evil.example.com").count()
        r = client.post("/api/v1/ssl/certificates",
                        json={"domain": "evil.example.com", "email": "admin@evil.com"},
                        headers=_h(role_tokens["engineer"]))
        assert r.status_code == 403
        after = s.query(SSLCertificate).filter(
            SSLCertificate.domain == "evil.example.com").count()
        assert after == before, "越权 403 不应落库"


# ========== 参数校验: 防 certbot 参数污染 → 422(用 admin 身份) ==========

class TestParameterValidation:
    """CertRequest.domain/sans/email 严格校验, 防空格/;/$(/路径穿越注入 certbot -d。

    用 admin 身份确保先过权限门, 422 必为 pydantic 拒绝(而非 403)。
    """

    @pytest.mark.parametrize("bad_domain", [
        "evil.com; rm -rf /",   # 分号 + shell 命令
        "$(whoami).com",        # 命令替换
        "evil.com`id`",         # 反引号命令替换
        "evil com.com",         # 空格
        "../etc/passwd",        # 路径穿越
        "a/../../b.com",        # 路径穿越
        "example..com",         # 连续点(空 label)
        "-bad.com",             # label 连字符开头
        "bad-.com",             # label 连字符结尾
        "foo;bar.com",          # 分号
        "|cat /etc/passwd",     # 管道 + 元字符
        "1.2.3.4",              # IP(证书仅域名, 不放宽)
    ])
    def test_bad_domain_422(self, client, role_tokens, bad_domain):
        r = client.post("/api/v1/ssl/certificates",
                        json={"domain": bad_domain, "email": "admin@evil.com"},
                        headers=_h(role_tokens["admin"]))
        assert r.status_code == 422, (
            f"非法域名 {bad_domain!r} 应 422, 实际 {r.status_code}: {r.text}")

    @pytest.mark.parametrize("bad_email", [
        "not-an-email",
        "admin@",
        "@nouser.com",
        "no space@test.com",
        "double..dot@test.com",
    ])
    def test_bad_email_422(self, client, role_tokens, bad_email):
        r = client.post("/api/v1/ssl/certificates",
                        json={"domain": "evil.example.com", "email": bad_email},
                        headers=_h(role_tokens["admin"]))
        assert r.status_code == 422, (
            f"非法 email {bad_email!r} 应 422, 实际 {r.status_code}: {r.text}")

    @pytest.mark.parametrize("bad_san", [
        "evil.com; rm -rf /",
        "$(id).com",
        "../etc/passwd",
        "a b.example.com",
    ])
    def test_bad_san_422(self, client, role_tokens, bad_san):
        r = client.post("/api/v1/ssl/certificates",
                        json={"domain": "ok.example.com",
                              "email": "admin@ok.com",
                              "sans": [bad_san]},
                        headers=_h(role_tokens["admin"]))
        assert r.status_code == 422, (
            f"非法 san {bad_san!r} 应 422, 实际 {r.status_code}: {r.text}")

    def test_valid_request_accepted(self, client, role_tokens):
        """合法域名/email/san 对照 → 200(确认校验非误伤)。"""
        with patch("app.api.v1.ssl_certificates._async_request_cert"):
            r = client.post("/api/v1/ssl/certificates",
                            json={"domain": "valid.example.com",
                                  "email": "admin@valid.com",
                                  "sans": ["alt1.valid.com", "alt2.valid.com"]},
                            headers=_h(role_tokens["admin"]))
        assert r.status_code == 200

    def test_valid_default_email_accepted(self, client, role_tokens):
        """不传 email 走默认 admin@tianlian.com(EmailStr 合法) → 200。"""
        with patch("app.api.v1.ssl_certificates._async_request_cert"):
            r = client.post("/api/v1/ssl/certificates",
                            json={"domain": "default.example.com"},
                            headers=_h(role_tokens["admin"]))
        assert r.status_code == 200


# ========== 匿名拒绝(401): 用 anon_client, 勿用模块级 client ==========

class TestAnonymous:
    """匿名(无 token)访问 → 401。

    conftest 的 client fixture 会注入 admin token → 必须用 anon_client
    表达真匿名, 否则假绿(任务卡明示坑)。
    """

    @pytest.mark.parametrize("method,url,body", READ_ENDPOINTS + [
        ("POST", "/api/v1/ssl/certificates", {"domain": "x.example.com"}),
        ("POST", "/api/v1/ssl/certificates/any.example.com/renew",
         {"domain": "any.example.com"}),
        ("PUT", "/api/v1/ssl/certificates/any.example.com/config",
         {"auto_renew": False}),
        ("POST", "/api/v1/ssl/auto-renew", None),
    ])
    def test_anon_401(self, anon_client, method, url, body):
        r = _call(anon_client, method, url, body, None)
        assert r.status_code == 401, (
            f"匿名 {method} {url} 应 401, 实际 {r.status_code}: {r.text}")

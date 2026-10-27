# -*- coding: utf-8 -*-
"""
SSL证书 API 辅助函数 & 后台任务覆盖测试 — 补 app/api/v1/ssl_certificates.py 未覆盖行。

聚焦未覆盖路径(不重复 test_ssl_certificates.py / test_ssl_certificates_authorization.py
已覆盖的 HTTP 端点 / 鉴权 / 参数校验):
- _check_remote_cert (93-109):  远程证书探测的成功/异常分支
- _run_certbot       (114-132): subprocess 执行的成功/失败码/超时/未安装/未知异常
- _detect_status     (139):     not_after 缺失 → days_remaining=None → "error"
- _async_request_cert(353-385): 后台申请(cert 不存在 / 成功落路径 / 失败记错误 / sans 拼参)
- _async_renew_cert   (390-416): 后台续期(cert 不存在 / staging 拼参 / 成功 / 失败)

后台任务函数内 `from app.core.database import SessionLocal` 取库, 故依赖 test_db
fixture override 模块级 SessionLocal 指向测试库(见 conftest test_db)。
helper 必须从 test_db["SessionLocal"] 动态取, 严禁模块顶部 import SessionLocal ——
否则拿到 override 前的生产库(任务卡 service-sessionlocal-import-binding 坑)。
"""
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.api.v1 import ssl_certificates as mod
from app.api.v1.ssl_certificates import (
    CertRequest,
    _check_remote_cert,
    _run_certbot,
    _detect_status,
    _async_request_cert,
    _async_renew_cert,
)
from app.models.ssl_certificate import SSLCertificate


# ========== _check_remote_cert (93-109) ==========

def test_check_remote_cert_success():
    """成功探测: 返回 domain/not_after/days_remaining/not_before/issuer。"""
    fake_cert = {
        "notAfter": "Jan 01 00:00:00 2027 GMT",
        "notBefore": "Jan 01 00:00:00 2026 GMT",
        "issuer": (("commonName", "Test CA"),),
    }
    ctx = MagicMock()
    sock = ctx.wrap_socket.return_value.__enter__.return_value
    sock.getpeercert.return_value = fake_cert
    with patch.object(mod.ssl, "create_default_context", return_value=ctx):
        result = _check_remote_cert("example.com")
    assert result["domain"] == "example.com"
    assert result["not_after"].startswith("2027-01-01")
    assert isinstance(result["days_remaining"], int)
    assert result["not_before"] == "Jan 01 00:00:00 2026 GMT"
    assert result["issuer"] == (("commonName", "Test CA"),)


def test_check_remote_cert_error():
    """异常分支: wrap_socket 抛错 → 返回 {domain, error}。"""
    ctx = MagicMock()
    ctx.wrap_socket.side_effect = OSError("connection refused")
    with patch.object(mod.ssl, "create_default_context", return_value=ctx):
        result = _check_remote_cert("bad.example.com")
    assert result["domain"] == "bad.example.com"
    assert "connection refused" not in result["error"]  # 安全: 不泄露内部异常原文
    assert result["error"]  # 仍提供通用错误描述


# ========== _run_certbot (114-132) ==========

def _run_result(returncode=0, stdout="", stderr=""):
    """构造 subprocess.run 返回的拟真对象(MagicMock 默认属性 truthy 会干扰判断, 显式赋值)。"""
    obj = MagicMock()
    obj.returncode = returncode
    obj.stdout = stdout
    obj.stderr = stderr
    return obj


def test_run_certbot_success():
    with patch.object(mod.subprocess, "run", return_value=_run_result(0, "ok", "warn")):
        r = _run_certbot(["certbot", "certonly"])
    assert r["success"] is True
    assert r["returncode"] == 0
    assert r["stdout"] == "ok"
    assert r["stderr"] == "warn"


def test_run_certbot_failure_returncode():
    with patch.object(mod.subprocess, "run", return_value=_run_result(1, "x", "boom")):
        r = _run_certbot(["certbot"])
    assert r["success"] is False
    assert r["returncode"] == 1


def test_run_certbot_empty_output():
    """stdout/stderr 为 None(falsy) → 空串分支 (line 123-124 的 `if ... else ""`)。"""
    obj = MagicMock()
    obj.returncode = 0
    obj.stdout = None
    obj.stderr = None
    with patch.object(mod.subprocess, "run", return_value=obj):
        r = _run_certbot(["certbot"])
    assert r["success"] is True
    assert r["stdout"] == ""
    assert r["stderr"] == ""


def test_run_certbot_timeout():
    with patch.object(mod.subprocess, "run",
                      side_effect=subprocess.TimeoutExpired(cmd="certbot", timeout=120)):
        r = _run_certbot(["certbot"])
    assert r["success"] is False
    assert r["returncode"] == -1
    assert "超时" in r["stderr"]


def test_run_certbot_not_installed():
    with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError()):
        r = _run_certbot(["certbot"])
    assert r["success"] is False
    assert r["returncode"] == -2
    assert "未安装" in r["stderr"]


def test_run_certbot_unknown_exception():
    with patch.object(mod.subprocess, "run", side_effect=RuntimeError("boom")):
        r = _run_certbot(["certbot"])
    assert r["success"] is False
    assert r["returncode"] == -3
    assert "boom" not in r["stderr"]  # 安全: 不泄露内部异常原文
    assert r["stderr"]  # 仍提供通用错误描述


# ========== _detect_status (139) ==========

def test_detect_status_no_expiry_is_error():
    """not_after 缺失 → days_remaining=None → status=error(覆盖第139行)。"""
    cert = SSLCertificate(domain="none.example.com", not_after=None, renew_days_before=30)
    assert _detect_status(cert) == "error"


# ========== 后台任务 helpers ==========

def _seed_cert(test_db, **overrides):
    """向测试库插入一条证书, 返回 id。SessionLocal 从 test_db 动态取(防生产库绑定)。"""
    SessionLocal = test_db["SessionLocal"]
    defaults = dict(
        domain=f"cov-{datetime.now(timezone.utc).strftime('%H%M%S%f')}.example.com",
        email="admin@cov.com",
        status="pending",
        auto_renew=True,
        renew_days_before=30,
    )
    defaults.update(overrides)
    s = SessionLocal()
    c = SSLCertificate(**defaults)
    s.add(c)
    s.commit()
    s.refresh(c)
    cid = c.id
    s.close()
    return cid


def _snapshot(test_db, cid):
    """读取证书关键字段快照(session 关闭前拷出, 避免 detached 访问)。"""
    SessionLocal = test_db["SessionLocal"]
    s = SessionLocal()
    try:
        c = s.query(SSLCertificate).get(cid)
        if c is None:
            return None
        return {
            "status": c.status,
            "cert_path": c.cert_path,
            "key_path": c.key_path,
            "last_renew_success": c.last_renew_success,
            "last_renew_error": c.last_renew_error,
        }
    finally:
        s.close()


# ========== _async_request_cert (353-385) ==========

def test_async_request_cert_cert_missing(test_db):
    """cert_id 不存在 → 提前 return, 不抛异常(覆盖 358-359)。"""
    req = CertRequest(domain="ghost.example.com", email="admin@cov.com")
    _async_request_cert(999999, req)  # 不存在, 静默返回


def test_async_request_cert_success_sets_paths(test_db):
    """certbot 成功 → status=active + cert_path/key_path 落库(覆盖 377-379, 含 sans 拼参 368-369)。"""
    cid = _seed_cert(test_db, domain="req-ok.example.com")
    req = CertRequest(domain="req-ok.example.com", email="admin@cov.com", sans=["alt.example.com"])
    with patch.object(mod, "_run_certbot", return_value={"success": True, "stdout": "", "stderr": ""}):
        _async_request_cert(cid, req)
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "active"
    assert snap["cert_path"] == "/etc/letsencrypt/live/req-ok.example.com/fullchain.pem"
    assert snap["key_path"] == "/etc/letsencrypt/live/req-ok.example.com/privkey.pem"
    assert snap["last_renew_success"] is True


def test_async_request_cert_failure_records_error(test_db):
    """certbot 失败 → status=error + last_renew_error 落库(覆盖 380-381)。"""
    cid = _seed_cert(test_db, domain="req-fail.example.com")
    req = CertRequest(domain="req-fail.example.com", email="admin@cov.com")
    with patch.object(mod, "_run_certbot", return_value={"success": False, "stderr": "rate limited"}):
        _async_request_cert(cid, req)
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "error"
    assert snap["last_renew_success"] is False
    assert snap["last_renew_error"] == "rate limited"


def test_async_request_cert_failure_unknown_error(test_db):
    """certbot 失败且无 stderr → last_renew_error 走 'Unknown error' 默认。"""
    cid = _seed_cert(test_db, domain="req-unk.example.com")
    req = CertRequest(domain="req-unk.example.com", email="admin@cov.com")
    with patch.object(mod, "_run_certbot", return_value={"success": False}):
        _async_request_cert(cid, req)
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "error"
    assert "Unknown error" in snap["last_renew_error"]


# ========== _async_renew_cert (390-416) ==========

def test_async_renew_cert_cert_missing(test_db):
    """cert_id 不存在 → 提前 return, 不抛异常(覆盖 395-396)。"""
    _async_renew_cert(999999, staging=True)


def test_async_renew_cert_staging_appends_flag(test_db):
    """staging=True → certbot 参数含 --staging 且走成功路径(覆盖 399-400)。"""
    cid = _seed_cert(test_db, domain="ren-staging.example.com")
    with patch.object(mod, "_run_certbot", return_value={"success": True}) as m:
        _async_renew_cert(cid, staging=True)
    args = m.call_args[0][0]
    assert "--staging" in args
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "active"
    assert snap["last_renew_success"] is True
    assert snap["last_renew_error"] is None


def test_async_renew_cert_success_clears_error(test_db):
    """续期成功 → status=active + last_renew_error 清空(覆盖 406-408)。"""
    cid = _seed_cert(test_db, domain="ren-ok.example.com", last_renew_error="old error")
    with patch.object(mod, "_run_certbot", return_value={"success": True}):
        _async_renew_cert(cid, staging=False)
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "active"
    assert snap["last_renew_error"] is None


def test_async_renew_cert_failure_sets_error(test_db):
    """续期失败 → status=error + last_renew_error 落库(覆盖 409-411)。"""
    cid = _seed_cert(test_db, domain="ren-fail.example.com")
    with patch.object(mod, "_run_certbot", return_value={"success": False, "stderr": "renew failed"}):
        _async_renew_cert(cid, staging=False)
    snap = _snapshot(test_db, cid)
    assert snap["status"] == "error"
    assert snap["last_renew_error"] == "renew failed"

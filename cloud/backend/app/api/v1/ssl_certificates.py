# -*- coding: utf-8 -*-
"""
SSL证书管理 & 自动续期 API — Phase9

功能:
- 证书状态查询 / 过期预警
- 手动申请证书 / 手动续期
- 自动续期配置
- 域名管理 (添加 / 删除 / 列出)
"""

import re
import subprocess
import ssl
import socket
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import require_platform_admin
from app.models.ssl_certificate import SSLCertificate
from app.models.user import User

router = APIRouter(tags=["SSL证书管理"])
logger = logging.getLogger(__name__)


# ============ Pydantic Schemas ============

# 严格域名正则（任务卡 55f8d345）：仅允许 a-zA-Z0-9 与连字符、点分隔，
# 拒绝空格/分号/$()/等 shell 元字符与 ``..``/``/`` 路径穿越字符，
# 防 certbot ``-d`` 参数注入/污染主机命令。
# 规则：1-253 字符；每段 label 1-63 字符、首尾为字母数字、可含连字符；
# 末段 TLD 纯字母 ≥2。证书属域名而非 IP，故不放宽至数字 TLD。
# 注意：须用普通 raw string 拼接，避免 f-string 把 ``{n,m}`` 当插值。
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63}$"
)


def _validate_domain(value: str) -> str:
    """校验单个域名，不合法抛 ValueError（pydantic 转 422）。"""
    if not isinstance(value, str) or not _DOMAIN_RE.match(value):
        raise ValueError("域名格式非法")
    return value


class CertRequest(BaseModel):
    """申请/续期证书请求"""
    domain: str = Field(..., description="域名 (如 example.com)")
    email: EmailStr = Field(default="admin@tianlian.com", description="Let's Encrypt 邮箱")
    sans: list[str] = Field(default_factory=list, description="SAN 域名列表")
    auto_renew: bool = Field(default=True, description="是否自动续期")
    renew_days_before: int = Field(default=30, ge=1, le=60, description="提前N天续期")

    @field_validator("domain")
    @classmethod
    def _check_domain(cls, v: str) -> str:
        return _validate_domain(v)

    @field_validator("sans")
    @classmethod
    def _check_sans(cls, v: list[str]) -> list[str]:
        return [_validate_domain(s) for s in v]


class RenewRequest(BaseModel):
    """手动续期请求"""
    domain: str = Field(..., max_length=255, description="域名")
    staging: bool = Field(default=False, description="使用 staging 环境测试")


class AutoRenewConfig(BaseModel):
    """自动续期配置"""
    auto_renew: bool = True
    renew_days_before: int = 30


class DomainRequest(BaseModel):
    """添加域名"""
    domain: str = Field(..., description="域名")
    email: str = Field(default="admin@tianlian.com")
    auto_renew: bool = Field(default=True)


# ============ 辅助函数 ============

def _check_remote_cert(domain: str, port: int = 443) -> dict:
    """远程检查证书信息（不依赖 certbot）"""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5)
            s.connect((domain, port))
            cert = s.getpeercert()
            not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
            not_after = not_after.replace(tzinfo=timezone.utc)
            return {
                "domain": domain,
                "issuer": cert.get("issuer", []),
                "not_after": not_after.isoformat(),
                "not_before": cert.get("notBefore", ""),
                "days_remaining": (not_after - datetime.now(timezone.utc)).days,
            }
    except Exception as e:
        logger.exception("远程证书检查失败")
        return {"domain": domain, "error": "证书检查失败"}


def _run_certbot(args: list[str], timeout: int = 120) -> dict:
    """安全执行 certbot 命令"""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "certbot 执行超时", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "certbot 未安装", "returncode": -2}
    except Exception as e:
        logger.exception("certbot 执行失败")
        return {"success": False, "stdout": "", "stderr": "certbot 执行异常", "returncode": -3}


def _detect_status(cert_entry: SSLCertificate) -> str:
    """根据剩余天数判断证书状态"""
    remaining = cert_entry.days_remaining
    if remaining is None:
        return "error"
    if remaining <= 0:
        return "expired"
    if remaining <= cert_entry.renew_days_before:
        return "expiring_soon"
    return "active"


# ============ API 端点 ============

@router.get("/certificates", summary="列出所有SSL证书")
def list_certificates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """返回所有已注册域名的 SSL 证书状态（分页）"""
    query = db.query(SSLCertificate).order_by(SSLCertificate.created_at.desc())
    total = query.count()
    certs = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for c in certs:
        items.append({
            "id": c.id,
            "domain": c.domain,
            "status": c.status,
            "not_after": c.not_after.isoformat() if c.not_after else None,
            "days_remaining": c.days_remaining,
            "auto_renew": c.auto_renew,
            "renew_days_before": c.renew_days_before,
            "last_renew_at": c.last_renew_at.isoformat() if c.last_renew_at else None,
            "last_renew_success": c.last_renew_success,
            "last_renew_error": c.last_renew_error,
            "last_check_at": c.last_check_at.isoformat() if c.last_check_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return {"total": total, "certificates": items, "page": page, "page_size": page_size}


@router.get("/certificates/{domain}", summary="查看单个证书详情")
def get_certificate(
    domain: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    cert = db.query(SSLCertificate).filter(SSLCertificate.domain == domain).first()
    if not cert:
        raise HTTPException(status_code=404, detail=f"证书 {domain} 不存在")

    return {
        "id": cert.id,
        "domain": cert.domain,
        "email": cert.email,
        "status": cert.status,
        "issuer": cert.issuer,
        "not_before": cert.not_before.isoformat() if cert.not_before else None,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "days_remaining": cert.days_remaining,
        "subject_alt_names": cert.subject_alt_names,
        "auto_renew": cert.auto_renew,
        "renew_days_before": cert.renew_days_before,
        "cert_path": cert.cert_path,
        "key_path": cert.key_path,
        "last_renew_at": cert.last_renew_at.isoformat() if cert.last_renew_at else None,
        "last_renew_success": cert.last_renew_success,
        "last_renew_error": cert.last_renew_error,
        "last_check_at": cert.last_check_at.isoformat() if cert.last_check_at else None,
    }


@router.post("/certificates", summary="申请新SSL证书")
def request_certificate(
    req: CertRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """申请 Let's Encrypt 证书（后台异步执行）"""
    existing = db.query(SSLCertificate).filter(SSLCertificate.domain == req.domain).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"域名 {req.domain} 已存在")

    cert = SSLCertificate(
        domain=req.domain,
        email=req.email,
        auto_renew=req.auto_renew,
        renew_days_before=req.renew_days_before,
        status="pending",
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)

    # 后台执行 certbot
    background_tasks.add_task(_async_request_cert, cert.id, req)

    return {
        "message": "证书申请已启动，请等待完成",
        "domain": req.domain,
        "task_id": cert.id,
    }


@router.post("/certificates/{domain}/renew", summary="手动续期证书")
def renew_certificate(
    domain: str,
    req: RenewRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """手动触发证书续期"""
    cert = db.query(SSLCertificate).filter(SSLCertificate.domain == domain).first()
    if not cert:
        raise HTTPException(status_code=404, detail=f"证书 {domain} 不存在")

    background_tasks.add_task(_async_renew_cert, cert.id, req.staging)

    return {"message": f"证书 {domain} 续期已启动", "domain": domain}


@router.put("/certificates/{domain}/config", summary="更新证书配置")
def update_certificate_config(
    domain: str,
    req: AutoRenewConfig,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    cert = db.query(SSLCertificate).filter(SSLCertificate.domain == domain).first()
    if not cert:
        raise HTTPException(status_code=404, detail=f"证书 {domain} 不存在")

    cert.auto_renew = req.auto_renew
    cert.renew_days_before = req.renew_days_before
    cert.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "配置已更新", "domain": domain, "auto_renew": cert.auto_renew}


@router.delete("/certificates/{domain}", summary="删除证书记录")
def delete_certificate(
    domain: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    cert = db.query(SSLCertificate).filter(SSLCertificate.domain == domain).first()
    if not cert:
        raise HTTPException(status_code=404, detail=f"证书 {domain} 不存在")

    db.delete(cert)
    db.commit()
    return {"message": f"证书记录 {domain} 已删除"}


@router.get("/health-check", summary="检查所有证书健康状态")
def health_check_all(
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """检查所有已注册证书的健康度"""
    certs = db.query(SSLCertificate).order_by(SSLCertificate.domain).all()

    results = []
    for c in certs:
        new_status = _detect_status(c)
        c.status = new_status
        c.last_check_at = datetime.now(timezone.utc)
        results.append({
            "domain": c.domain,
            "status": new_status,
            "days_remaining": c.days_remaining,
            "auto_renew": c.auto_renew,
        })

    db.commit()

    total = len(results)
    healthy = sum(1 for r in results if r["status"] == "active")
    expiring = sum(1 for r in results if r["status"] == "expiring_soon")
    expired = sum(1 for r in results if r["status"] == "expired")

    return {
        "total": total,
        "healthy": healthy,
        "expiring_soon": expiring,
        "expired": expired,
        "certificates": results,
    }


@router.post("/auto-renew", summary="执行一次自动续期检查")
def trigger_auto_renew(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """手动触发自动续期扫描（也可由 cron 调用）"""
    certs = db.query(SSLCertificate).filter(SSLCertificate.auto_renew == True).all()
    to_renew = [c for c in certs if c.needs_renewal]

    for c in to_renew:
        background_tasks.add_task(_async_renew_cert, c.id, False)

    return {
        "total_certificates": len(certs),
        "needs_renewal": len(to_renew),
        "domains": [c.domain for c in to_renew],
    }


# ============ 后台任务 ============

def _async_request_cert(cert_id: int, req: CertRequest):
    """后台: 申请证书"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        cert = db.query(SSLCertificate).get(cert_id)
        if not cert:
            return

        certbot_args = [
            "certbot", "certonly", "--nginx",
            "--non-interactive",
            "--agree-tos",
            "--email", req.email,
            "-d", req.domain,
        ]
        for s in req.sans:
            certbot_args.extend(["-d", s])

        result = _run_certbot(certbot_args)

        cert.last_renew_at = datetime.now(timezone.utc)
        cert.last_renew_success = result["success"]
        cert.status = "active" if result["success"] else "error"

        if result["success"]:
            cert.cert_path = f"/etc/letsencrypt/live/{req.domain}/fullchain.pem"
            cert.key_path = f"/etc/letsencrypt/live/{req.domain}/privkey.pem"
        else:
            cert.last_renew_error = result.get("stderr", "Unknown error")[:500]

        db.commit()
    finally:
        db.close()


def _async_renew_cert(cert_id: int, staging: bool = False):
    """后台: 续期证书"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        cert = db.query(SSLCertificate).get(cert_id)
        if not cert:
            return

        certbot_args = ["certbot", "renew", "--quiet"]
        if staging:
            certbot_args.append("--staging")

        result = _run_certbot(certbot_args)

        cert.last_renew_at = datetime.now(timezone.utc)
        cert.last_renew_success = result["success"]
        if result["success"]:
            cert.status = "active"
            cert.last_renew_error = None
        else:
            cert.status = "error"
            cert.last_renew_error = result.get("stderr", "Unknown error")[:500]

        cert.last_check_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

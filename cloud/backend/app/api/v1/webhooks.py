# -*- coding: utf-8 -*-
"""
出站 Webhook 管理 API — SPEC §2.6

功能:
- Webhook CRUD (创建 / 列表 / 详情 / 更新 / 删除)
- 测试发送 POST /webhooks/{id}/test
- 投递日志 GET /webhooks/{id}/deliveries
- 启用/停用 PUT /webhooks/{id}/toggle
"""
import json
import hmac
import hashlib
import asyncio
import time
import httpx
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_async_db
from app.core.response import success_response, paginated_response
from app.core.url_safety import validate_external_url, UnsafeURLError
from app.models.webhook import Webhook, WebhookDelivery, WEBHOOK_EVENT_TYPES, DELIVERY_STATUS
from app.middleware.permission import require_write_permission
from app.api.deps import require_platform_admin

# 越权高危修复（审计 #4）: Webhook 模型无 team_id 归属字段，零归属隔离——
# 任意 operator 可改/删/重定向任意 webhook 回调 URL，任意认证用户可读全平台
# 投递日志 payload 原文。全模块 8 端点（含投递日志读）一律收紧 platform admin，
# 模式对齐 vpp.py / teams.py（require_platform_admin，无迁移）。
router = APIRouter(dependencies=[
    Depends(require_write_permission("notification:manage")),
    Depends(require_platform_admin),
])


# ============ Schemas ============

class WebhookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Webhook 名称")
    url: str = Field(..., min_length=1, max_length=500, description="回调 URL")
    event_types: list[str] = Field(default_factory=list, description="订阅事件类型 alert/ticket/order/device")
    secret: Optional[str] = Field(None, max_length=256, description="HMAC-SHA256 签名密钥")
    retry_count: int = Field(default=3, ge=0, le=10, description="失败重试次数")
    retry_interval: int = Field(default=60, ge=1, le=3600, description="重试间隔(秒)")
    timeout: int = Field(default=10, ge=1, le=120, description="请求超时(秒)")
    enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(None, max_length=500, description="描述")

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        """SSRF 防护:回调 URL 必须指向公网 http/https 端点 (卡 310ac90a)"""
        validate_external_url(v)
        return v


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    event_types: Optional[list[str]] = None
    secret: Optional[str] = Field(None, max_length=256)
    retry_count: Optional[int] = Field(None, ge=0, le=10)
    retry_interval: Optional[int] = Field(None, ge=1, le=3600)
    timeout: Optional[int] = Field(None, ge=1, le=120)
    enabled: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: Optional[str]) -> Optional[str]:
        """SSRF 防护:url 提供时必须指向公网 http/https 端点 (卡 310ac90a)"""
        if v is not None:
            validate_external_url(v)
        return v


class ToggleRequest(BaseModel):
    enabled: bool


# ============ Helpers ============

def _parse_event_types(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def _validate_event_types(types: list[str]):
    for t in types:
        if t not in WEBHOOK_EVENT_TYPES:
            raise HTTPException(400, f"event_type 取值: {WEBHOOK_EVENT_TYPES}, 得到 '{t}'")


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    """secret 打码（卡 0ff95dca）：仅保留前3 + **** + 尾4。短 secret（≤8）全打码
    防泄露。None 原样返回。原文仅在 POST 创建响应一次性回显（_to_dict(expose_secret)）。
    """
    if secret is None:
        return None
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"


def _to_dict(wh: Webhook, expose_secret: bool = False) -> dict:
    """Webhook ORM → dict。secret 默认打码（卡 0ff95dca）；expose_secret=True
    仅用于 POST 创建响应一次性回显原文（之后无法再取回）。"""
    return {
        "id": wh.id,
        "name": wh.name,
        "url": wh.url,
        "event_types": _parse_event_types(wh.event_types),
        "secret": wh.secret if expose_secret else _mask_secret(wh.secret),
        "retry_count": wh.retry_count,
        "retry_interval": wh.retry_interval,
        "timeout": wh.timeout,
        "enabled": wh.enabled,
        "description": wh.description,
        "created_at": wh.created_at.isoformat() if wh.created_at else None,
        "updated_at": wh.updated_at.isoformat() if wh.updated_at else None,
    }


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "webhook_id": d.webhook_id,
        "event_type": d.event_type,
        "payload": _safe_json(d.payload),
        "status_code": d.status_code,
        "response_body": d.response_body,
        "status": d.status,
        "duration_ms": d.duration_ms,
        "attempt": d.attempt,
        "error_message": d.error_message,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _safe_json(raw: Optional[str]) -> any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _compute_signature(secret: str, timestamp: str, body: str) -> str:
    """计算防重放签名。

    签名格式: HMAC-SHA256(secret, "{timestamp}.{body}")
    timestamp 为秒级整数字符串。接收方应校验签名并比对 timestamp 与当前时间
    (拒绝过期时间戳), 以检测重放攻击。
    """
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()


async def _deliver(webhook: Webhook, payload: dict, db: AsyncSession, event_type: str = "test"):
    """实际发送 HTTP 请求并记录投递日志 (异步会话, 卡52f731ac)"""
    body = json.dumps(payload, ensure_ascii=False)
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event_type=event_type,
        payload=body,
        status="pending",
        attempt=1,
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)

    # 发送前二次校验:防 DNS 重绑定 / 数据投毒 (TOCTOU)。库内 URL 可能在创建后
    # 因 DNS 变更或直接写库而指向内网,此处再次拦截,标 failed 并记原因,不外发。
    try:
        validate_external_url(webhook.url)
    except UnsafeURLError as exc:
        delivery.status = "failed"
        delivery.error_message = f"URL 安全校验失败: {exc}"[:1000]
        await db.commit()
        await db.refresh(delivery)
        return delivery

    start = time.monotonic()
    max_attempts = webhook.retry_count + 1
    try:
        for attempt in range(1, max_attempts + 1):
            delivery.attempt = attempt
            # 卡 211f5c97:每 attempt 重建请求头。ts/签名循环内重算 — 合法配置
            # retry_count(≤10)×retry_interval(≤3600s) 下重试可晚至 ~10h,若循环外
            # 一次构建,接收方按新鲜度契约(拒绝过期时间戳)必拒晚到重试 → 重试自毁。
            # X-Webhook-Delivery-Id 明文幂等头(不参与签名,签名继续覆盖 "{ts}.{body}",
            # 对齐业界惯例):接收方凭此去重"已处理但响应丢失"的网络异常重试。
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Delivery-Id": str(delivery.id),
            }
            if webhook.secret:
                # 签名绑定时间戳防重放: HMAC-SHA256(secret, "{timestamp}.{body}")
                # 接收方凭 X-Webhook-Timestamp 校验新鲜度, 凭签名验证完整性
                ts = str(int(time.time()))
                headers["X-Webhook-Timestamp"] = ts
                headers["X-Webhook-Signature"] = _compute_signature(webhook.secret, ts, body)
                headers["X-Webhook-Signature-Version"] = "v1"
            try:
                async with httpx.AsyncClient(timeout=webhook.timeout) as client:
                    resp = await client.post(webhook.url, content=body, headers=headers)
            except Exception as exc:
                # 网络异常可重试 (对齐 channel_providers 卡 8d98ebe3 语义)
                delivery.duration_ms = int((time.monotonic() - start) * 1000)
                delivery.error_message = str(exc)[:1000]
                if attempt < max_attempts:
                    delivery.status = "retrying"
                    await db.commit()
                    await asyncio.sleep(webhook.retry_interval)
                    continue
                delivery.status = "failed"
                break

            delivery.status_code = resp.status_code
            delivery.response_body = resp.text[:2000]
            delivery.duration_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code < 400:
                delivery.status = "success"
                break
            if resp.status_code >= 500 and attempt < max_attempts:
                # 5xx 可重试;4xx 为终态失败不重试
                delivery.status = "retrying"
                await db.commit()
                await asyncio.sleep(webhook.retry_interval)
                continue
            delivery.status = "failed"
            break
    except Exception as exc:
        # 兜底:重试循环本身的意外异常仍记 failed,不外泄
        delivery.status = "failed"
        delivery.error_message = str(exc)[:1000]
        delivery.duration_ms = int((time.monotonic() - start) * 1000)

    await db.commit()
    await db.refresh(delivery)
    return delivery


# ============ CRUD ============

@router.get("", summary="Webhook 列表")
def list_webhooks(
    enabled: Optional[bool] = Query(None, description="按启用状态筛选"),
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    keyword: Optional[str] = Query(None, description="按名称/URL模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Webhook)
    if enabled is not None:
        q = q.filter(Webhook.enabled == enabled)
    if event_type:
        q = q.filter(Webhook.event_types.like(f'%"{event_type}"%'))
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(Webhook.name.like(kw) | Webhook.url.like(kw))

    total = q.count()
    items = q.order_by(desc(Webhook.id)).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_to_dict(w) for w in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", summary="创建 Webhook")
def create_webhook(data: WebhookCreate, db: Session = Depends(get_db)):
    _validate_event_types(data.event_types)
    wh = Webhook(
        name=data.name,
        url=data.url,
        event_types=json.dumps(data.event_types, ensure_ascii=False),
        secret=data.secret,
        retry_count=data.retry_count,
        retry_interval=data.retry_interval,
        timeout=data.timeout,
        enabled=data.enabled,
        description=data.description,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    # 卡 0ff95dca: secret 原文仅创建响应一次性回显
    return success_response(_to_dict(wh, expose_secret=True), message="Webhook 创建成功")


@router.get("/{webhook_id}", summary="Webhook 详情")
def get_webhook(webhook_id: int, db: Session = Depends(get_db)):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")
    return success_response(_to_dict(wh))


@router.put("/{webhook_id}", summary="更新 Webhook")
def update_webhook(webhook_id: int, data: WebhookUpdate, db: Session = Depends(get_db)):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")

    payload = data.model_dump(exclude_unset=True)
    if "event_types" in payload and payload["event_types"] is not None:
        _validate_event_types(payload["event_types"])
        payload["event_types"] = json.dumps(payload["event_types"], ensure_ascii=False)

    for k, v in payload.items():
        setattr(wh, k, v)

    db.commit()
    db.refresh(wh)
    return success_response(_to_dict(wh), message="Webhook 更新成功")


@router.delete("/{webhook_id}", summary="删除 Webhook")
def delete_webhook(webhook_id: int, db: Session = Depends(get_db)):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")
    db.delete(wh)
    db.commit()
    return success_response({"id": webhook_id}, message="Webhook 已删除")


# ============ 启用/停用 ============

@router.put("/{webhook_id}/toggle", summary="启用/停用 Webhook")
def toggle_webhook(webhook_id: int, req: ToggleRequest, db: Session = Depends(get_db)):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")
    wh.enabled = req.enabled
    db.commit()
    db.refresh(wh)
    return success_response(_to_dict(wh), message=f"Webhook 已{'启用' if req.enabled else '停用'}")


# ============ 测试发送 ============

@router.post("/{webhook_id}/test", summary="发送测试事件")
async def test_webhook(webhook_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_async_db)):
    wh = (await db.execute(select(Webhook).where(Webhook.id == webhook_id))).scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")

    test_payload = {
        "event": "test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "webhook_id": wh.id,
            "webhook_name": wh.name,
            "message": "这是一条来自天链V3的测试事件",
        },
    }

    # 卡 e7d88c10:_deliver 按 retry_count(0-10)+retry_interval(1-3600s) 退避重试,
    # 内联 await 会使测试请求最长挂起 ~10h。改为后台投递,立即返回 queued,
    # 结果经 GET /{webhook_id}/deliveries 查询;yield 依赖的 db 会话在后台任务完成后才关闭。
    background_tasks.add_task(_deliver, wh, test_payload, db, event_type="test")
    return success_response(
        {"status": "queued", "webhook_id": wh.id},
        message="测试事件已加入后台投递,请稍后通过投递日志查询结果",
    )


# ============ 投递日志 ============

@router.get("/{webhook_id}/deliveries", summary="投递日志")
def list_deliveries(
    webhook_id: int,
    status: Optional[str] = Query(None, description="按状态筛选 success/failed/pending/retrying"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(404, "Webhook 不存在")

    q = db.query(WebhookDelivery).filter(WebhookDelivery.webhook_id == webhook_id)
    if status:
        if status not in DELIVERY_STATUS:
            raise HTTPException(400, f"status 取值: {DELIVERY_STATUS}")
        q = q.filter(WebhookDelivery.status == status)

    total = q.count()
    items = q.order_by(desc(WebhookDelivery.id)).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_delivery_to_dict(d) for d in items],
        total=total, page=page, page_size=page_size,
    )

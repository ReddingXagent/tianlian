"""手动开票申请服务 (用户端云端契约 §5, 工作卡 a09f8a21)

职责:
- 用户端: 申请(校验订单 PAID + 未开票, 金额汇总元→分) / 列表 / 详情(签名URL) / 补发邮件
- 运营端: 列表(team 隔离) / 上传发票文件(magic bytes, ISSUED+通知) / 拒绝(REJECTED)

状态机: PENDING ──upload──▶ ISSUED; PENDING ──reject──▶ REJECTED (用户可重申, 新建一条)。
金额单位: 分整数 (契约 §6), 汇总 sum(paid_amount[元]) → int(round(sum*100))。
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.invoice_request import (
    InvoiceRequest,
    InvoiceRequestStatus,
    InvoiceMode,
    InvoiceTitleType,
    InvoiceFileType,
)
from app.models.station import Station
from app.models.user import User
from app.services import invoice_notification
from app.services import wx_subscribe_msg

logger = logging.getLogger(__name__)

MAX_INVOICE_FILE_BYTES = 10 * 1024 * 1024  # 10MB (契约 §5.4)

# (magic bytes → 文件类型) —— 校验文件头防伪造扩展名 (与 enterprise_registration 同源)
_INVOICE_MAGIC = [
    (b"%PDF", InvoiceFileType.PDF),        # PDF
    (b"\x89PNG", InvoiceFileType.IMAGE),   # PNG
    (b"\xff\xd8\xff", InvoiceFileType.IMAGE),  # JPEG
    (b"PK\x03\x04", InvoiceFileType.OFD),  # OFD (ZIP 容器)
]

# content_type 软校验白名单
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/ofd",
}

_INVOICE_UPLOAD_DIR = os.path.join("uploads", "invoices")


class InvoiceError(Exception):
    """开票领域错误。status 为对应 HTTP 状态码, message 为用户可见原因。

    reason (卡 418a675a): 契约 §6 原因码, 仅业务状态类错误标注 (订单不存在/未支付/
    重复申请/申请不存在/未开具/跨团队/场站缺失/金额异常)。C 端路由据此转
    biz_error (HTTP 200 + code!=0 + message=原因码); 输入校验类 (抬头空/税号缺失/
    邮箱空) 不标 reason, 保留 HTTPException 422。ops 端点不读 reason, 行为不变。
    """

    def __init__(self, message: str, status: int = 400, reason: Optional[str] = None):
        self.message = message
        self.status = status
        self.reason = reason
        super().__init__(message)


# ─── 工具 ────────────────────────────────────────────────────────────────────

def _dump_order_ids(order_ids: list[str]) -> str:
    return json.dumps(list(order_ids), ensure_ascii=False)


def _parse_order_ids(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def _amount_yuan_to_cents(value: Optional[Decimal]) -> int:
    """元(Decimal) → 分(int), 向最近的整数四舍五入。"""
    if value is None:
        return 0
    return int(round(Decimal(value) * Decimal(100)))


def _iso_utc(value: Optional[datetime]) -> Optional[str]:
    """ISO8601 统一带时区 (契约 §6)。

    SQLite DateTime 列读回 naive (写入的 UTC 丢 tzinfo); isoformat() 无 +00:00
    后缀 → 端侧解析歧义。naive 一律按 UTC 解释补后缀; PG 列带 tz 时原样输出。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _detect_file_type(content: bytes) -> Optional[InvoiceFileType]:
    for magic, ftype in _INVOICE_MAGIC:
        if content.startswith(magic):
            return ftype
    return None


# ─── 用户端: 申请 ──────────────────────────────────────────────────────────────

def _used_order_nos(db: Session, user_id: int) -> set[str]:
    """用户已占用的订单号集合 (存在 PENDING/ISSUED 申请 → 视为已开票, 不可重复申请)。"""
    active = (
        db.query(InvoiceRequest)
        .filter(
            InvoiceRequest.user_id == user_id,
            InvoiceRequest.status.in_(
                [InvoiceRequestStatus.PENDING, InvoiceRequestStatus.ISSUED]
            ),
        )
        .all()
    )
    used: set[str] = set()
    for r in active:
        used.update(_parse_order_ids(r.order_ids))
    return used


def apply_invoice(
    db: Session,
    user: User,
    order_ids: list[str],
    title_type: InvoiceTitleType,
    title_name: str,
    tax_number: Optional[str] = None,
    email: Optional[str] = None,
    remark: Optional[str] = None,
) -> InvoiceRequest:
    """用户提交开票申请 (契约 §5.1)。

    校验:
    - order_ids 非空;
    - 每张订单存在 + 归属本人 + payment_status=PAID;
    - 每张订单未在另一条 PENDING/ISSUED 申请中 (REJECTED 不占位, 可重申);
    - 全部订单同属一个 team (跨团队 → 422, 分开申请; 卡 71062d84);
    - 订单场站存在且有 team (缺失 → 422, 防平台孤儿申请; 卡 71062d84);
    - title_type=company → tax_number 必填。
    """
    if not order_ids:
        raise InvoiceError("至少选择一张订单", 422)
    # 去重保序
    seen: set[str] = set()
    unique_ids: list[str] = []
    for oid in order_ids:
        if oid and oid not in seen:
            seen.add(oid)
            unique_ids.append(oid)
    if not unique_ids:
        raise InvoiceError("至少选择一张订单", 422)

    if not title_name or not title_name.strip():
        raise InvoiceError("发票抬头不能为空", 422)
    if title_type == InvoiceTitleType.COMPANY and not (tax_number and tax_number.strip()):
        raise InvoiceError("企业抬头必须填写税号", 422)

    # 已占用订单号 (用户级)
    used = _used_order_nos(db, user.id)

    # 批量拉取订单 (卡e6ae624b: 消除 N+1 — 原 for 内逐条 db.query(ChargingOrder))
    orders = (
        db.query(ChargingOrder)
        .filter(ChargingOrder.order_no.in_(unique_ids))
        .all()
    )
    order_map = {o.order_no: o for o in orders}

    # 批量拉取 station → team_id (原 for 内逐条 db.query(Station.team_id))
    station_ids = [o.station_id for o in order_map.values()]
    station_team_map: dict = {}
    if station_ids:
        station_rows = (
            db.query(Station.id, Station.team_id)
            .filter(Station.id.in_(station_ids))
            .all()
        )
        station_team_map = {sid: tid for sid, tid in station_rows}

    total_cents = 0
    team_ids: set = set()
    first_team_id: Optional[int] = None
    for oid in unique_ids:
        order = order_map.get(oid)
        if order is None:
            raise InvoiceError(f"订单不存在: {oid}", 404, reason="ORDER_NOT_FOUND")
        if order.user_id != user.id:
            # 不泄露他人订单存在性, 统一报「不存在」
            raise InvoiceError(f"订单不存在: {oid}", 404, reason="ORDER_NOT_FOUND")
        if order.payment_status != OrderPaymentStatus.PAID:
            raise InvoiceError(f"订单未支付, 无法开票: {oid}", 422, reason="ORDER_NOT_PAID")
        if order.paid_amount is None:
            # 卡4b14971e: PAID 订单实付金额为 NULL (历史/raw SQL 脏数据) 属异常状态,
            # 显式拒绝而非静默归零开 0 元发票 (ORM 正常路径 None 已被列 default 归零,
            # 此 guard 防的是绕过 ORM 写入的 DB 层 NULL)
            raise InvoiceError(
                f"订单支付金额异常, 无法开票: {oid}", 422, reason="ORDER_AMOUNT_INVALID"
            )
        if oid in used:
            raise InvoiceError(
                f"订单已申请开票, 请勿重复: {oid}", 409, reason="INVOICE_DUPLICATE"
            )

        # 卡 71062d84: 场站已删/缺失 → team 无法解析, 拒绝而非静默挂 team_id=None
        # (团队级 ops 全不可见, 申请永久滞留 PENDING)
        order_team = station_team_map.get(order.station_id)
        if order_team is None:
            raise InvoiceError(
                f"订单所属场站不存在, 无法开票: {oid}", 422, reason="STATION_NOT_FOUND"
            )
        if first_team_id is None:
            first_team_id = order_team
        team_ids.add(order_team)

        total_cents += _amount_yuan_to_cents(order.paid_amount)

    # 卡 71062d84: 单张申请只允许挂一个 team (InvoiceRequest.team_id 单值)。
    # 跨团队合并 → 整张发票只能挂首单团队, 其余团队的运营在 team 隔离列表
    # 永不可见、无法审核; 拆单方案会把一次用户操作变成多条申请且响应结构
    # 变更 (invoice_id 单值), 破坏已交付契约§5.1 前端; 故拒绝并提示分开申请。
    if len(team_ids) > 1:
        raise InvoiceError(
            "所选订单分属不同运营团队, 请按团队分开申请开票", 422,
            reason="CROSS_TEAM_ORDERS",
        )
    team_id = first_team_id

    # TOCTOU 防护 (卡4b14971e): 首次占用检查 (上方 used) 与 commit 之间存在并发窗口,
    # 两个并发请求可同时通过首次检查 → 同一订单出现在两条 PENDING 申请中。
    # 提交前对同一用户的占用集合二次校验, 将竞态窗口收敛到「二次校验→commit」极短瞬间。
    used_now = _used_order_nos(db, user.id)
    for oid in unique_ids:
        if oid in used_now:
            raise InvoiceError(
                f"订单已申请开票, 请勿重复: {oid}", 409, reason="INVOICE_DUPLICATE"
            )

    req = InvoiceRequest(
        order_ids=_dump_order_ids(unique_ids),
        user_id=user.id,
        team_id=team_id,
        title_type=title_type,
        title_name=title_name.strip(),
        tax_number=(tax_number.strip() if tax_number else None),
        email=(email.strip() if email else None),
        remark=remark,
        amount=total_cents,
        invoice_mode=InvoiceMode.MANUAL,
        status=InvoiceRequestStatus.PENDING,
        applied_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    logger.info(
        "开票申请已提交 id=%s user=%s amount=%s分 orders=%s",
        req.id, user.id, req.amount, unique_ids,
    )
    return req


# ─── 用户端: 列表 / 详情 ─────────────────────────────────────────────────────

def _user_list_item(r: InvoiceRequest) -> dict:
    """契约 §5.2 列表轻量版 (无 invoice_file)。

    voided 族字段 (Phase2-B2, 卡 f42bdf5a, R1 方案b): 契约只增不破 ——
    新增可选字段, 未红冲恒 voided=False。
    """
    return {
        "invoice_id": r.id,
        "status": r.status.value,
        "amount": r.amount,
        "title_type": r.title_type.value,
        "title_name": r.title_name,
        "tax_number": r.tax_number,
        "order_ids": _parse_order_ids(r.order_ids),
        "email": r.email,
        "applied_at": _iso_utc(r.applied_at),
        "reviewed_at": _iso_utc(r.reviewed_at),
        "reject_reason": r.reject_reason,
        "voided": bool(r.voided),
        "void_reason": r.void_reason,
        "voided_at": _iso_utc(r.voided_at),
        "created_at": _iso_utc(r.created_at),
    }


def list_user_invoices(
    db: Session,
    user: User,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    q = db.query(InvoiceRequest).filter(InvoiceRequest.user_id == user.id)
    if status:
        q = q.filter(InvoiceRequest.status == status)
    total = q.count()
    items = (
        q.order_by(InvoiceRequest.applied_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_user_list_item(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _file_info_dict(r: InvoiceRequest, base_url: str) -> Optional[dict]:
    """契约 §5.2 invoice_file: 仅 ISSUED 返回 (含 2h 签名 URL)。"""
    if r.status != InvoiceRequestStatus.ISSUED or not r.invoice_file_path:
        return None
    return {
        "file_url": invoice_notification.build_signed_file_url(r.id, base_url),
        "file_type": r.invoice_file_type.value if r.invoice_file_type else None,
        "file_name": r.invoice_file_name,
    }


def get_user_invoice(
    db: Session, user: User, invoice_id: int, base_url: str
) -> dict:
    r = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.id == invoice_id)
        .first()
    )
    if r is None or r.user_id != user.id:
        raise InvoiceError(
            "开票申请不存在", 404, reason="INVOICE_REQUEST_NOT_FOUND"
        )
    data = _user_list_item(r)
    data["invoice_file"] = _file_info_dict(r, base_url)
    data["issued_at"] = _iso_utc(r.reviewed_at)
    return data


# ─── 用户端: 补发 / 改发邮箱 (契约 §5.3) ───────────────────────────────────────

def resend_invoice_email(
    db: Session, user: User, invoice_id: int, email: str
) -> bool:
    r = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.id == invoice_id)
        .first()
    )
    if r is None or r.user_id != user.id:
        raise InvoiceError(
            "开票申请不存在", 404, reason="INVOICE_REQUEST_NOT_FOUND"
        )
    if r.status != InvoiceRequestStatus.ISSUED:
        raise InvoiceError("发票尚未开具, 暂无法发送", 422, reason="INVOICE_NOT_ISSUED")
    if not email or not email.strip():
        raise InvoiceError("邮箱不能为空", 422)

    # 改发: 更新申请邮箱 (后续通知以最新邮箱为准)
    r.email = email.strip()
    db.commit()
    db.refresh(r)

    subject = f"【天链】您的发票 (申请单 #{r.id})"
    body = invoice_notification._build_issued_email_body(
        r, invoice_notification.build_signed_file_url(r.id, _noop_base())
    )
    return invoice_notification.send_invoice_email(
        email.strip(), subject, body, r.invoice_file_path
    )


def _noop_base() -> str:
    """补发/开票完成邮件内文件链接的 base (无 Request 上下文时读取配置)。

    读 settings.PUBLIC_BASE_URL (云端对外可访问域名); 未配置时回退空串
    (相对路径) 并记 warning 告警运维, 不再硬编码假域名 tianlian.example
    (卡 283c1f12, 契约 §5.5)。build_signed_file_url 签名与 2h 时效逻辑不变,
    仅改 base 来源; token 仍由 itsdangerous 签发, verify_file_token 不受影响。
    """
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        logger.warning(
            "PUBLIC_BASE_URL 未配置, 开票邮件文件下载链接退化为相对路径, "
            "请配置为对外可访问域名 (契约 §5.5)"
        )
    return base


# ─── 运营端: 列表 (team 隔离) ─────────────────────────────────────────────────

def _ops_list_item(r: InvoiceRequest) -> dict:
    issued_at = _iso_utc(r.reviewed_at) if r.status == InvoiceRequestStatus.ISSUED else None
    return {
        "id": r.id,
        "user_id": r.user_id,
        "team_id": r.team_id,
        "status": r.status.value,
        "amount": r.amount,
        "amount_yuan": round(r.amount / 100, 2) if r.amount else 0.0,
        "title_type": r.title_type.value,
        "title_name": r.title_name,
        "tax_number": r.tax_number,
        "email": r.email,
        "remark": r.remark,
        "order_ids": _parse_order_ids(r.order_ids),
        "invoice_mode": r.invoice_mode.value,
        "invoice_file_name": r.invoice_file_name,
        "invoice_file_type": r.invoice_file_type.value if r.invoice_file_type else None,
        "reviewed_by": r.reviewed_by,
        # 契约 §5.4 「记录 issuer/issued_at」: 与 reviewed_by/reviewed_at 同源双写
        # (issuer=处理运营, issued_at 仅 ISSUED 有值 — REJECTED 时为 None)
        "issuer": r.reviewed_by,
        "issued_at": issued_at,
        "reviewed_at": _iso_utc(r.reviewed_at),
        "reject_reason": r.reject_reason,
        # 红冲标记 (Phase2-B2, 卡 f42bdf5a, R1 方案b): status 保持 issued, 打 voided 标记
        "voided": bool(r.voided),
        "void_reason": r.void_reason,
        "voided_by": r.voided_by,
        "voided_at": _iso_utc(r.voided_at),
        "applied_at": _iso_utc(r.applied_at),
        "created_at": _iso_utc(r.created_at),
    }


def list_ops_requests(
    db: Session,
    user: User,
    team_scope_value: Optional[int],
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """运营开票申请列表。team_scope_value=None → 平台级全量; 否则按 team 过滤。"""
    q = db.query(InvoiceRequest)
    if team_scope_value is not None:
        q = q.filter(InvoiceRequest.team_id == team_scope_value)
    if status:
        q = q.filter(InvoiceRequest.status == status)
    total = q.count()
    items = (
        q.order_by(InvoiceRequest.applied_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_ops_list_item(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _get_ops_request(
    db: Session, invoice_id: int, user: User, assert_team_access
) -> InvoiceRequest:
    """取申请单并校验团队归属 (assert_team_access 由 router 注入, 复用 deps)。"""
    r = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.id == invoice_id)
        .first()
    )
    if r is None:
        raise InvoiceError("开票申请不存在", 404)
    assert_team_access(user, r.team_id)  # admin 豁免; 跨团队 → 404
    return r


# ─── 运营端: 上传发票文件 (契约 §5.4) ──────────────────────────────────────────

def upload_invoice_file(
    db: Session,
    user: User,
    invoice_id: int,
    file_name: str,
    content: bytes,
    content_type: Optional[str],
    assert_team_access,
) -> InvoiceRequest:
    """运营上传发票文件 → ISSUED + 触发通知。

    校验: content_type 软校验 + size ≤10MB + magic bytes 硬校验;
    状态: 仅 PENDING 可上传; 落盘 uploads/invoices/, status→ISSUED。
    """
    r = _get_ops_request(db, invoice_id, user, assert_team_access)
    if r.status != InvoiceRequestStatus.PENDING:
        raise InvoiceError(
            f"仅待开票状态可上传发票, 当前: {r.status.value}", 400
        )

    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvoiceError(f"不支持的文件类型: {content_type}", 400)
    if not content:
        raise InvoiceError("文件为空", 400)
    if len(content) > MAX_INVOICE_FILE_BYTES:
        raise InvoiceError("文件超过 10MB 上限", 400)

    ftype = _detect_file_type(content)
    if ftype is None:
        raise InvoiceError("文件内容与声明类型不符, 校验失败", 400)

    ext = {"pdf": "pdf", "ofd": "ofd", "image": "jpg"}[ftype.value]
    os.makedirs(_INVOICE_UPLOAD_DIR, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(_INVOICE_UPLOAD_DIR, saved_name)
    with open(fpath, "wb") as fp:
        fp.write(content)

    r.invoice_file_path = fpath
    r.invoice_file_name = file_name or saved_name
    r.invoice_file_type = ftype
    r.status = InvoiceRequestStatus.ISSUED
    r.reviewed_by = user.id
    r.reviewed_at = datetime.now(timezone.utc)
    r.reject_reason = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        # 卡4b14971e 修复点3: commit 失败时清理已落盘文件, 避免磁盘孤儿 (文件已写但 DB 无引用)
        try:
            os.remove(fpath)
        except OSError:
            logger.warning("孤儿发票文件清理失败 path=%s", fpath)
        raise
    db.refresh(r)
    logger.info(
        "发票已上传开具 id=%s operator=%s type=%s file=%s",
        r.id, user.id, ftype.value, saved_name,
    )

    # 通知钩子 (best-effort, 不阻断主流程)
    # 卡 3591ea8f: 解析 openid 后传入, 触发IM-B订阅消息真实发送 (无 openid/未配置则降级日志)
    try:
        openid = wx_subscribe_msg.resolve_openid(db, r)
    except Exception:
        logger.exception("resolve_openid 异常 invoice_id=%s", r.id)
        openid = None
    # 卡 f4288442: 构建签名下载链接传入邮件钩子, 否则 _build_issued_email_body 收到
    # file_url=None, 开票完成邮件正文不含发票下载链接 (与 resend_invoice_email 同源)。
    file_url = invoice_notification.build_signed_file_url(r.id, _noop_base())
    try:
        # 卡 5a280e1a: 传 db 供 App push 按 openid 查 device tokens (多设备分发)
        invoice_notification.notify_invoice_issued(
            r, file_url=file_url, db=db, openid=openid
        )
    except Exception:
        logger.exception("开票通知钩子异常 invoice_id=%s", r.id)

    return r


# ─── 运营端: 拒绝开票 (契约 §5.4) ──────────────────────────────────────────────

def reject_invoice_request(
    db: Session,
    user: User,
    invoice_id: int,
    reject_reason: str,
    assert_team_access,
) -> InvoiceRequest:
    """拒绝开票 → REJECTED; 用户可对同一订单重新申请 (新建 InvoiceRequest)。"""
    r = _get_ops_request(db, invoice_id, user, assert_team_access)
    if r.status != InvoiceRequestStatus.PENDING:
        raise InvoiceError(
            f"仅待开票状态可拒绝, 当前: {r.status.value}", 400
        )
    if not reject_reason or not reject_reason.strip():
        raise InvoiceError("拒绝原因不能为空", 422)

    r.status = InvoiceRequestStatus.REJECTED
    r.reject_reason = reject_reason.strip()
    r.reviewed_by = user.id
    r.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    logger.info("开票申请已拒绝 id=%s operator=%s", r.id, user.id)

    # 通知钩子 (卡4b14971e 修复点2): best-effort 通知用户被拒, 异常仅记日志不阻断主流程
    # 卡 3591ea8f: 解析 openid 触发IM-B订阅消息真实发送 (无 openid/未配置则降级日志)
    try:
        openid = wx_subscribe_msg.resolve_openid(db, r)
    except Exception:
        logger.exception("resolve_openid 异常 invoice_id=%s", r.id)
        openid = None
    try:
        # 卡 5a280e1a: 传 db 供 App push 按 openid 查 device tokens (多设备分发)
        invoice_notification.notify_invoice_rejected(r, db=db, openid=openid)
    except Exception:
        logger.exception("拒绝通知钩子异常 invoice_id=%s", r.id)
    return r


def get_invoice_for_download(db: Session, invoice_id: int) -> Optional[InvoiceRequest]:
    """签名 URL 校验通过后, 取申请单用于文件下载 (仅 ISSUED 可下载)。"""
    r = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.id == invoice_id)
        .first()
    )
    if r is None or r.status != InvoiceRequestStatus.ISSUED:
        return None
    return r


# ─── 运营端: 红冲 (Phase2-B2, 卡 f42bdf5a; R1 方案b) ──────────────────────────

def void_invoice_request(
    db: Session,
    user: User,
    invoice_id: int,
    reason: str,
    assert_team_access,
) -> InvoiceRequest:
    """红冲已开发票 (旧 OpsInvoice /void 能力迁入新体系)。

    R1 方案b (丁哥拍板): status 三态 pending/issued/rejected 不变 —— 红冲只在
    ISSUED 发票上打 voided 标记, 契约只增不破 (响应新增可选字段)。

    守卫: 仅 ISSUED 可红冲; 已红冲重复红冲 → 400 (锁非幂等: 防覆盖首红冲审计记录);
    reason 必填 (strip 后非空)。红冲不动金额/发票文件 (保留原票追溯)。
    """
    r = _get_ops_request(db, invoice_id, user, assert_team_access)
    if r.status != InvoiceRequestStatus.ISSUED:
        raise InvoiceError(
            f"仅已开具状态可红冲, 当前: {r.status.value}", 400
        )
    if r.voided:
        raise InvoiceError("该发票已红冲, 请勿重复操作", 400)
    if not reason or not reason.strip():
        raise InvoiceError("红冲原因不能为空", 422)

    r.voided = True
    r.void_reason = reason.strip()
    r.voided_by = user.id
    r.voided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    logger.info(
        "发票已红冲 id=%s operator=%s reason=%s", r.id, user.id, reason.strip()
    )
    # 通知钩子 (卡 9211f668): best-effort 三通道通知申请人红冲, 异常仅记日志不阻断主流程
    # (完全同构 reject_invoice_request: 先 resolve_openid, 再 notify_invoice_voided)
    try:
        openid = wx_subscribe_msg.resolve_openid(db, r)
    except Exception:
        logger.exception("resolve_openid 异常 invoice_id=%s", r.id)
        openid = None
    try:
        invoice_notification.notify_invoice_voided(r, db=db, openid=openid)
    except Exception:
        logger.exception("红冲通知钩子异常 invoice_id=%s", r.id)
    return r

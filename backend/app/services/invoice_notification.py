"""开票完成通知 + 签名文件 URL (用户端云端契约 §5.5, 工作卡 a09f8a21 / 3591ea8f)

通知钩子 (ISSUED 时触发, best-effort: 失败仅记日志, 不阻断开票主流程):
- 小程序订阅消息 (卡 3591ea8f): service 层 resolve_openid(db, invoice_request) 解析
  openid 后传入, openid 有值且 settings.WX_MP_APPID 配置时走真实IM-B订阅消息发送;
  否则降级日志 (开发/测试零配置可用)。
- App push (卡 5a280e1a): 按 openid 查 end_user_device_tokens 逐设备分发,
  走 PushProvider 抽象 (默认日志实现, 厂商对接后续卡 set_push_provider 替换);
- SMTP 邮件: 复用现有 smtplib 基础设施 (与 notification_dispatcher 同源),
  SMTP 未配置 → mock 日志 (开发/测试零配置可用)。

签名文件 URL: itsdangerous URLSafeTimedSerializer, 2h 过期, 防链接泄露。
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Optional

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import settings
from app.utils.sanitize import mask_email, mask_token

logger = logging.getLogger(__name__)

# 契约 §5.5: 文件 URL 带签名时效 2h
SIGNED_URL_MAX_AGE = 2 * 60 * 60  # 秒
_SALT = "invoice-file-download"


# ─── 签名文件 URL ────────────────────────────────────────────────────────────

def _serializer() -> URLSafeTimedSerializer:
    """复用全局 SECRET_KEY 签名 (与 JWT 同源密钥, salt 隔离用途)。"""
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt=_SALT)


def generate_file_token(invoice_id: int) -> str:
    """为发票申请单生成下载令牌 (嵌入 invoice_id, 验证时校验 2h 过期)。"""
    return _serializer().dumps({"iid": invoice_id})


def verify_file_token(token: str) -> Optional[int]:
    """校验下载令牌: 有效且未过期 → 返回 invoice_id; 否则 None。"""
    try:
        data = _serializer().loads(token, max_age=SIGNED_URL_MAX_AGE)
    except SignatureExpired:
        logger.info("发票下载令牌已过期")
        return None
    except BadSignature:
        logger.info("发票下载令牌无效")
        return None
    iid = data.get("iid")
    try:
        return int(iid) if iid is not None else None
    except (TypeError, ValueError):
        return None


def build_signed_file_url(invoice_id: int, base_url: str) -> str:
    """拼接带签名 token 的文件下载绝对 URL (端侧/邮箱可直接打开)。"""
    token = generate_file_token(invoice_id)
    base = base_url.rstrip("/")
    return f"{base}/api/v1/business/invoice-file?token={token}"


# ─── 邮件 ────────────────────────────────────────────────────────────────────

def _smtp_send(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
) -> None:
    """底层 SMTP 发送 (仅 SMTP 配置就绪时调用)。测试通过 monkeypatch 本函数验证。

    attachment_path: 发票文件磁盘路径, 若提供则作为附件 (契约 §5.3 ≤10MB 附件发送)。
    """
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = getattr(settings, "EMAIL_FROM", None) or "noreply@tianlian.com"
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if attachment_path:
        import os
        with open(attachment_path, "rb") as fp:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fp.read())
        encoders.encode_base64(part)
        fname = os.path.basename(attachment_path)
        part.add_header("Content-Disposition", "attachment", filename=("", fname))
        msg.attach(part)

    with smtplib.SMTP(
        getattr(settings, "SMTP_HOST", None),
        getattr(settings, "SMTP_PORT", 587),
        timeout=10,
    ) as server:
        server.starttls()
        user = getattr(settings, "SMTP_USER", None)
        pwd = getattr(settings, "SMTP_PASS", None)
        if user and pwd:
            server.login(user, pwd)
        server.sendmail(msg["From"], [to_email], msg.as_string())


def _smtp_configured() -> bool:
    """SMTP 是否已配置 (SMTP_HOST 非空)。测试通过 monkeypatch 本函数切换路径。"""
    return bool(getattr(settings, "SMTP_HOST", None))


def send_invoice_email(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
) -> bool:
    """发送开票邮件。SMTP 未配置 → mock 日志 (返回 True, 开发/测试行为)。

    返回 True 表示「已发出或已 mock」; 仅当 SMTP 已配置但发送抛错时返回 False。
    测试通过 monkeypatch _smtp_configured / _smtp_send 验证两条路径。
    """
    if not _smtp_configured():
        logger.info(
            "[INVOICE EMAIL MOCK] To: %s, Subject: %s, attach=%s",
            mask_email(to_email), subject, bool(attachment_path),
        )
        return True
    try:
        _smtp_send(to_email, subject, body_text, attachment_path)
        logger.info("[INVOICE EMAIL] Sent to %s: %s", mask_email(to_email), subject)
        return True
    except Exception:
        logger.exception("开票邮件发送失败 to=%s subject=%s", mask_email(to_email), subject)
        return False


# ─── 推送通道 (卡 3591ea8f: openid 有值则真实发送, 否则降级日志) ────────────────

def _build_subscribe_data(invoice_request, issued: bool, void: bool = False) -> dict:
    """构造订阅消息模板参数 (IM-B标准 {key: {value: ...}} 结构)。

    模板字段名以天链自建模板为准 (占位: invoice_no/title/amount/status); 真实模板 ID
    在小程序后台配置后填 settings.WX_INVOICE_ISSUED_TPL / WX_INVOICE_REJECTED_TPL。
    卡 9211f668: void=True 显式红冲模式 (优先于 issued 布尔), 文案区分已开具/未通过;
    默认 void=False 向后兼容, issued/rejected 原行为不变。
    """
    amount_yuan = (
        round(invoice_request.amount / 100, 2) if invoice_request.amount else 0.0
    )
    if void:
        void_reason = getattr(invoice_request, "void_reason", None) or ""
        status_text = "已红冲作废"
        if void_reason:
            status_text += f" ({void_reason})"
    else:
        status_text = "已开具" if issued else "未通过"
    return {
        "invoice_no": {"value": str(invoice_request.id)},
        "title": {"value": invoice_request.title_name},
        "amount": {"value": f"{amount_yuan:.2f} 元"},
        "status": {"value": status_text},
    }


def _push_miniprogram_subscribe(
    invoice_request, openid=None, issued=True, void: bool = False
) -> None:
    """小程序订阅消息推送 (契约 §5.5)。

    openid 为 service 层 resolve_openid 解析后的接收人; None (无支付单/未配置) → 降级日志。
    发送走 wx_subscribe_msg.send_subscribe_msg (best-effort: 失败仅记日志不抛)。
    template_id 未配置 (settings.WX_INVOICE_*_TPL) → 同样降级日志, 不发不抛。
    卡 9211f668: void=True 红冲模式, 复用 REJECTED 模板 (拒绝/红冲同类「负向通知」
    模板, 不新增渠道配置), 文案语义区分 (「已红冲作废」非「未通过」)。
    """
    # 始终留痕 (含未发送场景, 便于排查为何用户没收到)
    logger.info(
        "[INVOICE MP-SUBSCRIBE] invoice_id=%s user_id=%s amount=%s openid=%s",
        invoice_request.id, invoice_request.user_id, invoice_request.amount,
        "有" if openid else "无",
    )
    if not openid:
        return  # 无 openid → 仅日志, 不尝试发送

    from app.services import wx_subscribe_msg

    # 凭证未配置时 send_subscribe_msg 内部降级 skipped, 此处只在已配置时取模板 ID
    if not wx_subscribe_msg._credentials_configured():
        return

    tpl_key = (
        "WX_INVOICE_REJECTED_TPL" if (void or not issued)
        else "WX_INVOICE_ISSUED_TPL"
    )
    template_id = getattr(settings, tpl_key, None)
    if not template_id:
        logger.info("[INVOICE MP-SUBSCRIBE] %s 未配置, 跳过发送", tpl_key)
        return

    page = f"pages/invoice/detail?id={invoice_request.id}"
    data = _build_subscribe_data(invoice_request, issued=issued, void=void)
    try:
        # 同步桥接 (notify 钩子在同步调用栈中执行, 如同 dispatch_real_channel._run_sync)
        from app.services.channel_providers import _run_sync
        _run_sync(wx_subscribe_msg.send_subscribe_msg(
            openid=openid, template_id=template_id, data=data, page=page,
        ))
    except Exception:
        logger.exception(
            "小程序订阅消息发送异常 invoice_id=%s openid=%s",
            invoice_request.id, mask_token(openid),
        )


def resolve_device_targets(db, openid: Optional[str]) -> list:
    """按 openid 解析用户注册的 device tokens (卡 5a280e1a)。

    openid → end_users.wx_openid → 该用户全部生效 token (多设备, ios/android 各一)。
    注意 id 空间: InvoiceRequest.user_id 是运营侧 users 表主键, 不能直接查
    end_user_device_tokens (两表 id 不互通, 会撞 id 推错人); openid 是两体系
    唯一稳定桥 (与小程序订阅消息 resolve_openid 同源)。
    卡 7f601f7f: DISABLED 用户的 token 不解析 (被禁账号不该再收推送)。
    永不抛异常 (best-effort); 无 openid / 用户不存在/DISABLED / 无 token → 空列表。
    """
    if not openid:
        return []
    try:
        from app.models.end_user import EndUser, EndUserStatus
        from app.models.end_user_device_token import EndUserDeviceToken

        user = (
            db.query(EndUser)
            .filter(EndUser.wx_openid == openid)
            .filter(EndUser.status == EndUserStatus.ACTIVE)
            .first()
        )
        if user is None:
            return []
        return (
            db.query(EndUserDeviceToken)
            .filter(EndUserDeviceToken.end_user_id == user.id)
            .all()
        )
    except Exception:
        logger.warning("resolve_device_targets 查询异常 openid=%s", mask_token(openid))
        return []


def _push_app_notification(invoice_request, db=None, openid: Optional[str] = None) -> None:
    """App push 推送 (契约 §5.5), 按 device tokens 分发到 PushProvider。

    db/openid 为卡 5a280e1a 新增 (默认 None 保持向后兼容): 有 openid 时查
    end_user_device_tokens 按设备逐个 send (payload 带 device_token/platform,
    厂商 SDK 可直接对接); 解析不到 token → 降级为原 user_id 单发语义。
    单设备发送失败仅记日志, 不阻断其它设备与开票主流程 (best-effort)。
    卡 7f601f7f: payload 增补 status (issued/rejected, 契约 v1.3 小写); 厂商
    报失效 token (JPush 1011) → 逐设备 send 后清理库中对应 token。
    卡 9211f668: voided → status 映射 'voided', 标题文案区分红冲。
    """
    from app.services.push import get_push_provider

    logger.info(
        "[INVOICE APP-PUSH] invoice_id=%s user_id=%s amount=%s",
        invoice_request.id, invoice_request.user_id, invoice_request.amount,
    )
    if invoice_request.user_id is None:
        return

    if getattr(invoice_request, "voided", False):
        title = "发票红冲通知"
        body = "您的发票已红冲作废"
    elif _payload_status(invoice_request) == "rejected":
        # 卡 acfe2394: 拒绝路径复用本函数, 托盘文案须含「未通过」语义
        # (payload.status 一直正确, 但用户第一眼看到的是托盘标题/正文)。
        title = "开票申请未通过"
        body = "您的开票申请未通过审核"
    else:
        title = "发票开具通知"
        body = "您的开票申请已处理"
    targets = resolve_device_targets(db, openid) if db is not None else []
    if not targets:
        # 无 db / 无注册设备 → 保留原语义 (user_id 直发, 默认实现仅日志)
        logger.debug(
            "[INVOICE APP-PUSH] invoice_id=%s openid=%s 无 device token, 降级 user_id 直发",
            invoice_request.id, mask_token(openid),
        )
        get_push_provider().send(
            invoice_request.user_id, title, body,
            {"invoice_id": invoice_request.id, "amount": invoice_request.amount},
        )
        return

    for t in targets:
        try:
            provider = get_push_provider()
            provider.send(
                t.end_user_id, title, body,
                {
                    "invoice_id": invoice_request.id,
                    "amount": invoice_request.amount,
                    "device_token": t.device_token,
                    "platform": t.platform,
                    "status": _payload_status(invoice_request),
                },
            )
            _cleanup_invalid_tokens(provider, db, targets)
        except Exception:
            logger.exception(
                "App push 单设备发送失败 invoice_id=%s token=%s",
                invoice_request.id, t.device_token,
            )


def _payload_status(invoice_request) -> str:
    """payload.status 取发票终态 (契约 v1.3: 小写); 无状态字段场景降级 'issued'。

    卡 9211f668: voided 标记优先 (红冲单 status 仍是 issued, 但终态语义是 voided)。
    """
    if getattr(invoice_request, "voided", False):
        return "voided"
    status = getattr(invoice_request, "status", None)
    value = getattr(status, "value", status)
    return value if isinstance(value, str) else "issued"


def _cleanup_invalid_tokens(provider, db, targets) -> None:
    """厂商报失效 token (如 JPush errcode 1011) → 从库里删掉该 token。

    duck-typed: provider 无 drain_invalid_tokens (如 LogPushProvider) → 跳过。
    删除范围限定本轮目标用户 (invalid 列表本就产自 targets 的发送)。
    清理失败仅记日志 (best-effort, 不阻断后续发送)。
    """
    drain = getattr(provider, "drain_invalid_tokens", None)
    if not callable(drain):
        return
    try:
        invalid = drain()
        if not invalid or db is None:
            return
        from app.models.end_user_device_token import EndUserDeviceToken

        deleted = (
            db.query(EndUserDeviceToken)
            .filter(EndUserDeviceToken.device_token.in_(invalid))
            .filter(
                EndUserDeviceToken.end_user_id.in_(
                    {t.end_user_id for t in targets}
                )
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info(
                "[INVOICE APP-PUSH] 清理失效 token %s 个 (厂商 1011)", deleted,
            )
    except Exception:
        logger.exception("失效 token 清理异常")
        try:
            db.rollback()
        except Exception:
            pass


def _build_issued_email_body(invoice_request, file_url: Optional[str]) -> str:
    """构建「发票已开具」邮件正文 (纯文本)。"""
    lines = [
        f"您的开票申请 (单号 #{invoice_request.id}) 已完成开具。",
        f"发票抬头: {invoice_request.title_name}",
        f"开票金额: {invoice_request.amount / 100:.2f} 元",
    ]
    if file_url:
        lines.append("")
        lines.append("发票文件下载 (链接 2 小时内有效):")
        lines.append(file_url)
    lines.append("")
    lines.append("— 天链")
    return "\n".join(lines)


def notify_invoice_issued(
    invoice_request, file_url: Optional[str] = None, db=None, openid=None
) -> None:
    """开票完成通知总钩子 (契约 §5.5)。

    三通道 best-effort: 任一通道异常仅记日志, 不影响 ISSUED 主流程与其它通道。
    邮件仅在 invoice_request.email 非空时发送。

    db/openid 为卡 3591ea8f 新增 (默认 None 保持向后兼容): service 层先
    resolve_openid(db, invoice_request) 解析 openid 再传入, 触发IM-B订阅消息真实发送;
    None 时小程序通道降级日志 (与历史行为一致)。
    卡 5a280e1a: db 同时透传 App push 通道, 按 openid 查 device tokens 分发。
    """
    # 1. 小程序订阅消息
    try:
        _push_miniprogram_subscribe(invoice_request, openid=openid, issued=True)
    except Exception:
        logger.exception("小程序订阅消息推送异常 invoice_id=%s", invoice_request.id)

    # 2. App push (db/openid → device tokens 分发)
    try:
        _push_app_notification(invoice_request, db=db, openid=openid)
    except Exception:
        logger.exception("App push 推送异常 invoice_id=%s", invoice_request.id)

    # 3. 邮件 (填了 email 才发)
    if invoice_request.email:
        subject = f"【天链】您的发票已开具 (申请单 #{invoice_request.id})"
        body = _build_issued_email_body(invoice_request, file_url)
        try:
            send_invoice_email(
                invoice_request.email,
                subject,
                body,
                invoice_request.invoice_file_path,
            )
        except Exception:
            logger.exception("开票邮件通知异常 invoice_id=%s", invoice_request.id)


def _build_rejected_email_body(invoice_request) -> str:
    """构建「开票申请被拒绝」邮件正文 (纯文本)。"""
    lines = [
        f"您的开票申请 (单号 #{invoice_request.id}) 未通过审核。",
        f"发票抬头: {invoice_request.title_name}",
    ]
    if invoice_request.reject_reason:
        lines.append(f"拒绝原因: {invoice_request.reject_reason}")
    lines.append("如需开票, 请根据以上原因修改后重新提交申请。")
    lines.append("")
    lines.append("— 天链")
    return "\n".join(lines)


def notify_invoice_rejected(invoice_request, db=None, openid=None) -> None:
    """开票申请被拒绝通知 (契约 §5.5, 卡4b14971e 修复点2)。

    与 notify_invoice_issued 同构的三通道 best-effort 通知: 任一通道异常仅记日志,
    不影响 REJECTED 主流程与其它通道。邮件仅在 invoice_request.email 非空时发送,
    让用户无需主动轮询即知申请被拒。

    db/openid 为卡 3591ea8f 新增 (默认 None 保持向后兼容): 详见 notify_invoice_issued。
    """
    # 1. 小程序订阅消息
    try:
        _push_miniprogram_subscribe(invoice_request, openid=openid, issued=False)
    except Exception:
        logger.exception("拒绝通知-小程序订阅消息推送异常 invoice_id=%s", invoice_request.id)

    # 2. App push (db/openid → device tokens 分发)
    try:
        _push_app_notification(invoice_request, db=db, openid=openid)
    except Exception:
        logger.exception("拒绝通知-App push 推送异常 invoice_id=%s", invoice_request.id)

    # 3. 邮件 (填了 email 才发)
    if invoice_request.email:
        subject = f"【天链】您的开票申请未通过 (申请单 #{invoice_request.id})"
        body = _build_rejected_email_body(invoice_request)
        try:
            send_invoice_email(invoice_request.email, subject, body)
        except Exception:
            logger.exception("拒绝通知-邮件通知异常 invoice_id=%s", invoice_request.id)


def _build_voided_email_body(invoice_request) -> str:
    """构建「发票已红冲」邮件正文 (纯文本, 卡 9211f668)。

    含申请单号、抬头、红冲原因 void_reason, 并说明原票作废。
    """
    lines = [
        f"您的发票 (申请单 #{invoice_request.id}) 已红冲作废。",
        f"发票抬头: {invoice_request.title_name}",
    ]
    if invoice_request.void_reason:
        lines.append(f"红冲原因: {invoice_request.void_reason}")
    lines.append("原发票已作废, 请勿继续使用; 如需开票, 请重新提交申请。")
    lines.append("")
    lines.append("— 天链")
    return "\n".join(lines)


def notify_invoice_voided(invoice_request, db=None, openid=None) -> None:
    """红冲通知总钩子 (契约 §5.5, 卡 9211f668)。

    与 notify_invoice_issued / notify_invoice_rejected 同构的三通道 best-effort
    通知: 任一通道异常仅记日志, 不影响红冲主流程与其它通道。
    - 小程序订阅消息: void 模式 (复用 REJECTED 模板, 文案「已红冲作废」+ 原因);
    - App push: 走 _push_app_notification, payload.status 映射 'voided', 标题区分;
    - 邮件: 仅 invoice_request.email 非空时发送, 正文含红冲原因与原票作废说明。
    """
    # 1. 小程序订阅消息 (void 模式)
    try:
        _push_miniprogram_subscribe(
            invoice_request, openid=openid, issued=False, void=True
        )
    except Exception:
        logger.exception("红冲通知-小程序订阅消息推送异常 invoice_id=%s", invoice_request.id)

    # 2. App push (db/openid → device tokens 分发)
    try:
        _push_app_notification(invoice_request, db=db, openid=openid)
    except Exception:
        logger.exception("红冲通知-App push 推送异常 invoice_id=%s", invoice_request.id)

    # 3. 邮件 (填了 email 才发)
    if invoice_request.email:
        subject = f"【天链】您的发票已红冲 (申请单 #{invoice_request.id})"
        body = _build_voided_email_body(invoice_request)
        try:
            send_invoice_email(invoice_request.email, subject, body)
        except Exception:
            logger.exception("红冲通知-邮件通知异常 invoice_id=%s", invoice_request.id)

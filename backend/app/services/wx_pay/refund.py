"""IM-B服务商退款服务 (工作卡 aa88371f — 退款链路财务边界配套)

契约 §2 扩展 (退款):
- process_refund: 调用IM-B退款 API (mock 先行), 返回渠道退款号 refund_id。
- complete_refund (app/api/v1/order_fees.py) 调用本服务, 落
  RefundRecord.channel_refund_no。

mock 先行: 不联网 / 不真实签名, 生成结构合规的退款单号; 真实凭证到位后
仅替换 client 实现 (新增 RealWxPayClient, 工厂切换), service / router /
契约零改动 (与 payment.py 同构)。
"""
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.wx_pay import get_wxpay_client
from app.services.wx_pay.payment import _pick_payment_row

logger = logging.getLogger(__name__)


def generate_out_refund_no() -> str:
    """平台退款单号 TLR_yyyymmdd_xxxx (唯一性由渠道侧 out_refund_no 幂等兜底)。"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"TLR_{today}_{secrets.token_hex(8)}"


def _yuan_to_fen(amount) -> int:
    """元(Decimal/数值) → 分(int), 用 Decimal 避免浮点误差。"""
    return int((Decimal(str(amount)) * Decimal("100")).to_integral_value())


def process_refund(db: Session, *, order, refund):
    """调用IM-B退款 (mock), 返回渠道退款单号 refund_id; 渠道异常时返回结构化错误。

    流程:
    1. out_trade_no 取业务订单关联的代表性支付行 (_pick_payment_row,
       PAID > UNPAID > CLOSED); mock 阶段无支付记录则降级本地单号
       (渠道侧以 out_refund_no 幂等去重)。
    2. 金额换算: refund.refund_amount(元) → 分。
    3. client.refund 发起渠道退款, 返回 RefundResult。

    卡 69fe6381 (幂等键持久化): out_refund_no 优先复用 refund.out_refund_no
    (重试同号 → 渠道幂等去重, 防重复打款), 否则生成新号; 成功/失败路径都把
    最终单号写进传入的 refund 对象 (refund.out_refund_no = ...), 由调用方
    随 db.commit 落库 — process_refund 自身不 commit (卡 d077c519)。

    Args:
        order: ChargingOrder — 取 order_no 关联支付单。
        refund: RefundRecord — 取 refund_amount / reason; out_refund_no 复用+回写。

    Returns:
        成功: IM-B退款单号 refund_id (str, 4200...); 调用方落 RefundRecord.channel_refund_no。
        渠道异常 (卡 692b3df7): 结构化错误 dict ``{"status": "error", "error": <msg>,
            "out_refund_no": <平台退款单号>}``, 不裸抛 — 让调用方据返回值类型决定降级
            策略 (重试 / 标记退款失败 / 返回 502), out_refund_no 供幂等重试。
    """
    # 卡 8f15802c: 选行复用 _pick_payment_row (PAID > UNPAID > CLOSED, 同级最新),
    # 避免盲取最新行拿到重复下单产生的 UNPAID 行 → 真实渠道拒退 / mock 退到幽灵交易。
    po = _pick_payment_row(db, order.order_no)
    out_trade_no = po.out_trade_no if po else f"TL_LOCAL_{order.order_no}"
    # 卡 69fe6381: 幂等键 — 已持久化则复用, 否则生成新号; 无论成败都附到 refund 对象
    out_refund_no = getattr(refund, "out_refund_no", None) or generate_out_refund_no()
    refund.out_refund_no = out_refund_no
    refund_amount_fen = _yuan_to_fen(refund.refund_amount)
    client = get_wxpay_client()
    try:
        result = client.refund(
            out_trade_no=out_trade_no,
            out_refund_no=out_refund_no,
            refund_amount_fen=refund_amount_fen,
            reason=refund.reason or "充电订单退款",
        )
    except Exception as exc:  # noqa: BLE001 — 渠道层任何异常都不应冒泡为裸 500
        # 卡 692b3df7: 兜底 WxPayError 及真实实现可能漏转的底层异常 (httpx 等),
        # 记 error 日志并返回结构化错误, 由 caller (complete_refund) 映射降级, 不推进
        # 退款状态。out_refund_no 已附到 refund 对象并回带 dict, 便于幂等重试
        # (同号重复请求渠道返回同一退款)。
        logger.error(
            "wx_pay refund 调用失败 out_trade_no=%s out_refund_no=%s amount_fen=%s: %s",
            out_trade_no, out_refund_no, refund_amount_fen, exc, exc_info=True,
        )
        return {
            "status": "error",
            "error": str(exc) or exc.__class__.__name__,
            "out_refund_no": out_refund_no,
        }
    return result.refund_id

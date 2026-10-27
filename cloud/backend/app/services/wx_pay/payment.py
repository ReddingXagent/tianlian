"""IM-B服务商支付服务 (工作卡 280c85ee — 云端配套④)

契约 §2 (支付):
- prepay: 解析 sub_mchid + merchant_status 校验 + mock 统一下单 + 落 PaymentOrder + 返回五字段
- handle_notify: 验签解密 + 幂等更新 PAID (契约 §2.2 回调)
- get_order_payment: 订单/支付状态查询 (契约 §2.3 结构)

sub_mchid 解析: 业务订单 → ChargingOrder → station → team → Merchant。
mock 阶段未关联商户时降级默认 sub_mchid (视为就绪); 解析到真实商户则校验运行态。
"""
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.models.merchant import Merchant, MerchantStatus
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.services.wx_pay import get_wxpay_client

logger = logging.getLogger(__name__)

# 业务日时区: IM-B下单单号按 Asia/Shanghai 业务日 (对账/运营按 CST), 不用 UTC (工作卡 16209d26)
_BIZ_TZ = ZoneInfo("Asia/Shanghai")


class SubMerchantNotReady(Exception):
    """子商户未就绪 (进件未 FINISH / merchant_status=PENDING)"""


class SubMerchantFrozen(Exception):
    """子商户冻结 (merchant_status=FROZEN)"""


class OrderAlreadyPaid(Exception):
    """订单已支付 (重复 prepay 掩盖已支付 → 拒绝重复下单, 工作卡 16209d26)"""


# mock 先行: 无关联商户时的默认 sub_mchid (真实接入前, 所有 prepay 走此降级)
MOCK_DEFAULT_SUB_MCHID = "2490000000"


def _dec_or_zero(v) -> Decimal:
    """金额字段 → Decimal, None/非法值安全降级 0 (未采集/未结算字段不炸整单)。"""
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def compute_amount_fen(order) -> int:
    """业务订单 → 应付金额 (分), 真实下单金额口径 (卡 6c8f930c A1)。

    应付 = total_amount − discount_amount − coupon_amount − points_amount (元),
    元→分用 Decimal ROUND_HALF_UP (0.005 进位), None 当 0, 负数钳 0
    (全折扣覆盖时不向IM-B下负金额单; 实收口径对齐 billing_engine 的
    "优惠不允许把实收打成负" 约定)。order 为 None (纯支付测试场景) → 0。
    """
    if order is None:
        return 0
    total = _dec_or_zero(order.total_amount)
    payable = total - (
        _dec_or_zero(order.discount_amount)
        + _dec_or_zero(order.coupon_amount)
        + _dec_or_zero(order.points_amount)
    )
    if payable < 0:
        payable = Decimal("0")
    fen = (payable * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(fen)


def generate_out_trade_no() -> str:
    """平台统一下单单号 TL_yyyymmdd_xxxx (唯一性由 DB unique 约束兜底)。

    业务日取 Asia/Shanghai (IM-B侧/对账按 CST), 不用 UTC (工作卡 16209d26)。
    """
    today = datetime.now(_BIZ_TZ).strftime("%Y%m%d")
    return f"TL_{today}_{secrets.token_hex(8)}"


def _lookup_merchant_by_order(db: Session, business_order_no: str) -> Optional[Merchant]:
    """业务订单 → station → team → Merchant(team 内最新商户)。

    只读查询; mock 阶段订单/站点未 seed 时返回 None (调用方降级默认 sub_mchid)。
    任何查询异常一律降级 None, 不阻断 prepay (mock 先行优先可用)。
    """
    try:
        from app.models.charging_order import ChargingOrder
        from app.models.station import Station

        order = (
            db.query(ChargingOrder.station_id)
            .filter(ChargingOrder.order_no == business_order_no)
            .first()
        )
        if not order or not order.station_id:
            return None
        team_id = db.query(Station.team_id).filter(Station.id == order.station_id).scalar()
        if not team_id:
            return None
        return (
            db.query(Merchant)
            .filter(Merchant.team_id == team_id)
            .order_by(Merchant.id.desc())
            .first()
        )
    except Exception:
        logger.exception("merchant lookup failed business_order_no=%s", business_order_no)
        return None


def _assert_merchant_usable(m: Merchant) -> None:
    if m.merchant_status == MerchantStatus.FROZEN:
        raise SubMerchantFrozen()
    if m.merchant_status != MerchantStatus.ACTIVE:
        raise SubMerchantNotReady()


def resolve_sub_mchid(db: Session, business_order_no: str):
    """解析 sub_mchid + 校验 merchant_status。返回 (sub_mchid, merchant|None)。

    - 商户状态闸对首单/复用路径统一生效 (卡 7f5b4d4f A2): 无论是否复用已存在
      PaymentOrder 的 sub_mchid (二次 prepay), 都按
      业务订单→station→team→Merchant 解析商户并校验 merchant_status
      (FROZEN→SubMerchantFrozen, 非ACTIVE→SubMerchantNotReady)。
      旧实现复用路径直接返回跳过校验 —— 商户冻结后二次 prepay 仍能下单, 绕过禁收闸。
    - 复用行命中可用商户 → 沿用存量 sub_mchid (不因商户换号漂移, 与IM-B侧
      out_trade_no 绑定的原 sub_mchid 一致)
    - 解析不到 (mock 阶段常见): 首单用 MOCK_DEFAULT_SUB_MCHID, 复用行用其
      sub_mchid, 均视为就绪
    """
    existing = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.business_order_no == business_order_no)
        .order_by(PaymentOrder.id.desc())
        .first()
    )
    m = _lookup_merchant_by_order(db, business_order_no)
    if m is None:
        if existing:
            return existing.sub_mchid, None
        return MOCK_DEFAULT_SUB_MCHID, None
    _assert_merchant_usable(m)
    if existing:
        return existing.sub_mchid, m
    return m.sub_mchid or MOCK_DEFAULT_SUB_MCHID, m


def _appid_for_scene(scene: str, settings_override=None) -> Optional[str]:
    """按 scene 取下单 appid (卡 7f5b4d4f A2, 回调比对基准)。

    settings_override: 测试注入 settings 命名空间; 缺省读全局 settings。
    取不到 (未配置) → None (订单行 appid 落 NULL, 回调跳过比对兼容)。
    """
    if settings_override is not None:
        s = settings_override
    else:
        from app.core.config import settings as s
    if scene == "app":
        return getattr(s, "WX_PAY_APPID_APP", None) or None
    return getattr(s, "WX_PAY_APPID_MINIPROGRAM", None) or None


def prepay(
    db: Session,
    *,
    order_id: str,
    openid: str,
    scene: str,
    _settings_override=None,
) -> dict:
    """服务商统一下单, 返回 wx.requestPayment 五字段 (camelCase, 契约 §2.1)。

    子商户未就绪/冻结 → 抛 SubMerchantNotReady/SubMerchantFrozen (router 映射业务错误码)。
    重复 prepay 防护 (工作卡 16209d26):
    - 已有 PAID 行 → 抛 OrderAlreadyPaid (订单已支付, 拒绝重复下单)
    - 已有 UNPAID 行 → 复用其 out_trade_no 重新发起 (刷新 prepay_id), 不新建行

    _settings_override: 测试缝 (注入 appid 配置), 生产调用方不传。
    """
    # 已支付 → 拒绝重复下单 (避免新建 UNPAID 行掩盖已支付状态)
    paid = (
        db.query(PaymentOrder)
        .filter(
            PaymentOrder.business_order_no == order_id,
            PaymentOrder.payment_status == PaymentStatus.PAID,
        )
        .first()
    )
    if paid:
        raise OrderAlreadyPaid()
    # 已有 UNPAID 行 → 复用 out_trade_no 重新发起 (而非新建第二行, 触发 unique 冲突)
    existing_unpaid = (
        db.query(PaymentOrder)
        .filter(
            PaymentOrder.business_order_no == order_id,
            PaymentOrder.payment_status == PaymentStatus.UNPAID,
        )
        .order_by(PaymentOrder.id.desc())
        .first()
    )

    # 金额真实化 (卡 6c8f930c A1): 从业务订单取应付金额 (分), 不再 mock=0。
    # 查询容错: 纯支付测试场景可能未建 ChargingOrder 表, 查询失败降级 amount=0
    # (与 _lookup_merchant_by_order 容错风格一致; PaymentOrder 仍是支付真相源)。
    try:
        charging_order = (
            db.query(ChargingOrder)
            .filter(ChargingOrder.order_no == order_id)
            .first()
        )
    except Exception:
        logger.exception("charging_order lookup failed business_order_no=%s", order_id)
        charging_order = None
    amount_fen = compute_amount_fen(charging_order)
    sub_mchid, _ = resolve_sub_mchid(db, order_id)
    appid = _appid_for_scene(scene, _settings_override)
    out_trade_no = existing_unpaid.out_trade_no if existing_unpaid else generate_out_trade_no()
    client = get_wxpay_client()
    result = client.unified_order(
        out_trade_no=out_trade_no,
        sub_mchid=sub_mchid,
        amount_fen=amount_fen,
        description=f"充电订单 {order_id}",
        openid=openid,
        scene=scene,
    )
    if existing_unpaid:
        # 复用行: 刷新 prepay_id + 下单参数, out_trade_no 与 payment_status(UNPAID) 不变
        existing_unpaid.prepay_id = result.prepay_id
        existing_unpaid.openid = openid
        existing_unpaid.scene = PayScene(scene)
        existing_unpaid.sub_mchid = sub_mchid
        existing_unpaid.appid = appid
        # 金额随订单当前值刷新 (结算修正后二次 prepay 不留旧金额)
        existing_unpaid.amount_fen = amount_fen
        # 事务安全 (卡 d077c519): commit 失败 rollback + 重抛, 由 business.py 兜底
        # except Exception 映射 500。service 层不耦合 HTTPException (参照
        # billing_engine.settle_order_fees 的 rollback+raise 模式)。
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("prepay 刷新 commit 失败 out_trade_no=%s", out_trade_no)
            raise
        db.refresh(existing_unpaid)
        po = existing_unpaid
    else:
        po = PaymentOrder(
            out_trade_no=out_trade_no,
            business_order_no=order_id,
            openid=openid,
            scene=PayScene(scene),
            sub_mchid=sub_mchid,
            appid=appid,
            amount_fen=amount_fen,
            prepay_id=result.prepay_id,
            payment_status=PaymentStatus.UNPAID,
        )
        db.add(po)
        # 事务安全 (卡 d077c519): 同上, commit 失败 rollback + 重抛, 调用方映射 500。
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("prepay 落库 commit 失败 out_trade_no=%s", out_trade_no)
            raise
        db.refresh(po)
    # 端侧原样传入 wx.requestPayment, 不做任何加工/签名
    return {
        "timeStamp": result.time_stamp,
        "nonceStr": result.nonce_str,
        "package": result.package,
        "signType": result.sign_type,
        "paySign": result.pay_sign,
    }


def _notify_matches_order(po: PaymentOrder, notify) -> bool:
    """回调与订单一致性校验 (资金安全, 卡 6c8f930c / 7f5b4d4f A2)。

    硬闸 (不符 → False):
    - 金额: notify.amount_fen != po.amount_fen (下单金额即应付金额, 真实回调
      IM-B侧回显 amount.total; 篡改/错单在此拦截)
    - sub_mchid: 回调携带且与订单行不符 (跨商户错配)
    - appid (卡 7f5b4d4f A2): 回调携带 sp_appid 且与订单行 appid 不符
      (跨应用嫁接/伪造后过验签的回调, 不能落 PAID)
    软维度 (None 跳过): 回调未携带 sub_mchid/appid (mock 明文 body 兼容);
    订单行 appid 为 NULL (存量行, 加列前落库) → 跳过比对 + WARNING 留痕
    (风控对账可查, 兼容期随存量单消化自然收敛)。
    """
    if notify.amount_fen != po.amount_fen:
        logger.error(
            "回调金额与订单不符, 拒绝落 PAID out_trade_no=%s order_amount_fen=%s "
            "notify_amount_fen=%s business_order_no=%s",
            po.out_trade_no, po.amount_fen, notify.amount_fen,
            po.business_order_no,
        )
        return False
    if notify.sub_mchid and po.sub_mchid and notify.sub_mchid != po.sub_mchid:
        logger.error(
            "回调 sub_mchid 与订单不符, 拒绝落 PAID out_trade_no=%s "
            "order_sub_mchid=%s notify_sub_mchid=%s business_order_no=%s",
            po.out_trade_no, po.sub_mchid, notify.sub_mchid,
            po.business_order_no,
        )
        return False
    if notify.appid and po.appid and notify.appid != po.appid:
        logger.error(
            "回调 appid 与订单不符, 拒绝落 PAID out_trade_no=%s order_appid=%s "
            "notify_appid=%s business_order_no=%s",
            po.out_trade_no, po.appid, notify.appid, po.business_order_no,
        )
        return False
    if notify.appid and not po.appid:
        logger.warning(
            "订单行 appid 为 NULL, 跳过回调 appid 比对 (存量兼容) "
            "out_trade_no=%s notify_appid=%s business_order_no=%s",
            po.out_trade_no, notify.appid, po.business_order_no,
        )
    return True


def handle_notify(db: Session, raw_body: bytes, headers: dict) -> dict:
    """回调验签解密 + 幂等更新 PAID/CLOSED。返回IM-B要求的响应结构。

    幂等: notify_count 每次+1; notify_processed 控制业务只处理一次
    (重复 SUCCESS 回调不重设 paid_at / wx_transaction_id)。
    终态回写 (卡 4eab7cae): CLOSED/PAYERROR 回调且当前 UNPAID → 落 CLOSED;
    PAID 行绝不降级; USERPAYING 等中间态保持 UNPAID。
    """
    client = get_wxpay_client()
    notify = client.verify_and_decrypt_notify(raw_body, headers)
    if notify is None:
        return {"code": "FAIL", "message": "验签失败"}
    po = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.out_trade_no == notify.out_trade_no)
        .first()
    )
    if po is None:
        # 未知订单: 仍 ACK 避免IM-B重试风暴, 但不落状态
        return {"code": "SUCCESS", "message": "成功"}
    po.notify_count = (po.notify_count or 0) + 1
    trade_state = str(notify.trade_state).upper()
    # 资金安全闸 (卡 6c8f930c): SUCCESS 落 PAID 前校验回调金额/身份与订单一致。
    # 仅拦首次处理 (notify_processed False): 重复回调首次已校验, 不重复校。
    # 不符 → 拒绝落 PAID + error 告警, 状态不动 + ACK SUCCESS (同构重试必然同值,
    # FAIL 只会造重试风暴; 与未知单 ACK 先例一致, notify_count 留审计线索)。
    # 不设 notify_processed: 正确金额的后续回调仍可正常落 PAID (见 guard 测试)。
    if (
        not po.notify_processed
        and trade_state == "SUCCESS"
        and not _notify_matches_order(po, notify)
    ):
        try:
            db.commit()  # 仅持久化 notify_count 累加
        except Exception:
            db.rollback()
            logger.exception(
                "notify guard commit 失败 out_trade_no=%s", po.out_trade_no
            )
            return {"code": "FAIL", "message": "落库失败, 等待IM-B重试"}
        return {"code": "SUCCESS", "message": "成功"}
    if not po.notify_processed and trade_state == "SUCCESS":
        po.payment_status = PaymentStatus.PAID
        po.wx_transaction_id = notify.wx_transaction_id
        po.paid_at = notify.paid_at or datetime.now(timezone.utc)
        po.notify_processed = True
        # 同步关联 ChargingOrder.payment_status (卡 1b5e3d1e):
        # 开票校验/订单列表/详情读的是 ChargingOrder 而非 PaymentOrder, 不同步则
        # 付款后仍显示 UNPAID → 开票永远失败。仅首次处理 (notify_processed False→True)
        # 时同步, 保证与 PaymentOrder 同幂等。
        # 查询容错: 纯支付测试场景可能无 ChargingOrder 行/表, 同步失败不阻断回调
        # (与 _lookup_merchant_by_order 的容错风格一致; PaymentOrder 已是支付真相源)。
        try:
            charging_order = (
                db.query(ChargingOrder)
                .filter(ChargingOrder.order_no == po.business_order_no)
                .first()
            )
            if charging_order is not None:
                charging_order.payment_status = OrderPaymentStatus.PAID
                # paid_amount 存元, PaymentOrder.amount_fen 存分, 换算对齐
                # invoice_request_service._amount_yuan_to_cents 口径。
                charging_order.paid_amount = Decimal(po.amount_fen) / Decimal(100)
        except Exception:
            logger.exception(
                "sync charging_order failed business_order_no=%s", po.business_order_no
            )
    elif not po.notify_processed and trade_state in ("CLOSED", "PAYERROR"):
        # 终态关单/支付失败回写 (卡 4eab7cae): 仅 UNPAID 行落 CLOSED
        # (PAID 行绝不降级 — notify_processed 已 True 时本分支天然跳过;
        #  USERPAYING 等中间态不落, 保持 UNPAID)。
        # 不设 notify_processed: 关单后IM-B不会再发 SUCCESS, 但万一交错先到
        # CLOSED 后到 SUCCESS, SUCCESS 分支仍可正常落 PAID (先关后付补偿)。
        if po.payment_status == PaymentStatus.UNPAID:
            po.payment_status = PaymentStatus.CLOSED
    # 事务安全 (卡 d077c519 / 资金安全 卡 5c0eb666): 最终 commit 失败 -> rollback,
    # 并返回 FAIL 触发IM-B重试。
    # 资金安全: commit 失败意味着 PaymentOrder/ChargingOrder 的 PAID 同步未持久化,
    # 此时若 ACK SUCCESS, IM-B不再重试, 用户订单将永久卡在 UNPAID (无法开票)。
    # 返回 FAIL 让IM-B按退避算法重试 (不会造成风暴), 下次重试时 notify_processed
    # 仍为 False, 幂等逻辑会重新同步, 最终落库成功。PaymentOrder 仍是支付真相源。
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("notify commit 失败 out_trade_no=%s", po.out_trade_no)
        return {"code": "FAIL", "message": "落库失败, 等待IM-B重试"}
    return {"code": "SUCCESS", "message": "成功"}


# 同一 business_order_no 多行时的状态优先级: PAID > UNPAID > CLOSED
# (防 "已 PAID 旧行 + 新 UNPAID 行" 掩盖已支付, 工作卡 16209d26; 其余态末位)
_STATUS_PRIORITY = {
    PaymentStatus.PAID: 0,
    PaymentStatus.UNPAID: 1,
    PaymentStatus.CLOSED: 2,
}


def _pick_payment_row(db: Session, business_order_no: str) -> Optional[PaymentOrder]:
    """取订单的代表性支付行 (同一订单多行时的选行规则)。

    同一订单多行时按状态优先级返回 (PAID > UNPAID > CLOSED; 其余态末位),
    避免重复下单产生的新行掩盖已支付状态 (工作卡 16209d26);
    同优先级多行时取最新 (id 最大), 与单行查询的 "最新行优先" 语义对齐。
    无支付记录 → None。§7.7 订单明细复用本函数取 paid_at/交易号 (卡 4b4a502a)。
    """
    rows = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.business_order_no == business_order_no)
        .all()
    )
    if not rows:
        return None
    return min(rows, key=lambda o: (_STATUS_PRIORITY.get(o.payment_status, 99), -o.id))


def get_order_payment(db: Session, business_order_no: str) -> Optional[dict]:
    """订单/支付状态查询 (契约 §2.3 结构)。无支付记录 → None。"""
    po = _pick_payment_row(db, business_order_no)
    if po is None:
        return None
    return {
        "order_id": po.business_order_no,
        "payment_status": po.payment_status.value,
        "transaction_id": po.wx_transaction_id,
        "paid_at": po.paid_at.isoformat() if po.paid_at else None,
    }

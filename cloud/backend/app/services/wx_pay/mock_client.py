"""IM-B服务商支付客户端 mock 实现 (工作卡 280c85ee — 云端配套④)

不依赖任何真实凭证/证书/网络。返回构造符合契约结构的数据, 真实接入仅替换本文件
(新增 RealWxPayClient, 工厂切换), 契约与 service/router 不变。

mock 回调约定: 明文 JSON body, 字段对齐IM-B真实回调解密后产物:
    {out_trade_no, transaction_id, trade_state, amount:{total}}
真实实现 verify_and_decrypt_notify 解密后产出同样结构。
"""
import base64
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from app.services.wx_pay.client import (
    WxPayClient,
    PrepayResult,
    NotifyResult,
    OrderQueryResult,
    RefundResult,
)


class MockWxPayClient(WxPayClient):
    """mock 实现: 返回结构合规的假数据, 不联网 / 不真实签名。"""

    def unified_order(
        self,
        *,
        out_trade_no: str,
        sub_mchid: str,
        amount_fen: int,
        description: str,
        openid: str,
        scene: str,
    ) -> PrepayResult:
        prepay_id = "wx" + secrets.token_hex(12)
        time_stamp = str(int(datetime.now(timezone.utc).timestamp()))
        nonce_str = secrets.token_hex(16).upper()
        package = f"prepay_id={prepay_id}"
        # mock 签名 (真实: SHA256withRSA 对 appId\ntimeStamp\nnonceStr\npackage\n, 商户 API 私钥)
        pay_sign = base64.b64encode(os.urandom(48)).decode().rstrip("=")
        return PrepayResult(
            prepay_id=prepay_id,
            time_stamp=time_stamp,
            nonce_str=nonce_str,
            package=package,
            sign_type="RSA",
            pay_sign=pay_sign,
        )

    def verify_and_decrypt_notify(
        self, raw_body: bytes, headers: dict
    ) -> Optional[NotifyResult]:
        # mock: 不验签, 直接解析明文 JSON (真实需 AES-GCM 解密 + 平台证书验签)
        try:
            if isinstance(raw_body, bytes):
                data = json.loads(raw_body.decode("utf-8"))
            elif isinstance(raw_body, str):
                data = json.loads(raw_body)
            else:
                data = raw_body
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        out_trade_no = data.get("out_trade_no")
        tx_id = data.get("transaction_id")
        trade_state = data.get("trade_state")
        if not out_trade_no or not tx_id or not trade_state:
            return None
        amount = data.get("amount") or {}
        amount_fen = int(amount.get("total", 0)) if isinstance(amount, dict) else 0
        paid_at = datetime.now(timezone.utc) if str(trade_state).upper() == "SUCCESS" else None
        # 身份回传 (卡 6c8f930c): 明文 body 可带 sp_appid/sub_mchid, 供 handle_notify
        # 与订单行比对; 不带则 None (校验跳过该维度, 兼容旧 mock 报文)。
        return NotifyResult(
            out_trade_no=out_trade_no,
            wx_transaction_id=tx_id,
            trade_state=str(trade_state).upper(),
            amount_fen=amount_fen,
            paid_at=paid_at,
            appid=data.get("sp_appid"),
            sub_mchid=data.get("sub_mchid"),
        )

    def query_order(self, out_trade_no: str) -> OrderQueryResult:
        # mock: 假设查单可见, 返回 SUCCESS + 生成的交易号 (真实调IM-B查单 API)
        return OrderQueryResult(
            out_trade_no=out_trade_no,
            wx_transaction_id="4200" + secrets.token_hex(12),
            trade_state="SUCCESS",
            paid_at=datetime.now(timezone.utc),
        )

    def refund(
        self,
        *,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount_fen: int,
        reason: str,
    ) -> RefundResult:
        # mock: 直接成功 + 生成退款单号 (真实: 调IM-B退款 API + 商户私钥签名)
        return RefundResult(
            out_refund_no=out_refund_no,
            refund_id="4200" + secrets.token_hex(12),
            status="SUCCESS",
            refund_amount_fen=refund_amount_fen,
        )

    def generate_sub_mchid(self) -> str:
        # mock 特约商户号 (真实: 进件 FINISH 时IM-B返回 10 位数字, 形如 2490000001)
        # mock_ 前缀显式标识, 避免与真实IM-B返回的商户号混淆 (卡 d53a2f2f)
        return "mock_" + "".join(str(secrets.randbelow(10)) for _ in range(10))

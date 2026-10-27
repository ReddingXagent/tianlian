"""IM-B服务商支付服务包 (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §2/§3/§4

mock 先行: 所有IM-B API 调用走 client 抽象 (本期 MockWxPayClient); 真实凭证到位后
仅替换 client 实现, service / router / 契约不变。
"""
from app.services.wx_pay.client import (
    WxPayClient,
    WxPayError,
    PrepayResult,
    NotifyResult,
    OrderQueryResult,
    RefundResult,
    get_wxpay_client,
    reset_wxpay_client_for_testing,
)
from app.services.wx_pay.mock_client import MockWxPayClient

__all__ = [
    "WxPayClient",
    "WxPayError",
    "MockWxPayClient",
    "PrepayResult",
    "NotifyResult",
    "OrderQueryResult",
    "RefundResult",
    "get_wxpay_client",
    "reset_wxpay_client_for_testing",
]

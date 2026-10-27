"""IM-B服务商支付客户端抽象 + 工厂 (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §2 (支付)

设计 (mock 先行):
- WxPayClient 抽象IM-B服务商 API: 统一下单 / 查单 / 回调验签解密 / 生成特约商户号。
- 业务逻辑 (sub_mchid 解析 / 进件状态机 / 回调幂等) 在 service 层, 不在 client。
- 真实凭证到位 → 新增真实实现 (RealWxPayClient), 工厂按配置切换, 契约与调用方零改动。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Optional


@dataclass
class PrepayResult:
    """统一下单结果 (映射 wx.requestPayment 五字段 + prepay_id 内部用)"""

    prepay_id: str
    time_stamp: str   # → 端侧 timeStamp
    nonce_str: str    # → 端侧 nonceStr
    package: str      # "prepay_id=xxx"
    sign_type: str    # → 端侧 signType ("RSA")
    pay_sign: str     # → 端侧 paySign


@dataclass
class NotifyResult:
    """回调验签解密结果"""

    out_trade_no: str
    wx_transaction_id: str
    trade_state: str          # SUCCESS / NOTPAY / CLOSED / REFUND ...
    amount_fen: int
    paid_at: Optional[datetime]
    # 身份回传 (卡 6c8f930c): 资金安全校验用 —— handle_notify 与订单比对。
    # None = 回调未携带 (mock 明文 body 可不带, 校验跳过该维度)。
    appid: Optional[str] = None       # sp_appid (服务商应用 appid)
    sub_mchid: Optional[str] = None   # 子商户号


@dataclass
class OrderQueryResult:
    """查单结果"""

    out_trade_no: str
    wx_transaction_id: Optional[str]
    trade_state: str
    paid_at: Optional[datetime]


@dataclass
class RefundResult:
    """退款结果 (映射IM-B退款 API 响应关键字段)"""

    out_refund_no: str       # 平台退款单号 (商户自定义)
    refund_id: str           # IM-B退款单号 (4200...)
    status: str              # SUCCESS / PROCESSING / CLOSED / ABNORMAL
    refund_amount_fen: int   # 退款金额 (分), 回显校验


class WxPayError(Exception):
    """IM-B服务商外部调用失败 (网络/超时/解析/业务错误) 的统一业务异常。

    真实 RealWxPayClient 的各方法 (unified_order / query_order / refund /
    verify_and_decrypt_notify / generate_sub_mchid) 经 httpx 调IM-B API, 可能抛
    httpx.RequestError / httpx.TimeoutException 或响应解析异常。约定: 真实实现应在
    方法内部捕获这类底层异常并统一 ``raise WxPayError(...) from exc``, 由 service 层
    (applyment / payment / refund) 与 router 兜底映射为 HTTP 502 —— 避免外部网络故障
    冒泡为裸 500 '服务器内部错误'。与 payment.py 的 SubMerchantNotReady 等业务异常
    同模式 (service 抛业务异常, router 映射)。

    mock 阶段 (MockWxPayClient) 不联网, 不触发本异常; caller 侧仍按本约定兜底,
    确保真实接入切换时零行为漂移。
    """


class WxPayClient(ABC):
    """IM-B服务商支付客户端抽象。

    真实实现需持有 sp_mchid (天链服务商号) + 商户 API 私钥/证书, 按 scene 选择 appid。
    """

    @abstractmethod
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
        """服务商统一下单 (sp_mchid + sub_mchid), 返回 prepay_id + 五字段签名。

        paySign = SHA256withRSA 对 ``appId\\ntimeStamp\\nnonceStr\\npackage\\n`` 签名,
        仅真实实现持有商户 API 私钥时可计算。
        """

    @abstractmethod
    def verify_and_decrypt_notify(
        self, raw_body: bytes, headers: dict
    ) -> Optional[NotifyResult]:
        """回调验签 + 解密。验签失败或解析异常 → None。"""

    @abstractmethod
    def query_order(self, out_trade_no: str) -> OrderQueryResult:
        """查单 (对账 / 主动轮询)。"""

    @abstractmethod
    def refund(
        self,
        *,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount_fen: int,
        reason: str,
    ) -> "RefundResult":
        """服务商退款 (sp_mchid + sub_mchid), 返回IM-B退款单号 + 状态。

        真实: POST /v3/refund/domestic/refunds, 需商户 API 私钥签名 + 平台证书。
        幂等键: out_refund_no (商户自定义退款单号, 同号重复请求返回同一退款)。
        """

    @abstractmethod
    def generate_sub_mchid(self) -> str:
        """生成特约商户号 (进件 FINISH 时IM-B返回, mock 模拟)。

        真实实现经 httpx 调IM-B applyment4sub 查询接口: 网络故障/超时/解析异常应转
        ``WxPayError`` (见其 docstring), 由 applyment.advance caller 兜底映射 502。
        """


_CLIENT_INSTANCE: Optional[WxPayClient] = None
# 双检锁保护单例初始化 (卡 692b3df7): 多请求/线程并发首调时避免重复构造 client。
# 参考 AIModelManager 模式: check None → lock → re-check None → init。
_CLIENT_LOCK = Lock()


def _build_client_from_settings() -> WxPayClient:
    """按 settings.WX_PAY_MODE 构造 client (卡 6c8f930c A1)。

    - mock (默认): MockWxPayClient, 不要求凭证, 现有环境零配置。
    - real: RealWxPayClient, 凭证齐备校验 fail-loud —— 任一必需项缺失 →
      WxPayError (不静默回退 mock: mock 假 paySign 混进真实支付流比启动报错
      更危险; mock 阶段的人工排障成本远低于资金错配)。
    - 其他值: WxPayError (不猜默认)。
    """
    from app.core.config import settings

    mode = (getattr(settings, "WX_PAY_MODE", "mock") or "mock").strip().lower()
    if mode == "mock":
        from app.services.wx_pay.mock_client import MockWxPayClient

        return MockWxPayClient()
    if mode == "real":
        from app.services.wx_pay.real_client import RealWxPayClient

        return RealWxPayClient(settings)
    raise WxPayError(f"WX_PAY_MODE 配置非法: {mode!r} (仅支持 mock|real)")


def get_wxpay_client() -> WxPayClient:
    """工厂: 按 settings.WX_PAY_MODE 返回 MockWxPayClient / RealWxPayClient。

    默认 mock (无真实凭证), 调用方零改动; real 凭证缺失在首调抛 WxPayError
    (fail-loud)。单例: client 无状态, 跨请求复用。
    线程安全: 双检锁保证并发首调只初始化一次 (_CLIENT_INSTANCE 赋值原子, 但
    构造 + 赋值非原子, 无锁竞态下可能多次构造仅留最后一个, 浪费且短暂泄漏)。
    """
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        with _CLIENT_LOCK:
            if _CLIENT_INSTANCE is None:  # re-check: 持锁期间可能已被另一线程初始化
                _CLIENT_INSTANCE = _build_client_from_settings()
    return _CLIENT_INSTANCE


def reset_wxpay_client_for_testing(client: Optional["WxPayClient"] = None) -> None:
    """测试用: 重置 / 注入 client 单例 (mock 注入固定值或 None 触发重建)。"""
    global _CLIENT_INSTANCE
    _CLIENT_INSTANCE = client

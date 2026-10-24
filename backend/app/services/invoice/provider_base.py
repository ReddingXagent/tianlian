"""
第三方开票平台适配器框架 — 抽象基类 + 工厂。

设计:
- InvoiceProvider (ABC): 统一 4 个能力口子 — refresh_token / issue_invoice /
  query_invoice / void_invoice。各平台 (诺诺/百旺/航信) 各自实现。
- get_provider(platform_type, config, ...): 工厂, 按平台类型路由到具体适配器。
  懒加载具体类避免 provider_base <-> 子模块循环导入。
- 结果用 dataclass 归一化, 隔离各平台原始响应差异。

config 为 duck-typed 对象 (通常是 InvoicePlatformConfig ORM 实例), 至少提供各适配器
所需属性 (api_url / app_key / app_secret / access_token_url / private_key_enc /
token_cache_json 等)。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from app.models.ops_settlement.invoice_platform_config import PlatformType


# ───────────────────────── 归一化结果 ─────────────────────────


@dataclass
class IssueResult:
    """开票结果。status: pending(异步受理中) | success | failed。"""

    status: str
    request_id: Optional[str] = None     # 平台请求号 / 流水号 (fpqqlsh)
    invoice_no: Optional[str] = None      # 发票号码
    invoice_url: Optional[str] = None     # 发票 PDF/预览地址
    message: Optional[str] = None         # 平台返回描述
    raw: Optional[dict] = field(default=None, repr=False)


@dataclass
class QueryResult:
    """查询发票结果。status: pending | success | failed。"""

    status: str
    invoice_no: Optional[str] = None
    invoice_url: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[dict] = field(default=None, repr=False)


@dataclass
class VoidResult:
    """冲红/作废结果。status: success | failed。"""

    status: str
    message: Optional[str] = None
    raw: Optional[dict] = field(default=None, repr=False)


# ───────────────────────── 抽象基类 ─────────────────────────


class InvoiceProvider(ABC):
    """第三方开票平台适配器统一接口。

    子类构造签名约定: __init__(self, config, http_client=None, clock=None)。
    - http_client: 注入的 HTTP 客户端 (默认 httpx.Client), 便于测试 mock。
    - clock: 返回当前 aware UTC datetime 的可调用, 便于 token 过期判断测试。
    """

    def __init__(self, config: Any, http_client: Any = None, clock: Any = None) -> None:
        self.config = config
        self._http = http_client
        self._clock = clock

    @abstractmethod
    def refresh_token(self, force: bool = False) -> str:
        """获取/刷新 access_token (带缓存, 过期前提前刷新)。返回有效 token。"""

    @abstractmethod
    def issue_invoice(self, payload: dict) -> IssueResult:
        """发起开票请求 (同步受理 / 异步受理后由回调推进)。"""

    @abstractmethod
    def query_invoice(
        self,
        request_id: Optional[str] = None,
        invoice_no: Optional[str] = None,
    ) -> QueryResult:
        """查询发票开具状态 (按平台流水号或发票号)。"""

    @abstractmethod
    def void_invoice(self, invoice_no: str, reason: Optional[str] = None) -> VoidResult:
        """发票作废 / 红冲。"""


# ───────────────────────── 工厂 ─────────────────────────


def _resolve_platform_type(platform_type: Union[PlatformType, str]) -> PlatformType:
    if isinstance(platform_type, PlatformType):
        return platform_type
    try:
        return PlatformType(platform_type)
    except ValueError as exc:
        raise ValueError(f"不支持的开票平台类型: {platform_type}") from exc


def get_provider(
    platform_type: Union[PlatformType, str],
    config: Any,
    http_client: Any = None,
    clock: Any = None,
) -> InvoiceProvider:
    """按平台类型构造适配器。

    懒加载具体适配器类, 避免 provider_base 与子模块循环导入。
    PlatformType.OTHER 及未知类型无适配器 -> ValueError。
    """
    pt = _resolve_platform_type(platform_type)

    # 懒导入: 子模块 import provider_base, 此处反向引用子模块 -> 必须延迟到函数体。
    from app.services.invoice.nuonuo_provider import NuonuoProvider
    from app.services.invoice.baiwang_provider import BaiwangProvider
    from app.services.invoice.hangxin_provider import HangxinProvider

    registry = {
        PlatformType.NUONUO: NuonuoProvider,
        PlatformType.BAIWANG: BaiwangProvider,
        PlatformType.HANGXIN: HangxinProvider,
    }
    cls = registry.get(pt)
    if cls is None:
        raise ValueError(f"平台类型 {pt.value} 暂未接入适配器")
    return cls(config, http_client=http_client, clock=clock)

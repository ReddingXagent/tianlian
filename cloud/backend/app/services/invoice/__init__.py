"""
第三方开票平台适配器框架。

- provider_base: InvoiceProvider ABC + 结果 dataclass + get_provider 工厂
- nuonuo_provider: 诺诺 (已实现 OAuth 刷新 + RSA-SHA256 签名 + 开票/查询/作废/回调)
- baiwang_provider / hangxin_provider: 骨架占位
"""
from app.services.invoice.provider_base import (
    InvoiceProvider,
    IssueResult,
    QueryResult,
    VoidResult,
    get_provider,
)

__all__ = [
    "InvoiceProvider",
    "IssueResult",
    "QueryResult",
    "VoidResult",
    "get_provider",
]

"""
百旺 (baiwang) 开票平台适配器 — 骨架占位。

接入待办: 百旺开放平台 token 换取 / 开票报文 / 回调协议确定后补全实现。
当前所有能力抛 NotImplementedError, 工厂可实例化以便框架联调, 但不可实际调用。
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.invoice.provider_base import (
    InvoiceProvider,
    IssueResult,
    QueryResult,
    VoidResult,
)

_NOT_IMPL = "百旺 (baiwang) 开票适配器尚未实现, 待平台协议接入后补全"


class BaiwangProvider(InvoiceProvider):
    """百旺开票适配器 (骨架)。"""

    def __init__(
        self,
        config: Any,
        http_client: Any = None,
        clock: Callable = None,
    ) -> None:
        super().__init__(config, http_client=http_client, clock=clock)

    def refresh_token(self, force: bool = False) -> str:  # noqa: D401
        raise NotImplementedError(_NOT_IMPL)

    def issue_invoice(self, payload: dict) -> IssueResult:
        raise NotImplementedError(_NOT_IMPL)

    def query_invoice(self, request_id=None, invoice_no=None) -> QueryResult:
        raise NotImplementedError(_NOT_IMPL)

    def void_invoice(self, invoice_no: str, reason: str = None) -> VoidResult:
        raise NotImplementedError(_NOT_IMPL)

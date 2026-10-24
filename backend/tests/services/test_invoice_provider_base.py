"""
InvoiceProvider 抽象基类 + 工厂契约测试。

覆盖:
- ABC 契约: 未实现全部抽象方法的子类不可实例化
- get_provider 工厂: 各平台类型路由正确
- 未知平台类型 -> ValueError
- 结果 dataclass 默认值
"""
import pytest

from app.models.ops_settlement.invoice_platform_config import PlatformType
from app.services.invoice.provider_base import (
    InvoiceProvider,
    IssueResult,
    QueryResult,
    VoidResult,
    get_provider,
)
from app.services.invoice.nuonuo_provider import NuonuoProvider
from app.services.invoice.baiwang_provider import BaiwangProvider
from app.services.invoice.hangxin_provider import HangxinProvider


class _Config:
    """最小可用的平台配置替身 (duck-typed)。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestABCContract:
    def test_cannot_instantiate_abstract_directly(self):
        """InvoiceProvider 是 ABC, 缺抽象方法实现不可实例化。"""
        with pytest.raises(TypeError):
            InvoiceProvider(_Config())  # type: ignore[abstract]

    def test_subclass_missing_method_is_abstract(self):
        class Incomplete(InvoiceProvider):
            def refresh_token(self, force=False):
                return "x"

            # 缺 issue_invoice / query_invoice / void_invoice

        with pytest.raises(TypeError):
            Incomplete(_Config())  # type: ignore[abstract]

    def test_abstract_methods_present(self):
        names = InvoiceProvider.__abstractmethods__
        assert {"refresh_token", "issue_invoice", "query_invoice", "void_invoice"} <= names


class TestFactory:
    def test_get_provider_nuonuo(self):
        p = get_provider(PlatformType.NUONUO, _Config())
        assert isinstance(p, NuonuoProvider)
        assert isinstance(p, InvoiceProvider)

    def test_get_provider_baiwang(self):
        p = get_provider(PlatformType.BAIWANG, _Config())
        assert isinstance(p, BaiwangProvider)

    def test_get_provider_hangxin(self):
        p = get_provider(PlatformType.HANGXIN, _Config())
        assert isinstance(p, HangxinProvider)

    def test_get_provider_accepts_str(self):
        """工厂接受字符串平台类型 (来自 API 层)。"""
        p = get_provider("nuonuo", _Config())
        assert isinstance(p, NuonuoProvider)

    def test_get_provider_unknown_raises(self):
        with pytest.raises(ValueError):
            get_provider("unknown-platform", _Config())

    def test_get_provider_other_raises(self):
        """PlatformType.OTHER 无对应适配器 -> ValueError。"""
        with pytest.raises(ValueError):
            get_provider(PlatformType.OTHER, _Config())

    def test_factory_injects_http_client(self):
        marker = object()
        p = get_provider(PlatformType.NUONUO, _Config(), http_client=marker)
        assert p._http is marker


class TestResultDataclasses:
    def test_issue_result_defaults(self):
        r = IssueResult(status="pending")
        assert r.status == "pending"
        assert r.request_id is None
        assert r.invoice_no is None
        assert r.raw is None

    def test_query_result_defaults(self):
        r = QueryResult(status="success")
        assert r.status == "success"
        assert r.invoice_no is None

    def test_void_result_defaults(self):
        r = VoidResult(status="success")
        assert r.status == "success"
        assert r.message is None

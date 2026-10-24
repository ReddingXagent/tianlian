"""wx_pay.client 单元测试 (契约 §2 支付, 工作卡 a2592b61)

被测: app/services/wx_pay/client.py — 客户端抽象 + 工厂 + dataclass。
      app/services/wx_pay/mock_client.py — mock 实现 (本期唯一实现, 不联网)。

设计澄清 (不谄媚): client.py 当前是 ABC + 工厂, 无真实 HTTP 实现 (RealWxPayClient 未提供,
凭证到位才新增)。故任务卡所述 "HTTP 请求构造 / 响应解析 / 超时异常 / mock requests" 无法
直接落到 client.py —— 被测对象里没有 requests/httpx 调用。强行 mock requests 会测一个
不存在的类。本文件测真实存在的可测面:
  1. MockWxPayClient 各方法行为 (unified_order 五字段 / verify_and_decrypt_notify 响应解析
     各分支 [正常JSON/缺字段/非JSON/dict直传/amount默认] / query_order / refund / generate_sub_mchid)
  2. get_wxpay_client 单例 + 双检锁 (重复调用同实例 / reset(None) 重建 / reset(替身) 注入)
  3. 并发首调只初始化一次 (双检锁线程安全)
  4. WxPayClient ABC 不可实例化
  5. WxPayError 异常语义
  6. dataclass 结构 (PrepayResult / NotifyResult / OrderQueryResult / RefundResult)

verify_and_decrypt_notify 的明文 JSON 解析分支即真实可测的 "响应解析" (正常/错误码/非JSON)。
铁律: 只加测试, 不改 production。
"""
import json
import threading
from unittest.mock import patch

import pytest

from app.services.wx_pay import client as cli
from app.services.wx_pay import mock_client as mc
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


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每测前后清空 client 单例, 隔离单例/并发测试对全局 _CLIENT_INSTANCE 的影响。"""
    reset_wxpay_client_for_testing(None)
    yield
    reset_wxpay_client_for_testing(None)


# ═══════════════════════════════════════════════════════════════
# MockWxPayClient.unified_order
# ═══════════════════════════════════════════════════════════════
class TestUnifiedOrder:
    def _client(self):
        return MockWxPayClient()

    def test_returns_prepay_result_with_five_fields(self):
        r = self._client().unified_order(
            out_trade_no="TL_20260810_abc", sub_mchid="2490000001",
            amount_fen=100, description="充电订单", openid="oXXXX",
            scene="miniprogram",
        )
        assert isinstance(r, PrepayResult)
        # 端侧 wx.requestPayment 五字段 (camelCase 由 service 层映射, client 出 dataclass)
        assert r.prepay_id
        assert r.time_stamp
        assert r.nonce_str
        assert r.package == f"prepay_id={r.prepay_id}"
        assert r.sign_type == "RSA"
        assert r.pay_sign

    def test_time_stamp_is_unix_seconds_string(self):
        r = self._client().unified_order(
            out_trade_no="x", sub_mchid="1", amount_fen=0,
            description="d", openid="o", scene="app",
        )
        # time_stamp 为可解析的秒级 unix 时间戳字符串
        ts = int(r.time_stamp)
        assert ts > 1_600_000_000  # 2020 年之后, 合理范围

    def test_two_calls_produce_different_values(self):
        """随机性: 两次下单 prepay_id / nonce_str / pay_sign 不同。"""
        c = self._client()
        r1 = c.unified_order(out_trade_no="a", sub_mchid="1", amount_fen=0,
                             description="d", openid="o", scene="miniprogram")
        r2 = c.unified_order(out_trade_no="b", sub_mchid="1", amount_fen=0,
                             description="d", openid="o", scene="miniprogram")
        assert r1.prepay_id != r2.prepay_id
        assert r1.nonce_str != r2.nonce_str
        assert r1.pay_sign != r2.pay_sign

    def test_prepay_id_has_wx_prefix(self):
        r = self._client().unified_order(
            out_trade_no="x", sub_mchid="1", amount_fen=0,
            description="d", openid="o", scene="miniprogram",
        )
        assert r.prepay_id.startswith("wx")


# ═══════════════════════════════════════════════════════════════
# MockWxPayClient.verify_and_decrypt_notify — 响应解析各分支
# ═══════════════════════════════════════════════════════════════
class TestVerifyAndDecryptNotify:
    def _client(self):
        return MockWxPayClient()

    def test_bytes_json_success(self):
        """bytes 明文 JSON + SUCCESS → NotifyResult + paid_at。"""
        body = json.dumps({
            "out_trade_no": "TL_1", "transaction_id": "4200000001",
            "trade_state": "SUCCESS", "amount": {"total": 100},
        }).encode("utf-8")
        r = self._client().verify_and_decrypt_notify(body, {})
        assert isinstance(r, NotifyResult)
        assert r.out_trade_no == "TL_1"
        assert r.wx_transaction_id == "4200000001"
        assert r.trade_state == "SUCCESS"
        assert r.amount_fen == 100
        assert r.paid_at is not None

    def test_str_json_accepted(self):
        """str 入参 (非 bytes) 也能解析。"""
        body = json.dumps({
            "out_trade_no": "TL_2", "transaction_id": "4200",
            "trade_state": "success",  # 小写也归一化为大写
        })
        r = self._client().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.trade_state == "SUCCESS"  # .upper()

    def test_dict_direct_input(self):
        """dict 直传 (非 JSON 串) 也能解析。"""
        data = {
            "out_trade_no": "TL_3", "transaction_id": "4200",
            "trade_state": "SUCCESS",
        }
        r = self._client().verify_and_decrypt_notify(data, {})
        assert r is not None
        assert r.out_trade_no == "TL_3"

    def test_non_success_paid_at_none(self):
        """trade_state 非 SUCCESS (如 NOTPAY) → paid_at=None。"""
        body = json.dumps({
            "out_trade_no": "TL_4", "transaction_id": "4200",
            "trade_state": "NOTPAY",
        }).encode()
        r = self._client().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.paid_at is None
        assert r.trade_state == "NOTPAY"

    def test_amount_missing_defaults_zero(self):
        """amount 对象缺失 → amount_fen=0 (不抛)。"""
        body = json.dumps({
            "out_trade_no": "TL_5", "transaction_id": "4200",
            "trade_state": "SUCCESS",
        }).encode()
        r = self._client().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.amount_fen == 0

    def test_amount_total_missing_defaults_zero(self):
        """amount 在但缺 total → amount_fen=0。"""
        body = json.dumps({
            "out_trade_no": "TL_6", "transaction_id": "4200",
            "trade_state": "SUCCESS", "amount": {},
        }).encode()
        r = self._client().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.amount_fen == 0

    def test_non_json_returns_none(self):
        """非 JSON body → None (验签/解析失败)。"""
        assert self._client().verify_and_decrypt_notify(b"not-a-json", {}) is None

    def test_invalid_bytes_returns_none(self):
        """无法 decode 的 bytes → None。"""
        assert self._client().verify_and_decrypt_notify(b"\xff\xfe\x00bad", {}) is None

    def test_missing_out_trade_no_returns_none(self):
        """缺 out_trade_no → None。"""
        body = json.dumps({"transaction_id": "4200", "trade_state": "SUCCESS"}).encode()
        assert self._client().verify_and_decrypt_notify(body, {}) is None

    def test_missing_transaction_id_returns_none(self):
        """缺 transaction_id → None。"""
        body = json.dumps({"out_trade_no": "TL", "trade_state": "SUCCESS"}).encode()
        assert self._client().verify_and_decrypt_notify(body, {}) is None

    def test_missing_trade_state_returns_none(self):
        """缺 trade_state → None。"""
        body = json.dumps({"out_trade_no": "TL", "transaction_id": "4200"}).encode()
        assert self._client().verify_and_decrypt_notify(body, {}) is None

    def test_non_dict_json_returns_none(self):
        """合法 JSON 但非 dict (如数组) → None。"""
        assert self._client().verify_and_decrypt_notify(b"[1,2,3]", {}) is None

    def test_none_body_returns_none(self):
        assert self._client().verify_and_decrypt_notify(None, {}) is None


# ═══════════════════════════════════════════════════════════════
# MockWxPayClient.query_order / refund / generate_sub_mchid
# ═══════════════════════════════════════════════════════════════
class TestQueryOrder:
    def test_returns_success_with_4200_tx_id(self):
        r = MockWxPayClient().query_order("TL_q")
        assert isinstance(r, OrderQueryResult)
        assert r.out_trade_no == "TL_q"
        assert r.trade_state == "SUCCESS"
        assert r.wx_transaction_id.startswith("4200")
        assert r.paid_at is not None

    def test_two_calls_different_tx_id(self):
        c = MockWxPayClient()
        r1 = c.query_order("a")
        r2 = c.query_order("b")
        assert r1.wx_transaction_id != r2.wx_transaction_id


class TestRefund:
    def test_returns_success_with_echoed_fields(self):
        r = MockWxPayClient().refund(
            out_trade_no="TL_r", out_refund_no="RF_1",
            refund_amount_fen=50, reason="用户申请",
        )
        assert isinstance(r, RefundResult)
        assert r.out_refund_no == "RF_1"           # 回显
        assert r.refund_amount_fen == 50           # 金额回显校验
        assert r.status == "SUCCESS"
        assert r.refund_id.startswith("4200")


class TestGenerateSubMchid:
    def test_has_mock_prefix_and_ten_digits(self):
        """mock_ 前缀 + 10 位数字 (卡 d53a2f2f: 显式标识避免与真实商户号混淆)。"""
        sub = MockWxPayClient().generate_sub_mchid()
        assert sub.startswith("mock_")
        digits = sub[len("mock_"):]
        assert len(digits) == 10
        assert digits.isdigit()

    def test_two_calls_different(self):
        c = MockWxPayClient()
        assert c.generate_sub_mchid() != c.generate_sub_mchid()


# ═══════════════════════════════════════════════════════════════
# get_wxpay_client — 单例 + 双检锁
# ═══════════════════════════════════════════════════════════════
class TestGetWxpayClient:
    def test_returns_mock_instance(self):
        c = get_wxpay_client()
        assert isinstance(c, MockWxPayClient)

    def test_singleton_repeated_calls_same_instance(self):
        """无 reset 时, 重复调用返回同一实例 (单例)。"""
        c1 = get_wxpay_client()
        c2 = get_wxpay_client()
        assert c1 is c2

    def test_reset_none_rebuilds_new_instance(self):
        """reset(None) 后再次 get → 新实例 (与旧实例不同)。"""
        old = get_wxpay_client()
        reset_wxpay_client_for_testing(None)
        new = get_wxpay_client()
        assert new is not old
        assert isinstance(new, MockWxPayClient)

    def test_reset_injects_custom_client(self):
        """reset(替身) 注入固定 client, get 原样返回。"""
        stub = MockWxPayClient()  # 真实替身 (也可用任意 WxPayClient 子类)
        reset_wxpay_client_for_testing(stub)
        assert get_wxpay_client() is stub

    def test_concurrent_first_calls_init_once(self):
        """双检锁线程安全: 多线程并发首调, MockWxPayClient 仅构造一次。

        patch 构造器计数: 若无线程保护, 并发可能多次构造 (短暂泄漏 + 仅留最后一个)。
        双检锁保证只构造一次, 所有线程拿到同一实例。
        """
        reset_wxpay_client_for_testing(None)
        call_count = {"n": 0}
        orig_init = MockWxPayClient.__init__

        def counting_init(self, *a, **kw):
            call_count["n"] += 1
            orig_init(self, *a, **kw)

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(get_wxpay_client())

        with patch.object(MockWxPayClient, "__init__", counting_init):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # 所有线程拿到同一实例
        assert len(results) == 8
        assert all(r is results[0] for r in results)
        # 双检锁: 仅构造一次
        assert call_count["n"] == 1


# ═══════════════════════════════════════════════════════════════
# WxPayClient ABC — 不可实例化
# ═══════════════════════════════════════════════════════════════
class TestWxPayClientABC:
    def test_abstract_cannot_instantiate(self):
        """WxPayClient 是 ABC, 有 5 个 abstractmethod, 不可直接实例化。"""
        with pytest.raises(TypeError):
            WxPayClient()

    def test_subclass_missing_methods_cannot_instantiate(self):
        """子类未实现全部抽象方法仍不可实例化。"""
        class Partial(WxPayClient):
            def unified_order(self, **kw):
                pass
        with pytest.raises(TypeError):
            Partial()

    def test_mock_client_is_subclass(self):
        assert issubclass(MockWxPayClient, WxPayClient)


# ═══════════════════════════════════════════════════════════════
# WxPayError — 异常语义
# ═══════════════════════════════════════════════════════════════
class TestWxPayError:
    def test_is_exception_subclass(self):
        assert issubclass(WxPayError, Exception)

    def test_raisable_and_catchable(self):
        with pytest.raises(WxPayError, match="接口异常"):
            raise WxPayError("IM-B接口异常")

    def test_preserves_cause(self):
        orig = ConnectionError("timeout")
        try:
            raise WxPayError("wrap") from orig
        except WxPayError as e:
            assert e.__cause__ is orig


# ═══════════════════════════════════════════════════════════════
# dataclass 结构
# ═══════════════════════════════════════════════════════════════
class TestDataclasses:
    def test_prepay_result_fields(self):
        r = PrepayResult(
            prepay_id="p", time_stamp="1", nonce_str="n",
            package="prepay_id=p", sign_type="RSA", pay_sign="s",
        )
        assert r.prepay_id == "p"
        assert r.sign_type == "RSA"

    def test_notify_result_fields(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        r = NotifyResult(
            out_trade_no="o", wx_transaction_id="t", trade_state="SUCCESS",
            amount_fen=100, paid_at=now,
        )
        assert r.trade_state == "SUCCESS"
        assert r.amount_fen == 100
        assert r.paid_at == now

    def test_order_query_result_fields(self):
        r = OrderQueryResult(out_trade_no="o", wx_transaction_id="t",
                             trade_state="SUCCESS", paid_at=None)
        assert r.wx_transaction_id == "t"
        assert r.paid_at is None

    def test_refund_result_fields(self):
        r = RefundResult(
            out_refund_no="rf", refund_id="4200", status="SUCCESS",
            refund_amount_fen=50,
        )
        assert r.out_refund_no == "rf"
        assert r.status == "SUCCESS"

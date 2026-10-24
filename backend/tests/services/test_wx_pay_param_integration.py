"""query_order/generate_sub_mchid 参数化测试 (卡 7f5b4d4f A2)

被测: app/services/wx_pay/real_client.py —
- query_order(out_trade_no, sub_mchid=...) 可选参数: 服务商查单接口必传
  sub_mchid, 旧骨架用 sp_mchid 占位 (_sub_mchid_hint), 本卡参数化。
- generate_sub_mchid(applyment_id=...) 可选参数: applyment4sub 查询端点
  按 applyment_id 查询; applyment service 的 Merchant 模型当前无IM-B侧
  applyment_id 列 (仅自产 business_code), 故默认无参走 /latest 端点不变,
  集成点留清晰接口 (调用方持 applyment_id 时传入)。

现状语义 (不破坏):
- query_order(out_trade_no) 单参调用 → sub_mchid 回退 _sub_mchid_hint (A1 行为)
- generate_sub_mchid() 无参 → GET /v3/applyment4sub/applyment_id/latest

商户档案集成: applyment.advance 持 merchant (business_code) 但无IM-B
applyment_id 字段, 造列属丁哥拍板项 —— 本卡不造表, 接口就位。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.wx_pay.client import WxPayError
from app.services.wx_pay.real_client import RealWxPayClient


@pytest.fixture(scope="module")
def keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _settings(tmp_path, keypair, **over):
    priv, _ = keypair
    pem = tmp_path / "k_param.pem"
    pem.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    base = dict(
        WX_PAY_MODE="real",
        WX_PAY_SP_MCHID="1900000001",
        WX_PAY_PRIVATE_KEY_PATH=str(pem),
        WX_PAY_CERT_SERIAL="SERIAL0001",
        WX_PAY_APIV3_KEY="0123456789abcdef0123456789abcdef",
        WX_PAY_APPID_MINIPROGRAM="wx1111111111111111",
        WX_PAY_APPID_APP="wx2222222222222222",
        WX_PAY_NOTIFY_URL="https://api.tianlian.example/v1/business/payments/notify",
    )
    base.update(over)
    return SimpleNamespace(**base)


class _RecordingTransport:
    """记录 GET url 的替身 (query/applyment 两端点)。"""

    def __init__(self, response_for=None):
        self.urls = []
        self._response_for = response_for or {}

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        for substr, payload in self._response_for.items():
            if substr in url:
                r = SimpleNamespace()
                r.status_code = 200
                r.json = lambda p=payload: p
                return r
        r = SimpleNamespace()
        r.status_code = 200
        r.json = lambda: {}
        return r

    def post(self, url, json=None, headers=None, timeout=None):
        raise AssertionError(f"unexpected post {url}")


class TestQueryOrderParameterized:
    def test_query_order_with_sub_mchid(self, keypair, tmp_path):
        """query_order 显式传 sub_mchid → URL query 带该 sub_mchid (订单侧解析值)。"""
        tp = _RecordingTransport({"out-trade-no": {
            "out_trade_no": "TL_q1", "transaction_id": "4200Q1",
            "trade_state": "SUCCESS",
            "success_time": "2026-08-17T10:00:00+08:00",
        }})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        r = c.query_order("TL_q1", sub_mchid="2490000088")
        assert r.trade_state == "SUCCESS"
        assert "sub_mchid=2490000088" in tp.urls[0]

    def test_query_order_default_falls_back_to_hint(self, keypair, tmp_path):
        """单参调用 (兼容现状) → sub_mchid 用 _sub_mchid_hint (sp_mchid 占位)。"""
        tp = _RecordingTransport({"out-trade-no": {
            "out_trade_no": "TL_q2", "trade_state": "NOTPAY",
        }})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        c.query_order("TL_q2")
        assert "sub_mchid=1900000001" in tp.urls[0]  # = WX_PAY_SP_MCHID (hint)

    def test_query_order_url_has_sp_mchid_filter(self, keypair, tmp_path):
        """服务商查单: URL 同时带 sp_mchid + sub_mchid 过滤。"""
        tp = _RecordingTransport({"out-trade-no": {"trade_state": "NOTPAY"}})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        c.query_order("TL_q3", sub_mchid="2490000099")
        assert "sp_mchid=1900000001" in tp.urls[0]
        assert "sub_mchid=2490000099" in tp.urls[0]


class TestGenerateSubMchidParameterized:
    def test_generate_sub_mchid_with_applyment_id(self, keypair, tmp_path):
        """显式 applyment_id → GET /v3/applyment4sub/applyment_id/{id}。"""
        tp = _RecordingTransport({"applyment4sub": {
            "applyment_state": "FINISH", "sub_mchid": "2490000123",
        }})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        sub = c.generate_sub_mchid(applyment_id=2000012345)
        assert sub == "2490000123"
        assert "/v3/applyment4sub/applyment_id/2000012345" in tp.urls[0]

    def test_generate_sub_mchid_no_arg_uses_latest(self, keypair, tmp_path):
        """无参 (兼容现状) → GET /v3/applyment4sub/applyment_id/latest。"""
        tp = _RecordingTransport({"applyment4sub": {
            "applyment_state": "FINISH", "sub_mchid": "2490000456",
        }})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        assert c.generate_sub_mchid() == "2490000456"
        assert "/v3/applyment4sub/applyment_id/latest" in tp.urls[0]

    def test_applyment_not_finish_raises(self, keypair, tmp_path):
        """进件未 FINISH (无 sub_mchid) → WxPayError (带 applyment_state)。"""
        tp = _RecordingTransport({"applyment4sub": {
            "applyment_state": "AUDITING",
        }})
        c = RealWxPayClient(_settings(tmp_path, keypair), transport=tp)
        with pytest.raises(WxPayError, match="AUDITING"):
            c.generate_sub_mchid(applyment_id=9876)


class TestApplymentServiceIntegrationSeam:
    """applyment service 集成缝: Merchant 无IM-B applyment_id 列 (摸底确认),
    advance 流程持 business_code 而非IM-B数字 ID。本卡留参数化接口 +
    TODO, 不造列 (丁哥拍板项)。固化: applyment.advance 调用兼容 (无参)。"""

    def test_advance_calls_generate_sub_mchid_compatible(self, keypair, tmp_path):
        """applyment.advance FINISH → client.generate_sub_mchid() 零参调用兼容。"""
        from app.services.wx_pay import applyment as ap
        from app.models.merchant import (
            Merchant, MerchantType, MerchantStatus, ApplymentState,
        )

        merchant = Merchant(
            business_code="APL_seam", merchant_type=MerchantType.MICRO_MERCHANT,
            merchant_name="m", applyment_state=ApplymentState.SIGNING,
            merchant_status=MerchantStatus.PENDING,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        client = MagicMock()
        client.generate_sub_mchid.return_value = "2490000777"
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ap, "get_wxpay_client", lambda: client)
            m = ap.advance(db, merchant, "finish")
        client.generate_sub_mchid.assert_called_once_with()
        assert m.sub_mchid == "2490000777"

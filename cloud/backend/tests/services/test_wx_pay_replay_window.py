"""回调防重放窗测试 (卡 071194e4 A3, 凭证无关)

被测: app/services/wx_pay/real_client.py::verify_and_decrypt_notify —
envelope.create_time (IM-B event 级时间戳, ISO8601 RFC3339 +08:00) 防重放校验:
- 窗口内 (|create_time - now| <= 300s) → 放行 (正常解密落 NotifyResult)
- 窗外 (过旧/过新) → 拒绝 (None, 不进解密 → 不落 PAID) + WARNING 日志
- create_time 缺失/解析失败/无时区 → fail-closed 拒绝
  (与 A1 金额闸 / appid 硬闸的资金安全风格一致: 不可证新即拒)

真实链路 (RealWxPayClient) 专属: mock 明文回调零签名零重放面, 不校验
(mock_client 不动, mock 阶段行为零变更)。

时序: 平台验签之后 (伪造报文先被签名闸拦, 不产生时间窗日志噪音),
AES-GCM 解密之前。

时钟打桩: patch real_client._now_utc → 固定 now (窗口 delta 精确可控,
复用模块函数注入缝, 不改 WxPayClient 抽象签名)。
"""
import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.wx_pay.real_client import RealWxPayClient


# 固定时钟: 窗口 delta 精确可控 (避开真实时钟在构造与断言间推进的毛刺)
FIXED_NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)

_APIV3_KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture(scope="module")
def keypair():
    """商户 API 私钥假密钥对 (RealWxPayClient 构造期签名校验用)。"""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _client(keypair, tmp_path, platform_priv):
    """RealWxPayClient + 平台公钥直注 (不走证书下载链, 隔离防重放单测面)。"""
    priv, _ = keypair
    pem = tmp_path / "k_replay.pem"
    pem.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    settings = SimpleNamespace(
        WX_PAY_MODE="real",
        WX_PAY_SP_MCHID="1900000001",
        WX_PAY_PRIVATE_KEY_PATH=str(pem),
        WX_PAY_CERT_SERIAL="SERIAL0001",
        WX_PAY_APIV3_KEY=_APIV3_KEY,
        WX_PAY_APPID_MINIPROGRAM="wx1111111111111111",
        WX_PAY_APPID_APP="wx2222222222222222",
        WX_PAY_NOTIFY_URL="https://api.tianlian.example/v1/business/payments/notify",
    )
    c = RealWxPayClient(settings)
    c._platform_pubkey = platform_priv.public_key()
    return c


def _notify_body(platform_priv, create_time):
    """构造带签名的回调报文 (body + headers)。

    create_time: ISO8601 字符串; None → 不带该字段 (测缺失 fail-closed)。
    resource 为合法 AES-GCM 密文 (控制变量: 被拒时拒绝原因只能是时间窗,
    不是解密失败)。
    """
    api_key = bytes.fromhex(_APIV3_KEY)
    nonce = b"0123456789ab"
    plaintext = json.dumps({
        "sp_appid": "wx1111111111111111",
        "sp_mchid": "1900000001",
        "sub_mchid": "2490000001",
        "out_trade_no": "TL_replay1",
        "transaction_id": "4200REPLAY1",
        "trade_state": "SUCCESS",
        "amount": {"total": 8200},
        "success_time": "2026-08-17T20:00:05+08:00",
    }).encode()
    ct = AESGCM(api_key).encrypt(nonce, plaintext, b"transaction")
    envelope = {
        "id": "EV-REPLAY-1",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "ciphertext": base64.b64encode(ct).decode(),
            "nonce": nonce.decode(),
            "associated_data": "transaction",
        },
    }
    if create_time is not None:
        envelope["create_time"] = create_time
    body = json.dumps(envelope).encode()
    sig = base64.b64encode(platform_priv.sign(
        body, padding.PKCS1v15(), hashes.SHA256()
    )).decode()
    headers = {"Wechatpay-Signature": sig, "Wechatpay-Serial": "PLAT0001"}
    return body, headers


def _wx_time(dt: datetime) -> str:
    """IM-B RFC3339 报文时间 (+08:00)。"""
    return dt.astimezone(timezone(timedelta(hours=8))).strftime(
        "%Y-%m-%dT%H:%M:%S+08:00"
    )


@pytest.fixture
def platform_priv():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _verify(c, platform_priv, create_time):
    """固定时钟下跑 verify_and_decrypt_notify。"""
    body, headers = _notify_body(platform_priv, create_time)
    with patch(
        "app.services.wx_pay.real_client._now_utc", return_value=FIXED_NOW
    ):
        return c.verify_and_decrypt_notify(body, headers)


# ═══════════════════════════════════════════════════════════════
# 1. 窗口内放行
# ═══════════════════════════════════════════════════════════════
class TestReplayWindowAccepts:
    def test_create_time_recent_past_passes(self, keypair, tmp_path, platform_priv):
        """create_time = now - 295s (IM-B侧刚发出) → 放行, 正常解密出 NotifyResult。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW - timedelta(seconds=295))
        )
        assert r is not None
        assert r.out_trade_no == "TL_replay1"
        assert r.trade_state == "SUCCESS"

    def test_create_time_recent_future_passes(self, keypair, tmp_path, platform_priv):
        """create_time = now + 295s (小额时钟偏移, 双向容忍) → 放行。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW + timedelta(seconds=295))
        )
        assert r is not None

    def test_create_time_at_boundary_passes(self, keypair, tmp_path, platform_priv):
        """delta 恰为 300s (闭区间边界) → 放行 (窗含端点, 不因边界抖动误杀)。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW - timedelta(seconds=300))
        )
        assert r is not None


# ═══════════════════════════════════════════════════════════════
# 2. 窗外拒绝 (重放)
# ═══════════════════════════════════════════════════════════════
class TestReplayWindowRejects:
    def test_create_time_too_old_rejected(self, keypair, tmp_path, platform_priv):
        """create_time = now - 301s (过期重放) → None, 不落 PAID。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW - timedelta(seconds=301))
        )
        assert r is None

    def test_create_time_too_new_rejected(self, keypair, tmp_path, platform_priv):
        """create_time = now + 301s (未来报文, 时钟投毒/构造攻击) → None。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW + timedelta(seconds=301))
        )
        assert r is None

    def test_replay_far_past_rejected(self, keypair, tmp_path, platform_priv):
        """昨日回调重放 (delta ≈ 24h) → None。"""
        c = _client(keypair, tmp_path, platform_priv)
        r = _verify(
            c, platform_priv, _wx_time(FIXED_NOW - timedelta(days=1))
        )
        assert r is None

    def test_out_of_window_rejection_logs_warning(
        self, keypair, tmp_path, platform_priv, caplog
    ):
        """窗外拒绝 → WARNING 日志留痕 (风控对账可查)。"""
        import logging

        c = _client(keypair, tmp_path, platform_priv)
        with caplog.at_level(
            logging.WARNING, logger="app.services.wx_pay.real_client"
        ):
            _verify(
                c, platform_priv, _wx_time(FIXED_NOW - timedelta(days=1))
            )
        warns = [r.getMessage() for r in caplog.records
                 if r.levelno >= logging.WARNING]
        assert any("重放" in m or "create_time" in m for m in warns), warns


# ═══════════════════════════════════════════════════════════════
# 3. 时间戳缺失/非法 → fail-closed
# ═══════════════════════════════════════════════════════════════
class TestReplayWindowFailClosed:
    def test_create_time_missing_rejected(self, keypair, tmp_path, platform_priv):
        """envelope 无 create_time → None (不可证新即拒, 不默放宽)。"""
        c = _client(keypair, tmp_path, platform_priv)
        assert _verify(c, platform_priv, None) is None

    def test_create_time_missing_logs_warning(
        self, keypair, tmp_path, platform_priv, caplog
    ):
        """缺失拒绝 → WARNING 日志。"""
        import logging

        c = _client(keypair, tmp_path, platform_priv)
        with caplog.at_level(
            logging.WARNING, logger="app.services.wx_pay.real_client"
        ):
            _verify(c, platform_priv, None)
        warns = [r.getMessage() for r in caplog.records
                 if r.levelno >= logging.WARNING]
        assert any("create_time" in m for m in warns), warns

    def test_create_time_garbage_rejected(self, keypair, tmp_path, platform_priv):
        """create_time 非法字符串 → None (解析失败 fail-closed)。"""
        c = _client(keypair, tmp_path, platform_priv)
        assert _verify(c, platform_priv, "not-a-timestamp") is None

    def test_create_time_naive_rejected(self, keypair, tmp_path, platform_priv):
        """create_time 无时区 (naive, astimezone 会按进程 TZ 误读) → None。

        天链时区坑 (strptime/astimezone 隐含本地时区): naive 经 astimezone
        按进程 TZ 解释, 测试进程 TZ≠生产时会产生假窗口。fail-closed 拒绝。
        """
        c = _client(keypair, tmp_path, platform_priv)
        assert _verify(c, platform_priv, "2026-08-17T20:00:00") is None

    def test_create_time_not_string_rejected(self, keypair, tmp_path, platform_priv):
        """create_time 非字符串类型 (int/None 变体) → None。"""
        c = _client(keypair, tmp_path, platform_priv)
        assert _verify(c, platform_priv, 1786000000) is None

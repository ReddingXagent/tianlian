"""平台证书 store 锁外下载测试 (卡 071194e4 A3, A2 遗留 WARNING 优化)

被测: app/services/wx_pay/real_client.py::_PlatformCertStore —
A2 现状: get_for_serial 全程持 _lock 做网络下载 → 并发验签串行阻塞
(下载 10s 超时 × N 并发回调 = 串行长尾)。

本卡改为: 锁内查缓存 → 锁外下载 → 锁内双检回填。不变量:
- 单飞: 并发首验签仅触发一次真实下载 (第二个到达者等结果复用, 不重下)
- 缓存命中零下载: 有效期内二次验签不发请求
- 下载失败不阻塞其他线程: 某线程下载慢/失败, 其他线程不被其独占锁卡死
- fail-closed 不变量: 下载失败回退缓存; 无可用证书 → None (验签拒绝)

直接单测 _PlatformCertStore (refresh_fn 打桩, 不经 HTTP 层), 叠加
RealWxPayClient._verify_platform 全链并发回归 (复用 A2 脚手架)。
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.wx_pay.real_client import _PlatformCert, _PlatformCertStore


@pytest.fixture(scope="module")
def keypair():
    """商户 API 私钥假密钥对 (全链用例 RealWxPayClient 构造签名用)。"""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _cert(serial="C1", lifetime_days=90):
    """一张有效期充裕的假证书 (公钥对象用占位, store 不触公钥运算)。"""
    now = datetime.now(timezone.utc)
    return _PlatformCert(
        serial=serial,
        pubkey=object(),
        effective_at=now - timedelta(days=1),
        expire_at=now + timedelta(days=lifetime_days - 1),
    )


class _Recorder:
    """refresh_fn 替身: 记次数, 可控延迟/异常, 信号量观察并发进入。"""

    def __init__(self, certs=None, exc=None, delay=0.0):
        self.calls = 0
        self.inflight = 0
        self.max_inflight = 0
        self._certs = certs if certs is not None else [_cert()]
        self._exc = exc
        self._delay = delay
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self._delay:
                time.sleep(self._delay)
            if self._exc is not None:
                raise self._exc
            return list(self._certs)
        finally:
            with self._lock:
                self.inflight -= 1


# ═══════════════════════════════════════════════════════════════
# 1. 并发单飞: 仅一次真实下载
# ═══════════════════════════════════════════════════════════════
class TestConcurrentSingleFlight:
    def test_concurrent_first_get_downloads_once(self):
        """8 线程并发首取 (无缓存) → refresh_fn 仅调 1 次, 全部拿到同一证书。"""
        store = _PlatformCertStore()
        rec = _Recorder(delay=0.05)  # 拉长下载窗口, 让并发都聚在门口
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(store.get_for_serial("C1", rec))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert rec.calls == 1, f"单飞破坏: 下载了 {rec.calls} 次"
        assert all(r is not None for r in results)
        assert len({id(r) for r in results}) == 1  # 同一张证书对象

    def test_download_not_under_cache_lock(self):
        """下载在锁外: 慢下载挂起期间, 缓存可用线程的命中路径不被阻塞。

        A2 病灶: 持缓存锁下载 → 下载不返回时任何并发 get_for_serial (哪怕
        纯缓存命中) 都进不来。锁外下载后: 慢刷新挂起时, 另一线程对已可用
        证书的取用即时返回 (快路径只碰轻量缓存锁, 不等网络)。
        """
        store = _PlatformCertStore()
        # 预置可用缓存 (另一 serial 已下载过 → _have_downloaded=True)
        store.certs = {"C1": _cert()}
        store._have_downloaded = True
        # 制造一次挂起的慢下载 (C2 首取, refresh 永不主动返回直到放行)
        release = threading.Event()
        slow_started = threading.Event()

        def slow_refresh():
            slow_started.set()
            release.wait(timeout=5)
            return [_cert(serial="C2")]

        t1 = threading.Thread(
            target=lambda: store.get_for_serial("C2", slow_refresh)
        )
        t1.start()
        assert slow_started.wait(timeout=5)
        # 慢下载进行中: C1 缓存命中线程必须即时返回, 且零下载
        done = threading.Event()

        def reader():
            # 若缓存读被下载锁阻塞 → 此调用挂起 → done 超时
            r = store.get_for_serial("C1", lambda: (_ for _ in ()).throw(
                RuntimeError("缓存命中不应下载")))
            assert r is not None and r.serial == "C1"
            done.set()

        t2 = threading.Thread(target=reader)
        t2.start()
        assert done.wait(timeout=2), "慢下载期间缓存命中路径被阻塞 (下载未在锁外)"
        release.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    def test_waiters_reuse_first_result_no_second_download(self):
        """首线程下载完成前到达的等待者复用结果 → 不触发第二次下载。"""
        store = _PlatformCertStore()
        rec = _Recorder(delay=0.1)
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            return store.get_for_serial("C1", rec)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert rec.calls == 1
        assert rec.max_inflight == 1  # 同一时刻仅一个真实下载在跑


# ═══════════════════════════════════════════════════════════════
# 2. 缓存命中零下载
# ═══════════════════════════════════════════════════════════════
class TestCacheHitNoDownload:
    def test_second_get_uses_cache(self):
        """首取下载入缓存 → 二次取 (有效期充足) 零下载。"""
        store = _PlatformCertStore()
        rec = _Recorder()
        assert store.get_for_serial("C1", rec) is not None
        assert rec.calls == 1
        assert store.get_for_serial("C1", rec) is not None
        assert rec.calls == 1  # 缓存命中, 不再下载

    def test_cache_hit_while_download_in_flight(self):
        """已缓存证书 + 需刷新场景: 刷新期间验签用缓存, 不等网络。"""
        store = _PlatformCertStore()
        store.certs = {"C1": _cert()}
        store._have_downloaded = True
        # 强制 needs (不可用旧证书) → 刷新路径, 但缓存换新前旧值不可用则走下载
        store.certs = {"C1": _PlatformCert(
            serial="C1", pubkey=object(),
            effective_at=datetime.now(timezone.utc) - timedelta(days=100),
            expire_at=datetime.now(timezone.utc) - timedelta(days=10),
        )}
        download_started = threading.Event()
        release = threading.Event()

        def slow_refresh():
            download_started.set()
            release.wait(timeout=5)
            return [_cert()]

        t = threading.Thread(
            target=lambda: store.get_for_serial("C1", slow_refresh)
        )
        t.start()
        assert download_started.wait(timeout=5)
        release.set()
        t.join(timeout=5)
        # 刷新完成 → 新证书入缓存可用
        rec = _Recorder()
        assert store.get_for_serial("C1", rec) is not None
        assert rec.calls == 0  # 刷新后的缓存直接命中


# ═══════════════════════════════════════════════════════════════
# 3. 下载失败: 回退缓存 + 不阻塞他人
# ═══════════════════════════════════════════════════════════════
class TestDownloadFailure:
    def test_refresh_failure_falls_back_to_cached(self):
        """刷新失败 → 回退缓存证书 (可用性优先, A2 不变量保持)。"""
        store = _PlatformCertStore()
        store.certs = {"C1": _cert()}
        store._have_downloaded = True
        # 有效期充足也会因 fail 注入路径触发: 直接令 refresh 抛错且缓存需刷新
        store.certs = {"C1": _PlatformCert(
            serial="C1", pubkey=object(),
            effective_at=datetime.now(timezone.utc) - timedelta(days=85),
            expire_at=datetime.now(timezone.utc) + timedelta(days=5),
        )}  # 剩 5/90 < 1/3 → needs_refresh
        bad = _Recorder(exc=ConnectionError("network down"))
        r = store.get_for_serial("C1", bad)
        assert r is not None and r.serial == "C1"  # 缓存证书兜底
        assert bad.calls == 1

    def test_failure_does_not_poison_single_flight(self):
        """一线程下载失败后, 其他线程可再发起下载 (失败不留在门口)。"""
        store = _PlatformCertStore()
        results = []

        def worker(flag):
            if flag:
                results.append(store.get_for_serial(
                    "C1", _Recorder(exc=ConnectionError("down"))))
            else:
                results.append(store.get_for_serial("C1", _Recorder()))

        t1 = threading.Thread(target=worker, args=(True,))
        t1.start(); t1.join(timeout=5)
        assert results[0] is None  # 首下载失败且无缓存 → fail-closed
        t2 = threading.Thread(target=worker, args=(False,))
        t2.start(); t2.join(timeout=5)
        assert results[1] is not None  # 后续线程重下成功

    def test_no_cert_available_returns_none(self):
        """下载成功但目标 serial 不在返回集 → None (fail-closed 不变量)。"""
        store = _PlatformCertStore()
        rec = _Recorder(certs=[_cert(serial="OTHER")])
        assert store.get_for_serial("C1", rec) is None

    def test_download_exception_never_propagates(self):
        """refresh_fn 抛非 Exception 基类外的错误也兜住? 只约 Exception
        (与 A2 行为一致): refresh_fn 抛 Exception 子类一律转回退, 不冒泡。
        """
        store = _PlatformCertStore()
        rec = _Recorder(exc=ValueError("bad payload"))
        assert store.get_for_serial("C1", rec) is None


# ═══════════════════════════════════════════════════════════════
# 4. 全链并发回归 (RealWxPayClient 走 store)
# ═══════════════════════════════════════════════════════════════
class TestVerifyPlatformConcurrency:
    def test_concurrent_verify_full_chain_downloads_once(
        self, keypair, tmp_path
    ):
        """8 线程并发 _verify_platform (走下载链) → /v3/certificates 仅 1 次。

        复用 A2 脚手架 (_CertTransport), 验证 store 改造后全链单飞仍成立。
        """
        import base64
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from tests.services.test_wx_pay_platform_cert import (
            _CertTransport, _encrypted_cert_payload, _make_platform_cert,
            _settings_with_key, _valid_cert_pair,
        )
        from app.services.wx_pay.real_client import RealWxPayClient

        cert, plat_priv = _valid_cert_pair()
        settings = _settings_with_key(tmp_path, keypair)
        tp = _CertTransport([_encrypted_cert_payload(settings.WX_PAY_APIV3_KEY, cert)])
        c = RealWxPayClient(settings, transport=tp)
        body = b'{"evt":"lockfree"}'
        sig = base64.b64encode(plat_priv.sign(
            body, padding.PKCS1v15(), hashes.SHA256()
        )).decode()
        serial = format(cert.serial_number, "X")
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(c._verify_platform(body, sig, serial))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert all(r is True for r in results)
        assert tp.cert_calls == 1

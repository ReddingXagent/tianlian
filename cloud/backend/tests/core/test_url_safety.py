"""app/core/url_safety.py SSRF 防护单测 (安全关键)

validate_external_url / _is_blocked_ip / _resolve_ips 的纯函数单测 + 对抗矩阵:
  - 放行: 公网 https/http, 大写 scheme 归一化, 带端口, IP 字面量, 空白裁剪
  - 拒绝: 非 http(s) scheme, 空/非 str/缺主机, localhost 字面量
  - SSRF 对抗: 私网/环回/链路本地(metadata!)/保留/未指定, IPv6 ULA/link-local
  - IPv4-mapped IPv6 绕过防御 (::ffff:127.0.0.1 等)
  - DNS rebinding: 多 IP 解析中任一内网即拒
  - _resolve_ips: 去重 / gaierror / 空 sockaddr 过滤 / 无结果报错

DNS 全程 monkeypatch (零真实网络依赖, 确定性)。
"""
import ipaddress
import socket

import pytest

from app.core import url_safety
from app.core.url_safety import UnsafeURLError, validate_external_url


def _resolve_factory(ips):
    """造 getaddrinfo 替身: 对任意 host 返回给定 IP 列表 (AF_INET 5-tuple)。"""
    def fake(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
            for ip in ips
        ]
    return fake


# ────────────────────────────────────────────────────────────────────
# 放行: 公网 http/https
# ────────────────────────────────────────────────────────────────────
class TestAcceptPublic:
    def test_https_domain(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1"]))
        assert validate_external_url("https://example.com/path") == "https://example.com/path"

    def test_http_scheme_allowed(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["8.8.8.8"]))
        assert validate_external_url("http://example.com") == "http://example.com"

    def test_uppercase_scheme_normalized(self, monkeypatch):
        """'HTTPS://' 经 .lower() 归一化后放行 (公网解析)。"""
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1"]))
        assert validate_external_url("HTTPS://example.com") == "HTTPS://example.com"

    def test_with_port(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1"]))
        assert validate_external_url("https://example.com:8443/hook")

    def test_public_ip_literal(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["8.8.8.8"]))
        assert validate_external_url("https://8.8.8.8/x")

    def test_leading_whitespace_does_not_break_scheme_parse(self, monkeypatch):
        """前导空白经 url.strip() 后 scheme 正确识别为 https (放行), 不被误判为空 scheme。

        契约: 返回原始 URL (原样, 含首尾空白) — strip 仅用于解析阶段。
        """
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1"]))
        assert validate_external_url("  https://example.com  ") == "  https://example.com  "

    def test_all_public_multi_ip_accepted(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1", "8.8.8.8"]))
        validate_external_url("http://multi.com/x")


# ────────────────────────────────────────────────────────────────────
# 拒绝: 非 http(s) scheme
# ────────────────────────────────────────────────────────────────────
class TestRejectScheme:
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "ftp://example.com",
        "gopher://example.com",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "dict://example.com",
    ])
    def test_rejects_non_http_scheme(self, url):
        with pytest.raises(UnsafeURLError):
            validate_external_url(url)

    def test_empty_scheme_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_external_url("//example.com/path")  # 无 scheme


# ────────────────────────────────────────────────────────────────────
# 拒绝: 空 / 非 str / 缺主机名
# ────────────────────────────────────────────────────────────────────
class TestRejectEmptyAndMissingHost:
    def test_none_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_external_url(None)

    def test_empty_string_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_external_url("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_external_url("   ")

    def test_non_str_rejected(self):
        with pytest.raises(UnsafeURLError):
            validate_external_url(12345)

    def test_missing_hostname_rejected(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory(["1.1.1.1"]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("https:///path")  # 主机名空


# ────────────────────────────────────────────────────────────────────
# 拒绝: localhost 字面量 (不依赖 DNS/hosts)
# ────────────────────────────────────────────────────────────────────
class TestRejectLocalhost:
    @pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "LocalHost"])
    def test_localhost_literal_rejected(self, host):
        with pytest.raises(UnsafeURLError):
            validate_external_url(f"http://{host}/x")


# ────────────────────────────────────────────────────────────────────
# SSRF 对抗: 内网/保留 IPv4
# ────────────────────────────────────────────────────────────────────
class TestRejectSsrfIPv4:
    @pytest.mark.parametrize("ip", [
        "127.0.0.1",        # loopback
        "10.0.0.1",         # private 10/8
        "192.168.1.1",      # private 192.168/16
        "172.16.0.1",       # private 172.16/12
        "169.254.169.254",  # link-local — 云元数据服务 (IMDS)!
        "0.0.0.0",          # unspecified
    ])
    def test_rejects_private_ipv4(self, monkeypatch, ip):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory([ip]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("http://evil.com/x")


# ────────────────────────────────────────────────────────────────────
# SSRF 对抗: IPv6 内网段
# ────────────────────────────────────────────────────────────────────
class TestRejectSsrfIPv6:
    @pytest.mark.parametrize("ip", [
        "::1",        # IPv6 loopback
        "fc00::1",    # IPv6 ULA private fc00::/7
        "fd00::1",    # IPv6 ULA private
        "fe80::1",    # IPv6 link-local fe80::/10
    ])
    def test_rejects_private_ipv6(self, monkeypatch, ip):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory([ip]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("http://evil.com/x")


# ────────────────────────────────────────────────────────────────────
# SSRF 对抗: IPv4-mapped IPv6 绕过防御 (核心安全逻辑)
#   ::ffff:127.0.0.1 等 — IPv6 视角 is_loopback=False, 但 ipv4_mapped 命中
# ────────────────────────────────────────────────────────────────────
class TestRejectIpv4MappedBypass:
    @pytest.mark.parametrize("ip", [
        "::ffff:127.0.0.1",        # mapped loopback
        "::ffff:169.254.169.254",  # mapped cloud metadata
        "::ffff:10.0.0.1",         # mapped private
        "::ffff:192.168.1.1",      # mapped private
    ])
    def test_rejects_mapped_ipv6(self, monkeypatch, ip):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", _resolve_factory([ip]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("http://evil.com/x")


# ────────────────────────────────────────────────────────────────────
# DNS rebinding: 多 IP 解析中任一内网即拒
# ────────────────────────────────────────────────────────────────────
class TestDnsRebindingDefense:
    def test_one_private_among_public_rejected(self, monkeypatch):
        """解析出 [公网, 内网], 任一内网即拒 (防 rebinding 到内网)。"""
        monkeypatch.setattr(url_safety.socket, "getaddrinfo",
                            _resolve_factory(["1.1.1.1", "127.0.0.1"]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("http://rebind.com/x")

    def test_private_first_then_public_still_rejected(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo",
                            _resolve_factory(["10.0.0.1", "1.1.1.1"]))
        with pytest.raises(UnsafeURLError):
            validate_external_url("http://rebind.com/x")


# ────────────────────────────────────────────────────────────────────
# _is_blocked_ip 直接单测 (所有判定类别 + mapped)
# ────────────────────────────────────────────────────────────────────
class TestIsBlockedIp:
    @pytest.mark.parametrize("ip", [
        "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1",
        "169.254.1.1", "0.0.0.0",
    ])
    def test_blocked_ipv4(self, ip):
        assert url_safety._is_blocked_ip(ipaddress.ip_address(ip)) is True

    @pytest.mark.parametrize("ip", ["::1", "fc00::1", "fe80::1"])
    def test_blocked_ipv6(self, ip):
        assert url_safety._is_blocked_ip(ipaddress.ip_address(ip)) is True

    @pytest.mark.parametrize("ip", ["1.1.1.1", "8.8.8.8", "9.9.9.9"])
    def test_public_not_blocked(self, ip):
        assert url_safety._is_blocked_ip(ipaddress.ip_address(ip)) is False

    def test_ipv4_mapped_detected_via_attribute(self):
        """IPv4-mapped IPv6 经 ipv4_mapped 属性命中 (绕过防御的核心)。"""
        assert url_safety._is_blocked_ip(
            ipaddress.ip_address("::ffff:127.0.0.1")) is True
        assert url_safety._is_blocked_ip(
            ipaddress.ip_address("::ffff:169.254.169.254")) is True


# ────────────────────────────────────────────────────────────────────
# _resolve_ips: 去重 / gaierror / 空 sockaddr / 无结果
# ────────────────────────────────────────────────────────────────────
class TestResolveIps:
    def test_dedupes_repeated_ips(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo",
                            _resolve_factory(["1.1.1.1", "1.1.1.1", "8.8.8.8"]))
        assert url_safety._resolve_ips("x") == ["1.1.1.1", "8.8.8.8"]

    def test_gaierror_raises_unsafe(self, monkeypatch):
        def raise_gai(host, *a, **kw):
            raise socket.gaierror("dns fail")
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", raise_gai)
        with pytest.raises(UnsafeURLError):
            url_safety._resolve_ips("x")

    def test_socket_error_raises_unsafe(self, monkeypatch):
        def raise_err(host, *a, **kw):
            raise socket.error("oops")
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", raise_err)
        with pytest.raises(UnsafeURLError):
            url_safety._resolve_ips("x")

    def test_empty_result_raises(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo", lambda *a, **kw: [])
        with pytest.raises(UnsafeURLError):
            url_safety._resolve_ips("x")

    def test_none_sockaddr_filtered(self, monkeypatch):
        """部分 info 缺 sockaddr → 过滤, 有效部分仍提取。"""
        monkeypatch.setattr(
            url_safety.socket, "getaddrinfo",
            lambda *a, **kw: [
                (socket.AF_INET, 1, 1, "", None),                   # 无 sockaddr
                (socket.AF_INET, 1, 1, "", ("9.9.9.9", 0)),         # 有效
            ],
        )
        assert url_safety._resolve_ips("x") == ["9.9.9.9"]

    def test_returns_all_distinct_ips(self, monkeypatch):
        monkeypatch.setattr(url_safety.socket, "getaddrinfo",
                            _resolve_factory(["1.1.1.1", "8.8.8.8", "9.9.9.9"]))
        assert url_safety._resolve_ips("x") == ["1.1.1.1", "8.8.8.8", "9.9.9.9"]

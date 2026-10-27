# -*- coding: utf-8 -*-
"""
URL 安全校验 — 防 SSRF (Server-Side Request Forgery)

供出站回调(Webhook 注册 / 投递)等场景复用:强制 http/https scheme,
解析主机名全部 IP,拒绝私网 / 环回 / 链路本地 / 保留 / 组播 / 未指定地址,
以及 localhost 字面量。

覆盖的常见内网段:
  - IPv4: 10/8、172.16/12、192.168/16 (is_private)
          127/8 (is_loopback)、169.254/16 (is_link_local)
  - IPv6: ::1 (is_loopback)、fc00::/7 (is_private)、fe80::/10 (is_link_local)
"""
import ipaddress
import socket
from typing import List
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")
# 显式拒绝的主机名字面量(不依赖 DNS/hosts 解析,避免环境差异)
_BLOCKED_HOST_LITERALS = {"localhost"}


class UnsafeURLError(ValueError):
    """URL 不安全(非法 scheme / 指向内网 / 解析失败 等)。"""


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """判断单个 IP 是否落入禁止访问的范围。"""
    blocked = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
    if blocked:
        return True
    # 防御 IPv4-mapped IPv6 绕过 (如 ::ffff:169.254.169.254 / ::ffff:127.0.0.1)
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return (
            mapped.is_private
            or mapped.is_loopback
            or mapped.is_link_local
            or mapped.is_reserved
            or mapped.is_multicast
            or mapped.is_unspecified
        )
    return False


def _resolve_ips(hostname: str) -> List[str]:
    """解析主机名为 IP 字符串列表;失败抛 UnsafeURLError。"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, socket.error, UnicodeError) as exc:
        raise UnsafeURLError(f"主机名解析失败: {exc}")
    ips: List[str] = []
    for info in infos:
        sockaddr = info[4] if len(info) >= 5 else None
        if sockaddr and len(sockaddr) >= 1:
            ip_str = sockaddr[0]
            if ip_str and ip_str not in ips:
                ips.append(ip_str)
    if not ips:
        raise UnsafeURLError("主机名未解析出任何 IP")
    return ips


def validate_external_url(url: str) -> str:
    """校验 URL 指向公网 http/https 端点。

    - 仅允许 http/https scheme(拒绝 file://、ftp://、gopher:// 等)
    - 拒绝空主机名与 localhost 字面量
    - 解析主机名全部 IP,任一落入内网/保留范围即拒绝
    - DNS 解析失败也拒绝(默认拒绝,不留隐式放行)

    Args:
        url: 待校验的 URL 字符串。

    Returns:
        原始 URL(校验通过)。

    Raises:
        UnsafeURLError: URL 不安全。
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("URL 为空")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"仅允许 http/https scheme,得到 '{scheme or '空'}'")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL 缺少主机名")
    if hostname.lower() in _BLOCKED_HOST_LITERALS:
        raise UnsafeURLError("禁止使用 localhost 主机名")

    for ip_str in _resolve_ips(hostname):
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise UnsafeURLError(f"非法 IP 地址: {ip_str}")
        if _is_blocked_ip(ip):
            raise UnsafeURLError(f"禁止访问内网/保留地址: {ip}")

    return url

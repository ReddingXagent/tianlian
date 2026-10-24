"""
字段级加密 (Fernet) — 敏感配置加密存储。

主要用途: 第三方开票平台 RSA 私钥 (InvoicePlatformConfig.private_key_enc) 等敏感字段,
存储时加密、读取时解密, 避免明文落库。

密钥来源 (优先级):
1. settings.FIELD_ENCRYPTION_KEY — 须为合法 Fernet key (urlsafe base64 of 32 bytes)。
2. 缺省: 从 settings.SECRET_KEY 经 HKDF-SHA256 派生 32 字节再 urlsafe-base64 编码,
   开发环境零配置可用。

约定:
- None / 空串透传 (字段可空, 不加密空值)。
- 同一明文每次加密密文不同 (Fernet 内置随机 IV)。
- 解密失败 (密钥不匹配 / 数据损坏) 抛 CryptoError, 由调用方处理。
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


class CryptoError(Exception):
    """加解密失败 (密钥不匹配 / 密文损坏 / 配置非法)。"""


# HKDF info 域: 把派生 key 与其他用途隔离, 防止同源 SECRET_KEY 派生出相同密钥。
_HKDF_INFO = b"tianlian-v3-field-encryption"
_DERIVED_LENGTH = 32  # Fernet 要求 32 字节 (256-bit) key


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """构造 (并缓存) Fernet 实例。lru_cache 使同进程内加解密共用同一密钥。

    测试如需切换密钥, monkeypatch settings 后调用 _get_fernet.cache_clear()。
    """
    explicit = settings.FIELD_ENCRYPTION_KEY
    if explicit:
        try:
            return Fernet(
                explicit.encode("utf-8") if isinstance(explicit, str) else explicit
            )
        except Exception as exc:  # 含: ValueError / TypeError
            raise CryptoError(f"FIELD_ENCRYPTION_KEY 非合法 Fernet key: {exc}") from exc

    # 缺省派生: SECRET_KEY -> HKDF-SHA256 -> 32B -> urlsafe base64
    base_secret = (settings.SECRET_KEY or "tianlian-dev-fallback").encode("utf-8")
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=_DERIVED_LENGTH,
        salt=None,
        info=_HKDF_INFO,
    ).derive(base_secret)
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """加密敏感字段。None / "" 原样返回。返回值为 Fernet token 字符串。"""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(token: Optional[str]) -> Optional[str]:
    """解密敏感字段。None / "" 原样返回。密文非法抛 CryptoError。"""
    if not token:
        return token
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("密文解密失败 (密钥不匹配或数据损坏)") from exc

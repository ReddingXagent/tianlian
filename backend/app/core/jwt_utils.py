"""
JWT 密钥与编解码工具 — 双 Key 灰度迁移 (卡 a89269c9)

RFC 7518 §3.2 要求 HMAC key ≥32 字节。本模块集中管理 SECRET_KEY 的
新旧两份密钥, 支持无感轮换:

  - 签发 (encode_token): 一律用「新 key」(SECRET_KEY_NEW, 未配置则 SECRET_KEY)。
  - 验证 (decode_token): 先试新 key, 失败再试旧 key (SECRET_KEY_OLD,
    未配置则 SECRET_KEY)。轮换窗口内存量 token 不失效。
  - SECRET_KEY_NEW 未配置时, 新/旧均退化为 SECRET_KEY, 候选 key 去重后
    仅剩一个 —— 行为与改造前单 key 完全一致, 零回归。

集中化的目的: JWT 编解码原本分散在 app/api/v1/auth.py、
app/middleware/permission.py、app/api/gateway/api_gateway.py 三处共 8 个
调用点。若任一 decode 路径漏掉「试新 key」, 轮换后该路径签发的新 token
会被拒 (例: permission.py 的 require_permission/require_role 守卫全部端点)。
统一入口杜绝漏迁移。

异常语义保持与改造前一致: 过期 → ExpiredSignatureError; 其余校验失败
(签名不符 / 格式错误) → DecodeError。调用方按这两个异常分支处理, 无需改动。
"""

from __future__ import annotations

import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError

from app.core.config import settings


def get_active_secret_key() -> str:
    """签发 token 用的密钥: 优先 SECRET_KEY_NEW, 未配置则退回 SECRET_KEY。"""
    return settings.SECRET_KEY_NEW or settings.SECRET_KEY


def _candidate_keys() -> list[str]:
    """验证 token 时依次尝试的密钥列表 (新 key 在前为热路径, 旧 key 在后兜底)。

    去重保序: SECRET_KEY_NEW=None 时新/旧均解析为 SECRET_KEY, 去重后仅一个,
    退化为单 key 验证, 与改造前行为一致。
    """
    new_key = settings.SECRET_KEY_NEW or settings.SECRET_KEY
    old_key = settings.SECRET_KEY_OLD or settings.SECRET_KEY
    keys = [new_key]
    if old_key != new_key:
        keys.append(old_key)
    return keys


def encode_token(payload: dict) -> str:
    """用新 key (active) 签发 JWT。"""
    return jwt.encode(payload, get_active_secret_key(), algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """验证 JWT, 依次尝试新 / 旧 key。

    返回 payload; 失败时抛出与改造前一致的异常:
      - ExpiredSignatureError: 任一候选 key 验出「签名正确但已过期」
        (过期优先于签名不符上报, 语义最贴近用户感知)。
      - DecodeError: 无任何候选 key 能验证通过 (含签名不符 / 格式错误)。
    """
    expired_error: ExpiredSignatureError | None = None
    decode_error: DecodeError | None = None
    for key in _candidate_keys():
        try:
            return jwt.decode(token, key, algorithms=[settings.ALGORITHM])
        except ExpiredSignatureError as e:
            # 签名正确但过期: 记下, 后续 key 可能签名不符(DecodeError),
            # 但过期语义应优先, 故仅在首次命中时保存不被覆盖。
            if expired_error is None:
                expired_error = e
        except DecodeError as e:
            # 含 InvalidSignatureError (PyJWT 中为其子类): 签名不符 → 换下一个 key 重试。
            if decode_error is None:
                decode_error = e
    if expired_error is not None:
        raise expired_error
    raise decode_error or DecodeError("token 解码失败")


def decode_token_for_audience(token: str, audience: str) -> dict:
    """按指定 audience 解码 JWT.

    PyJWT 2.10 起未显式传 audience 且 payload 带 aud 时会拒绝解码;
    C端 token 与运营 token 依赖 aud 隔离, 必须在解码层声明期望值。
    """
    expired_error: ExpiredSignatureError | None = None
    decode_error: DecodeError | None = None
    for key in _candidate_keys():
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[settings.ALGORITHM],
                audience=audience,
            )
        except ExpiredSignatureError as e:
            if expired_error is None:
                expired_error = e
        except DecodeError as e:
            if decode_error is None:
                decode_error = e
    if expired_error is not None:
        raise expired_error
    raise decode_error or DecodeError("token 解码失败")

"""
输入验证与净化模块

安全功能:
  - HTML/XSS 字符转义
  - SQL 注入防御 (参数化查询辅助)
  - 路径遍历防御
  - 命令注入防御
  - 敏感数据脱敏
"""
import re
import html
import logging
import unicodedata
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── XSS 防御 ───

# 危险字符模式 (用于检测而非清理)
DANGEROUS_HTML_PATTERNS = re.compile(
    r'<\s*(script|iframe|object|embed|form|link|meta|base|svg|math|img|video|audio|source)'
    r'|on\w+\s*='
    r'|javascript\s*:'
    r'|vbscript\s*:'
    r'|data\s*:'
    r'|expression\s*\('
    r'|url\s*\(\s*["\']?\s*javascript',
    re.IGNORECASE,
)


def sanitize_html(text: str) -> str:
    """
    HTML 转义 — 防止 XSS 注入
    将 < > & " ' 转义为安全实体
    """
    if not isinstance(text, str):
        return text
    return html.escape(text, quote=True)


def validate_no_xss(text: str) -> bool:
    """
    检查文本是否包含潜在 XSS 攻击模式
    返回 True 表示安全，False 表示危险
    """
    if not isinstance(text, str):
        return True
    return not bool(DANGEROUS_HTML_PATTERNS.search(text))


def strip_html(text: str) -> str:
    """移除所有 HTML 标签，保留纯文本"""
    if not isinstance(text, str):
        return text
    return re.sub(r'<[^>]+>', '', text)


# ─── 路径安全 ───

def sanitize_path(user_path: str, base_dir: Optional[Path] = None) -> Path:
    """
    安全路径解析 — 防止路径遍历攻击

    Args:
        user_path: 用户提供的路径 (可能包含 ../ 等)
        base_dir: 允许的根目录，解析后必须在此目录内

    Returns:
        安全的绝对路径

    Raises:
        ValueError: 路径超出允许范围
    """
    if base_dir is not None:
        base_resolved = base_dir.resolve()
        # 先将用户路径拼接到 base_dir，再解析
        safe = (base_resolved / user_path).resolve()
        # 检查安全路径是否在允许目录内
        if not str(safe).startswith(str(base_resolved)):
            raise ValueError(
                f"路径遍历攻击: {user_path} 解析后超出允许目录 {base_dir}"
            )
        return safe
    else:
        return Path(user_path).resolve()


# ─── 命令注入防御 ───

# 危险 shell 字符
SHELL_METACHARACTERS = re.compile(r'[;&|`$(){}!<>\\]')


def validate_command_arg(arg: str) -> bool:
    """
    检查命令行参数是否包含危险 shell 元字符
    返回 True 表示安全
    """
    if not isinstance(arg, str):
        return False
    return not bool(SHELL_METACHARACTERS.search(arg))


# ─── 敏感数据脱敏 ───

def mask_email(email: str) -> str:
    """脱敏邮箱地址"""
    if not isinstance(email, str) or "@" not in email:
        return email
    parts = email.split("@")
    name = parts[0]
    domain = parts[1]
    if len(name) <= 2:
        masked = f"{name[0]}*"
    else:
        masked = f"{name[0]}***{name[-1]}"
    return f"{masked}@{domain}"


def mask_phone(phone: str) -> str:
    """脱敏手机号 (保留前3后4)"""
    if not isinstance(phone, str) or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def mask_token(token: str, visible: int = 4) -> str:
    """脱敏 token/密钥 (仅显示前N位)"""
    if not isinstance(token, str) or len(token) <= visible:
        return "****"
    return f"{token[:visible]}{'*' * (len(token) - visible)}"


def mask_sensitive_dict(data: dict, sensitive_keys: Optional[set] = None) -> dict:
    """
    字典中的敏感字段自动脱敏

    Args:
        data: 原始数据字典
        sensitive_keys: 需要脱敏的键名 (默认包含常见敏感字段)
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "password", "passwd", "secret", "token", "api_key",
            "api_secret", "access_token", "refresh_token",
            "phone", "mobile", "email", "id_card", "ssn",
            "authorization", "cookie", "session_id",
        }

    result = {}
    for key, value in data.items():
        lower_key = key.lower()
        if lower_key in sensitive_keys:
            if isinstance(value, str):
                if "phone" in lower_key or "mobile" in lower_key:
                    result[key] = mask_phone(value)
                elif "email" in lower_key:
                    result[key] = mask_email(value)
                else:
                    result[key] = mask_token(value)
            else:
                result[key] = "***"
        elif isinstance(value, dict):
            result[key] = mask_sensitive_dict(value, sensitive_keys)
        else:
            result[key] = value
    return result


# ─── 日志脱敏 ───

# 日志中需要脱敏的模式
LOG_SENSITIVE_PATTERNS = [
    # password=xxx 或 password: "xxx"
    (re.compile(r'(password|passwd|pwd)["\']?\s*[=:]\s*["\']?([^"\'\s,}]+)["\']?', re.IGNORECASE), r'\1="***"'),
    # token=xxx
    (re.compile(r'(token|secret|api_key|api_secret|authorization)["\']?\s*[=:]\s*["\']?([^"\'\s,}]+)["\']?', re.IGNORECASE), r'\1="***"'),
    # 手机号 (中国)
    (re.compile(r'1[3-9]\d{9}'), lambda m: mask_phone(m.group())),
]


def sanitize_for_log(message: str) -> str:
    """脱敏日志消息中的敏感信息"""
    if not isinstance(message, str):
        return message
    for pattern, replacement in LOG_SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


# ─── 字符串输入净化 ───

# 最大字符串长度 (防止 ReDoS)
MAX_STRING_LENGTH = 10000


def sanitize_string(value: Any, max_length: int = MAX_STRING_LENGTH) -> Any:
    """
    通用字符串净化

    - 去除首尾空白
    - 限制长度
    - 移除控制字符 (除 \n \t \r)
    - Unicode 规范化
    """
    if not isinstance(value, str):
        return value

    # 长度限制
    if len(value) > max_length:
        value = value[:max_length]

    # 移除控制字符
    value = ''.join(
        c for c in value
        if c in ('\n', '\t', '\r') or unicodedata.category(c)[0] != 'C'
    )

    # Unicode NFC 规范化
    value = unicodedata.normalize('NFC', value)

    return value.strip()

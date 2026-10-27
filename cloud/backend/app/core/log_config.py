"""
统一日志配置 - 结构化 JSON 日志 + 控制台彩色输出

功能:
  - JSON 格式化输出 (可直接被 ELK/Loki 消费)
  - request_id / correlation_id 链路追踪 (contextvars)
  - 敏感信息自动脱敏 (复用 app.utils.sanitize)
  - 日志分级: DEBUG/INFO/WARNING/ERROR/CRITICAL
  - 日志轮转: 按天+按大小, 保留 30 天
  - 慢日志检测: 超过 100ms 自动标记 WARNING
"""
import os
import sys
import json
import uuid
import logging
import re
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional
from contextvars import ContextVar

# ─── 链路追踪 (contextvars) ───
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
_user_id_ctx: ContextVar[str] = ContextVar("user_id", default="-")
_client_ip_ctx: ContextVar[str] = ContextVar("client_ip", default="-")


def set_request_id(request_id: str) -> None:
    """设置当前请求的 request_id"""
    _request_id_ctx.set(request_id)


def set_user_id(user_id: str) -> None:
    """设置当前请求的 user_id"""
    _user_id_ctx.set(str(user_id))


def set_client_ip(client_ip: str) -> None:
    """设置当前请求的 client_ip"""
    _client_ip_ctx.set(client_ip)


def get_request_id() -> str:
    """获取当前请求的 request_id"""
    return _request_id_ctx.get()


def get_user_id() -> str:
    """获取当前请求的 user_id"""
    return _user_id_ctx.get()


# ─── 日志目录 ───
LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── 日志级别 ───
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# ─── 敏感信息脱敏 (复用 sanitize.py) ───
_SENSITIVE_PATTERNS = [
    # password=xxx / password: "xxx"
    (re.compile(r'(password|passwd|pwd|secret)["\']?\s*[=:]\s*["\']?([^"\'\s,}]+)["\']?', re.IGNORECASE), r'\1="****"'),
    # token / api_key / api_secret
    (re.compile(r'(token|api_key|api_secret|authorization|access_token|refresh_token)["\']?\s*[=:]\s*["\']?([^"\'\s,}]+)["\']?', re.IGNORECASE), r'\1="****"'),
    # 手机号 (中国 1xx-xxxx-xxxx)
    (re.compile(r'1[3-9]\d{9}'), lambda m: m.group()[:3] + '****' + m.group()[-4:]),
    # 身份证号 (18位)
    (re.compile(r'\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'), lambda m: m.group()[:4] + '**********' + m.group()[-4:]),
    # 邮箱
    (re.compile(r'([\w.+-]+)@([\w-]+\.[\w.-]+)'), lambda m: m.group(1)[0] + '****' + m.group(1)[-1] + '@' + m.group(2) if len(m.group(1)) > 2 else '****@' + m.group(2)),
]


def _sanitize_log_message(message: str) -> str:
    """脱敏日志消息中的敏感信息"""
    if not isinstance(message, str):
        return message
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


# ─── 格式化器 ───

class RequestIDFilter(logging.Filter):
    """自动注入 request_id / user_id / client_ip 到每一条日志"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or _request_id_ctx.get()
        record.user_id = getattr(record, "user_id", None) or _user_id_ctx.get()
        record.client_ip = getattr(record, "client_ip", None) or _client_ip_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """JSON 行格式化 — 生产环境，可被 ELK/Loki 直接消费"""

    def format(self, record: logging.LogRecord) -> str:
        # 先对消息脱敏
        message = _sanitize_log_message(record.getMessage())

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": message,
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "client_ip": getattr(record, "client_ip", "-"),
        }

        # 附加异常信息
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = _sanitize_log_message(self.formatException(record.exc_info))

        # 附加 extra 字段
        for key in ("path", "method", "status_code", "duration_ms", "query_time_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, ensure_ascii=False)


class ColorConsoleFormatter(logging.Formatter):
    """控制台彩色输出 — 开发环境"""

    COLORS = {
        "DEBUG": "\033[36m",      # 青色
        "INFO": "\033[32m",       # 绿色
        "WARNING": "\033[33m",    # 黄色
        "ERROR": "\033[31m",      # 红色
        "CRITICAL": "\033[35m",   # 紫色
        "RESET": "\033[0m",
        "DIM": "\033[2m",         # 灰色
    }

    def format(self, record: logging.LogRecord) -> str:
        # 对消息脱敏 (非 JSON 模式下)
        message = _sanitize_log_message(record.getMessage())

        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        dim = self.COLORS["DIM"]

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level = f"{color}[{record.levelname:^7}]{reset}"
        module = f"{dim}{record.name}{reset}"
        req_id = getattr(record, "request_id", "-")
        dur = getattr(record, "duration_ms", None)
        dur_str = f" {dim}{dur}ms{reset}" if dur else ""

        parts = [f"{dim}{ts}{reset}", level, module]
        if req_id and req_id != "-":
            parts.append(f"{dim}[{req_id[:8]}]{reset}")
        parts.append(f"{message}{dur_str}")

        return " ".join(parts)


# ─── 日志帮助函数 ───

def get_log_level() -> int:
    return LOG_LEVEL_MAP.get(LOG_LEVEL, logging.INFO)


def setup_logging(
    app_name: str = "tianlian-v3",
    log_dir: Optional[Path] = None,
) -> logging.Logger:
    """
    初始化全局日志配置

    - 开发环境 (DEBUG=True) → 控制台彩色输出
    - 生产环境 → JSON 格式文件输出 + 控制台
    - 日志轮转: 按天轮转 + 按大小轮转 (50MB)，保留 30 天
    """
    target_dir = log_dir or LOG_DIR
    level = get_log_level()
    is_production = os.getenv("DEBUG", "true").lower() in ("false", "0", "no")

    # 根 logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()  # 避免重复添加

    request_filter = RequestIDFilter()

    # ── 文件 handler: 按天轮转 + 按大小轮转 ──
    app_log = target_dir / f"{app_name}.log"
    json_formatter = JsonFormatter()

    # 通用日志 — 按天轮转，保留 30 天
    daily_handler = TimedRotatingFileHandler(
        str(app_log),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    daily_handler.setLevel(level)
    daily_handler.setFormatter(json_formatter)
    daily_handler.addFilter(request_filter)
    root.addHandler(daily_handler)

    # 错误日志独立文件 (按天轮转)
    error_log = target_dir / f"{app_name}-error.log"
    error_handler = TimedRotatingFileHandler(
        str(error_log),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(request_filter)
    root.addHandler(error_handler)

    # ── 控制台 handler ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        ColorConsoleFormatter() if not is_production else json_formatter
    )
    console.addFilter(request_filter)
    root.addHandler(console)

    # 抑制 noisy 第三方 logger
    for noisy in ("uvicorn.access", "passlib", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(app_name)
    # level/production/dir 并入 message 文本: 这三键不在 JsonFormatter 的 extra 白名单,
    # 走 extra 会在生产 JSON 日志中被静默丢弃; 且 "level" 键与 JSON 顶层 level 字段
    # (record.levelname) 同名会错误覆盖。并入 message 两种 formatter 下均可见。
    logger.info(
        "日志系统初始化完成 level=%s production=%s dir=%s",
        LOG_LEVEL, is_production, str(target_dir),
    )
    return logger


def get_request_logger(name: str) -> logging.LoggerAdapter:
    """获取请求作用域 logger (返回 LoggerAdapter, 但 extra 为空, 不在此层绑定字段)。

    request_id / user_id / client_ip 的注入由 RequestIDFilter 经 contextvars 在
    handler 层完成 (见 setup_logging 中各 handler 的 addFilter(request_filter));
    此处 LoggerAdapter 仅作历史兼容包装, 传入空 dict, 不主动写入任何链路字段。
    """
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, {})


def generate_request_id() -> str:
    """生成唯一请求 ID (16 位 hex)"""
    return uuid.uuid4().hex[:16]


# ─── 慢查询日志帮助函数 ───

def log_slow_query(query_name: str, duration_ms: float, query_info: str = ""):
    """
    记录慢查询日志 (>100ms 标记 WARNING, >1s 标记 ERROR)
    
    用法:
        start = time.time()
        # ... 执行查询 ...
        duration_ms = (time.time() - start) * 1000
        log_slow_query("find_devices", duration_ms, "device_ids=1,2,3")
    """
    logger = logging.getLogger("app.db.slow_query")
    extra = {"query_time_ms": round(duration_ms, 2)}
    
    if duration_ms >= 1000:
        logger.error(
            "超慢查询 [%s] %.1fms: %s",
            query_name, duration_ms, query_info,
            extra=extra,
        )
    elif duration_ms >= 100:
        logger.warning(
            "慢查询 [%s] %.1fms: %s",
            query_name, duration_ms, query_info,
            extra=extra,
        )
    else:
        logger.info(
            "查询 [%s] %.1fms: %s",
            query_name, duration_ms, query_info,
            extra=extra,
        )
"""
天链 V3 边缘网关 - 日志配置
"""
import logging
import sys
from pathlib import Path
from app.core.config import config


def setup_logging() -> logging.Logger:
    """配置日志系统"""
    log_config = config.logging

    # 确保日志目录存在
    log_file = Path(log_config.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 根日志器
    logger = logging.getLogger("edge_gateway")
    logger.setLevel(getattr(logging, log_config.level.upper(), logging.INFO))

    # 格式
    formatter = logging.Formatter(log_config.format)

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    file_handler = logging.FileHandler(log_config.file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()

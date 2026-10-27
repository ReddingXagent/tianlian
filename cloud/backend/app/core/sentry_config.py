"""
Sentry 错误监控配置

环境变量:
  SENTRY_DSN         - Sentry DSN 地址
  SENTRY_ENABLED     - 是否启用 (true/false, 默认 false)
  SENTRY_ENVIRONMENT - 环境标识 (development/production, 默认 development)
  SENTRY_TRACES_SAMPLE_RATE - 性能采样率 (0.0-1.0, 默认 1.0)
"""
import os
import logging

logger = logging.getLogger(__name__)


def init_sentry(
    dsn: str = "",
    environment: str = "development",
    traces_sample_rate: float = 1.0,
):
    """
    初始化 Sentry SDK

    Args:
        dsn: Sentry DSN（优先从 SENTRY_DSN 环境变量读取）
        environment: 环境标识
        traces_sample_rate: 性能追踪采样率
    """
    enabled = os.getenv("SENTRY_ENABLED", "false").lower() == "true"
    dsn = dsn or os.getenv("SENTRY_DSN", "")
    environment = environment or os.getenv("SENTRY_ENVIRONMENT", "development")

    if not enabled:
        logger.info("Sentry 已禁用 (SENTRY_ENABLED=false)")
        return

    if not dsn:
        logger.warning("Sentry DSN 未配置，跳过初始化")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            integrations=[
                FastApiIntegration(
                    transaction_style="endpoint",
                ),
            ],
            send_default_pii=False,  # 不发送用户个人信息
        )
        logger.info(
            "Sentry 已初始化: env=%s, traces_sample_rate=%s",
            environment,
            traces_sample_rate,
        )
    except Exception as e:
        logger.error("Sentry 初始化失败: %s", e)
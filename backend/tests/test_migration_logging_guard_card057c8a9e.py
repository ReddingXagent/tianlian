"""迁移链 logging 无痕守护 (卡 057c8a9e)

根因: alembic/env.py 的 fileConfig(alembic.ini) 默认 disable_existing_loggers=True
→ 测试进程内跑 command.upgrade 后, 收集期已创建的全部 app.* logger 被设
disabled=True (alembic.ini 只声明 root/sqlalchemy/alembic 三个 logger),
且 [logger_root] 被重配 (handlers=console, level=WARNING)。这些状态跨测试
残留 → 后续所有 caplog 断言族消息缺失红 (set_level/at_level 无法穿透
logger.disabled), 全量串行 34 红受害者全部在收集序 migration_chain 之后
(test_n* 起, vpp/test_auto_scheduler 等尾部文件亦中招)。

守护链分两层:
1. env.py 修复守护 — 真实 fresh 库 upgrade head 后立即断言 (恢复动作之前)
   app.* logger 未被禁用; 丢失 disable_existing_loggers=False 即 RED。
2. 跨测试受害链守护 — 本文件名 (test_migration_...) 收集序在
   test_migration_chain_fresh_db 之后, 文件尾的受害断言天然承接其残留:
   任何跑 alembic 链的测试忘带 preserve_global_logging 包裹, 本文件即 RED。
"""
import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.timing_log import emit_write_timing
from tests._test_helpers import preserve_global_logging

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class TestUpgradeHeadLeavesGlobalLoggingIntact:
    def test_fresh_upgrade_does_not_disable_app_loggers(self, tmp_path, monkeypatch):
        """upgrade 后 (恢复前) app.* logger 不得被 fileConfig 禁用。"""
        db_file = tmp_path / "guard_fresh.db"
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_file}")
        cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
        with preserve_global_logging():
            command.upgrade(cfg, "head")
            # env.py 修复点 (disable_existing_loggers=False) 的即时效果:
            # 断言在 with 内 = 恢复动作之前, 捕获 fileConfig 的真实残留
            assert not logging.getLogger("app.core.timing_log").disabled, (
                "app.core.timing_log 被 fileConfig 禁用 "
                "(env.py 丢失 disable_existing_loggers=False?)"
            )
            assert not logging.getLogger("app.services.channel_providers").disabled, (
                "app.services.channel_providers 被 fileConfig 禁用 "
                "(env.py 丢失 disable_existing_loggers=False?)"
            )
        # 恢复后 root 无痕 (fileConfig 曾把 root 换成 console+WARNING,
        # 主 log FileHandler 被摘 → 污染态全量批 08:46 起主 log 停写即此副作用)
        assert not logging.getLogger("app.core.timing_log").disabled

    def test_root_level_and_handlers_restored_after_upgrade(self, tmp_path, monkeypatch):
        """preserve_global_logging 包裹的 upgrade 结束后 root 无痕。"""
        root = logging.getLogger()
        saved_level = root.level
        saved_handlers = root.handlers[:]
        db_file = tmp_path / "guard_fresh2.db"
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_file}")
        cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
        with preserve_global_logging():
            command.upgrade(cfg, "head")
            # with 内: fileConfig 副作用可见 (root 已被换成 ini 的 console)
            assert root.handlers != saved_handlers or root.level != saved_level
        assert root.level == saved_level
        assert root.handlers == saved_handlers


class TestVictimChainAfterPriorUpgrades:
    """跨测试受害链: 本类不跑 upgrade, 只承接文件内先前 upgrade 的残留。

    文件内 TestUpgradeHeadLeavesGlobalLoggingIntact 已跑过真实 upgrade 链;
    若其 preserve 失效 (或收集序更早的 test_migration_chain_fresh_db 忘带
    包裹), 本类断言立即以 34 红同款「消息缺失」形态失败。
    """

    def test_timing_log_capture_not_killed_by_prior_upgrade(self, caplog):
        caplog.set_level(logging.INFO, logger="app.core.timing_log")
        emit_write_timing(
            "telemetry/batch-report", 3,
            auth_ms=1.0, parse_ms=2.0, insert_ms=10.0, commit_ms=5.0,
            total_ms=18.0,
        )
        msgs = " ".join(rec.getMessage() for rec in caplog.records)
        assert "write_request_timing" in msgs, (
            f"消息缺失 (logger 被禁用 / root handlers 被换): {caplog.records!r}"
        )

    def test_channel_providers_capture_not_killed_by_prior_upgrade(self, caplog):
        from app.services import channel_providers as cp

        caplog.set_level(logging.INFO, logger="app.services.channel_providers")
        cp._CloudProviderSmsProvider().send("13812345678", "内容", {})
        text = caplog.text
        assert "138****5678" in text, (
            f"消息缺失 (logger 被禁用 / root handlers 被换): {text!r}"
        )

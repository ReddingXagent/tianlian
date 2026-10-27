"""测试辅助函数（供 conftest 与各测试模块共同导入）。

这些 helper 原先定义在 conftest.py, 但 pytest 不保证 conftest.py 可作为常规模块
导入 (ModuleNotFoundError: No module named 'conftest')。抽取到独立模块后,
conftest 与测试文件用同一种 import 方式引用, 避免收集期 ImportError。见卡 17354607。
"""
# 卡43bb99d7: 测试用 bcrypt hash 进程级缓存。
# 根因: function-scope fixture (seed_users/test_db) 每 test 反复 bcrypt.hashpw(~30ms/次),
# 12000+ 测试 × 4 次 ≈ 48000 次慢 hash, 是全量套件 >4min 无输出的主因。
# 安全性: bcrypt 验证 (checkpw) 用 hash 内嵌 salt, 同密码复用同 hash 不影响校验正确性 ——
# 仅失去「同密码不同 hash」的随机性, 测试场景可接受。生产代码绝不复用此 helper。
_PRECOMPUTED_HASHES: dict[str, str] = {}


def _fast_hash(password: str) -> str:
    """测试用：首次计算 bcrypt hash，后续直接复用（进程级缓存）。"""
    if password not in _PRECOMPUTED_HASHES:
        import bcrypt
        _PRECOMPUTED_HASHES[password] = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt()
        ).decode()
    return _PRECOMPUTED_HASHES[password]


def preserve_global_logging():
    """上下文管理器: 快照并恢复全局 logging 配置 (卡 057c8a9e)。

    根因: alembic/env.py 的 fileConfig(alembic.ini) 会 (a) 把 root handlers 换成
    ini 的 console + root.setLevel(WARNING), (b) 默认 disable_existing_loggers=True
    禁用所有已创建的 app.* logger, (c) 配置 ini 声明的 sqlalchemy/alembic logger
    level。在测试进程内跑 command.upgrade (tests/test_migration_chain_fresh_db.py)
    后这些状态跨测试残留 → 后续所有 caplog 断言族消息缺失红
    (caplog.set_level/at_level 无法穿透 logger.disabled / 摘除的 root handlers)。

    本 helper 供跑 alembic 迁移链的测试包裹 upgrade 调用, 保证全局 logging 无痕:
    root level/handlers 恢复 (新增 handler close), 全部已创建 logger 的
    disabled/level 逐项还原。propagate 不快照: fileConfig 不改它。
    """
    import contextlib
    import logging

    root = logging.getLogger()
    saved_root_level = root.level
    saved_root_handlers = root.handlers[:]
    saved_logger_state = {
        name: (lg.disabled, lg.level)
        for name, lg in logging.Logger.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }

    @contextlib.contextmanager
    def _ctx():
        try:
            yield
        finally:
            root.setLevel(saved_root_level)
            new_handlers = [h for h in root.handlers if h not in saved_root_handlers]
            root.handlers[:] = saved_root_handlers
            for h in new_handlers:
                try:
                    h.close()
                except Exception:
                    pass
            for name, (disabled, level) in saved_logger_state.items():
                lg = logging.Logger.manager.loggerDict.get(name)
                if isinstance(lg, logging.Logger):
                    lg.disabled = disabled
                    lg.setLevel(level)

    return _ctx()

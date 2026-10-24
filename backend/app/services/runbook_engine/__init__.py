"""
Runbook 自动化执行引擎 — 包入口

原 app/services/runbook_engine.py(1075行) 按职责拆为子模块 (卡 1ed83abf):
- security.py  : shell 注入防御 (_SHELL_INJECTION_CHARS / validate_shell_command / safe_command_list)
- models.py    : 枚举 (RunbookActionType / RunbookStatus / RiskLevel) + 数据模型 (RunbookStep / RunbookExecution)
- templates.py : RunbookTemplate 内置模板库
- engine.py    : RunbookEngine 执行引擎 + execute_runbook_for_alarm 便捷函数

本 __init__ 重导出全部公共符号, 保持
``from app.services.runbook_engine import X`` 与
``import app.services.runbook_engine as m; m.X`` 两类导入路径完全不变。

⚠️ 拆包兼容要点 (测试 patch 目标):
1. ``logger`` 定义在本 __init__ (logging.getLogger(__name__) 名称与原单文件一致)。
   engine 子模块经 ``_LoggerProxy`` 动态查找本属性, 保留
   ``patch("app.services.runbook_engine.logger")`` 生效 —— 若改由 engine 子模块各自
   getLogger, 方法全局解析于子模块命名空间, 包级 patch 脱钩。
2. ``subprocess`` / ``shlex`` 在本 __init__ 显式 import, 使
   ``patch("app.services.runbook_engine.subprocess.run")`` /
   ``monkeypatch.setattr(m.shlex, "split", ...)`` 的属性解析链可达 (二者均为进程级
   单例模块, 子模块 import 同一对象, patch 自然传播)。
3. RunbookTemplate / RunbookEngine 为类对象 (单例), ``patch(...RunbookTemplate.match)``
   与 ``patch.object(RunbookEngine, ...)`` 经重导出命中同一类。
"""
import logging
import shlex
import subprocess

# 包级 logger: 名称 = "app.services.runbook_engine", 与原单文件一致。
# 必须先于 engine 子模块导入定义, 供 _LoggerProxy 运行时动态查找。
logger = logging.getLogger(__name__)

from .security import _SHELL_INJECTION_CHARS, validate_shell_command, safe_command_list  # noqa: E402
from .models import (  # noqa: E402
    RunbookActionType,
    RunbookStatus,
    RiskLevel,
    RunbookStep,
    RunbookExecution,
)
from .templates import RunbookTemplate  # noqa: E402
from .engine import RunbookEngine, execute_runbook_for_alarm  # noqa: E402

__all__ = [
    # security
    "_SHELL_INJECTION_CHARS",
    "validate_shell_command",
    "safe_command_list",
    # models
    "RunbookActionType",
    "RunbookStatus",
    "RiskLevel",
    "RunbookStep",
    "RunbookExecution",
    # templates / engine
    "RunbookTemplate",
    "RunbookEngine",
    "execute_runbook_for_alarm",
    # 拆包兼容: 测试 patch 目标
    "logger",
    "subprocess",
    "shlex",
]

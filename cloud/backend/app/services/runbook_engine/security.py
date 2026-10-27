"""Shell 注入防御 — 从原 runbook_engine.py 拆出 (卡 1ed83abf)。

对外符号 ``_SHELL_INJECTION_CHARS`` / ``validate_shell_command`` /
``safe_command_list`` 由包 ``__init__`` 重导出, import 路径不变。
"""
import shlex
from typing import List


# ========== Shell 注入防御 ==========

# 危险 shell 元字符黑名单: 出现即拒绝执行。
# 即使 shell=False 下这些字符不会被 shell 解释,仍作为纵深防御——
# 防止命令被误以 shell=True 重新启用、或被 shlex 意外重组造成注入。
_SHELL_INJECTION_CHARS = (
    ";", "&", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\\", "\n", "\r",
)


def validate_shell_command(command: str) -> None:
    """校验用户可控的命令字符串,禁止 shell 注入元字符。

    适用于 runbook step.command / pre_check / rollback_command 等外部输入。

    Args:
        command: 待执行的命令字符串。

    Raises:
        ValueError: 命令为空或包含危险 shell 元字符。
    """
    if not command or not command.strip():
        raise ValueError("命令为空,拒绝执行")
    for ch in _SHELL_INJECTION_CHARS:
        if ch in command:
            raise ValueError(f"命令含危险 shell 元字符 {ch!r},疑似注入,拒绝执行")


def safe_command_list(command: str) -> List[str]:
    """校验命令并把字符串拆分为 argv 列表,供 subprocess.run(shell=False) 使用。

    Returns:
        argv 列表。

    Raises:
        ValueError: 命令含危险元字符、为空、或 shlex 解析失败。
    """
    validate_shell_command(command)
    try:
        argv = shlex.split(command)
    except ValueError as e:
        raise ValueError(f"命令解析失败: {e}") from e
    if not argv:
        raise ValueError("命令解析后为空 argv")
    return argv

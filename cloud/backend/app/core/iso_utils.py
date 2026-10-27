"""ISO8601 时间字符串解析的共享 helper。

背景: py3.9 ``datetime.fromisoformat`` 不识别末尾 ``'Z'`` 后缀 (3.11+ 才支持),
直接喂 ``"...Z"`` 会抛 ``ValueError``。多个端点 (charging_orders / fleet_drivers /
fleet_vehicle_profiles / inspection / on_call) 各自 ``datetime.fromisoformat`` 解析
用户输入, 在 py3.9 生产环境对 ``Z`` 后缀行为不一 (500 / 误拒 / 静默吞)。

本模块统一收口: 先把末尾 ``'Z'``/``'z'`` 归一为 ``'+00:00'`` 再解析, 3.9 与 3.11
行为一致。解析失败由调用方决定 (通常 ``parse_iso8601_or_400`` 显式 HTTPException(400))。

- 卡 a7d04453: on_call 首次引入 ``_parse_iso`` (本模块的雏形)
- 卡 c4cbcbf1: 提取为共享模块, 收口同族缺陷
"""
from datetime import datetime

from fastapi import HTTPException


def parse_iso8601(value: str) -> datetime:
    """解析 ISO8601 时间字符串; py3.9 兼容末尾 ``'Z'`` 后缀。

    与 ``datetime.fromisoformat`` 行为一致, 仅额外做末尾 ``'Z'``/``'z'`` → ``'+00:00'``
    归一 (3.9 必须, 3.11+ 幂等)。不做时区剥离/转换 —— aware 或 naive 由输入决定,
    aware/naive 落 naive DB 列时 SQLAlchemy 自行剥 tzinfo 存墙钟。

    成功返回 ``datetime``; 失败 (非 ISO / 非法日期 / 空串) 抛 ``ValueError``。
    """
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def parse_iso8601_or_400(value: str, detail: str = "时间格式无效，需 ISO8601") -> datetime:
    """同 :func:`parse_iso8601`, 解析失败显式 ``HTTPException(400)``。

    用户输入错误不应冒泡到端点通用 ``except Exception`` 返回 500; ``detail`` 可按
    字段名定制 (如 ``"hire_date 格式无效，需 ISO 8601"``)。
    """
    try:
        return parse_iso8601(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=detail)

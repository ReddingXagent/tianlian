"""共享 ISO8601 解析 helper 单元测试 (卡 c4cbcbf1)。

卡 a7d04453 在 on_call.py 首次引入 ``_parse_iso`` (py3.9 fromisoformat 不识 Z);
本卡将其提取为 ``app/core/iso_utils.py`` 共享模块, 供 charging_orders /
fleet_drivers / fleet_vehicle_profiles / inspection 同族缺陷统一收口。

纯函数测试, 不起 HTTP; 覆盖四态: Z后缀 / 显式offset / naive / 坏值。
py3.9(.venv=3.11看不出该bug) 两端行为一致 (Z 归一后等价于 +00:00)。
"""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.iso_utils import parse_iso8601, parse_iso8601_or_400


# ─── parse_iso8601 (纯函数, 失败抛 ValueError) ───

def test_parse_z_suffix_normalized():
    """末尾 'Z' 归一为 '+00:00' → aware UTC datetime。

    py3.9 ``datetime.fromisoformat`` 不识别 'Z' (3.11+ 才支持), helper 先归一再解析,
    故 3.9/3.11 行为一致。
    """
    dt = parse_iso8601("2026-01-01T09:00:00Z")
    assert dt == datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    assert dt.utcoffset().total_seconds() == 0


def test_parse_lowercase_z_suffix_normalized():
    """小写 'z' 同样归一 (与 on_call 旧行为一致)。"""
    dt = parse_iso8601("2026-01-01T09:00:00z")
    assert dt == datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def test_parse_explicit_offset_preserved():
    """显式 '+08:00' 本就可解析, helper 透传, offset 原样保留。"""
    from datetime import timedelta, timezone as tz
    dt = parse_iso8601("2026-01-01T09:00:00+08:00")
    assert dt == datetime(2026, 1, 1, 9, 0, tzinfo=tz(timedelta(hours=8)))


def test_parse_naive_returns_naive():
    """无 tz 输入 → naive datetime (tzinfo is None), 不强行注入时区。"""
    dt = parse_iso8601("2026-01-01T09:00:00")
    assert dt == datetime(2026, 1, 1, 9, 0)
    assert dt.tzinfo is None


def test_parse_strips_surrounding_whitespace():
    """首尾空白先 strip (与 on_call 旧行为一致)。"""
    dt = parse_iso8601("  2026-01-01T09:00:00Z  ")
    assert dt == datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("bad", ["not-a-date", "", "   ", "2026-13-99T99:99:99", "2026/01/01T09:00:00"])
def test_parse_bad_value_raises_valueerror(bad):
    """坏值/非法日期/空串 → ValueError (交由调用方决定 400/默认值等)。"""
    with pytest.raises(ValueError):
        parse_iso8601(bad)


# ─── parse_iso8601_or_400 (HTTP 包装, 失败抛 HTTPException(400)) ───

def test_or_400_z_suffix_ok():
    """合法 Z → 正常返回 datetime, 不抛。"""
    dt = parse_iso8601_or_400("2026-01-01T09:00:00Z")
    assert dt == datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def test_or_400_bad_value_raises_400():
    """坏值 → HTTPException(400), 不冒泡 500。"""
    with pytest.raises(HTTPException) as exc:
        parse_iso8601_or_400("not-a-date")
    assert exc.value.status_code == 400


def test_or_400_custom_detail():
    """detail 文案可定制 (各端点字段名不同)。"""
    with pytest.raises(HTTPException) as exc:
        parse_iso8601_or_400("bad", detail="hire_date 格式无效，需 ISO 8601")
    assert exc.value.status_code == 400
    assert exc.value.detail == "hire_date 格式无效，需 ISO 8601"


def test_or_400_default_detail():
    """未传 detail 用默认文案。"""
    with pytest.raises(HTTPException) as exc:
        parse_iso8601_or_400("bad")
    assert exc.value.status_code == 400
    assert exc.value.detail  # 非空

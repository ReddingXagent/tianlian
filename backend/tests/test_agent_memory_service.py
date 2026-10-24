"""agent_memory_service 行为锁测试 (卡 85e195a2)

覆盖源文件头实现约定的行为锚点:
- 记忆持久化 + ILIKE 检索 (命中/未命中/大小写不敏感/board/category 过滤)
- 对话历史持久化与回放 (最近在前, 同 created_at 时 id 兜底保证插入顺序)
- team_id 多租户隔离红线: 空/None 拒绝, 跨 team 不可见
- _now_utc 返回 aware UTC
"""
from datetime import datetime, timezone

import pytest

from app.services import agent_memory_service as svc
from app.services.agent_memory_service import (
    _now_utc,
    get_conversation_history,
    get_findings,
    save_conversation,
    save_memory,
    search_memory,
    update_finding_status,
)


T1, T2 = 101, 202  # 两个租户 (SQLite 不强制 FK, 直接用任意 id)


# ---------------------------------------------------------------- _now_utc

def test_now_utc_is_aware_utc(test_db):
    now = _now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0
    # 与真实当前时间差在 5s 内
    assert abs((now - datetime.now(timezone.utc)).total_seconds()) < 5


# ---------------------------------------------------------------- 持久化 + 检索

def test_save_memory_persists_and_returns(test_db):
    mem = save_memory(
        T1, "maintenance", "finding",
        title="设备离线", content="3号充电桩离线超过30分钟",
        source="patrol:device_offline", severity="warning",
        metadata={"station": "S01"}, importance=0.9,
        related_type="device", related_id="dev-3",
    )
    assert mem.id is not None
    assert mem.team_id == T1
    assert mem.board == "maintenance"
    assert mem.category == "finding"
    assert mem.severity == "warning"
    assert mem.meta_info == {"station": "S01"}
    assert mem.importance == 0.9
    assert mem.related_type == "device"
    assert mem.related_id == "dev-3"
    assert mem.status == "open"  # 默认值


def test_search_memory_hit_title_and_content(test_db):
    save_memory(T1, "maintenance", "finding", title="充电异常", content="无关正文")
    save_memory(T1, "maintenance", "diagnosis", title="其他标题", content="电池温度过高诊断")
    # title 命中 + content 命中
    assert len(search_memory(T1, "充电异常")) == 1
    assert len(search_memory(T1, "温度过高")) == 1


def test_search_memory_miss(test_db):
    save_memory(T1, "maintenance", "finding", title="标题", content="正文")
    assert search_memory(T1, "不存在的关键词") == []


def test_search_memory_case_insensitive(test_db):
    save_memory(T1, "admin", "learning", title="Runbook ABC", content="...")
    # 查询小写命中大写存储
    assert len(search_memory(T1, "runbook abc")) == 1
    # 反向: 存储小写、查询大写
    save_memory(T1, "admin", "learning", title="lowercase title", content="...")
    assert len(search_memory(T1, "LOWERCASE")) == 1


def test_search_memory_filters_board_and_category(test_db):
    save_memory(T1, "maintenance", "finding", title="离线告警", content="c")
    save_memory(T1, "operations", "finding", title="离线告警", content="c")
    save_memory(T1, "maintenance", "learning", title="离线经验", content="c")

    assert len(search_memory(T1, "离线")) == 3
    assert len(search_memory(T1, "离线", board="maintenance")) == 2
    assert len(search_memory(T1, "离线", board="maintenance", category="finding")) == 1


def test_search_memory_blank_query_returns_empty(test_db):
    save_memory(T1, "maintenance", "finding", title="t", content="c")
    assert search_memory(T1, "   ") == []
    assert search_memory(T1, "") == []


def test_get_findings_filters_status_and_board(test_db):
    m1 = save_memory(T1, "maintenance", "finding", title="f1", content="c")
    save_memory(T1, "operations", "finding", title="f2", content="c")
    save_memory(T1, "maintenance", "learning", title="l1", content="c")

    # get_findings 只按 created_at 倒序, 同秒写入顺序不承诺稳定 → 集合比较
    assert {m.title for m in get_findings(T1)} == {"f1", "f2"}

    assert [m.title for m in get_findings(T1, board="maintenance")] == ["f1"]

    update_finding_status(m1.id, "resolved")
    assert [m.title for m in get_findings(T1, board="maintenance")] == []
    assert [m.title for m in get_findings(T1, board="maintenance", status="resolved")] == ["f1"]


def test_update_finding_status_nonexistent_raises(test_db):
    with pytest.raises(ValueError):
        update_finding_status(999999, "resolved")


# ---------------------------------------------------------------- 对话历史

def test_conversation_roundtrip_order(test_db):
    # 逐条独立事务写入, 模拟真实多轮对话
    save_conversation(T1, "operations", "user", "查一下今天的订单")
    save_conversation(T1, "operations", "assistant", "今天共 12 笔订单", tool_calls=[{"name": "query_orders"}])
    save_conversation(T1, "operations", "user", "其中异常几笔")

    hist = get_conversation_history(T1, "operations")
    assert [(h.role, h.content) for h in hist] == [
        ("user", "其中异常几笔"),          # 最近在前
        ("assistant", "今天共 12 笔订单"),
        ("user", "查一下今天的订单"),
    ]
    assert hist[1].tool_calls == [{"name": "query_orders"}]


def test_conversation_history_limit(test_db):
    for i in range(5):
        save_conversation(T1, "admin", "user", f"msg-{i}")
    hist = get_conversation_history(T1, "admin", limit=3)
    assert [h.content for h in hist] == ["msg-4", "msg-3", "msg-2"]


def test_conversation_history_isolated_by_board_and_user(test_db):
    save_conversation(T1, "operations", "user", "ops-1")
    save_conversation(T1, "admin", "user", "admin-1")
    save_conversation(T1, "operations", "user", "ops-u9", user_id=9)

    assert [h.content for h in get_conversation_history(T1, "operations")] == [
        "ops-u9", "ops-1",
    ]
    assert [h.content for h in get_conversation_history(T1, "admin")] == ["admin-1"]
    # user_id 过滤: user 9 只见自己
    assert [h.content for h in get_conversation_history(T1, "operations", user_id=9)] == ["ops-u9"]


# ---------------------------------------------------------------- team_id 隔离红线

@pytest.mark.parametrize("fn", [save_memory, save_conversation, search_memory, get_findings, get_conversation_history], ids=["save_memory", "save_conversation", "search_memory", "get_findings", "get_conversation_history"])
def test_team_id_none_rejected(test_db, fn):
    with pytest.raises(ValueError):
        if fn is save_memory:
            fn(None, "maintenance", "finding", title="t", content="c")
        elif fn is save_conversation:
            fn(None, "maintenance", "user", "hello")
        elif fn is search_memory:
            fn(None, "kw")
        elif fn is get_findings:
            fn(None)
        else:
            fn(None, "maintenance")


def test_team_id_zero_rejected(test_db):
    with pytest.raises(ValueError):
        save_memory(0, "maintenance", "finding", title="t", content="c")


def test_cross_team_invisible(test_db):
    save_memory(T1, "maintenance", "finding", title="共享关键词", content="租户1的秘密")
    save_conversation(T1, "maintenance", "user", "租户1的对话")

    # 租户 2 搜同样的关键词, 不可见租户 1 的记忆/对话
    assert search_memory(T2, "共享关键词") == []
    assert search_memory(T2, "租户1") == []
    assert get_findings(T2) == []
    assert get_conversation_history(T2, "maintenance") == []

    # 租户 2 写入后也不影响租户 1
    save_memory(T2, "maintenance", "finding", title="共享关键词", content="租户2的内容")
    t1_hits = search_memory(T1, "共享关键词")
    assert len(t1_hits) == 1
    assert t1_hits[0].team_id == T1

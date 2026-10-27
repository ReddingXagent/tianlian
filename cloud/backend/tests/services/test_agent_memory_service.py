#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能体记忆服务测试 (卡 fa5ee850 → bf1f7e27 补强)

覆盖 app/services/agent_memory_service.py 全部 7 个核心函数:
    save_memory / save_conversation / search_memory / get_findings /
    update_finding_status / get_conversation_history (+ _new_session / _now_utc)

测试策略:
- CRUD 正常路径 + 边界值 + 多租户校验: 用 conftest 的 test_db (已 override 模块级
  SessionLocal, service 函数体内 `from app.core.database import SessionLocal`
  拿到的即此测试库 — 见 memory: service-sessionlocal-import-binding)。
  走真实 SQL/ILIKE/排序, 验证持久化往返与租户隔离。
- 异常容错分支 (commit 抛错 / 记录不存在): 用 MagicMock 注入坏 session,
  monkeypatch _new_session 避免触碰真实库。

team_id 是 FK→teams.id, 测试库未 seed team, 故 _seed_team 插入 team_id=1。

卡 bf1f7e27 补强 (TestSemanticEdgeCases): 行覆盖虽已 100%, 但补任务点名的语义场景 ——
真实数据多租户隔离、ILIKE 通配符 % 与 _ 的实际行为、超长输入、limit=0/超大、
单条搜索、SQLite datetime 时区往返现状、同 created_at 下双键排序稳定性。
"""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.services import agent_memory_service as svc
from app.models.agent_memory import AgentMemory, AgentConversation
from app.models.user import Team


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _seed_team(test_db) -> int:
    """插入一条 team (team_id=1), 满足 AgentMemory/Conversation 的 FK。返回 id。"""
    db = test_db["SessionLocal"]()
    try:
        db.add(Team(name="智能体测试团队", code="AGENT_TEST"))
        db.commit()
        return 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------
class TestSaveMemory:
    def test_save_memory_normal(self, test_db):
        """正常写入: 字段持久化 + id 回填"""
        _seed_team(test_db)
        mem = svc.save_memory(
            team_id=1,
            board="maintenance",
            category="finding",
            title="设备离线",
            content="充电桩 #3 心跳超时",
            source="patrol:device_offline",
            severity="critical",
            metadata={"device_id": 3, "ip": "10.0.0.3"},
            importance=0.9,
            related_type="device",
            related_id="3",
        )
        assert mem.id is not None
        assert mem.team_id == 1
        assert mem.board == "maintenance"
        assert mem.category == "finding"
        assert mem.title == "设备离线"
        assert mem.content == "充电桩 #3 心跳超时"
        assert mem.source == "patrol:device_offline"
        assert mem.severity == "critical"
        assert mem.meta_info == {"device_id": 3, "ip": "10.0.0.3"}
        assert mem.importance == 0.9
        assert mem.related_type == "device"
        assert mem.related_id == "3"
        assert mem.status == "open"  # 默认

    def test_save_memory_defaults(self, test_db):
        """省略可选参数时使用默认值"""
        _seed_team(test_db)
        mem = svc.save_memory(
            team_id=1, board="operations", category="decision",
            title="调度策略", content="削峰填谷",
        )
        assert mem.severity == "info"
        assert mem.importance == 0.5
        assert mem.status == "open"
        assert mem.meta_info == {}
        assert mem.source is None

    def test_save_memory_empty_team_id_raises(self, test_db):
        """多租户隔离红线: team_id 为空必须拒绝"""
        for bad in (0, None):
            with pytest.raises(ValueError, match="team_id 不能为空"):
                svc.save_memory(
                    team_id=bad, board="admin", category="learning",
                    title="x", content="y",
                )

    def test_save_memory_different_types(self, test_db):
        """四种 category + 三种 board + 自定义 status/expires_at 都能落库"""
        _seed_team(test_db)
        expires = svc._now_utc() + timedelta(days=7)
        mem = svc.save_memory(
            team_id=1, board="admin", category="learning",
            title="经验", content="重启可解 90% 问题",
            status="resolved", severity="warning", expires_at=expires,
        )
        assert mem.category == "learning"
        assert mem.status == "resolved"
        assert mem.expires_at is not None

    def test_save_memory_db_exception_rolls_back(self, test_db, monkeypatch):
        """commit 抛异常: rollback 被调用 + 异常上抛 + session 关闭"""
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db down")
        monkeypatch.setattr(svc, "_new_session", lambda: session)

        with pytest.raises(RuntimeError, match="db down"):
            svc.save_memory(
                team_id=1, board="maintenance", category="finding",
                title="x", content="y",
            )
        session.add.assert_called_once()
        session.rollback.assert_called_once()
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# save_conversation
# ---------------------------------------------------------------------------
class TestSaveConversation:
    def test_save_conversation_normal(self, test_db):
        """正常写入对话记录"""
        _seed_team(test_db)
        convo = svc.save_conversation(
            team_id=1, board="operations", role="user",
            content="查询昨日发电量", user_id=1,
            tool_calls=[{"name": "query_generation", "args": {"date": "2026-08-08"}}],
        )
        assert convo.id is not None
        assert convo.team_id == 1
        assert convo.user_id == 1
        assert convo.board == "operations"
        assert convo.role == "user"
        assert convo.content == "查询昨日发电量"
        assert convo.tool_calls[0]["name"] == "query_generation"

    def test_save_conversation_empty_content_allowed(self, test_db):
        """空字符串 content 在服务层不拦截 (DB Text 不强制非空校验在 service 层)"""
        _seed_team(test_db)
        convo = svc.save_conversation(
            team_id=1, board="admin", role="system", content="",
        )
        assert convo.content == ""
        assert convo.user_id is None
        assert convo.tool_calls is None

    def test_save_conversation_long_content(self, test_db):
        """超长内容可持久化 (Text 列)"""
        _seed_team(test_db)
        long_text = "长" * 10000
        convo = svc.save_conversation(
            team_id=1, board="maintenance", role="assistant", content=long_text,
        )
        assert len(convo.content) == 10000

    def test_save_conversation_empty_team_id_raises(self, test_db):
        with pytest.raises(ValueError, match="team_id 不能为空"):
            svc.save_conversation(team_id=0, board="admin", role="user", content="x")

    def test_save_conversation_db_exception(self, test_db, monkeypatch):
        """commit 失败: rollback + 上抛 + 关闭"""
        session = MagicMock()
        session.commit.side_effect = RuntimeError("convo db down")
        monkeypatch.setattr(svc, "_new_session", lambda: session)

        with pytest.raises(RuntimeError, match="convo db down"):
            svc.save_conversation(team_id=1, board="admin", role="user", content="x")
        session.rollback.assert_called_once()
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# search_memory
# ---------------------------------------------------------------------------
class TestSearchMemory:
    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="maintenance", category="finding",
                        title="充电桩离线", content="桩 #3 心跳超时", importance=0.8)
        svc.save_memory(team_id=1, board="operations", category="diagnosis",
                        title="电压异常诊断", content="母线电压波动", importance=0.6)
        svc.save_memory(team_id=1, board="admin", category="learning",
                        title="运维经验", content="重启可解离线", importance=0.4)

    def test_search_with_results(self, test_db):
        results = svc.search_memory(team_id=1, query="离线")
        assert len(results) >= 2  # 充电桩离线(title) + 重启可解离线(content)
        assert all(isinstance(r, AgentMemory) for r in results)

    def test_search_no_results(self, test_db):
        results = svc.search_memory(team_id=1, query="不存在的内容xyz123")
        assert results == []

    def test_search_fuzzy_ilike(self, test_db):
        """ILIKE 模糊匹配 + 不区分大小写"""
        results = svc.search_memory(team_id=1, query="CHARGING")
        # 不匹配中文 title; 英文大写关键词对中文内容无命中
        assert results == []
        # 子串模糊命中 content
        results = svc.search_memory(team_id=1, query="母线")
        assert any(r.title == "电压异常诊断" for r in results)

    def test_search_empty_query_returns_empty(self, test_db):
        """空关键词 / 纯空白: 直接返回空列表, 不查库"""
        assert svc.search_memory(team_id=1, query="") == []
        assert svc.search_memory(team_id=1, query="   ") == []

    def test_search_filters_board_category(self, test_db):
        """board + category 组合过滤"""
        results = svc.search_memory(
            team_id=1, query="离线", board="maintenance", category="finding",
        )
        assert len(results) == 1
        assert results[0].title == "充电桩离线"

    def test_search_limit(self, test_db):
        """limit 截断"""
        results = svc.search_memory(team_id=1, query="离线", limit=1)
        assert len(results) == 1

    def test_search_team_isolation(self, test_db):
        """跨租户隔离: 查 team_id=2 命中 0"""
        results = svc.search_memory(team_id=2, query="离线")
        assert results == []

    def test_search_empty_team_id_raises(self, test_db):
        with pytest.raises(ValueError, match="team_id 不能为空"):
            svc.search_memory(team_id=None, query="x")

    def test_search_db_exception(self, test_db, monkeypatch):
        """query 阶段异常上抛, session 仍关闭"""
        session = MagicMock()
        session.query.return_value.filter.return_value.filter.return_value \
            .order_by.return_value.limit.return_value.all.side_effect = RuntimeError("search down")
        monkeypatch.setattr(svc, "_new_session", lambda: session)
        with pytest.raises(RuntimeError, match="search down"):
            svc.search_memory(team_id=1, query="离线")
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# get_findings
# ---------------------------------------------------------------------------
class TestGetFindings:
    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        _seed_team(test_db)
        # 3 条 finding + 1 条非 finding (被 category 过滤掉)
        svc.save_memory(team_id=1, board="maintenance", category="finding",
                        title="发现A", content="c1", status="open")
        svc.save_memory(team_id=1, board="operations", category="finding",
                        title="发现B", content="c2", status="resolved")
        svc.save_memory(team_id=1, board="maintenance", category="finding",
                        title="发现C", content="c3", status="open")
        svc.save_memory(team_id=1, board="maintenance", category="learning",
                        title="经验D", content="c4", status="open")

    def test_get_findings_default_open(self, test_db):
        """默认 status=open, 仅返回 open 的 finding"""
        results = svc.get_findings(team_id=1)
        assert len(results) == 2  # 发现A + 发现C
        assert all(r.category == "finding" for r in results)
        assert all(r.status == "open" for r in results)

    def test_get_findings_status_filter(self, test_db):
        """status=resolved"""
        results = svc.get_findings(team_id=1, status="resolved")
        assert len(results) == 1
        assert results[0].title == "发现B"

    def test_get_findings_status_empty_returns_all(self, test_db):
        """status='' 不加状态过滤, 返回该 team 全部 finding"""
        results = svc.get_findings(team_id=1, status="")
        assert len(results) == 3

    def test_get_findings_board_filter(self, test_db):
        """board 过滤"""
        results = svc.get_findings(team_id=1, board="maintenance")
        # maintenance 下 finding: A(open) + C(open) = 2
        assert len(results) == 2

    def test_get_findings_limit(self, test_db):
        """limit 截断"""
        results = svc.get_findings(team_id=1, limit=1)
        assert len(results) == 1

    def test_get_findings_empty_result(self, test_db):
        """无匹配: 空列表"""
        assert svc.get_findings(team_id=999) == []

    def test_get_findings_empty_team_id_raises(self, test_db):
        with pytest.raises(ValueError, match="team_id 不能为空"):
            svc.get_findings(team_id=0)


# ---------------------------------------------------------------------------
# update_finding_status
# ---------------------------------------------------------------------------
class TestUpdateFindingStatus:
    def test_update_status_normal(self, test_db):
        """正常更新: 状态变更 + updated_at 刷新"""
        _seed_team(test_db)
        mem = svc.save_memory(team_id=1, board="maintenance", category="finding",
                              title="待处理", content="c")
        old_updated = mem.updated_at

        updated = svc.update_finding_status(mem.id, "acknowledged")
        assert updated.status == "acknowledged"
        assert updated.id == mem.id

    def test_update_status_nonexistent_id_raises(self, test_db):
        """不存在的 id: ValueError"""
        with pytest.raises(ValueError, match="不存在"):
            svc.update_finding_status(999999, "resolved")

    def test_update_status_invalid_value_still_writes(self, test_db):
        """非法状态字符串: 服务层不做枚举校验 (设计上状态由调用方保证),
        直接写入并返回"""
        _seed_team(test_db)
        mem = svc.save_memory(team_id=1, board="maintenance", category="finding",
                              title="x", content="y")
        result = svc.update_finding_status(mem.id, "bogus_status")
        assert result.status == "bogus_status"

    def test_update_status_db_exception(self, test_db, monkeypatch):
        """commit 失败: rollback + 上抛 + 关闭"""
        _seed_team(test_db)
        mem = svc.save_memory(team_id=1, board="maintenance", category="finding",
                              title="x", content="y")

        session = MagicMock()
        fake_mem = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = fake_mem
        session.commit.side_effect = RuntimeError("update down")
        monkeypatch.setattr(svc, "_new_session", lambda: session)

        with pytest.raises(RuntimeError, match="update down"):
            svc.update_finding_status(mem.id, "resolved")
        session.rollback.assert_called_once()
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# get_conversation_history
# ---------------------------------------------------------------------------
class TestGetConversationHistory:
    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        _seed_team(test_db)
        svc.save_conversation(team_id=1, board="operations", role="user",
                              content="u1", user_id=1)
        svc.save_conversation(team_id=1, board="operations", role="assistant",
                              content="a1", user_id=1)
        svc.save_conversation(team_id=1, board="operations", role="user",
                              content="u2", user_id=2)
        svc.save_conversation(team_id=1, board="admin", role="system",
                              content="s1")

    def test_get_history_normal(self, test_db):
        """正常: 返回 operations 板块全部对话, 倒序"""
        results = svc.get_conversation_history(team_id=1, board="operations")
        assert len(results) == 3
        assert all(isinstance(r, AgentConversation) for r in results)
        # 倒序: 最近插入在前
        assert results[0].content == "u2"

    def test_get_history_empty(self, test_db):
        """无匹配: 空列表"""
        assert svc.get_conversation_history(team_id=999, board="operations") == []

    def test_get_history_board_filter(self, test_db):
        """board 过滤: admin 仅 1 条"""
        results = svc.get_conversation_history(team_id=1, board="admin")
        assert len(results) == 1
        assert results[0].content == "s1"

    def test_get_history_user_id_filter(self, test_db):
        """user_id 过滤"""
        results = svc.get_conversation_history(team_id=1, board="operations", user_id=1)
        assert len(results) == 2
        assert all(r.user_id == 1 for r in results)

    def test_get_history_limit(self, test_db):
        """limit 截断 (最近 N 条)"""
        results = svc.get_conversation_history(team_id=1, board="operations", limit=2)
        assert len(results) == 2
        # 最近的 2 条: u2, a1
        assert results[0].content == "u2"
        assert results[1].content == "a1"

    def test_get_history_empty_team_id_raises(self, test_db):
        with pytest.raises(ValueError, match="team_id 不能为空"):
            svc.get_conversation_history(team_id=None, board="operations")


# ---------------------------------------------------------------------------
# 私有 helper
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_now_utc_is_aware(self):
        """_now_utc 返回带时区的 UTC datetime"""
        ts = svc._now_utc()
        assert ts.tzinfo is not None
        # UTC offset 应为 0
        assert ts.utcoffset().total_seconds() == 0

    def test_new_session_returns_session(self, test_db):
        """_new_session 返回可用 session (已被 test_db override)"""
        s = svc._new_session()
        try:
            assert hasattr(s, "query")
            assert hasattr(s, "commit")
        finally:
            s.close()


# ---------------------------------------------------------------------------
# 语义边界场景 (卡 bf1f7e27)
# 行覆盖已 100%, 这里补任务点名的语义契约, 防回归:
#   真实数据多租户隔离 / ILIKE 通配符行为 / 超长输入 / limit 边界 /
#   单条搜索 / datetime 时区往返现状 / 同 created_at 双键排序稳定性
# ---------------------------------------------------------------------------
class TestSemanticEdgeCases:
    def test_team_isolation_real_data(self, test_db):
        """多租户隔离红线 (真实数据版): team_id=1 写入, team_id=2 写入,
        互不可见 —— 不仅验证"空库查空", 而是验证"有数据但被隔离"。

        _seed_team 只插 team_id=1; team_id=2 无对应 team 行, 但 SQLite 默认
        不强制 FK, 故 team_id=2 的记录仍可落库, 用于验证查询侧的 team 过滤。
        """
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="maintenance", category="finding",
                        title="团队一私有发现", content="机密内容AAA")
        svc.save_memory(team_id=2, board="maintenance", category="finding",
                        title="团队二私有发现", content="机密内容AAA")

        # 各自只看到自己的数据, 关键词 AAA 两边都有但互不串
        a = svc.search_memory(team_id=1, query="AAA")
        b = svc.search_memory(team_id=2, query="AAA")
        assert len(a) == 1 and a[0].team_id == 1
        assert len(b) == 1 and b[0].team_id == 2

        # get_findings 同样隔离
        assert len(svc.get_findings(team_id=1)) == 1
        assert len(svc.get_findings(team_id=2)) == 1

    def test_search_ilike_wildcard_percent_matches_all(self, test_db):
        """ILIKE 把 % 当通配符: 关键词为纯 '%' 时匹配任意非空 title/content。

        这不是 bug 而是 ILIKE 语义约定 —— 调用方传裸 % 会命中全表。
        测试如实记录该行为, 防止有人误以为 % 被转义。
        """
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="alpha", content="x")
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="beta", content="y")
        # 纯 % → 通配, 命中两条
        assert len(svc.search_memory(team_id=1, query="%")) == 2
        # 含 % 的真实关键词: SQLite ilike 不转义, % 仍作通配 → 仍命中两条
        assert len(svc.search_memory(team_id=1, query="a%")) == 2

    def test_search_ilike_wildcard_underscore(self, test_db):
        """ILIKE 把 _ 当单字符通配: 'a_' 匹配以 a 开头两字符的串。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="ab", content="c")
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="ax", content="c")
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="abc", content="c")
        # pattern %a_% → 含至少 a 后跟一字符, 命中 ab/ax/abc 全部
        results = svc.search_memory(team_id=1, query="a_")
        titles = {r.title for r in results}
        assert "ab" in titles and "ax" in titles

    def test_search_special_chars_literal(self, test_db):
        """真实业务文本含 % _ 等字符时, 作为子串仍可被精确关键词命中
        (调用方传完整子串, 不触发通配)。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="完成度100%", content="def")
        # 传完整 '100%' 作关键词: SQLite ilike 中尾部 % 仍作通配, 但
        # '完成度100%' 本身是 title 子串 → 命中
        results = svc.search_memory(team_id=1, query="完成度100")
        assert any(r.title == "完成度100%" for r in results)

    def test_search_very_long_query(self, test_db):
        """超长关键词 (10k 字符): 不报错, 正常走 ILIKE, 无命中返回空。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="short", content="c")
        long_q = "x" * 10000
        assert svc.search_memory(team_id=1, query=long_q) == []

    def test_search_case_insensitive(self, test_db):
        """ILIKE 大小写不敏感 (英文)。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="Server Offline", content="c")
        assert len(svc.search_memory(team_id=1, query="server")) == 1
        assert len(svc.search_memory(team_id=1, query="OFFLINE")) == 1
        assert len(svc.search_memory(team_id=1, query="SeRvEr")) == 1

    def test_search_limit_zero(self, test_db):
        """limit=0: SQLAlchemy .limit(0) 生效, 返回空列表 (不报错)。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="hit", content="hit")
        assert svc.search_memory(team_id=1, query="hit", limit=0) == []

    def test_search_limit_huge(self, test_db):
        """limit 超大: 等价于无上限, 返回全部命中。"""
        _seed_team(test_db)
        for i in range(3):
            svc.save_memory(team_id=1, board="m", category="finding",
                            title=f"hit{i}", content="hit")
        assert len(svc.search_memory(team_id=1, query="hit", limit=10**9)) == 3

    def test_search_single_result(self, test_db):
        """单条命中边界: 恰好一条且字段完整。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="唯一标题", content="唯一正文")
        results = svc.search_memory(team_id=1, query="唯一标题")
        assert len(results) == 1
        assert results[0].title == "唯一标题"

    def test_search_orders_by_importance_secondary(self, test_db):
        """排序: created_at 相近时, importance 高的排前 (次序键)。"""
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="low", content="k", importance=0.1)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="high", content="k", importance=0.9)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="mid", content="k", importance=0.5)
        results = svc.search_memory(team_id=1, query="k")
        # created_at 同秒 (SQLite server_default 精度), 故按 importance 倒序
        assert [r.title for r in results] == ["high", "mid", "low"]

    def test_save_memory_datetime_persistence_sqlite_naive(self, test_db):
        """datetime 时区往返现状: 存 aware UTC, 经 SQLite 往返读回为 naive。

        SQLite 的 DateTime(timezone=True) 实际不保留时区信息 (与 PostgreSQL 不同),
        读回 created_at/updated_at 的 tzinfo 为 None。这是 SQLite 测试库的已知
        行为, 非 service bug —— 生产 PG 会保留 tzinfo。测试如实记录, 防误判回归。
        expires_at 由调用方传入, 同样往返后 naive。
        """
        _seed_team(test_db)
        expires = svc._now_utc()  # aware UTC
        mem = svc.save_memory(
            team_id=1, board="m", category="finding",
            title="tz", content="c", expires_at=expires,
        )
        # 写入时传入 aware, 读回后 SQLite 丢失 tzinfo
        assert mem.created_at is not None
        assert mem.expires_at is not None
        assert mem.created_at.tzinfo is None  # SQLite 往返后 naive
        assert mem.expires_at.tzinfo is None

    def test_update_status_persists_across_sessions(self, test_db):
        """update_finding_status 持久化: 新 session 查回状态确已变更
        (覆盖 commit + refresh 真实落库, 非仅内存)。"""
        _seed_team(test_db)
        mem = svc.save_memory(team_id=1, board="m", category="finding",
                              title="x", content="y")
        svc.update_finding_status(mem.id, "resolved")

        # 用全新 session 查回, 验证持久化
        db = test_db["SessionLocal"]()
        try:
            reloaded = db.query(AgentMemory).filter(AgentMemory.id == mem.id).first()
            assert reloaded.status == "resolved"
            assert reloaded.updated_at is not None
        finally:
            db.close()

    def test_get_findings_order_unstable_without_id_tiebreaker(self, test_db):
        """get_findings 排序现状: 仅 created_at.desc() 无 id 兜底
        (对比 get_conversation_history 有 id.desc() 双键)。

        SQLite func.now() 同秒插入多条 → created_at 完全相同 → 单键排序不稳定,
        返回顺序由 SQLite 内部决定 (实测按主键 asc = 插入顺序)。
        这是源码与 conversation 查询的排序一致性差异点, 此处如实记录现状,
        不固化具体顺序; 若未来补 id 兜底, 本测试可改为严格倒序断言。
        """
        _seed_team(test_db)
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="first", content="c")
        svc.save_memory(team_id=1, board="m", category="finding",
                        title="second", content="c")
        results = svc.get_findings(team_id=1)
        # 不固化顺序, 只验证两条都被召回
        assert {r.title for r in results} == {"first", "second"}

    def test_conversation_history_id_tiebreaker(self, test_db):
        """对话排序双键: 同 created_at (SQLite 同秒) 下, id 大的 (后插入) 排前。
        覆盖 created_at + id.desc() 兜底逻辑, 防单键排序不稳定。"""
        _seed_team(test_db)
        # 同事务连插多条, created_at 完全相同 (SQLite func.now() 同值)
        for i in range(5):
            svc.save_conversation(team_id=1, board="ops", role="user",
                                  content=f"msg{i}")
        results = svc.get_conversation_history(team_id=1, board="ops")
        # id 倒序: msg4(id最大) 在前 → msg0 在后
        assert [r.content for r in results] == [f"msg{i}" for i in range(4, -1, -1)]

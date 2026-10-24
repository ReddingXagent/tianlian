"""
AI 通用对话服务(ai_chat)测试 - 覆盖率补强 ≥70%

被测: app/services/ai_chat.py (388 行)
覆盖:
- _team_scope          team_id=0 不过滤 / >0 隔离(杜绝跨企业泄露)
- _query_knowledge_base 关键词提取 / Article+FAQ 检索 / team 隔离 / published 过滤 / 异常吞掉
- _build_context_prompt page_type/device/station/alarms/workorder/extra 各分支
- _call_llm            正常/流式/fallback/无 provider/异常响应/raise_for_status
- chat                 JSON(markdown 块/裸对象/非JSON/DecodeError)解析 / sources 补充 /
                       RAG 注入 / history 截断 / stream / 错误兜底(needs_human)
- stream_generator     chunk / [DONE] / 无效行跳过
- chat_stream          stream 直返 / 非 stream 回落 async gen
"""
import json
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests as _real_requests

import socket as _socket

from app.core import url_safety as _url_safety
from app.services.ai_chat import (
    SYSTEM_PROMPT,
    _team_scope,
    _query_knowledge_base,
    _call_llm,
    _build_context_prompt,
    chat,
    stream_generator,
    chat_stream,
)
from app.models.knowledge import KnowledgeArticle, KnowledgeFAQ


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

def _make_article(db, title, content, tags=None, team_id=0, published=True, category="cat"):
    art = KnowledgeArticle(
        title=title, content=content, tags=tags,
        team_id=team_id, published=published, category=category,
    )
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


def _make_faq(db, question, answer, tags=None, team_id=0, category="cat"):
    faq = KnowledgeFAQ(
        question=question, answer=answer, tags=tags,
        team_id=team_id, category=category,
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


# ═══════════════════════════════════════════════════════════════
# 1. _team_scope
# ═══════════════════════════════════════════════════════════════

class TestTeamScope:
    """team 隔离过滤条件: 杜绝天链助手跨账户(企业)数据泄露。"""

    def test_zero_returns_none_no_filter(self):
        # team_id=0(平台默认) → None, 表示不过滤(见全部)
        assert _team_scope(KnowledgeArticle, 0) is None

    def test_none_team_id_returns_none(self):
        # falsy 的 team_id 都视为平台, 不过滤
        assert _team_scope(KnowledgeArticle, None) is None

    def test_nonzero_returns_in_clause(self):
        clause = _team_scope(KnowledgeArticle, 5)
        assert clause is not None
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # 企业 5 仅可见 平台共享(0) + 本企业(5)
        assert "0" in compiled and "5" in compiled
        assert "IN" in compiled.upper()

    def test_different_team_excluded_from_clause(self):
        # team 5 的 in 列表不含 10
        clause = _team_scope(KnowledgeArticle, 5)
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "10" not in compiled


# ═══════════════════════════════════════════════════════════════
# 2. _query_knowledge_base (真 DB)
# ═══════════════════════════════════════════════════════════════

class TestQueryKnowledgeBase:

    def test_article_title_match(self, test_db):
        db = test_db["session"]
        _make_article(db, title="逆变器过温故障排查", content="检查散热风扇", tags="逆变器,温控")
        results = _query_knowledge_base("逆变器过温", db)
        assert len(results) >= 1
        art = [r for r in results if r["type"] == "article"]
        assert any("逆变器" in r["title"] for r in art)

    def test_article_content_and_tag_scoring(self, test_db):
        db = test_db["session"]
        # 标题不含关键词, 仅 content + tags 命中
        _make_article(db, title="通用手册", content="充电桩维护要点", tags="充电桩")
        results = _query_knowledge_base("充电桩", db)
        assert any(r["type"] == "article" for r in results)

    def test_faq_question_higher_score_than_answer(self, test_db):
        db = test_db["session"]
        # FAQ question 命中 +4(+tags +2), 应优先于仅 answer 命中(+1)
        _make_faq(db, question="如何重置逆变器?", answer="请参考手册", tags="逆变器,重置")
        _make_faq(db, question="其他问题", answer="逆变器复位步骤如下")
        results = _query_knowledge_base("逆变器", db)
        faqs = [r for r in results if r["type"] == "faq"]
        # 至少命中, 且 question 直接命中的排前
        assert len(faqs) >= 1
        assert faqs[0]["title"] == "如何重置逆变器?"

    def test_unpublished_article_excluded(self, test_db):
        db = test_db["session"]
        _make_article(db, title="草稿逆变器说明", content="草稿内容", published=False)
        results = _query_knowledge_base("逆变器", db)
        assert not any(r["title"] == "草稿逆变器说明" for r in results)

    def test_team_isolation_excludes_other_enterprise(self, test_db):
        db = test_db["session"]
        # 企业 5 的 article + 平台共享(0) + 企业 10(不应可见)
        _make_article(db, title="平台共享逆变器文档", content="共享", team_id=0)
        _make_article(db, title="企业5专属逆变器文档", content="专属", team_id=5)
        _make_article(db, title="企业10机密逆变器文档", content="机密", team_id=10)
        results = _query_knowledge_base("逆变器", db, team_id=5)
        titles = [r["title"] for r in results]
        assert "平台共享逆变器文档" in titles
        assert "企业5专属逆变器文档" in titles
        # 关键断言: 杜绝跨企业数据泄露
        assert "企业10机密逆变器文档" not in titles

    def test_team_isolation_faq(self, test_db):
        db = test_db["session"]
        _make_faq(db, question="企业5逆变器FAQ", answer="a", team_id=5)
        _make_faq(db, question="企业10逆变器FAQ", answer="a", team_id=10)
        results = _query_knowledge_base("逆变器", db, team_id=5)
        questions = [r["title"] for r in results]
        assert "企业5逆变器FAQ" in questions
        assert "企业10逆变器FAQ" not in questions

    def test_empty_keywords_returns_empty(self, test_db):
        db = test_db["session"]
        _make_article(db, title="逆变器", content="内容")
        # 全标点/单字(被 len>1 过滤) → 无关键词 → []
        assert _query_knowledge_base("？？？！！！", db) == []
        # 单字关键词也被丢弃
        assert _query_knowledge_base("电", db) == []

    def test_no_match_returns_empty(self, test_db):
        db = test_db["session"]
        _make_article(db, title="逆变器文档", content="内容")
        assert _query_knowledge_base("完全不相关的关键词XYZ", db) == []

    def test_topk_limit(self, test_db):
        db = test_db["session"]
        for i in range(5):
            _make_article(db, title=f"逆变器文档{i}", content="逆变器", team_id=0)
        results = _query_knowledge_base("逆变器", db, top_k=2)
        assert len(results) <= 2

    def test_relevance_capped_at_one(self, test_db):
        db = test_db["session"]
        _make_article(db, title="逆变器逆变器", content="逆变器逆变器逆变器", tags="逆变器")
        results = _query_knowledge_base("逆变器", db)
        assert all(r["relevance"] <= 1.0 for r in results)

    def test_db_exception_swallowed_returns_empty(self):
        # db.query 抛异常 → 两个 try 块吞掉 → 返回 []
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert _query_knowledge_base("逆变器故障", db) == []

    def test_long_content_truncated(self, test_db):
        db = test_db["session"]
        long_body = "逆变器" + ("x" * 3000)
        _make_article(db, title="逆变器手册", content=long_body)
        results = _query_knowledge_base("逆变器", db)
        art = next(r for r in results if r["type"] == "article")
        # content 截断到 2000 字符
        assert len(art["content"]) <= 2000


# ═══════════════════════════════════════════════════════════════
# 3. _build_context_prompt
# ═══════════════════════════════════════════════════════════════

class TestBuildContextPrompt:

    def test_none_context_returns_empty(self):
        assert _build_context_prompt(None) == ""

    def test_empty_context_returns_empty(self):
        assert _build_context_prompt({}) == ""

    def test_page_type(self):
        out = _build_context_prompt({"page_type": "device_detail"})
        assert "当前页面" in out
        assert "device_detail" in out

    def test_device_block(self):
        out = _build_context_prompt({"device": {
            "name": "充电桩#1", "id": 42, "type": "DC", "status": "online", "station_name": "测试站",
        }})
        assert "充电桩#1" in out
        assert "42" in out
        assert "测试站" in out

    def test_station_block_default_health(self):
        out = _build_context_prompt({"station": {"name": "A站", "id": 1, "address": "北京"}})
        assert "A站" in out
        assert "北京" in out
        # 无 health_score → N/A
        assert "N/A" in out

    def test_alarms_block_uses_content(self):
        out = _build_context_prompt({"alarms": [
            {"content": "温度过高", "level": "warning"}
        ]})
        assert "温度过高" in out
        assert "warning" in out
        assert "1条" in out

    def test_alarms_block_falls_back_to_title(self):
        out = _build_context_prompt({"alarms": [
            {"title": "告警标题", "level": "critical"}
        ]})
        assert "告警标题" in out

    def test_empty_alarms_list_skipped(self):
        out = _build_context_prompt({"alarms": []})
        assert "当前告警" not in out

    def test_workorder_block(self):
        out = _build_context_prompt({"workorder": {
            "title": "工单A", "id": 9, "status": "open", "priority": "high",
        }})
        assert "工单A" in out
        assert "open" in out
        assert "high" in out

    def test_extra_block_json(self):
        out = _build_context_prompt({"extra": {"k": "v"}})
        assert "额外" in out
        assert '"k"' in out

    def test_full_context_combination(self):
        out = _build_context_prompt({
            "page_type": "dashboard",
            "device": {"name": "D"},
            "station": {"name": "S"},
            "alarms": [{"content": "A"}],
            "workorder": {"title": "W"},
            "extra": {"x": 1},
        })
        # 各块都应出现
        assert "当前页面" in out
        assert "设备" in out
        assert "站点" in out
        assert "当前告警" in out
        assert "工单" in out
        assert "额外" in out


# ═══════════════════════════════════════════════════════════════
# 4. _call_llm
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch):
    """api.example.com 本机不可解析; SSRF 出站校验按公网 IP 放行(确定性)。"""
    real = _socket.getaddrinfo

    def fake(host, *a, **kw):
        try:
            return real(host, *a, **kw)
        except (_socket.gaierror, _socket.error):
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(_url_safety.socket, "getaddrinfo", fake)


def _cfg(**over):
    base = {
        "base_url": "https://api.example.com/v1/",
        "api_key": "sk-test",
        "model_id": "test-model",
        "name": "TestProvider",
        "max_tokens": 8000,
    }
    base.update(over)
    return base


class TestCallLLM:

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_normal_non_stream(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hello world"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_req.post.return_value = mock_resp

        result = _call_llm([{"role": "user", "content": "hi"}])

        assert result["content"] == "hello world"
        assert result["model"] == "test-model"
        assert result["provider"] == "TestProvider"
        assert result["usage"]["total_tokens"] == 15
        assert result["usage"]["prompt_tokens"] == 10

        # 验证请求 url / headers / payload
        args, kwargs = mock_req.post.call_args
        assert args[0].endswith("/chat/completions")
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
        assert kwargs["timeout"] == 120
        assert kwargs["json"]["model"] == "test-model"
        assert kwargs["json"]["stream"] is False

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_max_tokens_capped_by_model_config(self, mock_mm, mock_req):
        # model_config max_tokens=1000 → 传入 4096 被压到 1000
        mock_mm.get_model_for_task.return_value = _cfg(max_tokens=1000)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = mock_resp

        _call_llm([{"role": "user", "content": "hi"}], max_tokens=4096)
        payload = mock_req.post.call_args.kwargs["json"]
        assert payload["max_tokens"] == 1000

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_max_tokens_default_when_absent(self, mock_mm, mock_req):
        # 无 max_tokens key → 默认 4096
        mock_mm.get_model_for_task.return_value = _cfg(max_tokens=None)
        del mock_mm.get_model_for_task.return_value["max_tokens"]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = mock_resp

        _call_llm([{"role": "user", "content": "hi"}])
        payload = mock_req.post.call_args.kwargs["json"]
        assert payload["max_tokens"] == 4096

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_stream_returns_response_object(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        stream_resp = MagicMock(name="stream_response")
        mock_req.post.return_value = stream_resp

        result = _call_llm([{"role": "user", "content": "hi"}], stream=True)

        assert result["stream"] is stream_resp
        assert result["model"] == "test-model"
        kwargs = mock_req.post.call_args.kwargs
        assert kwargs["stream"] is True
        assert kwargs["timeout"] == 120

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_fallback_to_first_provider_when_no_task_mapping(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = None
        mock_mm.get_providers.return_value = [_cfg(model_id="fallback-model", name="FB")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_req.post.return_value = mock_resp

        result = _call_llm([{"role": "user", "content": "hi"}])
        assert result["model"] == "fallback-model"
        assert result["provider"] == "FB"

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_no_provider_raises(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = None
        mock_mm.get_providers.return_value = []
        with pytest.raises(ValueError, match="没有可用"):
            _call_llm([{"role": "user", "content": "hi"}])
        mock_req.post.assert_not_called()

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_empty_choices_raises(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        mock_req.post.return_value = mock_resp
        with pytest.raises(ValueError, match="LLM返回异常"):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_no_choices_key_raises(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"unexpected": "shape"}
        mock_req.post.return_value = mock_resp
        with pytest.raises(ValueError, match="LLM返回异常"):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_usage_missing_defaults_zero(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = mock_resp
        result = _call_llm([{"role": "user", "content": "hi"}])
        assert result["usage"]["total_tokens"] == 0

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_http_error_propagates(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = _real_requests.HTTPError("500 Server Error")
        mock_req.post.return_value = mock_resp
        with pytest.raises(_real_requests.HTTPError):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_timeout_propagates(self, mock_mm, mock_req):
        # 模型不可用/网络超时: requests 抛 Timeout → 调用方 chat 兜底
        mock_mm.get_model_for_task.return_value = _cfg()
        mock_req.post.side_effect = _real_requests.Timeout("connect timed out")
        with pytest.raises(_real_requests.Timeout):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_base_url_trailing_slash_stripped(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg(base_url="https://api.example.com/v1///")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = mock_resp
        _call_llm([{"role": "user", "content": "hi"}])
        url = mock_req.post.call_args.args[0]
        assert "//chat/completions" not in url
        assert url == "https://api.example.com/v1/chat/completions"


# ═══════════════════════════════════════════════════════════════
# 5. chat
# ═══════════════════════════════════════════════════════════════

class TestChat:

    @patch("app.services.ai_chat._call_llm")
    def test_parses_markdown_json_block(self, mock_call):
        mock_call.return_value = {"content": '```json\n{"answer":"A","confidence":0.9,"sources":["s1"]}\n```'}
        result = chat("问题")
        assert result["answer"] == "A"
        assert result["confidence"] == 0.9
        assert result["sources"] == ["s1"]

    @patch("app.services.ai_chat._call_llm")
    def test_parses_bare_json_object(self, mock_call):
        mock_call.return_value = {"content": '{"answer":"B","confidence":0.7,"actions":[{"label":"x"}]}'}
        result = chat("问题")
        assert result["answer"] == "B"
        assert result["actions"] == [{"label": "x"}]

    @patch("app.services.ai_chat._call_llm")
    def test_plain_text_falls_back_to_answer(self, mock_call):
        mock_call.return_value = {"content": "这是一段普通文本, 不含 JSON"}
        result = chat("问题")
        assert result["answer"] == "这是一段普通文本, 不含 JSON"
        assert result["confidence"] == 0.8

    @patch("app.services.ai_chat._call_llm")
    def test_malformed_json_falls_back(self, mock_call):
        # 含 { ... } 但中间非法 JSON → JSONDecodeError → fallback(except 分支)
        mock_call.return_value = {"content": "{bad} json trailing"}
        result = chat("问题")
        assert result["answer"] == "{bad} json trailing"
        assert result["confidence"] == 0.8

    @patch("app.services.ai_chat._call_llm")
    def test_llm_failure_returns_needs_human(self, mock_call):
        # API 超时/模型不可用 → 错误兜底
        mock_call.side_effect = Exception("service unavailable")
        result = chat("问题")
        assert result["needs_human"] is True
        assert result["confidence"] == 0
        assert result["sources"] == []
        assert result["actions"] == []
        assert "不可用" in result["answer"]

    @patch("app.services.ai_chat._call_llm")
    def test_stream_passes_through(self, mock_call):
        mock_call.return_value = {"stream": "resp_obj", "model": "m"}
        result = chat("问题", stream=True)
        assert result["stream"] == "resp_obj"

    @patch("app.services.ai_chat._call_llm")
    def test_history_appended_to_messages(self, mock_call):
        mock_call.return_value = {"content": '{"answer":"D"}'}
        chat("当前问题", history=[
            {"role": "user", "content": "历史问题1"},
            {"role": "assistant", "content": "历史回答1"},
        ])
        messages = mock_call.call_args.args[0]
        contents = [m["content"] for m in messages]
        assert "历史问题1" in contents
        assert "历史回答1" in contents
        # 当前问题在最后
        assert messages[-1] == {"role": "user", "content": "当前问题"}

    @patch("app.services.ai_chat._call_llm")
    def test_history_truncated_to_last_twenty(self, mock_call):
        mock_call.return_value = {"content": '{"answer":"D"}'}
        history = [{"role": "user", "content": f"msg{i}"} for i in range(25)]
        chat("问题", history=history)
        messages = mock_call.call_args.args[0]
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        # 历史 25 条被截到 20 + 当前 1 条 = 21 条 user
        assert len(user_msgs) == 21
        # 保留最近 20 条: msg5..msg24
        assert "msg4" not in user_msgs
        assert "msg5" in user_msgs
        assert "msg24" in user_msgs

    @patch("app.services.ai_chat._call_llm")
    def test_system_prompt_always_first(self, mock_call):
        mock_call.return_value = {"content": '{"answer":"D"}'}
        chat("问题")
        messages = mock_call.call_args.args[0]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    @patch("app.services.ai_chat._call_llm")
    def test_rag_injects_context_and_sources(self, mock_call, test_db):
        db = test_db["session"]
        _make_article(db, title="逆变器过温故障排查", content="检查散热风扇与滤网", team_id=0)
        # LLM 返回不含 sources, 应被 RAG sources 补充
        mock_call.return_value = {"content": '{"answer":"请检查散热"}'}

        result = chat("逆变器过温故障", db=db)

        messages = mock_call.call_args.args[0]
        joined = "\n".join(m["content"] for m in messages)
        assert "相关知识库文档" in joined
        assert "逆变器过温故障排查" in joined
        # sources 补充进 parsed(LLM 返回无 sources 字段)
        assert "逆变器过温故障排查" in result["sources"]

    @patch("app.services.ai_chat._call_llm")
    def test_rag_failure_does_not_break_chat(self, mock_call, test_db):
        # db 查询异常 → RAG 失败被吞, chat 仍正常返回
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        mock_call.return_value = {"content": '{"answer":"ok"}'}
        result = chat("逆变器故障", db=db)
        assert result["answer"] == "ok"

    @patch("app.services.ai_chat._query_knowledge_base", side_effect=RuntimeError("rag boom"))
    @patch("app.services.ai_chat._call_llm")
    def test_rag_query_exception_caught_at_chat_level(self, mock_call, mock_qkb, test_db):
        # _query_knowledge_base 直接抛异常(非内部吞) → chat 自身 except 兜底
        db = test_db["session"]
        mock_call.return_value = {"content": '{"answer":"ok"}'}
        result = chat("逆变器", db=db)
        assert result["answer"] == "ok"
        mock_qkb.assert_called_once()

    @patch("app.services.ai_chat._call_llm")
    def test_context_prompt_injected(self, mock_call):
        mock_call.return_value = {"content": '{"answer":"ok"}'}
        chat("问题", context={"page_type": "device_detail"})
        messages = mock_call.call_args.args[0]
        joined = "\n".join(m["content"] for m in messages if m["role"] == "system")
        assert "device_detail" in joined

    @patch("app.services.ai_chat._call_llm")
    def test_team_id_passed_to_rag(self, mock_call, test_db):
        db = test_db["session"]
        _make_article(db, title="企业10机密逆变器", content="机密", team_id=10)
        mock_call.return_value = {"content": '{"answer":"ok"}'}
        chat("逆变器", db=db, team_id=5)
        messages = mock_call.call_args.args[0]
        joined = "\n".join(m["content"] for m in messages)
        # team_id=5 不应见到 team_id=10 的文档
        assert "企业10机密逆变器" not in joined


# ═══════════════════════════════════════════════════════════════
# 6. stream_generator
# ═══════════════════════════════════════════════════════════════

class TestStreamGenerator:

    def _resp(self, lines):
        resp = MagicMock()
        resp.iter_lines.return_value = lines
        return resp

    def test_emits_chunks_and_done(self):
        resp = self._resp([
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" World"}}]}',
            'data: [DONE]',
            'data: {"choices":[{"delta":{"content":"after done"}}]}',
        ])
        out = [json.loads(c) for c in stream_generator(resp)]
        assert out[0] == {"type": "chunk", "content": "Hello"}
        assert out[1] == {"type": "chunk", "content": " World"}
        assert out[2] == {"type": "done"}
        # [DONE] 后 break, 不再处理
        assert len(out) == 3

    def test_skips_non_data_lines(self):
        resp = self._resp([
            '',  # 空行 → if line 跳过
            ': comment line',
            'not a data line',
        ])
        out = list(stream_generator(resp))
        assert out == []

    def test_skips_invalid_json_data(self):
        resp = self._resp([
            'data: not-valid-json',
            'data: [DONE]',
        ])
        out = [json.loads(c) for c in stream_generator(resp)]
        # 第一行 JSONDecodeError 被吞, 仅剩 done
        assert len(out) == 1
        assert out[0] == {"type": "done"}

    def test_logs_on_invalid_json_data(self, caplog):
        """可观测性契约: 无效JSON触发JSONDecodeError时, 静默except必须产出debug日志,
        不再零日志地吞掉异常 (卡8713759e)。"""
        resp = self._resp([
            'data: not-valid-json',
            'data: [DONE]',
        ])
        with caplog.at_level(logging.DEBUG, logger="app.services.ai_chat"):
            list(stream_generator(resp))
        assert any(
            rec.levelno == logging.DEBUG and "流式JSON" in rec.message
            for rec in caplog.records
        ), "无效JSON路径应产出debug日志, 不再静默吞异常"

    def test_skips_empty_delta_content(self):
        resp = self._resp([
            'data: {"choices":[{"delta":{}}]}',          # 无 content
            'data: {"choices":[]}',                       # 空 choices
            'data: {"choices":[{"delta":{"content":""}}]}',  # 空字符串 content
            'data: [DONE]',
        ])
        out = [json.loads(c) for c in stream_generator(resp)]
        # 仅 done, 空内容不输出
        assert out == [{"type": "done"}]


# ═══════════════════════════════════════════════════════════════
# 7. chat_stream
# ═══════════════════════════════════════════════════════════════

class TestChatStream:

    @patch("app.services.ai_chat.chat")
    def test_returns_stream_when_available(self, mock_chat):
        mock_chat.return_value = {"stream": "stream_obj"}
        result = chat_stream("msg")
        assert result == {"stream": "stream_obj"}
        mock_chat.assert_called_once()
        assert mock_chat.call_args.kwargs["stream"] is True

    @patch("app.services.ai_chat.chat")
    async def test_fallback_async_generator_when_no_stream(self, mock_chat):
        # chat 返回非流式(如错误兜底) → 包装成 async gen
        mock_chat.return_value = {"answer": "兜底回答"}
        gen = chat_stream("msg")
        chunks = [c async for c in gen]
        # 第一条 chunk 含 answer, 第二条 done
        parsed = [json.loads(c) for c in chunks]
        assert parsed[0] == {"type": "chunk", "content": "兜底回答"}
        assert parsed[1] == {"type": "done"}

    @patch("app.services.ai_chat.chat")
    async def test_fallback_empty_answer(self, mock_chat):
        mock_chat.return_value = {}
        gen = chat_stream("msg")
        parsed = [json.loads(c) async for c in gen]
        assert parsed[0]["content"] == ""
        assert parsed[1] == {"type": "done"}


# 防 linter 误报未使用
_ = datetime

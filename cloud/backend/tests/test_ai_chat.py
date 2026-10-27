"""
AI 对话服务 (app/services/ai_chat.py) 单元测试

被测: ai_chat 模块函数 —— team 隔离 / 知识库检索 / LLM 调用 / 上下文构建 /
      对话编排 / 流式生成。与 tests/services/test_ai_chat.py 独立、互补。
隔离: MagicMock/patch 隔离 model_manager / requests / _call_llm / _query_knowledge_base;
      知识库检索用 MagicMock db (不依赖真实 DB)。
覆盖: 正常路径 + 边界条件 + 异常处理。
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests as _real_requests
import socket as _socket

from app.core import url_safety as _url_safety

from app.models.knowledge import KnowledgeArticle
from app.services.ai_chat import (
    SYSTEM_PROMPT,
    _build_context_prompt,
    _call_llm,
    _query_knowledge_base,
    _team_scope,
    chat,
    chat_stream,
    stream_generator,
)


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════
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
    """一份完整的最小 model_config。"""
    base = {
        "base_url": "https://api.example.com/v1/",
        "api_key": "sk-test",
        "model_id": "test-model",
        "name": "TestProvider",
        "max_tokens": 4096,
    }
    base.update(over)
    return base


def _mock_db_for_kb(articles=None, faqs=None):
    """构造 mock db, 配置 team_id=0 时的 article/faq 查询链。

    article(team_id=0): db.query().filter(published).all()
    faq   (team_id=0):  db.query().all()
    """
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value.all.return_value = articles or []
    q.all.return_value = faqs or []
    return db


def _article(title="逆变器手册", content="逆变器维护指南", tags="逆变器", category="cat", aid=1):
    return SimpleNamespace(title=title, content=content, tags=tags, category=category, id=aid)


def _faq(question="如何重置逆变器?", answer="请参考手册", tags="逆变器", category="cat", fid=1):
    return SimpleNamespace(question=question, answer=answer, tags=tags, category=category, id=fid)


# ═══════════════════════════════════════════════════════════════════
# _team_scope
# ═══════════════════════════════════════════════════════════════════
class TestTeamScope:
    def test_zero_returns_none_no_filter(self):
        # team_id=0 (平台默认) → 不过滤, 见全部
        assert _team_scope(KnowledgeArticle, 0) is None

    def test_falsy_team_id_returns_none(self):
        assert _team_scope(KnowledgeArticle, None) is None

    def test_nonzero_returns_in_clause_with_team(self):
        clause = _team_scope(KnowledgeArticle, 7)
        assert clause is not None
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "IN" in compiled.upper()
        # 企业 7 仅可见 平台共享(0) + 本企业(7)
        assert "0" in compiled and "7" in compiled

    def test_other_team_excluded_from_clause(self):
        clause = _team_scope(KnowledgeArticle, 7)
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert " 10" not in compiled and "(10" not in compiled


# ═══════════════════════════════════════════════════════════════════
# _query_knowledge_base (mock db)
# ═══════════════════════════════════════════════════════════════════
class TestQueryKnowledgeBase:
    def test_empty_keywords_returns_empty(self):
        # 全标点/单字被过滤 → 无关键词
        assert _query_knowledge_base("？？？！！！", MagicMock()) == []
        assert _query_knowledge_base("电", MagicMock()) == []  # 单字丢弃

    def test_no_match_returns_empty(self):
        db = _mock_db_for_kb()
        assert _query_knowledge_base("完全不相关xyz", db) == []

    def test_article_match_returns_result(self):
        db = _mock_db_for_kb(articles=[_article()])
        results = _query_knowledge_base("逆变器", db)
        assert len(results) == 1
        assert results[0]["type"] == "article"
        assert results[0]["title"] == "逆变器手册"
        assert results[0]["id"] == 1

    def test_relevance_capped_at_one(self):
        # 标题+内容+标签全命中 → score 6 → relevance min(6/5,1) = 1.0
        db = _mock_db_for_kb(articles=[_article(title="逆变器", content="逆变器", tags="逆变器")])
        results = _query_knowledge_base("逆变器", db)
        assert results[0]["relevance"] == 1.0

    def test_long_content_truncated(self):
        long_body = "逆变器" + "x" * 3000
        db = _mock_db_for_kb(articles=[_article(content=long_body)])
        results = _query_knowledge_base("逆变器", db)
        assert len(results[0]["content"]) <= 2000

    def test_db_exception_swallowed_returns_empty(self):
        # 两个 try 块吞掉异常 → 最终返回 []
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert _query_knowledge_base("逆变器故障", db) == []

    def test_faq_match_returns_result(self):
        db = _mock_db_for_kb(faqs=[_faq()])
        results = _query_knowledge_base("逆变器", db)
        assert any(r["type"] == "faq" for r in results)

    def test_results_sorted_by_relevance_desc(self):
        art_low = _article(title="手册", content="逆变器", tags="", aid=1)   # score 1
        art_high = _article(title="逆变器", content="逆变器", tags="逆变器", aid=2)  # score 6
        db = _mock_db_for_kb(articles=[art_low, art_high])
        results = _query_knowledge_base("逆变器", db)
        assert results[0]["id"] == 2  # 高分在前


# ═══════════════════════════════════════════════════════════════════
# _build_context_prompt
# ═══════════════════════════════════════════════════════════════════
class TestBuildContextPrompt:
    def test_none_returns_empty(self):
        assert _build_context_prompt(None) == ""

    def test_empty_dict_returns_empty(self):
        assert _build_context_prompt({}) == ""

    def test_page_type(self):
        out = _build_context_prompt({"page_type": "device_detail"})
        assert "当前页面" in out and "device_detail" in out

    def test_device_block(self):
        out = _build_context_prompt({"device": {
            "name": "充电桩#1", "id": 42, "type": "DC", "status": "online", "station_name": "测试站",
        }})
        assert "充电桩#1" in out and "42" in out and "测试站" in out

    def test_station_block_default_health(self):
        out = _build_context_prompt({"station": {"name": "A站", "id": 1, "address": "北京"}})
        assert "A站" in out and "北京" in out and "N/A" in out

    def test_station_block_with_health(self):
        out = _build_context_prompt({"station": {"name": "A站", "id": 1, "health_score": 88}})
        assert "88" in out

    def test_alarms_block_uses_content(self):
        out = _build_context_prompt({"alarms": [{"content": "温度过高", "level": "warning"}]})
        assert "温度过高" in out and "1条" in out

    def test_alarms_block_falls_back_to_title(self):
        out = _build_context_prompt({"alarms": [{"title": "告警标题", "level": "critical"}]})
        assert "告警标题" in out

    def test_empty_alarms_skipped(self):
        out = _build_context_prompt({"alarms": []})
        assert "当前告警" not in out

    def test_workorder_block(self):
        out = _build_context_prompt({"workorder": {"title": "工单A", "id": 9, "status": "open", "priority": "high"}})
        assert "工单A" in out and "open" in out and "high" in out

    def test_extra_block_json(self):
        out = _build_context_prompt({"extra": {"k": "v"}})
        assert "额外" in out and '"k"' in out

    def test_full_context(self):
        out = _build_context_prompt({
            "page_type": "dashboard", "device": {"name": "D"}, "station": {"name": "S"},
            "alarms": [{"content": "A"}], "workorder": {"title": "W"}, "extra": {"x": 1},
        })
        for kw in ("当前页面", "设备", "站点", "当前告警", "工单", "额外"):
            assert kw in out


# ═══════════════════════════════════════════════════════════════════
# _call_llm
# ═══════════════════════════════════════════════════════════════════
class TestCallLLM:
    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_normal_non_stream(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_req.post.return_value = resp
        r = _call_llm([{"role": "user", "content": "hi"}])
        assert r["content"] == "hello"
        assert r["model"] == "test-model"
        assert r["provider"] == "TestProvider"
        assert r["usage"]["total_tokens"] == 15
        kwargs = mock_req.post.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
        assert kwargs["timeout"] == 120
        assert kwargs["json"]["stream"] is False

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_stream_returns_response(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        stream_resp = MagicMock()
        mock_req.post.return_value = stream_resp
        r = _call_llm([{"role": "user", "content": "hi"}], stream=True)
        assert r["stream"] is stream_resp
        assert mock_req.post.call_args.kwargs["stream"] is True

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
    def test_fallback_to_first_provider(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = None
        mock_mm.get_providers.return_value = [_cfg(model_id="fallback", name="FB")]
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_req.post.return_value = resp
        r = _call_llm([{"role": "user", "content": "hi"}])
        assert r["model"] == "fallback" and r["provider"] == "FB"

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_empty_choices_raises(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {"choices": []}
        mock_req.post.return_value = resp
        with pytest.raises(ValueError, match="LLM返回异常"):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_no_choices_key_raises(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {"unexpected": "shape"}
        mock_req.post.return_value = resp
        with pytest.raises(ValueError, match="LLM返回异常"):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_max_tokens_capped_by_config(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg(max_tokens=500)
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = resp
        _call_llm([{"role": "user", "content": "hi"}], max_tokens=4096)
        assert mock_req.post.call_args.kwargs["json"]["max_tokens"] == 500

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_usage_missing_defaults_zero(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = resp
        r = _call_llm([{"role": "user", "content": "hi"}])
        assert r["usage"]["total_tokens"] == 0

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_http_error_propagates(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.raise_for_status.side_effect = _real_requests.HTTPError("500")
        mock_req.post.return_value = resp
        with pytest.raises(_real_requests.HTTPError):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_content_none_falls_back_to_reasoning_content(self, mock_mm, mock_req):
        # reasoning 模型 content=None + reasoning_content 有值 → 返回 reasoning_content, 不抛
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning_content": "推理内容"}}]
        }
        mock_req.post.return_value = resp
        r = _call_llm([{"role": "user", "content": "hi"}])
        assert r["content"] == "推理内容"

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_both_content_and_reasoning_missing_raises(self, mock_mm, mock_req):
        # content 与 reasoning_content 均缺失/None → 明确 ValueError, 不再静默降级
        mock_mm.get_model_for_task.return_value = _cfg()
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": None}}]}
        mock_req.post.return_value = resp
        with pytest.raises(ValueError, match="LLM 返回空 content"):
            _call_llm([{"role": "user", "content": "hi"}])

    @patch("app.services.ai_chat._call_llm")
    def test_reasoning_only_response_not_silent_degraded(self, m):
        # chat 层: reasoning_content 兜底后正常返回 answer, 而非"服务暂时不可用"
        m.return_value = {"content": "仅推理内容"}
        r = chat("问题")
        assert r["answer"] == "仅推理内容"
        assert "不可用" not in r["answer"]

    @patch("app.services.ai_chat.requests")
    @patch("app.services.ai_chat.model_manager")
    def test_base_url_trailing_slash_stripped(self, mock_mm, mock_req):
        mock_mm.get_model_for_task.return_value = _cfg(base_url="https://api.example.com/v1///")
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
        mock_req.post.return_value = resp
        _call_llm([{"role": "user", "content": "hi"}])
        assert mock_req.post.call_args.args[0] == "https://api.example.com/v1/chat/completions"


# ═══════════════════════════════════════════════════════════════════
# chat
# ═══════════════════════════════════════════════════════════════════
class TestChat:
    @patch("app.services.ai_chat._call_llm")
    def test_parses_markdown_json_block(self, m):
        m.return_value = {"content": '```json\n{"answer":"A","confidence":0.9,"sources":["s1"]}\n```'}
        r = chat("问题")
        assert r["answer"] == "A" and r["confidence"] == 0.9 and r["sources"] == ["s1"]

    @patch("app.services.ai_chat._call_llm")
    def test_parses_bare_json_object(self, m):
        m.return_value = {"content": '{"answer":"B","actions":[{"label":"x"}]}'}
        r = chat("问题")
        assert r["answer"] == "B" and r["actions"] == [{"label": "x"}]

    @patch("app.services.ai_chat._call_llm")
    def test_plain_text_falls_back(self, m):
        m.return_value = {"content": "这是一段普通文本"}
        r = chat("问题")
        assert r["answer"] == "这是一段普通文本" and r["confidence"] == 0.8

    @patch("app.services.ai_chat._call_llm")
    def test_malformed_json_falls_back(self, m):
        m.return_value = {"content": "{bad} json"}
        r = chat("问题")
        assert r["confidence"] == 0.8

    @patch("app.services.ai_chat._call_llm")
    def test_llm_failure_returns_needs_human(self, m):
        m.side_effect = RuntimeError("service unavailable")
        r = chat("问题")
        assert r["needs_human"] is True
        assert r["confidence"] == 0
        assert r["sources"] == [] and r["actions"] == []
        assert "不可用" in r["answer"]

    @patch("app.services.ai_chat._call_llm")
    def test_stream_passes_through(self, m):
        m.return_value = {"stream": "resp_obj", "model": "m"}
        assert chat("问题", stream=True)["stream"] == "resp_obj"

    @patch("app.services.ai_chat._call_llm")
    def test_system_prompt_always_first(self, m):
        m.return_value = {"content": '{"answer":"D"}'}
        chat("问题")
        msgs = m.call_args.args[0]
        assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}

    @patch("app.services.ai_chat._call_llm")
    def test_current_question_is_last(self, m):
        m.return_value = {"content": '{"answer":"D"}'}
        chat("当前问题")
        msgs = m.call_args.args[0]
        assert msgs[-1] == {"role": "user", "content": "当前问题"}

    @patch("app.services.ai_chat._call_llm")
    def test_history_appended(self, m):
        m.return_value = {"content": '{"answer":"D"}'}
        chat("当前问题", history=[
            {"role": "user", "content": "历史问题"},
            {"role": "assistant", "content": "历史回答"},
        ])
        contents = [x["content"] for x in m.call_args.args[0]]
        assert "历史问题" in contents and "历史回答" in contents

    @patch("app.services.ai_chat._call_llm")
    def test_history_truncated_to_last_twenty(self, m):
        m.return_value = {"content": '{"answer":"D"}'}
        history = [{"role": "user", "content": f"msg{i}"} for i in range(25)]
        chat("问题", history=history)
        user_msgs = [x for x in m.call_args.args[0] if x["role"] == "user"]
        # 历史 25 → 截到 20 + 当前 1 = 21
        assert len(user_msgs) == 21
        assert "msg5" in [x["content"] for x in user_msgs]
        assert "msg4" not in [x["content"] for x in user_msgs]

    @patch("app.services.ai_chat._query_knowledge_base")
    @patch("app.services.ai_chat._call_llm")
    def test_rag_injects_context_and_sources(self, m_call, m_qkb):
        m_qkb.return_value = [{"type": "article", "title": "逆变器手册", "content": "检查风扇", "relevance": 0.9}]
        m_call.return_value = {"content": '{"answer":"请检查散热"}'}
        r = chat("逆变器过温", db=MagicMock())
        msgs = m_call.call_args.args[0]
        joined = "\n".join(x["content"] for x in msgs)
        assert "相关知识库文档" in joined and "逆变器手册" in joined
        # LLM 返回无 sources → 用 RAG sources 补充
        assert "逆变器手册" in r["sources"]

    @patch("app.services.ai_chat._query_knowledge_base")
    @patch("app.services.ai_chat._call_llm")
    def test_rag_failure_does_not_break_chat(self, m_call, m_qkb):
        # _query_knowledge_base 抛异常 → chat 自身 except 兜底, 不影响主流程
        m_qkb.side_effect = RuntimeError("rag boom")
        m_call.return_value = {"content": '{"answer":"ok"}'}
        r = chat("逆变器故障", db=MagicMock())
        assert r["answer"] == "ok"
        m_qkb.assert_called_once()

    @patch("app.services.ai_chat._call_llm")
    def test_context_prompt_injected(self, m):
        m.return_value = {"content": '{"answer":"ok"}'}
        chat("问题", context={"page_type": "device_detail"})
        joined = "\n".join(x["content"] for x in m.call_args.args[0] if x["role"] == "system")
        assert "device_detail" in joined

    @patch("app.services.ai_chat._call_llm")
    def test_preserves_llm_sources_when_present(self, m):
        # LLM 已返回 sources → RAG sources 不覆盖
        m.return_value = {"content": '{"answer":"A","sources":["llm_src"]}'}
        r = chat("问题")
        assert r["sources"] == ["llm_src"]


# ═══════════════════════════════════════════════════════════════════
# stream_generator
# ═══════════════════════════════════════════════════════════════════
class TestStreamGenerator:
    def _resp(self, lines):
        r = MagicMock()
        r.iter_lines.return_value = lines
        return r

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
        assert len(out) == 3  # [DONE] 后 break

    def test_skips_non_data_lines(self):
        resp = self._resp(["", ": comment", "not a data line"])
        assert list(stream_generator(resp)) == []

    def test_skips_invalid_json_data(self):
        resp = self._resp(['data: not-valid-json', 'data: [DONE]'])
        out = [json.loads(c) for c in stream_generator(resp)]
        assert len(out) == 1 and out[0]["type"] == "done"

    def test_skips_empty_delta_content(self):
        resp = self._resp([
            'data: {"choices":[{"delta":{}}]}',
            'data: {"choices":[]}',
            'data: {"choices":[{"delta":{"content":""}}]}',
            'data: [DONE]',
        ])
        out = [json.loads(c) for c in stream_generator(resp)]
        assert out == [{"type": "done"}]

    def test_reasoning_only_delta_yields_chunk(self):
        # 流式 reasoning 模型: delta 只有 reasoning_content 无 content → 仍应产出 chunk
        resp = self._resp([
            'data: {"choices":[{"delta":{"reasoning_content":"思考中"}}]}',
            'data: {"choices":[{"delta":{"content":"答案"}}]}',
            'data: [DONE]',
        ])
        out = [json.loads(c) for c in stream_generator(resp)]
        assert out[0] == {"type": "chunk", "content": "思考中"}
        assert out[1] == {"type": "chunk", "content": "答案"}
        assert out[2] == {"type": "done"}


# ═══════════════════════════════════════════════════════════════════
# chat_stream
# ═══════════════════════════════════════════════════════════════════
class TestChatStream:
    @patch("app.services.ai_chat.chat")
    def test_returns_stream_when_available(self, m):
        m.return_value = {"stream": "stream_obj"}
        assert chat_stream("msg") == {"stream": "stream_obj"}
        assert m.call_args.kwargs["stream"] is True

    @patch("app.services.ai_chat.chat")
    async def test_fallback_async_generator_when_no_stream(self, m):
        m.return_value = {"answer": "兜底回答"}
        gen = chat_stream("msg")
        parsed = [json.loads(c) async for c in gen]
        assert parsed[0] == {"type": "chunk", "content": "兜底回答"}
        assert parsed[1] == {"type": "done"}

    @patch("app.services.ai_chat.chat")
    async def test_fallback_empty_answer(self, m):
        m.return_value = {}
        gen = chat_stream("msg")
        parsed = [json.loads(c) async for c in gen]
        assert parsed[0]["content"] == ""
        assert parsed[1]["type"] == "done"

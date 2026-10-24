"""
AI 通用对话服务 - 支持运维问答、数据查询、操作指导
RAG集成知识库（设备手册/运维文档/FAQ）
上下文注入 + 可插拔语音架构

丁哥要求:
1. STT/TTS不在天链服务器(1.6G内存)上跑语音模型
2. 可插拔架构: 浏览器Web Speech API + 自定义云端API(云服务商/服务商B云/服务商D)
3. 复用现有AI模型配置(app/services/ai_model_config.py)
"""
import json
import logging
import re
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from app.services.ai_model_config import model_manager
from app.core.url_safety import UnsafeURLError, validate_external_url
from app.models.knowledge import KnowledgeArticle, KnowledgeFAQ

logger = logging.getLogger(__name__)

# ========== 系统 Prompt ==========

SYSTEM_PROMPT = """你是一位资深的光储充运维专家助手"天链助手"，用中文回答运维问题。

## 你的能力
1. **运维问答** - 回答设备故障、配置、维护相关问题
2. **数据查询** - 查询设备状态、告警信息、站点概况
3. **操作指导** - 给出排查步骤、修复建议、预防措施
4. **知识问答** - 基于知识库回答设备手册、运维指南问题

## 回答风格
- 简洁明了，分步骤说明
- 基于提供的上下文和数据，不确定时说明"根据现有信息"
- 涉及操作时注安全注意事项
- 使用Markdown格式（列表、代码块、表格）

## 返回格式
以JSON格式返回（不要用markdown代码块包裹）：
```json
{
  "answer": "回答内容（支持Markdown）",
  "confidence": 0.95,
  "sources": ["来源1", "来源2"],
  "actions": [{"label": "查看设备", "url": "/devices/123"}],
  "needs_human": false
}
```
"""


def _team_scope(model, team_id: int):
    """返回按 team 隔离的过滤条件; team_id=0(平台默认)返回 None 表示不过滤(见全部)。

    杜绝天链助手跨账户(企业)数据泄露: 企业 team 仅可见 平台共享(team_id=0) + 本企业(team_id=自身)。
    """
    if not team_id:
        return None
    return model.team_id.in_([0, team_id])


def _query_knowledge_base(query: str, db: Session, top_k: int = 3, team_id: int = 0) -> List[Dict]:
    """
    从知识库检索相关文档（简单关键词匹配 + 向量搜索占位）

    支持:
    - KnowledgeArticle: 知识文章（设备手册/运维文档）
    - KnowledgeFAQ: FAQ问题库
    """
    results = []
    keywords = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', ' ', query).strip().split()
    keywords = [k for k in keywords if len(k) > 1]

    if not keywords:
        return results

    # 1. 搜索知识文章（按 team_id 隔离）
    try:
        art_q = db.query(KnowledgeArticle).filter(KnowledgeArticle.published == True)
        art_scope = _team_scope(KnowledgeArticle, team_id)
        if art_scope is not None:
            art_q = art_q.filter(art_scope)
        articles = art_q.all()

        scored_articles = []
        for art in articles:
            score = 0
            title_lower = (art.title or "").lower()
            content_lower = (art.content or "").lower()
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in title_lower:
                    score += 3
                if kw_lower in content_lower:
                    score += 1
                # 标签匹配加分
                if art.tags and kw_lower in art.tags.lower():
                    score += 2
            if score > 0 and len(scored_articles) < top_k * 2:
                scored_articles.append((score, art))

        scored_articles.sort(key=lambda x: -x[0])
        for score, art in scored_articles[:top_k]:
            results.append({
                "type": "article",
                "title": art.title,
                "content": art.content[:2000],  # 截断长文本
                "category": art.category,
                "relevance": round(min(score / 5, 1.0), 2),
                "id": art.id
            })
    except Exception as e:
        logger.warning("知识文章检索异常: %s", e)

    # 2. 搜索FAQ（按 team_id 隔离）
    try:
        faq_q = db.query(KnowledgeFAQ)
        faq_scope = _team_scope(KnowledgeFAQ, team_id)
        if faq_scope is not None:
            faq_q = faq_q.filter(faq_scope)
        faqs = faq_q.all()
        scored_faqs = []
        for faq in faqs:
            score = 0
            question_lower = (faq.question or "").lower()
            answer_lower = (faq.answer or "").lower()
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in question_lower:
                    score += 4
                if kw_lower in answer_lower:
                    score += 1
                if faq.tags and kw_lower in faq.tags.lower():
                    score += 2
            if score > 0:
                scored_faqs.append((score, faq))

        scored_faqs.sort(key=lambda x: -x[0])
        for score, faq in scored_faqs[:top_k]:
            results.append({
                "type": "faq",
                "title": faq.question,
                "content": faq.answer[:1000],
                "category": faq.category,
                "relevance": round(min(score / 5, 1.0), 2),
                "id": faq.id
            })
    except Exception as e:
        logger.warning("FAQ检索异常: %s", e)

    # 按相关性排序
    results.sort(key=lambda x: -x["relevance"])
    return results[:top_k]


def _call_llm(
    messages: List[Dict],
    temperature: float = 0.5,
    max_tokens: int = 4096,
    stream: bool = False
) -> Dict:
    """
    调用AI模型（复用现有ai_model_config配置）

    支持所有已配置的provider:
    - cloud_provider-token (llm-pro-a/flash, llm-b, model_d-k2.6, llm-pro-c)
    """
    model_config = model_manager.get_model_for_task("chat_general")
    if not model_config:
        # fallback: 取第一个启用的provider
        providers = model_manager.get_providers()
        if not providers:
            raise ValueError("没有可用的AI模型配置")
        model_config = providers[0]

    try:
        validate_external_url(model_config['base_url'])
    except UnsafeURLError:
        raise ValueError("AI模型 base_url 不安全(内网/环回/非 http(s)), 拒绝出站请求")
    url = f"{model_config['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model_config['api_key']}"
    }
    payload = {
        "model": model_config["model_id"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": min(max_tokens, model_config.get("max_tokens", 4096)),
        "stream": stream
    }

    logger.info("调用AI模型: %s (%s)", model_config.get("name"), model_config["model_id"])

    if stream:
        # 流式返回
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
        response.raise_for_status()
        return {"stream": response, "model": model_config["model_id"], "provider": model_config.get("name")}

    response = requests.post(url, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    data = response.json()

    if "choices" in data and len(data["choices"]) > 0:
        # reasoning 模型(model_a-reasoner等)可能只返回 reasoning_content 而 content=None
        message = data["choices"][0].get("message", {}) or {}
        content = message.get("content") or message.get("reasoning_content") or ""
        if not content:
            raise ValueError("LLM 返回空 content")
        usage = data.get("usage", {})
        return {
            "content": content,
            "model": model_config["model_id"],
            "provider": model_config.get("name"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }
        }

    raise ValueError(f"LLM返回异常: {json.dumps(data, ensure_ascii=False)[:500]}")


def _build_context_prompt(context: Optional[Dict] = None) -> str:
    """构建上下文提示"""
    if not context:
        return ""

    parts = ["## 当前页面上下文"]
    page_type = context.get("page_type", "")

    if page_type:
        parts.append(f"- 当前页面: {page_type}")

    if context.get("device"):
        d = context["device"]
        parts.append(f"- 设备: {d.get('name', '')}(ID:{d.get('id', '')}) 类型:{d.get('type', '')} 状态:{d.get('status', '')} 站点:{d.get('station_name', '')}")

    if context.get("station"):
        s = context["station"]
        parts.append(f"- 站点: {s.get('name', '')}(ID:{s.get('id', '')}) 地址:{s.get('address', '')} 健康度:{s.get('health_score', 'N/A')}")

    if context.get("alarms") and len(context["alarms"]) > 0:
        alarms = context["alarms"]
        parts.append(f"- 当前告警({len(alarms)}条): 最新: {alarms[0].get('content', alarms[0].get('title', 'N/A'))} 等级:{alarms[0].get('level', 'N/A')}")

    if context.get("workorder"):
        w = context["workorder"]
        parts.append(f"- 工单: {w.get('title', '')}(#{w.get('id', '')}) 状态:{w.get('status', '')} 优先级:{w.get('priority', '')}")

    if context.get("extra"):
        parts.append(f"- 额外: {json.dumps(context['extra'], ensure_ascii=False)}")

    return "\n".join(parts)


def chat(
    message: str,
    history: Optional[List[Dict]] = None,
    context: Optional[Dict] = None,
    db: Optional[Session] = None,
    stream: bool = False,
    team_id: int = 0
) -> Dict:
    """
    通用对话入口

    Args:
        message: 用户消息
        history: 对话历史 [{"role":"user"/"assistant","content":"..."}]
        context: 页面上下文 {page_type, device, station, alarms, workorder, extra}
        db: 数据库Session（用于RAG检索）
        stream: 是否流式返回

    Returns:
        对话结果 dict {answer, confidence, sources, actions, needs_human}
        或流式 response
    """
    # 1. RAG: 从知识库检索相关文档
    rag_context = ""
    sources = []
    if db:
        try:
            kb_results = _query_knowledge_base(message, db, team_id=team_id)
            if kb_results:
                rag_parts = ["\n## 相关知识库文档"]
                for r in kb_results:
                    rag_parts.append(f"\n### [{r['type']}] {r['title']} (相关度:{r['relevance']})")
                    rag_parts.append(r['content'][:500] + "...")
                    sources.append(r['title'])
                rag_context = "\n".join(rag_parts)
        except Exception as e:
            logger.warning("RAG检索失败: %s", e)

    # 2. 构建页面上下文
    page_context = _build_context_prompt(context)

    # 3. 构建 messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 添加上下文
    context_parts = []
    if rag_context:
        context_parts.append(rag_context)
    if page_context:
        context_parts.append(page_context)
    if context_parts:
        messages.append({
            "role": "system",
            "content": "## 以下是为本次对话提供的参考信息\n\n" + "\n\n".join(context_parts)
        })

    # 添加对话历史
    if history:
        for h in history[-20:]:  # 保留最近20轮
            messages.append(h)

    # 添加当前问题
    messages.append({"role": "user", "content": message})

    # 4. 调用LLM
    try:
        result = _call_llm(messages, stream=stream)

        if stream:
            return result  # 流式响应对象

        content = result["content"]

        # 尝试解析JSON响应
        try:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if json_match:
                parsed = json.loads(json_match.group(1).strip())
            else:
                # 直接尝试找JSON对象
                start = content.find('{')
                end = content.rfind('}')
                if start >= 0 and end > start:
                    parsed = json.loads(content[start:end+1])
                else:
                    parsed = {"answer": content, "confidence": 0.8}
        except json.JSONDecodeError:
            parsed = {"answer": content, "confidence": 0.8}

        # 补充sources
        if sources and "sources" not in parsed:
            parsed["sources"] = sources

        return parsed

    except Exception as e:
        logger.error("对话调用失败: %s", e)
        return {
            "answer": "抱歉，对话服务暂时不可用，请稍后重试",
            "confidence": 0,
            "sources": [],
            "actions": [],
            "needs_human": True
        }


def stream_generator(response_iter):
    """流式响应生成器（用于SSE）"""
    for line in response_iter.iter_lines(decode_unicode=True):
        if line:
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    yield json.dumps({"type": "done"}) + "\n"
                    break
                try:
                    data = json.loads(data_str)
                    if "choices" in data and len(data["choices"]) > 0:
                        delta = data["choices"][0].get("delta", {})
                        # 流式 reasoning 模型首段可能只有 reasoning_content 而 content 为空
                        content = delta.get("content") or delta.get("reasoning_content") or ""
                        if content:
                            yield json.dumps({"type": "chunk", "content": content}) + "\n"
                except json.JSONDecodeError:
                    logger.debug("流式JSON解析跳过", exc_info=True)


def chat_stream(message, history=None, context=None, db=None, team_id=0):
    """流式对话"""
    result = chat(message, history, context, db, stream=True, team_id=team_id)
    if "stream" in result:
        return result
    # fallback: 非流式结果包装成流
    async def gen():
        ans = result.get("answer", "")
        yield json.dumps({"type": "chunk", "content": ans}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
    return gen()
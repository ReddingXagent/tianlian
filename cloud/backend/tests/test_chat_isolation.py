"""
天链助手 - 账户数据隔离测试

验证:
- /chat 端点强制鉴权 (无 token / 无效 token -> 401)
- team_id 服务端强制取 current_user.team_id；伪造 X-Team-Id 不得越权

向后兼容约定: team_id=0 为平台默认, 可见全部内容;
非 0 的企业 team_id 仅可见 平台共享(team_id=0) + 本企业(team_id=自身) 内容。
"""
import pytest


# ============ 鉴权辅助 ============

def _login_token(client, username="admin", password="admin123"):
    """通过 /auth/login 换取真实 JWT (依赖 seed_users 注入的 admin)"""
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _auth_headers(client, **extra):
    """构造带 Bearer token 的请求头"""
    h = {"Authorization": f"Bearer {_login_token(client)}"}
    h.update(extra)
    return h


# ============ 用例 ============

def test_chat_no_token_returns_401(anon_client, seed_users):
    """无 Authorization header -> 401 (禁止匿名调用 /chat)"""
    resp = anon_client.post("/api/v1/chat", json={"message": "充电桩故障如何排查?"})
    assert resp.status_code == 401


def test_chat_invalid_token_returns_401(client, seed_users):
    """无效 JWT -> 401"""
    resp = client.post(
        "/api/v1/chat",
        json={"message": "充电桩故障如何排查?"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


def test_chat_filters_by_user_team_not_header(client, seed_users, monkeypatch):
    """team_id 服务端强制取 current_user.team_id；伪造 X-Team-Id 不得越权。

    任务卡 708350b3：原实现 ``_get_team_id(x_team_id) or current_user.team_id``
    使客户端 header 优先于服务端身份 → 攻击者伪造 X-Team-Id 即可读取任意团队
    知识库。修复后 header 一律忽略，仅按登录身份隔离。
    """
    import bcrypt
    from app.models.user import User, UserRole, Team
    from app.models.knowledge import KnowledgeArticle
    from app.services.ai_chat import _query_knowledge_base

    s = client._sesh
    # 两团队 + 团队A 用户
    ta = Team(name="Chat团队A", code="CTA1")
    tb = Team(name="Chat团队B", code="CTB1")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "ct123456"
    ua = User(
        username="ct_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(ua)
    s.commit()

    # 三篇不同归属的知识文章 (title 均含关键词 "充电桩故障")
    articles = [
        KnowledgeArticle(title="公共文档-充电桩故障", content="平台共享的充电桩故障说明",
                         published=True, team_id=0),
        KnowledgeArticle(title="团队A-充电桩故障", content="团队A专属的充电桩故障说明",
                         published=True, team_id=ta.id),
        KnowledgeArticle(title="团队B-充电桩故障", content="团队B专属的充电桩故障说明",
                         published=True, team_id=tb.id),
    ]
    s.add_all(articles)
    s.commit()

    # 屏蔽外部 LLM 调用, 让 chat() 走 RAG 检索 + 纯文本回退
    monkeypatch.setattr(
        "app.services.ai_chat._call_llm",
        lambda *a, **k: {"content": "ok"},
    )

    token = _login_token(client, "ct_eng_a", pwd)

    # A 用户故意伪造 X-Team-Id = B 的 team → 仍只能看 公共(0) + A，看不到 B
    resp = client.post(
        "/api/v1/chat",
        json={"message": "充电桩故障"},
        headers={"Authorization": f"Bearer {token}", "X-Team-Id": str(tb.id)},
    )
    assert resp.status_code == 200, resp.text
    sources = resp.json()["data"]["sources"]
    assert any("公共" in src for src in sources), f"应可见平台共享文档, sources={sources}"
    assert any("团队A" in src for src in sources), f"应可见本团队文档, sources={sources}"
    assert not any("团队B" in src for src in sources), f"伪造 X-Team-Id 不得越权看 B, sources={sources}"

    # 平台默认(team_id=0) service 层仍可见全部
    results_all = _query_knowledge_base("充电桩故障", s, team_id=0)
    titles_all = [r["title"] for r in results_all]
    assert len(titles_all) == 3, f"平台默认应见全部, 实际={titles_all}"

"""知识库文章端点测试 — app/api/v1/knowledge/articles.py

覆盖：list / get / create / update / delete
维度：正常路径 × 分页&过滤&搜索 × team scoping × view_count 自增 × CRUD 404 × 匿名401 × viewer写403
"""
import pytest

from tests.api._helpers import KB_URL, login_as
from app.models.knowledge import KnowledgeArticle

ARTICLES = KB_URL + "/articles"


def _seed_article(session, *, title="种子文章", content="内容", category="general",
                  team_id=0, published=True):
    a = KnowledgeArticle(
        title=title, content=content, category=category,
        team_id=team_id, published=published,
    )
    session.add(a)
    session.commit()
    return a.id


class TestList:
    def test_list_empty(self, client):
        r = client.get(ARTICLES)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_list_with_data(self, client, db_session):
        _seed_article(db_session, title="A1")
        r = client.get(ARTICLES)
        assert r.json()["data"]["total"] == 1
        assert r.json()["data"]["items"][0]["title"] == "A1"

    def test_list_filter_category(self, client, db_session):
        _seed_article(db_session, title="X", category="设备类")
        _seed_article(db_session, title="Y", category="告警类")
        r = client.get(ARTICLES, params={"category": "设备类"})
        assert r.json()["data"]["total"] == 1

    def test_list_search(self, client, db_session):
        _seed_article(db_session, title="逆变器维修指南", content="正文")
        _seed_article(db_session, title="其他", content="无关")
        r = client.get(ARTICLES, params={"search": "逆变器"})
        assert r.json()["data"]["total"] == 1

    def test_list_pagination_invalid(self, client):
        r = client.get(ARTICLES, params={"page": 0})
        assert r.status_code == 422

    def test_list_team_scoped(self, client, db_session, seed_users):
        """非 admin 仅见 team_id in (0, own)"""
        _seed_article(db_session, title="共享", team_id=0)
        _seed_article(db_session, title="本团", team_id=5)
        _seed_article(db_session, title="他团", team_id=999)
        seed_users["engineer1"].team_id = 5
        db_session.commit()
        login_as(client, "engineer1", "eng123")
        r = client.get(ARTICLES)
        titles = {it["title"] for it in r.json()["data"]["items"]}
        assert titles == {"共享", "本团"}


class TestGet:
    def test_get_ok_increments_views(self, client, db_session):
        aid = _seed_article(db_session)
        r1 = client.get(f"{ARTICLES}/{aid}")
        assert r1.status_code == 200
        assert r1.json()["data"]["view_count"] == 1
        r2 = client.get(f"{ARTICLES}/{aid}")
        assert r2.json()["data"]["view_count"] == 2

    def test_get_not_found(self, client):
        r = client.get(f"{ARTICLES}/99999")
        assert r.status_code == 404

    def test_get_cross_team_404(self, client, db_session, seed_users):
        aid = _seed_article(db_session, team_id=999)
        seed_users["engineer1"].team_id = 5
        db_session.commit()
        login_as(client, "engineer1", "eng123")
        r = client.get(f"{ARTICLES}/{aid}")
        assert r.status_code == 404


class TestCreate:
    def test_create_ok(self, client):
        r = client.post(ARTICLES, json={
            "title": "新文章", "content": "正文", "category": "general", "tags": "a,b",
        })
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "新文章"
        assert r.json()["message"] == "文章创建成功"

    def test_create_missing_title(self, client):
        r = client.post(ARTICLES, json={"content": "正文"})
        assert r.status_code == 422

    def test_create_missing_content(self, client):
        r = client.post(ARTICLES, json={"title": "T"})
        assert r.status_code == 422

    def test_create_default_category(self, client):
        """不传 category → 默认 general"""
        r = client.post(ARTICLES, json={"title": "T", "content": "C"})
        assert r.status_code == 200
        assert r.json()["data"]["category"] == "general"


class TestUpdate:
    def test_update_ok(self, client, db_session):
        aid = _seed_article(db_session, title="旧")
        r = client.put(f"{ARTICLES}/{aid}", json={"title": "新", "published": False})
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "新"

    def test_update_not_found(self, client):
        r = client.put(f"{ARTICLES}/99999", json={"title": "x"})
        assert r.status_code == 404


class TestDelete:
    def test_delete_ok(self, client, db_session):
        aid = _seed_article(db_session)
        r = client.delete(f"{ARTICLES}/{aid}")
        assert r.status_code == 200
        assert client.get(f"{ARTICLES}/{aid}").status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete(f"{ARTICLES}/99999")
        assert r.status_code == 404


class TestAuth:
    def test_anon_denied(self, anon_client):
        r = anon_client.get(ARTICLES)
        assert r.status_code == 401

    def test_viewer_write_forbidden(self, client, seed_users):
        """viewer 无 knowledge:manage 写权限 → 403"""
        seed_users
        login_as(client, "viewer1", "view123")
        r = client.post(ARTICLES, json={"title": "T", "content": "C"})
        assert r.status_code == 403

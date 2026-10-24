"""知识库 FAQ 端点测试 — app/api/v1/knowledge/faq.py

覆盖：list / create / batch-import / helpful / categories
维度：正常路径 × 过滤&搜索 × team scoping × helpful 自增 × 404 × 匿名401 × viewer写403
"""
import pytest

from tests.api._helpers import KB_URL, login_as
from app.models.knowledge import KnowledgeFAQ

FAQ = KB_URL + "/faq"


def _seed_faq(session, *, question="Q?", answer="A.", category="设备类",
              team_id=0, views=0, helpful_count=0):
    f = KnowledgeFAQ(
        question=question, answer=answer, category=category,
        team_id=team_id, views=views, helpful_count=helpful_count,
    )
    session.add(f)
    session.commit()
    return f.id


class TestList:
    def test_list_empty(self, client):
        r = client.get(FAQ)
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_with_data(self, client, db_session):
        _seed_faq(db_session, question="怎么处理？")
        r = client.get(FAQ)
        assert len(r.json()["data"]) == 1
        assert r.json()["data"][0]["question"] == "怎么处理？"

    def test_list_filter_category(self, client, db_session):
        _seed_faq(db_session, category="设备类")
        _seed_faq(db_session, category="告警类", question="Q2?")
        r = client.get(FAQ, params={"category": "告警类"})
        assert len(r.json()["data"]) == 1

    def test_list_search(self, client, db_session):
        _seed_faq(db_session, question="逆变器报警怎么办", answer="重启")
        _seed_faq(db_session, question="其他", answer="无关")
        r = client.get(FAQ, params={"q": "逆变器"})
        assert len(r.json()["data"]) == 1

    def test_list_team_scoped(self, client, db_session, seed_users):
        _seed_faq(db_session, question="共享", team_id=0)
        _seed_faq(db_session, question="本团", team_id=5)
        _seed_faq(db_session, question="他团", team_id=999)
        seed_users["engineer1"].team_id = 5
        db_session.commit()
        login_as(client, "engineer1", "eng123")
        r = client.get(FAQ)
        qs = {it["question"] for it in r.json()["data"]}
        assert qs == {"共享", "本团"}


class TestCreate:
    def test_create_ok(self, client):
        r = client.post(FAQ, json={
            "question": "Q?", "answer": "A.", "category": "设备类", "tags": ["a", "b"],
        })
        assert r.status_code == 200
        assert r.json()["data"]["tags"] == "a,b"  # list → 逗号串
        assert r.json()["message"] == "FAQ创建成功"

    def test_create_missing_question(self, client):
        r = client.post(FAQ, json={"answer": "A.", "category": "c"})
        assert r.status_code == 422

    def test_create_missing_answer(self, client):
        r = client.post(FAQ, json={"question": "Q?", "category": "c"})
        assert r.status_code == 422


class TestBatchImport:
    def test_batch_import_ok(self, client):
        r = client.post(f"{FAQ}/batch-import", json={"faqs": [
            {"question": "Q1?", "answer": "A1.", "category": "设备类"},
            {"question": "Q2?", "answer": "A2.", "category": "告警类", "tags": ["x"]},
        ]})
        assert r.status_code == 200
        assert r.json()["data"]["imported_count"] == 2
        assert len(r.json()["data"]["items"]) == 2

    def test_batch_import_empty(self, client):
        """空列表 → 导入 0"""
        r = client.post(f"{FAQ}/batch-import", json={"faqs": []})
        assert r.status_code == 200
        assert r.json()["data"]["imported_count"] == 0

    def test_batch_import_invalid_item(self, client):
        """某项缺 question → 422"""
        r = client.post(f"{FAQ}/batch-import", json={"faqs": [
            {"answer": "A.", "category": "c"},
        ]})
        assert r.status_code == 422


class TestHelpful:
    def test_helpful_ok(self, client, db_session):
        fid = _seed_faq(db_session, helpful_count=2)
        r = client.put(f"{FAQ}/{fid}/helpful")
        assert r.status_code == 200
        assert r.json()["data"]["helpful_count"] == 3

    def test_helpful_not_found(self, client):
        r = client.put(f"{FAQ}/99999/helpful")
        assert r.status_code == 404

    def test_helpful_cross_team_404(self, client, db_session, seed_users):
        fid = _seed_faq(db_session, team_id=999)
        seed_users["engineer1"].team_id = 5
        db_session.commit()
        login_as(client, "engineer1", "eng123")
        r = client.put(f"{FAQ}/{fid}/helpful")
        assert r.status_code == 404


class TestCategories:
    def test_categories_ok(self, client, db_session):
        _seed_faq(db_session, category="设备类")
        _seed_faq(db_session, category="告警类")
        _seed_faq(db_session, category="设备类")
        r = client.get(f"{FAQ}/categories")
        assert r.status_code == 200
        cats = set(r.json()["data"])
        assert cats == {"设备类", "告警类"}

    def test_categories_empty(self, client):
        r = client.get(f"{FAQ}/categories")
        assert r.status_code == 200
        assert r.json()["data"] == []


class TestAuth:
    def test_anon_denied(self, anon_client):
        r = anon_client.get(FAQ)
        assert r.status_code == 401

    def test_viewer_write_forbidden(self, client, seed_users):
        """viewer 无 knowledge:manage 写权限 → 403"""
        seed_users
        login_as(client, "viewer1", "view123")
        r = client.post(FAQ, json={"question": "Q?", "answer": "A.", "category": "c"})
        assert r.status_code == 403

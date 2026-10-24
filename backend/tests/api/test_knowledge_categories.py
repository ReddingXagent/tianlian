"""知识库分类 CRUD API 测试 (app/api/v1/knowledge/categories.py, 卡 96f676b3)

覆盖端点 (前缀 /api/v1/knowledge):
- GET    /categories            列表 (含 article_count, 按 sort_order 排序)
- POST   /categories            创建 (Query 参数; 重名 → 400)
- PUT    /categories/{id}       更新 (不存在 → 404; 重名冲突 → 400)
- DELETE /categories/{id}       删除 (不存在 → 404; 有关联文章 → 400)
- GET    /categories/list       旧版兼容路由

覆盖维度:
(a) 正常路径: CRUD 各端点字段正确 + 排序
(b) 边界: 空列表 / article_count 计数
(c) 异常: 404 (不存在) / 400 (重名, 删除带文章的分类)
(d) 权限门: router-level get_current_user — 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
from app.models.knowledge import KnowledgeArticle, KnowledgeCategory

KB = "/api/v1/knowledge"


# ───────────────────────── helpers ─────────────────────────


def _category(session, name, *, sort_order=0, icon="", description=""):
    c = KnowledgeCategory(
        name=name, icon=icon, sort_order=sort_order, description=description
    )
    session.add(c)
    session.flush()
    return c


# ═══════════════════════════════════════════════════════════════
# 1. GET /categories (列表)
# ═══════════════════════════════════════════════════════════════

class TestListCategories:
    def test_empty_list(self, client):
        """无分类时返回空数组。"""
        r = client.get(f"{KB}/categories")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_fields_and_sort(self, client):
        """字段正确 + 按 sort_order 升序排序。"""
        s = client._sesh
        _category(s, "B类", sort_order=2)
        _category(s, "A类", sort_order=1)
        _category(s, "C类", sort_order=3)
        s.commit()

        r = client.get(f"{KB}/categories")
        assert r.status_code == 200
        items = r.json()["data"]
        assert [it["name"] for it in items] == ["A类", "B类", "C类"]
        first = items[0]
        assert set(first.keys()) >= {"id", "name", "icon", "sort_order", "description", "article_count"}
        assert first["sort_order"] == 1

    def test_article_count(self, client):
        """article_count 按 category 名统计 KnowledgeArticle 数量。"""
        s = client._sesh
        cat = _category(s, "运维")
        s.commit()
        s.add_all([
            KnowledgeArticle(title="t1", category="运维", content="c1"),
            KnowledgeArticle(title="t2", category="运维", content="c2"),
            KnowledgeArticle(title="t3", category="其他", content="c3"),
        ])
        s.commit()

        r = client.get(f"{KB}/categories")
        item = next(it for it in r.json()["data"] if it["name"] == "运维")
        assert item["article_count"] == 2


# ═══════════════════════════════════════════════════════════════
# 2. POST /categories (创建)
# ═══════════════════════════════════════════════════════════════

class TestCreateCategory:
    def test_create_success(self, client):
        r = client.post(
            f"{KB}/categories",
            params={"name": "新建类", "icon": "🔧", "sort_order": 5, "description": "测试描述"},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "新建类"
        assert d["icon"] == "🔧"
        assert d["sort_order"] == 5
        assert d["description"] == "测试描述"
        assert "id" in d

    def test_create_duplicate_400(self, client):
        s = client._sesh
        _category(s, "重复类")
        s.commit()

        r = client.post(f"{KB}/categories", params={"name": "重复类"})
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]

    def test_create_default_params(self, client):
        """只传 name, 其余用默认值。"""
        r = client.post(f"{KB}/categories", params={"name": "默认类"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["sort_order"] == 0
        assert d["icon"] == ""
        assert d["description"] == ""


# ═══════════════════════════════════════════════════════════════
# 3. PUT /categories/{id} (更新)
# ═══════════════════════════════════════════════════════════════

class TestUpdateCategory:
    def test_update_fields(self, client):
        s = client._sesh
        c = _category(s, "原名", sort_order=0)
        s.commit()

        r = client.put(
            f"{KB}/categories/{c.id}",
            params={"name": "新名", "sort_order": 9, "description": "改了"},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "新名"
        assert d["sort_order"] == 9
        assert d["description"] == "改了"

    def test_update_not_found_404(self, client):
        r = client.put(f"{KB}/categories/999999", params={"name": "x"})
        assert r.status_code == 404
        assert r.json()["detail"] == "分类不存在"

    def test_update_name_conflict_400(self, client):
        """改成与其它分类同名 → 400。"""
        s = client._sesh
        a = _category(s, "AAA")
        b = _category(s, "BBB")
        s.commit()
        r = client.put(f"{KB}/categories/{b.id}", params={"name": "AAA"})
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# 4. DELETE /categories/{id} (删除)
# ═══════════════════════════════════════════════════════════════

class TestDeleteCategory:
    def test_delete_success(self, client):
        s = client._sesh
        c = _category(s, "待删")
        s.commit()
        cid = c.id

        r = client.delete(f"{KB}/categories/{cid}")
        assert r.status_code == 200
        assert "已删除" in r.json()["message"]
        # 确认已删除
        assert s.query(KnowledgeCategory).filter_by(id=cid).first() is None

    def test_delete_not_found_404(self, client):
        r = client.delete(f"{KB}/categories/999999")
        assert r.status_code == 404

    def test_delete_with_articles_400(self, client):
        """分类下有文章 → 400 拒绝删除。"""
        s = client._sesh
        c = _category(s, "有文章")
        s.commit()
        s.add(KnowledgeArticle(title="t", category="有文章", content="c"))
        s.commit()

        r = client.delete(f"{KB}/categories/{c.id}")
        assert r.status_code == 400
        assert "文章" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# 5. GET /categories/list (旧版兼容)
# ═══════════════════════════════════════════════════════════════

class TestLegacyList:
    def test_legacy_list_shape(self, client):
        """旧路由返回 {categories: [名字], items: [分类对象]}。"""
        s = client._sesh
        _category(s, "旧类", sort_order=1)
        s.commit()
        s.add(KnowledgeArticle(title="t", category="旧类", content="c"))
        s.commit()

        r = client.get(f"{KB}/categories/list")
        assert r.status_code == 200
        d = r.json()["data"]
        assert "categories" in d and "items" in d
        assert "旧类" in d["categories"]
        assert any(it["name"] == "旧类" for it in d["items"])


# ═══════════════════════════════════════════════════════════════
# 6. 权限门 (router-level get_current_user)
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_anonymous_list_401(self, anon_client):
        assert anon_client.get(f"{KB}/categories").status_code == 401

    def test_anonymous_create_401(self, anon_client):
        assert anon_client.post(f"{KB}/categories", params={"name": "x"}).status_code == 401

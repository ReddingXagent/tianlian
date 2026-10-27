"""
知识库 API 测试
覆盖: 文章CRUD + 分类列表 + 搜索 + 统计摘要 + FAQ + 文档生成
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


@pytest.fixture
def auth_token(test_db):
    """获取认证token"""
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return token


class TestKnowledgeAPI:
    """知识库 API 测试类"""

    # ========== 鉴权测试 ==========

    def test_list_articles_requires_auth(self):
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/knowledge/articles").status_code == 401

    def test_create_article_requires_auth(self):
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.post("/api/v1/knowledge/articles", json={
            "title": "t", "content": "c"
        }).status_code in (401, 403)

    # ========== 文章 CRUD ==========

    def test_list_articles_success(self, auth_token):
        """测试获取文章列表成功"""
        response = client.get("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        items = data.get("data", {}).get("items", []) or data.get("items", [])
        total = data.get("data", {}).get("total", 0) or data.get("total", 0)
        assert isinstance(items, list)
        assert isinstance(total, int)

    def test_list_articles_with_pagination(self, auth_token):
        """测试文章列表分页"""
        response = client.get("/api/v1/knowledge/articles?page=1&page_size=10", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        page_info = data.get("data", data)
        assert page_info.get("page", 1) == 1

    def test_list_articles_with_category_filter(self, auth_token):
        """测试文章列表分类过滤"""
        response = client.get("/api/v1/knowledge/articles?category=general", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_articles_with_search(self, auth_token):
        """测试文章列表搜索"""
        response = client.get("/api/v1/knowledge/articles?search=测试", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_articles_combined_filters(self, auth_token):
        """测试文章列表组合过滤"""
        response = client.get("/api/v1/knowledge/articles?category=general&search=test&page=1&page_size=20", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_create_article_success(self, auth_token):
        """测试创建文章成功"""
        response = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "测试文章标题",
            "content": "这是测试文章的内容，包含一些技术说明。",
            "category": "general",
            "tags": "测试,技术"
        })
        assert response.status_code == 200
        data = response.json()
        article_data = data.get("data", data)
        assert article_data.get("title") == "测试文章标题"
        assert article_data.get("category") == "general"

    def test_create_article_minimal(self, auth_token):
        """测试创建文章最小字段"""
        response = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "最小文章",
            "content": "简单内容"
        })
        assert response.status_code == 200
        data = response.json()
        article_data = data.get("data", data)
        assert article_data.get("title") == "最小文章"

    def test_create_article_with_tags(self, auth_token):
        """测试创建文章带标签"""
        response = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "带标签文章",
            "content": "带标签的内容",
            "category": "technical",
            "tags": "运维,光伏,逆变器"
        })
        assert response.status_code == 200
        article_data = response.json().get("data", {})
        assert article_data.get("tags") == "运维,光伏,逆变器"

    def test_get_article_success(self, auth_token):
        """测试获取文章详情成功"""
        create_resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "详情测试文章",
            "content": "用于测试获取详情"
        })
        article_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.get(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        article_data = data.get("data", data)
        assert article_data.get("id") == article_id

    def test_get_article_not_found(self, auth_token):
        """测试获取文章不存在"""
        response = client.get("/api/v1/knowledge/articles/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_get_article_increments_view_count(self, auth_token):
        """测试获取文章详情增加浏览次数"""
        create_resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "浏览计数测试",
            "content": "测试浏览计数"
        })
        article_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        resp1 = client.get(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        vc1 = resp1.json().get("data", {}).get("view_count", 0) or resp1.json().get("view_count", 0)

        resp2 = client.get(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        vc2 = resp2.json().get("data", {}).get("view_count", 0) or resp2.json().get("view_count", 0)

        assert vc2 >= vc1 + 1

    def test_update_article_success(self, auth_token):
        """测试更新文章成功"""
        create_resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "待更新文章",
            "content": "原始内容",
            "category": "general"
        })
        article_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.put(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "已更新文章",
            "content": "更新后的内容",
            "category": "technical"
        })
        assert response.status_code == 200
        article_data = response.json().get("data", {})
        assert article_data.get("title") == "已更新文章"
        assert article_data.get("category") == "technical"

    def test_update_article_partial(self, auth_token):
        """测试部分更新文章"""
        create_resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "部分更新文章",
            "content": "原始内容",
            "category": "general"
        })
        article_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.put(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "content": "只更新了内容"
        })
        assert response.status_code == 200
        article_data = response.json().get("data", {})
        assert article_data.get("content") == "只更新了内容"
        assert article_data.get("title") == "部分更新文章"

    def test_update_article_not_found(self, auth_token):
        """测试更新文章不存在"""
        response = client.put("/api/v1/knowledge/articles/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"title": "不存在"})
        assert response.status_code == 404

    def test_delete_article_success(self, auth_token):
        """测试删除文章成功"""
        create_resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "待删除文章",
            "content": "将被删除"
        })
        article_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.delete(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

        get_resp = client.get(f"/api/v1/knowledge/articles/{article_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert get_resp.status_code == 404

    def test_delete_article_not_found(self, auth_token):
        """测试删除文章不存在"""
        response = client.delete("/api/v1/knowledge/articles/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== 分类 ==========

    def test_list_categories_success(self, auth_token):
        """测试获取分类列表成功"""
        response = client.get("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        categories = data.get("data", [])
        assert isinstance(categories, list)

    def test_list_categories_legacy(self, auth_token):
        """测试获取分类列表（旧版兼容）"""
        response = client.get("/api/v1/knowledge/categories/list", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_create_category_success(self, auth_token):
        """测试创建分类成功"""
        response = client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={
            "name": "测试分类",
            "icon": "📚",
            "sort_order": 1,
            "description": "测试用分类"
        })
        assert response.status_code == 200
        data = response.json()
        cat = data.get("data", data)
        assert cat.get("name") == "测试分类"
        assert cat.get("icon") == "📚"

    def test_create_category_duplicate(self, auth_token):
        """测试创建重复分类"""
        client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "重复分类"})
        response = client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "重复分类"})
        assert response.status_code == 400

    def test_update_category_success(self, auth_token):
        """测试更新分类成功"""
        create_resp = client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "待更新分类"})
        cat_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.put(f"/api/v1/knowledge/categories/{cat_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "已更新分类", "icon": "🔧"})
        assert response.status_code == 200
        cat = response.json().get("data", {})
        assert cat.get("name") == "已更新分类"
        assert cat.get("icon") == "🔧"

    def test_update_category_not_found(self, auth_token):
        """测试更新不存在的分类"""
        response = client.put("/api/v1/knowledge/categories/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "不存在"})
        assert response.status_code == 404

    def test_delete_category_success(self, auth_token):
        """测试删除分类成功"""
        create_resp = client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "待删除分类"})
        cat_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        response = client.delete(f"/api/v1/knowledge/categories/{cat_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_delete_category_not_found(self, auth_token):
        """测试删除不存在的分类"""
        response = client.delete("/api/v1/knowledge/categories/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_delete_category_with_articles(self, auth_token):
        """测试删除有文章的分类应被阻止"""
        # 创建分类
        create_resp = client.post("/api/v1/knowledge/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        }, params={"name": "有文章的分类"})
        cat_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 创建该分类下的文章
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"title": "测试", "content": "内容", "category": "有文章的分类"})

        # 尝试删除分类
        response = client.delete(f"/api/v1/knowledge/categories/{cat_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 400

    # ========== 统计 ==========

    def test_get_stats_summary_success(self, auth_token):
        """测试获取知识库统计摘要成功"""
        response = client.get("/api/v1/knowledge/stats/summary", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        stats = data.get("data", data)
        assert "total" in stats
        assert "categories" in stats or "total_views" in stats

    # ========== 搜索 ==========

    def test_search_articles_by_title(self, auth_token):
        """测试按标题搜索文章"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "光伏逆变器维护指南",
            "content": "详细说明"
        })

        response = client.get("/api/v1/knowledge/articles?search=光伏", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_search_articles_by_content(self, auth_token):
        """测试按内容搜索文章"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "通用标题",
            "content": "储能系统运维要点说明"
        })

        response = client.get("/api/v1/knowledge/articles?search=储能", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    # ========== FAQ ==========

    def test_list_faq_success(self, auth_token):
        """测试获取FAQ列表成功"""
        response = client.get("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        faqs = data.get("data", data) if isinstance(data.get("data"), list) else data
        assert isinstance(data.get("data", []), list)

    def test_create_faq_success(self, auth_token):
        """测试创建FAQ成功"""
        response = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "逆变器温度过高怎么办？",
            "answer": "检查散热系统、清理灰尘、降低负载。",
            "category": "operation",
            "tags": ["逆变器", "温度"]
        })
        assert response.status_code == 200
        data = response.json()
        faq = data.get("data", data)
        assert faq.get("question") == "逆变器温度过高怎么办？"
        assert faq.get("category") == "operation"

    def test_create_faq_no_tags(self, auth_token):
        """测试创建FAQ不带标签"""
        response = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "简单FAQ？",
            "answer": "简单回答。",
            "category": "general"
        })
        assert response.status_code == 200

    def test_list_faq_with_category_filter(self, auth_token):
        """测试按分类筛选FAQ"""
        response = client.get("/api/v1/knowledge/faq?category=operation", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_faq_with_search(self, auth_token):
        """测试FAQ关键词搜索"""
        response = client.get("/api/v1/knowledge/faq?q=温度", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_mark_faq_helpful(self, auth_token):
        """测试标记FAQ有帮助"""
        # 先创建FAQ
        create_resp = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "有用测试？",
            "answer": "有用回答。",
            "category": "general"
        })
        faq_id = create_resp.json().get("data", {}).get("id") or create_resp.json().get("id")

        # 标记有帮助
        resp = client.put(f"/api/v1/knowledge/faq/{faq_id}/helpful", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        helpful = data.get("data", {}).get("helpful_count") or data.get("helpful_count")
        assert helpful >= 1

    def test_mark_faq_helpful_not_found(self, auth_token):
        """测试标记不存在的FAQ"""
        resp = client.put("/api/v1/knowledge/faq/99999/helpful", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 404

    def test_batch_import_faq(self, auth_token):
        """测试批量导入FAQ"""
        response = client.post("/api/v1/knowledge/faq/batch-import", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "faqs": [
                {"question": "Q1", "answer": "A1", "category": "general"},
                {"question": "Q2", "answer": "A2", "category": "operation", "tags": ["tag1"]},
            ]
        })
        assert response.status_code == 200
        data = response.json()
        result = data.get("data", data)
        assert result.get("imported_count") == 2

    def test_list_faq_categories(self, auth_token):
        """测试获取FAQ分类列表"""
        response = client.get("/api/v1/knowledge/faq/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        categories = data.get("data", [])
        assert isinstance(categories, list)


class TestFAQAPI:
    """FAQ端点专项测试"""

    def test_create_faq_long_content(self, auth_token):
        """测试创建FAQ - 超长问题和答案"""
        response = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "测试" * 100,
            "answer": "回答" * 500,
            "category": "general"
        })
        assert response.status_code == 200

    def test_create_faq_special_chars(self, auth_token):
        """测试创建FAQ - 特殊字符"""
        response = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "如何检查电池温度？#电池组#$%^&",
            "answer": "温度>60°C时需注意！<br>湿度:45%~80%\n电压:±5%",
            "category": "technical"
        })
        assert response.status_code == 200
        faq = response.json().get("data", {})
        assert "温度" in faq.get("question", "")

    def test_batch_import_single_faq(self, auth_token):
        """测试批量导入单个FAQ"""
        response = client.post("/api/v1/knowledge/faq/batch-import", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "faqs": [
                {"question": "单个问题？", "answer": "单个答案", "category": "general"}
            ]
        })
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("imported_count") == 1

    def test_batch_import_empty_list(self, auth_token):
        """测试批量导入空列表"""
        response = client.post("/api/v1/knowledge/faq/batch-import", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"faqs": []})
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("imported_count") == 0

    def test_batch_import_mixed_tags(self, auth_token):
        """测试批量导入 - 混合标签格式"""
        response = client.post("/api/v1/knowledge/faq/batch-import", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "faqs": [
                {"question": "Q1?", "answer": "A1", "category": "general", "tags": ["tag1", "tag2"]},
                {"question": "Q2?", "answer": "A2", "category": "operation", "tags": []},
                {"question": "Q3?", "answer": "A3", "category": "system"},
            ]
        })
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("imported_count") == 3

    def test_mark_faq_helpful_multiple_times(self, auth_token):
        """测试标记FAQ有帮助多次 - 检查计数递增"""
        create_resp = client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "计数测试？",
            "answer": "看这里。",
            "category": "general"
        })
        faq_id = create_resp.json().get("data", {}).get("id")

        count_before = create_resp.json().get("data", {}).get("helpful_count", 0)

        # 标记3次
        for _ in range(3):
            resp = client.put(f"/api/v1/knowledge/faq/{faq_id}/helpful", headers={
                "Authorization": f"Bearer {auth_token}"
            })
            assert resp.status_code == 200

        # 获取FAQ详情确认计数
        list_resp = client.get("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        faqs = list_resp.json().get("data", [])
        for f in faqs:
            if f.get("id") == faq_id:
                assert f.get("helpful_count", 0) >= count_before + 3
                break

    def test_list_faq_no_results(self, auth_token):
        """测试FAQ搜索无结果"""
        response = client.get("/api/v1/knowledge/faq?q=__NONEXISTENT_KEYWORD_9999__", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        faqs = data.get("data", [])
        assert len(faqs) == 0

    def test_list_faq_category_no_results(self, auth_token):
        """测试FAQ分类筛选无结果"""
        response = client.get("/api/v1/knowledge/faq?category=__NONEXISTENT_CAT__", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        faqs = data.get("data", [])
        assert len(faqs) == 0

    def test_list_faq_combined_filters(self, auth_token):
        """测试FAQ组合过滤（分类+关键词）"""
        response = client.get("/api/v1/knowledge/faq?category=operation&q=逆变器", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        faqs = data.get("data", [])
        assert isinstance(faqs, list)

    def test_faq_categories_after_creation(self, auth_token):
        """测试创建FAQ后分类列表包含新分类"""
        # 创建一个新类别的FAQ
        client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "新类别测试？",
            "answer": "测试",
            "category": "new_category_pytest"
        })

        resp = client.get("/api/v1/knowledge/faq/categories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        categories = resp.json().get("data", [])
        assert "new_category_pytest" in categories

    # ========== 文档生成 ==========

    def test_generate_doc_manual(self, auth_token):
        """测试生成运维手册"""
        response = client.post("/api/v1/knowledge/generate-doc", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "doc_type": "manual",
            "device_type": "inverter",
            "title": "逆变器运维手册"
        })
        assert response.status_code == 200
        data = response.json()
        doc = data.get("data", data)
        assert "content" in doc
        assert doc.get("format") == "markdown"
        assert "逆变器" in doc.get("content", "")

    def test_generate_doc_checklist(self, auth_token):
        """测试生成检查清单"""
        response = client.post("/api/v1/knowledge/generate-doc", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "doc_type": "checklist",
            "title": "日常巡检清单"
        })
        assert response.status_code == 200
        data = response.json()
        doc = data.get("data", data)
        assert "content" in doc
        assert "检查清单" in doc.get("content", "")

    def test_generate_doc_with_fault_code(self, auth_token):
        """测试根据故障码生成文档"""
        response = client.post("/api/v1/knowledge/generate-doc", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "doc_type": "document",
            "fault_code": "E001",
            "title": "故障处理文档"
        })
        assert response.status_code == 200
        data = response.json()
        doc = data.get("data", data)
        assert "content" in doc
        assert "E001" in doc.get("content", "")

    def test_generate_doc_default(self, auth_token):
        """测试默认文档生成"""
        response = client.post("/api/v1/knowledge/generate-doc", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "doc_type": "general",
            "title": "通用文档"
        })
        assert response.status_code == 200
        data = response.json()
        doc = data.get("data", data)
        assert "content" in doc

    # ========== 兼容路由 ==========

    def test_list_articles_legacy_route(self, auth_token):
        """测试旧版列表路由"""
        response = client.get("/api/v1/knowledge", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_list_articles_legacy_with_filters(self, auth_token):
        """测试旧版列表路由带过滤"""
        response = client.get("/api/v1/knowledge?category=general&search=test&page=1&page_size=10", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200


class TestKnowledgeSearch:
    """知识库搜索端点专项测试 (GET /api/v1/knowledge/search)"""

    # ========== 基础搜索 ==========

    def test_search_by_title(self, auth_token):
        """测试按标题搜索 - 返回 id/title/category/summary/author/updated_at"""
        # 先创建一篇带关键词的文章
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "光伏逆变器远程诊断指南",
            "content": "详细的诊断步骤说明",
            "category": "operation"
        })

        response = client.get("/api/v1/knowledge/search?q=光伏逆变器", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", search_data.get("items", []))
        total = search_data.get("total", 0)
        assert total >= 1
        assert len(items) >= 1

        result = items[0]
        # 检查必需字段
        assert "id" in result
        assert "title" in result
        assert "category" in result
        assert "summary" in result  # 高亮片段
        assert "updated_at" in result
        # author 字段存在（可能为 None 或 "未知"）
        assert "author" in result

    def test_search_by_content(self, auth_token):
        """测试按内容搜索"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "通用标题",
            "content": "储能系统电池管理运维要点详细说明",
            "category": "technical"
        })

        response = client.get("/api/v1/knowledge/search?q=电池管理", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        assert len(items) >= 1

        # 高亮片段应包含搜索关键词的 mark 标签
        result = items[0]
        summary = result.get("summary", "")
        assert "电池管理" in summary or "<mark>" in summary

    def test_search_summary_contains_highlight(self, auth_token):
        """测试搜索摘要包含 <mark> 高亮"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "充电桩日常维护规范",
            "content": "充电桩需要每日检查接插件和绝缘电阻",
            "category": "maintenance"
        })

        response = client.get("/api/v1/knowledge/search?q=充电桩", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        assert len(items) >= 1

        result = items[0]
        summary = result.get("summary", "")
        assert "<mark>" in summary
        assert "</mark>" in summary

    # ========== 结果字段 ==========

    def test_search_result_fields_complete(self, auth_token):
        """测试搜索结果包含完整字段"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "安全操作规范2025版",
            "content": "关于高压设备的操作安全规范内容",
            "category": "safety"
        })

        response = client.get("/api/v1/knowledge/search?q=安全操作", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        assert len(items) >= 1

        result = items[0]
        # 验证所有必需字段存在
        required_fields = ["id", "title", "category", "summary", "author", "updated_at"]
        for field in required_fields:
            assert field in result, f"搜索结果缺少字段: {field}"

        # 验证向后兼容字段
        assert "highlight" in result

    def test_search_result_id_is_int(self, auth_token):
        """测试搜索结果的 id 是整数"""
        resp = client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "维保检查清单",
            "content": "定期维保检查内容",
            "category": "maintenance"
        })
        article_id = resp.json().get("data", {}).get("id")

        response = client.get("/api/v1/knowledge/search?q=维保检查", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        items = response.json().get("data", {}).get("items", [])
        assert len(items) >= 1
        assert isinstance(items[0].get("id"), int)

    # ========== 搜索无结果 ==========

    def test_search_empty_keyword(self, auth_token):
        """测试空关键词搜索"""
        response = client.get("/api/v1/knowledge/search?q=", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        total = search_data.get("total", 0)
        assert total == 0
        assert len(items) == 0

    def test_search_no_results(self, auth_token):
        """测试搜索无匹配结果"""
        response = client.get("/api/v1/knowledge/search?q=__ZZZZ_NONEXISTENT_9999__", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        total = search_data.get("total", 0)
        assert total == 0
        assert len(items) == 0

    def test_search_with_spaces_only(self, auth_token):
        """测试仅空格关键词"""
        response = client.get("/api/v1/knowledge/search?q=   ", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        total = search_data.get("total", 0)
        assert total == 0

    # ========== 分页 ==========

    def test_search_pagination(self, auth_token):
        """测试搜索分页"""
        # 创建多篇文章
        for i in range(3):
            client.post("/api/v1/knowledge/articles", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "title": f"搜索分页测试文章{i}",
                "content": "这是搜索分页测试的内容",
                "category": "test"
            })

        response = client.get(
            "/api/v1/knowledge/search?q=搜索分页测试&page=1&page_size=2",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        total = search_data.get("total", 0)
        assert len(items) <= 2
        assert total >= 3
        assert search_data.get("page", 1) == 1

    def test_search_page2(self, auth_token):
        """测试搜索第二页"""
        for i in range(4):
            client.post("/api/v1/knowledge/articles", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "title": f"第二页测试{i}",
                "content": "测试搜索第二页的内容",
                "category": "test"
            })

        response = client.get(
            "/api/v1/knowledge/search?q=第二页测试&page=2&page_size=2",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        search_data = data.get("data", data)
        items = search_data.get("items", [])
        total = search_data.get("total", 0)
        assert total >= 4
        assert search_data.get("page", 2) == 2

    # ========== 鉴权 ==========

    def test_search_requires_auth(self):
        """测试搜索需要鉴权"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        response = client.get("/api/v1/knowledge/search?q=test")
        assert response.status_code == 401

    # ========== 大小写不敏感 ==========

    def test_search_case_insensitive(self, auth_token):
        """测试搜索大小写不敏感"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "光伏PV系统运维",
            "content": "PV系统运维详细说明",
            "category": "operation"
        })

        resp_lower = client.get("/api/v1/knowledge/search?q=pv系统", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp_lower.status_code == 200
        items_lower = resp_lower.json().get("data", {}).get("items", [])

        resp_upper = client.get("/api/v1/knowledge/search?q=PV系统", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp_upper.status_code == 200
        items_upper = resp_upper.json().get("data", {}).get("items", [])

        # 大小写搜索结果应一致
        assert len(items_lower) == len(items_upper)

    # ========== FAQ 搜索 ==========

    def test_search_includes_faq(self, auth_token):
        """测试搜索包含FAQ结果"""
        client.post("/api/v1/knowledge/faq", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "question": "如何重置逆变器？",
            "answer": "按复位按钮5秒后重新上电",
            "category": "operation"
        })

        response = client.get("/api/v1/knowledge/search?q=逆变器", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        items = response.json().get("data", {}).get("items", [])
        # FAQ 结果的 author 应为 None
        faq_items = [i for i in items if i.get("author") is None]
        assert len(faq_items) >= 1

    # ========== 特殊字符搜索 ==========

    def test_search_with_special_chars(self, auth_token):
        """测试搜索带特殊字符的关键词"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "100kW光伏电站运维",
            "content": "大型光伏电站运维要点",
            "category": "operation"
        })

        response = client.get("/api/v1/knowledge/search?q=100kW", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        items = data.get("data", {}).get("items", [])
        assert len(items) >= 1

    def test_search_with_chinese_chars(self, auth_token):
        """测试中文关键词搜索"""
        client.post("/api/v1/knowledge/articles", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "title": "电力系统安全运维规程",
            "content": "详细的电力系统安全运维规程内容",
            "category": "safety"
        })

        response = client.get("/api/v1/knowledge/search?q=安全运维规程", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        items = response.json().get("data", {}).get("items", [])
        assert len(items) >= 1
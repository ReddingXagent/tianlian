"""知识库文档生成 API 测试 (app/api/v1/knowledge/docs.py, 卡 96f676b3)

覆盖端点 (前缀 /api/v1/knowledge):
- POST /generate-doc  自动生成运维 markdown 文档

按 doc_type 分支:
- "manual"   + device_type → 设备手册模板
- "checklist"              → 检查清单模板
- 其它 + fault_code        → 故障码处理方案模板
- 其它 (默认)              → 从知识库相关文章提取

覆盖维度:
(a) 正常路径: 各分支生成内容正确 (markdown 标题/小节)
(b) 默认值: title 缺省回退; generated_at/format 字段
(c) 知识库提取: 默认分支按 category 过滤文章
(d) 参数校验: 缺 doc_type → 422
(e) 权限门: router-level get_current_user — 匿名 → 401

铁律: 仅加测试, 不改业务代码。
"""
import pytest

from app.models.knowledge import KnowledgeArticle

KB = "/api/v1/knowledge"


# ═══════════════════════════════════════════════════════════════
# 1. manual 分支
# ═══════════════════════════════════════════════════════════════

class TestManualBranch:
    def test_manual_generates_device_template(self, client):
        r = client.post(f"{KB}/generate-doc", json={
            "doc_type": "manual", "device_type": "逆变器", "title": "手册X",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["title"] == "手册X"
        assert d["format"] == "markdown"
        c = d["content"]
        assert "# 手册X" in c
        assert "设备类型: 逆变器" in c
        assert "常见故障码" in c  # manual 专属小节

    def test_manual_default_title(self, client):
        """title 缺省 → "运维手册 - {doc_type}"。"""
        r = client.post(f"{KB}/generate-doc", json={"doc_type": "manual", "device_type": "X"})
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "运维手册 - manual"


# ═══════════════════════════════════════════════════════════════
# 2. checklist 分支
# ═══════════════════════════════════════════════════════════════

class TestChecklistBranch:
    def test_checklist_content(self, client):
        r = client.post(f"{KB}/generate-doc", json={"doc_type": "checklist"})
        assert r.status_code == 200
        c = r.json()["data"]["content"]
        assert "## 检查清单" in c
        assert "日常巡检" in c
        assert "- [ ]" in c  # 复选框语法


# ═══════════════════════════════════════════════════════════════
# 3. fault_code 分支
# ═══════════════════════════════════════════════════════════════

class TestFaultCodeBranch:
    def test_fault_code_content(self, client):
        r = client.post(f"{KB}/generate-doc", json={"doc_type": "document", "fault_code": "E001"})
        assert r.status_code == 200
        c = r.json()["data"]["content"]
        assert "## 故障码: E001" in c
        assert "故障描述" in c


# ═══════════════════════════════════════════════════════════════
# 4. 默认分支 (知识库文章提取)
# ═══════════════════════════════════════════════════════════════

class TestDefaultBranch:
    def test_default_extracts_articles(self, client):
        """无 manual/checklist/fault_code → 按 category=doc_type 提取文章。"""
        s = client._sesh
        s.add_all([
            KnowledgeArticle(title="文章A", category="运维", content="正文内容A" * 5),
            KnowledgeArticle(title="文章B", category="其他", content="不相关"),
        ])
        s.commit()

        r = client.post(f"{KB}/generate-doc", json={"doc_type": "运维"})
        assert r.status_code == 200
        c = r.json()["data"]["content"]
        assert "## 相关知识库文章" in c
        assert "文章A" in c
        assert "文章B" not in c  # 仅 category==运维

    def test_default_no_articles(self, client):
        """无匹配文章时, 仅生成骨架, 不报错。"""
        r = client.post(f"{KB}/generate-doc", json={"doc_type": "不存在的分类"})
        assert r.status_code == 200
        c = r.json()["data"]["content"]
        assert "## 相关知识库文章" in c
        # 结尾免责声明始终存在
        assert "系统自动生成" in c


# ═══════════════════════════════════════════════════════════════
# 5. 参数校验 + 权限门
# ═══════════════════════════════════════════════════════════════

class TestValidationAndPermission:
    def test_missing_doc_type_422(self, client):
        """doc_type 必填 → 缺失 422。"""
        r = client.post(f"{KB}/generate-doc", json={"device_type": "X"})
        assert r.status_code == 422

    def test_wrong_content_type_422(self, client):
        """body 不是 JSON → 422。"""
        r = client.post(f"{KB}/generate-doc", params={"doc_type": "manual"})
        assert r.status_code == 422

    def test_anonymous_401(self, anon_client):
        r = anon_client.post(f"{KB}/generate-doc", json={"doc_type": "manual"})
        assert r.status_code == 401

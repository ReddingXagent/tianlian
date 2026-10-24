"""
Runbook 模板持久化 (DB CRUD) 测试

覆盖:
1. 内置模板种子 (幂等)
2. CRUD 全端点: 列表(分页+筛选)/详情/创建/更新/删除
3. 执行兼容: RunbookEngine 优先命中 DB 模板, 未命中 fallback 内置
"""
import pytest

from app.models.runbook import RunbookTemplateModel, seed_builtin_runbook_templates


# ─── 种子数据 ───

class TestSeed:
    """内置模板种子 (init_db 调用)"""

    def test_seed_inserts_builtin_templates(self, db_session):
        """首次种子应插入全部内置模板"""
        seed_builtin_runbook_templates(db_session)
        count = db_session.query(RunbookTemplateModel).count()
        assert count == 10  # 内置 10 个模板

    def test_seed_is_idempotent(self, db_session):
        """重复种子不应产生重复记录"""
        seed_builtin_runbook_templates(db_session)
        seed_builtin_runbook_templates(db_session)
        count = db_session.query(RunbookTemplateModel).count()
        assert count == 10

    def test_seed_sets_alarm_type_equal_to_name(self, db_session):
        """内置模板 alarm_type 默认等于 name (兼容旧 match 行为)"""
        seed_builtin_runbook_templates(db_session)
        inv = db_session.query(RunbookTemplateModel).filter_by(name="逆变器通讯中断").first()
        assert inv is not None
        assert inv.alarm_type == "逆变器通讯中断"
        assert inv.category == "inverter"
        assert inv.status == "active"
        assert len(inv.steps) == 4


# ─── 列表 ───

class TestListTemplates:
    """GET /api/v1/runbooks/templates"""

    def test_list_after_seed(self, client, db_session):
        """种子后列表应返回内置模板"""
        seed_builtin_runbook_templates(db_session)
        r = client.get("/api/v1/runbooks/templates")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 10
        assert len(data["items"]) == 10
        item = data["items"][0]
        # 列表项契约
        for key in ("id", "name", "category", "alarm_type", "step_count", "status", "version"):
            assert key in item

    def test_list_empty(self, client):
        """无数据时列表为空"""
        r = client.get("/api/v1/runbooks/templates")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_filter_by_category(self, client, db_session):
        """按 category 筛选"""
        seed_builtin_runbook_templates(db_session)
        r = client.get("/api/v1/runbooks/templates?category=inverter")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 3  # 逆变器类 3 个
        assert all(it["category"] == "inverter" for it in data["items"])

    def test_list_filter_by_status(self, client, db_session):
        """按 status 筛选"""
        seed_builtin_runbook_templates(db_session)
        r = client.get("/api/v1/runbooks/templates?status=active")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 10
        assert all(it["status"] == "active" for it in data["items"])

    def test_list_pagination(self, client, db_session):
        """分页"""
        seed_builtin_runbook_templates(db_session)
        r = client.get("/api/v1/runbooks/templates?page=1&page_size=3")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 10
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["page_size"] == 3


# ─── 详情 ───

class TestGetTemplate:
    """GET /api/v1/runbooks/templates/{id}"""

    def test_get_detail_with_steps(self, client, db_session):
        """详情含完整 steps"""
        seed_builtin_runbook_templates(db_session)
        tmpl = db_session.query(RunbookTemplateModel).filter_by(name="逆变器通讯中断").first()
        r = client.get(f"/api/v1/runbooks/templates/{tmpl.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "逆变器通讯中断"
        assert d["category"] == "inverter"
        assert len(d["steps"]) == 4
        step = d["steps"][0]
        # 步骤详情字段
        for key in ("step_id", "action_type", "description", "risk_level", "auto_execute"):
            assert key in step
        assert d["step_count"] == 4

    def test_get_detail_not_found(self, client):
        """不存在的 id 返回 404"""
        r = client.get("/api/v1/runbooks/templates/99999")
        assert r.status_code == 404


# ─── 创建 ───

class TestCreateTemplate:
    """POST /api/v1/runbooks/templates"""

    def test_create_template(self, client):
        """创建模板"""
        payload = {
            "name": "自定义故障A",
            "category": "general",
            "description": "测试模板",
            "steps": [
                {"step_id": 1, "action_type": "remote_command",
                 "description": "检查", "command": "echo ok",
                 "risk_level": "low", "auto_execute": True},
            ],
        }
        r = client.post("/api/v1/runbooks/templates", json=payload)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] is not None
        assert d["name"] == "自定义故障A"
        assert d["version"] == 1
        assert d["status"] == "active"
        # alarm_type 默认 = name
        assert d["alarm_type"] == "自定义故障A"
        assert d["step_count"] == 1

    def test_create_template_with_explicit_alarm_type(self, client):
        """显式指定 alarm_type"""
        r = client.post("/api/v1/runbooks/templates", json={
            "name": "显示名B", "alarm_type": "告警码B", "category": "charger",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["alarm_type"] == "告警码B"
        assert d["name"] == "显示名B"

    def test_create_template_invalid_status(self, client):
        """非法 status 返回 422 (卡fbc05dc8: schema收紧Literal后Pydantic前置拦截)"""
        r = client.post("/api/v1/runbooks/templates", json={
            "name": "X", "status": "bogus",
        })
        assert r.status_code == 422

    def test_create_template_missing_name(self, client):
        """缺 name 触发 Pydantic 422"""
        r = client.post("/api/v1/runbooks/templates", json={"category": "general"})
        assert r.status_code == 422


# ─── 更新 ───

class TestUpdateTemplate:
    """PUT /api/v1/runbooks/templates/{id}"""

    def test_update_increments_version(self, client):
        """更新后 version 自增"""
        created = client.post("/api/v1/runbooks/templates", json={
            "name": "待更新", "category": "general",
        }).json()["data"]
        r = client.put(f"/api/v1/runbooks/templates/{created['id']}", json={
            "description": "新描述",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["description"] == "新描述"
        assert d["version"] == created["version"] + 1

    def test_update_not_found(self, client):
        r = client.put("/api/v1/runbooks/templates/99999", json={"description": "x"})
        assert r.status_code == 404


# ─── 删除 ───

class TestDeleteTemplate:
    """DELETE /api/v1/runbooks/templates/{id}"""

    def test_delete_template(self, client):
        created = client.post("/api/v1/runbooks/templates", json={
            "name": "待删除", "category": "general",
        }).json()["data"]
        r = client.delete(f"/api/v1/runbooks/templates/{created['id']}")
        assert r.status_code == 200
        # 删除后查不到
        r2 = client.get(f"/api/v1/runbooks/templates/{created['id']}")
        assert r2.status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete("/api/v1/runbooks/templates/99999")
        assert r.status_code == 404


# ─── 执行兼容 ───

class TestExecutionCompatibility:
    """RunbookEngine 优先用 DB 模板, fallback 内置"""

    def test_db_template_preferred_over_builtin(self, client, db_session):
        """DB 存在同 alarm_type 的 active 模板时, 执行用 DB 版本"""
        from app.services.runbook_engine import RunbookEngine

        # DB 创建一个独特 alarm_type 的模板, 步骤带可识别标记
        client.post("/api/v1/runbooks/templates", json={
            "name": "独特故障XYZ",
            "alarm_type": "独特故障XYZ",
            "category": "general",
            "steps": [
                {"step_id": 1, "action_type": "remote_command",
                 "description": "DB_STEP_MARKER", "command": "echo hi",
                 "risk_level": "low", "auto_execute": True},
            ],
        })

        engine = RunbookEngine(dry_run=True)
        result = engine.execute(
            alarm_id=999,
            diagnosis_result={"fault_type": "独特故障XYZ"},
            device_info={"id": 1, "name": "d", "sn": "s",
                         "ip": "1.1.1.1", "type": "general", "station_id": 1},
            db=db_session,
        )
        descs = [s["description"] for s in result["steps"]]
        assert "DB_STEP_MARKER" in descs  # 命中 DB 模板

    def test_falls_back_to_builtin_when_db_miss(self, client, db_session):
        """DB 无匹配时 fallback 到内置模板"""
        from app.services.runbook_engine import RunbookEngine

        # 不种子 → DB 无 "逆变器通讯中断" → 应 fallback 内置 (4 步)
        engine = RunbookEngine(dry_run=True)
        result = engine.execute(
            alarm_id=888,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={"id": 1, "name": "d", "sn": "s",
                         "ip": "1.1.1.1", "type": "inverter", "station_id": 1},
            db=db_session,
        )
        assert len(result["steps"]) == 4  # 内置 4 步

    def test_inactive_db_template_falls_back(self, client, db_session):
        """inactive 的 DB 模板不参与匹配, fallback 内置/default"""
        from app.services.runbook_engine import RunbookEngine

        # DB 创建 inactive 模板 (alarm_type 与内置同名, 但 inactive)
        created = client.post("/api/v1/runbooks/templates", json={
            "name": "逆变器通讯中断",
            "alarm_type": "逆变器通讯中断",
            "category": "inverter",
            "status": "inactive",
            "steps": [
                {"step_id": 1, "action_type": "remote_command",
                 "description": "INACTIVE_MARKER", "command": "echo x",
                 "risk_level": "low", "auto_execute": True},
            ],
        }).json()["data"]
        assert created["status"] == "inactive"

        engine = RunbookEngine(dry_run=True)
        result = engine.execute(
            alarm_id=777,
            diagnosis_result={"fault_type": "逆变器通讯中断"},
            device_info={"id": 1, "name": "d", "sn": "s",
                         "ip": "1.1.1.1", "type": "inverter", "station_id": 1},
            db=db_session,
        )
        descs = [s["description"] for s in result["steps"]]
        # 不应命中 inactive DB 模板
        assert "INACTIVE_MARKER" not in descs

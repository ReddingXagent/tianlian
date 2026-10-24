#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
巡检运维管理 API 测试（/api/v1/inspection）

覆盖巡检计划 CRUD + 状态切换、巡检任务 CRUD + 进度推进、统计概览。
计划端点挂 get_current_user 依赖（任务卡 708350b3: team_id 服务端强制）；
任务/模板/结果端点暂不涉 team_id，维持原行为。
"""
import bcrypt
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_plan(**overrides):
    payload = {"name": "测试巡检计划", "cycle": "weekly", "target": "all"}
    payload.update(overrides)
    headers = overrides.pop("headers", None) or _auth_headers()
    resp = client.post("/api/v1/inspection/plans", json=payload, headers=headers)
    assert resp.status_code == 200, f"Create plan failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


class TestInspection:
    """巡检运维 /inspection 端点"""

    def test_create_plan_and_invalid_cycle(self):
        """创建计划 + 无效周期返回 400"""
        data = _create_plan(name="周巡检计划")
        assert data["name"] == "周巡检计划"
        assert data["cycle"] == "weekly"
        assert data["status"] == "active"
        assert data["id"] > 0

        resp = client.post("/api/v1/inspection/plans", json={"name": "x", "cycle": "hourly"}, headers=_auth_headers())
        assert resp.status_code == 400

    def test_list_plans_pagination(self):
        """列表 — 分页结构"""
        _create_plan(name="计划A")
        _create_plan(name="计划B")
        resp = client.get("/api/v1/inspection/plans", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2
        assert "items" in data and "page" in data and "page_size" in data

    def test_get_plan_detail_with_tasks(self):
        """计划详情 — 嵌套 tasks + task_count"""
        plan = _create_plan(name="详情计划")
        client.post("/api/v1/inspection/tasks", json={
            "name": "子任务1", "plan_id": plan["id"], "total_items": 5,
        })
        resp = client.get(f"/api/v1/inspection/plans/{plan['id']}", headers=_auth_headers())
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["name"] == "详情计划"
        assert d["task_count"] >= 1
        assert len(d["tasks"]) >= 1

    def test_update_plan_and_toggle_status(self):
        """更新计划 + 状态切换"""
        plan = _create_plan(name="更新计划", description="前")
        resp = client.put(f"/api/v1/inspection/plans/{plan['id']}", json={
            "description": "后", "cycle": "monthly",
        }, headers=_auth_headers())
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["description"] == "后"
        assert d["cycle"] == "monthly"

        # 切换暂停
        resp = client.put(f"/api/v1/inspection/plans/{plan['id']}/status?status=paused", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "paused"

        # 无效状态
        assert client.put(
            f"/api/v1/inspection/plans/{plan['id']}/status?status=running", headers=_auth_headers()
        ).status_code == 400

    def test_delete_plan(self):
        """删除计划 — 删除后 404"""
        plan = _create_plan(name="删除计划")
        assert client.delete(f"/api/v1/inspection/plans/{plan['id']}", headers=_auth_headers()).status_code == 200
        assert client.get(f"/api/v1/inspection/plans/{plan['id']}", headers=_auth_headers()).status_code == 404

    def test_task_crud_and_progress(self):
        """任务 CRUD + 进度推进计算"""
        plan = _create_plan(name="任务计划")
        # 创建
        resp = client.post("/api/v1/inspection/tasks", json={
            "name": "巡检任务A", "plan_id": plan["id"],
            "station_name": "测试站", "total_items": 10,
        })
        assert resp.status_code == 200
        task = resp.json()["data"]
        assert task["name"] == "巡检任务A"
        assert task["total_items"] == 10
        assert task["progress"] == 0
        tid = task["id"]

        # 更新 — 推进进度
        resp = client.put(f"/api/v1/inspection/tasks/{tid}", json={
            "completed_items": 5, "status": "in_progress",
        })
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["completed_items"] == 5
        assert d["status"] == "in_progress"
        assert d["progress"] == 50.0  # 5/10

        # 详情 + 删除
        assert client.get(f"/api/v1/inspection/tasks/{tid}").status_code == 200
        assert client.delete(f"/api/v1/inspection/tasks/{tid}").status_code == 200
        assert client.get(f"/api/v1/inspection/tasks/{tid}").status_code == 404

    def test_inspection_stats(self):
        """统计概览 — tasks/plans 结构"""
        _create_plan(name="统计计划")
        client.post("/api/v1/inspection/tasks", json={"name": "统计任务", "total_items": 3})
        resp = client.get("/api/v1/inspection/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "tasks" in data and "plans" in data
        assert data["tasks"]["total"] >= 1
        assert data["plans"]["total"] >= 1
        assert "by_status" in data["tasks"]
        assert "completion_rate" in data["tasks"]

    def test_plan_and_task_404(self):
        """不存在资源返回 404"""
        assert client.get("/api/v1/inspection/plans/99999", headers=_auth_headers()).status_code == 404
        assert client.get("/api/v1/inspection/tasks/99999").status_code == 404
        assert client.put("/api/v1/inspection/plans/99999", json={"name": "x"}, headers=_auth_headers()).status_code == 404


# ─── 越权测试脚手架（任务卡 708350b3）───

@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(engineer) + token，用于 team_id 越权测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="巡检团队A", code="INSPTA")
    tb = Team(name="巡检团队B", code="INSPTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "insp123456"
    ua = User(
        username="insp_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="insp_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "tokens": {"a": _tok("insp_eng_a"), "b": _tok("insp_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestInspectionTeamIsolation:
    """巡检计划团队隔离（任务卡 708350b3）"""

    def test_create_forces_own_team(self, client, team_pair):
        """团队级用户创建的计划归属其本人 team；伪造 body team_id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        # A 故意伪造 body team_id=B
        r = client.post(
            "/api/v1/inspection/plans",
            json={"name": "A的计划", "cycle": "weekly", "team_id": tb.id},
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == ta.id  # 锁本人 team

    def test_list_filters_by_team(self, client, team_pair):
        """团队级用户仅见本 team 计划；伪造 query team_id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        # A、B 各建一条
        client.post("/api/v1/inspection/plans", json={"name": "A计划"},
                    headers=_h(team_pair["tokens"]["a"]))
        client.post("/api/v1/inspection/plans", json={"name": "B计划"},
                    headers=_h(team_pair["tokens"]["b"]))

        # A 故意伪造 ?team_id=B，仍只见本人 team
        r = client.get(
            f"/api/v1/inspection/plans?team_id={tb.id}",
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "A计划"
        assert items[0]["team_id"] == ta.id

        # admin 看全部
        r = client.get("/api/v1/inspection/plans", headers=_auth_headers())
        assert r.json()["data"]["total"] >= 2

    def test_cross_team_access_returns_404(self, client, team_pair):
        """团队A访问/改/删团队B的计划 → 404（伪造 X-Team-Id 也无效）。"""
        tb = team_pair["teams"]["b"]
        r = client.post("/api/v1/inspection/plans", json={"name": "B专属"},
                        headers=_h(team_pair["tokens"]["b"]))
        pid_b = r.json()["data"]["id"]

        ha = {**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)}
        assert client.get(f"/api/v1/inspection/plans/{pid_b}", headers=ha).status_code == 404
        assert client.put(f"/api/v1/inspection/plans/{pid_b}", json={"name": "篡改"}, headers=ha).status_code == 404
        assert client.delete(f"/api/v1/inspection/plans/{pid_b}", headers=ha).status_code == 404
        assert client.put(f"/api/v1/inspection/plans/{pid_b}/status?status=paused", headers=ha).status_code == 404

        # B 本人可正常操作
        hb = _h(team_pair["tokens"]["b"])
        assert client.get(f"/api/v1/inspection/plans/{pid_b}", headers=hb).status_code == 200


# ====================================================================
# 深度补充测试（卡 acf43702）
# 任务生命周期/过滤、模板 CRUD（此前 0 测试）、结果录入（此前 0 测试）、
# 计划边界、未认证。
# 注：源码无「超时处理」端点（TaskStatus 仅 scheduled/in_progress/completed/
#     cancelled，无 failed/timeout 逻辑），此处不虚构。
# ====================================================================


def _create_task(**overrides):
    """创建巡检任务，返回 data。"""
    payload = {"name": "UT任务", "total_items": 10}
    payload.update(overrides)
    resp = client.post("/api/v1/inspection/tasks", json=payload, headers=_auth_headers())
    assert resp.status_code == 200, f"创建任务失败: {resp.status_code} {resp.text}"
    return resp.json()["data"]


class TestInspectionTaskLifecycle:
    """任务状态流转 + 进度边界 + 日期解析"""

    def test_full_lifecycle_scheduled_to_completed(self):
        """scheduled → in_progress(50%) → completed(100%)"""
        task = _create_task(name="生命周期任务", total_items=4)
        tid = task["id"]
        assert task["status"] == "scheduled"
        assert task["progress"] == 0

        r = client.put(f"/api/v1/inspection/tasks/{tid}", json={
            "completed_items": 2, "status": "in_progress",
        }, headers=_auth_headers())
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "in_progress"
        assert d["progress"] == 50.0

        r = client.put(f"/api/v1/inspection/tasks/{tid}", json={
            "completed_items": 4, "status": "completed",
        }, headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "completed"
        assert r.json()["data"]["progress"] == 100.0

    def test_transition_to_cancelled(self):
        """任务可流转到 cancelled"""
        task = _create_task(name="取消任务")
        r = client.put(f"/api/v1/inspection/tasks/{task['id']}", json={
            "status": "cancelled",
        }, headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "cancelled"

    def test_update_invalid_status_422(self):
        """无效任务状态 → 422（卡 77a186b3：TaskUpdate.status 已收紧为 Literal）"""
        task = _create_task(name="无效状态任务")
        r = client.put(f"/api/v1/inspection/tasks/{task['id']}", json={
            "status": "running",
        }, headers=_auth_headers())
        assert r.status_code == 422

    def test_progress_zero_when_total_zero(self):
        """total_items=0 → progress 恒 0（避免除零）"""
        task = _create_task(name="零项任务", total_items=0)
        assert task["progress"] == 0
        r = client.put(f"/api/v1/inspection/tasks/{task['id']}", json={
            "completed_items": 5, "status": "in_progress",
        }, headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["progress"] == 0

    def test_scheduled_date_valid_parse(self):
        """有效 scheduled_date 原样回传"""
        task = _create_task(name="日期任务", scheduled_date="2026-09-01")
        assert task["scheduled_date"] == "2026-09-01"

    def test_scheduled_date_invalid_ignored(self):
        """无效 scheduled_date 被忽略（不报错，置 None）"""
        task = _create_task(name="无效日期任务", scheduled_date="not-a-date")
        assert task["scheduled_date"] is None


class TestInspectionTaskFilter:
    """任务列表多维度过滤 + 分页"""

    def test_filter_by_status(self):
        _create_task(name="过滤-默认")
        t = _create_task(name="过滤-已完成")
        client.put(f"/api/v1/inspection/tasks/{t['id']}", json={"status": "completed"},
                   headers=_auth_headers())
        r = client.get("/api/v1/inspection/tasks?status=completed", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items
        assert all(it["status"] == "completed" for it in items)

    def test_filter_by_plan(self):
        plan = _create_plan(name="过滤计划")
        _create_task(name="计划内任务", plan_id=plan["id"])
        _create_task(name="计划外任务")
        r = client.get(f"/api/v1/inspection/tasks?plan_id={plan['id']}", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["plan_id"] == plan["id"]

    def test_filter_by_station(self, client):
        # 卡 0ff95dca: create_task 校验 station 存在+归属, 裸编 station_id 已不可
        # (404), 须 seed 真实站点再关联
        from app.models.station import Station, StationStatus
        s = client._sesh
        sta = Station(name="过滤站A", code="FLTSTA", status=StationStatus.NORMAL)
        s.add(sta)
        s.commit()
        s.refresh(sta)
        _create_task(name="站A任务", station_id=sta.id, station_name="站A")
        _create_task(name="站B任务")
        r = client.get(f"/api/v1/inspection/tasks?station_id={sta.id}", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["station_id"] == sta.id

    def test_filter_by_keyword(self):
        _create_task(name="独特关键词XYZ任务")
        _create_task(name="普通任务")
        r = client.get("/api/v1/inspection/tasks?keyword=XYZ", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert "XYZ" in items[0]["name"]

    def test_filter_by_assignee(self):
        _create_task(name="张三的任务", assignee="张三丰")
        _create_task(name="李四的任务", assignee="李四")
        r = client.get("/api/v1/inspection/tasks?assignee=张三", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items
        assert all("张三" in (it["assignee"] or "") for it in items)

    def test_tasks_pagination(self):
        for i in range(3):
            _create_task(name=f"分页任务{i}")
        r = client.get("/api/v1/inspection/tasks?page=1&page_size=2", headers=_auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2
        assert data["total"] >= 3


class TestInspectionTemplate:
    """巡检模板 CRUD（spec 2.5）— 此前 0 测试"""

    def _create(self, name="UT模板", **overrides):
        payload = {"name": name, "items": [{"name": "温度", "unit": "℃"}]}
        payload.update(overrides)
        r = client.post("/api/v1/inspection/templates", json=payload, headers=_auth_headers())
        assert r.status_code == 200, f"创建模板失败: {r.status_code} {r.text}"
        return r.json()["data"]

    def test_template_crud_full(self):
        """创建 → 详情 → 更新 → 删除 全流程"""
        t = self._create(name="全流程模板")
        assert t["id"] > 0
        assert t["name"] == "全流程模板"
        assert t["item_count"] == 1
        assert t["status"] == "active"

        r = client.get(f"/api/v1/inspection/templates/{t['id']}", headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "全流程模板"

        r = client.put(f"/api/v1/inspection/templates/{t['id']}", json={
            "name": "改名模板", "status": "inactive",
        }, headers=_auth_headers())
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "改名模板"
        assert d["status"] == "inactive"

        assert client.delete(f"/api/v1/inspection/templates/{t['id']}", headers=_auth_headers()).status_code == 200
        assert client.get(f"/api/v1/inspection/templates/{t['id']}", headers=_auth_headers()).status_code == 404

    def test_create_template_target_bridge(self):
        """target 单选 → 桥接为 device_types 数组；target 取首元素"""
        t = self._create(name="桥接模板", target="inverter")
        assert t["device_types"] == ["inverter"]
        assert t["target"] == "inverter"

    def test_create_template_explicit_device_types(self):
        """显式 device_types 优先于 target"""
        t = self._create(name="显式模板", device_types=["inverter", "battery"])
        assert t["device_types"] == ["inverter", "battery"]
        assert t["target"] == "inverter"

    def test_create_template_invalid_status_400(self):
        """无效模板状态 → 422 (卡fbc05dc8: schema收紧Literal后Pydantic前置拦截)"""
        r = client.post("/api/v1/inspection/templates", json={
            "name": "坏状态", "status": "archived",
        }, headers=_auth_headers())
        assert r.status_code == 422

    def test_get_template_not_found_404(self):
        assert client.get("/api/v1/inspection/templates/99999", headers=_auth_headers()).status_code == 404

    def test_list_templates_filter_status(self):
        self._create(name="活跃模板", status="active")
        self._create(name="停用模板", status="inactive")
        r = client.get("/api/v1/inspection/templates?status=inactive", headers=_auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items
        assert all(it["status"] == "inactive" for it in items)

    def test_update_template_target_resets_device_types(self):
        """update 未提供 device_types 但提供 target → 用 target 重置 device_types"""
        t = self._create(name="更新桥接", device_types=["inverter"])
        r = client.put(f"/api/v1/inspection/templates/{t['id']}", json={
            "target": "battery",
        }, headers=_auth_headers())
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["device_types"] == ["battery"]
        assert d["target"] == "battery"


class TestInspectionResult:
    """巡检结果录入（按任务）— 此前 0 测试"""

    def _task(self):
        return _create_task(name="结果任务", total_items=3)

    def test_submit_normal_results(self):
        """正常录入多条结果"""
        t = self._task()
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [
                {"item_name": "温度", "item_value": "25", "result": "normal"},
                {"item_name": "电压", "value": "220", "result": "normal"},
            ],
        }, headers=_auth_headers())
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert len(data) == 2
        assert data[0]["item_name"] == "温度"

    def test_submit_abnormal_result(self):
        """异常结果 + 异常描述"""
        t = self._task()
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "温度", "item_value": "99",
                         "result": "abnormal", "abnormal_desc": "超温"}],
        }, headers=_auth_headers())
        assert r.status_code == 200
        d = r.json()["data"][0]
        assert d["result"] == "abnormal"
        assert d["abnormal_desc"] == "超温"

    def test_submit_results_empty_400(self):
        """空结果列表 → 400"""
        t = self._task()
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [],
        }, headers=_auth_headers())
        assert r.status_code == 400

    def test_submit_results_invalid_status_400(self):
        """无效结果状态 → 400"""
        t = self._task()
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "x", "result": "broken"}],
        }, headers=_auth_headers())
        assert r.status_code == 400

    def test_submit_results_task_not_found_404(self):
        """不存在任务录结果 → 404"""
        r = client.post("/api/v1/inspection/tasks/99999/results", json={
            "results": [{"item_name": "x"}],
        }, headers=_auth_headers())
        assert r.status_code == 404

    def test_value_field_bridged_to_item_value(self):
        """前端 value 字段桥接到 item_value，响应同时回传两别名"""
        t = self._task()
        r = client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "电压", "value": "380"}],
        }, headers=_auth_headers())
        assert r.status_code == 200
        d = r.json()["data"][0]
        assert d["item_value"] == "380"
        assert d["value"] == "380"

    def test_submit_results_appends_not_overwrites(self):
        """重复提交追加（非覆盖）"""
        t = self._task()
        client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "项1"}],
        }, headers=_auth_headers())
        client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "项2"}],
        }, headers=_auth_headers())
        r = client.get(f"/api/v1/inspection/tasks/{t['id']}/results", headers=_auth_headers())
        assert r.status_code == 200
        assert len(r.json()["data"]) == 2

    def test_list_results_task_not_found_404(self):
        assert client.get("/api/v1/inspection/tasks/99999/results",
                          headers=_auth_headers()).status_code == 404

    def test_list_results_ordering(self):
        """结果按 id 升序返回（录入顺序）"""
        t = self._task()
        client.post(f"/api/v1/inspection/tasks/{t['id']}/results", json={
            "results": [{"item_name": "第一"}, {"item_name": "第二"}, {"item_name": "第三"}],
        }, headers=_auth_headers())
        r = client.get(f"/api/v1/inspection/tasks/{t['id']}/results", headers=_auth_headers())
        names = [it["item_name"] for it in r.json()["data"]]
        assert names == ["第一", "第二", "第三"]


class TestInspectionPlanEdgeCases:
    """计划边界：无效 target 回退 / 合法 target 落库"""

    def test_create_plan_invalid_target_falls_back_to_all(self):
        """无效 target 不报错，回退 ALL"""
        r = client.post("/api/v1/inspection/plans", json={
            "name": "无效对象计划", "cycle": "weekly", "target": "nonexistent",
        }, headers=_auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["target"] == "all"

    def test_create_plan_valid_targets(self):
        """各合法 target 原样落库"""
        for tgt in ("all", "inverter", "battery", "charger", "gateway"):
            r = client.post("/api/v1/inspection/plans", json={
                "name": f"对象-{tgt}", "cycle": "daily", "target": tgt,
            }, headers=_auth_headers())
            assert r.status_code == 200
            assert r.json()["data"]["target"] == tgt


class TestInspectionUnauthenticated:
    """未认证访问 — inspection router 仅 require_write_permission 守卫：

    写端点(POST/PUT/DELETE)无 token → require_permission 拦 401；
    GET 端点对认证放行（router 无 get_current_user，enforce_auth 测试环境关闭），
    故此处只断言写端点。
    """

    def test_write_endpoints_require_auth(self):
        saved = client.headers.pop("Authorization", None)
        try:
            # POST 计划
            assert client.post("/api/v1/inspection/plans",
                               json={"name": "x", "cycle": "weekly"}).status_code in (401, 403)
            # POST 任务
            assert client.post("/api/v1/inspection/tasks",
                               json={"name": "x"}).status_code in (401, 403)
            # POST 模板
            assert client.post("/api/v1/inspection/templates",
                               json={"name": "x"}).status_code in (401, 403)
            # PUT 任务
            assert client.put("/api/v1/inspection/tasks/1",
                              json={"status": "completed"}).status_code in (401, 403)
            # DELETE 计划
            assert client.delete("/api/v1/inspection/plans/1").status_code in (401, 403)
        finally:
            if saved:
                client.headers["Authorization"] = saved


# ====================================================================
# 卡 c4cbcbf1: recorded_at ISO8601 解析 (py3.9 Z静默吞 + 坏值静默改用 server now)
# 旧实现: try: datetime.fromisoformat(item.recorded_at) except ValueError: pass
# → py3.9 客户端传 Z 抛错被 except:pass 静默, recorded_at 改用 server now (数据丢失);
# 坏值同样静默吞。改为共享 helper 显式 400。
# ====================================================================

_RECORDED_STATES = [
    pytest.param("2026-01-15T10:30:00Z", "2026-01-15T10:30:00", id="z"),
    pytest.param("2026-01-15T10:30:00+08:00", "2026-01-15T10:30:00", id="offset"),
    pytest.param("2026-01-15T10:30:00", "2026-01-15T10:30:00", id="naive"),
]


@pytest.mark.parametrize("value,stored", _RECORDED_STATES)
def test_create_results_recorded_at_valid_formats(value, stored):
    """recorded_at Z/offset/naive → 200, 墙钟落库回显输入值 (非静默 server now)。

    py3.9 旧实现 fromisoformat 不识 Z → except:pass → recorded_at 改用 server now,
    回显的不是输入时间 → RED。aware 落 naive 列剥 tzinfo 存墙钟。
    """
    task = _create_task(name="recorded_at解析任务")
    resp = client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={
        "results": [{"item_name": "检查项", "result": "normal", "recorded_at": value}],
    }, headers=_auth_headers())
    assert resp.status_code == 200, f"合法 recorded_at={value} 应200, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"][0]["recorded_at"] == stored, \
        f"recorded_at={value} 应回显 {stored}, 实际 {resp.json()['data'][0]['recorded_at']}"


def test_create_results_recorded_at_bad_400():
    """recorded_at 坏值 → 400 (非静默改用 server now 数据丢失)。"""
    task = _create_task(name="坏recorded_at任务")
    resp = client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={
        "results": [{"item_name": "检查项", "result": "normal", "recorded_at": "not-a-date"}],
    }, headers=_auth_headers())
    assert resp.status_code == 400, f"坏值应400非静默200, 实际 {resp.status_code}: {resp.text}"

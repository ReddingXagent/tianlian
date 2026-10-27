#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
巡检模板 + 结果 API 测试（/api/v1/inspection）

覆盖前端 inspectionAPI.templates（CRUD 5 端点）+ inspectionAPI.results（list/create 2 端点）。
路由未挂 get_current_user 依赖，无需认证。镜像 tests/test_inspection.py 的 test_db 模式。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _create_template(**overrides):
    """创建一个巡检模板，返回 data。"""
    payload = {
        "name": "充电桩周巡检模板",
        "target": "charger",
        "items": [
            {"name": "外观", "unit": "", "standard_value": "完好"},
            {"name": "输出电压", "unit": "V", "standard_value": "220"},
        ],
    }
    payload.update(overrides)
    resp = client.post("/api/v1/inspection/templates", json=payload)
    assert resp.status_code == 200, f"Create template failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


def _create_task(name="结果测试任务"):
    resp = client.post("/api/v1/inspection/tasks", json={"name": name, "total_items": 3})
    assert resp.status_code == 200, f"Create task failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


class TestInspectionTemplates:
    """巡检模板 /inspection/templates 端点"""

    def test_create_template_and_target_bridge(self):
        """创建模板 — target 桥接 device_types + item_count 计数"""
        data = _create_template(name="逆变器日检模板", target="inverter")
        assert data["id"] > 0
        assert data["name"] == "逆变器日检模板"
        # target 桥接：存为 device_types，回传 target 取首元素
        assert data["target"] == "inverter"
        assert data["device_types"] == ["inverter"]
        assert data["status"] == "active"  # 默认激活
        assert data["item_count"] == 2     # 2 个巡检项
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "外观"

    def test_create_template_invalid_status(self):
        """创建模板 — 非法 status 返回 422 (卡fbc05dc8: Literal前置拦截)"""
        resp = client.post("/api/v1/inspection/templates", json={
            "name": "x", "target": "all", "status": "frozen",
        })
        assert resp.status_code == 422

    def test_list_templates_pagination_and_status_filter(self):
        """列表 — 分页结构 + status 筛选"""
        _create_template(name="活跃模板A", target="all")
        _create_template(name="停用模板B", target="all", status="inactive")

        # 全量
        resp = client.get("/api/v1/inspection/templates")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data and "total" in data and "page" in data and "page_size" in data
        assert data["total"] >= 2

        # status 筛选 — 只剩停用模板
        resp = client.get("/api/v1/inspection/templates?status=inactive")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) >= 1
        assert all(t["status"] == "inactive" for t in items)

    def test_get_template_detail_and_404(self):
        """详情 — 存在返回 200；不存在返回 404"""
        t = _create_template(name="详情模板")
        resp = client.get(f"/api/v1/inspection/templates/{t['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "详情模板"

        assert client.get("/api/v1/inspection/templates/99999").status_code == 404

    def test_update_template_and_invalid_status(self):
        """更新 — 字段变更 + target 重置 device_types + 非法 status 400 + 不存在 404"""
        t = _create_template(name="更新前", target="charger")

        resp = client.put(f"/api/v1/inspection/templates/{t['id']}", json={
            "name": "更新后",
            "target": "battery",
            "items": [{"name": "SOC", "unit": "%", "standard_value": "80"}],
            "status": "inactive",
        })
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["name"] == "更新后"
        assert d["target"] == "battery"
        assert d["device_types"] == ["battery"]
        assert d["status"] == "inactive"
        assert d["item_count"] == 1

        # 非法 status
        bad = client.put(f"/api/v1/inspection/templates/{t['id']}", json={"status": "running"})
        assert bad.status_code == 422

        # 不存在
        assert client.put("/api/v1/inspection/templates/99999", json={"name": "x"}).status_code == 404

    def test_delete_template(self):
        """删除 — 删除后详情 404；重复删除 404"""
        t = _create_template(name="删除模板")
        assert client.delete(f"/api/v1/inspection/templates/{t['id']}").status_code == 200
        assert client.get(f"/api/v1/inspection/templates/{t['id']}").status_code == 404
        assert client.delete(f"/api/v1/inspection/templates/{t['id']}").status_code == 404


class TestInspectionResults:
    """巡检结果 /inspection/tasks/{task_id}/results 端点"""

    def test_create_results_batch_and_value_bridge(self):
        """批量录入 — value 桥接 item_value + 返回录入条数"""
        task = _create_task()
        resp = client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={
            "results": [
                {"item_name": "外观", "value": "完好", "result": "normal"},
                {"item_name": "温度", "value": "75", "result": "abnormal", "abnormal_desc": "过温"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        # value 桥接到 item_value
        assert data[0]["item_value"] == "完好"
        assert data[0]["result"] == "normal"
        assert data[1]["result"] == "abnormal"
        assert data[1]["abnormal_desc"] == "过温"
        # recorded_at 服务端自动填充
        assert data[0]["recorded_at"] is not None
        assert data[0]["task_id"] == task["id"]

    def test_create_results_invalid_result_status(self):
        """批量录入 — 非法 result 返回 400"""
        task = _create_task()
        resp = client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={
            "results": [{"item_name": "x", "value": "1", "result": "warning"}],
        })
        assert resp.status_code == 400

    def test_create_results_empty_batch(self):
        """批量录入 — 空批量返回 400"""
        task = _create_task()
        resp = client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={"results": []})
        assert resp.status_code == 400

    def test_create_results_task_not_found(self):
        """批量录入 — 任务不存在返回 404"""
        resp = client.post("/api/v1/inspection/tasks/99999/results", json={
            "results": [{"item_name": "x", "value": "1"}],
        })
        assert resp.status_code == 404

    def test_list_results_and_task_not_found(self):
        """查询 — 返回该任务结果（按 id 升序）；任务不存在 404"""
        task = _create_task()
        # 录入 2 条
        client.post(f"/api/v1/inspection/tasks/{task['id']}/results", json={
            "results": [
                {"item_name": "项A", "value": "1", "result": "normal"},
                {"item_name": "项B", "value": "2", "result": "normal"},
            ],
        })
        resp = client.get(f"/api/v1/inspection/tasks/{task['id']}/results")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert [r["item_name"] for r in data] == ["项A", "项B"]  # 升序

        # 任务不存在
        assert client.get("/api/v1/inspection/tasks/99999/results").status_code == 404

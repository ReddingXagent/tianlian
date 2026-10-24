"""
充电排序队列测试

覆盖:
- 模型 CRUD
- 队列入队/离队/优先级调整
- 规则 CRUD
- 排序逻辑 (priority_criteria 权重计算)
- 队列长度限制
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.models.charging_queue import ChargingQueue, ChargingQueueRule, ChargingQueueStatus
from app.services.charging_queue_service import (
    sort_queue,
    compute_sort_score,
    _parse_criteria,
    DEFAULT_PRIORITY_CRITERIA,
)


# ═══════════════════════════════════════════
# 排序逻辑单元测试
# ═══════════════════════════════════════════

class TestPriorityCriteriaParsing:
    """priority_criteria JSON 解析测试"""

    def test_default_criteria(self):
        parsed = _parse_criteria(None)
        assert len(parsed) == 2
        assert parsed[0]["field"] == "priority"

    def test_valid_criteria(self):
        raw = [
            {"field": "priority", "weight": 100, "direction": "asc"},
            {"field": "required_energy", "weight": 50, "direction": "desc"},
        ]
        parsed = _parse_criteria(raw)
        assert len(parsed) == 2
        assert parsed[1]["field"] == "required_energy"

    def test_invalid_direction_filtered(self):
        raw = [
            {"field": "priority", "weight": 10, "direction": "invalid"},
            {"field": "arrival_time", "weight": 20, "direction": "asc"},
        ]
        parsed = _parse_criteria(raw)
        assert len(parsed) == 1
        assert parsed[0]["field"] == "arrival_time"

    def test_empty_list_falls_back(self):
        parsed = _parse_criteria([])
        assert len(parsed) == len(DEFAULT_PRIORITY_CRITERIA)

    def test_json_string_input(self):
        import json
        raw = json.dumps([{"field": "priority", "weight": 10, "direction": "asc"}])
        parsed = _parse_criteria(raw)
        assert len(parsed) == 1


class TestSortQueue:
    """队列排序测试"""

    def _make_entry(self, eid=1, priority=100, arrival=None, energy=10.0, target_soc=0.8, current_soc=0.2):
        """创建轻量 mock 对象模拟 ChargingQueue"""
        class _E:
            pass
        e = _E()
        e.id = eid
        e.priority = priority
        e.arrival_time = arrival or datetime(2025, 1, 1, 12, 0, 0)
        e.required_energy_kwh = energy
        e.target_soc = target_soc
        e.current_soc = current_soc
        e.estimated_wait_minutes = 0
        e.status = "waiting"
        e.station_id = 1
        e.vehicle_id = eid
        e.enterprise_id = 0
        e.rule_id = None
        e.assigned_device_id = None
        e.created_at = datetime(2025, 1, 1)
        e.updated_at = datetime(2025, 1, 1)
        return e

    def test_fifo_default(self):
        """默认 FIFO: 同优先级按到达时间排序"""
        entries = [
            self._make_entry(eid=1, arrival=datetime(2025, 1, 1, 12, 10)),
            self._make_entry(eid=2, arrival=datetime(2025, 1, 1, 12, 5)),
            self._make_entry(eid=3, arrival=datetime(2025, 1, 1, 12, 0)),
        ]
        result = sort_queue(entries, DEFAULT_PRIORITY_CRITERIA)
        assert [e.id for e in result] == [3, 2, 1]

    def test_priority_overrides_fifo(self):
        """高优先级 (低数字) 排前面"""
        entries = [
            self._make_entry(eid=1, priority=50, arrival=datetime(2025, 1, 1, 12, 0)),
            self._make_entry(eid=2, priority=10, arrival=datetime(2025, 1, 1, 12, 30)),
            self._make_entry(eid=3, priority=100, arrival=datetime(2025, 1, 1, 12, 0)),
        ]
        result = sort_queue(entries, DEFAULT_PRIORITY_CRITERIA)
        assert result[0].id == 2  # priority=10 最优先
        assert result[-1].id == 3  # priority=100 最后

    def test_energy_desc_criteria(self):
        """能量需求大优先"""
        criteria = [
            {"field": "required_energy", "weight": 100, "direction": "desc"},
        ]
        entries = [
            self._make_entry(eid=1, energy=10.0),
            self._make_entry(eid=2, energy=50.0),
            self._make_entry(eid=3, energy=30.0),
        ]
        result = sort_queue(entries, criteria)
        assert [e.id for e in result] == [2, 3, 1]  # 50, 30, 10

    def test_mixed_weight_criteria(self):
        """混合权重: priority(asc) + energy(desc)"""
        criteria = [
            {"field": "priority", "weight": 100, "direction": "asc"},
            {"field": "required_energy", "weight": 50, "direction": "desc"},
        ]
        entries = [
            self._make_entry(eid=1, priority=50, energy=20.0),
            self._make_entry(eid=2, priority=50, energy=40.0),
            self._make_entry(eid=3, priority=10, energy=5.0),
        ]
        result = sort_queue(entries, criteria)
        # priority=10 最优先 → id=3 first
        assert result[0].id == 3
        # 同 priority=50 中 energy=40 更优先 → id=2 before id=1
        assert result[1].id == 2
        assert result[2].id == 1

    def test_empty_queue(self):
        assert sort_queue([], DEFAULT_PRIORITY_CRITERIA) == []

    def test_single_entry(self):
        entries = [self._make_entry(eid=1)]
        result = sort_queue(entries, DEFAULT_PRIORITY_CRITERIA)
        assert len(result) == 1
        assert result[0].id == 1

    def test_stable_sort(self):
        """同分条目保持原始顺序"""
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        entries = [
            self._make_entry(eid=1, priority=50, arrival=base_time, energy=10.0),
            self._make_entry(eid=2, priority=50, arrival=base_time, energy=10.0),
            self._make_entry(eid=3, priority=50, arrival=base_time, energy=10.0),
        ]
        result = sort_queue(entries, DEFAULT_PRIORITY_CRITERIA)
        assert [e.id for e in result] == [1, 2, 3]


# ═══════════════════════════════════════════
# API 集成测试
# ═══════════════════════════════════════════

class TestChargingQueueAPI:
    """充电队列 API 集成测试"""

    @pytest.fixture(autouse=True)
    def _seed_stations(self, client):
        """预建 station 1-5。

        team scoping（任务卡 e1f0e6d5）后 enqueue/get_charging_queue 校验站点存在性
        （不存在的站点对任何角色一律 404，admin 也不豁免存在性）。原测试用硬编码
        station_id 1-5 且不预建站点，此处补齐种子使集成测试反映新契约。
        """
        from app.models.station import Station, StationStatus
        s = client._sesh
        for i in range(1, 6):
            if not s.query(Station).filter(Station.id == i).first():
                s.add(Station(id=i, name=f"队列测试站{i}", code=f"CQTS{i}",
                              status=StationStatus.NORMAL))
        s.commit()
        yield

    def test_enqueue_and_list(self, client):
        """入队 + 查看队列"""
        # 先创建规则
        rule_resp = client.post("/api/v1/fleet/charging/rules", json={
            "enterprise_id": 1,
            "rule_name": "默认规则",
            "priority_criteria": [
                {"field": "priority", "weight": 100, "direction": "asc"},
                {"field": "arrival_time", "weight": 50, "direction": "asc"},
            ],
            "max_queue_length": 50,
            "enable": True,
        })
        assert rule_resp.status_code == 200
        rule_data = rule_resp.json()["data"]
        rule_id = rule_data["id"]

        # 入队两辆车
        for vid, pri in [(101, 50), (102, 10)]:
            r = client.post("/api/v1/fleet/charging/queue/enqueue", json={
                "station_id": 1,
                "vehicle_id": vid,
                "enterprise_id": 1,
                "required_energy_kwh": 30.0,
                "target_soc": 0.9,
                "current_soc": 0.2,
                "priority": pri,
            })
            assert r.status_code == 200, f"入队失败 vid={vid}: {r.text}"

        # 查看队列
        resp = client.get("/api/v1/fleet/charging/queue", params={"station_id": 1})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 2
        # priority=10 (vid=102) 应排前面
        assert items[0]["vehicle_id"] == 102
        assert items[1]["vehicle_id"] == 101

    def test_duplicate_enqueue_rejected(self, client):
        """重复入队返回 409"""
        client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 2,
            "vehicle_id": 201,
            "required_energy_kwh": 10.0,
            "priority": 50,
        })
        r = client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 2,
            "vehicle_id": 201,
            "required_energy_kwh": 10.0,
            "priority": 50,
        })
        assert r.status_code == 409

    def test_dequeue(self, client):
        """离队"""
        r = client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 3,
            "vehicle_id": 301,
            "priority": 30,
        })
        assert r.status_code == 200
        qid = r.json()["data"]["id"]

        # 离队
        r2 = client.delete(f"/api/v1/fleet/charging/queue/{qid}/dequeue", params={"reason": "manual"})
        assert r2.status_code == 200

        # 队列应为空
        r3 = client.get("/api/v1/fleet/charging/queue", params={"station_id": 3})
        assert r3.status_code == 200
        items = r3.json()["data"]["items"]
        assert len(items) == 0

    def test_priority_update(self, client):
        """优先级调整"""
        # 入队两辆
        r1 = client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 4, "vehicle_id": 401, "priority": 100,
        })
        r2 = client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 4, "vehicle_id": 402, "priority": 100,
        })
        q1_id = r1.json()["data"]["id"]
        q2_id = r2.json()["data"]["id"]

        # 提升 402 优先级 (降低数字)
        resp = client.patch(f"/api/v1/fleet/charging/queue/{q2_id}/priority", json={"priority": 5})
        assert resp.status_code == 200

        # 验证排序
        r = client.get("/api/v1/fleet/charging/queue", params={"station_id": 4})
        items = r.json()["data"]["items"]
        assert items[0]["vehicle_id"] == 402
        assert items[0]["priority"] == 5

    def test_queue_full_rejected(self, client):
        """队列满后拒绝入队"""
        # 创建 max_queue_length=2 的规则
        client.post("/api/v1/fleet/charging/rules", json={
            "enterprise_id": 5,
            "station_id": 5,
            "rule_name": "小队列",
            "max_queue_length": 2,
            "enable": True,
        })

        for vid in [501, 502]:
            client.post("/api/v1/fleet/charging/queue/enqueue", json={
                "station_id": 5, "vehicle_id": vid, "enterprise_id": 5,
            })

        # 第三辆应被拒绝
        r = client.post("/api/v1/fleet/charging/queue/enqueue", json={
            "station_id": 5, "vehicle_id": 503, "enterprise_id": 5,
        })
        assert r.status_code == 429

    def test_dequeue_not_found(self, client):
        """离队不存在的条目"""
        r = client.delete("/api/v1/fleet/charging/queue/99999/dequeue")
        assert r.status_code == 404

    def test_priority_update_not_found(self, client):
        r = client.patch("/api/v1/fleet/charging/queue/99999/priority", json={"priority": 1})
        assert r.status_code == 404


class TestChargingRuleAPI:
    """充电规则 CRUD API 测试"""

    def test_create_rule(self, client):
        r = client.post("/api/v1/fleet/charging/rules", json={
            "enterprise_id": 10,
            "rule_name": "测试规则A",
            "priority_criteria": [
                {"field": "priority", "weight": 100, "direction": "asc"},
            ],
            "max_queue_length": 20,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["rule_name"] == "测试规则A"
        assert data["max_queue_length"] == 20
        assert data["enable"] is True

    def test_list_rules(self, client):
        # 创建两条规则
        for name in ["规则B1", "规则B2"]:
            client.post("/api/v1/fleet/charging/rules", json={
                "enterprise_id": 20,
                "rule_name": name,
            })
        r = client.get("/api/v1/fleet/charging/rules", params={"enterprise_id": 20})
        assert r.status_code == 200
        rules = r.json()["data"]
        assert len(rules) >= 2

    def test_update_rule(self, client):
        r = client.post("/api/v1/fleet/charging/rules", json={
            "enterprise_id": 30,
            "rule_name": "待更新",
        })
        rid = r.json()["data"]["id"]

        r2 = client.put(f"/api/v1/fleet/charging/rules/{rid}", json={
            "rule_name": "已更新",
            "max_queue_length": 200,
            "enable": False,
        })
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert data["rule_name"] == "已更新"
        assert data["max_queue_length"] == 200
        assert data["enable"] is False

    def test_delete_rule(self, client):
        r = client.post("/api/v1/fleet/charging/rules", json={
            "enterprise_id": 40,
            "rule_name": "待删除",
        })
        rid = r.json()["data"]["id"]

        r2 = client.delete(f"/api/v1/fleet/charging/rules/{rid}")
        assert r2.status_code == 200

        # 确认已删除
        r3 = client.get("/api/v1/fleet/charging/rules", params={"enterprise_id": 40})
        rules = r3.json()["data"]
        assert all(rule["id"] != rid for rule in rules)

    def test_update_rule_not_found(self, client):
        r = client.put("/api/v1/fleet/charging/rules/99999", json={"rule_name": "x"})
        assert r.status_code == 404

    def test_delete_rule_not_found(self, client):
        r = client.delete("/api/v1/fleet/charging/rules/99999")
        assert r.status_code == 404

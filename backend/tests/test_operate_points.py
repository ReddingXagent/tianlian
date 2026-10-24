"""
运营-积分管理 API 测试

覆盖 /api/v1/operate/points 全部端点:
- POST   /points          创建积分规则
- GET    /points          积分规则列表(含 is_active 过滤)
- GET    /points/stats    积分统计
- GET    /points/records  积分流水
- GET    /points/{id}     规则详情(含 404)
- PUT    /points/{id}     更新规则
- DELETE /points/{id}     删除规则(含 404)
"""
import pytest

from app.models.points import PointsRule, PointsRecord, PointsRuleType, PointsRecordType


def _create_rule(client, name="充电返积分", points=10, is_active=True):
    """创建一条积分规则，返回响应 data"""
    r = client.post("/api/v1/operate/points", json={
        "name": name,
        "rule_type": "charge",
        "points": points,
        "unit": "每消费1元",
        "is_active": is_active,
        "description": "测试规则",
    })
    assert r.status_code == 200
    return r.json()["data"]


class TestOperatePoints:
    """积分规则 CRUD + 统计 + 流水"""

    def test_create_points_rule(self, client):
        """创建规则返回 id 与名称"""
        data = _create_rule(client, name="新建规则", points=5)
        assert data["id"] > 0
        assert data["name"] == "新建规则"

    def test_create_points_rule_validation_error(self, client):
        """points 为负数应被 Pydantic 拒绝(ge=0)"""
        r = client.post("/api/v1/operate/points", json={"name": "非法", "points": -1})
        assert r.status_code == 422

    def test_list_points_rules_and_filter(self, client):
        """列表返回全部 + is_active 过滤"""
        _create_rule(client, name="启用规则", points=1, is_active=True)
        _create_rule(client, name="停用规则", points=2, is_active=False)

        all_rules = client.get("/api/v1/operate/points").json()["data"]
        assert all_rules["total"] >= 2

        active = client.get("/api/v1/operate/points?is_active=true").json()["data"]
        assert active["total"] >= 1
        assert all(item["is_active"] is True for item in active["items"])

    def test_get_points_rule_detail_and_404(self, client):
        """详情正确 + 不存在返回 404"""
        data = _create_rule(client, name="详情规则", points=8)
        r = client.get(f"/api/v1/operate/points/{data['id']}")
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "详情规则"

        r404 = client.get("/api/v1/operate/points/999999")
        assert r404.status_code == 404

    def test_update_points_rule(self, client):
        """更新规则名称与积分"""
        data = _create_rule(client, name="旧名称", points=3)
        r = client.put(f"/api/v1/operate/points/{data['id']}", json={
            "name": "新名称", "points": 30,
        })
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["name"] == "新名称"

        # 校验持久化
        detail = client.get(f"/api/v1/operate/points/{data['id']}").json()["data"]
        assert detail["name"] == "新名称"
        assert detail["points"] == 30

    def test_delete_points_rule(self, client):
        """删除后查询应 404"""
        data = _create_rule(client, name="待删除", points=1)
        r = client.delete(f"/api/v1/operate/points/{data['id']}")
        assert r.status_code == 200
        assert client.get(f"/api/v1/operate/points/{data['id']}").status_code == 404

        # 重复删除返回 404
        assert client.delete(f"/api/v1/operate/points/{data['id']}").status_code == 404

    def test_points_stats(self, client):
        """统计: 规则数/启用数/流水数"""
        _create_rule(client, name="统计-启用", points=1, is_active=True)
        _create_rule(client, name="统计-停用", points=1, is_active=False)

        # 造一条积分流水
        s = client._sesh
        s.add(PointsRecord(
            user_id=101, user_type="app", rule_id=None,
            record_type=PointsRecordType.EARN, points=10,
            balance_before=0, balance_after=10, description="测试流水",
        ))
        s.commit()

        stats = client.get("/api/v1/operate/points/stats").json()["data"]
        assert stats["total_rules"] >= 2
        assert stats["active_rules"] >= 1
        assert stats["total_records"] >= 1
        assert stats["total_earned"] >= 10

    def test_points_records_list(self, client):
        """积分流水列表"""
        s = client._sesh
        s.add(PointsRecord(
            user_id=202, user_type="app",
            record_type=PointsRecordType.EARN, points=5,
            balance_before=0, balance_after=5,
        ))
        s.commit()

        r = client.get("/api/v1/operate/points/records?user_id=202")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1
        assert all(item["user_id"] == 202 for item in data["items"])

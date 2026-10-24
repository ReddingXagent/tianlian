"""
运营-积分管理 API 测试 (P0 运营核心补齐)

覆盖 /api/v1/operate/points:
- 积分规则 CRUD + 列表筛选(is_active/rule_type) + 详情 404
- 积分统计 (total_rules / active_rules / total_earned / total_records)
- 积分流水记录 (列表 + user_id 筛选)
- Pydantic 校验 (points < 0 → 422)
- 匿名拒绝 (401)
"""
from app.models.points import (
    PointsRule,
    PointsRecord,
    PointsRuleType,
    PointsRecordType,
)


def _seed_record(session, user_id=1, record_type=PointsRecordType.EARN,
                 points=10, before=0, after=10):
    rec = PointsRecord(
        user_id=user_id, record_type=record_type, points=points,
        balance_before=before, balance_after=after,
    )
    session.add(rec)
    session.commit()
    return rec


# ==================== 积分规则 CRUD ====================

class TestPointsRuleCrud:
    def test_create_rule(self, client):
        r = client.post("/api/v1/operate/points", json={
            "name": "充电积分", "rule_type": "charge", "points": 10, "unit": "每度",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] > 0
        assert data["name"] == "充电积分"

    def test_create_rule_negative_points(self, client):
        """points < 0 违反 ge=0 → 422"""
        r = client.post("/api/v1/operate/points", json={
            "name": "坏规则", "points": -1,
        })
        assert r.status_code == 422

    def test_list_rules_filter(self, client):
        client.post("/api/v1/operate/points", json={
            "name": "R1", "rule_type": "charge", "points": 1, "is_active": True,
        })
        client.post("/api/v1/operate/points", json={
            "name": "R2", "rule_type": "sign_in", "points": 2, "is_active": False,
        })
        # is_active 筛选
        items = client.get("/api/v1/operate/points?is_active=true").json()["data"]["items"]
        assert items and all(i["is_active"] is True for i in items)
        # rule_type 筛选
        items = client.get("/api/v1/operate/points?rule_type=sign_in").json()["data"]["items"]
        assert items and all(i["rule_type"] == "sign_in" for i in items)

    def test_get_rule(self, client):
        cid = client.post("/api/v1/operate/points", json={
            "name": "详情规则", "points": 5,
        }).json()["data"]["id"]
        r = client.get(f"/api/v1/operate/points/{cid}")
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "详情规则"

    def test_get_rule_not_found(self, client):
        assert client.get("/api/v1/operate/points/99999").status_code == 404

    def test_update_rule(self, client):
        cid = client.post("/api/v1/operate/points", json={
            "name": "旧", "points": 1,
        }).json()["data"]["id"]
        r = client.put(f"/api/v1/operate/points/{cid}", json={"name": "新", "points": 99})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "新"
        # points 已落库
        assert client.get(f"/api/v1/operate/points/{cid}").json()["data"]["points"] == 99

    def test_update_rule_not_found(self, client):
        r = client.put("/api/v1/operate/points/99999", json={"name": "x"})
        assert r.status_code == 404

    def test_delete_rule(self, client):
        cid = client.post("/api/v1/operate/points", json={
            "name": "待删", "points": 1,
        }).json()["data"]["id"]
        assert client.delete(f"/api/v1/operate/points/{cid}").status_code == 200
        assert client.get(f"/api/v1/operate/points/{cid}").status_code == 404

    def test_delete_rule_not_found(self, client):
        assert client.delete("/api/v1/operate/points/99999").status_code == 404


# ==================== 积分统计 ====================

class TestPointsStats:
    def test_stats(self, client):
        client.post("/api/v1/operate/points", json={
            "name": "A", "points": 10, "is_active": True,
        })
        client.post("/api/v1/operate/points", json={
            "name": "B", "points": 5, "is_active": False,
        })
        _seed_record(client._sesh, points=10)   # 一条 EARN +10 流水

        r = client.get("/api/v1/operate/points/stats")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_rules"] == 2
        assert d["active_rules"] == 1
        assert d["total_earned"] == 10
        assert d["total_records"] == 1


# ==================== 积分流水记录 ====================

class TestPointsRecords:
    def test_records_list(self, client):
        _seed_record(client._sesh, user_id=1, points=10, before=0, after=10)
        _seed_record(client._sesh, user_id=2, record_type=PointsRecordType.REDEEM,
                     points=-3, before=10, after=7)
        r = client.get("/api/v1/operate/points/records")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_records_filter_user(self, client):
        _seed_record(client._sesh, user_id=1, points=10)
        _seed_record(client._sesh, user_id=2, points=5)
        r = client.get("/api/v1/operate/points/records?user_id=1")
        items = r.json()["data"]["items"]
        assert items and all(i["user_id"] == 1 for i in items)

    def test_records_filter_type(self, client):
        _seed_record(client._sesh, record_type=PointsRecordType.EARN, points=10)
        _seed_record(client._sesh, record_type=PointsRecordType.REDEEM,
                     points=-3, before=10, after=7)
        r = client.get("/api/v1/operate/points/records?record_type=earn")
        items = r.json()["data"]["items"]
        assert items and all(i["record_type"] == "earn" for i in items)


# ==================== 积分流水录入 ====================

class TestPointsRecordCreate:
    """POST /points/records — 运营手动发放/调整积分流水

    PointsRecord 无业务自动写入点(充电/签到等场景未接线), 此端点供运营补录/赠送/调整
    积分流水, 同时为种子演示提供HTTP注入通道。balance_after 未显式传入时自动推导。
    """

    def test_create_earn_record_auto_balance_after(self, client):
        """earn 流水: balance_after 自动 = balance_before + points"""
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 501, "record_type": "earn", "points": 20, "balance_before": 0,
        })
        assert r.status_code == 200, r.text
        rid = r.json()["data"]["id"]
        obj = client._sesh.query(PointsRecord).get(rid)
        assert obj.points == 20
        assert obj.balance_before == 0
        assert obj.balance_after == 20

    def test_create_record_with_rule_and_order(self, client):
        """携带 rule_id/order_id/description 落库"""
        rule_id = client.post("/api/v1/operate/points", json={
            "name": "签到规则", "rule_type": "sign_in", "points": 5,
        }).json()["data"]["id"]
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 502, "record_type": "earn", "points": 5,
            "rule_id": rule_id, "order_id": 9001, "balance_before": 10,
            "description": "签到奖励",
        })
        assert r.status_code == 200
        obj = client._sesh.query(PointsRecord).get(r.json()["data"]["id"])
        assert obj.rule_id == rule_id
        assert obj.order_id == 9001
        assert obj.balance_after == 15
        assert obj.description == "签到奖励"

    def test_create_redeem_record_negative_points(self, client):
        """兑换流水允许负积分, balance_after 正确递减"""
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 503, "record_type": "redeem", "points": -8, "balance_before": 100,
        })
        assert r.status_code == 200
        obj = client._sesh.query(PointsRecord).get(r.json()["data"]["id"])
        assert obj.points == -8
        assert obj.balance_after == 92

    def test_create_record_explicit_balance_after_respected(self, client):
        """显式传 balance_after 时端点尊重传入值(校正场景)"""
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 504, "record_type": "adjust", "points": 0,
            "balance_before": 50, "balance_after": 200,
        })
        assert r.status_code == 200
        obj = client._sesh.query(PointsRecord).get(r.json()["data"]["id"])
        assert obj.balance_after == 200

    def test_create_record_invalid_type_rejected(self, client):
        """record_type 非法枚举值 → 422"""
        r = client.post("/api/v1/operate/points/records", json={
            "user_id": 1, "record_type": "bogus", "points": 1,
        })
        assert r.status_code == 422

    def test_create_record_missing_user_id_rejected(self, client):
        """user_id 必填缺失 → 422"""
        r = client.post("/api/v1/operate/points/records", json={
            "record_type": "earn", "points": 1,
        })
        assert r.status_code == 422

    def test_anon_create_record_denied(self, anon_client):
        """匿名写入流水 → 401"""
        r = anon_client.post("/api/v1/operate/points/records", json={
            "user_id": 1, "record_type": "earn", "points": 1,
        })
        assert r.status_code == 401


# ==================== 鉴权 ====================

class TestPointsAuth:
    def test_anon_list_denied(self, anon_client):
        assert anon_client.get("/api/v1/operate/points").status_code == 401

    def test_anon_create_denied(self, anon_client):
        r = anon_client.post("/api/v1/operate/points", json={"name": "x", "points": 1})
        assert r.status_code == 401

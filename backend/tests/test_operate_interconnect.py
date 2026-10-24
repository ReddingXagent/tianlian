"""
运营平台 - 互联互通对接 后端测试 (迁移自 admin, SPEC §2.5)

覆盖:
- 配置 CRUD + 联调测试 + 取值校验 (按运营团队隔离)
- 订单手动录入 + 列表筛选(来源平台) + 详情
- 团队隔离: A团队看不到B团队配置；伪造 X-Team-Id 不得越权 (任务卡 708350b3)
"""
import bcrypt
import pytest
from decimal import Decimal


# ─── 越权测试脚手架 ───

@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(operator, 具 operate:manage) + token，用于 team_id 越权测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="互联团队A", code="ICTA")
    tb = Team(name="互联团队B", code="ICTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "ic123456"
    ua = User(
        username="ic_eng_a", real_name="A工程师", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="ic_eng_b", real_name="B工程师", role=UserRole.OPERATOR,
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
        "tokens": {"a": _tok("ic_eng_a"), "b": _tok("ic_eng_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestOpsInterconnectConfig:
    """运营平台 - 互联互通平台配置"""

    def test_create_config_default_team(self, client):
        """无 X-Team-Id 头时默认 team_id=0"""
        resp = client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "华为云充电",
            "platform_code": "huawei",
            "api_base_url": "https://api.huawei-charge.com/v1",
            "auth_type": "apikey",
            "auth_params": {"app_key": "AK001", "app_secret": "SK001"},
            "revenue_share_ratio": 0.70,
            "data_sync_interval": 300,
            "status": "active",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["team_id"] == 0
        assert data["platform_name"] == "华为云充电"
        assert data["platform_code"] == "huawei"
        assert data["auth_params"]["app_key"] == "AK001"
        assert data["revenue_share_ratio"] == 0.7
        assert data["status"] == "active"

    def test_create_config_with_team(self, client, team_pair):
        """团队级用户创建的配置归属其 team；伪造 X-Team-Id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        resp = client.post(
            "/api/v1/operate/interconnect/configs",
            json={
                "platform_name": "国网",
                "platform_code": "sgcc",
                "api_base_url": "https://sgcc",
                "auth_type": "apikey",
            },
            # 故意伪造 X-Team-Id=B，资源仍归属 A
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["team_id"] == ta.id

    def test_invalid_platform_code(self, client):
        resp = client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "X", "platform_code": "unknown",
            "api_base_url": "https://x", "auth_type": "apikey",
        })
        assert resp.status_code == 400

    def test_invalid_auth_type(self, client):
        resp = client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "X", "platform_code": "teld",
            "api_base_url": "https://x", "auth_type": "jwt",
        })
        assert resp.status_code == 422  # Literal 前置到 Pydantic 层 (卡 6031add1)

    def test_list_and_filter(self, client):
        client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "国网", "platform_code": "sgcc",
            "api_base_url": "https://sgcc", "auth_type": "apikey",
        })
        client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "特来电", "platform_code": "teld",
            "api_base_url": "https://teld", "auth_type": "oauth",
        })

        # 全量
        resp = client.get("/api/v1/operate/interconnect/configs")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 2

        # 按平台编码筛选
        resp = client.get("/api/v1/operate/interconnect/configs?platform_code=teld")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_code"] == "teld"

        # 关键字搜索
        resp = client.get("/api/v1/operate/interconnect/configs?keyword=国")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "南网", "platform_code": "csg",
            "api_base_url": "https://csg", "auth_type": "apikey",
        })
        cid = r.json()["data"]["id"]

        # 详情
        assert client.get(f"/api/v1/operate/interconnect/configs/{cid}").status_code == 200

        # 更新
        resp = client.put(f"/api/v1/operate/interconnect/configs/{cid}", json={
            "status": "inactive", "revenue_share_ratio": 0.80,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "inactive"
        assert data["revenue_share_ratio"] == 0.8

        # 不存在
        assert client.put("/api/v1/operate/interconnect/configs/99999", json={"status": "active"}).status_code == 404

        # 删除
        assert client.delete(f"/api/v1/operate/interconnect/configs/{cid}").status_code == 200
        assert client.get(f"/api/v1/operate/interconnect/configs/{cid}").status_code == 404

    def test_config_404(self, client):
        assert client.get("/api/v1/operate/interconnect/configs/99999").status_code == 404

    def test_test_endpoint(self, client):
        r = client.post("/api/v1/operate/interconnect/configs", json={
            "platform_name": "华为", "platform_code": "huawei",
            "api_base_url": "https://api.huawei.com", "auth_type": "apikey",
        })
        cid = r.json()["data"]["id"]
        resp = client.post(f"/api/v1/operate/interconnect/configs/{cid}/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["reachable"] is True


class TestOpsInterconnectTeamIsolation:
    """运营平台 - 互联互通团队隔离"""

    def test_team_a_cannot_see_team_b(self, client, team_pair):
        """团队级用户只看本 team 配置；伪造 X-Team-Id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        # A 创建（故意伪造 X-Team-Id=B）
        resp_a = client.post(
            "/api/v1/operate/interconnect/configs",
            json={
                "platform_name": "团队A-华为",
                "platform_code": "huawei",
                "api_base_url": "https://a.huawei.com",
                "auth_type": "apikey",
            },
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["data"]["team_id"] == ta.id

        # B 创建
        resp_b = client.post(
            "/api/v1/operate/interconnect/configs",
            json={
                "platform_name": "团队B-国网",
                "platform_code": "sgcc",
                "api_base_url": "https://b.sgcc.com",
                "auth_type": "apikey",
            },
            headers=_h(team_pair["tokens"]["b"]),
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["data"]["team_id"] == tb.id

        # A 只看到自己（伪造 X-Team-Id=B 也无效）
        resp = client.get(
            "/api/v1/operate/interconnect/configs",
            headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_name"] == "团队A-华为"

        # B 只看到自己
        resp = client.get(
            "/api/v1/operate/interconnect/configs",
            headers=_h(team_pair["tokens"]["b"]),
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_name"] == "团队B-国网"

    def test_team_a_cannot_access_team_b_config(self, client, team_pair):
        """团队A无法查看/编辑/删除团队B的配置（404）。"""
        resp_b = client.post(
            "/api/v1/operate/interconnect/configs",
            json={
                "platform_name": "B专属",
                "platform_code": "teld",
                "api_base_url": "https://b.teld.com",
                "auth_type": "apikey",
            },
            headers=_h(team_pair["tokens"]["b"]),
        )
        cid_b = resp_b.json()["data"]["id"]

        # A 无法查看/更新/删除（伪造 X-Team-Id=B 也无效）
        ha = {**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(team_pair["teams"]["b"].id)}
        assert client.get(f"/api/v1/operate/interconnect/configs/{cid_b}", headers=ha).status_code == 404
        assert client.put(
            f"/api/v1/operate/interconnect/configs/{cid_b}",
            json={"status": "inactive"}, headers=ha,
        ).status_code == 404
        assert client.delete(f"/api/v1/operate/interconnect/configs/{cid_b}", headers=ha).status_code == 404

        # B 可以正常操作
        assert client.get(
            f"/api/v1/operate/interconnect/configs/{cid_b}",
            headers=_h(team_pair["tokens"]["b"]),
        ).status_code == 200


class TestOpsInterconnectOrder:
    """运营平台 - 互联互通导流订单"""

    def _make_config(self, client, code="huawei", team_id=None):
        headers = {"X-Team-Id": str(team_id)} if team_id else {}
        r = client.post(
            "/api/v1/operate/interconnect/configs",
            json={
                "platform_name": code.upper(), "platform_code": code,
                "api_base_url": "https://x", "auth_type": "apikey",
            },
            headers=headers,
        )
        return r.json()["data"]["id"]

    def test_create_order(self, client):
        cid = self._make_config(client)
        resp = client.post("/api/v1/operate/interconnect/orders", json={
            "platform_id": cid, "platform_code": "huawei",
            "outer_order_id": "HW20260720001", "outer_user_id": "U001",
            "station_id": "S1", "device_id": "D1",
            "charge_energy_kwh": 30.5, "total_amount": 45.75,
            "our_share": 32.02, "partner_share": 13.73,
            "status": "synced",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["outer_order_id"] == "HW20260720001"
        assert data["charge_energy_kwh"] == 30.5
        assert data["our_share"] == 32.02

    def test_create_order_platform_not_found(self, client):
        resp = client.post("/api/v1/operate/interconnect/orders", json={
            "platform_id": 99999, "platform_code": "huawei",
            "outer_order_id": "X1",
        })
        assert resp.status_code == 404

    def test_list_filter_by_platform(self, client):
        cid_h = self._make_config(client, "huawei")
        cid_t = self._make_config(client, "teld")
        client.post("/api/v1/operate/interconnect/orders", json={
            "platform_id": cid_h, "platform_code": "huawei", "outer_order_id": "H1",
        })
        client.post("/api/v1/operate/interconnect/orders", json={
            "platform_id": cid_t, "platform_code": "teld", "outer_order_id": "T1",
        })

        # 按来源平台编码筛选
        resp = client.get("/api/v1/operate/interconnect/orders?platform_code=huawei")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_code"] == "huawei"

        # 按 platform_id 筛选
        resp = client.get(f"/api/v1/operate/interconnect/orders?platform_id={cid_t}")
        assert resp.json()["data"]["total"] == 1

        # 关键字
        resp = client.get("/api/v1/operate/interconnect/orders?keyword=T1")
        assert resp.json()["data"]["total"] == 1

    def test_order_detail(self, client):
        cid = self._make_config(client)
        r = client.post("/api/v1/operate/interconnect/orders", json={
            "platform_id": cid, "platform_code": "huawei", "outer_order_id": "D1",
        })
        oid = r.json()["data"]["id"]
        resp = client.get(f"/api/v1/operate/interconnect/orders/{oid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["outer_order_id"] == "D1"
        assert client.get("/api/v1/operate/interconnect/orders/99999").status_code == 404

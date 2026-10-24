"""
管理后台 - 互联互通对接 后端测试 (SPEC §2.5)

覆盖:
- 配置 CRUD + 联调测试 + 取值校验
- 订单手动录入 + 列表筛选(来源平台) + 详情
"""
from decimal import Decimal


class TestInterconnectConfig:
    """互联互通平台配置"""

    def test_create_config(self, client):
        resp = client.post("/api/v1/admin/interconnect/configs", json={
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
        assert data["platform_name"] == "华为云充电"
        assert data["platform_code"] == "huawei"
        assert data["auth_params"]["app_key"] == "AK001"
        assert data["revenue_share_ratio"] == 0.7
        assert data["status"] == "active"

    def test_invalid_platform_code(self, client):
        resp = client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "X", "platform_code": "unknown",
            "api_base_url": "https://x", "auth_type": "apikey",
        })
        assert resp.status_code == 400

    def test_invalid_auth_type(self, client):
        resp = client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "X", "platform_code": "teld",
            "api_base_url": "https://x", "auth_type": "jwt",
        })
        assert resp.status_code == 422  # Literal 前置到 Pydantic 层 (卡 6031add1)

    def test_list_and_filter(self, client):
        client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "国网", "platform_code": "sgcc",
            "api_base_url": "https://sgcc", "auth_type": "apikey",
        })
        client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "特来电", "platform_code": "teld",
            "api_base_url": "https://teld", "auth_type": "oauth",
        })

        # 全量
        resp = client.get("/api/v1/admin/interconnect/configs")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 2

        # 按平台编码筛选
        resp = client.get("/api/v1/admin/interconnect/configs?platform_code=teld")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_code"] == "teld"

        # 关键字搜索
        resp = client.get("/api/v1/admin/interconnect/configs?keyword=国")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "南网", "platform_code": "csg",
            "api_base_url": "https://csg", "auth_type": "apikey",
        })
        cid = r.json()["data"]["id"]

        # 详情
        assert client.get(f"/api/v1/admin/interconnect/configs/{cid}").status_code == 200

        # 更新
        resp = client.put(f"/api/v1/admin/interconnect/configs/{cid}", json={
            "status": "inactive", "revenue_share_ratio": 0.80,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "inactive"
        assert data["revenue_share_ratio"] == 0.8

        # 不存在
        assert client.put("/api/v1/admin/interconnect/configs/99999", json={"status": "active"}).status_code == 404

        # 删除
        assert client.delete(f"/api/v1/admin/interconnect/configs/{cid}").status_code == 200
        assert client.get(f"/api/v1/admin/interconnect/configs/{cid}").status_code == 404

    def test_config_404(self, client):
        assert client.get("/api/v1/admin/interconnect/configs/99999").status_code == 404

    def test_test_endpoint(self, client):
        r = client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": "华为", "platform_code": "huawei",
            "api_base_url": "https://api.huawei.com", "auth_type": "apikey",
        })
        cid = r.json()["data"]["id"]
        resp = client.post(f"/api/v1/admin/interconnect/configs/{cid}/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["reachable"] is True


class TestInterconnectOrder:
    """互联互通导流订单"""

    def _make_config(self, client, code="huawei"):
        r = client.post("/api/v1/admin/interconnect/configs", json={
            "platform_name": code.upper(), "platform_code": code,
            "api_base_url": "https://x", "auth_type": "apikey",
        })
        return r.json()["data"]["id"]

    def test_create_order(self, client):
        cid = self._make_config(client)
        resp = client.post("/api/v1/admin/interconnect/orders", json={
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
        resp = client.post("/api/v1/admin/interconnect/orders", json={
            "platform_id": 99999, "platform_code": "huawei",
            "outer_order_id": "X1",
        })
        assert resp.status_code == 404

    def test_list_filter_by_platform(self, client):
        cid_h = self._make_config(client, "huawei")
        cid_t = self._make_config(client, "teld")
        client.post("/api/v1/admin/interconnect/orders", json={
            "platform_id": cid_h, "platform_code": "huawei", "outer_order_id": "H1",
        })
        client.post("/api/v1/admin/interconnect/orders", json={
            "platform_id": cid_t, "platform_code": "teld", "outer_order_id": "T1",
        })

        # 按来源平台编码筛选
        resp = client.get("/api/v1/admin/interconnect/orders?platform_code=huawei")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_code"] == "huawei"

        # 按 platform_id 筛选
        resp = client.get(f"/api/v1/admin/interconnect/orders?platform_id={cid_t}")
        assert resp.json()["data"]["total"] == 1

        # 关键字
        resp = client.get("/api/v1/admin/interconnect/orders?keyword=T1")
        assert resp.json()["data"]["total"] == 1

    def test_order_detail(self, client):
        cid = self._make_config(client)
        r = client.post("/api/v1/admin/interconnect/orders", json={
            "platform_id": cid, "platform_code": "huawei", "outer_order_id": "D1",
        })
        oid = r.json()["data"]["id"]
        resp = client.get(f"/api/v1/admin/interconnect/orders/{oid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["outer_order_id"] == "D1"
        assert client.get("/api/v1/admin/interconnect/orders/99999").status_code == 404

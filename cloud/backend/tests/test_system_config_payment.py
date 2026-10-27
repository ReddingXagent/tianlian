"""
系统配置 - 支付通道 API 测试 (admin spec §2.3)

覆盖 /api/v1/system-config/payment-channels:
- CRUD + 列表按 sort_order 排序
- Pydantic 校验 (channel_type 正则 / name 长度) → 422
- 资源不存在 → 404
- 匿名拒绝 (401)

支付通道以 JSON 存于 system_configs.payment_channels, 每测试独立 DB。
"""


class TestPaymentChannelList:
    def test_list_empty(self, client):
        r = client.get("/api/v1/system-config/payment-channels")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_sorted_by_sort_order(self, client):
        client.post("/api/v1/system-config/payment-channels", json={
            "name": "B通道", "channel_type": "im_b", "sort_order": 5,
        })
        client.post("/api/v1/system-config/payment-channels", json={
            "name": "A通道", "channel_type": "alipay", "sort_order": 1,
        })
        items = client.get("/api/v1/system-config/payment-channels").json()["data"]["items"]
        assert [i["name"] for i in items] == ["A通道", "B通道"]


class TestPaymentChannelCreate:
    def test_create_channel(self, client):
        r = client.post("/api/v1/system-config/payment-channels", json={
            "name": "IM-B支付", "channel_type": "im_b",
            "config": {"mch_id": "1234567890"},
            "api_key": "ak", "api_secret": "sk",
            "enabled": True, "sort_order": 1,
        })
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["id"] == 1
        assert data["name"] == "IM-B支付"
        assert data["channel_type"] == "im_b"
        assert data["enabled"] is True
        assert data["config"]["mch_id"] == "1234567890"
        # 创建后列表可见
        assert client.get("/api/v1/system-config/payment-channels").json()["data"]["total"] == 1

    def test_create_invalid_channel_type(self, client):
        """channel_type 不在正则白名单 → 422"""
        r = client.post("/api/v1/system-config/payment-channels", json={
            "name": "比特币", "channel_type": "bitcoin",
        })
        assert r.status_code == 422

    def test_create_short_name(self, client):
        """name < min_length(2) → 422"""
        r = client.post("/api/v1/system-config/payment-channels", json={
            "name": "A", "channel_type": "im_b",
        })
        assert r.status_code == 422

    def test_create_id_autoincrement(self, client):
        """新建 id = max(已有)+1"""
        first = client.post("/api/v1/system-config/payment-channels", json={
            "name": "通道一", "channel_type": "im_b",
        }).json()["data"]["id"]
        second = client.post("/api/v1/system-config/payment-channels", json={
            "name": "通道二", "channel_type": "alipay",
        }).json()["data"]["id"]
        assert second == first + 1


class TestPaymentChannelUpdate:
    def test_update_channel(self, client):
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "支付宝", "channel_type": "alipay", "enabled": True,
        }).json()["data"]["id"]
        r = client.put(f"/api/v1/system-config/payment-channels/{cid}", json={
            "enabled": False, "name": "支付宝(停用)",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["enabled"] is False
        assert data["name"] == "支付宝(停用)"

    def test_update_partial(self, client):
        """仅传 enabled, 其他字段不变"""
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "银联", "channel_type": "unionpay",
        }).json()["data"]["id"]
        r = client.put(f"/api/v1/system-config/payment-channels/{cid}", json={"enabled": False})
        data = r.json()["data"]
        assert data["enabled"] is False
        assert data["name"] == "银联"   # 未变

    def test_update_not_found(self, client):
        r = client.put("/api/v1/system-config/payment-channels/99999", json={"enabled": False})
        assert r.status_code == 404


class TestPaymentChannelDelete:
    def test_delete_channel(self, client):
        cid = client.post("/api/v1/system-config/payment-channels", json={
            "name": "银行转账", "channel_type": "bank_transfer",
        }).json()["data"]["id"]
        r = client.delete(f"/api/v1/system-config/payment-channels/{cid}")
        assert r.status_code == 200
        assert "已删除" in r.json()["message"]
        # 删除后列表回归空
        assert client.get("/api/v1/system-config/payment-channels").json()["data"]["total"] == 0

    def test_delete_not_found(self, client):
        assert client.delete("/api/v1/system-config/payment-channels/99999").status_code == 404


class TestPaymentChannelAuth:
    def test_anon_list_denied(self, anon_client):
        assert anon_client.get("/api/v1/system-config/payment-channels").status_code == 401

    def test_anon_create_denied(self, anon_client):
        r = anon_client.post("/api/v1/system-config/payment-channels", json={
            "name": "X", "channel_type": "im_b",
        })
        assert r.status_code == 401

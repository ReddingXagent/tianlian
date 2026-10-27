"""
管理后台 - 云服务配置 后端测试 (SPEC §2.4)

覆盖:
- 云配置 CRUD + 取值校验(提供商/同步策略/状态)
- 连通性测试(mock: 校验存储桶 + 同步端点可达)
"""


class TestCloudConfigs:
    """云平台连接配置(公有云/私有云)"""

    def test_create_cloud_config(self, client):
        resp = client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "云服务商生产环境",
            "provider": "cloud-a",
            "config_json": {"region": "cn-hangzhou", "endpoint": "oss-cn-hangzhou.cloud_providercs.com"},
            "bucket": "tianlian-prod",
            "sync_strategy": "realtime",
            "status": "active",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["config_name"] == "云服务商生产环境"
        assert data["provider"] == "cloud-a"
        assert data["config_json"]["region"] == "cn-hangzhou"
        assert data["bucket"] == "tianlian-prod"
        assert data["sync_strategy"] == "realtime"
        assert data["status"] == "active"

    def test_invalid_provider(self, client):
        resp = client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "X", "provider": "gcp",
            "bucket": "b1", "sync_strategy": "realtime", "status": "active",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_invalid_sync_strategy(self, client):
        resp = client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "X", "provider": "cloud-a",
            "bucket": "b1", "sync_strategy": "weekly", "status": "active",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_list_and_filter(self, client):
        client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "云服务商", "provider": "cloud-a",
            "bucket": "bucket-a", "sync_strategy": "realtime", "status": "active",
        })
        client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "服务商B云", "provider": "cloud-b",
            "bucket": "bucket-t", "sync_strategy": "hourly", "status": "inactive",
        })
        client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "私有云", "provider": "private",
            "bucket": "bucket-p", "sync_strategy": "daily", "status": "active",
        })

        # 全量
        resp = client.get("/api/v1/admin/cloud-configs")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 3

        # 按提供商筛选
        resp = client.get("/api/v1/admin/cloud-configs?provider=cloud_provider")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["provider"] == "cloud-a"

        # 按状态筛选
        resp = client.get("/api/v1/admin/cloud-configs?status=active")
        assert resp.json()["data"]["total"] == 2

        # 按同步策略筛选
        resp = client.get("/api/v1/admin/cloud-configs?sync_strategy=hourly")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["sync_strategy"] == "hourly"

        # 关键字搜索(配置名称)
        resp = client.get("/api/v1/admin/cloud-configs?keyword=服务商B")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "AWS", "provider": "aws",
            "bucket": "b1", "sync_strategy": "daily", "status": "active",
        })
        cid = r.json()["data"]["id"]

        # 详情
        assert client.get(f"/api/v1/admin/cloud-configs/{cid}").status_code == 200

        # 更新
        resp = client.put(f"/api/v1/admin/cloud-configs/{cid}", json={
            "status": "inactive",
            "sync_strategy": "hourly",
            "config_json": {"region": "us-east-1"},
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "inactive"
        assert data["sync_strategy"] == "hourly"
        assert data["config_json"]["region"] == "us-east-1"

        # 不存在
        assert client.put("/api/v1/admin/cloud-configs/99999", json={"status": "active"}).status_code == 404

        # 删除
        assert client.delete(f"/api/v1/admin/cloud-configs/{cid}").status_code == 200
        assert client.get(f"/api/v1/admin/cloud-configs/{cid}").status_code == 404

    def test_cloud_404(self, client):
        assert client.get("/api/v1/admin/cloud-configs/99999").status_code == 404

    def test_connectivity(self, client):
        r = client.post("/api/v1/admin/cloud-configs", json={
            "config_name": "云服务商", "provider": "cloud-a",
            "bucket": "tianlian-test", "sync_strategy": "realtime", "status": "active",
        })
        cid = r.json()["data"]["id"]
        resp = client.post(f"/api/v1/admin/cloud-configs/{cid}/test")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # mock: 存储桶 + 同步端点均可达即视为成功
        assert data["reachable"] is True
        assert data["storage_ok"] is True
        assert "tested_at" in data

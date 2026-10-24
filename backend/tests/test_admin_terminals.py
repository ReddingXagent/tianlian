"""
管理后台 - 终端管理 后端测试 (SPEC §2.4)

覆盖:
- 终端 CRUD + 取值校验(类型/状态)
- 按站点/类型/状态筛选 + 关键字搜索
"""
from datetime import datetime


class TestTerminals:
    """终端设备(摄像头/传感器/门禁)管理"""

    def test_create_terminal(self, client):
        resp = client.post("/api/v1/admin/terminals", json={
            "terminal_code": "CAM-A001",
            "terminal_type": "camera",
            "station_name": "郑州东站充电站",
            "ip_address": "192.168.1.101",
            "rtsp_url": "rtsp://10.0.0.1:554/stream1",
            "recording_config": {"enable": True, "quality": "1080p", "retention_days": 30},
            "status": "online",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["terminal_code"] == "CAM-A001"
        assert data["terminal_type"] == "camera"
        assert data["station_name"] == "郑州东站充电站"
        assert data["recording_config"]["quality"] == "1080p"
        assert data["status"] == "online"

    def test_invalid_terminal_type(self, client):
        resp = client.post("/api/v1/admin/terminals", json={
            "terminal_code": "X1", "terminal_type": "drone",
            "station_name": "S1", "status": "online",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_invalid_status(self, client):
        resp = client.post("/api/v1/admin/terminals", json={
            "terminal_code": "X1", "terminal_type": "camera",
            "station_name": "S1", "status": "running",
        })
        assert resp.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_duplicate_code(self, client):
        payload = {
            "terminal_code": "DUP-001", "terminal_type": "camera",
            "station_name": "S1", "status": "online",
        }
        assert client.post("/api/v1/admin/terminals", json=payload).status_code == 200
        resp = client.post("/api/v1/admin/terminals", json=payload)
        assert resp.status_code == 400

    def test_list_and_filter(self, client):
        client.post("/api/v1/admin/terminals", json={
            "terminal_code": "CAM-01", "terminal_type": "camera",
            "station_name": "郑州东站", "ip_address": "10.0.0.1", "status": "online",
        })
        client.post("/api/v1/admin/terminals", json={
            "terminal_code": "SENS-01", "terminal_type": "sensor",
            "station_name": "开封北站", "ip_address": "10.0.0.2", "status": "offline",
        })
        client.post("/api/v1/admin/terminals", json={
            "terminal_code": "AC-01", "terminal_type": "access_control",
            "station_name": "郑州东站", "ip_address": "10.0.0.3", "status": "online",
        })

        # 全量
        resp = client.get("/api/v1/admin/terminals")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 3

        # 按类型筛选
        resp = client.get("/api/v1/admin/terminals?terminal_type=camera")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["terminal_type"] == "camera"

        # 按站点筛选
        resp = client.get("/api/v1/admin/terminals?station_name=郑州东站")
        assert resp.json()["data"]["total"] == 2

        # 按状态筛选
        resp = client.get("/api/v1/admin/terminals?status=offline")
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "offline"

        # 关键字搜索(编号)
        resp = client.get("/api/v1/admin/terminals?keyword=SENS")
        assert resp.json()["data"]["total"] == 1

    def test_get_update_delete(self, client):
        r = client.post("/api/v1/admin/terminals", json={
            "terminal_code": "UPD-01", "terminal_type": "sensor",
            "station_name": "S1", "status": "online",
        })
        tid = r.json()["data"]["id"]

        # 详情
        assert client.get(f"/api/v1/admin/terminals/{tid}").status_code == 200

        # 更新
        resp = client.put(f"/api/v1/admin/terminals/{tid}", json={
            "status": "maintenance",
            "recording_config": {"enable": False},
            "ip_address": "10.0.0.99",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "maintenance"
        assert data["ip_address"] == "10.0.0.99"
        assert data["recording_config"]["enable"] is False

        # 不存在
        assert client.put("/api/v1/admin/terminals/99999", json={"status": "online"}).status_code == 404

        # 删除
        assert client.delete(f"/api/v1/admin/terminals/{tid}").status_code == 200
        assert client.get(f"/api/v1/admin/terminals/{tid}").status_code == 404

    def test_terminal_404(self, client):
        assert client.get("/api/v1/admin/terminals/99999").status_code == 404

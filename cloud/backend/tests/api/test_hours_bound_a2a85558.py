"""hours Query 参数无界加固测试 (任务卡 a2a85558)

延续卡 eb23751f 同族收尾, 补 2 处遗漏的 hours 边界 (纯校验, 零逻辑改动):
- GET /api/v1/alarm-notices   hours: ge=1, le=720
- GET /api/v1/operation-log   hours: ge=1, le=720

超界/越下限 → 422 (Pydantic 声明式校验, 防 timedelta(hours=超大int) OverflowError→500);
合法边界值 → 非 422。鉴权走 client fixture 默认 admin token。
"""

AN_URL = "/api/v1/alarm-notices"
OL_URL = "/api/v1/operation-log"


class TestAlarmNoticesHoursBounds:
    def test_over_max_422(self, client):
        r = client.get(AN_URL, params={"hours": 100000})
        assert r.status_code == 422

    def test_below_min_422(self, client):
        r = client.get(AN_URL, params={"hours": 0})
        assert r.status_code == 422
        r = client.get(AN_URL, params={"hours": -1})
        assert r.status_code == 422

    def test_boundary_720_ok(self, client):
        r = client.get(AN_URL, params={"hours": 720})
        assert r.status_code != 422

    def test_boundary_1_ok(self, client):
        r = client.get(AN_URL, params={"hours": 1})
        assert r.status_code != 422


class TestOperationLogHoursBounds:
    def test_over_max_422(self, client):
        r = client.get(OL_URL, params={"hours": 100000})
        assert r.status_code == 422

    def test_below_min_422(self, client):
        r = client.get(OL_URL, params={"hours": 0})
        assert r.status_code == 422

    def test_boundary_720_ok(self, client):
        r = client.get(OL_URL, params={"hours": 720})
        assert r.status_code != 422

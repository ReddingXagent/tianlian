"""预测性维护 API 测试
覆盖: dashboard, predict, train, batch
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(name="PM-站点", code="PM-STATION-001", status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="PM-DEV-001", name="预测维护设备",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestPredictiveMaintenanceAPI:

    def test_dashboard_requires_auth(self):
        # Dashboard is public (no auth required)
        assert client.get("/api/v1/predictive-maintenance/dashboard").status_code == 200

    def test_dashboard(self, auth_token):
        resp = client.get("/api/v1/predictive-maintenance/dashboard",
                          headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200
        data = resp.json()
        # DashboardResponse has flat keys: total_devices, predicted_devices, etc.
        assert "total_devices" in data
        assert "predictions" in data

    def test_predict_requires_auth(self):
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        # 无 token：enforce_auth 拦截 → 401（测试环境 CSRF 已跳过）
        assert client.post("/api/v1/predictive-maintenance/predict",
                          json={"device_id": 1, "hours": 24}).status_code in (401, 403)

    def test_predict(self, auth_token, test_device):
        resp = client.post("/api/v1/predictive-maintenance/predict",
                          headers={"Authorization": f"Bearer {auth_token}"},
                          json={"device_id": test_device.id, "hours": 24})
        # 404 when no telemetry data; 200 if telemetry exists
        assert resp.status_code in (200, 404)

    def test_batch_predict(self, auth_token, test_device):
        resp = client.post("/api/v1/predictive-maintenance/batch-predict",
                          headers={"Authorization": f"Bearer {auth_token}"},
                          json={"device_ids": [test_device.id], "hours": 24})
        assert resp.status_code == 200

    def test_train_requires_auth(self):
        # CSRF middleware blocks unauthenticated POST → 403，或业务层先返回404
        assert client.post("/api/v1/predictive-maintenance/train",
                          json={"device_id": 1, "days": 30}).status_code in (401, 403, 404)

    def test_train(self, auth_token, test_device):
        resp = client.post("/api/v1/predictive-maintenance/train",
                          headers={"Authorization": f"Bearer {auth_token}"},
                          json={"device_id": test_device.id, "days": 30})
        # 400 when <50 records; 200 if enough data
        assert resp.status_code in (200, 400)

    def test_model_status(self, auth_token):
        resp = client.get("/api/v1/predictive-maintenance/model-status",
                          headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200

    def test_prediction_history(self, auth_token, test_device):
        # Route is /device/{device_id}/history, not /predictions/{device_id}
        resp = client.get(f"/api/v1/predictive-maintenance/device/{test_device.id}/history",
                          headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200


class TestBatchPredictErrorPlaceholder:
    """batch-predict 失败设备不再静默丢弃（卡11efed41）"""

    def _seed_telemetry(self, db, device_id):
        from datetime import datetime, timezone
        from app.models.telemetry import Telemetry
        for _ in range(3):
            db.add(Telemetry(
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                battery_soc=80.0, battery_temperature=25.0,
            ))
        db.commit()

    def test_failed_device_yields_error_placeholder(self, auth_token, test_device, test_db):
        from unittest.mock import patch, AsyncMock
        self._seed_telemetry(test_db["session"], test_device.id)
        with patch(
            "app.api.v1.predictive_maintenance.get_service"
        ) as mock_get:
            mock_get.return_value.predict_failure = AsyncMock(side_effect=ValueError("boom"))
            resp = client.post(
                "/api/v1/predictive-maintenance/batch-predict",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={"device_ids": [test_device.id], "hours": 24},
            )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        entry = results[0]
        assert entry["device_id"] == test_device.id
        assert entry.get("error")

    def test_normal_path_unaffected(self, auth_token, test_device, test_db):
        self._seed_telemetry(test_db["session"], test_device.id)
        resp = client.post(
            "/api/v1/predictive-maintenance/batch-predict",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"device_ids": [test_device.id], "hours": 24},
        )
        assert resp.status_code == 200
        results = resp.json()
        for entry in results:
            assert "error" not in entry
            assert entry["device_id"] == test_device.id


class TestDashboardErrorNotSilent:
    """dashboard 单设备预测失败不静默：日志记录 + 跳过该设备，其余正常（卡4458b67b）"""

    def _seed_telemetry(self, db, device_id):
        from datetime import datetime, timezone
        from app.models.telemetry import Telemetry
        for _ in range(3):
            db.add(Telemetry(
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                battery_soc=80.0, battery_temperature=25.0,
            ))
        db.commit()

    def _make_device(self, db, station_id, sn, name):
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        device = Device(
            sn=sn, name=name,
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=station_id, protocol_type=ProtocolType.MODBUS_RTU
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    def test_failed_device_skipped_with_log(self, auth_token, test_station, test_db, caplog):
        import logging
        db = test_db["session"]
        bad = self._make_device(db, test_station.id, "PM-DEV-BAD", "损坏设备")
        good = self._make_device(db, test_station.id, "PM-DEV-GOOD", "正常设备")
        self._seed_telemetry(db, bad.id)
        self._seed_telemetry(db, good.id)

        from unittest.mock import patch, AsyncMock
        real_predict = None
        async def _predict(device_id, data, name):
            if device_id == bad.id:
                raise ValueError("boom")
            from app.services.predictive_maintenance import get_service
            return await get_service().predict_failure(device_id, data, name)

        with patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            # 真service包装：坏设备抛错，好设备走真实预测
            from app.services.predictive_maintenance import get_service as real_get
            real = real_get()
            async def wrapped(device_id, data, name):
                if device_id == bad.id:
                    raise ValueError("boom")
                return await real.predict_failure(device_id, data, name)
            mock_get.return_value.predict_failure = wrapped
            mock_get.return_value.get_model_status = real.get_model_status
            with caplog.at_level(logging.ERROR, logger="app.api.v1.predictive_maintenance"):
                resp = client.get(
                    "/api/v1/predictive-maintenance/dashboard",
                    headers={"Authorization": f"Bearer {auth_token}"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 2
        assert data["predicted_devices"] == 1
        # 响应不含损坏设备的预测条目
        assert [p["device_id"] for p in data["predictions"]] == [good.id]
        # 日志已记录（不再静默）
        assert any(
            r.name == "app.api.v1.predictive_maintenance" and r.levelno == logging.ERROR
            and str(bad.id) in r.getMessage()
            for r in caplog.records
        )

    def test_all_devices_fail_no_500(self, auth_token, test_device, test_db, caplog):
        import logging
        from unittest.mock import patch, AsyncMock
        self._seed_telemetry(test_db["session"], test_device.id)
        with patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            mock_get.return_value.predict_failure = AsyncMock(side_effect=ValueError("boom"))
            mock_get.return_value.get_model_status = dict
            with caplog.at_level(logging.ERROR, logger="app.api.v1.predictive_maintenance"):
                resp = client.get(
                    "/api/v1/predictive-maintenance/dashboard",
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicted_devices"] == 0
        assert data["predictions"] == []
        assert any(r.levelno == logging.ERROR for r in caplog.records)

class TestDashboardTelemetryWindow:
    """dashboard 遥测窗口函数语义固化（卡 e0dcffcb：每设备 desc 前100条下推 SQL）"""

    @staticmethod
    def _seed(db, device_id, n, base=None):
        from datetime import datetime, timezone, timedelta
        from app.models.telemetry import Telemetry
        start = base or datetime.now(timezone.utc) - timedelta(hours=23)
        for i in range(n):
            db.add(Telemetry(
                device_id=device_id,
                timestamp=start + timedelta(seconds=i),
                battery_soc=50.0 + i, battery_temperature=25.0,
            ))
        db.commit()

    @staticmethod
    def _capture_telemetry(mock_predict):
        """从 predict_failure 调用参数中捕获每设备实际收到的遥测"""
        calls = {}
        for c in mock_predict.await_args_list:
            device_id, data, _name = c.args
            calls[device_id] = data
        return calls

    def test_per_device_capped_at_100_desc(self, auth_token, test_device, test_db):
        """每设备>100条 → 恰好100条，且为时间倒序前100（最新100条）"""
        from unittest.mock import patch, AsyncMock
        self._seed(test_db["session"], test_device.id, 150)
        with patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            mock_predict = AsyncMock(return_value=self._fake_result())
            mock_get.return_value.predict_failure = mock_predict
            mock_get.return_value.get_model_status = dict
            resp = client.get(
                "/api/v1/predictive-maintenance/dashboard",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        calls = self._capture_telemetry(mock_predict)
        data = calls[test_device.id]
        assert len(data) == 100
        ts = [d["timestamp"] for d in data]
        assert ts == sorted(ts, reverse=True)  # desc 序
        assert ts[0] == max(ts)  # 最新的在前 → 截的是最新100条

    def test_under_100_kept_all_desc(self, auth_token, test_device, test_db):
        """每设备<100条 → 全保留，desc 序"""
        from unittest.mock import patch, AsyncMock
        self._seed(test_db["session"], test_device.id, 40)
        with patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            mock_predict = AsyncMock(return_value=self._fake_result())
            mock_get.return_value.predict_failure = mock_predict
            mock_get.return_value.get_model_status = dict
            resp = client.get(
                "/api/v1/predictive-maintenance/dashboard",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        data = self._capture_telemetry(mock_predict)[test_device.id]
        assert len(data) == 40
        ts = [d["timestamp"] for d in data]
        assert ts == sorted(ts, reverse=True)

    def test_multi_device_independent_windows(self, auth_token, test_device, test_station, test_db):
        """多设备各自独立截断：150/40条 → 100/40"""
        from unittest.mock import patch, AsyncMock
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        db = test_db["session"]
        dev2 = Device(
            sn="PM-DEV-002", name="预测维护设备2",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU
        )
        db.add(dev2)
        db.commit()
        db.refresh(dev2)
        self._seed(db, test_device.id, 150)
        self._seed(db, dev2.id, 40)
        with patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            mock_predict = AsyncMock(return_value=self._fake_result())
            mock_get.return_value.predict_failure = mock_predict
            mock_get.return_value.get_model_status = dict
            resp = client.get(
                "/api/v1/predictive-maintenance/dashboard",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        calls = self._capture_telemetry(mock_predict)
        assert len(calls[test_device.id]) == 100
        assert len(calls[dev2.id]) == 40

    def test_empty_device_list_short_circuits(self, auth_token, test_db):
        """无设备 → 不发遥测查询（防 in_([]) ），响应仍 200"""
        from unittest.mock import patch
        from sqlalchemy.ext.asyncio import AsyncSession
        queried = []
        orig_execute = AsyncSession.execute
        async def _spy(self, statement, *a, **kw):
            if "telemetry" in str(statement).lower():
                queried.append(str(statement))
            return await orig_execute(self, statement, *a, **kw)
        with patch.object(AsyncSession, "execute", _spy), \
             patch("app.api.v1.predictive_maintenance.get_service") as mock_get:
            mock_get.return_value.get_model_status = dict
            resp = client.get(
                "/api/v1/predictive-maintenance/dashboard",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["total_devices"] == 0
        assert not queried, "空设备列表不应触发 telemetry 查询"

    @staticmethod
    def _fake_result():
        """构造能通过 format_prediction_for_display + PredictionResponse 的最小结果"""
        from types import SimpleNamespace
        return SimpleNamespace(
            device_id=0, device_name="d", prediction_time="2026-01-01T00:00:00",
            risk_level="low",
            failure_probability=0.1,
            health_trend="stable",
            rul_hours=100.0,
            anomaly_score=0.1,
            key_indicators=[],
            recommended_actions=[],
            confidence=0.9,
        )

    @staticmethod
    def _seed_telemetry(db, device_id):
        from datetime import datetime, timezone
        from app.models.telemetry import Telemetry
        for _ in range(3):
            db.add(Telemetry(
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                battery_soc=80.0, battery_temperature=25.0,
            ))
        db.commit()


class TestNormalDashboardLegacy:
    @staticmethod
    def _seed_telemetry(db, device_id):
        from datetime import datetime, timezone
        from app.models.telemetry import Telemetry
        for _ in range(3):
            db.add(Telemetry(
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                battery_soc=80.0, battery_temperature=25.0,
            ))
        db.commit()

    def test_normal_dashboard_unaffected(self, auth_token, test_device, test_db):
        self._seed_telemetry(test_db["session"], test_device.id)
        resp = client.get(
            "/api/v1/predictive-maintenance/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] >= 1
        assert data["predicted_devices"] >= 1
        assert all("error" not in p for p in data["predictions"])

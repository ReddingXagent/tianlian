"""遥测大表物化聚合读放大修复测试 (卡 7c1c396d)

覆盖三个读放大缺口:
1. POST /analytics/anomaly-detection   AnomalyDetectionRequest.hours 无界 → Field(24, ge=1, le=168)
2. GET  /predictive-maintenance/device/{id}/history   日聚合下推 SQL, 响应契约不变
3. POST /analytics/health-score         Telemetry 物化列裁剪, 响应契约不变
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry

ANOMALY_URL = "/api/v1/analytics/anomaly-detection"
HISTORY_URL = "/api/v1/predictive-maintenance/device/{device_id}/history"
HEALTH_URL = "/api/v1/analytics/health-score"


# ─── helpers ───

def _seed_device(session, tag="7c1c396d"):
    st = Station(
        name=f"物化站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址", status=StationStatus.NORMAL,
    )
    session.add(st); session.commit(); session.refresh(st)
    d = Device(
        sn=f"SN-{uuid.uuid4().hex[:8]}", name=f"物化设备{tag}",
        code=f"DEV{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=st.id,
    )
    session.add(d); session.commit(); session.refresh(d)
    return d


def _seed_telemetry(session, device_id, rows):
    """rows: (timestamp, battery_soc, battery_temperature, battery_soh, bms_alarm_word)"""
    for ts, soc, temp, soh, alarm in rows:
        session.add(Telemetry(
            device_id=device_id, timestamp=ts,
            battery_soc=soc, battery_temperature=temp,
            battery_soh=soh, bms_alarm_word=alarm,
        ))
    session.commit()


# ─── 1. anomaly hours 边界 ───

class TestAnomalyHoursBounds:

    @pytest.mark.parametrize("hours", [0, -1, 10**9, 169])
    def test_out_of_bounds_rejected(self, client, hours):
        r = client.post(ANOMALY_URL, json={"device_id": 1, "hours": hours})
        assert r.status_code == 422, f"hours={hours} 应 422, got {r.status_code}"

    def test_bounds_valid(self, client):
        """hours=1/24/168 均合法（不因边界被拒）。"""
        for hours in (1, 24, 168):
            r = client.post(ANOMALY_URL, json={"device_id": 1, "hours": hours})
            assert r.status_code != 422, f"hours={hours} 不应 422: {r.text[:200]}"

    def test_hours_24_returns_200_with_data(self, client):
        s = client._sesh
        d = _seed_device(s)
        base = datetime.now(timezone.utc) - timedelta(minutes=30)
        _seed_telemetry(s, d.id, [
            (base + timedelta(minutes=i), 50.0, 25.0, 95.0, 0) for i in range(6)
        ])
        r = client.post(ANOMALY_URL, json={"device_id": d.id, "hours": 24})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["device_id"] == d.id
        assert isinstance(body["anomaly_score"], float)
        assert body["severity"] in ("low", "medium", "high", "critical")


# ─── 2. prediction_history 日聚合下推 SQL ───

class TestPredictionHistoryContract:

    def test_daily_structure_and_values(self, client):
        s = client._sesh
        d = _seed_device(s)
        day1 = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0)
        day2 = day1 + timedelta(days=1)
        _seed_telemetry(s, d.id, [
            # day1: soc 60/80 → avg 70; temp 20/30 → avg 25; soh 全 None → None; alarm 1/4 行
            (day1, 60.0, 20.0, None, 0),
            (day1 + timedelta(hours=1), 80.0, 30.0, None, 1),
            (day1 + timedelta(hours=2), None, None, None, 0),
            (day1 + timedelta(hours=3), None, None, None, 1),
            # day2: soh 90/100 → avg 95; 无告警
            (day2, 70.0, 25.0, 90.0, 0),
            (day2 + timedelta(hours=1), 70.0, 25.0, 100.0, 0),
        ])
        r = client.get(HISTORY_URL.format(device_id=d.id), params={"days": 7})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["device_id"] == d.id
        assert body["period_days"] == 7
        assert isinstance(body["device_name"], str)
        history = body["history"]
        assert len(history) == 2

        # 排序: 日期升序
        assert [h["date"] for h in history] == sorted(h["date"] for h in history)
        h1, h2 = history

        # day1: avg 只统计非 None 值 (soc/temp 各 2 行), soh 无值 → None
        assert h1["date"] == day1.strftime("%Y-%m-%d")
        assert h1["avg_soc"] == pytest.approx(70.0)
        assert h1["avg_temperature"] == pytest.approx(25.0)
        assert h1["avg_soh"] is None
        assert h1["record_count"] == 4
        assert h1["anomaly_rate"] == pytest.approx(2 / 4)

        # day2: 无告警 → rate 0
        assert h2["date"] == day2.strftime("%Y-%m-%d")
        assert h2["avg_soh"] == pytest.approx(95.0)
        assert h2["record_count"] == 2
        assert h2["anomaly_rate"] == pytest.approx(0.0)

        # 字段齐全 (旧实现输出结构一字不变)
        for h in history:
            assert set(h.keys()) == {
                "date", "avg_soc", "avg_temperature", "avg_soh",
                "anomaly_rate", "record_count",
            }

    def test_empty_window_returns_empty_history(self, client):
        s = client._sesh
        d = _seed_device(s)
        r = client.get(HISTORY_URL.format(device_id=d.id), params={"days": 7})
        assert r.status_code == 200
        assert r.json()["history"] == []

    def test_days_out_of_window_excluded(self, client):
        """窗口外旧数据不进聚合。"""
        s = client._sesh
        d = _seed_device(s)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        _seed_telemetry(s, d.id, [(old, 10.0, 10.0, 50.0, 0)])
        r = client.get(HISTORY_URL.format(device_id=d.id), params={"days": 7})
        assert r.status_code == 200
        assert r.json()["history"] == []


# ─── 3. health-score 契约 ───

class TestHealthScoreContract:

    def test_health_score_success(self, client):
        s = client._sesh
        d = _seed_device(s)
        base = datetime.now(timezone.utc) - timedelta(hours=10)
        _seed_telemetry(s, d.id, [
            (base + timedelta(hours=i), 60.0 + i, 25.0, 95.0, 0) for i in range(6)
        ])
        r = client.post(HEALTH_URL, json={"device_id": d.id, "days": 7})
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["device_id"] == d.id
        assert body["device_name"] == d.name
        assert 0 <= body["overall_score"] <= 100
        assert set(body["score_breakdown"].keys()) == {
            "battery_health", "temperature_stability", "power_efficiency",
            "alarm_frequency", "operational_consistency",
        }
        assert body["risk_level"] in ("low", "medium", "high", "critical")
        assert body["trend"] in ("improving", "stable", "degrading")
        assert isinstance(body["key_issues"], list)
        assert isinstance(body["recommendations"], list)

    def test_anomaly_detection_values_unchanged(self, client):
        """列裁剪后检测数值不漂移: SOC 过低 → soc_low critical。"""
        s = client._sesh
        d = _seed_device(s)
        base = datetime.now(timezone.utc) - timedelta(hours=2)
        rows = [(base + timedelta(minutes=i), 50.0, 25.0, 95.0, 0) for i in range(5)]
        rows.append((base + timedelta(minutes=5), 5.0, 25.0, 95.0, 0))
        _seed_telemetry(s, d.id, rows)
        r = client.post(ANOMALY_URL, json={"device_id": d.id, "hours": 24})
        assert r.status_code == 200
        anomalies = r.json()["detected_anomalies"]
        soc = [a for a in anomalies if a["type"] == "soc_low"]
        assert soc, f"应检出 soc_low: {anomalies}"
        assert soc[0]["severity"] == "critical"
        assert soc[0]["value"] == pytest.approx(5.0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
效率报表 API 测试（/api/v1/reports）

覆盖设备利用率排名、充电效率排名、光伏PR排名、V2G运营报表。
所有端点均需认证。
"""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login(username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.fixture
def seed_report_data(test_db):
    """seed 站点 + 设备(利用率/光伏PR) + 充电效率日志"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.device_efficiency_log import DeviceEfficiencyLog
    s = test_db["session"]

    st_a = Station(name="报表站A", code="RPT001", address="地址A", status=StationStatus.NORMAL)
    st_b = Station(name="报表站B", code="RPT002", address="地址B", status=StationStatus.NORMAL)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    dev_low = Device(sn="SN-EFF-LOW", name="低利用充电桩", code="EFFLOW",
                    type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                    station_id=st_a.id, rated_power=100.0, utilization_rate=15.0)
    dev_over = Device(sn="SN-EFF-OVR", name="过载充电桩", code="EFFOVR",
                     type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                     station_id=st_a.id, rated_power=100.0, utilization_rate=95.0)
    dev_normal = Device(sn="SN-EFF-NOR", name="正常充电桩", code="EFFNOR",
                       type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                       station_id=st_b.id, rated_power=100.0, utilization_rate=60.0)
    dev_pv_hi = Device(sn="SN-EFF-PV1", name="高效光伏", code="EFFPV1",
                      type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                      station_id=st_a.id, rated_power=50.0, utilization_rate=70.0,
                      pv_pr_ratio=0.85, total_runtime_hours=100.0, total_generation_kwh=4000.0)
    dev_pv_lo = Device(sn="SN-EFF-PV2", name="低效光伏", code="EFFPV2",
                      type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                      station_id=st_b.id, rated_power=50.0,
                      pv_pr_ratio=0.50, total_runtime_hours=100.0, total_generation_kwh=2000.0)
    s.add_all([dev_low, dev_over, dev_normal, dev_pv_hi, dev_pv_lo])
    s.commit()
    for d in (dev_low, dev_over, dev_normal, dev_pv_hi, dev_pv_lo):
        s.refresh(d)

    # 充电效率日志（metric_type=charge），同一时刻各一条
    now = datetime(2026, 7, 21, 10, 0, 0)
    s.add_all([
        DeviceEfficiencyLog(device_id=dev_low.id, station_id=st_a.id,
                            metric_type="charge", metric_value=65.0,
                            recorded_at=now, log_date="2026-07-21"),
        DeviceEfficiencyLog(device_id=dev_over.id, station_id=st_a.id,
                            metric_type="charge", metric_value=92.0,
                            recorded_at=now, log_date="2026-07-21"),
    ])
    s.commit()

    return {
        "st_a": st_a, "st_b": st_b,
        "dev_low": dev_low, "dev_over": dev_over, "dev_normal": dev_normal,
        "dev_pv_hi": dev_pv_hi, "dev_pv_lo": dev_pv_lo,
    }


class TestEfficiencyReports:
    """效率报表 /reports 端点"""

    def test_utilization_report_structure(self, seed_report_data):
        """利用率排名 — 结构正确 + 倒序"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/utilization", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data and data["total"] >= 5
        assert "alerts" in data
        assert "low_utilization" in data["alerts"]
        assert "overload" in data["alerts"]
        # 利用率应倒序排列
        rates = [it["utilization_rate"] for it in data["items"]]
        assert rates == sorted(rates, reverse=True)

    def test_utilization_low_and_overload_alerts(self, seed_report_data):
        """利用率预警 — <30% 进低利用，>90% 进过载"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        alerts = client.get("/api/v1/reports/utilization", headers=h).json()["data"]["alerts"]
        low_ids = [it["device_id"] for it in alerts["low_utilization"]["items"]]
        assert seed_report_data["dev_low"].id in low_ids
        over_ids = [it["device_id"] for it in alerts["overload"]["items"]]
        assert seed_report_data["dev_over"].id in over_ids

    def test_utilization_filter_by_station(self, seed_report_data):
        """利用率 — 按 station_id 过滤"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        sid = seed_report_data["st_a"].id
        resp = client.get(f"/api/v1/reports/utilization?station_id={sid}", headers=h)
        assert resp.status_code == 200
        for it in resp.json()["data"]["items"]:
            assert it["station_id"] == sid

    def test_efficiency_report_with_logs(self, seed_report_data):
        """充电效率排名 — 仅含 charge 日志设备 + 默认阈值预警"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/efficiency", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = [it["device_id"] for it in data["items"]]
        assert seed_report_data["dev_low"].id in ids
        assert seed_report_data["dev_over"].id in ids
        # 默认阈值 70%：dev_low=65 进 abnormal，dev_over=92 不进
        abnormal_ids = [it["device_id"] for it in data["alerts"]["abnormal_low_efficiency"]["items"]]
        assert seed_report_data["dev_low"].id in abnormal_ids
        assert seed_report_data["dev_over"].id not in abnormal_ids

    def test_efficiency_min_efficiency_param(self, seed_report_data):
        """min_efficiency 参数 — 调低阈值后 dev_low 不再预警"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/efficiency?min_efficiency=60", headers=h)
        assert resp.status_code == 200
        abnormal = resp.json()["data"]["alerts"]["abnormal_low_efficiency"]
        # 阈值是 float，渲染为 "<60.0%"
        assert "<60" in abnormal["threshold"]
        ids = [it["device_id"] for it in abnormal["items"]]
        assert seed_report_data["dev_low"].id not in ids  # 65 > 60

    def test_generation_report(self, seed_report_data):
        """光伏PR排名 — 仅 PV 设备 + 高/低性能分组"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/generation", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = [it["device_id"] for it in data["items"]]
        assert seed_report_data["dev_pv_hi"].id in ids
        assert seed_report_data["dev_pv_lo"].id in ids
        hi_ids = [it["device_id"] for it in data["alerts"]["high_performance"]["items"]]
        assert seed_report_data["dev_pv_hi"].id in hi_ids  # PR=0.85 >= 0.80
        lo_ids = [it["device_id"] for it in data["alerts"]["low_performance"]["items"]]
        assert seed_report_data["dev_pv_lo"].id in lo_ids  # PR=0.50 < 0.65

    def test_v2g_report(self, seed_report_data):
        """V2G运营报表 — 汇总字段齐全

        注意：/reports/v2g 实际由 reports.py 的 report_v2g 处理 —— efficiency.py
        的同名 get_v2g_report 因 reports.router 先注册而被覆盖（死代码）。
        本测试断言实际生效的返回结构。
        """
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/v2g", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "period_days" in data
        assert "device_count" in data
        # 能量统计
        assert "energy" in data
        for key in ("total_charge_kwh", "total_discharge_kwh", "net_energy_kwh"):
            assert key in data["energy"]
        # 效率统计
        assert "efficiency" in data
        for key in ("avg_charge_efficiency", "avg_discharge_efficiency", "avg_conversion_efficiency"):
            assert key in data["efficiency"]
        # 调度统计
        assert "dispatch" in data
        for key in ("total_dispatches", "completed_dispatches", "failed_dispatches"):
            assert key in data["dispatch"]

    def test_utilization_pagination(self, seed_report_data):
        """利用率报表分页 — items 受 page_size 限制，total 为全量，翻页不重叠"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/utilization?page_size=2", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["total"] >= 5  # 全量设备数，不受分页影响
        # alerts 仍基于全量设备计算（dev_low=15 < 30 必入低利用）
        assert data["alerts"]["low_utilization"]["count"] >= 1
        # 翻第二页：与第一页 device_id 不重叠
        resp2 = client.get("/api/v1/reports/utilization?page_size=2&page=2", headers=h)
        page1_ids = {it["device_id"] for it in data["items"]}
        page2_ids = {it["device_id"] for it in resp2.json()["data"]["items"]}
        assert page1_ids & page2_ids == set()

    def test_efficiency_report_pagination(self, seed_report_data):
        """充电效率报表分页 — items 受限，total 全量"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/efficiency?page_size=1", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 1
        assert data["total"] >= 2
        assert data["page_size"] == 1

    def test_generation_report_pagination(self, seed_report_data):
        """光伏PR报表分页 — items 受限，total 全量"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/reports/generation?page_size=1", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 1
        assert data["total"] >= 2
        assert data["page_size"] == 1

    def test_unauthorized_access(self):
        """未认证访问返回 401/403"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/reports/utilization").status_code in (401, 403)
        assert client.get("/api/v1/reports/generation").status_code in (401, 403)

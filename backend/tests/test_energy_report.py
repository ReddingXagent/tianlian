"""
能耗报表 API 测试
覆盖: /trend, /summary, /station-compare
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


# ========== 鉴权检查 ==========

def test_trend_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/energy/trend")
    assert resp.status_code == 401


def test_summary_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/energy/summary")
    assert resp.status_code == 401


def test_station_compare_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/energy/station-compare")
    assert resp.status_code == 401


# ========== 趋势数据测试 ==========

def test_energy_trend_default():
    token = _login()
    resp = client.get("/api/v1/energy/trend", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "trend" in data["data"]
    assert data["data"]["trend"] == []  # 卡6bc6f3f1: 无 telemetry 空列表
    assert data["data"]["granularity"] == "day"


def test_energy_trend_with_dates():
    token = _login()
    resp = client.get(
        "/api/v1/energy/trend?start_date=2026-01-01&end_date=2026-01-07&granularity=day",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    trend = data["data"]["trend"]
    assert trend == []  # 卡6bc6f3f1: 无数据不造桶
    assert data["data"]["period"] == {"start": "2026-01-01", "end": "2026-01-07"}
    entry = {"pv_generation": 0, "charging_amount": 0, "total_revenue": 0}
    assert "pv_generation" in entry
    assert "charging_amount" in entry
    assert "total_revenue" in entry


def test_energy_trend_invalid_date():
    token = _login()
    resp = client.get(
        "/api/v1/energy/trend?start_date=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert data["code"] == 400, f"期望code=400, 实际={data['code']}"
    assert "格式错误" in data["message"]


def test_energy_trend_monthly():
    token = _login()
    resp = client.get(
        "/api/v1/energy/trend?start_date=2026-01-01&end_date=2026-03-01&granularity=month",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["granularity"] == "month"


# ========== 汇总统计测试 ==========

def test_energy_summary_default():
    token = _login()
    resp = client.get("/api/v1/energy/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    summary = data["data"]
    assert "pv_generation" in summary
    assert "charging_amount" in summary
    assert "discharge_amount" in summary
    assert "total_revenue" in summary
    assert "yoy" in summary
    assert "price_info" in summary
    assert summary["period"] == "month"


def test_energy_summary_day_period():
    token = _login()
    resp = client.get(
        "/api/v1/energy/summary?period=day",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["period"] == "day"


def test_energy_summary_year_period():
    token = _login()
    resp = client.get(
        "/api/v1/energy/summary?period=year",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["period"] == "year"


# ========== 站点对比测试 ==========

def test_station_compare():
    token = _login()
    resp = client.get(
        "/api/v1/energy/station-compare",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "stations" in data["data"]
    assert "totals" in data["data"]
    # 卡6bc6f3f1: 无 telemetry 的站点不输出假排行
    assert data["data"]["stations"] == []
    assert data["data"]["totals"]["total_revenue"] == 0


# ========== 卡6bc6f3f1: 接真实 Telemetry 聚合 ==========

from datetime import datetime, timedelta, timezone as _tz


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    d = resp.json()
    return d.get("token") or d.get("data", {}).get("token")


class TestEnergyTrendReal:
    """trend 接真实 Telemetry (卡6bc6f3f1)"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry import Telemetry
        self.session = test_db["session"]
        self.Te = Telemetry
        st = Station(name="能耗站", code="ENR001", status=StationStatus.NORMAL)
        self.session.add(st)
        self.session.flush()
        self.st = st
        self.d1 = Device(sn="SN-ENR-1", name="逆变器1", code="ENR1",
                         type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                         station_id=st.id)
        self.d2 = Device(sn="SN-ENR-2", name="桩2", code="ENR2",
                         type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                         station_id=st.id)
        self.session.add_all([self.d1, self.d2])
        self.session.commit()

    def _tele(self, did, ts, **kw):
        self.session.add(self.Te(device_id=did, timestamp=ts, **kw))

    def _get(self, token, **params):
        r = client.get("/api/v1/energy/trend",
                       headers={"Authorization": f"Bearer {token}"}, params=params)
        assert r.status_code == 200
        return r.json().get("data", r.json())

    def test_empty_db_no_fake(self, auth_token):
        """无 telemetry 返回空 trend，禁止日期算术假数据"""
        data = self._get(auth_token, start_date="2026-01-01", end_date="2026-01-07")
        assert data["trend"] == []

    def test_daily_pv_from_pv1_power_integral(self, auth_token):
        """day 粒度: pv_generation = pv1_power 积分(梯形×时长)"""
        day0 = datetime(2026, 1, 1)
        # 10:00 2kW, 11:00 4kW → 梯形 3kW×1h = 3 kWh
        self._tele(self.d1.id, day0 + timedelta(hours=10), pv1_power=2.0)
        self._tele(self.d1.id, day0 + timedelta(hours=11), pv1_power=4.0)
        self.session.commit()
        data = self._get(auth_token, start_date="2026-01-01", end_date="2026-01-01")
        assert len(data["trend"]) == 1
        assert data["trend"][0]["pv_generation"] == 3.0
        assert data["trend"][0]["date"] == "2026-01-01"

    def test_daily_charge_charger_kwh_delta(self, auth_token):
        """day 粒度: charging_amount = charger_kwh 累计差值"""
        day0 = datetime(2026, 1, 2)
        self._tele(self.d2.id, day0 + timedelta(hours=8), charger_kwh=100.0)
        self._tele(self.d2.id, day0 + timedelta(hours=9), charger_kwh=105.5)
        self.session.commit()
        data = self._get(auth_token, start_date="2026-01-02", end_date="2026-01-02")
        assert data["trend"][0]["charging_amount"] == 5.5

    def test_daily_charge_grid_power_fallback(self, auth_token):
        """无 charger_kwh: 回退 avg(grid_power_total)×时长"""
        day0 = datetime(2026, 1, 3)
        self._tele(self.d2.id, day0 + timedelta(hours=8), grid_power_total=10.0)
        self._tele(self.d2.id, day0 + timedelta(hours=10), grid_power_total=20.0)
        self.session.commit()
        data = self._get(auth_token, start_date="2026-01-03", end_date="2026-01-03")
        # avg=15kW × 2h = 30 kWh
        assert data["trend"][0]["charging_amount"] == 30.0

    def test_multi_day_multi_device(self, auth_token):
        """多设备多日聚合互不串日"""
        for i in range(2):
            d = datetime(2026, 1, 5 + i)
            self._tele(self.d1.id, d + timedelta(hours=10), pv1_power=2.0)
            self._tele(self.d1.id, d + timedelta(hours=12), pv1_power=2.0)
            self._tele(self.d2.id, d + timedelta(hours=10), charger_kwh=10.0 + i)
            self._tele(self.d2.id, d + timedelta(hours=12), charger_kwh=12.0 + i)
        self.session.commit()
        data = self._get(auth_token, start_date="2026-01-05", end_date="2026-01-06")
        assert len(data["trend"]) == 2
        assert data["trend"][0]["pv_generation"] == 4.0   # 2kW×2h
        assert data["trend"][0]["charging_amount"] == 2.0
        assert data["trend"][1]["pv_generation"] == 4.0
        assert data["trend"][1]["charging_amount"] == 2.0

    def test_station_filter(self, auth_token):
        """station_id 过滤生效"""
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        st2 = Station(name="别站", code="ENR002", status=StationStatus.NORMAL)
        self.session.add(st2)
        self.session.flush()
        d3 = Device(sn="SN-ENR-3", name="别站设备", code="ENR3",
                    type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                    station_id=st2.id)
        self.session.add(d3)
        self.session.flush()
        day0 = datetime(2026, 1, 7)
        self._tele(self.d1.id, day0 + timedelta(hours=10), pv1_power=2.0)
        self._tele(self.d1.id, day0 + timedelta(hours=12), pv1_power=2.0)
        self._tele(d3.id, day0 + timedelta(hours=10), pv1_power=100.0)
        self._tele(d3.id, day0 + timedelta(hours=12), pv1_power=100.0)
        self.session.commit()
        all_data = self._get(auth_token, start_date="2026-01-07", end_date="2026-01-07")
        assert all_data["trend"][0]["pv_generation"] == 204.0
        filt = self._get(auth_token, start_date="2026-01-07", end_date="2026-01-07",
                         station_id=self.st.id)
        assert filt["trend"][0]["pv_generation"] == 4.0

    def test_end_before_start_empty(self, auth_token):
        """end < start 返回空"""
        data = self._get(auth_token, start_date="2026-01-10", end_date="2026-01-01")
        assert data["trend"] == []

    def test_month_granularity(self, auth_token):
        """month 粒度跨月聚合"""
        for m in (1, 2):
            d = datetime(2026, m, 15)
            self._tele(self.d1.id, d + timedelta(hours=10), pv1_power=4.0)
            self._tele(self.d1.id, d + timedelta(hours=11), pv1_power=4.0)
        self.session.commit()
        data = self._get(auth_token, start_date="2026-01-01", end_date="2026-02-28",
                         granularity="month")
        assert len(data["trend"]) == 2
        assert data["trend"][0]["date"] == "2026-01"
        assert data["trend"][0]["pv_generation"] == 4.0
        assert data["trend"][1]["date"] == "2026-02"
        assert data["trend"][1]["pv_generation"] == 4.0


class TestShanghaiDayBoundary:
    """卡20cb47ed: 时间窗/分桶按上海墙钟日界切, 非 UTC 零点"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry import Telemetry
        self.session = test_db["session"]
        self.Te = Telemetry
        st = Station(name="时区站", code="TZB001", status=StationStatus.NORMAL)
        self.session.add(st)
        self.session.flush()
        self.d1 = Device(sn="SN-TZB-1", name="桩", code="TZB1",
                         type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                         station_id=st.id)
        self.session.add(self.d1)
        self.session.commit()

    def _tele(self, ts, **kw):
        self.session.add(self.Te(device_id=self.d1.id, timestamp=ts, **kw))

    def _get_trend(self, token, **params):
        r = client.get("/api/v1/energy/trend",
                       headers={"Authorization": f"Bearer {token}"}, params=params)
        assert r.status_code == 200
        return r.json()["data"]

    def test_day_bucket_splits_at_shanghai_midnight(self, auth_token):
        """UTC 15:59=上海23:59 归当日桶; UTC 16:00=上海次日00:00 归次日桶"""
        # 1/10 上海日内两点 + 跨界点
        self._tele(datetime(2026, 1, 10, 14, 0), charger_kwh=10.0)
        self._tele(datetime(2026, 1, 10, 15, 59), charger_kwh=12.0)  # 上海1/10 23:59
        self._tele(datetime(2026, 1, 10, 16, 0), charger_kwh=14.0)   # 上海1/11 00:00
        self._tele(datetime(2026, 1, 11, 2, 0), charger_kwh=17.0)    # 上海1/11 10:00
        self.session.commit()
        data = self._get_trend(auth_token, start_date="2026-01-10",
                               end_date="2026-01-11", granularity="day")
        by_date = {e["date"]: e["charging_amount"] for e in data["trend"]}
        assert by_date.get("2026-01-10") == 2.0   # 10→12
        # 卡 d386c813: 12→14 跨界差值归属较晚样本桶, 周期总和守恒 (2+2+3)
        assert by_date.get("2026-01-11") == 5.0   # 12→14(跨界) + 14→17

    def test_day_window_covers_shanghai_day(self, auth_token):
        """查询日窗覆盖上海 [00:00,24:00): UTC 1/9 16:00 至 1/10 16:00 前都算查询日"""
        self._tele(datetime(2026, 1, 9, 16, 0), charger_kwh=5.0)    # 上海1/10 00:00
        self._tele(datetime(2026, 1, 10, 15, 59), charger_kwh=9.0)  # 上海1/10 23:59
        self.session.commit()
        data = self._get_trend(auth_token, start_date="2026-01-10",
                               end_date="2026-01-10", granularity="day")
        assert len(data["trend"]) == 1
        assert data["trend"][0]["date"] == "2026-01-10"
        assert data["trend"][0]["charging_amount"] == 4.0

    def test_week_bucket_splits_at_shanghai_monday(self, auth_token):
        """2026-01-12(一) 上海周界: UTC 周日 15:59=W02, 16:00=W03"""
        self._tele(datetime(2026, 1, 11, 15, 59), charger_kwh=10.0)  # 上海周日23:59
        self._tele(datetime(2026, 1, 11, 16, 0), charger_kwh=12.0)   # 上海周一00:00
        self.session.commit()
        data = self._get_trend(auth_token, start_date="2026-01-05",
                               end_date="2026-01-18", granularity="week")
        dates = sorted(e["date"] for e in data["trend"])
        assert "2026-W02" in dates
        assert "2026-W03" in dates

    def test_month_bucket_splits_at_shanghai_month_start(self, auth_token):
        """UTC 1/31 17:00 = 上海 2/1 01:00 → 归 2026-02 桶"""
        self._tele(datetime(2026, 1, 31, 10, 0), charger_kwh=10.0)
        self._tele(datetime(2026, 1, 31, 16, 0), charger_kwh=12.0)  # 上海2/1 00:00
        self._tele(datetime(2026, 2, 1, 2, 0), charger_kwh=15.0)    # 上海2/1 10:00
        self.session.commit()
        data = self._get_trend(auth_token, start_date="2026-01-01",
                               end_date="2026-02-28", granularity="month")
        by_m = {e["date"]: e["charging_amount"] for e in data["trend"]}
        assert by_m.get("2026-01") == 0.0
        # 卡 d386c813: 10→12 跨月界差值归属 2 月桶 (2+3), 不再凭空丢弃
        assert by_m.get("2026-02") == 5.0

    def _patch_now(self, monkeypatch, biz_dt):
        from zoneinfo import ZoneInfo
        aware = biz_dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        import app.api.v1.energy_report as mod
        monkeypatch.setattr(mod, "now_in_biz_tz", lambda now=None: aware)

    def test_summary_day_window_from_shanghai_midnight(self, monkeypatch, auth_token):
        """summary period=day 窗自上海 00:00 (UTC 前日16:00) 起"""
        # 固定"现在"= 上海 2026-01-10 20:00 (= UTC 12:00)
        self._patch_now(monkeypatch, datetime(2026, 1, 10, 20, 0))
        self._tele(datetime(2026, 1, 9, 17, 0), charger_kwh=10.0)  # 上海1/10 01:00
        self._tele(datetime(2026, 1, 10, 2, 0), charger_kwh=13.0)  # 上海1/10 10:00
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        assert r.json()["data"]["charging_amount"] == 3.0
        assert r.json()["data"]["days"] == 1

    def test_summary_prev_period_shifted_by_shanghai_day(self, monkeypatch, auth_token):
        """同比窗 = 上一等长周期平移对齐墙钟: now=上海1/10 12:00, 本期 [1/10 00:00,12:00),
        上期 [1/9 12:00, 1/10 00:00) —— 上期数据按上海墙钟落位"""
        self._patch_now(monkeypatch, datetime(2026, 1, 10, 12, 0))
        # 本期 上海1/10 10:00/11:00 (= UTC 02:00/03:00)
        self._tele(datetime(2026, 1, 10, 2, 0), charger_kwh=10.0)
        self._tele(datetime(2026, 1, 10, 3, 0), charger_kwh=12.0)
        # 上期 上海1/9 13:00/14:00 (= UTC 05:00/06:00)
        self._tele(datetime(2026, 1, 9, 5, 0), charger_kwh=20.0)
        self._tele(datetime(2026, 1, 9, 6, 0), charger_kwh=26.0)
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        yoy = r.json()["data"]["yoy"]["charging_amount_yoy"]
        # cur=2, prev=6 → (2-6)/6 = -66.7%
        assert yoy == -66.7

    def test_summary_excludes_before_shanghai_midnight(self, monkeypatch, auth_token):
        """上海 1/9 23:00 (UTC 15:00) 不计入 1/10 本期"""
        self._patch_now(monkeypatch, datetime(2026, 1, 10, 12, 0))
        self._tele(datetime(2026, 1, 9, 15, 0), charger_kwh=10.0)  # 上海1/9 23:00
        self._tele(datetime(2026, 1, 10, 2, 0), charger_kwh=11.0)  # 上海1/10 10:00
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        assert r.json()["data"]["charging_amount"] == 0.0  # 窗内仅单点无差值


class TestEnergySummaryReal:
    """summary 真实聚合 + yoy (卡6bc6f3f1)"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry import Telemetry
        self.session = test_db["session"]
        self.Te = Telemetry
        st = Station(name="汇总站", code="SUM001", status=StationStatus.NORMAL)
        self.session.add(st)
        self.session.flush()
        self.st = st
        self.d1 = Device(sn="SN-SUM-1", name="桩", code="SUM1",
                         type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                         station_id=st.id)
        self.session.add(self.d1)
        self.session.commit()

    def test_empty_db_zero_and_null_yoy(self, auth_token):
        """空库全零 + yoy=null"""
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["pv_generation"] == 0
        assert data["charging_amount"] == 0
        assert data["total_revenue"] == 0
        for v in data["yoy"].values():
            assert v is None

    def test_today_summary_real_aggregation(self, auth_token):
        """period=day 用真实今日数据 (上海今日 00:00 起的 charger_kwh 差值, 卡b20e99a8)"""
        from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz
        start, end = biz_day_bounds_utc_naive(today_in_biz_tz())
        elapsed = datetime.utcnow() - start
        if elapsed < timedelta(minutes=2):  # 上海零点刚过, 窗内无两点空间
            pytest.skip("上海日界后窗过窄")
        mid = elapsed / 3  # 两点均落在 [start, now) 窗内
        self.session.add(self.Te(device_id=self.d1.id, timestamp=start + mid,
                                 charger_kwh=10.0))
        self.session.add(self.Te(device_id=self.d1.id, timestamp=start + mid * 2,
                                 charger_kwh=13.0))
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        data = r.json()["data"]
        assert data["charging_amount"] == 3.0

    def _patch_now(self, monkeypatch, biz_dt):
        from zoneinfo import ZoneInfo
        aware = biz_dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        import app.api.v1.energy_report as mod
        monkeypatch.setattr(mod, "now_in_biz_tz", lambda now=None: aware)

    def test_summary_day_boundary_straddles_shanghai_midnight(self, monkeypatch, auth_token):
        """上海日界两侧归属: 1/10 23:59:59 属昨日, 1/11 00:00:01 起属今日 (卡b20e99a8)"""
        self._patch_now(monkeypatch, datetime(2026, 1, 11, 2, 0))
        # 上海 1/10 23:59:59 = UTC 1/10 15:59:59 → 昨日
        self.session.add(self.Te(device_id=self.d1.id,
                                 timestamp=datetime(2026, 1, 10, 15, 59, 59),
                                 charger_kwh=10.0))
        # 上海 1/11 00:00:01 = UTC 1/10 16:00:01 → 今日窗首点
        self.session.add(self.Te(device_id=self.d1.id,
                                 timestamp=datetime(2026, 1, 10, 16, 0, 1),
                                 charger_kwh=13.0))
        # 上海 1/11 01:00 = UTC 1/10 17:00 → 今日
        self.session.add(self.Te(device_id=self.d1.id,
                                 timestamp=datetime(2026, 1, 10, 17, 0),
                                 charger_kwh=16.0))
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        data = r.json()["data"]
        # 今日窗 [上海1/11 00:00, now) 内差值 16-13=3; 昨日 23:59:59 点不计入
        assert data["charging_amount"] == 3.0
        assert data["days"] == 1

    def test_price_info_source_default(self, auth_token):
        """无定价配置: price_info 标注 source=default"""
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        data = r.json()["data"]
        assert data["price_info"]["source"] == "default"
        assert "charging_price" in data["price_info"]

    def test_price_info_source_pricing_rules(self, auth_token):
        """有 PricingRule: source=pricing_rules 且电价取规则均值"""
        from app.models.pricing_rule import PricingRule, PeriodType
        from datetime import time as dtime
        self.session.add(PricingRule(name="峰", period_type=PeriodType.PEAK,
                                     start_time=dtime(8, 0), end_time=dtime(12, 0),
                                     electricity_price=1.0, service_fee_rate=0.4))
        self.session.add(PricingRule(name="谷", period_type=PeriodType.VALLEY,
                                     start_time=dtime(0, 0), end_time=dtime(8, 0),
                                     electricity_price=0.3, service_fee_rate=0.2))
        self.session.commit()
        r = client.get("/api/v1/energy/summary?period=day",
                       headers={"Authorization": f"Bearer {auth_token}"})
        data = r.json()["data"]
        assert data["price_info"]["source"] == "pricing_rules"
        # 平均电价 0.65, 平均服务费 0.3
        assert abs(data["price_info"]["charging_price"] - 0.3) < 0.01
        assert abs(data["price_info"]["feed_in_tariff"] - 0.65) < 0.01

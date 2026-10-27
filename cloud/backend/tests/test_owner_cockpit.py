#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经营驾驶舱 (Owner Cockpit) API 测试 — /api/v1/owner-cockpit

聚合收入 / 利用率 / 毛利 / ROI 四类指标，面向"充电站拥有者/投资人"视角。

口径（与 owner_cockpit.py 注释同源，测试据此断言）：
  - 收入 revenue        : Σ paid_amount, 仅 order_status=COMPLETED & payment_status=PAID
  - 售电量 energy_kwh   : Σ charged_kwh (同上订单过滤)
  - 购电成本 purchase_cost: Σ charged_kwh × purchase_price (默认 0.60 元/kWh, Query 可配)
  - 毛利 gross_margin   : revenue - purchase_cost
  - 利用率 utilization  : Σ duration_minutes / (Σ gun_count × num_days × 1440) × 100
  - ROI%                : 累计毛利(全时段) / Σ station.total_cost × 100
  - 回本月 payback      : total_cost / 月均毛利; 月均毛利<=0 → null

团队隔离: admin 平台级全见; 团队级用户(operator)仅本 team 站点, 跨团队 station_id → 404。
"""
from datetime import datetime, timedelta, timezone
import pytest

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod,
)
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole, Team


# ─── 脚手架 ───

def _login(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def cockpit_data(client):
    """构造 2 站点 + 多笔订单(含被排除/越界) 的经营数据。

    返回 dict 含站点/订单 ORM 与确定性数值常量, 供断言复用。
    """
    s = client._sesh
    now = datetime.now(timezone.utc)

    st_a = Station(
        name="资方站A", code="OCK001", status=StationStatus.NORMAL,
        gun_count=2, total_cost=100000,
        created_at=now - timedelta(days=60),
    )
    st_b = Station(
        name="资方站B", code="OCK002", status=StationStatus.NORMAL,
        gun_count=4, total_cost=200000,
        created_at=now - timedelta(days=60),
    )
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    def mk(station_id, kwh, paid, efee=0, sfee=0, dur=0, created=None,
           ostatus=OrderStatus.COMPLETED, pstatus=OrderPaymentStatus.PAID, suffix=""):
        return ChargingOrder(
            order_no=f"OCK-{station_id}-{suffix}",
            station_id=station_id, device_id=999,
            charged_kwh=kwh, paid_amount=paid,
            electricity_fee=efee, service_fee=sfee,
            duration_minutes=dur,
            order_status=ostatus, payment_status=pstatus,
            payment_method=PaymentMethod.WECHAT,
            created_at=created if created is not None else (now - timedelta(days=1)),
        )

    yesterday = now - timedelta(days=1)
    long_ago = now - timedelta(days=100)
    s.add_all([
        # 站A 区间内 2 单
        mk(st_a.id, 100, 200, 150, 50, 60, yesterday, suffix="A1"),
        mk(st_a.id, 50, 100, 75, 25, 30, yesterday, suffix="A2"),
        # 站B 区间内 1 单
        mk(st_b.id, 200, 400, 300, 100, 120, yesterday, suffix="B1"),
        # 被排除: 取消单
        mk(st_a.id, 999, 999, created=yesterday, ostatus=OrderStatus.CANCELLED, suffix="AX"),
        # 被排除: 未支付
        mk(st_a.id, 888, 888, created=yesterday, pstatus=OrderPaymentStatus.UNPAID, suffix="AU"),
        # 越出默认 30 天窗口, 但计入累计(全时段)毛利
        mk(st_b.id, 1000, 2000, 1500, 500, 600, long_ago, suffix="BOLD"),
    ])
    s.commit()

    return {
        "st_a": st_a, "st_b": st_b, "now": now,
        "DEFAULT_PRICE": 0.60,
        # 区间内聚合 (站A 2单 / 站B 1单)
        "range_revenue": 200 + 100 + 400,
        "range_energy": 100 + 50 + 200,
        "range_orders": 3,
        "range_duration": 60 + 30 + 120,
        # 累计(全时段) 含 BOLD 单
        "cum_revenue": 200 + 100 + 400 + 2000,
        "cum_energy": 100 + 50 + 200 + 1000,
        "total_cost": 100000 + 200000,
        "total_guns": 2 + 4,
    }


@pytest.fixture(scope="function")
def team_cockpit(client):
    """构造两团队 + 两 operator 用户 + 分属两团队的站点(各一订单)。"""
    s = client._sesh
    ta = Team(name="OCK团队A", code="OCKTA")
    tb = Team(name="OCK团队B", code="OCKTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "ock123456"
    ua = User(username="ock_op_a", real_name="A运营", role=UserRole.OPERATOR,
              team_id=ta.id, status="active",
              password_hash=__import__("bcrypt").hashpw(pwd.encode(), __import__("bcrypt").gensalt()).decode())
    ub = User(username="ock_op_b", real_name="B运营", role=UserRole.OPERATOR,
              team_id=tb.id, status="active",
              password_hash=__import__("bcrypt").hashpw(pwd.encode(), __import__("bcrypt").gensalt()).decode())
    s.add_all([ua, ub])
    s.commit()

    now = datetime.now(timezone.utc)
    sa = Station(name="OCK-A站", code="OCKSA", team_id=ta.id, status=StationStatus.NORMAL,
                 gun_count=2, total_cost=50000, created_at=now - timedelta(days=30))
    sb = Station(name="OCK-B站", code="OCKSB", team_id=tb.id, status=StationStatus.NORMAL,
                 gun_count=2, total_cost=50000, created_at=now - timedelta(days=30))
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    s.add_all([
        ChargingOrder(order_no="OCK-TA-1", station_id=sa.id, device_id=999,
                      charged_kwh=100, paid_amount=300, electricity_fee=200, service_fee=100,
                      duration_minutes=60, order_status=OrderStatus.COMPLETED,
                      payment_status=OrderPaymentStatus.PAID, payment_method=PaymentMethod.WECHAT,
                      created_at=now - timedelta(days=1)),
        ChargingOrder(order_no="OCK-TB-1", station_id=sb.id, device_id=999,
                      charged_kwh=80, paid_amount=240, electricity_fee=160, service_fee=80,
                      duration_minutes=40, order_status=OrderStatus.COMPLETED,
                      payment_status=OrderPaymentStatus.PAID, payment_method=PaymentMethod.WECHAT,
                      created_at=now - timedelta(days=1)),
    ])
    s.commit()

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sa, "b": sb},
        "tokens": {
            "a": _login(client, "ock_op_a", pwd),
            "b": _login(client, "ock_op_b", pwd),
            "admin": _login(client),
        },
    }


# ─── 测试用例 ───

class TestOwnerCockpitAuth:
    """认证与基础可达性"""

    def test_overview_requires_auth(self, anon_client):
        """匿名访问 → 401/403"""
        r = anon_client.get("/api/v1/owner-cockpit/overview")
        assert r.status_code in (401, 403)


class TestOwnerCockpitOverview:
    """overview 端点 — 结构 / 收入 / 毛利 / 利用率 / ROI"""

    def test_overview_structure(self, client, cockpit_data):
        """返回结构完整 (summary/investment/stations/trend/caliber 齐全)"""
        r = client.get("/api/v1/owner-cockpit/overview")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        for key in ("period", "caliber", "summary", "investment", "stations", "trend"):
            assert key in data, f"缺少顶层字段 {key}"
        for key in ("revenue", "energy_kwh", "order_count", "avg_per_order",
                    "purchase_cost", "gross_margin", "gross_margin_rate", "utilization_rate"):
            assert key in data["summary"], f"缺少 summary.{key}"
        for key in ("total_cost", "cumulative_gross_margin", "roi_rate", "payback_months"):
            assert key in data["investment"], f"缺少 investment.{key}"

    def test_overview_empty_database(self, client):
        """空库 → 200, 数值为 0 / null, 不崩溃"""
        r = client.get("/api/v1/owner-cockpit/overview")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["summary"]["revenue"] == 0
        assert data["summary"]["order_count"] == 0
        assert data["summary"]["gross_margin"] == 0
        assert data["stations"] == []
        assert data["investment"]["roi_rate"] is None

    def test_overview_revenue_aggregation(self, client, cockpit_data):
        """收入/电量/订单 = Σ (仅 completed+paid)"""
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        sm = data["summary"]
        assert sm["revenue"] == pytest.approx(cockpit_data["range_revenue"])
        assert sm["energy_kwh"] == pytest.approx(cockpit_data["range_energy"])
        assert sm["order_count"] == cockpit_data["range_orders"]
        assert sm["avg_per_order"] == pytest.approx(
            cockpit_data["range_revenue"] / cockpit_data["range_orders"], abs=0.01
        )

    def test_overview_gross_margin_caliber(self, client, cockpit_data):
        """毛利 = 收入 - Σcharged_kwh × purchase_price (默认 0.60)"""
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        sm = data["summary"]
        price = cockpit_data["DEFAULT_PRICE"]
        expected_cost = cockpit_data["range_energy"] * price
        assert sm["purchase_cost"] == pytest.approx(expected_cost)
        assert sm["gross_margin"] == pytest.approx(cockpit_data["range_revenue"] - expected_cost)
        assert sm["gross_margin_rate"] == pytest.approx(
            (cockpit_data["range_revenue"] - expected_cost) / cockpit_data["range_revenue"] * 100
        )

    def test_overview_purchase_price_param(self, client, cockpit_data):
        """purchase_price Query 参数可调, 影响购电成本与毛利"""
        r = client.get("/api/v1/owner-cockpit/overview?purchase_price=0.50")
        sm = r.json()["data"]["summary"]
        expected_cost = cockpit_data["range_energy"] * 0.50
        assert sm["purchase_cost"] == pytest.approx(expected_cost)
        assert sm["gross_margin"] == pytest.approx(cockpit_data["range_revenue"] - expected_cost)

    def test_overview_utilization_formula(self, client, cockpit_data):
        """利用率 = Σduration / (Σgun_count × num_days × 1440) × 100

        传固定 10 天窗口使 num_days 确定可算。
        """
        now = cockpit_data["now"]
        start = (now - timedelta(days=9)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        num_days = 10
        r = client.get(f"/api/v1/owner-cockpit/overview?start_date={start}&end_date={end}")
        util = r.json()["data"]["summary"]["utilization_rate"]
        expected = cockpit_data["range_duration"] / (
            cockpit_data["total_guns"] * num_days * 1440
        ) * 100
        assert util == pytest.approx(expected, abs=1e-4)
        assert 0 <= util <= 100

    def test_overview_roi_and_cumulative(self, client, cockpit_data):
        """ROI% = 累计毛利(全时段) / Σtotal_cost × 100; 含越界 BOLD 单"""
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        inv = data["investment"]
        price = cockpit_data["DEFAULT_PRICE"]
        cum_margin = cockpit_data["cum_revenue"] - cockpit_data["cum_energy"] * price
        assert inv["cumulative_gross_margin"] == pytest.approx(cum_margin)
        assert inv["total_cost"] == pytest.approx(cockpit_data["total_cost"])
        assert inv["roi_rate"] == pytest.approx(cum_margin / cockpit_data["total_cost"] * 100)
        assert inv["payback_months"] is None or inv["payback_months"] > 0

    def test_overview_no_total_cost_roi_null(self, client):
        """站点无 total_cost → ROI/payback 为 null"""
        s = client._sesh
        st = Station(name="无成本站", code="OCKNC", status=StationStatus.NORMAL,
                     gun_count=2, total_cost=None)
        s.add(st); s.commit(); s.refresh(st)
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        assert data["investment"]["roi_rate"] is None
        assert data["investment"]["payback_months"] is None

    def test_overview_stations_breakdown(self, client, cockpit_data):
        """stations 明细按场站拆分且含每站毛利/ROI"""
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        ids = [it["station_id"] for it in data["stations"]]
        assert cockpit_data["st_a"].id in ids
        assert cockpit_data["st_b"].id in ids
        a = next(it for it in data["stations"] if it["station_id"] == cockpit_data["st_a"].id)
        # 站A 区间内 2 单: kwh=150, revenue=300
        assert a["energy_kwh"] == pytest.approx(150)
        assert a["revenue"] == pytest.approx(300)
        assert "gross_margin" in a and "roi_rate" in a

    def test_overview_station_filter(self, client, cockpit_data):
        """station_id 过滤 → 只剩该站"""
        sid = cockpit_data["st_b"].id
        data = client.get(f"/api/v1/owner-cockpit/overview?station_id={sid}").json()["data"]
        ids = [it["station_id"] for it in data["stations"]]
        assert ids == [sid]
        assert data["summary"]["energy_kwh"] == pytest.approx(200)

    def test_overview_trend_series(self, client, cockpit_data):
        """trend 含按日序列, 且至少有一天有收入"""
        data = client.get("/api/v1/owner-cockpit/overview").json()["data"]
        assert isinstance(data["trend"], list)
        assert len(data["trend"]) >= 1
        for pt in data["trend"]:
            assert "date" in pt and "revenue" in pt and "gross_margin" in pt
        assert sum(pt["revenue"] for pt in data["trend"]) == pytest.approx(cockpit_data["range_revenue"])


class TestOwnerCockpitTeamScoping:
    """团队隔离: admin 全见, operator 仅本 team, 跨团队 → 404"""

    def test_admin_sees_all(self, client, team_cockpit):
        r = client.get("/api/v1/owner-cockpit/overview",
                       headers=_h(team_cockpit["tokens"]["admin"]))
        assert r.status_code == 200
        ids = {it["station_id"] for it in r.json()["data"]["stations"]}
        assert team_cockpit["stations"]["a"].id in ids
        assert team_cockpit["stations"]["b"].id in ids

    def test_operator_sees_own_team_only(self, client, team_cockpit):
        r = client.get("/api/v1/owner-cockpit/overview",
                       headers=_h(team_cockpit["tokens"]["a"]))
        assert r.status_code == 200
        ids = {it["station_id"] for it in r.json()["data"]["stations"]}
        assert team_cockpit["stations"]["a"].id in ids
        assert team_cockpit["stations"]["b"].id not in ids

    def test_operator_cross_team_station_404(self, client, team_cockpit):
        """operator A 查 team B 站点 → 404 (不泄露存在)"""
        sid = team_cockpit["stations"]["b"].id
        r = client.get(f"/api/v1/owner-cockpit/overview?station_id={sid}",
                       headers=_h(team_cockpit["tokens"]["a"]))
        assert r.status_code == 404

    def test_operator_own_station_ok(self, client, team_cockpit):
        sid = team_cockpit["stations"]["a"].id
        r = client.get(f"/api/v1/owner-cockpit/overview?station_id={sid}",
                       headers=_h(team_cockpit["tokens"]["a"]))
        assert r.status_code == 200

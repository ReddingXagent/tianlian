#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经营驾驶舱 API 测试 (app/api/v1/owner_cockpit.py)

覆盖 GET /api/v1/owner-cockpit/overview — 站长视角聚合视图(收入/利用率/毛利/ROI)。

覆盖维度:
(a) 正常聚合各字段正确 (revenue/energy/order_count/avg_per_order/purchase_cost/
    gross_margin/gross_margin_rate)
(b) 口径: 仅 order_status=COMPLETED & payment_status=PAID 计入
(c) purchase_price 参数影响购电成本/毛利, 不影响收入
(d) 日期范围 [start_date, end_date+1day) 半开区间
(e) summary 受时间窗约束, investment 累计毛利/ROI 为全时段(口径差异锁定)
(f) 利用率 = Σduration / (Σgun_count × num_days × 1440) × 100
(g) team scoping: 非 admin 仅本 team 站点; admin 跨 team 全见
(h) station_id 跨团队/不存在 → 404 (不泄露存在)
(i) 空数据: 无站点 / 有站无单 均不报错
(j) stations 明细字段 + trend 按日序列
(k) ROI/payback: 有 total_cost 才算; 月均毛利<=0 → payback null
(l) 权限门: 未登录 → 401
(m) DB 异常 → 500 中文兜底 + logger 记录 (本卡新增的异常保护)

铁律: 仅 (m) 依赖源码新增的 try/except; (a)-(l) 锁定既有正确行为防回归。
"""
import uuid
import logging

import bcrypt
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

from tests.api._helpers import login_as, login_admin

OV = "/api/v1/owner-cockpit/overview"
DEFAULT_PRICE = 0.60  # 与源码 DEFAULT_PURCHASE_PRICE 同源


# ───────────────────────── seed helpers ─────────────────────────


def _station(session, *, name, code, team_id=None, gun_count=2, total_cost=None,
             created_at=None):
    """造一个 Station。total_cost/created_at 默认 None (测 ROI/payback 的 null 分支)。"""
    s = Station(
        name=name, code=code, address="测试地址", status=StationStatus.NORMAL,
        team_id=team_id, gun_count=gun_count, total_cost=total_cost,
        created_at=created_at,
    )
    session.add(s)
    session.flush()
    return s


def _order(session, station_id, *, paid=Decimal("0"), kwh=Decimal("0"), duration=0,
           created_at=None, payment_status=OrderPaymentStatus.PAID,
           order_status=OrderStatus.COMPLETED):
    """造一条 ChargingOrder (默认 COMPLETED+PAID, 计入营收口径)。

    created_at=None → 走模型默认 (now, aware), 落在默认近30天窗口内。
    """
    o = ChargingOrder(
        order_no=f"ORD-{uuid.uuid4().hex[:12]}",  # uuid 保证唯一, 不可用 id()
        station_id=station_id, device_id=1, user_type=UserType.APP,
        charged_kwh=kwh, total_amount=paid, paid_amount=paid,
        payment_status=payment_status, order_status=order_status,
        payment_method=PaymentMethod.WECHAT, duration_minutes=duration,
        created_at=created_at,
    )
    session.add(o)
    session.flush()
    return o


def _make_team_viewer(client, team_id, username="oc_viewer"):
    """创建/复用带 team_id 的 VIEWER 用户 (非 admin), 供 team_scope 过滤验证。"""
    s = client._sesh
    existing = s.query(User).filter(User.username == username).first()
    if existing:
        existing.team_id = team_id
        s.commit()
        return existing
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(b"v123456", bcrypt.gensalt()).decode(),
        real_name=username, role=UserRole.VIEWER, status="active", team_id=team_id,
    )
    s.add(u)
    s.commit()
    return u


# ───────────────────────── (a)(b)(c) 聚合与口径 ─────────────────────────


class TestOwnerCockpitAggregation:
    """GET /owner-cockpit/overview — 聚合数值与口径。"""

    def test_summary_aggregation_basic(self, client):
        """(a) 默认窗口内多单聚合: 各 summary 字段准确。"""
        s = client._sesh
        sta = _station(s, name="聚合站", code="OC001", gun_count=4)
        _order(s, sta.id, paid=Decimal("120"), kwh=Decimal("200"), duration=60)
        _order(s, sta.id, paid=Decimal("80"), kwh=Decimal("100"), duration=30)
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        sm = d["summary"]
        assert sm["revenue"] == 200.0              # 120 + 80
        assert sm["energy_kwh"] == 300.0           # 200 + 100
        assert sm["order_count"] == 2
        assert sm["avg_per_order"] == 100.0        # 200 / 2
        assert sm["purchase_cost"] == 180.0        # 300 × 0.60
        assert sm["gross_margin"] == 20.0          # 200 - 180
        assert sm["gross_margin_rate"] == 10.0     # 20 / 200 × 100
        # 利用率依赖 num_days (默认窗口), 仅断言非负
        assert sm["utilization_rate"] >= 0.0

    def test_caliber_excludes_unpaid_and_uncompleted(self, client):
        """(b) 仅 COMPLETED+PAID 计入: UNPAID / 非COMPLETED 排除。"""
        s = client._sesh
        sta = _station(s, name="口径站", code="OC002")
        _order(s, sta.id, paid=Decimal("100"))                                   # 计入
        _order(s, sta.id, paid=Decimal("200"), payment_status=OrderPaymentStatus.UNPAID)
        _order(s, sta.id, paid=Decimal("50"), order_status=OrderStatus.PENDING)  # 非COMPLETED
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        sm = r.json()["data"]["summary"]
        assert sm["revenue"] == 100.0
        assert sm["order_count"] == 1

    def test_purchase_price_changes_margin_not_revenue(self, client):
        """(c) purchase_price 影响购电成本/毛利, 不影响收入与电量。"""
        s = client._sesh
        sta = _station(s, name="价差站", code="OC003")
        _order(s, sta.id, paid=Decimal("100"), kwh=Decimal("100"))
        s.commit()

        r_default = client.get(OV).json()["data"]["summary"]
        assert r_default["purchase_cost"] == 60.0   # 100 × 0.60
        assert r_default["gross_margin"] == 40.0    # 100 - 60

        r_low = client.get(f"{OV}?purchase_price=0.3").json()["data"]["summary"]
        assert r_low["purchase_cost"] == 30.0       # 100 × 0.30
        assert r_low["gross_margin"] == 70.0        # 100 - 30
        # 收入/电量不受购电价影响
        assert r_low["revenue"] == 100.0
        assert r_low["energy_kwh"] == 100.0


# ───────────────────────── (d)(e)(f) 时间窗与利用率 ─────────────────────────


class TestOwnerCockpitWindow:
    """日期范围 / 窗口内外口径 / 利用率。"""

    def test_date_range_half_open(self, client):
        """(d) [start_date, end_date+1day) 半开区间, end_date 当日包含。"""
        s = client._sesh
        sta = _station(s, name="日期站", code="OC004")
        _order(s, sta.id, paid=Decimal("100"), created_at=datetime(2026, 8, 5, 12, 0))   # 区间内
        _order(s, sta.id, paid=Decimal("10"), created_at=datetime(2026, 7, 31, 12, 0))   # 早于 start
        _order(s, sta.id, paid=Decimal("20"), created_at=datetime(2026, 8, 10, 23, 0))   # =end 当日, 包含
        _order(s, sta.id, paid=Decimal("30"), created_at=datetime(2026, 8, 15, 12, 0))   # 晚于 end
        s.commit()

        r = client.get(f"{OV}?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        sm = r.json()["data"]["summary"]
        assert sm["revenue"] == 120.0   # 100 + 20
        assert sm["order_count"] == 2

    def test_summary_windowed_but_investment_cumulative(self, client):
        """(e) summary 受时间窗约束, investment.cumulative_gross_margin 为全时段。

        锁定口径差异: 一条窗口外老订单不计入 summary.revenue, 但计入累计毛利(ROI 用)。
        """
        s = client._sesh
        sta = _station(s, name="累计站", code="OC005")
        # 窗口外 (2024, 远早于默认近30天)
        _order(s, sta.id, paid=Decimal("300"),
               created_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
        # 窗口内 (now)
        _order(s, sta.id, paid=Decimal("100"),
               created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 100.0                       # 仅窗口内
        assert d["summary"]["order_count"] == 1
        # 累计毛利含两条 (kwh=0 → 购电成本0): 300 + 100 = 400
        assert d["investment"]["cumulative_gross_margin"] == 400.0

    def test_utilization_rate_explicit(self, client):
        """(f) 利用率 = Σduration / (Σgun_count × num_days × 1440) × 100。

        显式 1 天窗口可控 num_days: gun_count=2, 单单 duration=1440(分钟) → 50%。
        """
        s = client._sesh
        sta = _station(s, name="利用率站", code="OC006", gun_count=2)
        _order(s, sta.id, paid=Decimal("10"), duration=1440,
               created_at=datetime(2026, 7, 1, 12, 0))
        s.commit()

        r = client.get(f"{OV}?start_date=2026-07-01&end_date=2026-07-01")
        assert r.status_code == 200
        sm = r.json()["data"]["summary"]
        # 1440 / (2 × 1 × 1440) × 100 = 50.0
        assert sm["utilization_rate"] == 50.0


# ───────────────────────── (g)(h) team scoping 与 station 过滤 ─────────────────────────


class TestOwnerCockpitTeamScoping:
    """team 隔离 / station_id 跨团队与不存在 → 404。"""

    def test_team_viewer_scoped(self, client):
        """(g) 非 admin 仅见本 team 站点的营收。"""
        s = client._sesh
        sa = _station(s, name="本队站", code="OCT1", team_id=1)
        sb = _station(s, name="他队站", code="OCT2", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        _make_team_viewer(client, team_id=1)
        s.commit()

        login_as(client, "oc_viewer", "v123456")
        r = client.get(OV)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 100.0                 # 仅本 team
        assert {st["station_id"] for st in d["stations"]} == {sa.id}
        login_admin(client)

    def test_admin_sees_all_teams(self, client):
        """(g) admin 跨 team 全见。"""
        s = client._sesh
        sa = _station(s, name="A队", code="OCA1", team_id=1)
        sb = _station(s, name="B队", code="OCA2", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 300.0
        assert {st["station_id"] for st in d["stations"]} == {sa.id, sb.id}

    def test_cross_team_station_404(self, client):
        """(h) 非 admin 传他 team 的 station_id → 404 (不泄露存在)。"""
        s = client._sesh
        sb = _station(s, name="他队站", code="OCX2", team_id=2)
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        _make_team_viewer(client, team_id=1)
        s.commit()

        login_as(client, "oc_viewer", "v123456")
        r = client.get(f"{OV}?station_id={sb.id}")
        assert r.status_code == 404
        login_admin(client)

    def test_nonexistent_station_404(self, client):
        """(h) station_id 不存在 → 404。"""
        r = client.get(f"{OV}?station_id=999999")
        assert r.status_code == 404

    def test_single_station_filter(self, client):
        """station_id 过滤: admin 指定单站, 仅该站数据。"""
        s = client._sesh
        sa = _station(s, name="主站", code="OCS1")
        sb = _station(s, name="旁站", code="OCS2")
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(f"{OV}?station_id={sa.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 100.0
        assert [st["station_id"] for st in d["stations"]] == [sa.id]


# ───────────────────────── (i) 空数据 ─────────────────────────


class TestOwnerCockpitEmpty:
    """空数据场景不报错。"""

    def test_empty_no_stations(self, client):
        """新账号无任何站点 → 200, summary 全零, stations/trend 空。"""
        r = client.get(OV)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 0
        assert d["summary"]["order_count"] == 0
        assert d["summary"]["energy_kwh"] == 0
        assert d["stations"] == []
        assert d["trend"] == []

    def test_empty_station_no_orders(self, client):
        """有站无单 → stations 含占位行(零值), summary 全零。"""
        s = client._sesh
        sta = _station(s, name="空站", code="OCE1", gun_count=2)
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["summary"]["revenue"] == 0
        assert d["summary"]["order_count"] == 0
        assert len(d["stations"]) == 1
        row = d["stations"][0]
        assert row["station_id"] == sta.id
        assert row["revenue"] == 0
        assert row["order_count"] == 0
        assert row["roi_rate"] is None          # 无 total_cost


# ───────────────────────── (j) 明细与趋势 ─────────────────────────


class TestOwnerCockpitBreakdown:
    """stations 明细字段 + trend 按日序列。"""

    def test_station_breakdown_fields(self, client):
        """stations 明细: 各站 revenue/energy/order_count/gun_count/roi 字段正确。"""
        s = client._sesh
        sa = _station(s, name="明细A", code="OCB1", gun_count=4, total_cost=Decimal("10000"))
        sb = _station(s, name="明细B", code="OCB2", gun_count=2, total_cost=None)
        _order(s, sa.id, paid=Decimal("120"), kwh=Decimal("200"), duration=60,
               created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("80"), kwh=Decimal("100"), duration=30,
               created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        by_id = {st["station_id"]: st for st in r.json()["data"]["stations"]}
        a = by_id[sa.id]
        assert a["station_name"] == "明细A"
        assert a["revenue"] == 120.0
        assert a["energy_kwh"] == 200.0
        assert a["order_count"] == 1
        assert a["gun_count"] == 4
        assert a["gross_margin"] == round(120.0 - 200.0 * DEFAULT_PRICE, 2)   # 0.0
        assert a["total_cost"] == 10000.0
        assert a["roi_rate"] is not None                                       # 有 cost
        b = by_id[sb.id]
        assert b["total_cost"] is None
        assert b["roi_rate"] is None                                           # 无 cost

    def test_trend_by_day(self, client):
        """trend: 按日分组, 升序, 每行 date/revenue/energy_kwh/gross_margin。"""
        s = client._sesh
        sta = _station(s, name="趋势站", code="OCTR", gun_count=2)
        _order(s, sta.id, paid=Decimal("100"), kwh=Decimal("50"),
               created_at=datetime(2026, 8, 5, 12, 0))
        _order(s, sta.id, paid=Decimal("200"), kwh=Decimal("80"),
               created_at=datetime(2026, 8, 6, 12, 0))
        s.commit()

        r = client.get(f"{OV}?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        trend = r.json()["data"]["trend"]
        assert len(trend) == 2
        # 升序
        assert trend[0]["date"] <= trend[1]["date"]
        d0 = trend[0]
        assert d0["revenue"] == 100.0
        assert d0["energy_kwh"] == 50.0
        assert d0["gross_margin"] == round(100.0 - 50.0 * DEFAULT_PRICE, 2)    # 70.0
        assert trend[1]["revenue"] == 200.0


# ───────────────────────── (k) ROI / 回本 ─────────────────────────


class TestOwnerCockpitInvestment:
    """ROI / payback_months 边界。"""

    def test_investment_roi_and_payback(self, client):
        """有 total_cost + 近期建站 + 正累计毛利 → roi_rate/payback_months 可算。

        created_at=now-5d → months=max(1, 5/30)=1.0, monthly_avg=cum_margin → payback 确定性。
        """
        s = client._sesh
        sta = _station(
            s, name="回本站", code="OCROI", gun_count=2,
            total_cost=Decimal("10000"),
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        _order(s, sta.id, paid=Decimal("500"), kwh=Decimal("0"),
               created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        inv = r.json()["data"]["investment"]
        assert inv["total_cost"] == 10000.0
        # cum_margin=500, roi=500/10000×100=5.0
        assert inv["roi_rate"] == 5.0
        # months=1.0, monthly_avg=500, payback=10000/500=20.0
        assert inv["payback_months"] == 20.0

    def test_roi_null_without_total_cost(self, client):
        """无 total_cost → roi_rate/payback_months/total_cost 均为 null, 累计毛利仍算。"""
        s = client._sesh
        sta = _station(s, name="无成本站", code="OCNC", total_cost=None)
        _order(s, sta.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        inv = r.json()["data"]["investment"]
        assert inv["total_cost"] is None
        assert inv["roi_rate"] is None
        assert inv["payback_months"] is None
        assert inv["cumulative_gross_margin"] == 100.0

    def test_payback_null_when_nonpositive_margin(self, client):
        """月均毛利<=0 (无累计毛利) → payback_months null; roi_rate=0 (有 cost)。"""
        s = client._sesh
        _station(
            s, name="零毛利站", code="OCZM", gun_count=2,
            total_cost=Decimal("10000"),
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        s.commit()

        r = client.get(OV)
        assert r.status_code == 200
        inv = r.json()["data"]["investment"]
        assert inv["total_cost"] == 10000.0
        assert inv["roi_rate"] == 0.0          # 0 / 10000 × 100
        assert inv["payback_months"] is None   # monthly_avg=0 → null


# ───────────────────────── (l) 权限门 ─────────────────────────


class TestOwnerCockpitAuth:
    """未登录 → 401。"""

    def test_unauthenticated_401(self, anon_client):
        r = anon_client.get(OV)
        assert r.status_code == 401


# ───────────────────────── (m) DB 异常保护 (本卡新增) ─────────────────────────


class TestOwnerCockpitExceptionSafety:
    """关键聚合查询异常 → 500 中文兜底 + logger 记录, 不泄露堆栈。

    依赖源码新增的 try/except: handler 体异常经 logger.exception 记录后,
    返回 JSONResponse(500) 通用消息 (与 revenue_stats 同风格)。
    """

    def test_db_exception_returns_500(self, client, monkeypatch, caplog):
        import app.api.v1.owner_cockpit as oc

        # 模拟 handler 体内抛异常 (team_scope 在认证之后、聚合查询处调用):
        # 认证/middleware 仍走真实路径 (成功), 进入 handler 后触发异常 → 被新 try/except 兜住。
        def _boom(user):
            raise RuntimeError("simulated aggregation failure")

        monkeypatch.setattr(oc, "team_scope", _boom)
        caplog.set_level(logging.ERROR, logger=oc.logger.name)

        r = client.get(OV)
        assert r.status_code == 500, r.text
        # 不泄露内部堆栈, 返回通用中文消息 (区别于 FastAPI 默认 "Internal Server Error")
        assert "服务器内部错误" in r.text
        # logger.exception (ERROR 级) 被调用
        err_records = [
            rec for rec in caplog.records
            if rec.name == oc.logger.name and rec.levelno >= logging.ERROR
        ]
        assert err_records, "聚合异常应经 logger 记录 (ERROR 级)"

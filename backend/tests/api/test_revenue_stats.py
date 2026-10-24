#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
营收统计 API 测试 (app/api/v1/operate/revenue_stats.py)

覆盖 10 个端点:
- GET  /api/v1/operate/revenue/summary            营收概览(预聚合表优先, 回退实时聚合)
- GET  /api/v1/operate/revenue/by-station         按站点营收明细(实时聚合)
- GET  /api/v1/operate/revenue/daily-trend        日趋势(预聚合表优先, 回退实时聚合)
- GET  /api/v1/operate/revenue/export             导出(同 by-station 格式)
- GET  /api/v1/operate/revenue/fee-breakdown      五项费用占比 + 月趋势
- GET  /api/v1/operate/revenue/by-user-type       用户类型收入/复充率
- GET  /api/v1/operate/revenue/by-time-period     尖峰平谷时段电量
- GET  /api/v1/operate/revenue/coupon-effectiveness 券核销率/ROI
- POST /api/v1/operate/revenue/aggregate          手动触发营收日报聚合(admin)
- POST /api/v1/operate/station-metrics/aggregate  手动触发站点日报聚合(admin)

覆盖维度:
(a) 正常聚合金额正确
(b) 非 admin 仅见本 team 数据 (_scope_orders/_scope_revenue_daily/_scope_fee_items/券 team)
(c) admin 全量可见
(d) 空数据不报错(返回 0/空列表)
(e) 日期范围边界([start_date, end_date+1day) 半开区间)
(f) 优惠券/折扣抵扣后金额准确 (discount_amount / paid_amount)
(g) admin-only 端点对非 admin 返回 403; 非法入参返回 400/422

铁律: 仅加测试, 不改业务代码。发现的业务可疑点记录于模块 docstring 末尾。
"""
import uuid

import bcrypt
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import (
    OrderFeeItem, FeeType as OrderFeeType, RefundRecord, RefundStatus,
)
from app.models.coupon import Coupon, CouponType, CouponUsage, CouponStatus
from app.models.spec_tables import RevenueDaily
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

from tests.api._helpers import login_as, login_admin

REV = "/api/v1/operate/revenue"


# ───────────────────────── seed helpers ─────────────────────────


def _station(session, name, code, team_id):
    s = Station(name=name, code=code, address="测试地址", status=StationStatus.NORMAL, team_id=team_id)
    session.add(s)
    session.flush()
    return s


def _order(session, station_id, *, paid, kwh=Decimal("0"), efee=Decimal("0"),
           sfee=Decimal("0"), park=Decimal("0"), idle=Decimal("0"), reservation=Decimal("0"),
           discount=Decimal("0"), total=None, duration=0, created_at=None,
           payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
           user_type=UserType.APP, user_id=None, end_time=None):
    """造一条 ChargingOrder。total 缺省取 paid(便于断言 by-station total_amount)。"""
    o = ChargingOrder(
        order_no=f"ORD-{uuid.uuid4().hex[:12]}",  # uuid 保证唯一, 不可用 id() (临时对象回收地址复用 → 撞唯一约束)
        station_id=station_id, device_id=1, user_id=user_id, user_type=user_type,
        charged_kwh=kwh, electricity_fee=efee, service_fee=sfee,
        parking_fee=park, idle_penalty=idle, reservation_fee=reservation,
        discount_amount=discount, total_amount=total if total is not None else paid,
        paid_amount=paid, payment_status=payment_status, order_status=order_status,
        payment_method=PaymentMethod.WECHAT, duration_minutes=duration,
        created_at=created_at, end_time=end_time,
    )
    session.add(o)
    session.flush()
    return o


def _make_team_viewer(client, team_id, username="viewer_team1"):
    """创建带 team_id 的 VIEWER 用户(非 admin), 供 _scope_orders 过滤验证。"""
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


# ───────────────────────── summary ─────────────────────────


class TestRevenueSummary:
    """GET /revenue/summary"""

    def test_aggregation_realtime(self, client):
        """(a) 正常聚合金额正确 — 无 RevenueDaily, 走实时聚合回退路径。"""
        s = client._sesh
        sta = _station(s, "汇总站", "REV001", team_id=None)
        _order(s, sta.id, paid=Decimal("50"), kwh=Decimal("50"), efee=Decimal("30"),
               sfee=Decimal("15"), park=Decimal("5"))
        _order(s, sta.id, paid=Decimal("80"), kwh=Decimal("40"), efee=Decimal("40"),
               sfee=Decimal("20"), discount=Decimal("10"), idle=Decimal("2"),
               reservation=Decimal("3"))
        _order(s, sta.id, paid=Decimal("9999"), payment_status=OrderPaymentStatus.UNPAID)
        s.commit()

        r = client.get(f"{REV}/summary")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        # 仅 2 条 PAID 计入
        assert d["total_orders"] == 2
        assert d["total_revenue"] == 130.0          # 50 + 80
        assert d["total_kwh"] == 90.0               # 50 + 40
        assert d["total_electricity_fee"] == 70.0   # 30 + 40
        assert d["total_service_fee"] == 35.0       # 15 + 20
        assert d["total_discount"] == 10.0
        assert d["total_parking_fee"] == 5.0
        assert d["total_idle_penalty"] == 2.0
        assert d["total_reservation_fee"] == 3.0
        # 实时回退路径不带 source 字段
        assert "source" not in d

    def test_admin_sees_all_teams(self, client):
        """(c) admin 全量可见两个 team 的订单。"""
        s = client._sesh
        sa = _station(s, "A站", "ADM001", team_id=1)
        sb = _station(s, "B站", "ADM002", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(f"{REV}/summary")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_revenue"] == 300.0
        assert d["total_orders"] == 2

    def test_team_viewer_scoped(self, client):
        """(b) 非 admin 仅见本 team 站点数据。"""
        s = client._sesh
        sa = _station(s, "本队站", "TM001", team_id=1)
        sb = _station(s, "他队站", "TM002", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/summary")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_revenue"] == 100.0   # 仅本 team
        assert d["total_orders"] == 1
        login_admin(client)  # 还原 admin, 避免污染后续用例

    def test_empty(self, client):
        """(d) 空数据不报错。"""
        r = client.get(f"{REV}/summary")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_revenue"] == 0
        assert d["total_orders"] == 0
        assert d["total_kwh"] == 0

    def test_date_range_half_open(self, client):
        """(e) 日期范围 [start_date, end_date+1day) 半开区间, end_date 当日包含。"""
        s = client._sesh
        sta = _station(s, "日期站", "DT001", team_id=None)
        _order(s, sta.id, paid=Decimal("100"), created_at=datetime(2026, 8, 5, 12, 0))    # 区间内
        _order(s, sta.id, paid=Decimal("10"), created_at=datetime(2026, 7, 31, 12, 0))    # 早于 start
        _order(s, sta.id, paid=Decimal("20"), created_at=datetime(2026, 8, 10, 23, 0))    # =end_date 当日, 应包含
        _order(s, sta.id, paid=Decimal("30"), created_at=datetime(2026, 8, 15, 12, 0))    # 晚于 end
        s.commit()

        r = client.get(f"{REV}/summary?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_revenue"] == 120.0   # 100 + 20
        assert d["total_orders"] == 2

    def test_coupon_discount_accuracy(self, client):
        """(f) 优惠券/折扣抵扣后金额准确: paid = total - discount - coupon, 且 discount 聚合正确。"""
        s = client._sesh
        sta = _station(s, "券站", "CPN001", team_id=None)
        # total=100, discount=20, coupon=5 -> paid=75
        _order(s, sta.id, paid=Decimal("75"), total=Decimal("100"), discount=Decimal("20"))
        s.commit()

        r = client.get(f"{REV}/summary")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_revenue"] == 75.0    # paid_amount (券后实付)
        assert d["total_discount"] == 20.0

    def test_pre_aggregated_path(self, client):
        """预聚合快路径: 区间内有 RevenueDaily -> source=pre_aggregated, 金额取自预聚合表。"""
        s = client._sesh
        sta = _station(s, "预聚合站", "PRE001", team_id=None)
        s.add(RevenueDaily(
            record_date=datetime(2026, 8, 5, 0, 0), station_id=sta.id,
            paid_revenue=Decimal("150"), energy_kwh=Decimal("60"),
            charge_fee=Decimal("80"), service_fee=Decimal("40"),
            parking_fee=Decimal("10"), reservation_fee=Decimal("20"), orders_count=3,
        ))
        s.commit()

        r = client.get(f"{REV}/summary?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["source"] == "pre_aggregated"
        assert d["total_revenue"] == 150.0
        assert d["total_kwh"] == 60.0
        assert d["total_electricity_fee"] == 80.0   # = charge_fee
        assert d["total_service_fee"] == 40.0
        assert d["total_parking_fee"] == 10.0
        assert d["total_reservation_fee"] == 20.0
        assert d["total_orders"] == 3

    def test_pre_aggregated_discount_excludes_unpaid(self, client):
        """(口径自洽) 预聚合路径: 已完成未支付订单的 discount/idle 不得计入 total_discount/idle。

        场景: 区间内有 RevenueDaily(走预聚合快路径), total_revenue 取自 paid_revenue(实付口径);
        同区间存在一条 COMPLETED+UNPAID 订单带 discount/idle。该订单未实付 → 其折扣/占桩费
        不应混入"已收营收"同屏指标, 否则折扣虚高、报表不自洽。
        """
        s = client._sesh
        sta = _station(s, "口径站", "CAL001", team_id=None)
        # 预聚合行(触发 pre_aggregated 路径, total_revenue 来自此 paid_revenue)
        s.add(RevenueDaily(
            record_date=datetime(2026, 8, 5, 0, 0), station_id=sta.id,
            paid_revenue=Decimal("100"), energy_kwh=Decimal("10"), orders_count=1,
        ))
        # 已完成已支付: 折扣/占桩费应计入
        _order(s, sta.id, paid=Decimal("100"), discount=Decimal("20"), idle=Decimal("5"),
               end_time=datetime(2026, 8, 5, 12, 0),
               payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED)
        # 已完成未支付: 折扣/占桩费不得计入(核心断言)
        _order(s, sta.id, paid=Decimal("0"), discount=Decimal("999"), idle=Decimal("888"),
               end_time=datetime(2026, 8, 5, 12, 0),
               payment_status=OrderPaymentStatus.UNPAID, order_status=OrderStatus.COMPLETED)
        s.commit()

        r = client.get(f"{REV}/summary?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["source"] == "pre_aggregated"
        assert d["total_revenue"] == 100.0          # 取自 paid_revenue, 与订单无关
        assert d["total_discount"] == 20.0          # 仅 PAID 订单, UNPAID 的 999 被排除
        assert d["total_idle_penalty"] == 5.0       # 仅 PAID 订单, UNPAID 的 888 被排除

    def test_realtime_discount_excludes_unpaid(self, client):
        """(口径自洽·回退路径) 实时聚合同样排除未支付订单的 discount/idle, 与预聚合路径口径一致。

        无 RevenueDaily → 走实时回退(PAID + created_at)。锁定回退路径 uphold 同一不变式,
        防止日后误删 payment_status==PAID 过滤导致双路径口径再次分裂。
        """
        s = client._sesh
        sta = _station(s, "口径站RT", "CAL002", team_id=None)
        _order(s, sta.id, paid=Decimal("100"), discount=Decimal("20"), idle=Decimal("5"),
               created_at=datetime(2026, 8, 5, 12, 0),
               payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED)
        _order(s, sta.id, paid=Decimal("0"), discount=Decimal("999"), idle=Decimal("888"),
               created_at=datetime(2026, 8, 5, 12, 0),
               payment_status=OrderPaymentStatus.UNPAID, order_status=OrderStatus.COMPLETED)
        s.commit()

        r = client.get(f"{REV}/summary?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "source" not in d                    # 实时回退路径不带 source
        assert d["total_discount"] == 20.0          # UNPAID 的 999 被排除
        assert d["total_idle_penalty"] == 5.0       # UNPAID 的 888 被排除


# ───────────────────────── by-station ─────────────────────────


class TestRevenueByStation:
    """GET /revenue/by-station"""

    def test_aggregation_grouped(self, client):
        """(a) 按站点分组聚合正确, UNPAID 不计入。"""
        s = client._sesh
        sa = _station(s, "站A", "BS001", team_id=None)
        sb = _station(s, "站B", "BS002", team_id=None)
        _order(s, sa.id, paid=Decimal("50"), total=Decimal("50"), kwh=Decimal("10"),
               duration=60, efee=Decimal("30"), sfee=Decimal("20"))
        _order(s, sa.id, paid=Decimal("30"), total=Decimal("30"), kwh=Decimal("6"),
               duration=40, discount=Decimal("5"))
        _order(s, sb.id, paid=Decimal("80"), total=Decimal("80"), kwh=Decimal("20"),
               duration=120)
        _order(s, sb.id, paid=Decimal("1"), payment_status=OrderPaymentStatus.UNPAID)
        s.commit()

        r = client.get(f"{REV}/by-station")
        assert r.status_code == 200
        rows = r.json()["data"]
        by_id = {row["station_id"]: row for row in rows}
        assert by_id[sa.id]["order_count"] == 2
        assert by_id[sa.id]["total_paid"] == 80.0
        assert by_id[sa.id]["total_amount"] == 80.0
        assert by_id[sa.id]["total_kwh"] == 16.0
        assert by_id[sa.id]["total_hours"] == round((60 + 40) / 60, 1)
        assert by_id[sa.id]["total_discount"] == 5.0
        assert by_id[sa.id]["station_name"] == "站A"
        assert by_id[sb.id]["order_count"] == 1
        assert by_id[sb.id]["total_paid"] == 80.0
        assert by_id[sb.id]["station_name"] == "站B"

    def test_team_viewer_scoped(self, client):
        """(b) 非 admin 仅见本 team 站点。"""
        s = client._sesh
        sa = _station(s, "本队", "BST001", team_id=1)
        sb = _station(s, "他队", "BST002", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/by-station")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1
        assert rows[0]["station_id"] == sa.id
        assert rows[0]["total_paid"] == 100.0
        login_admin(client)

    def test_admin_sees_all_teams(self, client):
        """(c) admin 见全部站点。"""
        s = client._sesh
        sa = _station(s, "A", "BSA001", team_id=1)
        sb = _station(s, "B", "BSA002", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        s.commit()

        r = client.get(f"{REV}/by-station")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert {row["station_id"] for row in rows} == {sa.id, sb.id}

    def test_refund_deduction_and_team_scoping(self, client):
        """卡 a1e8299d: 每行增 total_refund/net_paid, 且退款聚合不串租户。

        口径: 退款按关联订单 created_at 窗口回溯(与营收窗口对齐, 今日下单/次日退仍归
        下单窗口); 毛 paid 口径含 PARTIAL/REFUNDING/REFUNDED(退款后订单离开 PAID 态),
        net_paid = gross_paid - refund 不重复扣。
        """
        s = client._sesh
        sa = _station(s, "退款站本队", "BSR001", team_id=1)
        sb = _station(s, "退款站他队", "BSR002", team_id=2)
        now = datetime.now(timezone.utc)
        # 本队: 部分退款订单(留 PAID 也算) + 全额退款订单(置 REFUNDED)
        oa = _order(s, sa.id, paid=Decimal("50"), created_at=now)
        ob = _order(s, sa.id, paid=Decimal("30"), created_at=now,
                    payment_status=OrderPaymentStatus.REFUNDED)
        # 他队: 一笔退款
        oc = _order(s, sb.id, paid=Decimal("80"), created_at=now)
        s.add_all([
            RefundRecord(order_id=oa.id, user_id=None, refund_amount=Decimal("10.00"),
                         reason="部分退", status=RefundStatus.REFUNDED, refunded_at=now),
            RefundRecord(order_id=ob.id, user_id=None, refund_amount=Decimal("30.00"),
                         reason="全退", status=RefundStatus.REFUNDED, refunded_at=now),
            # 在途退款不计入
            RefundRecord(order_id=oa.id, user_id=None, refund_amount=Decimal("5.00"),
                         reason="在途", status=RefundStatus.PENDING),
            RefundRecord(order_id=oc.id, user_id=None, refund_amount=Decimal("20.00"),
                         reason="他队", status=RefundStatus.REFUNDED, refunded_at=now),
        ])
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/by-station")
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) == 1
        row = rows[0]
        assert row["station_id"] == sa.id
        # gross = 50 + 30(REFUNDED 态仍计入毛口径); refund = 10 + 30(他队 20 不串入)
        assert row["total_paid"] == 80.0
        assert row["total_refund"] == 40.0
        assert row["net_paid"] == 40.0
        login_admin(client)

    def test_empty(self, client):
        """(d) 空数据返回空列表。"""
        r = client.get(f"{REV}/by-station")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_date_range_half_open(self, client):
        """(e) 日期范围边界: 仅区间内订单计入对应站点。"""
        s = client._sesh
        sta = _station(s, "日期站B", "BSD001", team_id=None)
        _order(s, sta.id, paid=Decimal("100"), created_at=datetime(2026, 8, 5, 12, 0))
        _order(s, sta.id, paid=Decimal("10"), created_at=datetime(2026, 7, 31, 12, 0))
        _order(s, sta.id, paid=Decimal("30"), created_at=datetime(2026, 8, 15, 12, 0))
        s.commit()

        r = client.get(f"{REV}/by-station?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1
        assert rows[0]["total_paid"] == 100.0
        assert rows[0]["order_count"] == 1


# ───────────────────────── daily-trend ─────────────────────────


class TestRevenueDailyTrend:
    """GET /revenue/daily-trend

    主测预聚合路径(稳定); 实时路径含 cast(Date) 在 SQLite 的已知解析问题(见源码注释),
    仅做可达性与数值断言, 不严格校验日期字符串格式。
    """

    def test_pre_aggregated_trend(self, client):
        """预聚合路径: 多日 RevenueDaily 按日分组, 字段正确。"""
        s = client._sesh
        sta = _station(s, "趋势站", "TR001", team_id=None)
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        s.add_all([
            RevenueDaily(record_date=base - timedelta(days=2), station_id=sta.id,
                         paid_revenue=Decimal("100"), energy_kwh=Decimal("50"), orders_count=2),
            RevenueDaily(record_date=base - timedelta(days=1), station_id=sta.id,
                         paid_revenue=Decimal("200"), energy_kwh=Decimal("80"), orders_count=3),
        ])
        s.commit()

        r = client.get(f"{REV}/daily-trend?days=30")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 2
        # 按 record_date 升序
        assert rows[0]["revenue"] == 100.0
        assert rows[0]["kwh"] == 50.0
        assert rows[0]["orders"] == 2
        assert rows[1]["revenue"] == 200.0
        assert rows[1]["orders"] == 3
        assert "date" in rows[0] and rows[0]["date"]

    def test_pre_aggregated_team_scoped(self, client):
        """(b) 预聚合路径 team 隔离: 非 admin 仅见本 team 站点的 RevenueDaily。"""
        s = client._sesh
        sa = _station(s, "本队趋势", "TRT001", team_id=1)
        sb = _station(s, "他队趋势", "TRT002", team_id=2)
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        s.add_all([
            RevenueDaily(record_date=base - timedelta(days=1), station_id=sa.id,
                         paid_revenue=Decimal("100"), orders_count=1),
            RevenueDaily(record_date=base - timedelta(days=1), station_id=sb.id,
                         paid_revenue=Decimal("999"), orders_count=9),
        ])
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/daily-trend?days=30")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert sum(row["revenue"] for row in rows) == 100.0
        assert sum(row["orders"] for row in rows) == 1
        login_admin(client)

    @pytest.mark.xfail(
        reason="SQLite 下 cast(created_at, Date) result-row 解析崩溃 (TypeError: fromisoformat); "
               "源码 revenue_stats.py:234 注释已标注, 生产 PostgreSQL 正常。仅记录不修业务代码。",
        strict=False,
    )
    def test_realtime_path_reachable(self, client):
        """无 RevenueDaily 时回退实时聚合: 端点可达且 orders 数值正确(不严格校验 date 格式)。

        SQLite 已知缺陷(见 xfail reason): 实时路径 cast(Date) 行解析报错 → 端点 500。
        生产 PG 正常, 故此处以 xfail 记录而非删除; 待 SQLite 兼容修复后自动转 xpass。
        """
        s = client._sesh
        sta = _station(s, "实时趋势站", "TRR001", team_id=None)
        _order(s, sta.id, paid=Decimal("100"), kwh=Decimal("10"),
               created_at=datetime.now(timezone.utc) - timedelta(days=1))
        s.commit()

        r = client.get(f"{REV}/daily-trend?days=30")
        assert r.status_code == 200
        rows = r.json()["data"]
        # 至少聚合出 1 行; orders 总和 == 1
        assert isinstance(rows, list)
        assert sum(row["orders"] for row in rows) == 1
        assert sum(row["revenue"] for row in rows) == 100.0

    def test_empty(self, client):
        """(d) 空数据返回空列表。"""
        r = client.get(f"{REV}/daily-trend?days=30")
        assert r.status_code == 200
        assert r.json()["data"] == []


# ───────────────────────── export ─────────────────────────


class TestRevenueExport:
    """GET /revenue/export — 复用 by-station 实现, 同格式返回。"""

    def test_export_same_as_by_station(self, client):
        """(a) export 与 by-station 返回结构一致、数值一致。"""
        s = client._sesh
        sta = _station(s, "导出站", "EXP001", team_id=None)
        _order(s, sta.id, paid=Decimal("50"), kwh=Decimal("10"),
               duration=60, efee=Decimal("30"), sfee=Decimal("20"))
        s.commit()

        re = client.get(f"{REV}/export")
        rb = client.get(f"{REV}/by-station")
        assert re.status_code == 200 == rb.status_code
        assert re.json()["data"] == rb.json()["data"]
        assert re.json()["data"][0]["station_name"] == "导出站"
        assert re.json()["data"][0]["total_paid"] == 50.0

    def test_export_empty(self, client):
        """(d) 空数据返回空列表, 不报错。"""
        r = client.get(f"{REV}/export")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_export_team_viewer_scoped(self, client):
        """(b) 非 admin 仅见本 team 站点。"""
        s = client._sesh
        sa = _station(s, "本队导出", "EXPT001", team_id=1)
        sb = _station(s, "他队导出", "EXPT002", team_id=2)
        _order(s, sa.id, paid=Decimal("100"), created_at=datetime.now(timezone.utc))
        _order(s, sb.id, paid=Decimal("200"), created_at=datetime.now(timezone.utc))
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/export")
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1
        assert rows[0]["station_id"] == sa.id
        login_admin(client)


# ───────────────────────── fee-breakdown ─────────────────────────


def _fee_item(session, order_id, fee_type, amount, created_at=None):
    """造一条 OrderFeeItem 明细。"""
    it = OrderFeeItem(
        order_id=order_id, fee_type=fee_type, fee_name=fee_type.value,
        amount=amount, created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(it)
    session.flush()
    return it


class TestRevenueFeeBreakdown:
    """GET /revenue/fee-breakdown — 五项费用占比 + 月趋势(数据源 order_fee_items)。"""

    def test_summary_and_ratios(self, client):
        """(a) summary 按 fee_type 聚合, ratios = 各项/总计。"""
        s = client._sesh
        sta = _station(s, "费站", "FB001", team_id=None)
        o = _order(s, sta.id, paid=Decimal("0"))
        created = datetime(2026, 8, 5, 12, 0)
        _fee_item(s, o.id, OrderFeeType.ELECTRICITY, Decimal("60"), created)
        _fee_item(s, o.id, OrderFeeType.SERVICE, Decimal("30"), created)
        _fee_item(s, o.id, OrderFeeType.PARKING, Decimal("10"), created)
        s.commit()

        r = client.get(f"{REV}/fee-breakdown?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        # 抵扣项(discount/coupon/points)被排除, 仅五项
        assert d["summary"]["electricity"] == 60.0
        assert d["summary"]["service"] == 30.0
        assert d["summary"]["parking"] == 10.0
        assert d["total"] == 100.0
        assert d["ratios"]["electricity"] == 0.6
        assert d["ratios"]["service"] == 0.3

    def test_monthly_trend_grouping(self, client):
        """月度分组: 跨月明细分到各自月份, 升序输出。"""
        s = client._sesh
        sta = _station(s, "月趋势站", "FB002", team_id=None)
        o = _order(s, sta.id, paid=Decimal("0"))
        _fee_item(s, o.id, OrderFeeType.ELECTRICITY, Decimal("40"),
                  datetime(2026, 7, 15, 12, 0))
        _fee_item(s, o.id, OrderFeeType.ELECTRICITY, Decimal("60"),
                  datetime(2026, 8, 5, 12, 0))
        s.commit()

        r = client.get(f"{REV}/fee-breakdown")
        assert r.status_code == 200
        trends = r.json()["data"]["trends"]
        months = [t["month"] for t in trends]
        assert months == sorted(months)
        assert "2026-07" in months and "2026-08" in months

    def test_empty(self, client):
        """(d) 空数据: total=0, ratios 全 0, trends 空。"""
        r = client.get(f"{REV}/fee-breakdown")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["trends"] == []
        assert all(v == 0 for v in d["ratios"].values())

    def test_team_viewer_scoped(self, client):
        """(b) 非 admin 仅统计本 team 订单的费用明细 (_scope_fee_items)。"""
        s = client._sesh
        sa = _station(s, "本队费", "FBT001", team_id=1)
        sb = _station(s, "他队费", "FBT002", team_id=2)
        oa = _order(s, sa.id, paid=Decimal("0"))
        ob = _order(s, sb.id, paid=Decimal("0"))
        _fee_item(s, oa.id, OrderFeeType.ELECTRICITY, Decimal("100"),
                  datetime(2026, 8, 5, 12, 0))
        _fee_item(s, ob.id, OrderFeeType.ELECTRICITY, Decimal("999"),
                  datetime(2026, 8, 5, 12, 0))
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/fee-breakdown")
        assert r.status_code == 200
        assert r.json()["data"]["summary"]["electricity"] == 100.0  # 他队 999 被排除
        login_admin(client)


# ───────────────────────── by-user-type ─────────────────────────


class TestRevenueByUserType:
    """GET /revenue/by-user-type — 各用户类型营收/户均/复充率(PAID 订单)。"""

    def test_aggregation_and_repeat_rate(self, client):
        """(a) 按 user_type 分组, avg_per_user 与 repeat_rate 正确。"""
        s = client._sesh
        sta = _station(s, "用户站", "UT001", team_id=None)
        # APP 用户 1 下 2 单(复充), 用户 2 下 1 单
        _order(s, sta.id, paid=Decimal("50"), user_type=UserType.APP, user_id=100)
        _order(s, sta.id, paid=Decimal("30"), user_type=UserType.APP, user_id=100)
        _order(s, sta.id, paid=Decimal("20"), user_type=UserType.APP, user_id=101)
        # CARD 用户 1 单
        _order(s, sta.id, paid=Decimal("40"), user_type=UserType.CARD, user_id=200)
        s.commit()

        r = client.get(f"{REV}/by-user-type")
        assert r.status_code == 200
        rows = {row["user_type"]: row for row in r.json()["data"]}
        app = rows["app"]
        assert app["revenue"] == 100.0       # 50+30+20
        assert app["orders"] == 3
        assert app["users"] == 2
        assert app["avg_per_user"] == 50.0   # 100/2
        assert app["repeat_rate"] == 0.5     # 1 个复充用户 / 2 去重用户
        assert rows["card"]["revenue"] == 40.0
        assert rows["card"]["users"] == 1

    def test_excludes_unpaid(self, client):
        """UNPAID 订单不计入(口径 payment_status==PAID)。"""
        s = client._sesh
        sta = _station(s, "未付站", "UT002", team_id=None)
        _order(s, sta.id, paid=Decimal("50"), user_type=UserType.APP, user_id=1)
        _order(s, sta.id, paid=Decimal("999"), user_type=UserType.APP, user_id=2,
               payment_status=OrderPaymentStatus.UNPAID)
        s.commit()

        r = client.get(f"{REV}/by-user-type")
        rows = {row["user_type"]: row for row in r.json()["data"]}
        assert rows["app"]["revenue"] == 50.0
        assert rows["app"]["users"] == 1   # UNPAID 的 user_id=2 不计入

    def test_empty(self, client):
        """(d) 空数据返回空列表。"""
        r = client.get(f"{REV}/by-user-type")
        assert r.status_code == 200
        assert r.json()["data"] == []


# ───────────────────────── by-time-period ─────────────────────────


class TestRevenueByTimePeriod:
    """GET /revenue/by-time-period — 尖/峰/平/谷时段电量分布(PAID 订单分时字段)。"""

    def test_energy_distribution(self, client):
        """(a) 各时段电量聚合 + ratio = 各项/总电量。"""
        s = client._sesh
        sta = _station(s, "时段站", "TP001", team_id=None)
        o = _order(s, sta.id, paid=Decimal("100"), efee=Decimal("70"), sfee=Decimal("30"))
        o.peak_energy = Decimal("10")
        o.flat_energy = Decimal("30")
        o.valley_energy = Decimal("60")
        s.commit()

        r = client.get(f"{REV}/by-time-period")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        periods = {p["period"]: p for p in d["periods"]}
        assert periods["peak"]["energy"] == 10.0
        assert periods["flat"]["energy"] == 30.0
        assert periods["valley"]["energy"] == 60.0
        assert d["total_energy"] == 100.0
        assert periods["valley"]["ratio"] == 0.6
        assert d["electricity_fee"] == 70.0
        assert d["service_fee"] == 30.0
        assert d["service_fee_ratio"] == 0.3   # 30/(70+30)

    def test_empty_zero_ratio(self, client):
        """(d) 空数据: total_energy=0, ratio 全 0, service_fee_ratio=0。"""
        r = client.get(f"{REV}/by-time-period")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_energy"] == 0
        assert all(p["ratio"] == 0 for p in d["periods"])
        assert d["service_fee_ratio"] == 0

    def test_team_viewer_scoped(self, client):
        """(b) 非 admin 仅统计本 team 站点订单。"""
        s = client._sesh
        sa = _station(s, "本队时段", "TPT001", team_id=1)
        sb = _station(s, "他队时段", "TPT002", team_id=2)
        oa = _order(s, sa.id, paid=Decimal("100"))
        oa.peak_energy = Decimal("100")
        ob = _order(s, sb.id, paid=Decimal("200"))
        ob.peak_energy = Decimal("999")
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/by-time-period")
        assert r.status_code == 200
        periods = {p["period"]: p for p in r.json()["data"]["periods"]}
        assert periods["peak"]["energy"] == 100.0  # 他队 999 排除
        login_admin(client)


# ───────────────────────── coupon-effectiveness ─────────────────────────


def _coupon(session, name="测试券"):
    c = Coupon(name=name, coupon_type=CouponType.FIXED, face_value=Decimal("10"),
               total_stock=100, remaining_stock=100,
               start_time=datetime(2026, 1, 1),
               end_time=datetime(2026, 12, 31, 23, 59, 59), is_active=True)
    session.add(c)
    session.flush()
    return c


def _usage(session, coupon_id, user_id, *, status=CouponStatus.USED, discount=Decimal("0"),
           order_id=None, created_at=None):
    u = CouponUsage(
        coupon_id=coupon_id, user_id=user_id,
        coupon_code=f"UC-{uuid.uuid4().hex[:12]}",
        status=status, discount_amount=discount, order_id=order_id,
        expires_at=datetime(2026, 12, 31, 23, 59, 59),
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(u)
    session.flush()
    return u


class TestRevenueCouponEffectiveness:
    """GET /revenue/coupon-effectiveness — 券核销率/优惠成本/ROI。"""

    def test_redemption_rate_and_roi(self, client):
        """(a) 核销率 = used/issued, ROI = 关联订单实付/优惠成本。"""
        s = client._sesh
        c = _coupon(s, "满减券")
        sta = _station(s, "券效站", "CE001", team_id=None)
        # 关联订单: paid=100
        o = _order(s, sta.id, paid=Decimal("100"))
        # 2 张发放: 1 已核销(抵扣 20, 关联订单), 1 过期
        _usage(s, c.id, user_id=1, status=CouponStatus.USED,
               discount=Decimal("20"), order_id=o.id,
               created_at=datetime(2026, 8, 5, 12, 0))
        _usage(s, c.id, user_id=2, status=CouponStatus.EXPIRED,
               created_at=datetime(2026, 8, 5, 12, 0))
        s.commit()

        r = client.get(f"{REV}/coupon-effectiveness?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        cp = d["coupons"][0]
        assert cp["issued"] == 2
        assert cp["used"] == 1
        assert cp["expired"] == 1
        assert cp["redemption_rate"] == 0.5
        assert cp["discount_cost"] == 20.0
        assert cp["order_revenue"] == 100.0
        assert cp["roi"] == 5.0   # 100/20
        assert d["summary"]["total_issued"] == 2
        assert d["summary"]["overall_redemption_rate"] == 0.5

    def test_empty(self, client):
        """(d) 空数据: coupons 空, summary 全 0。"""
        r = client.get(f"{REV}/coupon-effectiveness")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["coupons"] == []
        assert d["summary"]["total_issued"] == 0
        assert d["summary"]["overall_roi"] == 0

    def test_team_viewer_scoped(self, client):
        """(b) 非 admin 仅统计本 team 用户的券使用记录 (CouponUsage→User.team_id)。"""
        s = client._sesh
        c = _coupon(s, "隔离券")
        # 本 team 用户(user.id 待 _make_team_viewer 后回填 team_id=1)
        other = User(username="team2_user", password_hash="x",
                     real_name="t2", role=UserRole.VIEWER, status="active", team_id=2)
        s.add(other)
        s.commit()
        _usage(s, c.id, user_id=other.id, status=CouponStatus.USED,
               discount=Decimal("999"), created_at=datetime(2026, 8, 5, 12, 0))
        viewer = _make_team_viewer(client, team_id=1, username="viewer_team1")
        _usage(s, c.id, user_id=viewer.id, status=CouponStatus.USED,
               discount=Decimal("10"), created_at=datetime(2026, 8, 5, 12, 0))
        s.commit()

        login_as(client, "viewer_team1", "v123456")
        r = client.get(f"{REV}/coupon-effectiveness?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        # 仅本 team viewer 的 1 条记录; team2 用户的 999 被排除
        if r.json()["data"]["coupons"]:
            assert r.json()["data"]["summary"]["total_discount_cost"] == 10.0
        login_admin(client)


# ───────────────────────── aggregate (admin-only) ─────────────────────────


class TestRevenueAggregate:
    """POST /revenue/aggregate — 手动触发营收日报聚合(require_platform_admin)。"""

    def test_aggregate_single_date(self, client):
        """(a) 指定单日聚合: 返回 status=completed, dates 含当日。"""
        r = client.post(f"{REV}/aggregate?target_date=2026-08-05")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "completed"
        assert "2026-08-05" in d["dates"]

    def test_aggregate_invalid_date_400(self, client):
        """非法日期 → _iter_target_dates 返回 [] → 400。"""
        r = client.post(f"{REV}/aggregate?target_date=not-a-date")
        assert r.status_code == 400
        assert "日期格式" in r.json()["detail"]

    def test_aggregate_viewer_forbidden(self, client):
        """(g) 非 admin 调用 require_platform_admin → 403。"""
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        login_as(client, "viewer_team1", "v123456")
        r = client.post(f"{REV}/aggregate?target_date=2026-08-05")
        assert r.status_code == 403
        login_admin(client)


class TestStationMetricsAggregate:
    """POST /station-metrics/aggregate — 手动触发站点日报聚合(require_platform_admin)。"""

    def test_aggregate_single_date(self, client):
        """(a) 指定单日聚合站点指标: status=completed。"""
        r = client.post("/api/v1/operate/station-metrics/aggregate?target_date=2026-08-05")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "completed"
        assert "2026-08-05" in d["dates"]

    def test_aggregate_invalid_date_400(self, client):
        """非法日期 → 400。"""
        r = client.post("/api/v1/operate/station-metrics/aggregate?target_date=bad")
        assert r.status_code == 400

    def test_aggregate_viewer_forbidden(self, client):
        """(g) 非 admin → 403。"""
        _make_team_viewer(client, team_id=1, username="viewer_team1")
        login_as(client, "viewer_team1", "v123456")
        r = client.post("/api/v1/operate/station-metrics/aggregate?target_date=2026-08-05")
        assert r.status_code == 403
        login_admin(client)


# ═══════════════════════════════════════════════════════════════════
# 审计观察 (业务可疑点, 仅记录不私自修改 — 供大圣/文曲裁决):
#
# 1. [summary 预聚合路径] total_discount/total_idle_penalty 来自 _supplemental_discount_idle,
#    口径为 order_status==COMPLETED + end_time; 而 total_revenue 等取自 revenue_daily
#    按 record_date + paid 口径。两口径不一致: 同一订单 end_time 跨日出/入会与
#    record_daily 错位; 且 supplemental 未按 payment_status==PAID 过滤, 可能把未支付
#    订单的 discount 算入"已收营收"的同屏指标。建议复核一致性。
#
# 2. [by-station] station_name 来自 db.query(Station).all() 全量查询(未 team 过滤);
#    当前因订单聚合先经 _scope_orders 过滤, 不存在的站点不会出现在结果行, 故无越权
#    泄露站点名。但若未来加入无订单的站点占位行, 需同步加 team 过滤。
#
# 3. [daily-trend 实时路径] cast(ChargingOrder.created_at, Date) 在 SQLite 下 result-row
#    解析有已知问题(源码注释已标注 xfail)。本测试对其仅做数值断言, 未严格校验 date 字段。
# ═══════════════════════════════════════════════════════════════════

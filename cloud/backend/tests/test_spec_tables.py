#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPEC §4 缺口补齐表测试 (ops-platform-spec.md)

覆盖 backend/app/models/spec_tables.py 的 11 个新表, 每表至少 2 个用例:
- 结构验证: 列 + 索引 + 表名
- CRUD: 建实例 -> 提交 -> 刷新 -> 断言字段

注: invoices / coupon_claims / points_logs / discount_prices 已有近似表覆盖,
    查重跳过(详见 spec_tables.py 文档串), 不在本测试范围。
"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.spec_tables import (
    AppUser, CardUser, VinUser,
    InterconnectPlatform, InterconnectUser,
    EnterpriseAccount, EnterpriseSubUser, BillingCycle,
    CouponActivityStat,
    OrderChargeCurve,
    RevenueDaily, StationDailyMetric,
)


# ═══════════════════════════════════════════════════════════════════
# 元数据注册: 11 张表必须在 Base.metadata 中
# ═══════════════════════════════════════════════════════════════════

SPEC_TABLES = [
    "app_users", "card_users", "vin_users",
    "interconnect_platforms", "interconnect_users",
    "enterprise_accounts", "enterprise_sub_users",
    "coupon_activity_stats", "order_charge_curves",
    "revenue_daily", "station_daily_metrics",
]


def test_all_spec_tables_registered():
    """11 张 SPEC 缺口表均注册到 Base.metadata"""
    from app.core.database import Base
    registered = set(Base.metadata.tables.keys())
    missing = [t for t in SPEC_TABLES if t not in registered]
    assert missing == [], f"未注册的表: {missing}"


# ═══════════════════════════════════════════════════════════════════
# 用户类型
# ═══════════════════════════════════════════════════════════════════

class TestAppUser:
    def test_columns_and_tablename(self):
        assert AppUser.__tablename__ == "app_users"
        cols = [c.name for c in AppUser.__table__.columns]
        for c in ["id", "user_id", "phone", "nickname", "avatar", "balance",
                  "total_charge_kwh", "total_spent", "level", "points", "status", "created_at"]:
            assert c in cols, f"缺列 {c}"

    def test_crud(self, db_session):
        u = AppUser(
            user_id=101, phone="13800000001", nickname="张三",
            avatar="https://cdn/a.png", balance=Decimal("100.50"),
            total_charge_kwh=Decimal("1234.56"), total_spent=Decimal("800.00"),
            level=3, points=500, status="active",
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        assert u.id is not None
        assert u.phone == "13800000001"
        assert float(u.balance) == 100.50
        assert u.level == 3
        assert u.points == 500

    def test_phone_unique(self, db_session):
        db_session.add(AppUser(user_id=1, phone="13900000000"))
        db_session.commit()
        db_session.add(AppUser(user_id=2, phone="13900000000"))
        with pytest.raises(Exception):
            db_session.commit()


class TestCardUser:
    def test_columns(self):
        cols = [c.name for c in CardUser.__table__.columns]
        for c in ["card_no", "user_id", "holder_name", "bind_phone", "balance",
                  "status", "issued_at", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        c = CardUser(
            card_no="CARD0001", user_id=5, holder_name="李四",
            bind_phone="13800000002", balance=Decimal("50.00"),
            status="active", issued_at=datetime(2026, 1, 1),
        )
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)
        assert c.id is not None
        assert c.card_no == "CARD0001"
        assert c.holder_name == "李四"
        assert c.issued_at == datetime(2026, 1, 1)


class TestVinUser:
    def test_columns(self):
        cols = [c.name for c in VinUser.__table__.columns]
        for c in ["vin", "brand", "model", "plate_number", "user_id",
                  "bind_phone", "auto_pay_account", "status", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        v = VinUser(
            vin="LSGAB52L7DF000001", brand="BYD", model="汉EV",
            plate_number="京A12345", user_id=9, bind_phone="13800000003",
            auto_pay_account="im_b-o123", status="active",
        )
        db_session.add(v)
        db_session.commit()
        db_session.refresh(v)
        assert v.id is not None
        assert v.vin == "LSGAB52L7DF000001"
        assert v.brand == "BYD"
        assert v.plate_number == "京A12345"


class TestInterconnectPlatform:
    def test_columns_and_indexes(self):
        assert InterconnectPlatform.__tablename__ == "interconnect_platforms"
        cols = [c.name for c in InterconnectPlatform.__table__.columns]
        for c in ["platform_name", "platform_code", "api_key", "contact", "phone",
                  "revenue_share_ratio", "bind_date", "status", "created_at"]:
            assert c in cols
        idx = [i.name for i in InterconnectPlatform.__table__.indexes]
        assert "idx_iplat_code" in idx

    def test_crud(self, db_session):
        p = InterconnectPlatform(
            platform_name="华为充电", platform_code="huawei",
            api_key="sk-xxx", contact="王经理", phone="010-12345678",
            revenue_share_ratio=Decimal("0.7000"), bind_date=datetime(2026, 6, 1),
            status="active",
        )
        db_session.add(p)
        db_session.commit()
        db_session.refresh(p)
        assert p.id is not None
        assert p.platform_code == "huawei"
        assert float(p.revenue_share_ratio) == 0.7000


class TestInterconnectUser:
    def test_columns(self):
        cols = [c.name for c in InterconnectUser.__table__.columns]
        for c in ["platform_id", "outer_user_id", "nickname", "phone", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        # 先建平台
        plat = InterconnectPlatform(platform_name="国网", platform_code="sgcc")
        db_session.add(plat)
        db_session.commit()
        db_session.refresh(plat)
        u = InterconnectUser(platform_id=plat.id, outer_user_id="SGCC-U001",
                             nickname="外部用户", phone="13800000004")
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        assert u.id is not None
        assert u.platform_id == plat.id
        assert u.outer_user_id == "SGCC-U001"


class TestEnterpriseAccount:
    def test_billing_cycle_enum(self):
        assert BillingCycle.MONTHLY.value == "monthly"
        assert BillingCycle.QUARTERLY.value == "quarterly"

    def test_columns(self):
        cols = [c.name for c in EnterpriseAccount.__table__.columns]
        for c in ["enterprise_name", "credit_code", "contact_person", "contact_phone",
                  "balance", "billing_cycle", "status", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        ea = EnterpriseAccount(
            enterprise_name="测试科技", credit_code="91110000MA01ABC23X",
            contact_person="赵总", contact_phone="010-87654321",
            balance=Decimal("50000.00"), billing_cycle=BillingCycle.QUARTERLY,
            status="active",
        )
        db_session.add(ea)
        db_session.commit()
        db_session.refresh(ea)
        assert ea.id is not None
        assert ea.enterprise_name == "测试科技"
        assert ea.billing_cycle == BillingCycle.QUARTERLY
        assert ea.credit_code == "91110000MA01ABC23X"


class TestEnterpriseSubUser:
    def test_columns(self):
        cols = [c.name for c in EnterpriseSubUser.__table__.columns]
        for c in ["enterprise_id", "user_id", "department", "budget_limit", "status", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        ea = EnterpriseAccount(enterprise_name="母公司", billing_cycle=BillingCycle.MONTHLY)
        db_session.add(ea)
        db_session.commit()
        db_session.refresh(ea)
        sub = EnterpriseSubUser(
            enterprise_id=ea.id, user_id=77, department="研发部",
            budget_limit=Decimal("10000.00"), status="active",
        )
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)
        assert sub.id is not None
        assert sub.enterprise_id == ea.id
        assert sub.department == "研发部"
        assert float(sub.budget_limit) == 10000.00


# ═══════════════════════════════════════════════════════════════════
# 优惠管理
# ═══════════════════════════════════════════════════════════════════

class TestCouponActivityStat:
    def test_columns(self):
        cols = [c.name for c in CouponActivityStat.__table__.columns]
        for c in ["coupon_id", "total_claimed", "total_used", "total_discount_amount", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        st = CouponActivityStat(
            coupon_id=42, total_claimed=1000, total_used=620,
            total_discount_amount=Decimal("18600.00"),
        )
        db_session.add(st)
        db_session.commit()
        db_session.refresh(st)
        assert st.id is not None
        assert st.coupon_id == 42
        assert st.total_claimed == 1000
        assert st.total_used == 620
        assert float(st.total_discount_amount) == 18600.00


# ═══════════════════════════════════════════════════════════════════
# 订单与费用
# ═══════════════════════════════════════════════════════════════════

class TestOrderChargeCurve:
    def test_columns_and_indexes(self):
        assert OrderChargeCurve.__tablename__ == "order_charge_curves"
        cols = [c.name for c in OrderChargeCurve.__table__.columns]
        for c in ["order_id", "record_time", "current_power", "energy_this_minute",
                  "voltage", "current", "soc"]:
            assert c in cols
        idx = [i.name for i in OrderChargeCurve.__table__.indexes]
        assert "idx_occ_order_time" in idx

    def test_crud(self, db_session):
        # 一条订单写多条曲线点
        points = []
        for i in range(3):
            points.append(OrderChargeCurve(
                order_id=5001,
                record_time=datetime(2026, 7, 21, 10, 0, i),
                current_power=Decimal("60.00"),
                energy_this_minute=Decimal("1.0000"),
                voltage=Decimal("400.00"),
                current=Decimal("150.00"),
                soc=Decimal(f"{20 + i}.00"),
            ))
        db_session.add_all(points)
        db_session.commit()
        for p in points:
            db_session.refresh(p)
            assert p.id is not None
            assert p.order_id == 5001
        assert points[0].soc == Decimal("20.00")
        assert points[2].soc == Decimal("22.00")


# ═══════════════════════════════════════════════════════════════════
# 运营分析
# ═══════════════════════════════════════════════════════════════════

class TestRevenueDaily:
    def test_columns(self):
        cols = [c.name for c in RevenueDaily.__table__.columns]
        for c in ["record_date", "user_type", "station_id", "orders_count", "energy_kwh",
                  "charge_fee", "service_fee", "parking_fee", "occupancy_fee",
                  "reservation_fee", "total_revenue", "paid_revenue", "refund_amount", "created_at"]:
            assert c in cols

    def test_crud(self, db_session):
        r = RevenueDaily(
            record_date=datetime(2026, 7, 20), user_type="app", station_id=1,
            orders_count=150, energy_kwh=Decimal("3000.00"),
            charge_fee=Decimal("2400.00"), service_fee=Decimal("900.00"),
            parking_fee=Decimal("150.00"), occupancy_fee=Decimal("30.00"),
            reservation_fee=Decimal("0.00"),
            total_revenue=Decimal("3480.00"), paid_revenue=Decimal("3400.00"),
            refund_amount=Decimal("80.00"),
        )
        db_session.add(r)
        db_session.commit()
        db_session.refresh(r)
        assert r.id is not None
        assert r.user_type == "app"
        assert r.orders_count == 150
        assert float(r.total_revenue) == 3480.00


class TestStationDailyMetric:
    def test_columns_and_indexes(self):
        assert StationDailyMetric.__tablename__ == "station_daily_metrics"
        cols = [c.name for c in StationDailyMetric.__table__.columns]
        for c in ["station_id", "record_date", "active_users", "new_users", "orders_count",
                  "energy_kwh", "revenue", "utilization_rate", "avg_charge_duration",
                  "avg_wait_time", "online_devices", "idle_ratio", "created_at"]:
            assert c in cols
        idx = [i.name for i in StationDailyMetric.__table__.indexes]
        assert "idx_sdm_station_date" in idx

    def test_crud(self, db_session):
        m = StationDailyMetric(
            station_id=7, record_date=datetime(2026, 7, 20),
            active_users=320, new_users=12, orders_count=210,
            energy_kwh=Decimal("4200.00"), revenue=Decimal("5200.00"),
            utilization_rate=Decimal("68.50"), avg_charge_duration=55,
            avg_wait_time=8, online_devices=10, idle_ratio=Decimal("31.50"),
        )
        db_session.add(m)
        db_session.commit()
        db_session.refresh(m)
        assert m.id is not None
        assert m.station_id == 7
        assert m.active_users == 320
        assert float(m.utilization_rate) == 68.50
        assert m.online_devices == 10

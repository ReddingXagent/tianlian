#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
车队充电统计 API 测试 (app/api/v1/fleet_charging_stats.py)

覆盖 2 个端点:
- GET /api/v1/enterprises/{eid}/vehicles/{vid}/charging-stats  单车充电统计(累计+月趋势)
- GET /api/v1/enterprises/{eid}/charging-stats                 车队级汇总(总量+排行+场站分布)

覆盖维度:
(a) 单车累计聚合正确 (次数/电量/金额/平均单次)
(b) 车队汇总 + Top N 排行 + 场站分布
(c) _build_monthly_trend 边界: 多月分组排序 / 近12月窗口(累计含·趋势不含)
(d) 日期过滤: start_date / end_date 半开区间(含当天) / 非法格式 400
(e) team scoping (第二层鉴权): 跨团队企业 → 404 (不泄露存在, 非 403); admin 豁免
(f) 权限门: 未登录 → 401
(g) 关联路径: vehicle_id=None 靠 plate_number 匹配 (or_ 分支)
(h) order_status 过滤: 仅 COMPLETED 计入
(i) 边界: 资源不存在 404 / top_n 越界 422 / 超大日期范围 / 企业无车辆早返回

铁律: 仅加测试, 不改业务代码。发现的业务可疑点记录于模块 docstring 末尾。

注: 同名根目录 tests/test_fleet_charging_stats.py 已有 11 个 admin 视角用例 (commit
3621a754a); 本文件补全 team 隔离/权限门/趋势边界/车牌匹配等真实缺口, 并改用
conftest.client fixture (规范位置 tests/api/, 避免旧文件 module-level TestClient +
SessionLocal 直连的隔离隐患)。
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus,
)
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

from tests.api._helpers import login_as, login_admin

VEH_URL = "/api/v1/enterprises/{eid}/vehicles/{vid}/charging-stats"
ENT_URL = "/api/v1/enterprises/{eid}/charging-stats"

# 固定 aware 日期 (2026-08-08 为当前日): 均落在趋势近12月窗口内 (>= now-365d)
# 注: 硬编码日期仅供 summary/显式日期参数类测试 (无 now 窗口, 不随时间腐烂);
# 断言 monthly_trend 的测试 (受 now-365d 窗口约束) 须动态取 now 附近日期, 见 _recent_month。
_JUN = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)   # 窗口内, 今年6月
_JUL = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)   # 窗口内, 今年7月
_OLD = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)   # >365天前, 窗口外


def _recent_month(base, months_back):
    """base 所在月往前推 months_back 个月的 15 日 12:00 UTC (卡 7b7a7444)。

    趋势窗口下界 = now-365d, 上月/上上月 15 日距今恒 < 75 天, 永在窗口内;
    且任意相邻两个月必不同 year-month, 满足跨月分组断言。
    """
    total = base.year * 12 + (base.month - 1) - months_back
    year, month = divmod(total, 12)
    return datetime(year, month + 1, 15, 12, 0, tzinfo=timezone.utc)


# ───────────────────────── seed helpers ─────────────────────────


def _enterprise(session, name, code, owner_team_id=None):
    ent = Enterprise(
        name=name, code=code, owner_team_id=owner_team_id,
        status=EnterpriseStatus.ACTIVE,
    )
    session.add(ent)
    session.flush()
    return ent


def _vehicle(session, ent_id, plate, vin):
    v = EnterpriseVehicle(
        enterprise_id=ent_id, plate_number=plate, vin=vin,
        status=EnterpriseVehicleStatus.ACTIVE,
    )
    session.add(v)
    session.flush()
    return v


def _station(session, name, code, team_id=None):
    s = Station(
        name=name, code=code, address="测试地址",
        status=StationStatus.NORMAL, team_id=team_id,
    )
    session.add(s)
    session.flush()
    return s


def _order(session, *, vehicle_id=None, plate_number=None, station_id=None,
           kwh=Decimal("50"), amount=Decimal("80"), start=None,
           order_status=OrderStatus.COMPLETED):
    """造一条 ChargingOrder。start 缺省取 now (aware)。amount 同时写入 total/paid。"""
    if start is None:
        start = datetime.now(timezone.utc)
    o = ChargingOrder(
        order_no=f"CO-{uuid.uuid4().hex[:12]}",
        station_id=station_id, device_id=1,
        vehicle_id=vehicle_id, plate_number=plate_number,
        start_time=start, end_time=start + timedelta(hours=1),
        duration_minutes=60,
        charged_kwh=kwh,
        electricity_fee=amount, service_fee=Decimal("0"),
        total_amount=amount, paid_amount=amount,
        order_status=order_status, payment_status=OrderPaymentStatus.PAID,
    )
    session.add(o)
    session.flush()
    return o


def _make_team_user(client, team_id, username, role=UserRole.VIEWER, password="v123456"):
    """创建带 team_id 的非 admin 用户 (viewer/engineer), 供 team scoping 验证。"""
    s = client._sesh
    existing = s.query(User).filter(User.username == username).first()
    if existing:
        existing.team_id = team_id
        existing.role = role
        s.commit()
        return existing
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        real_name=username, role=role, status="active", team_id=team_id,
    )
    s.add(u)
    s.commit()
    return u


# ════════════════════════ 单车充电统计 ════════════════════════


class TestVehicleChargingStats:
    """GET /enterprises/{eid}/vehicles/{vid}/charging-stats"""

    def test_aggregation_correct(self, client):
        """(a) 累计聚合: 次数/电量/金额/平均单次 均正确。"""
        s = client._sesh
        ent = _enterprise(s, "车队A", "FCS001")
        v = _vehicle(s, ent.id, "京A11111", "LSVAU2189N2000011")
        sta = _station(s, "站A", "ST001")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("30"), amount=Decimal("48"), start=_JUN)
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 2
        assert d["summary"]["total_kwh"] == 80.0
        assert d["summary"]["total_amount"] == 128.0
        assert d["summary"]["avg_kwh_per_order"] == 40.0     # 80/2
        assert d["summary"]["avg_amount_per_order"] == 64.0  # 128/2
        assert d["vehicle"]["id"] == v.id
        assert d["vehicle"]["plate_number"] == "京A11111"

    def test_empty_zero_structure(self, client):
        """(a) 零订单返回零值结构 + 空趋势, 不报错。"""
        s = client._sesh
        ent = _enterprise(s, "空车队", "FCS002")
        v = _vehicle(s, ent.id, "京A22222", "LSVAU2189N2000022")
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"] == {
            "total_orders": 0, "total_kwh": 0.0, "total_amount": 0.0,
            "avg_kwh_per_order": 0.0, "avg_amount_per_order": 0.0,
        }
        assert d["monthly_trend"] == []

    def test_monthly_trend_multi_months(self, client):
        """(c) _build_monthly_trend: 跨月订单按 year-month 分组升序, 字段正确。

        造数动态取 now 所在月的上两月/上一月 (卡 7b7a7444): 趋势窗口下界为
        now-365d, 硬编码 2026-06/07 会随时间滑出窗口致 len(trend) 由 2 变 1。
        """
        s = client._sesh
        ent = _enterprise(s, "趋势车队", "FCS003")
        v = _vehicle(s, ent.id, "京A33333", "LSVAU2189N2000033")
        sta = _station(s, "趋势站", "ST003")
        now = datetime.now(timezone.utc)
        m_prev = _recent_month(now, 1)   # 上一月
        m_prev2 = _recent_month(now, 2)  # 上上月
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("30"), amount=Decimal("45"), start=m_prev2)
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=m_prev)
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        trend = r.json()["data"]["monthly_trend"]
        assert len(trend) == 2
        assert trend[0]["month"] == m_prev2.strftime("%Y-%m")   # 升序
        assert trend[0]["charged_kwh"] == 30.0
        assert trend[0]["total_amount"] == 45.0
        assert trend[1]["month"] == m_prev.strftime("%Y-%m")
        assert trend[1]["charged_kwh"] == 50.0

    def test_trend_excludes_beyond_12_months(self, client):
        """(c) 趋势仅近12月: >365天订单不计入趋势, 但累计 summary 仍含。"""
        s = client._sesh
        ent = _enterprise(s, "窗口车队", "FCS004")
        v = _vehicle(s, ent.id, "京A44444", "LSVAU2189N2000044")
        sta = _station(s, "窗口站", "ST004")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("999"), amount=Decimal("999"), start=_OLD)  # 窗口外
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 1            # 累计含
        assert d["summary"]["total_kwh"] == 999.0
        assert d["monthly_trend"] == []                     # 趋势不含

    def test_start_date_filter(self, client):
        """(d) start_date 过滤: 早于 start 的订单不计入。"""
        s = client._sesh
        ent = _enterprise(s, "日期车队", "FCS005")
        v = _vehicle(s, ent.id, "京A55555", "LSVAU2189N2000055")
        sta = _station(s, "日期站", "ST005")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)   # 7月, 区间内
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("999"), amount=Decimal("999"), start=_OLD)  # 去年, 区间外
        s.commit()

        r = client.get(
            VEH_URL.format(eid=ent.id, vid=v.id),
            params={"start_date": "2026-01-01"},
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 1
        assert d["summary"]["total_kwh"] == 50.0

    def test_end_date_filter_half_open(self, client):
        """(d) end_date 半开区间 [.., end+1day): end 当天包含, 次日排除。"""
        s = client._sesh
        ent = _enterprise(s, "end车队", "FCS006")
        v = _vehicle(s, ent.id, "京A66666", "LSVAU2189N2000066")
        sta = _station(s, "end站", "ST006")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("10"), start=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc))   # 区间内
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("20"), start=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc))  # =end 当天, 包含
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("30"), start=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc))  # 次日, 排除
        s.commit()

        r = client.get(
            VEH_URL.format(eid=ent.id, vid=v.id),
            params={"end_date": "2026-08-10"},
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 2            # 10 + 20
        assert d["summary"]["total_kwh"] == 30.0

    def test_bad_start_date_format_400(self, client):
        """(d) start_date 非法格式 → 400, detail 提示格式。"""
        s = client._sesh
        ent = _enterprise(s, "格式车队", "FCS007")
        v = _vehicle(s, ent.id, "京A77777", "LSVAU2189N2000077")
        s.commit()

        r = client.get(
            VEH_URL.format(eid=ent.id, vid=v.id),
            params={"start_date": "2026/08/01"},
        )
        assert r.status_code == 400
        assert "YYYY-MM-DD" in r.json()["detail"]

    def test_bad_end_date_format_400(self, client):
        """(d) end_date 非法格式 → 400。"""
        s = client._sesh
        ent = _enterprise(s, "格式车队2", "FCS008")
        v = _vehicle(s, ent.id, "京A88888", "LSVAU2189N2000088")
        s.commit()

        r = client.get(
            VEH_URL.format(eid=ent.id, vid=v.id),
            params={"end_date": "not-a-date"},
        )
        assert r.status_code == 400
        assert "YYYY-MM-DD" in r.json()["detail"]

    def test_plate_number_match_path(self, client):
        """(g) or_ 分支: 订单 vehicle_id=None, 靠 plate_number 命中车辆。"""
        s = client._sesh
        ent = _enterprise(s, "车牌车队", "FCS009")
        v = _vehicle(s, ent.id, "京A99999", "LSVAU2189N2000099")
        sta = _station(s, "车牌站", "ST009")
        # 仅车牌关联, vehicle_id 为 None —— 若 or_ 缺 plate 分支则漏单
        _order(s, vehicle_id=None, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("40"), amount=Decimal("60"))
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 1
        assert d["summary"]["total_kwh"] == 40.0

    def test_only_completed_orders_counted(self, client):
        """(h) order_status 过滤: 仅 COMPLETED 计入, CANCELLED 排除。"""
        s = client._sesh
        ent = _enterprise(s, "状态车队", "FCS010")
        v = _vehicle(s, ent.id, "京B11111", "LSVAU2189N2000101")
        sta = _station(s, "状态站", "ST010")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), order_status=OrderStatus.COMPLETED)
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("999"), amount=Decimal("999"), order_status=OrderStatus.CANCELLED)
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 1
        assert d["summary"]["total_kwh"] == 50.0

    def test_vehicle_not_found_404(self, client):
        """(i) 车辆不存在 → 404。"""
        s = client._sesh
        ent = _enterprise(s, "无车车队", "FCS011")
        s.commit()

        r = client.get(VEH_URL.format(eid=ent.id, vid=99999))
        assert r.status_code == 404
        assert r.json()["detail"] == "车辆不存在"

    def test_vehicle_cross_enterprise_404(self, client):
        """(i) 车辆存在但不属于该 enterprise (eid+vid 联合校验) → 404。"""
        s = client._sesh
        ent1 = _enterprise(s, "甲车队", "FCS012")
        ent2 = _enterprise(s, "乙车队", "FCS013")
        v1 = _vehicle(s, ent1.id, "京B22222", "LSVAU2189N2000121")
        s.commit()

        # v1 属 ent1, 用 ent2 的 id 查 → 404
        r = client.get(VEH_URL.format(eid=ent2.id, vid=v1.id))
        assert r.status_code == 404
        assert r.json()["detail"] == "车辆不存在"


# ════════════════════════ 车队级汇总 ════════════════════════


class TestEnterpriseChargingStats:
    """GET /enterprises/{eid}/charging-stats"""

    def test_aggregation_ranking_distribution(self, client):
        """(b) 汇总 + Top N 排行 + 场站分布 全部正确。"""
        s = client._sesh
        ent = _enterprise(s, "汇总车队", "FCS101")
        v1 = _vehicle(s, ent.id, "京C11111", "LSVAU2189N2000201")
        v2 = _vehicle(s, ent.id, "京C22222", "LSVAU2189N2000202")
        sta = _station(s, "汇总站", "ST101")
        _order(s, vehicle_id=v1.id, plate_number=v1.plate_number, station_id=sta.id,
               kwh=Decimal("100"), amount=Decimal("150"), start=_JUL)
        _order(s, vehicle_id=v1.id, plate_number=v1.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("75"), start=_JUN)
        _order(s, vehicle_id=v2.id, plate_number=v2.plate_number, station_id=sta.id,
               kwh=Decimal("80"), amount=Decimal("120"), start=_JUL)
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        # 汇总
        assert d["summary"]["total_orders"] == 3
        assert d["summary"]["total_kwh"] == 230.0
        assert d["summary"]["total_amount"] == 345.0
        assert d["active_vehicles"] == 2
        # 排行: v1(150) > v2(80), 降序
        assert len(d["top_vehicles"]) == 2
        assert d["top_vehicles"][0]["vehicle_id"] == v1.id
        assert d["top_vehicles"][0]["charged_kwh"] == 150.0
        assert d["top_vehicles"][0]["total_amount"] == 225.0
        assert d["top_vehicles"][1]["vehicle_id"] == v2.id
        assert d["top_vehicles"][1]["charged_kwh"] == 80.0
        # 场站分布
        assert len(d["station_distribution"]) == 1
        assert d["station_distribution"][0]["station_id"] == sta.id
        assert d["station_distribution"][0]["station_name"] == "汇总站"
        assert d["station_distribution"][0]["charged_kwh"] == 230.0
        assert d["station_distribution"][0]["order_count"] == 3

    def test_empty_zero_structure(self, client):
        """(b) 企业有车辆但无订单 → 零值汇总 + 空排行/分布。"""
        s = client._sesh
        ent = _enterprise(s, "零单车队", "FCS102")
        _vehicle(s, ent.id, "京C33333", "LSVAU2189N2000301")
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 0
        assert d["summary"]["total_kwh"] == 0.0
        assert d["active_vehicles"] == 0
        assert d["top_vehicles"] == []
        assert d["station_distribution"] == []

    def test_no_vehicles_zero_structure(self, client):
        """(i) 企业无任何车辆 → 早返回零值结构 (不进入订单聚合)。"""
        s = client._sesh
        ent = _enterprise(s, "空企业", "FCS103")
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 0
        assert d["active_vehicles"] == 0
        assert d["top_vehicles"] == []
        assert d["station_distribution"] == []

    def test_top_n_custom(self, client):
        """(b) top_n 自定义: 多辆车仅返回前 N (按电量降序)。"""
        s = client._sesh
        ent = _enterprise(s, "topn车队", "FCS104")
        sta = _station(s, "topn站", "ST104")
        plates_vins = [
            ("京D11111", "LSVAU2189N2000401", Decimal("100")),
            ("京D22222", "LSVAU2189N2000402", Decimal("80")),
            ("京D33333", "LSVAU2189N2000403", Decimal("60")),
        ]
        for plate, vin, kwh in plates_vins:
            v = _vehicle(s, ent.id, plate, vin)
            _order(s, vehicle_id=v.id, plate_number=plate, station_id=sta.id,
                   kwh=kwh, amount=kwh, start=_JUL)
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id), params={"top_n": 2})
        assert r.status_code == 200, r.text
        top = r.json()["data"]["top_vehicles"]
        assert len(top) == 2
        assert top[0]["charged_kwh"] == 100.0
        assert top[1]["charged_kwh"] == 80.0

    def test_top_n_out_of_range_422(self, client):
        """(i) top_n 越界 (<1 或 >50) → 422 (Query(ge=1, le=50))。"""
        s = client._sesh
        ent = _enterprise(s, "越界车队", "FCS105")
        s.commit()

        r_lo = client.get(ENT_URL.format(eid=ent.id), params={"top_n": 0})
        assert r_lo.status_code == 422
        r_hi = client.get(ENT_URL.format(eid=ent.id), params={"top_n": 51})
        assert r_hi.status_code == 422

    def test_ranking_sorted_desc(self, client):
        """(b) 排行严格按 charged_kwh 降序。"""
        s = client._sesh
        ent = _enterprise(s, "排行车队", "FCS106")
        sta = _station(s, "排行站", "ST106")
        # 故意以升序造数据, 验证端点降序输出
        for i, kwh in enumerate([Decimal("30"), Decimal("90"), Decimal("60")]):
            v = _vehicle(s, ent.id, f"京E{i}0001", f"LSVAU2189N2000{i:03d}01")
            _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
                   kwh=kwh, amount=kwh, start=_JUL)
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200
        kwhs = [row["charged_kwh"] for row in r.json()["data"]["top_vehicles"]]
        assert kwhs == sorted(kwhs, reverse=True)
        assert kwhs[0] == 90.0

    def test_station_unknown_fallback_name(self, client):
        """(i) 订单 station_id 在 Station 表不存在 → 场站名 fallback 为 "场站{sid}"。"""
        s = client._sesh
        ent = _enterprise(s, "fallback车队", "FCS107")
        v = _vehicle(s, ent.id, "京F11111", "LSVAU2189N2000501")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number,
               station_id=88888, kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200, r.text
        dist = r.json()["data"]["station_distribution"]
        assert len(dist) == 1
        assert dist[0]["station_id"] == 88888
        assert dist[0]["station_name"] == "场站88888"

    def test_date_range_filter(self, client):
        """(d) 车队汇总日期范围: 区间外订单排除。"""
        s = client._sesh
        ent = _enterprise(s, "日界车队", "FCS108")
        v = _vehicle(s, ent.id, "京G11111", "LSVAU2189N2000601")
        sta = _station(s, "日界站", "ST108")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("100"), start=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc))
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("999"), start=_OLD)
        s.commit()

        r = client.get(
            ENT_URL.format(eid=ent.id),
            params={"start_date": "2026-08-01", "end_date": "2026-08-10"},
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["summary"]["total_orders"] == 1
        assert d["summary"]["total_kwh"] == 100.0

    def test_active_vehicles_plate_match(self, client):
        """(g) active_vehicles 计入靠 plate_number 匹配的车辆 (vehicle_id=None 订单)。"""
        s = client._sesh
        ent = _enterprise(s, "活跃车队", "FCS109")
        v = _vehicle(s, ent.id, "京H11111", "LSVAU2189N2000701")
        sta = _station(s, "活跃站", "ST109")
        # 订单 vehicle_id=None, 仅车牌关联 → active_vehicles 仍应识别为 1
        _order(s, vehicle_id=None, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)
        s.commit()

        r = client.get(ENT_URL.format(eid=ent.id))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["active_vehicles"] == 1
        assert len(d["top_vehicles"]) == 1
        assert d["top_vehicles"][0]["vehicle_id"] == v.id

    def test_enterprise_not_found_404(self, client):
        """(i) 企业不存在 → 404 (经 assert_enterprise_team_access)。"""
        r = client.get(ENT_URL.format(eid=99999))
        assert r.status_code == 404
        assert r.json()["detail"] == "企业不存在"


# ════════════════════════ team scoping + 权限门 ════════════════════════


class TestTeamScopingAndAuth:
    """第二层鉴权 (assert_enterprise_team_access) + 未登录权限门。

    跨团队访问一律 404 (不泄露资源存在), 与 deps._team_denied 语义一致 —— 非 403。
    """

    def test_cross_team_enterprise_404_and_admin_exempt(self, client):
        """(e) 团队级用户访问他队企业 → 404; admin 跨团队 → 200 (豁免)。"""
        s = client._sesh
        ent_mine = _enterprise(s, "本队企业", "FCS201", owner_team_id=1)
        ent_other = _enterprise(s, "他队企业", "FCS202", owner_team_id=2)
        _vehicle(s, ent_mine.id, "京I11111", "LSVAU2189N2000801")
        _vehicle(s, ent_other.id, "京I22222", "LSVAU2189N2000802")
        _make_team_user(client, team_id=1, username="viewer_t1")
        s.commit()

        # admin 视角: 两企业均可见
        assert client.get(ENT_URL.format(eid=ent_other.id)).status_code == 200

        # 切到 team1 viewer: 本队 200, 他队 404
        login_as(client, "viewer_t1", "v123456")
        assert client.get(ENT_URL.format(eid=ent_mine.id)).status_code == 200
        r = client.get(ENT_URL.format(eid=ent_other.id))
        assert r.status_code == 404
        assert r.json()["detail"] == "企业不存在"
        login_admin(client)  # 还原, 避免污染后续用例

    def test_cross_team_vehicle_stats_404(self, client):
        """(e) 团队级用户查他队企业的单车统计 → 404 (enterprise 校验先于 vehicle)。"""
        s = client._sesh
        ent_other = _enterprise(s, "他队企业2", "FCS203", owner_team_id=2)
        v_other = _vehicle(s, ent_other.id, "京J11111", "LSVAU2189N2000901")
        _make_team_user(client, team_id=1, username="viewer_t1b")
        s.commit()

        login_as(client, "viewer_t1b", "v123456")
        r = client.get(VEH_URL.format(eid=ent_other.id, vid=v_other.id))
        assert r.status_code == 404
        assert r.json()["detail"] == "企业不存在"
        login_admin(client)

    def test_team_viewer_own_enterprise_ok(self, client):
        """(e) 团队级用户访问本队企业的单车统计 → 200, 数据正确。"""
        s = client._sesh
        ent = _enterprise(s, "本队企业3", "FCS204", owner_team_id=1)
        v = _vehicle(s, ent.id, "京K11111", "LSVAU2189N2001001")
        sta = _station(s, "本队站", "ST201")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)
        _make_team_user(client, team_id=1, username="viewer_t1c")
        s.commit()

        login_as(client, "viewer_t1c", "v123456")
        r = client.get(VEH_URL.format(eid=ent.id, vid=v.id))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["summary"]["total_kwh"] == 50.0
        login_admin(client)

    def test_anon_unauth_vehicle_401(self, anon_client):
        """(f) 未登录访问单车统计 → 401。"""
        r = anon_client.get(VEH_URL.format(eid=1, vid=1))
        assert r.status_code == 401

    def test_anon_unauth_enterprise_401(self, anon_client):
        """(f) 未登录访问车队汇总 → 401。"""
        r = anon_client.get(ENT_URL.format(eid=1))
        assert r.status_code == 401


# ════════════════════════ 边界 ════════════════════════


class TestEdgeCases:
    """超大范围 / 跨企业隔离等边界。"""

    def test_huge_date_range_no_error(self, client):
        """(i) 超大日期范围 (近 50 年) 不报错, 正常聚合。"""
        s = client._sesh
        ent = _enterprise(s, "大范围车队", "FCS301")
        v = _vehicle(s, ent.id, "京L11111", "LSVAU2189N2001101")
        sta = _station(s, "大范围站", "ST301")
        _order(s, vehicle_id=v.id, plate_number=v.plate_number, station_id=sta.id,
               kwh=Decimal("50"), amount=Decimal("80"), start=_JUL)
        s.commit()

        r = client.get(
            VEH_URL.format(eid=ent.id, vid=v.id),
            params={"start_date": "1980-01-01", "end_date": "2099-12-31"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["summary"]["total_orders"] == 1


# ═════════════════════════════════════════════════════════════════
# 审计观察 (业务可疑点, 仅记录不私自修改 — 供大圣/文曲裁决):
#
# 1. [趋势窗口 vs 累计口径不一致] vehicle_charging_stats 的 summary 取全部 COMPLETED
#    订单(仅日期筛选), 而 monthly_trend 额外叠加 start_time >= now-365d 窗口。当用户
#    指定 start_date 早于 12 个月前时, 会出现 summary.total_orders 与趋势各月订单数
#    之和不相等(累计含旧单、趋势不含)。前端需知此口径差, 否则"趋势总和≠累计"易被
#    误判为 bug。本测试 test_trend_excludes_beyond_12_months 已锁定该行为。
#
# 2. [车队汇总 active_vehicles 复杂度] active_vehicles 计算(243-257行)与车辆排行
#    (261-291行)分别完整遍历订单两遍, 且车牌→vid 反查为 O(orders×vehicles) 嵌套循环。
#    车队订单量大时有 N×M 性能风险。功能正确性已由 test_active_vehicles_plate_match
#    覆盖, 性能仅作记录。
#
# 3. [单车/车队端点 owner_team_id 隔离依赖 enterprise] team scoping 经 enterprise.
#    owner_team_id, 但 ChargingOrder 本身无 team 列, 订单经 vehicle_id/plate 关联企业
#    后间接归属。若一条订单的 vehicle_id 指向企业A车辆、plate 却匹配企业B车辆(同车牌
#    跨企业), or_(vehicle_id IN, plate IN) 会把该订单同时计入两企业汇总。当前车牌跨
#    企业重复概率低, 作记录。
# ═════════════════════════════════════════════════════════════════

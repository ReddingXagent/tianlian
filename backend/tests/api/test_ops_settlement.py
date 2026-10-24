"""
运营结算对账 API 测试 (app/api/v1/operate/ops_settlement.py, SPEC §2.7)

覆盖 11 个端点, 前缀 /api/v1/operate/settlement:
  日结汇总:
    - GET  /settlement/daily                    列表(经 station→team 隔离)
    - GET  /settlement/daily/{id}               详情(station→team; NULL station 平台级仅 admin)
    - POST /settlement/daily/generate           生成(require_platform_admin)
    - PUT  /settlement/daily/{id}/confirm       确认(require_permission operate:manage; 状态机 PENDING→CONFIRMED)
  支付对账:
    - GET  /settlement/reconciliation           列表(require_platform_admin)
    - POST /settlement/reconciliation           创建(require_platform_admin)
    - PUT  /settlement/reconciliation/{id}/reconcile  对账(状态机 PENDING→RECONCILED)
  互联互通结算:
    - GET  /settlement/interconnect             列表(require_platform_admin)
    - POST /settlement/interconnect             创建(require_platform_admin; 分账比例 0~1 边界)
    - PUT  /settlement/interconnect/{id}/settle 结算(状态机 PENDING→SETTLED)
  企业结算:
    - GET  /settlement/enterprise               列表(经 enterprise→owner_team 隔离)

测试矩阵:
  ① happy path: 各端点正常创建/查询/状态流转, 数值序列化正确
  ② error path: 404(不存在) / 400(状态机冲突, 重复, 分账越界) / 403(非 admin 写端点) / 422(分页/必填)
  ③ team scoping: daily/enterprise 经 station→team / enterprise→owner_team 隔离; admin 豁免
  ④ 过滤 + 分页: start_date/end_date/station_id/status/payment_channel/platform_id; page 越界

风格同 test_supervision.py: client 默认 admin(平台级, team_id=None); team 级用例经
_add_user + _login_token 注入 ENGINEER token, 直接 seed ORM 到 client._sesh。

铁律: 仅加测试, 不改业务代码。发现的业务可疑点记录于模块 docstring 末尾。
"""
import bcrypt
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from app.models.ops_settlement import (
    DailySettlement, SettlementStatus,
    PaymentReconciliation, ReconciliationStatus,
    InterconnectSettlement, InterconnectSettlementStatus,
)
from app.models.settlement.bill import FleetSettlementBill, BillStatus
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole, Team

BASE = "/api/v1/operate/settlement"


# ─── seed helpers ───

def _add_user(session, username, role, team_id=None, password="pw123456"):
    """创建并提交用户, 返回 ORM (供 team scoping 用例复用)。"""
    u = User(
        username=username, real_name=username, role=role, team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json().get("data", {}).get("token") or r.json().get("token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _station(session, name, code, team_id=None):
    s = Station(name=name, code=code, address="测试地址",
                status=StationStatus.NORMAL, team_id=team_id)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def _seed_daily(session, settlement_date, station_id=None, status=SettlementStatus.PENDING,
                total_amount=Decimal("100"), total_paid=Decimal("100"), **overrides):
    """直接 seed 一条日结记录。"""
    ds = DailySettlement(
        settlement_date=settlement_date, station_id=station_id,
        total_orders=overrides.get("total_orders", 1),
        total_amount=total_amount, total_paid=total_paid,
        total_charge_fee=overrides.get("total_charge_fee", Decimal("60")),
        total_service_fee=overrides.get("total_service_fee", Decimal("40")),
        status=status, remark=overrides.get("remark"),
    )
    session.add(ds)
    session.commit()
    session.refresh(ds)
    return ds


def _seed_recon(session, settlement_date, payment_channel="im_b",
                status=ReconciliationStatus.PENDING, **overrides):
    r = PaymentReconciliation(
        settlement_date=settlement_date, payment_channel=payment_channel,
        platform_orders_count=overrides.get("platform_orders_count", 10),
        platform_amount=overrides.get("platform_amount", Decimal("100")),
        payment_orders_count=overrides.get("payment_orders_count", 10),
        payment_amount=overrides.get("payment_amount", Decimal("100")),
        difference_count=overrides.get("difference_count", 0),
        difference_amount=overrides.get("difference_amount", Decimal("0")),
        difference_detail=overrides.get("difference_detail"),
        status=status, remark=overrides.get("remark"),
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _seed_interconnect(session, platform_id="MA1", status=InterconnectSettlementStatus.PENDING, **overrides):
    s = InterconnectSettlement(
        platform_id=platform_id, platform_name=overrides.get("platform_name"),
        start_date=overrides.get("start_date", date(2026, 8, 1)),
        end_date=overrides.get("end_date", date(2026, 8, 7)),
        total_orders=overrides.get("total_orders", 5),
        total_amount=overrides.get("total_amount", Decimal("1000")),
        revenue_share_ratio=overrides.get("revenue_share_ratio", Decimal("0.7")),
        our_revenue=overrides.get("our_revenue", Decimal("700")),
        partner_revenue=overrides.get("partner_revenue", Decimal("300")),
        settlement_amount=overrides.get("settlement_amount", Decimal("700")),
        status=status, remark=overrides.get("remark"),
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def _seed_enterprise(session, name, code, owner_team_id=None):
    e = Enterprise(name=name, code=code, owner_team_id=owner_team_id,
                   status=EnterpriseStatus.ACTIVE)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


def _seed_bill(session, enterprise_id, bill_no, bill_period="2026-08",
               total_amount=Decimal("500"), status=BillStatus.PENDING):
    b = FleetSettlementBill(
        enterprise_id=enterprise_id, bill_no=bill_no, bill_period=bill_period,
        total_amount=total_amount, paid_amount=Decimal("0"), balance_amount=total_amount,
        status=status,
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


# ==================== 日结汇总 ====================

class TestDailySettlementList:
    """GET /settlement/daily"""

    def test_list_admin_sees_all(self, client):
        """(a) admin 见全部日结(含 NULL station 平台级)。"""
        sta = _station(client._sesh, "日结站", "DS001", team_id=None)
        _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id)
        _seed_daily(client._sesh, date(2026, 8, 5), station_id=None)  # 平台级
        r = client.get(f"{BASE}/daily")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["total"] == 2
        assert len(d["items"]) == 2

    def test_list_empty(self, client):
        """(d) 空数据返回空列表。"""
        r = client.get(f"{BASE}/daily")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0
        assert r.json()["data"]["items"] == []

    def test_list_filter_by_date_range(self, client):
        """过滤: [start_date, end_date] 闭区间(源码用 <=)。"""
        sta = _station(client._sesh, "日结站F", "DSF01", team_id=None)
        _seed_daily(client._sesh, date(2026, 8, 1), station_id=sta.id)
        _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id)
        _seed_daily(client._sesh, date(2026, 8, 15), station_id=sta.id)
        r = client.get(f"{BASE}/daily?start_date=2026-08-01&end_date=2026-08-10")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 2  # 8/1 + 8/5

    def test_list_filter_by_station_and_status(self, client):
        sta = _station(client._sesh, "日结站S", "DSS01", team_id=None)
        _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id, status=SettlementStatus.PENDING)
        _seed_daily(client._sesh, date(2026, 8, 6), station_id=sta.id, status=SettlementStatus.CONFIRMED)
        r = client.get(f"{BASE}/daily?station_id={sta.id}&status=pending")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "pending"

    def test_list_pagination(self, client):
        sta = _station(client._sesh, "日结页", "DSP01", team_id=None)
        for i in range(5):
            _seed_daily(client._sesh, date(2026, 8, i + 1), station_id=sta.id)
        r = client.get(f"{BASE}/daily?page=1&page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 5
        assert len(d["items"]) == 2

    def test_list_invalid_pagination_422(self, client):
        r = client.get(f"{BASE}/daily?page=0")
        assert r.status_code == 422

    def test_list_team_scoped_excludes_other_team(self, client):
        """(③) 非 admin 经 station→team 过滤, 仅本 team 站点日结; NULL station 平台级不含。"""
        s = client._sesh
        ta = Team(name="结算队A", code="STTA")
        tb = Team(name="结算队B", code="STTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)
        sa = _station(s, "A站", "DST_A", team_id=ta.id)
        sb = _station(s, "B站", "DST_B", team_id=tb.id)
        _seed_daily(s, date(2026, 8, 5), station_id=sa.id, total_amount=Decimal("100"))
        _seed_daily(s, date(2026, 8, 5), station_id=sb.id, total_amount=Decimal("999"))
        _seed_daily(s, date(2026, 8, 5), station_id=None)  # 平台级, team 用户不可见
        eng_a = _add_user(s, "set_eng_a", UserRole.ENGINEER, team_id=ta.id)

        r = client.get(f"{BASE}/daily", headers=_auth(_login_token(client, "set_eng_a")))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["station_id"] == sa.id
        assert items[0]["total_amount"] == 100.0


class TestDailySettlementDetail:
    """GET /settlement/daily/{id}"""

    def test_detail_ok(self, client):
        sta = _station(client._sesh, "详情站", "DSD01", team_id=None)
        ds = _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id)
        r = client.get(f"{BASE}/daily/{ds.id}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == ds.id
        assert r.json()["data"]["settlement_date"] == "2026-08-05"

    def test_detail_not_found_404(self, client):
        r = client.get(f"{BASE}/daily/999999")
        assert r.status_code == 404

    def test_detail_platform_level_admin_ok(self, client):
        """NULL station 平台级日结: admin 可见。"""
        ds = _seed_daily(client._sesh, date(2026, 8, 5), station_id=None)
        r = client.get(f"{BASE}/daily/{ds.id}")
        assert r.status_code == 200

    def test_detail_platform_level_team_user_404(self, client):
        """NULL station 平台级日结: 非 admin 视为不存在 → 404。"""
        s = client._sesh
        ta = Team(name="详情队", code="DSTT")
        s.add(ta)
        s.commit()
        s.refresh(ta)
        ds = _seed_daily(s, date(2026, 8, 5), station_id=None)
        _add_user(s, "detail_eng", UserRole.ENGINEER, team_id=ta.id)
        r = client.get(f"{BASE}/daily/{ds.id}", headers=_auth(_login_token(client, "detail_eng")))
        assert r.status_code == 404

    def test_detail_cross_team_404(self, client):
        """跨 team 站点的日结: assert_station_team_access → 404(不泄露存在)。"""
        s = client._sesh
        ta = Team(name="跨队A", code="CSTA")
        tb = Team(name="跨队B", code="CSTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)
        sb = _station(s, "他队站", "CST_B", team_id=tb.id)
        ds = _seed_daily(s, date(2026, 8, 5), station_id=sb.id)
        _add_user(s, "cross_eng_a", UserRole.ENGINEER, team_id=ta.id)
        r = client.get(f"{BASE}/daily/{ds.id}", headers=_auth(_login_token(client, "cross_eng_a")))
        assert r.status_code == 404


class TestDailySettlementGenerate:
    """POST /settlement/daily/generate (require_platform_admin)"""

    def test_generate_admin_ok(self, client):
        r = client.post(f"{BASE}/daily/generate", json={
            "settlement_date": "2026-08-05", "total_orders": 3,
            "total_amount": "150.00", "total_paid": "150.00",
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["settlement_date"] == "2026-08-05"
        assert d["status"] == "pending"
        assert d["total_orders"] == 3

    def test_generate_duplicate_400(self, client):
        """同日期+站点重复生成 → 400。"""
        body = {"settlement_date": "2026-08-06", "total_amount": "100.00"}
        assert client.post(f"{BASE}/daily/generate", json=body).status_code == 200
        r = client.post(f"{BASE}/daily/generate", json=body)
        assert r.status_code == 400
        assert "已存在" in r.json()["detail"]

    def test_generate_duplicate_platform_level_400(self, client):
        """同日期 NULL station 平台级重复 → 400。"""
        body = {"settlement_date": "2026-08-07"}
        assert client.post(f"{BASE}/daily/generate", json=body).status_code == 200
        assert client.post(f"{BASE}/daily/generate", json=body).status_code == 400

    def test_generate_viewer_forbidden_403(self, client):
        """(②) 非 admin → require_platform_admin → 403。"""
        _add_user(client._sesh, "gen_viewer", UserRole.VIEWER)
        r = client.post(f"{BASE}/daily/generate",
                        json={"settlement_date": "2026-08-05"},
                        headers=_auth(_login_token(client, "gen_viewer")))
        assert r.status_code == 403

    def test_generate_missing_date_422(self, client):
        r = client.post(f"{BASE}/daily/generate", json={})
        assert r.status_code == 422


class TestDailySettlementConfirm:
    """PUT /settlement/daily/{id}/confirm (require_permission operate:manage)"""

    def test_confirm_pending_to_confirmed(self, client):
        sta = _station(client._sesh, "确认站", "DCF01", team_id=None)
        ds = _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id,
                         status=SettlementStatus.PENDING)
        r = client.put(f"{BASE}/daily/{ds.id}/confirm")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "confirmed"
        assert r.json()["data"]["confirmed_at"] is not None

    def test_confirm_already_confirmed_400(self, client):
        """状态机: 非 PENDING → 400。"""
        sta = _station(client._sesh, "重复确认站", "DCF02", team_id=None)
        ds = _seed_daily(client._sesh, date(2026, 8, 5), station_id=sta.id,
                         status=SettlementStatus.CONFIRMED)
        r = client.put(f"{BASE}/daily/{ds.id}/confirm")
        assert r.status_code == 400

    def test_confirm_not_found_404(self, client):
        r = client.put(f"{BASE}/daily/999999/confirm")
        assert r.status_code == 404

    def test_confirm_cross_team_404(self, client):
        """(③) 跨 team 站点日结: team 用户确认 → 404。"""
        s = client._sesh
        ta = Team(name="确认队A", code="CFTA")
        tb = Team(name="确认队B", code="CFTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)
        sb = _station(s, "他队确认站", "CFT_B", team_id=tb.id)
        ds = _seed_daily(s, date(2026, 8, 5), station_id=sb.id)
        _add_user(s, "conf_eng_a", UserRole.ENGINEER, team_id=ta.id)
        r = client.put(f"{BASE}/daily/{ds.id}/confirm",
                       headers=_auth(_login_token(client, "conf_eng_a")))
        assert r.status_code == 404


# ==================== 支付对账 ====================

class TestReconciliation:
    """GET/POST /settlement/reconciliation, PUT .../reconcile (均 require_platform_admin)"""

    def test_list_admin_ok(self, client):
        _seed_recon(client._sesh, date(2026, 8, 5))
        r = client.get(f"{BASE}/reconciliation")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_list_empty(self, client):
        r = client.get(f"{BASE}/reconciliation")
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []

    def test_list_filter_by_channel(self, client):
        _seed_recon(client._sesh, date(2026, 8, 5), payment_channel="im_b")
        _seed_recon(client._sesh, date(2026, 8, 5), payment_channel="alipay")
        r = client.get(f"{BASE}/reconciliation?payment_channel=im_b")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["payment_channel"] == "im_b"

    def test_create_admin_ok(self, client):
        r = client.post(f"{BASE}/reconciliation", json={
            "settlement_date": "2026-08-05", "payment_channel": "im_b",
            "platform_orders_count": 10, "platform_amount": "1000.00",
            "payment_orders_count": 9, "payment_amount": "950.00",
            "difference_count": 1, "difference_amount": "50.00",
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "pending"
        assert d["platform_amount"] == 1000.0
        assert d["difference_amount"] == 50.0

    def test_create_viewer_forbidden_403(self, client):
        """(②) 非 admin → 403。"""
        _add_user(client._sesh, "rec_viewer", UserRole.VIEWER)
        r = client.post(f"{BASE}/reconciliation",
                        json={"settlement_date": "2026-08-05", "payment_channel": "im_b"},
                        headers=_auth(_login_token(client, "rec_viewer")))
        assert r.status_code == 403

    def test_list_viewer_forbidden_403(self, client):
        """(②) 列表同样 require_platform_admin → 非 admin 403。"""
        _add_user(client._sesh, "rec_list_viewer", UserRole.VIEWER)
        r = client.get(f"{BASE}/reconciliation",
                       headers=_auth(_login_token(client, "rec_list_viewer")))
        assert r.status_code == 403

    def test_create_missing_required_422(self, client):
        r = client.post(f"{BASE}/reconciliation", json={"settlement_date": "2026-08-05"})
        assert r.status_code == 422  # payment_channel 必填


class TestReconcile:
    """PUT /settlement/reconciliation/{id}/reconcile"""

    def test_reconcile_pending_to_reconciled(self, client):
        rec = _seed_recon(client._sesh, date(2026, 8, 5), status=ReconciliationStatus.PENDING)
        r = client.put(f"{BASE}/reconciliation/{rec.id}/reconcile",
                       json={"operator": "审计员", "difference_detail": "已平账"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "reconciled"
        assert d["reconciled_by"] == "审计员"
        assert d["difference_detail"] == "已平账"
        assert d["reconciled_at"] is not None

    def test_reconcile_already_reconciled_400(self, client):
        rec = _seed_recon(client._sesh, date(2026, 8, 5), status=ReconciliationStatus.RECONCILED)
        r = client.put(f"{BASE}/reconciliation/{rec.id}/reconcile", json={})
        assert r.status_code == 400

    def test_reconcile_not_found_404(self, client):
        r = client.put(f"{BASE}/reconciliation/999999/reconcile", json={})
        assert r.status_code == 404


# ==================== 互联互通结算 ====================

class TestInterconnectList:
    """GET /settlement/interconnect (require_platform_admin)"""

    def test_list_admin_ok(self, client):
        _seed_interconnect(client._sesh, platform_id="MA1")
        _seed_interconnect(client._sesh, platform_id="MA2")
        r = client.get(f"{BASE}/interconnect")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_list_filter_by_platform(self, client):
        _seed_interconnect(client._sesh, platform_id="MA1")
        _seed_interconnect(client._sesh, platform_id="MA2")
        r = client.get(f"{BASE}/interconnect?platform_id=MA1")
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["platform_id"] == "MA1"

    def test_list_viewer_forbidden_403(self, client):
        _add_user(client._sesh, "ic_viewer", UserRole.VIEWER)
        r = client.get(f"{BASE}/interconnect",
                       headers=_auth(_login_token(client, "ic_viewer")))
        assert r.status_code == 403


class TestInterconnectCreate:
    """POST /settlement/interconnect (require_platform_admin; 分账比例边界)"""

    def test_create_admin_ok_revenue_split(self, client):
        """(a) 创建: our_rev = total * ratio, partner = total - our, settlement = our。"""
        r = client.post(f"{BASE}/interconnect", json={
            "platform_id": "MA1", "platform_name": "云快充",
            "start_date": "2026-08-01", "end_date": "2026-08-07",
            "total_orders": 10, "total_amount": "1000.00", "revenue_share_ratio": "0.7",
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "pending"
        assert d["our_revenue"] == 700.0
        assert d["partner_revenue"] == 300.0
        assert d["settlement_amount"] == 700.0

    @pytest.mark.parametrize("ratio", ["1.5", "-0.1"])
    def test_create_invalid_ratio_400(self, client, ratio):
        """(②) 分账比例越界(>1 / 负数) → 400(资金安全)。"""
        r = client.post(f"{BASE}/interconnect", json={
            "platform_id": "MA1", "start_date": "2026-08-01", "end_date": "2026-08-07",
            "total_amount": "1000.00", "revenue_share_ratio": ratio,
        })
        assert r.status_code == 400
        assert "0~1" in r.json()["detail"]

    def test_create_boundary_ratio_zero_and_one_ok(self, client):
        """边界 0 与 1 均合法(闭区间)。"""
        for ratio in ["0", "1"]:
            r = client.post(f"{BASE}/interconnect", json={
                "platform_id": f"BND{ratio}", "start_date": "2026-08-01",
                "end_date": "2026-08-07", "total_amount": "1000.00",
                "revenue_share_ratio": ratio,
            })
            assert r.status_code == 200, f"ratio={ratio} 应放行: {r.text}"

    def test_create_viewer_forbidden_403(self, client):
        _add_user(client._sesh, "ic_create_viewer", UserRole.VIEWER)
        r = client.post(f"{BASE}/interconnect",
                        json={"platform_id": "MA1", "start_date": "2026-08-01",
                              "end_date": "2026-08-07"},
                        headers=_auth(_login_token(client, "ic_create_viewer")))
        assert r.status_code == 403

    def test_create_missing_required_422(self, client):
        r = client.post(f"{BASE}/interconnect", json={"start_date": "2026-08-01"})
        assert r.status_code == 422  # platform_id / end_date 必填


class TestInterconnectSettle:
    """PUT /settlement/interconnect/{id}/settle"""

    def test_settle_pending_to_settled(self, client):
        ic = _seed_interconnect(client._sesh, status=InterconnectSettlementStatus.PENDING)
        r = client.put(f"{BASE}/interconnect/{ic.id}/settle", json={"operator": "财务"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "settled"
        assert d["settled_by"] == "财务"
        assert d["settled_at"] is not None

    def test_settle_already_settled_400(self, client):
        ic = _seed_interconnect(client._sesh, status=InterconnectSettlementStatus.SETTLED)
        r = client.put(f"{BASE}/interconnect/{ic.id}/settle", json={})
        assert r.status_code == 400

    def test_settle_not_found_404(self, client):
        r = client.put(f"{BASE}/interconnect/999999/settle", json={})
        assert r.status_code == 404


# ==================== 企业结算 ====================

class TestEnterpriseSettlement:
    """GET /settlement/enterprise (经 enterprise→owner_team 隔离)"""

    def test_list_admin_sees_all(self, client):
        ea = _seed_enterprise(client._sesh, "企业A", "EPSA")
        eb = _seed_enterprise(client._sesh, "企业B", "EPSB")
        _seed_bill(client._sesh, ea.id, "BILL-A1")
        _seed_bill(client._sesh, eb.id, "BILL-B1")
        r = client.get(f"{BASE}/enterprise")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_list_empty(self, client):
        r = client.get(f"{BASE}/enterprise")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_list_team_scoped(self, client):
        """(③) 非 admin 经 enterprise→owner_team 过滤, 仅本 team 企业账单。"""
        s = client._sesh
        ta = Team(name="企业队A", code="ESTA")
        tb = Team(name="企业队B", code="ESTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)
        ea = _seed_enterprise(s, "本队企业", "EPS_A", owner_team_id=ta.id)
        eb = _seed_enterprise(s, "他队企业", "EPS_B", owner_team_id=tb.id)
        _seed_bill(s, ea.id, "BILL-TA")
        _seed_bill(s, eb.id, "BILL-TB")
        _add_user(s, "ent_eng_a", UserRole.ENGINEER, team_id=ta.id)

        r = client.get(f"{BASE}/enterprise", headers=_auth(_login_token(client, "ent_eng_a")))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["enterprise_id"] == ea.id

    def test_list_pagination(self, client):
        """分页: 注意 (enterprise_id, bill_period) 唯一约束, 每条用不同账期。"""
        e = _seed_enterprise(client._sesh, "分页企业", "EPPG")
        for i in range(5):
            _seed_bill(client._sesh, e.id, f"BILL-P{i}", bill_period=f"2026-{i + 1:02d}")
        r = client.get(f"{BASE}/enterprise?page=1&page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 5
        assert len(d["items"]) == 2


# ═══════════════════════════════════════════════════════════════════
# 审计观察 (业务可疑点, 仅记录不私自修改 — 供大圣/文曲裁决):
#
# 1. [daily/generate 重复判定] existing 查询用 `station_id == station_id if station_id else
#    station_id.is_(None)`。当 station_id=None 时, 表达式退化为 `DailySettlement.station_id
#    == None` (Python 三元的 else 分支未触发), 该条件在 SQLAlchemy 经典版下被翻译为 IS NULL,
#    行为正确; 但写法依赖三元短路语义, 可读性差, 建议显式 `is_(None)`。
#
# 2. [reconciliation/interconnect 无 team scoping] 这两类端点全量 require_platform_admin,
#    非 admin 直接 403, 故无 team 隔离需求。daily/enterprise 有 team scoping 已覆盖。
#
# 3. [enterprise 唯一约束] FleetSettlementBill 在 (enterprise_id, bill_period) 上有
#    UniqueConstraint, 同企业同账期仅一条; 测试 seed 多条须用不同 bill_period。
# ═══════════════════════════════════════════════════════════════════

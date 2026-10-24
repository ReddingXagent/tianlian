"""光储充能量策略 REST API 测试 (工作卡 a6f3b8db 修正版)

覆盖 app/api/v1/energy_strategy.py (挂 /api/v1/energy-strategy 前缀, 599 行, 原零测试):
- A 策略配置: GET /strategies, GET/PUT /strategies/{station_id}
- B 模板管理: GET/POST /price-templates, GET /price-templates/by-province/{province},
              PUT /price-templates/{id}
- C 调度计划: GET /plans/current, GET /plans/{station_id}
- D 能量流水: GET /flow, GET /savings

权限: router 级 get_current_user (无 token → 401); 写端点叠加
      require_permission("energy:*:edit") —— 该权限点尚未进入 ROLE_PERMISSIONS_MATRIX
      (energy_strategy.py 模块 docstring 明示「矩阵补齐后自动生效」), 故:
        - admin/super_admin 直通 (permission.py:86 admin 分支) → 写端点可用
        - viewer/engineer/operator 无此权限 → 写端点 403
团队隔离: 列表/详情按 user.team_id 过滤, 跨团队资源 404 (不暴露存在性)。
"""
import uuid
from datetime import datetime, timezone

import bcrypt
import pytest

from app.models.energy_strategy import (
    EnergyDispatchPlan,
    EnergyFlowLog,
    EnergyPricePeriod,
    EnergyPriceTemplate,
    StationEnergyStrategy,
)
from app.models.pricing_v2 import PeriodType
from app.models.station import Station, StationStatus
from app.models.user import Team, User, UserRole

BASE = "/api/v1/energy-strategy"


# ─── helpers ───

def _add_user(session, username, *, role=UserRole.VIEWER, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_team(session, tag=""):
    t = Team(name=f"能源团队{tag}{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4].upper()}")
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def _seed_station(session, *, team_id=None, tag=""):
    st = Station(
        name=f"能源站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ES{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_strategy(session, *, station_id, team_id, is_active=True, scenario="fleet"):
    o = StationEnergyStrategy(
        station_id=station_id, team_id=team_id, scenario_preset=scenario, is_active=is_active,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _seed_template(session, *, province="北京市", version=1, team_id=None, active=True,
                   effective_from="2026-01-01", effective_until=None):
    from datetime import date
    tpl = EnergyPriceTemplate(
        province=province, version=version,
        effective_from=date.fromisoformat(effective_from),
        effective_until=date.fromisoformat(effective_until) if effective_until else None,
        is_active=active, team_id=team_id,
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    # 时段明细
    session.add(EnergyPricePeriod(
        template_id=tpl.id, period_type=PeriodType.PEAK,
        start_time=__import__("datetime").time(10, 0), end_time=__import__("datetime").time(12, 0),
        purchase_price=1.0,
    ))
    session.commit()
    return tpl


@pytest.fixture
def viewer_ctx(client):
    """团队级 VIEWER 上下文: 团队 + 用户 + 站点 + 策略, 用于团队隔离与只读断言。"""
    h = uuid.uuid4().hex[:6]
    s = client._sesh
    team = _seed_team(s, tag=h)
    st = _seed_station(s, team_id=team.id, tag=h)
    strat = _seed_strategy(s, station_id=st.id, team_id=team.id)
    u = _add_user(s, f"es_viewer_{h}", role=UserRole.VIEWER, team_id=team.id)
    return {
        "s": s, "team": team, "st": st, "strat": strat, "u": u, "h": h,
        "token": _login_token(client, f"es_viewer_{h}"),
    }


@pytest.fixture
def other_team_strategy(client, viewer_ctx):
    """另一团队的站点+策略, 用于断言跨团队隔离。"""
    s = viewer_ctx["s"]
    team2 = _seed_team(s, tag="other" + viewer_ctx["h"])
    st2 = _seed_station(s, team_id=team2.id, tag="other")
    strat2 = _seed_strategy(s, station_id=st2.id, team_id=team2.id, scenario="public_fast")
    return {"team": team2, "st": st2, "strat": strat2}


# ==================== A. 策略配置 ====================

class TestStrategy:
    """A 段: 策略列表 / 详情 / 更新 (含团队隔离与权限)。"""

    def test_list_admin_sees_all(self, client, viewer_ctx, other_team_strategy):
        """admin 不受 team_id 过滤 → 两团队策略都可见。"""
        r = client.get(f"{BASE}/strategies")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        station_ids = {i["station_id"] for i in data["items"]}
        assert viewer_ctx["st"].id in station_ids
        assert other_team_strategy["st"].id in station_ids
        assert data["total"] >= 2

    def test_list_viewer_team_scoped(self, client, viewer_ctx, other_team_strategy):
        """VIEWER 仅见本团队策略, 跨团队不暴露。"""
        r = client.get(f"{BASE}/strategies", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 200
        station_ids = {i["station_id"] for i in r.json()["data"]["items"]}
        assert viewer_ctx["st"].id in station_ids
        assert other_team_strategy["st"].id not in station_ids

    def test_get_strategy_ok(self, client, viewer_ctx):
        r = client.get(f"{BASE}/strategies/{viewer_ctx['st'].id}", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["station_id"] == viewer_ctx["st"].id
        assert r.json()["data"]["scenario_preset"] == "fleet"

    def test_get_strategy_cross_team_404(self, client, viewer_ctx, other_team_strategy):
        """跨团队详情 → 404 (不暴露存在)。"""
        r = client.get(
            f"{BASE}/strategies/{other_team_strategy['st'].id}",
            headers=_auth(viewer_ctx["token"]),
        )
        assert r.status_code == 404

    def test_get_strategy_not_exist_404(self, client):
        r = client.get(f"{BASE}/strategies/99999999")
        assert r.status_code == 404

    def test_update_strategy_admin_toggle_active(self, client, viewer_ctx):
        """admin 持有全部权限直通 → 更新 is_active 状态流转 (active→停用)。"""
        sid = viewer_ctx["st"].id
        assert viewer_ctx["strat"].is_active is True
        r = client.put(f"{BASE}/strategies/{sid}", json={"is_active": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message"] == "策略更新成功"
        assert body["data"]["is_active"] is False
        # 持久化校验
        viewer_ctx["s"].expire_all()
        fresh = viewer_ctx["s"].query(StationEnergyStrategy).filter(
            StationEnergyStrategy.station_id == sid).first()
        assert fresh.is_active is False

    def test_update_strategy_viewer_forbidden_403(self, client, viewer_ctx):
        """VIEWER 无 energy:strategy:edit 权限点 → 403。"""
        r = client.put(
            f"{BASE}/strategies/{viewer_ctx['st'].id}",
            json={"is_active": False}, headers=_auth(viewer_ctx["token"]),
        )
        assert r.status_code == 403

    def test_update_strategy_cross_team_404(self, client, viewer_ctx, other_team_strategy):
        """admin 改无碍, 但 viewer 跨团队 → 权限先 403 还是团队 404?
        require_permission 在路由级先执行 → viewer 无权限先 403。用 admin 视角验跨团队:
        admin 直通权限, 端点内 _assert_team 对 admin 也直通, 故 admin 改任意团队均可。
        本例断言: viewer 对他团队策略 → 403 (路由级权限拦截在前)。"""
        r = client.put(
            f"{BASE}/strategies/{other_team_strategy['st'].id}",
            json={"is_active": False}, headers=_auth(viewer_ctx["token"]),
        )
        assert r.status_code == 403


# ==================== B. 模板管理 ====================

class TestPriceTemplate:
    """B 段: 购电价模板 CRUD + 时段明细 + 权限。"""

    def test_create_template_admin_ok(self, client):
        """admin 建平台级模板 (team_id=None) + 时段明细 → 200。"""
        payload = {
            "province": "上海市", "version": 1, "effective_from": "2026-01-01",
            "allow_export_to_grid": True, "is_active": True,
            "periods": [
                {"period_type": "peak", "start_time": "10:00", "end_time": "12:00",
                 "purchase_price": 1.2, "float_ratio": 0.1},
                {"period_type": "valley", "start_time": "00:00", "end_time": "06:00",
                 "purchase_price": 0.3},
            ],
        }
        r = client.post(f"{BASE}/price-templates", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message"] == "模板创建成功"
        assert body["data"]["province"] == "上海市"
        assert body["data"]["team_id"] is None  # admin 平台级
        assert body["data"]["id"] > 0

    def test_create_template_invalid_period_type_400(self, client):
        """非法时段类型 → 400 (PeriodType 枚举校验)。"""
        payload = {
            "province": "广东省", "version": 1, "effective_from": "2026-01-01",
            "periods": [{"period_type": "super_peak", "start_time": "10:00",
                         "end_time": "12:00", "purchase_price": 1.0}],
        }
        r = client.post(f"{BASE}/price-templates", json=payload)
        assert r.status_code == 400
        assert "super_peak" in r.json()["detail"]

    def test_create_template_viewer_forbidden_403(self, client, viewer_ctx):
        """VIEWER 无 energy:price:edit → 403; 非 admin 还会被强制绑本 team_id。"""
        payload = {"province": "江苏省", "version": 1, "effective_from": "2026-01-01"}
        r = client.post(f"{BASE}/price-templates", json=payload, headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 403

    def test_create_template_missing_required_422(self, client):
        """缺必填字段 province → 422 (Pydantic)。"""
        r = client.post(f"{BASE}/price-templates", json={"version": 1, "effective_from": "2026-01-01"})
        assert r.status_code == 422

    def test_create_template_bad_version_422(self, client):
        """version < 1 → 422 (Pydantic ge=1)。"""
        r = client.post(f"{BASE}/price-templates",
                        json={"province": "浙江省", "version": 0, "effective_from": "2026-01-01"})
        assert r.status_code == 422

    def test_template_by_province_returns_periods(self, client):
        """按省份取生效模板 (最高版本) 含时段明细。"""
        tpl = _seed_template(client._sesh, province="天津市", version=1, active=True)
        r = client.get(f"{BASE}/price-templates/by-province/天津市")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["id"] == tpl.id
        assert len(data["periods"]) == 1
        assert data["periods"][0]["period_type"] == "peak"

    def test_template_by_province_not_found_404(self, client):
        r = client.get(f"{BASE}/price-templates/by-province/火星省")
        assert r.status_code == 404

    def test_update_template_admin_ok(self, client):
        tpl = _seed_template(client._sesh, province="重庆市", version=1, active=True)
        r = client.put(f"{BASE}/price-templates/{tpl.id}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["data"]["is_active"] is False

    def test_update_template_not_exist_404(self, client):
        r = client.put(f"{BASE}/price-templates/99999999", json={"is_active": False})
        assert r.status_code == 404


# ==================== C. 调度计划 ====================

class TestDispatchPlan:
    """C 段: 调度计划查询 (无计划/无场站 → 404)。"""

    def test_current_plan_none_404(self, client, viewer_ctx):
        """当前团队无任何调度计划 → 404。"""
        r = client.get(f"{BASE}/plans/current", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 404

    def test_current_plan_ok(self, client, viewer_ctx):
        """seed 一条计划 → viewer 见本团队最新窗口。"""
        s = viewer_ctx["s"]
        now = datetime.now(timezone.utc)
        plan = EnergyDispatchPlan(
            station_id=viewer_ctx["st"].id, team_id=viewer_ctx["team"].id,
            window_start=now, window_end=now, decision_reason="谷电充电",
        )
        s.add(plan)
        s.commit()
        s.refresh(plan)
        r = client.get(f"{BASE}/plans/current", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["id"] == plan.id

    def test_plans_by_station_not_exist_404(self, client):
        r = client.get(f"{BASE}/plans/99999999")
        assert r.status_code == 404

    def test_plans_current_path_before_int(self, client):
        """路由顺序: /plans/current 必须先于 /plans/{station_id:int} 注册,
        否则 'current' 被 int 匹配 → 422。此处断言走 current 分支 (admin 无计划 → 404, 非 422)。"""
        r = client.get(f"{BASE}/plans/current")
        assert r.status_code == 404  # 不是 422


# ==================== D. 能量流水 ====================

class TestEnergyFlow:
    """D 段: 能量流时序 + 套利汇总 (含日期格式校验)。"""

    def test_flow_bad_date_format_400(self, client):
        """date_from 非 YYYY-MM-DD → 400 (严格正则校验, 卡 1e168cb3)。"""
        r = client.get(f"{BASE}/flow", params={"date_from": "2026/08/08"})
        assert r.status_code == 400

    def test_flow_invalid_calendar_date_400(self, client):
        """非法日历日期 → 400 (strptime 兜底)。"""
        r = client.get(f"{BASE}/flow", params={"date_from": "2026-13-45"})
        assert r.status_code == 400

    def test_flow_ok(self, client, viewer_ctx):
        s = viewer_ctx["s"]
        now = datetime.now(timezone.utc)
        log = EnergyFlowLog(
            station_id=viewer_ctx["st"].id, team_id=viewer_ctx["team"].id,
            window_start=now, cost_saving_yuan=12.5,
        )
        s.add(log)
        s.commit()
        r = client.get(f"{BASE}/flow", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

    def test_savings_aggregation(self, client, viewer_ctx):
        """savings 按 team_id 聚合 cost_saving_yuan。"""
        s = viewer_ctx["s"]
        now = datetime.now(timezone.utc)
        s.add_all([
            EnergyFlowLog(station_id=viewer_ctx["st"].id, team_id=viewer_ctx["team"].id,
                          window_start=now, cost_saving_yuan=10.0),
            EnergyFlowLog(station_id=viewer_ctx["st"].id, team_id=viewer_ctx["team"].id,
                          window_start=now, cost_saving_yuan=5.5),
        ])
        s.commit()
        r = client.get(f"{BASE}/savings", headers=_auth(viewer_ctx["token"]))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_saving_yuan"] == 15.5
        assert data["window_count"] == 2


# ==================== 认证 ====================

class TestAuth:
    """无 token → 401 (router 级 get_current_user)。"""

    def test_strategies_no_token_401(self, anon_client):
        r = anon_client.get(f"{BASE}/strategies")
        assert r.status_code == 401

    def test_create_template_no_token_401(self, anon_client):
        r = anon_client.post(f"{BASE}/price-templates",
                             json={"province": "x", "version": 1, "effective_from": "2026-01-01"})
        assert r.status_code == 401

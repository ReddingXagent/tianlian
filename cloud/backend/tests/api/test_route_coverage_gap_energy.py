# 卡18885b82: 路由补盲 — /energy-strategy/* 10 端点
# GET/PUT /strategies, /strategies/{station_id}; GET/POST /price-templates,
# GET /price-templates/by-province/{province}, PUT /price-templates/{template_id},
# GET /plans/current, GET /plans/{station_id}, GET /flow, GET /savings
from datetime import datetime, timezone

from app.models.energy_strategy import (
    EnergyPriceTemplate, EnergyPricePeriod, StationEnergyStrategy,
    EnergyDispatchPlan, EnergyFlowLog,
)
from app.models.pricing_v2 import PeriodType
from app.models.station import Station, StationStatus
from app.models.user import Team

BASE = "/api/v1/energy-strategy"


def _seed_team(s):
    t = Team(name=f"能量团队{s.query(Team).count()}", description="测试")
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _seed_station(s, name="光储充站", team_id=None):
    sta = Station(name=name, code=f"ES{abs(hash(name)) % 10**8}", address="测试地址",
                  status=StationStatus.NORMAL, team_id=team_id)
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


def _seed_template(s, province="北京", version=1, is_active=True, effective_until=None):
    tpl = EnergyPriceTemplate(province=province, version=version,
                              effective_from=datetime(2026, 1, 1).date(),
                              effective_until=effective_until,
                              is_active=is_active, team_id=None)
    s.add(tpl)
    s.commit()
    s.refresh(tpl)
    s.add(EnergyPricePeriod(template_id=tpl.id, period_type=PeriodType.PEAK,
                            start_time=datetime.strptime("08:00", "%H:%M").time(),
                            end_time=datetime.strptime("11:00", "%H:%M").time(),
                            purchase_price=1.0))
    s.commit()
    return tpl


def _seed_strategy(s, station_id, team_id=None):
    # team_id 列 NOT NULL, 调用方未给时自动建团队
    if team_id is None:
        team_id = _seed_team(s).id
    st = StationEnergyStrategy(station_id=station_id, team_id=team_id,
                               scenario_preset="peak_shaving")
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


# ─── A. 策略配置 ───

def test_list_strategies_empty_and_seeded(client):
    r = client.get(f"{BASE}/strategies")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0
    sta = _seed_station(client._sesh)
    _seed_strategy(client._sesh, sta.id)
    r = client.get(f"{BASE}/strategies")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["station_id"] == sta.id
    assert items[0]["scenario_preset"] == "peak_shaving"


def test_get_strategy_detail_and_404(client):
    sta = _seed_station(client._sesh)
    st = _seed_strategy(client._sesh, sta.id)
    r = client.get(f"{BASE}/strategies/{sta.id}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == st.id
    assert client.get(f"{BASE}/strategies/99999").status_code == 404


def test_update_strategy_and_404(client):
    sta = _seed_station(client._sesh)
    _seed_strategy(client._sesh, sta.id)
    r = client.put(f"{BASE}/strategies/{sta.id}", json={"soc_floor": 0.2, "is_active": False})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["soc_floor"] == 0.2
    assert data["is_active"] is False
    assert client.put(f"{BASE}/strategies/99999", json={"soc_floor": 0.1}).status_code == 404


# ─── B. 模板管理 ───

def test_list_price_templates_with_filters(client):
    _seed_template(client._sesh, province="北京", version=1)
    _seed_template(client._sesh, province="上海", version=2, is_active=False)
    r = client.get(f"{BASE}/price-templates")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 2
    r = client.get(f"{BASE}/price-templates", params={"province": "上海"})
    assert r.json()["data"]["total"] == 1
    r = client.get(f"{BASE}/price-templates", params={"is_active": True})
    assert r.json()["data"]["total"] == 1


def test_create_price_template_and_invalid_period(client):
    body = {
        "province": "广东", "version": 1, "effective_from": "2026-01-01",
        "periods": [{"period_type": "peak", "start_time": "08:00",
                     "end_time": "11:00", "purchase_price": 1.2}],
    }
    r = client.post(f"{BASE}/price-templates", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["province"] == "广东"
    assert client._sesh.query(EnergyPricePeriod).count() == 1
    # 无效时段类型 → 400
    bad = dict(body, periods=[{"period_type": "bad_type", "start_time": "08:00",
                               "end_time": "11:00", "purchase_price": 1.0}])
    assert client.post(f"{BASE}/price-templates", json=bad).status_code == 400


def test_price_template_by_province(client):
    _seed_template(client._sesh, province="北京", version=1)
    _seed_template(client._sesh, province="北京", version=2)
    r = client.get(f"{BASE}/price-templates/by-province/北京")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["version"] == 2  # 取最高版本
    assert len(data["periods"]) >= 1
    assert client.get(f"{BASE}/price-templates/by-province/不存在省").status_code == 404


def test_update_price_template_and_404(client):
    tpl = _seed_template(client._sesh)
    r = client.put(f"{BASE}/price-templates/{tpl.id}", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["data"]["is_active"] is False
    assert client.put(f"{BASE}/price-templates/99999", json={"is_active": False}).status_code == 404


# ─── C. 调度计划 ───

def test_current_plan_and_404(client):
    assert client.get(f"{BASE}/plans/current").status_code == 404
    sta = _seed_station(client._sesh)
    plan = EnergyDispatchPlan(station_id=sta.id, team_id=None,
                              window_start=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc),
                              window_end=datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc))
    client._sesh.add(plan)
    client._sesh.commit()
    r = client.get(f"{BASE}/plans/current")
    assert r.status_code == 200
    assert r.json()["data"]["station_id"] == sta.id


def test_plans_by_station_and_404(client):
    sta = _seed_station(client._sesh)
    r = client.get(f"{BASE}/plans/{sta.id}")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0
    assert client.get(f"{BASE}/plans/99999").status_code == 404  # 场站不存在


# ─── D. 能量流水 ───

def _seed_flow(s, station_id):
    s.add(EnergyFlowLog(station_id=station_id, team_id=None,
                        window_start=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc),
                        pv_generation_kwh=10.0, cost_saving_yuan=5.5))
    s.commit()


def test_flow_list_and_bad_date(client):
    sta = _seed_station(client._sesh)
    _seed_flow(client._sesh, sta.id)
    r = client.get(f"{BASE}/flow")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 1
    r = client.get(f"{BASE}/flow", params={"station_id": sta.id, "date_from": "2026-08-01"})
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 1
    assert client.get(f"{BASE}/flow", params={"date_from": "not-a-date"}).status_code == 400


def test_savings_summary(client):
    sta = _seed_station(client._sesh)
    _seed_flow(client._sesh, sta.id)
    r = client.get(f"{BASE}/savings")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_saving_yuan"] == 5.5
    assert data["window_count"] == 1

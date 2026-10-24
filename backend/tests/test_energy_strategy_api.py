"""能量策略 REST API 测试 — P1-4 (任务卡 P1-4)

覆盖:
- 任务A 4省购电价模板查询 (列表 / 按省 / 时段明细)
- 任务B 端点:
  A. 策略配置  GET/PUT /strategies
  B. 模板管理  GET/POST/PUT /price-templates, /by-province/{province}
  C. 调度计划  /plans/{station_id}, /plans/current
  D. 能量流水  /flow, /savings
- 权限: viewer 写 → 403; admin 写 → 200
- 团队隔离: A 团队用户不可见 B 团队策略/计划/流水, 跨团队详情 404

注: 4 省模板的测试 seed (PROVINCES_SEED) 与 alembic data migration
(4 省种子迁移) 同源; 测试库走 Base.metadata.create_all 不跑 alembic,
故 fixture 自带等价 seed。
"""
import bcrypt
import pytest
from datetime import date, time, datetime, timedelta
from urllib.parse import quote

from app.seed.energy_price_seed import SEED_PROVINCES as PROVINCES_SEED

API = "/api/v1/energy-strategy"

# 4 省示意值权威定义见 app/seed/energy_price_seed.py (与 alembic 种子迁移同源;
# 上线前须按电网文件校准)。此处仅 import, 保证单一真相源。


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def four_provinces(client):
    """4 省平台级(team_id=NULL)购电价模板 + 时段明细。"""
    from app.models.energy_strategy import EnergyPriceTemplate, EnergyPricePeriod
    from app.models.pricing_v2 import PeriodType
    s = client._sesh
    created = {}
    for prov in PROVINCES_SEED:
        tpl = EnergyPriceTemplate(
            province=prov["province"], version=1,
            effective_from=date(2026, 1, 1), effective_until=None,
            season_start_month=prov["season_start"],
            season_end_month=prov["season_end"],
            is_active=True, team_id=None,
        )
        s.add(tpl)
        s.commit()
        s.refresh(tpl)
        for p in prov["periods"]:
            s.add(EnergyPricePeriod(
                template_id=tpl.id,
                period_type=PeriodType(p["type"]),
                start_time=time(*p["start"]), end_time=time(*p["end"]),
                purchase_price=p["price"],
            ))
        s.commit()
        created[prov["province"]] = tpl
    return created


@pytest.fixture
def viewer_user(client):
    """viewer 角色 token — 矩阵无 energy:* 权限, 写端点应 403。"""
    from app.models.user import User, UserRole
    s = client._sesh
    u = User(
        username="es_viewer", role=UserRole.VIEWER, status="active",
        password_hash=bcrypt.hashpw(b"view123456", bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    r = client.post("/api/v1/auth/login", data={"username": "es_viewer", "password": "view123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


@pytest.fixture
def cross_team_energy(client):
    """两团队 + 两 OPERATOR 用户 + 两站点 + 各站策略/计划/流水。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.energy_strategy import (
        StationEnergyStrategy, EnergyDispatchPlan, EnergyFlowLog,
    )
    s = client._sesh
    ta = Team(name="能源团队A", code="ENA")
    tb = Team(name="能源团队B", code="ENB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "eng123456"
    ua = User(username="es_eng_a", role=UserRole.OPERATOR, team_id=ta.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    ub = User(username="es_eng_b", role=UserRole.OPERATOR, team_id=tb.id, status="active",
              password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    s.add_all([ua, ub])
    s.commit()

    sa = Station(name="能源A站", code="ENSA", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="能源B站", code="ENSB", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    strat_a = StationEnergyStrategy(
        station_id=sa.id, team_id=ta.id, scenario_preset="fleet",
        pv_capacity_kw=100.0, ess_capacity_kwh=200.0, soc_floor=0.10,
    )
    strat_b = StationEnergyStrategy(
        station_id=sb.id, team_id=tb.id, scenario_preset="public_fast",
        pv_capacity_kw=50.0, ess_capacity_kwh=100.0, soc_floor=0.10,
    )
    s.add_all([strat_a, strat_b])
    s.commit()
    s.refresh(strat_a)
    s.refresh(strat_b)

    win_end = datetime(2026, 8, 1, 12, 0)
    win_start = win_end - timedelta(minutes=15)
    s.add(EnergyDispatchPlan(
        station_id=sa.id, team_id=ta.id, window_start=win_start, window_end=win_end,
        pv_setpoint_kw=80.0, grid_purchase_kw=20.0, available_power_budget_kw=100.0,
    ))
    s.add_all([
        EnergyFlowLog(station_id=sa.id, team_id=ta.id, window_start=win_start,
                      pv_generation_kwh=20.0, grid_purchase_kwh=5.0, cost_saving_yuan=12.5),
        EnergyFlowLog(station_id=sb.id, team_id=tb.id, window_start=win_start,
                      pv_generation_kwh=10.0, grid_purchase_kwh=3.0, cost_saving_yuan=6.0),
    ])
    s.commit()

    def _tok(uname):
        r = client.post("/api/v1/auth/login", data={"username": uname, "password": pwd})
        assert r.status_code == 200, r.text
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sa, "b": sb},
        "strategies": {"a": strat_a, "b": strat_b},
        "tokens": {"a": _tok("es_eng_a"), "b": _tok("es_eng_b")},
    }


# ═══════════════════════════════════════════════════════════════
# B-模板管理: 4 省模板查询 (任务A 验证)
# ═══════════════════════════════════════════════════════════════

def test_list_price_templates_returns_4_provinces(client, four_provinces):
    """admin 列表可见全部 4 省模板。"""
    r = client.get(f"{API}/price-templates")
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    provinces = {it["province"] for it in items}
    assert {"四川", "浙江", "广东", "甘肃"}.issubset(provinces)


def test_price_template_by_province_with_periods(client, four_provinces):
    """按省取当前生效模板 → 含时段明细 (3 段) + 购电价。"""
    r = client.get(f"{API}/price-templates/by-province/{quote('浙江')}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["province"] == "浙江"
    assert data["version"] == 1
    assert len(data["periods"]) == 3
    # 尖峰(shoulder) 价最高 1.20
    prices = {(p["period_type"], float(p["purchase_price"])) for p in data["periods"]}
    assert ("shoulder", 1.20) in prices


def test_price_template_by_province_not_found(client):
    """无该省模板 → 404。"""
    r = client.get(f"{API}/price-templates/by-province/{quote('西藏')}")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# B-模板管理: CRUD + 权限
# ═══════════════════════════════════════════════════════════════

def test_create_price_template_admin(client):
    """admin 新建模板版本 → 200。"""
    body = {
        "province": "江苏", "version": 1, "effective_from": "2026-01-01",
        "is_active": True,
        "periods": [
            {"period_type": "peak", "start_time": "10:00", "end_time": "12:00", "purchase_price": 0.90},
            {"period_type": "valley", "start_time": "00:00", "end_time": "06:00", "purchase_price": 0.30},
        ],
    }
    r = client.post(f"{API}/price-templates", json=body)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["province"] == "江苏"
    assert data["id"] > 0


def test_update_price_template_admin(client, four_provinces):
    """admin 更新模板生效区间 → 200。"""
    tid = four_provinces["四川"].id
    r = client.put(f"{API}/price-templates/{tid}", json={"effective_until": "2026-12-31"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["effective_until"] == "2026-12-31"


def test_create_price_template_viewer_forbidden(client, viewer_user):
    """viewer 无 energy:price:edit → 403。"""
    body = {"province": "X", "version": 1, "effective_from": "2026-01-01", "periods": []}
    r = client.post(f"{API}/price-templates", json=body, headers=_h(viewer_user))
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# A-策略配置: 列表/详情/更新 + 团队隔离
# ═══════════════════════════════════════════════════════════════

def test_list_strategies_team_isolation(client, cross_team_energy):
    """A 团队用户只看到本团队策略; admin 看全部。"""
    sa = cross_team_energy["stations"]["a"]
    sb = cross_team_energy["stations"]["b"]
    # A 用户
    r = client.get(f"{API}/strategies", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    ids = {it["station_id"] for it in r.json()["data"]["items"]}
    assert sa.id in ids and sb.id not in ids
    # admin 看全部
    r = client.get(f"{API}/strategies")
    ids = {it["station_id"] for it in r.json()["data"]["items"]}
    assert sa.id in ids and sb.id in ids


def test_get_strategy_by_station_ok(client, cross_team_energy):
    """A 用户取本站策略 → 200 + scenario_preset 正确。"""
    sa = cross_team_energy["stations"]["a"]
    r = client.get(f"{API}/strategies/{sa.id}", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["scenario_preset"] == "fleet"


def test_get_strategy_other_team_404(client, cross_team_energy):
    """A 用户取 B 站策略 → 404 (跨团队隔离)。"""
    sb = cross_team_energy["stations"]["b"]
    r = client.get(f"{API}/strategies/{sb.id}", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 404


def test_update_strategy_admin(client, cross_team_energy):
    """admin 更新策略 soc_floor/容量 → 200。"""
    sa = cross_team_energy["stations"]["a"]
    r = client.put(f"{API}/strategies/{sa.id}", json={"soc_floor": 0.15, "pv_capacity_kw": 200.0})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["soc_floor"] == 0.15
    assert data["pv_capacity_kw"] == 200.0


def test_get_strategy_not_found(client):
    """不存在的 station_id → 404。"""
    r = client.get(f"{API}/strategies/999999")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# C-调度计划
# ═══════════════════════════════════════════════════════════════

def test_plans_by_station(client, cross_team_energy):
    """A 用户取本站计划列表 → 含 seed 计划; B 站 404。"""
    sa = cross_team_energy["stations"]["a"]
    sb = cross_team_energy["stations"]["b"]
    r = client.get(f"{API}/plans/{sa.id}", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["available_power_budget_kw"] == 100.0
    # B 站对 A 用户 → 404
    r = client.get(f"{API}/plans/{sb.id}", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 404


def test_plans_current(client, cross_team_energy):
    """A 用户取本团队最新计划窗口 → 200。"""
    sa = cross_team_energy["stations"]["a"]
    r = client.get(f"{API}/plans/current", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 至少返回最近窗口 (A 站那条)
    assert data["station_id"] == sa.id


def test_plans_current_admin_sees_a(client, cross_team_energy):
    """admin 取 current (默认无团队), 任意团队最近计划均可。"""
    r = client.get(f"{API}/plans/current")
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# D-能量流水
# ═══════════════════════════════════════════════════════════════

def test_flow_list(client, cross_team_energy):
    """A 用户能量流水只含本团队 (A 站 1 条)。"""
    sa = cross_team_energy["stations"]["a"]
    r = client.get(f"{API}/flow", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["station_id"] == sa.id
    assert items[0]["pv_generation_kwh"] == 20.0


def test_flow_date_filter(client, cross_team_energy):
    """date_from/date_to 区间过滤不报错, 命中 seed 窗口 (2026-08-01)。"""
    r = client.get(f"{API}/flow?date_from=2026-08-01&date_to=2026-08-01")
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["items"]) >= 1


# ── 日期参数输入校验 (卡 1e168cb3) ──
# 旧拼接式 datetime.fromisoformat(value + " 00:00:00") 对非法/带时间串抛
# ValueError 冒泡 500; 严格 YYYY-MM-DD 校验后坏值应显式 400。

def test_flow_invalid_date_format_returns_400(client, cross_team_energy):
    """date_from 非日期格式 (乱串) → 400 而非 500。"""
    r = client.get(f"{API}/flow?date_from=not-a-date",
                   headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 400, r.text


def test_flow_invalid_calendar_date_returns_400(client, cross_team_energy):
    """date_from 格式对但非法日历 (2026-13-45) → 400。"""
    r = client.get(f"{API}/flow?date_from=2026-13-45",
                   headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 400, r.text


def test_flow_date_with_time_component_returns_400(client, cross_team_energy):
    """date_from 带时间分量 (用户误传 ISO 时间) → 400 (严格 YYYY-MM-DD)。

    旧拼接式 fromisoformat("2026-08-08T12:00:00 00:00:00") 抛 ValueError 冒泡 500。
    """
    r = client.get(f"{API}/flow?date_from=2026-08-08T12:00:00",
                   headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 400, r.text


def test_flow_invalid_date_to_returns_400(client, cross_team_energy):
    """date_to 非法日历 (2026-02-30, 2 月无 30 号) → 400。"""
    r = client.get(f"{API}/flow?date_to=2026-02-30",
                   headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 400, r.text


def test_savings_invalid_date_returns_400(client, cross_team_energy):
    """savings 端点同样校验 date_from/date_to → 400。"""
    r = client.get(f"{API}/savings?date_from=2026-13-01",
                   headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 400, r.text


def test_flow_team_isolation(client, cross_team_energy):
    """A 用户看不到 B 团队流水; admin 看到两条。"""
    sb = cross_team_energy["stations"]["b"]
    r = client.get(f"{API}/flow", headers=_h(cross_team_energy["tokens"]["a"]))
    ids = {it["station_id"] for it in r.json()["data"]["items"]}
    assert sb.id not in ids
    # admin
    r = client.get(f"{API}/flow")
    assert len(r.json()["data"]["items"]) == 2


def test_savings(client, cross_team_energy):
    """A 用户套利节省 = 本团队 cost_saving 汇总 (12.5); admin = 全部 (18.5)。"""
    r = client.get(f"{API}/savings", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert float(data["total_saving_yuan"]) == pytest.approx(12.5)
    # admin
    r = client.get(f"{API}/savings")
    assert float(r.json()["data"]["total_saving_yuan"]) == pytest.approx(18.5)


def test_savings_dispatch_rerun_same_window_not_double_counted(
    client, cross_team_energy
):
    """卡 113e313b: dispatch 同窗口重跑 (acks_late 重投递) flow 仅 1 行,
    /savings 不双计。守卫在任务层 (同窗口查重), 端点 sum 口径依赖该唯一性。"""
    from app.models.energy_strategy import EnergyFlowLog
    from app.tasks.energy_tasks import run_dispatch_cycle
    s = client._sesh
    sa = cross_team_energy["stations"]["a"]
    base = db_count = s.query(EnergyFlowLog).filter(
        EnergyFlowLog.station_id == sa.id).count()

    now = datetime(2026, 8, 1, 12, 7, 0)
    run_dispatch_cycle(s, now=now)
    s.commit()
    run_dispatch_cycle(s, now=now)   # 同窗口重跑
    s.commit()

    assert s.query(EnergyFlowLog).filter(
        EnergyFlowLog.station_id == sa.id).count() == base + 1

    r = client.get(f"{API}/savings", headers=_h(cross_team_energy["tokens"]["a"]))
    assert r.status_code == 200, r.text
    # dispatch flow cost_saving_yuan=None → 不影响 total, 但窗口数若双插会被
    # /flows 列出重复行; 此处固化 savings 口径不因重跑漂移
    assert float(r.json()["data"]["total_saving_yuan"]) == pytest.approx(12.5)


# ═══════════════════════════════════════════════════════════════
# DB 写操作异常保护 (卡 d8acd3f9)
# ═══════════════════════════════════════════════════════════════

def _patch_commit_boom(client, monkeypatch):
    """patch session.commit 抛 RuntimeError + spy rollback 计数。

    路由 db 即 client._sesh (conftest get_db override 返回同一 session 实例)。
    返回 rollback 计数器, 断言 rollback_calls["n"] >= 1 即证明路由 except 调用了 rollback。
    """
    sesh = client._sesh
    rollback_calls = {"n": 0}
    real_rollback = sesh.rollback

    def _spy_rollback(*a, **kw):
        rollback_calls["n"] += 1
        return real_rollback(*a, **kw)

    def _boom(*a, **kw):
        raise RuntimeError("simulated db commit failure")

    monkeypatch.setattr(sesh, "commit", _boom)
    monkeypatch.setattr(sesh, "rollback", _spy_rollback)
    return rollback_calls


def test_update_strategy_db_failure(client, cross_team_energy, monkeypatch):
    """PUT /strategies/{id} commit 失败 → 500 + rollback, 原策略未被破坏。"""
    sa = cross_team_energy["stations"]["a"]
    orig_pv = cross_team_energy["strategies"]["a"].pv_capacity_kw  # 100.0

    rollback_calls = _patch_commit_boom(client, monkeypatch)
    r = client.put(f"{API}/strategies/{sa.id}", json={"pv_capacity_kw": 999.0})
    assert r.status_code == 500, r.text
    # 路由级保护抛 HTTPException(500,"内部错误"): 裸 TestClient app 返回 detail,
    # 生产 app.main 经 http_exception_handler 返回 message; 两者择一。
    assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
    assert "simulated" not in r.text  # 不泄露内部异常明文
    assert rollback_calls["n"] >= 1  # rollback 被调用
    # rollback 保护: 原值仍在 (update 未落库)
    monkeypatch.undo()
    rget = client.get(f"{API}/strategies/{sa.id}")
    assert rget.status_code == 200
    assert float(rget.json()["data"]["pv_capacity_kw"]) == float(orig_pv)


def test_create_price_template_db_failure(client, monkeypatch):
    """POST /price-templates (两次 commit) commit 失败 → 500 + rollback, 无脏数据。

    覆盖 create_price_template 的 tpl commit + periods commit 序列: 任一失败须
    rollback + 500, 不留半成品模板。
    """
    body = {
        "province": "测试失败省", "version": 1, "effective_from": "2026-01-01",
        "is_active": True,
        "periods": [
            {"period_type": "peak", "start_time": "10:00", "end_time": "12:00", "purchase_price": 0.90},
        ],
    }
    rollback_calls = _patch_commit_boom(client, monkeypatch)
    r = client.post(f"{API}/price-templates", json=body)
    assert r.status_code == 500, r.text
    assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
    assert "simulated" not in r.text
    assert rollback_calls["n"] >= 1
    # rollback 生效: 未留下脏模板
    monkeypatch.undo()
    rget = client.get(f"{API}/price-templates?province=%E6%B5%8B%E8%AF%95%E5%A4%B1%E8%B4%A5%E7%9C%81")
    assert rget.status_code == 200
    assert rget.json()["data"]["items"] == []


# ═══════════════════════════════════════════════════════════════
# 业务时区边界 (卡 48bc65fe, 时区缺陷族第5弹)
# ═══════════════════════════════════════════════════════════════

def test_price_template_by_province_uses_biz_today(client, monkeypatch):
    """凌晨窗口: effective_from=业务今天的模板应判定为生效。

    云端 UTC 容器 date.today()=UTC 昨天 < effective_from(业务今天) →
    旧实现误判未生效返回 404; today_in_biz_tz() 取业务今天 → 生效 200。
    """
    from app.api.v1 import energy_strategy as es_mod
    from app.models.energy_strategy import EnergyPriceTemplate

    biz_today = date(2026, 8, 7)
    utc_today = date(2026, 8, 6)
    s = client._sesh
    s.add(EnergyPriceTemplate(
        province="时区省", version=1,
        effective_from=biz_today, effective_until=None,
        is_active=True, team_id=None,
    ))
    s.commit()

    monkeypatch.setattr(es_mod, "today_in_biz_tz", lambda: biz_today, raising=False)

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return utc_today
    monkeypatch.setattr(es_mod, "date", _FrozenDate, raising=False)

    r = client.get(f"{API}/price-templates/by-province/{quote('时区省')}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["province"] == "时区省"

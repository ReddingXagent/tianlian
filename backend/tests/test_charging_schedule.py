"""
智能充电调度引擎测试 - Phase45

覆盖调度算法与服务+API:
- SOC 优先级排序(低 SOC 优先)
- 变压器容量约束下功率分配
- 峰谷时段偏好(谷时充电)
- V2G 反向放电窗口(峰时放电 / 非峰不放电)
- 时段归类工具函数
- 动态调整功率分配
- API 端点集成(路由挂载 / 响应格式 / 错误处理)
"""
from datetime import datetime

from app.models.enterprise import Enterprise
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.charging_schedule import ChargingPeriodType
from app.services.charging_schedule_service import (
    generate_schedule,
    adjust_schedule,
    classify_period,
)


# ─── Helpers ───

def _seed_fleet(db_session, n_vehicles=3, code="SCH_TEST"):
    """建企业 + n 辆车, 返回 (enterprise_id, [vehicle_ids])。"""
    ent = Enterprise(name="调度测试企业", code=code, balance=10000.0)
    db_session.add(ent)
    db_session.commit()
    db_session.refresh(ent)

    vids = []
    for i in range(n_vehicles):
        v = EnterpriseVehicle(
            enterprise_id=ent.id,
            plate_number=f"豫A-SCH-{i:03d}",
            vin=f"LSVAUSCH{ent.id:06d}{i:02d}",
        )
        db_session.add(v)
        vids.append(v)
    db_session.commit()
    for v in vids:
        db_session.refresh(v)
    return ent.id, [v.id for v in vids]


_VALLEY_START = datetime(2026, 7, 22, 2, 0)    # 02:00 谷时
_VALLEY_END = datetime(2026, 7, 22, 6, 0)
_PEAK_START = datetime(2026, 7, 22, 12, 0)     # 12:00 峰时
_PEAK_END = datetime(2026, 7, 22, 15, 0)


# ======================================================================
# 时段归类工具
# ======================================================================

def test_classify_period():
    """峰/平/谷时段归类正确。"""
    assert classify_period(2) == ChargingPeriodType.VALLEY     # 凌晨谷
    assert classify_period(23) == ChargingPeriodType.VALLEY    # 深夜谷
    assert classify_period(6) == ChargingPeriodType.VALLEY     # 早6点仍属谷
    assert classify_period(12) == ChargingPeriodType.PEAK      # 午间峰
    assert classify_period(19) == ChargingPeriodType.PEAK      # 晚间峰
    assert classify_period(8) == ChargingPeriodType.FLAT       # 上午平
    assert classify_period(16) == ChargingPeriodType.FLAT      # 下午平


# ======================================================================
# SOC 优先级排序
# ======================================================================

def test_generate_schedule_priority_by_soc(db_session):
    """低 SOC 车辆优先级更高(priority 更小), 且在功率充足时全部获得充电。"""
    ent_id, vids = _seed_fleet(db_session, 3)
    states = [
        {"vehicle_id": vids[0], "current_soc": 0.8, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": vids[1], "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": vids[2], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    result = generate_schedule(db_session, ent_id, states, 30.0, _VALLEY_START, _VALLEY_END)

    assert "error" not in result
    by_priority = sorted(result["entries"], key=lambda e: e["priority"])
    # priority=1 必须是 SOC 最低的车(vids[2], soc=0.2)
    assert by_priority[0]["vehicle_id"] == vids[2]
    assert by_priority[0]["soc_start"] == 0.2
    assert by_priority[0]["priority"] == 1
    # 功率充足(需求 21 < 30), 三辆都充电
    assert result["summary"]["charging_vehicles"] == 3


# ======================================================================
# 变压器容量约束
# ======================================================================

def test_generate_schedule_power_constraint(db_session):
    """功率不足时按优先级贪心分配, 不超总容量, 单车不超 max_power_per_vehicle。"""
    ent_id, vids = _seed_fleet(db_session, 3)
    states = [
        {"vehicle_id": vids[i], "current_soc": 0.1 + i * 0.1, "target_soc": 0.9, "max_power_kw": 10.0}
        for i in range(3)
    ]
    # 排序: soc 0.1(p1) / 0.2(p2) / 0.3(p3); 单车上限 7; 可用 15
    # p1:7(rem8) p2:7(rem1) p3:1(rem0) => 合计 15
    result = generate_schedule(
        db_session, ent_id, states, 15.0, _VALLEY_START, _VALLEY_END,
        rule_spec={"max_power_per_vehicle": 7.0},
    )

    assert result["summary"]["allocated_power_kw"] == 15.0
    assert result["summary"]["remaining_power_kw"] == 0.0
    for e in result["entries"]:
        assert e["assigned_power_kw"] <= 7.0          # 单车上限
    # SOC 最高的车(vids[2]=0.3, 优先级最低)只分到残余 1kW
    by_vid = {e["vehicle_id"]: e for e in result["entries"]}
    assert by_vid[vids[2]]["assigned_power_kw"] == 1.0


# ======================================================================
# 峰谷时段偏好(谷时充电)
# ======================================================================

def test_generate_schedule_valley_preference(db_session):
    """谷时段窗口标记 valley_preferred, 充电条目 period_type=valley。"""
    ent_id, vids = _seed_fleet(db_session, 1)
    states = [{"vehicle_id": vids[0], "current_soc": 0.3, "target_soc": 0.9, "max_power_kw": 7.0}]

    result = generate_schedule(db_session, ent_id, states, 10.0, _VALLEY_START, _VALLEY_END)

    assert result["period_type"] == "valley"
    assert result["valley_preferred"] is True
    assert result["entries"][0]["charge_mode"] == "charge"
    assert result["entries"][0]["period_type"] == "valley"


# ======================================================================
# V2G 反向放电窗口
# ======================================================================

def test_generate_schedule_v2g_discharge_in_peak(db_session):
    """峰时段: 高 SOC 车辆进入 V2G 放电, 低 SOC 车辆正常充电。"""
    ent_id, vids = _seed_fleet(db_session, 2)
    states = [
        {"vehicle_id": vids[0], "current_soc": 0.95, "target_soc": 0.9, "max_power_kw": 7.0},  # 可放电
        {"vehicle_id": vids[1], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},   # 需充电
    ]
    result = generate_schedule(
        db_session, ent_id, states, 10.0, _PEAK_START, _PEAK_END,
        rule_spec={"v2g_enabled": True, "v2g_discharge_kw": 5.0},
    )

    assert result["period_type"] == "peak"
    by_vid = {e["vehicle_id"]: e for e in result["entries"]}
    assert by_vid[vids[0]]["charge_mode"] == "discharge"      # 高 SOC 放电
    assert by_vid[vids[0]]["assigned_power_kw"] == 5.0
    assert by_vid[vids[1]]["charge_mode"] == "charge"         # 低 SOC 充电
    assert result["summary"]["v2g_discharge_vehicles"] == 1


def test_generate_schedule_v2g_no_discharge_off_peak(db_session):
    """非峰时段(谷时): 即便启用 V2G, 高 SOC 车辆也不放电(只待机)。"""
    ent_id, vids = _seed_fleet(db_session, 1)
    states = [{"vehicle_id": vids[0], "current_soc": 0.95, "target_soc": 0.9, "max_power_kw": 7.0}]
    result = generate_schedule(
        db_session, ent_id, states, 10.0, _VALLEY_START, _VALLEY_END,
        rule_spec={"v2g_enabled": True},
    )

    by_vid = {e["vehicle_id"]: e for e in result["entries"]}
    assert by_vid[vids[0]]["charge_mode"] == "idle"
    assert by_vid[vids[0]]["assigned_power_kw"] == 0.0
    assert result["summary"]["v2g_discharge_vehicles"] == 0


# ======================================================================
# 动态调整
# ======================================================================

def test_adjust_schedule(db_session):
    """动态调整覆盖原功率分配, 返回最新条目。"""
    ent_id, vids = _seed_fleet(db_session, 2)
    states = [
        {"vehicle_id": vids[0], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
        {"vehicle_id": vids[1], "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
    ]
    gen = generate_schedule(db_session, ent_id, states, 14.0, _VALLEY_START, _VALLEY_END)
    plan_id = gen["plan_id"]
    e0 = next(e for e in gen["entries"] if e["vehicle_id"] == vids[0])
    e1 = next(e for e in gen["entries"] if e["vehicle_id"] == vids[1])

    result = adjust_schedule(db_session, plan_id, [
        {"entry_id": e0["id"], "new_power_kw": 3.0},
        {"entry_id": e1["id"], "new_power_kw": 11.0},
    ])

    assert "error" not in result
    assert result["status"] == "planned"
    by_vid = {e["vehicle_id"]: e for e in result["entries"]}
    assert by_vid[vids[0]]["assigned_power_kw"] == 3.0
    assert by_vid[vids[1]]["assigned_power_kw"] == 11.0


def test_adjust_schedule_plan_not_found(db_session):
    """调整不存在的计划返回 error。"""
    result = adjust_schedule(db_session, 99999, [{"entry_id": 1, "new_power_kw": 5.0}])
    assert "error" in result


# ======================================================================
# API 端点集成
# ======================================================================

def test_api_generate_schedule(client, db_session):
    """POST /fleet/charging/schedule/generate 路由可达, 返回统一响应。"""
    ent_id, vids = _seed_fleet(db_session, 2)
    resp = client.post("/api/v1/fleet/charging/schedule/generate", json={
        "enterprise_id": ent_id,
        "vehicle_states": [
            {"vehicle_id": vids[0], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
            {"vehicle_id": vids[1], "current_soc": 0.5, "target_soc": 0.9, "max_power_kw": 7.0},
        ],
        "available_power_kw": 14.0,
        "time_window_start": "2026-07-22T02:00:00",
        "time_window_end": "2026-07-22T06:00:00",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plan_id"] > 0
    assert data["period_type"] == "valley"
    assert len(data["entries"]) == 2
    assert data["summary"]["charging_vehicles"] == 2


def test_api_generate_schedule_enterprise_not_found(client, db_session):
    """企业不存在时返回 404。"""
    ent_id, vids = _seed_fleet(db_session, 1)
    resp = client.post("/api/v1/fleet/charging/schedule/generate", json={
        "enterprise_id": 999999,
        "vehicle_states": [
            {"vehicle_id": vids[0], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
        ],
        "available_power_kw": 10.0,
        "time_window_start": "2026-07-22T02:00:00",
        "time_window_end": "2026-07-22T06:00:00",
    })
    assert resp.status_code == 404


def test_api_current_and_adjust(client, db_session):
    """生成后可通过 current 查询, 并通过 adjust 动态调整。"""
    ent_id, vids = _seed_fleet(db_session, 1)
    gen = client.post("/api/v1/fleet/charging/schedule/generate", json={
        "enterprise_id": ent_id,
        "vehicle_states": [
            {"vehicle_id": vids[0], "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0},
        ],
        "available_power_kw": 7.0,
        "time_window_start": "2026-07-22T02:00:00",
        "time_window_end": "2026-07-22T06:00:00",
    })
    plan_id = gen.json()["data"]["plan_id"]
    entry_id = gen.json()["data"]["entries"][0]["id"]

    # current
    cur = client.get(f"/api/v1/fleet/charging/schedule/current?enterprise_id={ent_id}")
    assert cur.status_code == 200
    assert cur.json()["data"]["plan"]["id"] == plan_id

    # adjust
    adj = client.patch(
        f"/api/v1/fleet/charging/schedule/{plan_id}/adjust",
        json={"new_distribution": [{"entry_id": entry_id, "new_power_kw": 4.0}]},
    )
    assert adj.status_code == 200
    assert adj.json()["data"]["entries"][0]["assigned_power_kw"] == 4.0

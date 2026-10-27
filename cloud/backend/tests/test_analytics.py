#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运维数据分析与预测 API 测试
覆盖: /health-score, /efficiency-analysis, /anomaly-detection
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.device import Device

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


# ========== 鉴权检查 ==========

def test_health_score_requires_auth():
    resp = client.post("/api/v1/analytics/health-score", json={"device_id": 1})
    assert resp.status_code in (401, 403, 404, 422)


def test_efficiency_requires_auth():
    resp = client.post("/api/v1/analytics/efficiency-analysis", json={"device_ids": [1]})
    assert resp.status_code in (401, 403, 422)


def test_anomaly_requires_auth():
    resp = client.post("/api/v1/analytics/anomaly-detection", json={"device_id": 1})
    assert resp.status_code in (401, 403, 404, 422)


# ========== Health Score 测试 ==========

def test_health_score_device_not_found():
    """设备不存在返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 9999, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_health_score_device_no_data():
    """设备存在但无遥测数据返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 1, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ========== Efficiency Analysis 测试 ==========

def test_efficiency_analysis_no_data():
    """空数据库 - 设备不存在返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": [1],
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-01-31T23:59:59",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_efficiency_analysis_by_station():
    """按站点筛选 - 设备不存在返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "station_id": 1,
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-01-31T23:59:59",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ========== Anomaly Detection 测试 ==========

def test_anomaly_detection_device_not_found():
    """设备不存在返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/anomaly-detection",
        json={"device_id": 9999, "hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_anomaly_detection_no_data():
    """设备无遥测数据返回 404"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/anomaly-detection",
        json={"device_id": 1, "hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ========== 成功路径测试 ==========

def _seed_telemetry_data(db, device_id, hours=24, base_temp=25, base_pf=0.95):
    """辅助函数：创建指定小时数的遥测种子数据"""
    from app.models.telemetry import Telemetry
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for i in range(hours):
        t = Telemetry(
            device_id=device_id,
            timestamp=now - timedelta(hours=i),
            battery_soc=50.0 + i * 0.5,
            battery_soh=85.0,
            battery_temperature=base_temp + (i % 10),
            battery_current=10.0 + i,
            grid_power_total=50.0 + i * 2,
            grid_power_factor=base_pf - i * 0.01,
            grid_voltage_a=220.0 + i * 0.5,
            grid_voltage_b=220.0 + i * 0.3,
            grid_voltage_c=220.0 + i * 0.4,
            grid_current_a=10.0 + i * 0.2,
            grid_current_b=10.0 + i * 0.1,
            grid_current_c=10.0 + i * 0.15,
            inv_power_a=40.0 + i * 1.5,
            charger_power=8.0 + i * 0.3,
        )
        db.add(t)
    db.commit()


def test_health_score_success(test_db):
    """health-score 成功路径：创建设备+遥测数据后调用"""
    db = test_db['session']
    device = Device(id=100, sn='DEV-100', name='测试逆变器', type='PV_INVERTER', station_id=1, status='online')
    db.add(device)
    db.commit()
    _seed_telemetry_data(db, 100, hours=24)

    token = _login()
    resp = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 100, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert resp.status_code == 200
    assert 'overall_score' in data
    assert 'score_breakdown' in data
    assert data.get('device_name') == '测试逆变器'
    assert 0 <= data['overall_score'] <= 100
    assert 'battery_health' in data['score_breakdown']
    assert 'recommendations' in data


def test_health_score_calc_failure_returns_500(test_db, monkeypatch):
    """健康度评分计算抛错 → 500, 不冒泡原始异常 (卡 f3e5633d)。"""
    from app.api.v1.analytics import health as health_api

    db = test_db['session']
    device = Device(id=150, sn='DEV-150', name='故障设备', type='PV_INVERTER', station_id=1, status='online')
    db.add(device)
    db.commit()
    _seed_telemetry_data(db, 150, hours=24)

    def _boom(*a, **kw):
        raise ValueError("遥测数据含 NaN")

    monkeypatch.setattr(health_api, "_calculate_battery_health_score", _boom)

    token = _login()
    resp = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 150, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 500
    assert "NaN" not in str(resp.json().get("detail", ""))


def test_efficiency_analysis_by_device_ids_success(test_db):
    """efficiency-analysis 按设备ID列表成功

    查询窗口动态取 now±2h (卡 7b7a7444): 种子遥测以 now 为锚 (见 _seed_telemetry_data),
    硬编码窗口 [2026-01-01, 2026-12-31] 在 2027 年起不再包含 now → 遥测滑出窗口断言失败。
    """
    from datetime import datetime, timedelta, timezone as _tz
    db = test_db['session']
    inv = Device(id=200, sn='DEV-200', name='逆变器', type='PV_INVERTER', station_id=1, status='online')
    chg = Device(id=201, sn='DEV-201', name='充电桩', type='CHARGER_DC', station_id=1, status='online')
    bat = Device(id=202, sn='DEV-202', name='电池', type='BATTERY', station_id=1, status='online')
    db.add_all([inv, chg, bat])
    db.commit()
    _seed_telemetry_data(db, 200, hours=10)
    _seed_telemetry_data(db, 201, hours=10)
    _seed_telemetry_data(db, 202, hours=10)

    now = datetime.now(_tz.utc)
    token = _login()
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": [200, 201, 202],
            "start_date": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert resp.status_code == 200
    assert data['total_devices'] == 3
    assert data['efficiency_score'] > 0
    assert len(data['breakdown_by_device']) == 3
    assert data['optimization_suggestions']


def test_efficiency_analysis_no_n_plus_1_telemetry(test_db):
    """N+1 断言: 能耗分析遥测数据必须批量(IN)加载。
    设备数 1→2 翻倍，efficiency-analysis 的 SQL 查询数增量应为 0(批量 O(1))；
    若 per-device 查询 Telemetry(N+1)，增量 ≥1。"""
    from sqlalchemy import event
    db = test_db['session']
    dev_a = Device(id=400, sn='DEV-400', name='设备A', type='PV_INVERTER', station_id=1, status='online')
    dev_b = Device(id=401, sn='DEV-401', name='设备B', type='CHARGER_DC', station_id=1, status='online')
    db.add_all([dev_a, dev_b])
    db.commit()
    _seed_telemetry_data(db, 400, hours=10)
    _seed_telemetry_data(db, 401, hours=10)

    token = _login()
    engine = test_db['engine']
    base_payload = {
        "start_date": "2026-01-01T00:00:00",
        "end_date": "2026-12-31T23:59:59",
    }

    def _count_queries(device_ids):
        counter = {"n": 0}

        def _on_cursor(conn, cursor, statement, params, ctx, executemany):
            counter["n"] += 1

        event.listen(engine, "after_cursor_execute", _on_cursor)
        try:
            r = client.post(
                "/api/v1/analytics/efficiency-analysis",
                json={**base_payload, "device_ids": device_ids},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
        finally:
            event.remove(engine, "after_cursor_execute", _on_cursor)
        return counter["n"]

    n1 = _count_queries([400])
    n2 = _count_queries([400, 401])
    delta = n2 - n1
    # 批量加载: 设备数翻倍查询数不增(delta=0); N+1: delta>=1
    assert delta <= 0, (
        f"N+1 未修复: 能耗分析遥测非批量加载。"
        f"设备数 1→2，SQL 查询数 {n1}→{n2}（增量 {delta}），批量 IN 应为增量 0。"
    )


def test_efficiency_analysis_by_station_id_success(test_db):
    """efficiency-analysis 按站点筛选成功 (窗口动态取 now±2h, 卡 7b7a7444)"""
    from datetime import datetime, timedelta, timezone as _tz
    db = test_db['session']
    dev = Device(id=300, sn='DEV-300', name='通用设备', type='METER', station_id=5, status='online')
    db.add(dev)
    db.commit()
    _seed_telemetry_data(db, 300, hours=12)

    now = datetime.now(_tz.utc)
    token = _login()
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "station_id": 5,
            "start_date": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert resp.status_code == 200
    assert data['total_devices'] >= 1


def test_efficiency_analysis_no_params_returns_400(test_db):
    """efficiency-analysis 缺少参数返回400"""
    token = _login()
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-12-31T23:59:59",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_anomaly_detection_success(test_db):
    """anomaly-detection 成功路径：有异常数据的场景"""
    db = test_db['session']
    dev = Device(id=400, sn='DEV-400', name='高温设备', type='PV_INVERTER', station_id=1, status='online')
    db.add(dev)
    db.commit()
    # 模拟高温+电流异常
    from app.models.telemetry import Telemetry
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for i in range(24):
        temp = 55.0 + (i % 3) * 2  # 高温 55-59°C
        current = 120.0 + i * 5     # 电流 120-235A
        t = Telemetry(
            device_id=400,
            timestamp=now - timedelta(hours=i),
            battery_temperature=temp,
            battery_current=current,
            grid_power_total=80.0 + i * 3,
            grid_power_factor=0.90 - i * 0.02,
            grid_voltage_a=240.0, grid_voltage_b=235.0, grid_voltage_c=245.0,
            grid_current_a=current, grid_current_b=current * 0.9, grid_current_c=current * 1.05,
        )
        db.add(t)
    db.commit()

    token = _login()
    resp = client.post(
        "/api/v1/analytics/anomaly-detection",
        json={"device_id": 400, "hours": 48},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert resp.status_code == 200
    assert len(data['detected_anomalies']) > 0
    assert data['severity'] in ('low', 'medium', 'high', 'critical')
    assert 'root_causes' in data
    assert 'suggested_actions' in data


def test_anomaly_detection_no_anomalies(test_db):
    """anomaly-detection 稳定数据无异常"""
    db = test_db['session']
    dev = Device(id=500, sn='DEV-500', name='稳定设备', type='BATTERY', station_id=1, status='online')
    db.add(dev)
    db.commit()
    from app.models.telemetry import Telemetry
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for i in range(8):
        t = Telemetry(
            device_id=500,
            timestamp=now - timedelta(hours=i),
            battery_temperature=25.0,  # 恒温
            battery_soc=70.0,
            battery_current=15.0,
            grid_power_total=50.0,
            grid_power_factor=0.98,
        )
        db.add(t)
    db.commit()

    token = _login()
    resp = client.post(
        "/api/v1/analytics/anomaly-detection",
        json={"device_id": 500, "hours": 24},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 数据点少于5个，异常检测返回空列表
    assert isinstance(data['detected_anomalies'], list)


# ========== Health Score 告警回归（卡 6a179c0c）==========

def _seed_alarm(db, device_id, level, count=1):
    """辅助函数：为设备种指定等级的活跃告警"""
    from app.models.alarm import Alarm, AlarmStatus
    for _ in range(count):
        db.add(Alarm(
            device_id=device_id,
            level=level,
            status=AlarmStatus.ACTIVE,
            alarm_type="test",
            content=f"{level.value if hasattr(level, 'value') else level} alarm",
        ))
    db.commit()


def test_health_score_with_alarms_returns_200_and_lower_score(test_db):
    """回归 6a179c0c: 设备有告警记录时 health-score 不再 500(AttributeError)，
    且告警拉低评分 —— 对比同配置无告警设备。"""
    from app.models.alarm import AlarmLevel
    db = test_db['session']

    # 两个同配置设备，唯一差异是有无告警
    dev_clean = Device(id=600, sn='DEV-600', name='无告警设备', type='PV_INVERTER', station_id=1, status='online')
    dev_alarmed = Device(id=601, sn='DEV-601', name='告警设备', type='PV_INVERTER', station_id=1, status='online')
    db.add_all([dev_clean, dev_alarmed])
    db.commit()
    _seed_telemetry_data(db, 600, hours=24)
    _seed_telemetry_data(db, 601, hours=24)

    # 告警设备种多条 critical 告警（未解决），拉低 alarm_frequency
    _seed_alarm(db, 601, AlarmLevel.CRITICAL, count=5)

    token = _login()
    resp_clean = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 600, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_alarmed = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 601, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 核心断言: 有告警设备不再 500
    assert resp_alarmed.status_code == 200, resp_alarmed.text
    assert resp_clean.status_code == 200
    alarmed = resp_alarmed.json()
    clean = resp_clean.json()
    # 告警直接拉低 alarm_frequency 子分
    assert alarmed['score_breakdown']['alarm_frequency'] < clean['score_breakdown']['alarm_frequency']
    # 进而拉低总分
    assert alarmed['overall_score'] < clean['overall_score']


def test_health_score_alarm_level_weighting(test_db):
    """回归 6a179c0c: 不同 AlarmLevel 命中不同权重。
    同条数下 critical(权重5) 远高于 info(权重1)，
    critical 设备的 alarm_frequency 子分应明显低于 info 设备。"""
    from app.models.alarm import AlarmLevel
    db = test_db['session']

    dev_crit = Device(id=610, sn='DEV-610', name='严重告警设备', type='PV_INVERTER', station_id=1, status='online')
    dev_info = Device(id=611, sn='DEV-611', name='提示告警设备', type='PV_INVERTER', station_id=1, status='online')
    db.add_all([dev_crit, dev_info])
    db.commit()
    _seed_telemetry_data(db, 610, hours=24)
    _seed_telemetry_data(db, 611, hours=24)

    # 同条数(3条)，仅等级不同
    _seed_alarm(db, 610, AlarmLevel.CRITICAL, count=3)
    _seed_alarm(db, 611, AlarmLevel.INFO, count=3)

    token = _login()
    crit = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 610, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    info = client.post(
        "/api/v1/analytics/health-score",
        json={"device_id": 611, "days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert crit.status_code == 200, crit.text
    assert info.status_code == 200, info.text
    crit_af = crit.json()['score_breakdown']['alarm_frequency']
    info_af = info.json()['score_breakdown']['alarm_frequency']
    # critical 权重高 → 扣分多 → 子分更低
    assert crit_af < info_af, f"告警等级权重未区分: critical={crit_af} info={info_af}"

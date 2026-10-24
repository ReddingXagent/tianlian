#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anomaly-detection 端点 numpy 边界保护 + 异常兜底测试。

覆盖:
- 空遥测 / 单点 / 含 None / 全 None → numpy 操作不崩溃(回归锁定)
- 正常异常数据 → 仍能正确检测(防加固破坏既有功能)
- 内部未预期异常 → 500 受控兜底, 不向客户端泄露 str(e) (对应修复 #5/#6)
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.telemetry import Telemetry

# 模块级 client：autouse _auth_module_level_client 会登录 admin 并注入 token，
# 且经 test_db override 的 SessionLocal 命中本测试库。
client = TestClient(app)

ENDPOINT = "/api/v1/analytics/anomaly-detection"


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(SessionLocal override + admin seed)，供模块级 client 命中。"""
    return test_db


def _make_device(db):
    from app.models.station import Station, StationStatus
    st = Station(name="异常检测测试站", code="STAANOM001", address="测试地址", status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    dev = Device(
        sn="SN-ANOMALY-001",
        name="异常检测测试设备",
        code="ANOM001",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=st.id,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _add_telemetry(db, device_id, rows):
    """插入遥测行；rows 为字段 dict 列表(不含 device_id/timestamp)。
    timestamp 按分钟递增，均落在默认 24h 检测窗口内。"""
    base = datetime.now(timezone.utc) - timedelta(minutes=len(rows) + 5)
    for i, fields in enumerate(rows):
        db.add(Telemetry(
            device_id=device_id,
            timestamp=base + timedelta(minutes=i),
            **fields,
        ))
    db.commit()


# ========== numpy 边界：不崩溃(回归锁定) ==========

def test_empty_telemetry_data(test_db):
    """设备存在但无遥测 → 404「没有遥测数据」，不触发 numpy。"""
    db = test_db["session"]
    dev = _make_device(db)
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 404
    assert "没有遥测数据" in resp.text  # 全局中间件包装：文案在 message/data.detail


def test_single_data_point(test_db):
    """单条遥测 → 200，各 _detect 因样本不足返回空，severity=low。"""
    db = test_db["session"]
    dev = _make_device(db)
    _add_telemetry(db, dev.id, [{"battery_temperature": 30.0, "battery_soc": 50.0}])
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_anomalies"] == []
    assert body["anomaly_score"] == 0.0
    assert body["severity"] == "low"


def test_none_values_in_telemetry(test_db):
    """含 None 的遥测(混合) → numpy 过滤 None 后正常计算，不崩溃。"""
    db = test_db["session"]
    dev = _make_device(db)
    rows = []
    for i in range(10):
        row = {"battery_soc": 50.0}
        if i % 2 == 0:  # 偶数行才有温度，奇数行 battery_temperature=None
            row["battery_temperature"] = 25.0
        rows.append(row)
    _add_telemetry(db, dev.id, rows)
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 200
    resp.json()  # 可序列化即未崩溃


def test_all_none_values(test_db):
    """所有数值字段为 None → 各维度过滤后为空，不崩溃。"""
    db = test_db["session"]
    dev = _make_device(db)
    _add_telemetry(db, dev.id, [{} for _ in range(10)])
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_anomalies"] == []
    assert body["severity"] == "low"


def test_normal_detection(test_db):
    """正常异常数据(SOC 绝对阈值 <20%) → 仍能检测到 soc_low。"""
    db = test_db["session"]
    dev = _make_device(db)
    _add_telemetry(db, dev.id, [{"battery_soc": 10.0} for _ in range(6)])
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 200
    types = {a["type"] for a in resp.json()["detected_anomalies"]}
    assert "soc_low" in types


# ========== 异常兜底：500 不泄露(对应修复 #5/#6) ==========

def test_internal_error_returns_500_not_leaked(test_db, monkeypatch):
    """端点级兜底：内部未预期异常 → 500 + message=「内部错误」，不泄露 str(e)。

    区分点：端点 try/except 抛 HTTPException(500,"内部错误") 经 HTTPException
    handler 包装后 message=="内部错误"；若未在端点捕获、冒泡到 app.main 的全局
    Exception handler，则 message=="服务器内部错误"。故精确断言 message 即可
    驱动端点级兜底（同时提供 device_id 业务日志上下文，全局 handler 无法替代）。
    """
    import app.api.v1.analytics.anomaly as anomaly_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("SECRET_NUMPY_BOOM_TRACE")

    monkeypatch.setattr(anomaly_mod, "_detect_temperature_anomalies", _boom)

    db = test_db["session"]
    dev = _make_device(db)
    _add_telemetry(db, dev.id, [{"battery_temperature": 30.0}])  # 遥测非空才会走到 _detect_*
    resp = client.post(ENDPOINT, json={"device_id": dev.id, "hours": 24})
    assert resp.status_code == 500
    assert resp.json().get("message") == "内部错误"
    assert "SECRET_NUMPY_BOOM_TRACE" not in resp.text

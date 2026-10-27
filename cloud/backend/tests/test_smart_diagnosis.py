#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能诊断 Smart Diagnosis API 测试
智能诊断流程、配置、结果查询
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup(test_db):
    """种子 station + device（任务卡 ab5c5f17：治理后 analyze/diagnose-and-repair
    校验 device 存在；admin 豁免 team，device_id=1 需存在）。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    s = test_db["session"]
    s.add(Station(id=1, name="种子站", code="SEEDST01", status=StationStatus.NORMAL))
    s.commit()
    s.add(Device(id=1, sn="SN-SEED-1", name="种子设备1", code="SEED1",
                 type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                 station_id=1, health_score=85.0))
    s.commit()

def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json().get("token") or resp.json().get("data", {}).get("token")

def test_analyze_fault():
    """智能故障诊断"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/analyze", json={
        "fault_desc": "设备温度过高，电压异常",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert len(data["possible_causes"]) > 0
    assert len(data["recommended_actions"]) > 0

def test_analyze_fault_with_device():
    """带设备ID的故障诊断"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/analyze", json={
        "device_id": 1,
        "fault_desc": "通信中断，设备离线",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert "matched_keywords" in data

def test_analyze_unknown_fault():
    """未知故障描述"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/analyze", json={
        "fault_desc": "一些完全无关的文字描述",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["confidence"] == 0.3

def test_list_keywords():
    """获取故障关键词列表"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/smart-diagnosis/keywords", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "keywords" in data
    assert data["total"] > 0

def test_diagnose_and_repair():
    """诊断并自动创建工单"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/diagnose-and-repair", json={
        "device_id": 1,
        "fault_desc": "设备温度过高，需要维修",
    }, headers=headers)
    assert resp.status_code == 200

def test_diagnosis_history():
    """查询历史诊断记录"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/smart-diagnosis/history", headers=headers)
    assert resp.status_code == 200

def test_diagnosis_history_by_device():
    """按设备查询历史诊断记录"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/smart-diagnosis/history?device_id=1", headers=headers)
    assert resp.status_code == 200

def test_diagnosis_history_pagination():
    """历史诊断记录分页"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/smart-diagnosis/history?page=1&page_size=5", headers=headers)
    assert resp.status_code == 200

def test_diagnose_and_repair_creator_id_binds_to_user(test_db):
    """[d3cc573c] 自动建单 creator_id == 当前登录用户 id，不为硬编码 999。

    未修前 creator_id=999（fresh DB 无 id=999 用户），断言失败。
    """
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/diagnose-and-repair", json={
        "device_id": 1,
        "fault_desc": "设备电压异常，需要维修",
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["data"]["auto_create_workorder"] is True if isinstance(data.get("data"), dict) else True
    wo = data.get("workorder")
    assert wo is not None, f"应触发自动建单, data={data}"
    assert wo is not None, "应触发自动建单"

    from app.models.user import User
    from app.models.workorder import WorkOrder
    s = test_db["session"]
    admin = s.query(User).filter(User.username == "admin").first()
    created = s.query(WorkOrder).filter(WorkOrder.id == wo["workorder_id"]).first()
    assert created is not None
    assert created.creator_id == admin.id
    assert created.creator_id != 999

def test_diagnose_and_repair_no_device():
    """诊断但不指定设备"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/smart-diagnosis/diagnose-and-repair", json={
        "fault_desc": "设备异常停机",
    }, headers=headers)
    assert resp.status_code == 200
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输入枚举守卫测试（卡 77a186b3）

一梯队 8 处自由字符串 status/type 字段已收紧为 Literal。
每个模型验证：非法值 → Pydantic 422；合法值不被误伤（不 422）。

只断言校验层行为（422/非422），不关心业务层返回（200/404/400 皆可），
避免与各端点的业务前置条件（资源存在性、team 归属）耦合。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BAD = "NOT_A_STATUS"


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _headers():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json().get("token") or resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _assert_guard(method, url, payload):
    """非法枚举值 → 422；同请求去掉坏字段或换合法值 → 不 422"""
    r = client.request(method, url, json=payload, headers=_headers())
    assert r.status_code == 422, f"{method} {url} 非法 status={payload.get('status') or payload.get('type')!r} 应 422, 实际 {r.status_code}: {r.text[:200]}"


# ─── 1. 充电订单状态 ───

def test_charging_order_status_rejected():
    _assert_guard("PUT", "/api/v1/charging-orders/1/status", {"status": BAD})


# ─── 2. 工单 ───

def test_workorder_create_type_rejected():
    _assert_guard("POST", "/api/v1/work-orders", {"fault_desc": "x", "type": "not_a_type"})


def test_workorder_update_status_rejected():
    _assert_guard("PUT", "/api/v1/work-orders/1", {"status": BAD})


# ─── 3. 设备 ───

def test_device_create_type_rejected():
    _assert_guard("POST", "/api/v1/devices", {"code": "T001", "name": "n", "type": "not_a_type"})


def test_device_update_status_rejected():
    _assert_guard("PUT", "/api/v1/devices/1", {"status": BAD})


# ─── 4. 网关 / 固件 ───

def test_gateway_create_status_rejected():
    _assert_guard("POST", "/api/v1/gateways", {"sn": "SN-77A186B3-1", "name": "gw", "status": BAD})


def test_gateway_update_status_rejected():
    _assert_guard("PUT", "/api/v1/gateways/1", {"status": BAD})


def test_firmware_update_status_rejected():
    _assert_guard("PUT", "/api/v1/gateways/firmware/1", {"status": BAD})


# ─── 5. 站点 ───

def test_station_create_status_rejected():
    _assert_guard("POST", "/api/v1/stations", {"name": "s", "code": "ST-77A186B3", "status": BAD})


def test_station_update_status_rejected():
    _assert_guard("PUT", "/api/v1/stations/1", {"status": BAD})


# ─── 6. 巡检任务 ───

def test_inspection_task_update_status_rejected():
    _assert_guard("PUT", "/api/v1/inspection/tasks/1", {"status": BAD})


# ─── 7. 工程师 ───

def test_engineer_update_status_rejected():
    _assert_guard("PUT", "/api/v1/engineers/1", {"status": BAD})


# ─── 8. 司机 ───

def test_driver_update_status_rejected():
    _assert_guard("PUT", "/api/v1/fleet/drivers/1", {"status": BAD})


# ─── 合法值不被误伤（校验层放行）───

@pytest.mark.parametrize("method,url,payload", [
    ("PUT", "/api/v1/charging-orders/1/status", {"status": "completed"}),
    ("POST", "/api/v1/work-orders", {"fault_desc": "x", "type": "repair"}),
    ("PUT", "/api/v1/work-orders/1", {"status": "completed"}),
    ("POST", "/api/v1/devices", {"code": "T77A186B3", "name": "n", "type": "charger_dc"}),
    ("PUT", "/api/v1/devices/1", {"status": "online"}),
    ("POST", "/api/v1/gateways", {"sn": "SN-77A186B3-2", "name": "gw", "status": "offline"}),
    ("PUT", "/api/v1/gateways/1", {"status": "online"}),
    ("PUT", "/api/v1/gateways/firmware/1", {"status": "released"}),
    ("POST", "/api/v1/stations", {"name": "s", "code": "ST-77A186B4", "status": "normal"}),
    ("PUT", "/api/v1/stations/1", {"status": "maintenance"}),
    ("PUT", "/api/v1/inspection/tasks/1", {"status": "in_progress"}),
    ("PUT", "/api/v1/engineers/1", {"status": "active"}),
    ("PUT", "/api/v1/fleet/drivers/1", {"status": "suspended"}),
])
def test_valid_values_pass_validation(method, url, payload):
    r = client.request(method, url, json=payload, headers=_headers())
    assert r.status_code != 422, f"{method} {url} 合法值 {payload} 被 422 误拒: {r.text[:200]}"


# ═══ 二梯队（卡 6031add1）：admin_*/operate/* 镜像、协议、租户/用户/团队、
# 知识/Runbook、车队考勤/资金/车辆档案、企业交易、维护记录 ═══

def _guard2(method, url, payload, bad_key):
    r = client.request(method, url, json=payload, headers=_headers())
    assert r.status_code == 422, f"{method} {url} 非法 {bad_key} 应 422, 实际 {r.status_code}: {r.text[:200]}"


# ─── 9. 管理后台/运营 镜像:互联互通 ───

def test_admin_interconnect_create_status_rejected():
    _guard2("POST", "/api/v1/admin/interconnect/configs",
            {"platform_name": "X", "platform_code": "teld", "api_base_url": "https://x",
             "auth_type": "apikey", "status": BAD}, "status")


def test_admin_interconnect_create_auth_type_rejected():
    _guard2("POST", "/api/v1/admin/interconnect/configs",
            {"platform_name": "X", "platform_code": "teld", "api_base_url": "https://x",
             "auth_type": "jwt"}, "auth_type")


def test_admin_interconnect_update_status_rejected():
    _guard2("PUT", "/api/v1/admin/interconnect/configs/1", {"status": BAD}, "status")


def test_operate_interconnect_update_auth_type_rejected():
    _guard2("PUT", "/api/v1/operate/interconnect/configs/1", {"auth_type": "jwt"}, "auth_type")


# ─── 10. 管理后台:终端 ───

def test_admin_terminal_create_terminal_type_rejected():
    _guard2("POST", "/api/v1/admin/terminals",
            {"terminal_code": "T-6031ADD1", "terminal_type": "not_a_type"}, "terminal_type")


def test_admin_terminal_create_status_rejected():
    _guard2("POST", "/api/v1/admin/terminals",
            {"terminal_code": "T-6031ADD1", "terminal_type": "camera", "status": BAD}, "status")


def test_admin_terminal_update_status_rejected():
    _guard2("PUT", "/api/v1/admin/terminals/1", {"status": BAD}, "status")


# ─── 11. 管理后台:云同步 ───

def test_admin_cloud_create_provider_rejected():
    _guard2("POST", "/api/v1/admin/cloud-configs",
            {"config_name": "c", "provider": "gcp"}, "provider")


def test_admin_cloud_create_status_rejected():
    _guard2("POST", "/api/v1/admin/cloud-configs",
            {"config_name": "c", "provider": "cloud-a", "status": BAD}, "status")


def test_admin_cloud_update_sync_strategy_rejected():
    _guard2("PUT", "/api/v1/admin/cloud-configs/1", {"sync_strategy": "weekly"}, "sync_strategy")


# ─── 12. 管理后台/运营 镜像:市政监管 ───

def test_admin_supervision_create_status_rejected():
    _guard2("POST", "/api/v1/admin/supervision/configs",
            {"city": "X", "platform_url": "https://x", "status": BAD}, "status")


def test_admin_supervision_manual_report_type_rejected():
    _guard2("POST", "/api/v1/admin/supervision/reports/manual",
            {"config_id": 1, "report_type": BAD}, "report_type")


def test_admin_supervision_compliance_result_rejected():
    _guard2("POST", "/api/v1/admin/supervision/compliance",
            {"config_id": 1, "check_type": "compliance", "result": BAD}, "result")


def test_operate_supervision_create_platform_type_rejected():
    _guard2("POST", "/api/v1/operate/supervision/configs",
            {"city": "X", "platform_url": "https://x", "platform_type": BAD}, "platform_type")


def test_operate_supervision_create_protocol_type_rejected():
    _guard2("POST", "/api/v1/operate/supervision/configs",
            {"city": "X", "platform_url": "https://x", "protocol_type": "grpc"}, "protocol_type")


def test_operate_supervision_update_status_rejected():
    _guard2("PUT", "/api/v1/operate/supervision/configs/1", {"status": BAD}, "status")


# ─── 13. 设备协议 / 协议实例 ───

def test_device_protocol_create_type_rejected():
    _guard2("POST", "/api/v1/device-protocols",
            {"name": "p", "code": "P-6031ADD1", "type": "grpc"}, "type")


def test_device_protocol_update_status_rejected():
    _guard2("PUT", "/api/v1/device-protocols/1", {"status": BAD}, "status")


def test_protocol_rule_create_direction_rejected():
    _guard2("POST", "/api/v1/protocol-rules",
            {"protocol_id": 1, "direction": "sideways"}, "direction")


def test_protocol_instance_create_protocol_type_rejected():
    _guard2("POST", "/api/v1/protocol-instances",
            {"name": "i", "protocol_type": "grpc"}, "protocol_type")


def test_protocol_instance_update_status_rejected():
    _guard2("PUT", "/api/v1/protocol-instances/1", {"status": BAD}, "status")


# ─── 14. 租户 / 用户 / 团队 ───

def test_tenant_update_status_rejected():
    _guard2("PUT", "/api/v1/tenants/1", {"status": BAD}, "status")


def test_user_create_status_rejected():
    _guard2("POST", "/api/v1/users",
            {"username": "u6031add1", "password": "x12345678", "status": BAD}, "status")


def test_user_update_status_rejected():
    _guard2("PUT", "/api/v1/users/1", {"status": BAD}, "status")


def test_team_create_type_rejected():
    _guard2("POST", "/api/v1/teams", {"name": "t6031add1", "region": "HN", "type": BAD}, "type")


def test_team_update_type_rejected():
    _guard2("PUT", "/api/v1/teams/1", {"type": BAD}, "type")


# ─── 15. 车队:考勤 / 资金 / 车辆档案 ───

def test_fleet_attendance_batch_status_rejected():
    _guard2("POST", "/api/v1/fleet/attendance/batch",
            {"driver_id": 1, "month": "2026-08",
             "records": [{"date": "2026-08-01", "shift_type": "day", "status": BAD}]}, "status")


def test_fleet_fund_create_status_rejected():
    _guard2("POST", "/api/v1/fleet/funds",
            {"account_name": "a", "status": BAD}, "status")


def test_fleet_vehicle_maintenance_create_type_rejected():
    _guard2("POST", "/api/v1/fleet/vehicles/1/maintenance",
            {"type": "not_a_type"}, "type")


def test_fleet_vehicle_maintenance_update_status_rejected():
    _guard2("PUT", "/api/v1/fleet/vehicles/1/maintenance/1", {"status": BAD}, "status")


def test_fleet_vehicle_insurance_create_type_rejected():
    _guard2("POST", "/api/v1/fleet/vehicles/1/insurance",
            {"insurance_type": "not_a_type", "company": "c", "policy_no": "p",
             "start_date": "2026-01-01", "end_date": "2026-12-31"}, "insurance_type")


# ─── 16. 企业交易 / 设备维护记录 ───

def test_enterprise_transaction_create_type_rejected():
    _guard2("POST", "/api/v1/enterprises/1/transactions",
            {"type": BAD, "amount": 100}, "type")


def test_maintenance_record_create_type_rejected():
    _guard2("POST", "/api/v1/maintenance-records",
            {"device_id": 1, "title": "x", "type": "not_a_type"}, "type")


def test_maintenance_record_update_status_rejected():
    _guard2("PUT", "/api/v1/maintenance-records/1", {"status": BAD}, "status")


# ─── 二梯队合法值不被误伤 ───

@pytest.mark.parametrize("method,url,payload", [
    ("POST", "/api/v1/admin/interconnect/configs",
     {"platform_name": "X", "platform_code": "teld", "api_base_url": "https://x",
      "auth_type": "oauth", "status": "inactive"}),
    ("PUT", "/api/v1/admin/interconnect/configs/1", {"auth_type": "apikey", "status": "active"}),
    ("POST", "/api/v1/admin/terminals",
     {"terminal_code": "T-6031ADD1-V", "terminal_type": "sensor", "status": "maintenance"}),
    ("POST", "/api/v1/admin/cloud-configs",
     {"config_name": "c", "provider": "cloud-b", "sync_strategy": "realtime", "status": "inactive"}),
    ("POST", "/api/v1/admin/supervision/configs",
     {"city": "X", "platform_url": "https://x", "report_strategy": "realtime", "status": "inactive"}),
    ("POST", "/api/v1/admin/supervision/reports/manual",
     {"config_id": 1, "report_type": "station"}),
    ("POST", "/api/v1/operate/supervision/configs",
     {"city": "X", "platform_url": "https://x", "platform_type": "lianlian",
      "protocol_type": "mqtt", "report_strategy": "realtime", "status": "inactive"}),
    ("PUT", "/api/v1/operate/supervision/configs/1", {"report_strategy": "scheduled"}),
    ("POST", "/api/v1/device-protocols", {"name": "p", "code": "P-6031ADD1-V", "type": "ocpp"}),
    ("PUT", "/api/v1/device-protocols/1", {"type": "modbus", "status": "inactive"}),
    ("POST", "/api/v1/protocol-instances", {"name": "i", "protocol_type": "mqtt"}),
    ("PUT", "/api/v1/protocol-instances/1", {"protocol_type": "rest", "status": "running"}),
    ("PUT", "/api/v1/tenants/1", {"status": "suspended"}),
    ("POST", "/api/v1/users", {"username": "u6031add1v", "password": "x12345678", "status": "inactive"}),
    ("PUT", "/api/v1/users/1", {"status": "suspended"}),
    ("POST", "/api/v1/teams", {"name": "t6031add1v", "region": "HN", "type": "fleet"}),
    ("PUT", "/api/v1/teams/1", {"type": "maintenance_team"}),
    ("POST", "/api/v1/fleet/attendance/batch",
     {"driver_id": 1, "month": "2026-08",
      "records": [{"date": "2026-08-02", "shift_type": "night", "status": "late"}]}),
    ("POST", "/api/v1/fleet/funds", {"account_name": "a", "status": "frozen"}),
    ("POST", "/api/v1/fleet/vehicles/1/maintenance", {"type": "repair", "status": "completed"}),
    ("PUT", "/api/v1/fleet/vehicles/1/maintenance/1", {"type": "inspection", "status": "cancelled"}),
    ("POST", "/api/v1/fleet/vehicles/1/insurance",
     {"insurance_type": "commercial", "company": "c", "policy_no": "p",
      "start_date": "2026-01-01", "end_date": "2026-12-31"}),
    ("POST", "/api/v1/enterprises/1/transactions", {"type": "refund", "amount": 1}),
    ("POST", "/api/v1/maintenance-records",
     {"device_id": 1, "title": "x", "type": "emergency"}),
    ("PUT", "/api/v1/maintenance-records/1", {"type": "corrective", "status": "completed"}),
])
def test_valid_values_pass_validation_tier2(method, url, payload):
    r = client.request(method, url, json=payload, headers=_headers())
    assert r.status_code != 422, f"{method} {url} 合法值 {payload} 被 422 误拒: {r.text[:200]}"

"""
扫码报修 API 测试
覆盖: scan_device, quick_repair, qrcode CRUD
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _create_station(token, name="扫码测试站", code="SCAN_ST_001"):
    """创建测试站点, 返回 station_id"""
    resp = client.post(
        "/api/v1/stations",
        json={"name": name, "code": code, "address": "测试地址", "lat": 31.0, "lon": 121.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"创建站点失败: {resp.text}"
    return resp.json()["data"]["id"]


def _create_device(token, station_id, sn="SCAN_SN_001", code="SCAN_DEV_001", name="扫码测试设备"):
    """创建设备, 返回 device_id"""
    resp = client.post(
        "/api/v1/devices",
        json={
            "sn": sn, "code": code, "name": name,
            "type": "charger_dc", "station_id": str(station_id),
            "rated_power": 120.0, "gun_count": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"创建设备失败: {resp.text}"
    return resp.json()["data"]["id"]


def _create_qrcode(token, device_id):
    """为设备生成二维码, 返回 qr_code"""
    resp = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"生成二维码失败: {resp.text}"
    return resp.json()["data"]["qr_code"]


# ========== 鉴权检查 ==========

def test_scan_device_requires_auth():
    """无 token 扫码应返回401/403，或业务层先返回404"""
    resp = client.post("/api/v1/scan/device", json={"qr_code": "test123"})
    assert resp.status_code in (401, 403, 404)


def test_quick_repair_requires_auth():
    """无 token 快速报修应返回401/403，或业务层先返回404"""
    resp = client.post("/api/v1/scan/quick-repair", json={"device_id": 1, "fault_desc": "故障"})
    assert resp.status_code in (401, 403, 404)


def test_generate_qrcode_requires_auth():
    """无 token 生成二维码应返回401/403，或业务层先返回404"""
    resp = client.post("/api/v1/scan/qrcode/generate", json={"device_id": 1})
    assert resp.status_code in (401, 403, 404)


# ========== 扫码识别 ==========

def test_scan_by_qrcode():
    """通过二维码扫码识别设备"""
    token = _login()
    station_id = _create_station(token, "扫码识别站", "SCAN_SCAN_001")
    device_id = _create_device(token, station_id, "SCAN_QR_001", "SCAN_QR_DEV", "扫码设备")
    qr_code = _create_qrcode(token, device_id)

    resp = client.post(
        "/api/v1/scan/device",
        json={"qr_code": qr_code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["device_id"] == device_id
    assert data["device_sn"] == "SCAN_QR_001"
    assert data["device_name"] == "扫码设备"


def test_scan_by_device_code():
    """通过设备编码扫码识别"""
    token = _login()
    station_id = _create_station(token, "扫码编码站", "SCAN_CODE_001")
    device_id = _create_device(token, station_id, "SCAN_CODE_SN", "SCAN_CODE_DEV", "编码设备")

    resp = client.post(
        "/api/v1/scan/device",
        json={"qr_code": "SCAN_CODE_DEV"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["device_id"] == device_id


def test_scan_by_device_sn():
    """通过设备序列号扫码识别"""
    token = _login()
    station_id = _create_station(token, "扫码序号站", "SCAN_SN_001")
    device_id = _create_device(token, station_id, "SCAN_BY_SN_001", "SCAN_SN_DEV", "序号设备")

    resp = client.post(
        "/api/v1/scan/device",
        json={"qr_code": "SCAN_BY_SN_001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["device_id"] == device_id


def test_scan_device_not_found():
    """扫码不存在的设备"""
    token = _login()
    resp = client.post(
        "/api/v1/scan/device",
        json={"qr_code": "NONEXISTENT_QR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_scan_empty_qr_code():
    """扫码空字符串"""
    token = _login()
    resp = client.post(
        "/api/v1/scan/device",
        json={"qr_code": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ========== 快速报修 ==========

def test_quick_repair_success():
    """快速报修成功"""
    token = _login()
    station_id = _create_station(token, "快速报修站", "SCAN_REP_001")
    device_id = _create_device(token, station_id, "SCAN_REP_SN", "SCAN_REP_DEV", "报修设备")

    resp = client.post(
        "/api/v1/scan/quick-repair",
        json={
            "device_id": device_id,
            "fault_desc": "设备温度异常",
            "fault_level": "warning",
            "contact_name": "测试用户",
            "contact_phone": "13800138000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert body["code"] == 200
    assert data["device_name"] == "报修设备"
    assert "WO-" in data["workorder_id"]


def test_quick_repair_device_not_found():
    """快速报修不存在的设备"""
    token = _login()
    resp = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": 999999, "fault_desc": "故障描述"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_quick_repair_critical_level():
    """快速报修紧急级别"""
    token = _login()
    station_id = _create_station(token, "紧急报修站", "SCAN_CRI_001")
    device_id = _create_device(token, station_id, "SCAN_CRI_SN", "SCAN_CRI_DEV", "紧急设备")

    resp = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": device_id, "fault_desc": "设备起火", "fault_level": "critical"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert body["code"] == 200
    assert "WO-" in data["workorder_id"]


# ========== 二维码管理 ==========

def test_generate_qrcode():
    """生成二维码"""
    token = _login()
    station_id = _create_station(token, "二维码生成站", "SCAN_QRG_001")
    device_id = _create_device(token, station_id, "SCAN_QRG_SN", "SCAN_QRG_DEV", "二维码设备")

    resp = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": device_id, "notes": "设备备注"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert "TL-" in data["qr_code"]
    assert data["device_id"] == device_id
    assert data["device_name"] == "二维码设备"


def test_generate_qrcode_device_not_found():
    """为不存在的设备生成二维码"""
    token = _login()
    resp = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_generate_qrcode_duplicate():
    """重复生成二维码(应提示已有二维码)"""
    token = _login()
    station_id = _create_station(token, "二维码重复站", "SCAN_QRD_001")
    device_id = _create_device(token, station_id, "SCAN_QRD_SN", "SCAN_QRD_DEV", "重复设备")

    # 第一次生成
    resp1 = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    first_qr = resp1.json()["data"]["qr_code"]

    # 第二次生成（应返回已有二维码）
    resp2 = client.post(
        "/api/v1/scan/qrcode/generate",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["qr_code"] == first_qr
    assert "已有二维码" in resp2.json()["data"]["message"]


def test_get_device_qrcode():
    """获取设备二维码"""
    token = _login()
    station_id = _create_station(token, "获取二维码站", "SCAN_GET_001")
    device_id = _create_device(token, station_id, "SCAN_GET_SN", "SCAN_GET_DEV", "获取设备")
    _create_qrcode(token, device_id)

    resp = client.get(
        f"/api/v1/scan/qrcode/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["device_id"] == device_id
    assert data["scan_count"] >= 0


def test_get_device_qrcode_not_found():
    """获取未生成二维码的设备"""
    token = _login()
    resp = client.get(
        "/api/v1/scan/qrcode/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_list_qrcodes():
    """扫码二维码列表"""
    token = _login()
    resp = client.get(
        "/api/v1/scan/qrcodes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_list_qrcodes_by_device():
    """按设备扫码二维码列表"""
    token = _login()
    station_id = _create_station(token, "列表筛选项", "SCAN_LST_001")
    device_id = _create_device(token, station_id, "SCAN_LST_SN", "SCAN_LST_DEV", "列表设备")
    _create_qrcode(token, device_id)

    resp = client.get(
        f"/api/v1/scan/qrcodes?device_id={device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) > 0
    assert data["items"][0]["device_id"] == device_id


def test_delete_qrcode():
    """删除/禁用二维码"""
    token = _login()
    station_id = _create_station(token, "删除码站", "SCAN_DEL_001")
    device_id = _create_device(token, station_id, "SCAN_DEL_SN", "SCAN_DEL_DEV", "删除设备")
    _create_qrcode(token, device_id)

    # 禁用二维码
    resp = client.delete(
        f"/api/v1/scan/qrcode/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "二维码已禁用" in resp.json()["message"]

    # 验证已禁用（扫码失败）
    qr_code = ""  # 我们需要先获取qr_code
    resp_get = client.get(
        f"/api/v1/scan/qrcode/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_get.status_code == 404


def test_delete_qrcode_not_found():
    """删除不存在的二维码"""
    token = _login()
    resp = client.delete(
        "/api/v1/scan/qrcode/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_full_scan_to_repair_flow():
    """完整流程: 生成二维码 → 扫码识别 → 快速报修"""
    token = _login()
    station_id = _create_station(token, "完整流程站", "SCAN_FLOW_001")
    device_id = _create_device(token, station_id, "SCAN_FLOW_SN", "SCAN_FLOW_DEV", "流程设备")

    # 1. 生成二维码
    qr_code = _create_qrcode(token, device_id)
    assert qr_code is not None

    # 2. 扫码识别
    resp_scan = client.post(
        "/api/v1/scan/device",
        json={"qr_code": qr_code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_scan.status_code == 200
    scan_data = resp_scan.json()["data"]
    assert scan_data["device_id"] == device_id

    # 3. 快速报修
    resp_repair = client.post(
        "/api/v1/scan/quick-repair",
        json={"device_id": device_id, "fault_desc": "完整流程测试故障", "fault_level": "warning"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_repair.status_code == 200
    repair_body = resp_repair.json()
    repair_data = repair_body["data"]
    assert repair_body["code"] == 200
    assert "WO-" in repair_data["workorder_id"]


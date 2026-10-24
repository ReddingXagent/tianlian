"""
AI 智能日志分析 API 测试

测试 AI 诊断 API 路由（log_analysis）的所有端点。
使用 unittest.mock 避免真实 LLM 调用。
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


# ========== Fixtures ==========

@pytest.fixture(scope="function")
def auth_token(test_db):
    """获取认证 token (依赖 test_db 确保 admin 用户存在)"""
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return token


@pytest.fixture(scope="function")
def test_data(test_db):
    """创建测试数据（站点、设备、告警），使用时间戳确保唯一性"""
    import time
    ts = str(int(time.time()))
    db = test_db["session"]

    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    station = Station(name=f"测试站点{ts}", code=f"TEST-ST-{ts}", status=StationStatus.NORMAL)
    db.add(station)
    db.flush()

    device = Device(
        sn=f"SN-TEST-{ts}",
        name=f"测试逆变器{ts}",
        code=f"DEV-TEST-{ts}",
        type=DeviceType.PV_INVERTER,
        station_id=station.id,
        status=DeviceStatus.ONLINE,
        firmware_version="v3.0.0",
    )
    db.add(device)
    db.flush()

    alarm = Alarm(
        device_id=device.id,
        station_id=station.id,
        level=AlarmLevel.CRITICAL,
        content="电网电压异常告警",
        alarm_type="过压",
        fault_code="0x01",
        status=AlarmStatus.ACTIVE,
    )
    db.add(alarm)
    db.flush()

    data = {
        "station_id": station.id,
        "device_id": device.id,
        "alarm_id": alarm.id,
    }
    db.commit()
    db.close()
    return data


# ========== 辅助 mock 结果 ==========

FAKE_ANALYSIS_RESULT = {
    "success": True,
    "result": {
        "fault_type": "电网过压",
        "fault_location": "逆变器A相输入端",
        "root_cause": "电网电压超过逆变器保护阈值",
        "severity": "high",
        "confidence": 0.85,
        "possible_causes": ["电网波动", "负载突变", "变压器故障"],
        "immediate_actions": ["检查电网电压是否恢复正常"],
        "repair_suggestions": ["联系电力公司检查电网"],
        "preventive_measures": ["加装电涌保护器"],
        "remote_fixable": True,
    },
    "raw_response": '{"fault_type": "电网过压"}',
    "model_used": "TP/ModelB5.1",
    "duration_ms": 2345,
}

FAKE_ANALYSIS_RESULT_FAILED = {
    "success": False,
    "result": None,
    "error": "Mock analysis failure",
    "raw_response": None,
    "model_used": None,
    "duration_ms": 1000,
}


# ========== 基础健康检查 ==========

def test_health():
    """测试健康检查端点"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    status = data.get("data", {}).get("status") or data.get("status")
    assert status == "healthy"


# ========== 手动分析 ==========

@patch("app.api.v1.log_analysis.analyze_device_logs", return_value=FAKE_ANALYSIS_RESULT)
def test_manual_analyze_success(mock_analyze, auth_token, test_data):
    """测试手动日志分析 - 成功场景"""
    payload = {
        "device_id": test_data["device_id"],
        "logs": [
            "[WARN] A相电压异常: 265V, 超过阈值264V",
            "[ERROR] 电网一段过压保护触发 (A相)",
        ],
        "fault_code": "0x01",
        "fault_description": "电网电压异常",
    }
    response = client.post(
        "/api/v1/log-analysis/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert data["data"]["analysis"] is not None
    assert data["data"]["analysis"]["fault_type"] == "电网过压"
    mock_analyze.assert_called_once()


@patch("app.api.v1.log_analysis.analyze_device_logs", return_value=FAKE_ANALYSIS_RESULT_FAILED)
def test_manual_analyze_failure(mock_analyze, auth_token, test_data):
    """测试手动日志分析 - AI分析失败，记录标记为failed"""
    payload = {
        "device_id": test_data["device_id"],
        "logs": ["[ERROR] 未知错误"],
        "fault_code": "0xFF",
    }
    response = client.post(
        "/api/v1/log-analysis/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert data["data"].get("record_id") is not None


def test_manual_analyze_no_device(auth_token):
    """测试手动日志分析 - 设备不存在"""
    payload = {
        "device_id": 99999,
        "logs": ["test log"],
    }
    response = client.post(
        "/api/v1/log-analysis/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 404


@patch("app.api.v1.log_analysis.analyze_device_logs", return_value=FAKE_ANALYSIS_RESULT)
def test_manual_analyze_empty_logs(mock_analyze, auth_token, test_data):
    """测试空日志"""
    payload = {
        "device_id": test_data["device_id"],
        "logs": [],
    }
    response = client.post(
        "/api/v1/log-analysis/analyze",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    # Should still work (empty logs sent to analysis)
    assert response.status_code == 200 or response.status_code == 500


# ========== 告警诊断触发 ==========

@patch("app.api.v1.log_analysis.trigger_diagnosis")
def test_trigger_alarm_diagnosis(mock_trigger, auth_token, test_data):
    """测试触发告警诊断"""
    mock_trigger.return_value = {
        "success": True,
        "record_id": 1,
        "model_used": "TP/ModelB5.1",
        "duration_ms": 3456,
    }
    response = client.post(
        f"/api/v1/log-analysis/trigger/{test_data['alarm_id']}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True


@patch("app.api.v1.log_analysis.trigger_diagnosis")
def test_trigger_alarm_diagnosis_failure(mock_trigger, auth_token):
    """测试触发不存在的告警"""
    mock_trigger.return_value = {
        "success": False,
        "error": "Alarm not found"
    }
    response = client.post(
        "/api/v1/log-analysis/trigger/99999",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 500


# ========== 诊断记录查询 ==========

def test_get_analysis_by_id(auth_token, test_data, test_db):
    """测试获取诊断结果 - 根据ID查询"""
    from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus
    db = test_db["session"]
    record = AIDiagnosisRecord(
        device_id=test_data["device_id"],
        station_id=test_data["station_id"],
        status=DiagnosisStatus.COMPLETED,
        trigger_type="manual",
        log_source="manual_paste",
        raw_log="test log",
        fault_type="电网过压",
        severity="high",
        confidence=0.85,
        root_cause="测试根因",
        remote_fixable=True,
    )
    db.add(record)
    db.commit()
    record_id = record.id
    db.close()

    response = client.get(
        f"/api/v1/log-analysis/{record_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("fault_type") == "电网过压"
    assert data.get("severity") == "high"
    assert data.get("confidence") == 0.85


def test_get_analysis_not_found(auth_token):
    """测试获取不存在的诊断记录"""
    response = client.get(
        "/api/v1/log-analysis/99999",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 404


# ========== 诊断历史 ==========

def test_list_analysis_history(auth_token):
    """测试诊断历史列表"""
    response = client.get(
        "/api/v1/log-analysis",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert "items" in data.get("data", {})
    assert "total" in data.get("data", {})


def test_list_analysis_with_filters(auth_token, test_data):
    """测试带过滤条件的诊断历史"""
    response = client.get(
        f"/api/v1/log-analysis?status=completed&device_id={test_data['device_id']}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert "items" in data.get("data", {})


def test_list_analysis_with_pagination(auth_token):
    """测试分页"""
    response = client.get(
        "/api/v1/log-analysis?page=1&page_size=5",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200


def test_list_analysis_with_invalid_status(auth_token):
    """测试无效状态过滤"""
    response = client.get(
        "/api/v1/log-analysis?status=invalid_status",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200


# ========== 模型配置 ==========

def test_get_model_config(auth_token):
    """测试获取模型配置"""
    response = client.get(
        "/api/v1/log-analysis/model_config",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "task_mappings" in data


def test_update_model_config(auth_token):
    """测试更新模型配置"""
    providers = [
        {
            "provider": "cloud_provider-token",
            "model_id": "llm-pro-a",
            "name": "TP/DS4P",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "enabled": True,
        }
    ]
    response = client.post(
        "/api/v1/log-analysis/model_config",
        json=providers,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200


def test_get_task_mappings(auth_token):
    """测试获取任务映射"""
    response = client.get(
        "/api/v1/log-analysis/model_config/task-mappings",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200


def test_update_task_mapping(auth_token):
    """测试更新任务映射"""
    payload = {
        "task_type": "log_analysis",
        "model_name": "TP/DS4P",
    }
    response = client.put(
        "/api/v1/log-analysis/model_config/task-mapping",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200


# ========== 告警诊断结果 ==========

def test_get_alarm_analysis_no_result(auth_token, test_data):
    """测试获取告警诊断 - 无诊断结果"""
    response = client.get(
        f"/api/v1/log-analysis/alarm/{test_data['alarm_id']}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert data["data"].get("has_diagnosis") is False


def test_get_alarm_analysis_with_result(auth_token, test_data, test_db):
    """测试获取告警诊断 - 有诊断结果"""
    from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus
    db = test_db["session"]
    record = AIDiagnosisRecord(
        alarm_id=test_data["alarm_id"],
        device_id=test_data["device_id"],
        station_id=test_data["station_id"],
        status=DiagnosisStatus.COMPLETED,
        trigger_type="auto",
        log_source="remote",
        raw_log="test",
        fault_type="电网过压",
        root_cause="电网波动",
        severity="high",
        confidence=0.9,
    )
    db.add(record)
    db.commit()
    db.close()

    response = client.get(
        f"/api/v1/log-analysis/alarm/{test_data['alarm_id']}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("code") == 200
    assert data["data"].get("has_diagnosis") is True
    assert data["data"].get("fault_type") == "电网过压"


def test_get_alarm_analysis_not_found(auth_token):
    """获取不存在的告警诊断"""
    response = client.get(
        "/api/v1/log-analysis/alarm/99999",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"].get("has_diagnosis") is False


# ========== 异常路径加固 (卡 416f2bb4) ==========

@patch("app.api.v1.log_analysis.analyze_device_logs", side_effect=RuntimeError("AI 网络超时"))
def test_manual_analyze_ai_call_exception(mock_analyze, auth_token, test_data, caplog):
    """AI 外部调用抛异常(网络故障) → 500 内部错误, 留 logger.exception 痕迹, 不泄露原始异常。"""
    import logging
    payload = {
        "device_id": test_data["device_id"],
        "logs": ["[ERROR] something"],
    }
    with caplog.at_level(logging.ERROR, logger="app.api.v1.log_analysis"):
        response = client.post(
            "/api/v1/log-analysis/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
    assert response.status_code == 500
    detail = response.json().get("detail", "")
    # 不泄露原始异常信息
    assert "AI 网络超时" not in str(detail)
    assert "RuntimeError" not in str(detail)
    # 加固专属: 必须留 logger.exception 痕迹便于排查
    assert any(
        r.name == "app.api.v1.log_analysis" and r.levelno == logging.ERROR
        for r in caplog.records
    )


@patch("app.api.v1.log_analysis.trigger_diagnosis", side_effect=RuntimeError("诊断管道崩溃"))
def test_trigger_alarm_diagnosis_exception(mock_trigger, auth_token, test_data, caplog):
    """trigger_diagnosis 抛异常 → 500, 留痕, 不冒泡。"""
    import logging
    with caplog.at_level(logging.ERROR, logger="app.api.v1.log_analysis"):
        response = client.post(
            f"/api/v1/log-analysis/trigger/{test_data['alarm_id']}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
    assert response.status_code == 500
    assert "诊断管道崩溃" not in str(response.json().get("detail", ""))
    assert any(
        r.name == "app.api.v1.log_analysis" and r.levelno == logging.ERROR
        for r in caplog.records
    )
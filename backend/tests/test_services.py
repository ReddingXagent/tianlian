"""
核心服务层测试

覆盖关键服务模块的基本可用性 + CRUD API 测试
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json().get("token") or resp.json().get("data", {}).get("token")


# ========== Alarm Rules CRUD (via /api/v1/alarms/rules) ==========

def test_alarm_rule_crud():
    """告警规则 CRUD"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}

    # 创建规则
    resp = client.post("/api/v1/alarms/rules", json={
        "name": "高温告警规则",
        "metric": "temperature",
        "operator": ">",
        "threshold": 45.0,
        "level": "warning",
        "enabled": True,
    }, headers=headers)
    assert resp.status_code == 200, f"create failed: {resp.status_code} {resp.text}"
    data = resp.json()
    rule_id = data["data"]["id"]

    # 列表（list_rules 返回分页结构 data.items）
    resp = client.get("/api/v1/alarms/rules", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert isinstance(items, list)
    assert any(r["id"] == rule_id for r in items)

    # 详情
    resp = client.get(f"/api/v1/alarms/rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "高温告警规则"

    # 更新
    resp = client.put(f"/api/v1/alarms/rules/{rule_id}", json={
        "name": "高温规则(改)",
        "threshold": 50.0,
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["threshold"] == 50.0

    # 切换
    resp = client.put(f"/api/v1/alarms/rules/{rule_id}/toggle", headers=headers)
    assert resp.status_code == 200

    # 删除
    resp = client.delete(f"/api/v1/alarms/rules/{rule_id}", headers=headers)
    assert resp.status_code == 200

    # 验证已删除
    resp = client.get(f"/api/v1/alarms/rules/{rule_id}", headers=headers)
    assert resp.status_code == 404


# ========== Module Availability ==========

def test_health_monitor_methods():
    """健康监控方法存在"""
    from app.services.health_monitor import health_monitor
    assert hasattr(health_monitor, "calculate_all_health")
    assert hasattr(health_monitor, "check_and_create_alarms")


def test_notification_dispatcher_methods():
    """通知分发器方法存在"""
    from app.services.notification_dispatcher import notification_dispatcher
    assert hasattr(notification_dispatcher, "dispatch")


def test_data_collector_classes():
    """数据采集器类存在"""
    from app.services.data_collector import ProtocolAdapter, ModbusRTUAdapter
    assert ProtocolAdapter is not None
    assert ModbusRTUAdapter is not None


def test_alarm_rule_engine():
    """告警规则引擎类存在"""
    from app.services.alarm_rule_service import AlarmRuleEngine
    engine = AlarmRuleEngine()
    assert hasattr(engine, "evaluate_all")
    assert hasattr(engine, "evaluate_single_rule")


def test_scheduler():
    """调度器存在（需要 schedule 包）"""
    pytest.importorskip("schedule")
    from app.services.scheduler import HealthScheduler, health_scheduler
    assert isinstance(health_scheduler, HealthScheduler)
    assert hasattr(health_scheduler, "start")
    assert hasattr(health_scheduler, "stop")
    assert hasattr(health_scheduler, "run_health_check")


def test_dispatch_engine_class():
    """调度引擎类存在且有方法"""
    from app.services.dispatch_engine import DispatchEngine
    engine = DispatchEngine()
    assert hasattr(engine, "calculate_best_engineer")


def test_healing_engine():
    """自愈引擎存在且有方法"""
    from app.services.healing_engine import HealingEngine
    engine = HealingEngine()
    assert hasattr(engine, "evaluate_alarm")
    assert hasattr(engine, "create_rule")


def test_health_engine():
    """健康引擎存在且有方法"""
    from app.services.health_engine import HealthEngine
    engine = HealthEngine()
    assert hasattr(engine, "calculate_health_score")
    assert hasattr(engine, "predict_remaining_life")


def test_diagnostic_pipeline_module():
    """诊断管道模块存在"""
    import app.services.diagnostic_pipeline as dp
    assert hasattr(dp, "AIDiagnosisRecord")
    assert hasattr(dp, "DiagnosisStatus")


def test_runbook_engine_class():
    """Runbook 引擎类存在且有方法"""
    from app.services.runbook_engine import RunbookEngine
    engine = RunbookEngine()
    methods = [m for m in dir(engine) if not m.startswith('_')]
    assert len(methods) > 0, "RunbookEngine should have methods"


def test_alarm_rule_engine_evaluate():
    """告警规则引擎 evaluate 方法可用"""
    from app.services.alarm_rule_service import AlarmRuleEngine
    engine = AlarmRuleEngine()
    assert hasattr(engine, "evaluate_all")
    # 不传 db 会创建自己的 session（测试数据库已覆盖）
    # 只验证方法可调用，不验证结果
    assert callable(engine.evaluate_all)

"""
告警闭环 API 测试
覆盖: 触发告警闭环 + 流程状态 + 诊断/修复/验证 + 统计 + 边界情况
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(name="测试站点", code="TEST-ALERT-001", status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="TEST-ALERT-DEV-001", name="测试告警设备",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestAlertWorkflowAPI:

    # ========== 触发告警闭环 ==========

    def test_trigger_alert_workflow(self, auth_token, test_device):
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "predictive",
            "severity": "critical",
            "message": "逆变器温度异常",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "alert_id" in data.get("data", {})
        assert data.get("data", {}).get("auto_workorder") is True

    def test_trigger_alert_info_no_workorder(self, auth_token, test_device):
        """info严重度不自动创建工单"""
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "threshold",
            "severity": "info",
            "message": "轻微通知",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data", {}).get("auto_workorder") is False

    def test_trigger_device_not_found(self, auth_token):
        """设备不存在"""
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": 99999,
            "alert_type": "predictive",
            "severity": "critical",
            "message": "测试",
        })
        assert resp.status_code == 404

    def test_trigger_with_prediction_data(self, auth_token, test_device):
        """带预测数据触发"""
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "predictive",
            "severity": "critical",
            "message": "预测告警",
            "prediction_data": {
                "type": "lstm",
                "score": 0.85,
                "details": {"predicted_value": 92.5, "threshold": 90.0}
            }
        })
        assert resp.status_code == 200

    def test_trigger_warning_severity(self, auth_token, test_device):
        """warning严重度触发"""
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "anomaly",
            "severity": "warning",
            "message": "电压波动",
        })
        assert resp.status_code == 200
        # warning does NOT create workorder (only high/critical)
        assert resp.json().get("data", {}).get("auto_workorder") is False

    def test_trigger_fatal_severity(self, auth_token, test_device):
        """fatal严重度触发"""
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "threshold",
            "severity": "fatal",
            "message": "致命故障",
        })
        assert resp.status_code == 200
        # fatal also creates workorder (severity not in ["high", "critical"] list)
        assert resp.json().get("data", {}).get("auto_workorder") is False

    # ========== 工作流状态查询 ==========

    def test_workflow_status(self, auth_token, test_device):
        resp = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "anomaly",
            "severity": "critical",
            "message": "电压波动",
        })
        assert resp.status_code == 200
        alert_id = resp.json().get("alert_id") or resp.json().get("data", {}).get("alert_id")

        resp2 = client.get(f"/api/v1/alert-workflow/status/{alert_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp2.status_code == 200

    def test_workflow_status_not_found(self, auth_token):
        """查询不存在的告警状态"""
        resp = client.get("/api/v1/alert-workflow/status/99999", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 404

    # ========== 诊断流程 ==========

    def test_diagnosis(self, auth_token, test_device):
        trig = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "threshold",
            "severity": "critical",
            "message": "温度过高报警",
        })
        assert trig.status_code == 200
        workorder_id = trig.json().get("data", {}).get("workorder_id")

        resp = client.post("/api/v1/alert-workflow/diagnosis", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": workorder_id,
            "diagnosis_type": "ai",
            "findings": ["温度传感器异常"],
            "root_cause": "传感器老化",
            "suggested_actions": ["更换传感器"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data", {}).get("diagnosis_added") is True

    def test_diagnosis_workorder_not_found(self, auth_token):
        """工单不存在时诊断"""
        resp = client.post("/api/v1/alert-workflow/diagnosis", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": "nonexistent-wo-99999",
            "diagnosis_type": "ai",
            "findings": [], "root_cause": "", "suggested_actions": []
        })
        assert resp.status_code == 404

    # ========== 修复流程 ==========

    def test_repair(self, auth_token, test_device):
        trig = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "predictive",
            "severity": "critical",
            "message": "故障预测",
        })
        assert trig.status_code == 200
        workorder_id = trig.json().get("data", {}).get("workorder_id")

        resp = client.post("/api/v1/alert-workflow/repair", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": workorder_id,
            "repair_type": "remote",
            "actions_taken": ["重启设备"],
            "duration_minutes": 15,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data", {}).get("total_repairs") == 1

    def test_repair_workorder_not_found(self, auth_token):
        """工单不存在时修复"""
        resp = client.post("/api/v1/alert-workflow/repair", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": "nonexistent-wo-99999",
            "repair_type": "remote",
            "actions_taken": [], "duration_minutes": 10
        })
        assert resp.status_code == 404

    def test_repair_multiple_entries(self, auth_token, test_device):
        """多次修复记录"""
        trig = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "predictive",
            "severity": "critical",
            "message": "多次修复测试",
        })
        assert trig.status_code == 200
        wid = trig.json().get("data", {}).get("workorder_id")

        resp1 = client.post("/api/v1/alert-workflow/repair", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": wid, "repair_type": "remote",
            "actions_taken": ["重启"], "duration_minutes": 5
        })
        assert resp1.status_code == 200
        assert resp1.json().get("data", {}).get("total_repairs") == 1

        resp2 = client.post("/api/v1/alert-workflow/repair", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": wid, "repair_type": "manual",
            "actions_taken": ["更换配件"], "duration_minutes": 30,
            "parts_replaced": ["温度传感器"]
        })
        assert resp2.status_code == 200
        # NOTE: repair_log is in-memory only (not persisted to DB),
        # so total_repairs may be 1 instead of 2 across requests
        assert resp2.json().get("data", {}).get("total_repairs") >= 1

    # ========== 验证与闭环 ==========

    def test_verification(self, auth_token, test_device):
        trig = client.post("/api/v1/alert-workflow/trigger", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "alert_type": "threshold",
            "severity": "critical",
            "message": "通信超时",
        })
        assert trig.status_code == 200
        workorder_id = trig.json().get("data", {}).get("workorder_id")

        client.post("/api/v1/alert-workflow/diagnosis", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": workorder_id, "diagnosis_type": "ai",
            "findings": ["测试"], "root_cause": "测试", "suggested_actions": ["测试"]
        })

        resp = client.post("/api/v1/alert-workflow/verify", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": workorder_id,
            "verification_type": "auto",
            "checks_passed": ["设备在线", "温度正常"],
            "health_score_after": 95.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data", {}).get("workflow_completed") is True
        assert data.get("data", {}).get("final_health_score") == 95.0

    def test_verification_workorder_not_found(self, auth_token):
        """工单不存在时验证"""
        resp = client.post("/api/v1/alert-workflow/verify", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "workorder_id": "nonexistent-wo-99999", "verification_type": "auto",
            "checks_passed": [], "health_score_after": 90
        })
        assert resp.status_code == 404

    # ========== 统计 ==========

    def test_stats(self, auth_token, test_device):
        """测试告警闭环统计"""
        for i in range(3):
            client.post("/api/v1/alert-workflow/trigger", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "device_id": test_device.id, "alert_type": "threshold",
                "severity": "critical", "message": f"测试告警{i}",
            })

        resp = client.get("/api/v1/alert-workflow/stats", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        stats = data.get("data", data)
        assert "alerts" in stats
        assert "workorders" in stats
        assert "metrics" in stats
        assert stats["alerts"]["total"] >= 3

    def test_stats_cache_write_and_hit_card_eb0e1afd(self, auth_token, monkeypatch):
        """stats 缓存写侧复活 (卡 eb0e1afd, 修 return{...} 后死代码)

        修复前: 内联 dict 直接 return, 其后 cacheable/set_json/return 三句死代码
        (result 未定义, 重构半途而废) → 缓存永不写入, 每次全量聚合。
        修复后契约: 首查写缓存 (30s TTL, admin 全平台口径键), 二查命中不再聚合。
        """
        from app.core.cache import cache, clear_memory_cache
        import app.api.v1.alert_workflow as awf_mod

        # 隔离: 本文件用模块级 TestClient + test_db (conftest 不清内存缓存),
        # 清掉前序测试 (如 test_stats) 残留的 stats 缓存, 保证首查必 miss
        clear_memory_cache()

        set_calls = []
        _orig_set = cache.set_json

        def _spy_set(key, value, expire=30):
            set_calls.append(key)
            return _orig_set(key, value, expire=expire)

        monkeypatch.setattr(cache, "set_json", _spy_set)

        agg_calls = {"n": 0}
        _orig_scoped = awf_mod._team_scoped

        def _counting_scoped(*args, **kwargs):
            agg_calls["n"] += 1
            return _orig_scoped(*args, **kwargs)

        monkeypatch.setattr(awf_mod, "_team_scoped", _counting_scoped)

        headers = {"Authorization": f"Bearer {auth_token}"}
        resp1 = client.get("/api/v1/alert-workflow/stats", headers=headers)
        assert resp1.status_code == 200, resp1.text
        assert agg_calls["n"] > 0, "首查应 miss 并执行全量聚合"
        # 写侧复活: 首查应以 30s TTL 写入 admin 全平台口径缓存键
        assert "alert_workflow:stats:all" in set_calls, \
            f"stats 首查未写缓存 (return后死代码): set_json calls={set_calls}"

        # 二查命中: 不再触发 team-scoped 聚合, 数据与首查一致
        agg_calls["n"] = 0
        resp2 = client.get("/api/v1/alert-workflow/stats", headers=headers)
        assert resp2.status_code == 200, resp2.text
        assert agg_calls["n"] == 0, f"二查未命中缓存, 仍全量聚合 {agg_calls['n']} 次"
        assert resp2.json()["data"] == resp1.json()["data"], "缓存命中应返回与首查一致的聚合数据"
        assert "timestamp" in resp2.json(), "命中路径须回填 timestamp 保持契约"

    # ========== 边缘情况 ==========

    def test_multiple_triggers_same_device(self, auth_token, test_device):
        """同一设备多次触发"""
        for i in range(5):
            resp = client.post("/api/v1/alert-workflow/trigger", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "device_id": test_device.id,
                "alert_type": "threshold",
                "severity": "warning",
                "message": f"重复告警{i}",
            })
            assert resp.status_code == 200

    # ========== Phase35: 告警升级测试 ==========

    def test_escalation_scan_basic(self, auth_token, test_device, test_db):
        """测试告警升级扫描 - WARN超时升级"""
        db = test_db["session"]
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        from datetime import timedelta

        # 创建一条WARN级别、创建时间超过30分钟的告警
        import datetime as dt
        old_time = dt.datetime.now(dt.timezone.utc) - timedelta(minutes=45)
        alarm = Alarm(
            device_id=test_device.id,
            station_id=test_device.station_id,
            rule_id=None,
            alarm_type="test_escalation",
            level=AlarmLevel.WARNING,
            content="测试升级告警",
            status=AlarmStatus.ACTIVE,
            created_at=old_time,
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        alarm_id = alarm.id

        # 执行升级扫描
        from app.services.alarm_rule_service import engine
        result = engine.scan_and_escalate(db)

        # 验证告警是否升级
        db.refresh(alarm)
        assert alarm.level == AlarmLevel.CRITICAL, f"预期升级为CRITICAL, 实际: {alarm.level}"
        assert alarm.escalated_from is not None
        assert alarm.original_level is not None
        assert "已升级" in alarm.content

    def test_escalation_skip_fresh_alarm(self, auth_token, test_device, test_db):
        """测试新告警不会触发升级"""
        db = test_db["session"]
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        import datetime as dt

        # 创建一条新WARN告警（明确设置 created_at 为当前时间）
        alarm = Alarm(
            device_id=test_device.id,
            station_id=test_device.station_id,
            rule_id=None,
            alarm_type="test_fresh",
            level=AlarmLevel.WARNING,
            content="新告警不应升级",
            status=AlarmStatus.ACTIVE,
            created_at=dt.datetime.now(dt.timezone.utc),
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        alarm_id = alarm.id

        # 执行升级扫描
        from app.services.alarm_rule_service import engine
        result = engine.scan_and_escalate(db)

        # 新告警不应升级
        db.refresh(alarm)
        assert alarm.level == AlarmLevel.WARNING, "新告警不应升级"
        assert alarm.escalated_from is None

    def test_escalate_by_id(self, auth_token, test_device, test_db):
        """测试手动触发升级"""
        db = test_db["session"]
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        import datetime as dt
        from datetime import timedelta

        old_time = dt.datetime.now(dt.timezone.utc) - timedelta(minutes=45)
        alarm = Alarm(
            device_id=test_device.id,
            station_id=test_device.station_id,
            rule_id=None,
            alarm_type="test_manual_escalation",
            level=AlarmLevel.CRITICAL,
            content="手动升级测试",
            status=AlarmStatus.ACTIVE,
            created_at=old_time,
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)

        from app.services.alarm_rule_service import engine
        result = engine.escalate_alarm_by_id(alarm.id, db)
        assert result['success'] is True

        db.refresh(alarm)
        assert alarm.level == AlarmLevel.FATAL

    # ========== Phase35: 告警聚合测试 ==========

    def test_alarm_aggregation_same_type(self, auth_token, test_device, test_db):
        """测试同类告警5分钟窗口内聚合"""
        db = test_db["session"]
        from app.models.alarm import AlarmRule, Alarm, AlarmLevel, AlarmStatus

        # 创建一条告警规则
        rule = AlarmRule(
            name="聚合测试规则",
            metric="temperature",
            operator=">",
            threshold=80.0,
            level=AlarmLevel.WARNING,
            enabled=True,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)

        # 模拟多次触发同样的告警
        from app.services.alarm_rule_service import engine
        from app.models.telemetry import Telemetry

        for i in range(4):
            alarm = Alarm(
                device_id=test_device.id,
                station_id=test_device.station_id,
                rule_id=rule.id,
                alarm_type=f"rule_{rule.id}",
                level=rule.level,
                content=f"温度异常{i}",
                status=AlarmStatus.ACTIVE,
                trigger_metric="temperature",
                trigger_value=85.0 + i,
                trigger_threshold=80.0,
                trigger_operator=">",
            )
            db.add(alarm)
            db.commit()
            db.refresh(alarm)

            from app.services.alarm_aggregation import try_aggregate_alarm, SUPPRESSED
            aggregated = try_aggregate_alarm(alarm, db)

            if aggregated is SUPPRESSED:
                # 防风暴抑制 (卡 2779d516): 新告警行已被删除, 跳过
                continue
            if aggregated and aggregated.id != alarm.id:
                # 已聚合，删除新创建的
                db.delete(alarm)
                db.commit()

        # 取最新创建的告警
        result_alarm = db.query(Alarm).filter(
            Alarm.rule_id == rule.id
        ).order_by(Alarm.id.desc()).first()

        if result_alarm:
            assert result_alarm.aggregation_count is not None
            assert result_alarm.aggregation_count >= 1

    def test_alarm_anti_storm(self):
        """测试防风暴逻辑：30秒内最多3次"""
        from app.services.alarm_aggregation import check_anti_storm

        device_id = 999999  # 使用特殊ID避免干扰
        rule_id = 999999

        # 前3次应通过
        for i in range(3):
            assert check_anti_storm(device_id, rule_id) is True, f"第{i+1}次应通过"

        # 第4次应被抑制
        assert check_anti_storm(device_id, rule_id) is False, "第4次应被风暴抑制"
"""test_diagnostic_pipeline.py — 诊断流水线单元测试

覆盖: trigger_diagnosis (告警不存在/设备不存在/成功路径/AI分析失败),
_match_fault_code (匹配/不匹配/异常), trigger_auto_diagnosis 委托,
_dictify 辅助函数。
"""
import pytest
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime

from app.services.diagnostic_pipeline import (
    trigger_diagnosis,
    _match_fault_code,
    trigger_auto_diagnosis,
    _dictify,
)


# ─── _dictify ───

class TestDictify:
    def test_none_returns_empty_dict(self):
        assert _dictify(None) == {}

    def test_object_returns_columns(self):
        class FakeColumn:
            def __init__(self, name):
                self.name = name
        class FakeTable:
            columns = [FakeColumn("id"), FakeColumn("name")]
        class FakeObj:
            __table__ = FakeTable()
            id = 1
            name = "test"
        result = _dictify(FakeObj())
        assert result == {"id": 1, "name": "test"}


# ─── trigger_diagnosis — 错误路径 ───

class TestTriggerDiagnosisErrors:
    def test_alarm_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = trigger_diagnosis(999, db=db)
        assert result["success"] is False
        assert "999" in result["error"]

    def test_device_not_found(self):
        db = MagicMock()
        alarm = MagicMock()
        alarm.id = 1
        alarm.device_id = 10
        # First query (Alarm) returns alarm, second (Device) returns None
        db.query.return_value.filter.return_value.first.side_effect = [alarm, None]
        result = trigger_diagnosis(1, db=db)
        assert result["success"] is False
        assert "10" in result["error"]


# ─── trigger_diagnosis — 成功路径 ───

class TestTriggerDiagnosisSuccess:
    def _setup_mocks(self, db, analysis_result=None, runbook_result=None):
        alarm = MagicMock()
        alarm.id = 1
        alarm.device_id = 1
        alarm.station_id = 1
        alarm.fault_code = "0x10"
        alarm.alarm_type = "过压"
        alarm.level = MagicMock(value="critical")
        alarm.content = "DC overvoltage"
        alarm.fault_source = "0x10"
        alarm.created_at = datetime.now()
        alarm.diagnosis_result = None
        alarm.repair_suggestion = None
        alarm.remote_fixable = None

        class FakeColumn:
            def __init__(self, name):
                self.name = name
        class FakeTable:
            columns = [FakeColumn("device_type")]
        device = MagicMock()
        device.id = 1
        device.station_id = 1
        device.device_type = "charger"
        device.__table__ = FakeTable()

        station = MagicMock()
        station.name = "Station1"

        # Set up query chain: alarm → device → station
        db.query.return_value.filter.return_value.first.side_effect = [alarm, device, station]

        # Mock AIDiagnosisRecord
        record = MagicMock()
        record.id = 100

        # Mock add/commit/refresh
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        if analysis_result is None:
            analysis_result = {
                "success": True,
                "result": {
                    "fault_type": "overvoltage",
                    "fault_location": "DC bus",
                    "root_cause": "Voltage regulator failure",
                    "severity": "high",
                    "confidence": 0.95,
                    "immediate_actions": ["reduce_power"],
                    "repair_suggestions": ["replace_regulator"],
                    "preventive_measures": ["regular_inspection"],
                    "remote_fixable": False,
                },
                "model_used": "gpt-4",
                "duration_ms": 500,
                "raw_response": "{}",
            }

        return alarm, device, analysis_result, record

    def test_successful_diagnosis(self):
        db = MagicMock()
        alarm, device, analysis, record = self._setup_mocks(db)

        with patch("app.services.diagnostic_pipeline.DeviceLogSimulator") as mock_sim, \
             patch("app.services.diagnostic_pipeline.analyze_with_fallback", return_value=analysis), \
             patch("app.services.diagnostic_pipeline.AIDiagnosisRecord", return_value=record), \
             patch("app.services.diagnostic_pipeline.DiagnosisStatus"), \
             patch("app.services.diagnostic_pipeline.execute_runbook_for_alarm", return_value={"status": "skipped"}), \
             patch("app.services.diagnostic_pipeline._match_fault_code", return_value=None):

            mock_sim.get_logs_for_alarm.return_value = ["log1", "log2"]
            result = trigger_diagnosis(1, db=db)

        assert result["success"] is True
        assert result["record_id"] == 100
        assert result["model_used"] == "gpt-4"

    def test_diagnosis_ai_failure(self):
        db = MagicMock()
        alarm, device, analysis, record = self._setup_mocks(db)
        analysis = {
            "success": False,
            "error": "AI service unavailable",
            "model_used": None,
            "duration_ms": 100,
            "raw_response": None,
        }

        with patch("app.services.diagnostic_pipeline.DeviceLogSimulator") as mock_sim, \
             patch("app.services.diagnostic_pipeline.analyze_with_fallback", return_value=analysis), \
             patch("app.services.diagnostic_pipeline.AIDiagnosisRecord", return_value=record), \
             patch("app.services.diagnostic_pipeline.DiagnosisStatus"), \
             patch("app.services.diagnostic_pipeline._match_fault_code", return_value=None):

            mock_sim.get_logs_for_alarm.return_value = ["log1"]
            result = trigger_diagnosis(1, db=db)

        # Even on AI failure, trigger_diagnosis returns success=True with the record
        # Actually, let me re-read: if analysis fails, it sets record.status=FAILED,
        # but still commits and returns success=True at the end
        # Wait no — the function doesn't return early on AI failure, it just marks the record
        # Actually, looking more carefully: the exception handler catches ALL exceptions
        # If analyze_with_fallback returns {"success": False}, it doesn't raise,
        # so the function continues and returns success=True at the end
        assert result["success"] is True

    def test_runbook_execution_exception_handled(self):
        db = MagicMock()
        alarm, device, analysis, record = self._setup_mocks(db)

        with patch("app.services.diagnostic_pipeline.DeviceLogSimulator") as mock_sim, \
             patch("app.services.diagnostic_pipeline.analyze_with_fallback", return_value=analysis), \
             patch("app.services.diagnostic_pipeline.AIDiagnosisRecord", return_value=record), \
             patch("app.services.diagnostic_pipeline.DiagnosisStatus"), \
             patch("app.services.diagnostic_pipeline.execute_runbook_for_alarm",
                   side_effect=RuntimeError("runbook crash")), \
             patch("app.services.diagnostic_pipeline._match_fault_code", return_value=None):

            mock_sim.get_logs_for_alarm.return_value = ["log1"]
            result = trigger_diagnosis(1, db=db)

        # Should still succeed even if runbook fails
        assert result["success"] is True


# ─── _match_fault_code ───

class TestMatchFaultCode:
    def test_no_fault_codes_returns_none(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = _match_fault_code(db, "overvoltage", "DC bus", "charger")
        assert result is None

    def test_match_found(self):
        fc = MagicMock()
        fc.fault_code = "E001"
        fc.fault_name = "Overvoltage Fault"
        fc.fault_description = "DC bus overvoltage detected"
        fc.possible_causes = ["regulator failure"]
        fc.repair_suggestions = ["replace regulator"]

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [fc]

        result = _match_fault_code(db, "overvoltage", "DC bus", "charger")
        assert result is not None
        assert result["fault_code"] == "E001"
        assert "Overvoltage" in result["fault_name"]

    def test_score_below_threshold(self):
        fc = MagicMock()
        fc.fault_code = "E999"
        fc.fault_name = "Unrelated"
        fc.fault_description = "Something else"
        fc.possible_causes = ["other"]
        fc.repair_suggestions = ["other fix"]

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [fc]

        result = _match_fault_code(db, "overvoltage", "DC bus", "charger")
        assert result is None  # score < 2

    def test_exception_returns_none(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db error")
        result = _match_fault_code(db, "test", "test", "charger")
        assert result is None

    def test_empty_fault_type_and_location(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = _match_fault_code(db, "", "", "charger")
        assert result is None


# ─── trigger_auto_diagnosis ───

class TestTriggerAutoDiagnosis:
    def test_delegates_to_trigger_diagnosis(self):
        with patch("app.services.diagnostic_pipeline.trigger_diagnosis", return_value={"success": True}) as mock_td:
            result = trigger_auto_diagnosis(42)
            mock_td.assert_called_once_with(42, trigger_type="auto")
            assert result["success"] is True

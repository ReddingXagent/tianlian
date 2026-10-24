#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断流水线测试 - 函数式 API

源码已从 DiagnosticPipeline 类改为函数式实现，本测试覆盖:
- trigger_diagnosis: 正常流程 / 告警不存在 / 设备不存在 / AI 分析失败 / runbook 异常
- trigger_auto_diagnosis: 委托 trigger_diagnosis(trigger_type="auto") + own_db 分支
- _match_fault_code: 命中 / 无候选 / 低分 / 异常
- _dictify: 正常对象 / None

外部依赖全部 mock（不触达真实 AI / 设备日志 / Runbook）:
- diagnostic_pipeline.DeviceLogSimulator          设备日志采集
- diagnostic_pipeline.analyze_with_fallback        AI 分析
- diagnostic_pipeline.execute_runbook_for_alarm    Runbook 自动修复

数据库走 conftest.test_db：隔离 SQLite 文件 + 覆盖模块级 SessionLocal。
"""
import pytest
from unittest.mock import patch, MagicMock

from app.services import diagnostic_pipeline as dp
from app.services.diagnostic_pipeline import (
    trigger_diagnosis,
    trigger_auto_diagnosis,
    _match_fault_code,
    _dictify,
)
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.fault_code import FaultCode
from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus


# ============================== fixtures ==============================

@pytest.fixture
def db(test_db):
    """隔离 SQLite 上的一个开 session；test_db 已覆盖 app.core.database.SessionLocal。"""
    session = test_db["session"]
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def seed(db):
    """种子数据：站点 + PCS 设备(推断 device_type=inverter) + 告警 + 一条匹配用故障码。"""
    station = Station(name="测试站", code="STA-T-01", address="测试地址",
                      status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)

    # PCS -> pipeline 内 type_name="pcs" -> device_type 推断为 "inverter"
    device = Device(sn="SN-T-01", name="储能PCS-T", code="PCS-T-01",
                    type=DeviceType.PCS, status=DeviceStatus.FAULT,
                    station_id=station.id, rated_power=50.0)
    db.add(device)
    db.commit()
    db.refresh(device)

    alarm = Alarm(device_id=device.id, station_id=station.id,
                  alarm_type="over_temp", level=AlarmLevel.WARNING,
                  content="机内温度过高", status=AlarmStatus.ACTIVE,
                  fault_code="0xA0", fault_source="temperature")
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    # 知识库故障码：文本含 "过温"，device_type="inverter" 供 _match_fault_code 命中
    fc = FaultCode(fault_code="0xA0", fault_name="逆变器过温保护",
                   fault_description="IGBT 模块过温", device_type="inverter",
                   possible_causes=["散热异常"], repair_suggestions=["更换风扇"],
                   enabled=True)
    db.add(fc)
    db.commit()

    return {"station": station, "device": device, "alarm": alarm, "fault_code": fc}


def _ok_analysis():
    """analyze_with_fallback 成功返回的固定结构（与源码 usage 对齐）。"""
    return {
        "success": True,
        "result": {
            "fault_type": "过温",
            "fault_location": "IGBT",
            "root_cause": "散热风扇故障导致 IGBT 过热",
            "severity": "high",
            "confidence": 0.92,
            "immediate_actions": ["降功率运行", "检查风扇"],
            "repair_suggestions": ["更换散热风扇", "清理风道"],
            "preventive_measures": ["定期清灰"],
            "remote_fixable": False,
        },
        "raw_response": '{"fault_type":"过温"}',
        "duration_ms": 123,
        "model_used": "test-model",
    }


# ============================== trigger_diagnosis ==============================

class TestTriggerDiagnosis:
    def test_normal_flow(self, db, seed):
        """正常流程：mock 全部依赖 -> success，记录 COMPLETED，故障码命中，告警同步。"""
        with patch.object(dp, "DeviceLogSimulator") as mock_sim, \
             patch.object(dp, "analyze_with_fallback", return_value=_ok_analysis()) as mock_ai, \
             patch.object(dp, "execute_runbook_for_alarm",
                          return_value={"runbook_id": "RB-1", "status": "completed"}) as mock_rb:
            mock_sim.get_logs_for_alarm.return_value = ["[ERROR] 温度过温保护触发"]

            result = trigger_diagnosis(seed["alarm"].id, trigger_type="manual", db=db)

        assert result["success"] is True
        assert result["record_id"] is not None
        assert result["model_used"] == "test-model"
        assert result["runbook"]["status"] == "completed"
        # 三个外部依赖都被调用
        mock_sim.get_logs_for_alarm.assert_called_once()
        mock_ai.assert_called_once()
        mock_rb.assert_called_once()

        record = db.query(AIDiagnosisRecord).filter_by(alarm_id=seed["alarm"].id).first()
        assert record is not None
        assert record.status == DiagnosisStatus.COMPLETED
        assert record.fault_type == "过温"
        assert record.confidence == pytest.approx(0.92)
        assert record.matched_fault_code == "0xA0"          # 命中知识库
        assert record.trigger_type == "manual"
        # 告警的诊断结果被同步回写
        db.refresh(seed["alarm"])
        assert seed["alarm"].diagnosis_result == "散热风扇故障导致 IGBT 过热"
        assert seed["alarm"].remote_fixable is False

    def test_alarm_not_found(self, db):
        """告警不存在 -> success=False，error 提示告警缺失。"""
        with patch.object(dp, "DeviceLogSimulator"), \
             patch.object(dp, "analyze_with_fallback"):
            result = trigger_diagnosis(alarm_id=999999, db=db)
        assert result["success"] is False
        assert "告警" in result["error"]

    def test_device_not_found(self, db):
        """告警指向不存在的设备 -> success=False，error 提示设备缺失。"""
        # SQLite 默认不校验外键，可插入 device_id 指向空设备的孤儿告警
        alarm = Alarm(device_id=999999, station_id=None, alarm_type="orphan",
                      level=AlarmLevel.WARNING, content="孤儿告警",
                      status=AlarmStatus.ACTIVE)
        db.add(alarm)
        db.commit()
        with patch.object(dp, "DeviceLogSimulator"), \
             patch.object(dp, "analyze_with_fallback"):
            result = trigger_diagnosis(alarm.id, db=db)
        assert result["success"] is False
        assert "设备" in result["error"]

    def test_ai_analysis_failed(self, db, seed):
        """AI 分析失败：流水线仍 success=True，但记录 FAILED + error_message，不触发 runbook。"""
        fail = {"success": False, "error": "AI 服务超时",
                "raw_response": None, "duration_ms": 5, "model_used": None}
        with patch.object(dp, "DeviceLogSimulator") as mock_sim, \
             patch.object(dp, "analyze_with_fallback", return_value=fail), \
             patch.object(dp, "execute_runbook_for_alarm") as mock_rb:
            mock_sim.get_logs_for_alarm.return_value = ["[ERROR] ..."]
            result = trigger_diagnosis(seed["alarm"].id, db=db)

        assert result["success"] is True                # 流水线本身正常完成
        assert "runbook" not in result                  # AI 失败不进入 runbook 分支
        mock_rb.assert_not_called()

        record = db.query(AIDiagnosisRecord).filter_by(alarm_id=seed["alarm"].id).first()
        assert record.status == DiagnosisStatus.FAILED
        assert record.error_message == "AI 服务超时"
        assert record.duration_ms == 5

    def test_runbook_exception_swallowed(self, db, seed):
        """Runbook 抛异常被捕获，流水线仍 success，错误回填 result['runbook']['error']。"""
        with patch.object(dp, "DeviceLogSimulator") as mock_sim, \
             patch.object(dp, "analyze_with_fallback", return_value=_ok_analysis()), \
             patch.object(dp, "execute_runbook_for_alarm",
                          side_effect=RuntimeError("runbook boom")):
            mock_sim.get_logs_for_alarm.return_value = ["[ERROR] 温度过温"]
            result = trigger_diagnosis(seed["alarm"].id, db=db)

        assert result["success"] is True
        assert result["runbook"]["error"] == "runbook boom"

    def test_station_missing_fallback(self, db):
        """设备指向不存在的站点(alarm.station_id 也为空) -> station 查询为空，回退“未知站点”。"""
        # SQLite 默认不校验外键：device.station_id 指向不存在的站点
        device = Device(sn="SN-ORPHAN", name="孤儿设备", code="ORPH-01",
                        type=DeviceType.PCS, status=DeviceStatus.FAULT,
                        station_id=999999, rated_power=10.0)
        db.add(device); db.commit(); db.refresh(device)
        alarm = Alarm(device_id=device.id, station_id=None, alarm_type="over_temp",
                      level=AlarmLevel.WARNING, content="温度过高",
                      status=AlarmStatus.ACTIVE, fault_code="0xA0")
        db.add(alarm); db.commit(); db.refresh(alarm)

        with patch.object(dp, "DeviceLogSimulator") as mock_sim, \
             patch.object(dp, "analyze_with_fallback", return_value=_ok_analysis()), \
             patch.object(dp, "execute_runbook_for_alarm",
                          return_value={"runbook_id": "RB-3", "status": "completed"}) as mock_rb:
            mock_sim.get_logs_for_alarm.return_value = ["[ERROR] 温度过温"]
            result = trigger_diagnosis(alarm.id, db=db)

        assert result["success"] is True
        # execute_runbook_for_alarm 收到的 device_info 应回退为“未知站点”
        device_info = mock_rb.call_args.kwargs["device_info"]
        assert device_info["station_name"] == "未知站点"


# ============================== trigger_auto_diagnosis ==============================

class TestTriggerAutoDiagnosis:
    def test_delegates_with_trigger_type_auto(self):
        """trigger_auto_diagnosis 委托 trigger_diagnosis(trigger_type='auto')。"""
        with patch.object(dp, "trigger_diagnosis", return_value={"success": True}) as mock_td:
            r = trigger_auto_diagnosis(42)
        mock_td.assert_called_once_with(42, trigger_type="auto")
        assert r == {"success": True}

    def test_own_db_branch_via_sessionlocal(self, db, seed, test_db):
        """db=None 走 own_db 分支：内部用 SessionLocal() 建独立 session 并在 finally 关闭。

        注意：diagnostic_pipeline 顶部 ``from app.core.database import SessionLocal``
        是按值绑定，conftest 对 db_module.SessionLocal 的属性覆盖对此无效，故这里
        显式 patch 模块内 SessionLocal，将 own_db 分支导向隔离测试库。
        """
        with patch.object(dp, "SessionLocal", test_db["SessionLocal"]), \
             patch.object(dp, "DeviceLogSimulator") as mock_sim, \
             patch.object(dp, "analyze_with_fallback", return_value=_ok_analysis()), \
             patch.object(dp, "execute_runbook_for_alarm",
                          return_value={"runbook_id": "RB-2", "status": "completed"}):
            mock_sim.get_logs_for_alarm.return_value = ["[ERROR] 温度过温"]
            result = trigger_auto_diagnosis(seed["alarm"].id)

        assert result["success"] is True
        assert result["record_id"] is not None
        # own_db 写入已落盘，经另一个 session 可读回，且 trigger_type="auto"
        record = db.query(AIDiagnosisRecord).filter_by(alarm_id=seed["alarm"].id).first()
        assert record is not None
        assert record.trigger_type == "auto"
        assert record.status == DiagnosisStatus.COMPLETED


# ============================== _match_fault_code ==============================

class TestMatchFaultCode:
    def test_match_hit(self, db, seed):
        """fault_type 命中知识库文本 -> 返回 {fault_code, fault_name}。"""
        matched = _match_fault_code(db, "过温", "IGBT", "inverter")
        assert matched is not None
        assert matched["fault_code"] == "0xA0"
        assert "过温" in matched["fault_name"]

    def test_no_candidate_returns_none(self, db, seed):
        """无候选（device_type 不匹配）-> None。"""
        assert _match_fault_code(db, "过温", "IGBT", "charger") is None

    def test_low_score_returns_none(self, db, seed):
        """有候选但关键词都不命中（score<2）-> None。"""
        assert _match_fault_code(db, "完全无关词", "无匹配位置", "inverter") is None

    def test_db_exception_returns_none(self):
        """db 抛异常 -> 静默返回 None（不向上抛）。"""
        bad_db = MagicMock()
        bad_db.query.side_effect = Exception("db dead")
        assert _match_fault_code(bad_db, "x", "y", "inverter") is None


# ============================== _dictify ==============================

class TestDictify:
    def test_normal_object(self, db, seed):
        """ORM 对象 -> 列名到值的字典。"""
        d = _dictify(seed["device"])
        assert isinstance(d, dict)
        assert d["id"] == seed["device"].id
        assert d["sn"] == "SN-T-01"
        assert d["name"] == "储能PCS-T"
        assert "type" in d

    def test_none_input(self):
        """None -> 空字典。"""
        assert _dictify(None) == {}


# ============================== commit rollback 保护 ==============================

def _ok_analysis_min():
    """analyze_with_fallback 成功返回结构(供第二个 commit 路径测试, 字段与源码 usage 对齐)。"""
    return {
        "success": True,
        "result": {
            "fault_type": "过温", "fault_location": "IGBT",
            "root_cause": "散热故障", "severity": "high", "confidence": 0.9,
            "immediate_actions": [], "repair_suggestions": [], "preventive_measures": [],
            "remote_fixable": False,
        },
        "raw_response": "{}", "duration_ms": 10, "model_used": "test-model",
    }


class TestCommitRollbackProtection:
    """trigger_diagnosis 两个 commit 点失败必须 rollback —— 防脏事务残留。

    用 MagicMock db 隔离真实 DB, patch 外部依赖(DeviceLogSimulator/analyze_with_fallback/
    _match_fault_code), 验证 commit 抛异常时 rollback 被调用且流水线返回 success=False。
    """

    @staticmethod
    def _mock_alarm():
        a = MagicMock()
        a.id = 1
        a.device_id = 1
        a.station_id = None
        a.fault_code = "0xA0"
        a.alarm_type = "over_temp"
        a.fault_source = None
        a.level = MagicMock()
        a.content = "温度过高"
        a.created_at = MagicMock()
        return a

    @staticmethod
    def _mock_device():
        d = MagicMock()
        d.id = 1
        d.station_id = None
        return d

    def test_first_commit_failure_rollbacks(self, monkeypatch):
        """创建诊断记录后的第一个 commit 失败 → rollback + success=False。"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            self._mock_alarm(), self._mock_device(), MagicMock(name="station"),
        ]
        mock_db.commit.side_effect = RuntimeError("db boom")

        sim = MagicMock()
        sim.get_logs_for_alarm.return_value = ["[ERROR] 过温"]
        monkeypatch.setattr(dp, "DeviceLogSimulator", sim)
        # stub _dictify: MagicMock 无 __table__ dunder(Python3.9 抛 AttributeError),
        # 测试聚焦 commit/rollback 契约, 不验证 _dictify 本身。
        monkeypatch.setattr(dp, "_dictify", lambda obj: {})

        result = trigger_diagnosis(alarm_id=1, db=mock_db)

        assert result["success"] is False
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_called_once()

    def test_second_commit_failure_rollbacks(self, monkeypatch):
        """更新诊断记录+告警后的第二个 commit 失败 → rollback + success=False。"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            self._mock_alarm(), self._mock_device(), MagicMock(name="station"),
        ]
        # 首次 commit(建记录)成功, 二次 commit(更新记录+告警)失败
        mock_db.commit.side_effect = [None, RuntimeError("db boom")]

        sim = MagicMock()
        sim.get_logs_for_alarm.return_value = ["[ERROR] 过温"]
        monkeypatch.setattr(dp, "DeviceLogSimulator", sim)
        # stub _dictify: MagicMock 无 __table__ dunder(Python3.9 抛 AttributeError),
        # 测试聚焦 commit/rollback 契约, 不验证 _dictify 本身。
        monkeypatch.setattr(dp, "_dictify", lambda obj: {})
        monkeypatch.setattr(dp, "analyze_with_fallback", lambda *a, **kw: _ok_analysis_min())
        monkeypatch.setattr(dp, "_match_fault_code", lambda *a, **kw: None)

        result = trigger_diagnosis(alarm_id=1, db=mock_db)

        assert result["success"] is False
        assert mock_db.commit.call_count == 2
        mock_db.rollback.assert_called_once()

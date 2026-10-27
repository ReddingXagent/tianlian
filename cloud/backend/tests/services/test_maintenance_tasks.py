"""
预测性维护异步任务测试 - 覆盖率补强 ≥70%

被测: app/tasks/maintenance_tasks.py (celery shared_task, bind=True)
设计: 复用 test_analytics_tasks_coverage 的 celery 调用约定 ——
      task.__wrapped__ 取裸函数注入 _FakeTaskSelf (request.id), 完全绕过 broker。

模块级 SessionLocal 绑定坑:
  maintenance_tasks line 12 `from app.core.database import SessionLocal` 绑定到
  导入时对象, 绕过 conftest 对 db_module.SessionLocal 的覆盖 → 显式 monkeypatch
  模块属性。

源码既有坑 (不修, 仅测试绕过):
  predict_faults_task line 117 读幻影列 t.temperature (Telemetry 无此列, 只有
  battery_temperature) → AttributeError。本测试用 property 把 temperature 映射
  到 battery_temperature 防崩, 覆盖温度预测分支。属源码 latent bug, 修复需另起
  fix 卡片 + impact 分析, 不在本次范围。

覆盖:
- _run_db_task            正常 commit / 异常 rollback+raise / finally close
- train_model_task        训练落 MLModel (sleep 被 patch 掉) + 返回体 + version 唯一性(秒+随机后缀)
- predict_faults_task     设备不存在 / 无遥测 / 温度偏高告警 / SOC过低告警
                          + prediction_days 参数化(cutoff 回看窗口 / predicted_time 落点)
- cleanup_old_data_task   删旧遥测 + 旧已处理告警 / 保留新数据与未处理告警
                          + days_old 数据安全守卫(0 / 负数 raise)
- batch_predict_faults    空设备 / 多设备(成功+无预测) / 单设备预测异常捕获
"""
import types
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import maintenance_tasks as tasks_mod
from app.tasks.maintenance_tasks import (
    train_model_task,
    predict_faults_task,
    cleanup_old_data_task,
    batch_predict_faults_task,
)
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.telemetry import Telemetry
from app.models.alarm import Alarm, AlarmStatus, AlarmLevel
from app.models.analytics import MLModel, PredictionAlert


# ═══════════════════════════════════════════════════════════════
# 辅助: 模拟 celery bind=True 任务的 self + 裸函数调用
# ═══════════════════════════════════════════════════════════════

class _FakeTaskSelf:
    """提供 request.id 供任务返回体引用; retry() 记录调用并重抛便于断言。"""

    def __init__(self, task_id="mt-task-001"):
        self.request = type("_Req", (), {"id": task_id})()
        self.retried = []

    def retry(self, exc=None, **kwargs):
        self.retried.append(exc)
        raise exc


def _run_task(task, fake_self, *args, **kwargs):
    """调用 celery bind=True 任务的裸函数, 注入 FakeSelf 作 self。

    `task.__wrapped__` 可能是 bound method (取 __func__) 或裸函数 (取自身)。
    """
    wrapped = task.__wrapped__
    func = getattr(wrapped, "__func__", wrapped)
    return func(fake_self, *args, **kwargs)


@pytest.fixture
def patched_db(test_db, monkeypatch):
    """注入测试库到 maintenance_tasks 模块 + 开 WAL 防嵌套写锁 + 温度幻影列映射。"""
    # 1) 模块级 SessionLocal 绑定坑
    monkeypatch.setattr(tasks_mod, "SessionLocal", test_db["SessionLocal"])
    # 2) batch 非空时内层任务写新 session → 开 WAL 规避 "database is locked"
    with test_db["engine"].connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    return test_db


# 种子构造器
def _dev(db, did, station_id=1, status=DeviceStatus.ONLINE, dtype=DeviceType.CHARGER_DC):
    d = Device(
        id=did, sn=f"SN-MT-{did}", name=f"设备{did}", code=f"MT{did}",
        type=dtype, status=status, station_id=station_id,
    )
    db.add(d)
    return d


def _tele(db, did, ts, soc=None, temp=None):
    t = Telemetry(
        device_id=did, timestamp=ts,
        battery_soc=soc, battery_temperature=temp,
    )
    db.add(t)
    return t


def _fresh_read(test_db):
    """新开 session 读任务提交的写入 (避开测试 session 快照)。"""
    return test_db["SessionLocal"]()


# ═══════════════════════════════════════════════════════════════
# train_model_task
# ═══════════════════════════════════════════════════════════════

class TestTrainModel:

    def test_success_persists_model(self, patched_db, monkeypatch):
        # _execute 内局部 import time; sleep(5) → patch 掉避免拖慢测试
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)

        result = _run_task(train_model_task, _FakeTaskSelf("tm-1"),
                           "预测模型A", "classification")

        assert result["status"] == "completed"
        assert result["model_name"] == "预测模型A"
        assert result["model_type"] == "classification"
        assert result["task_id"] == "tm-1"
        assert result["version"].startswith("v")

        s = _fresh_read(patched_db)
        try:
            m = s.query(MLModel).filter_by(model_name="预测模型A").one()
            assert m.is_active is True
            assert m.performance_metrics["accuracy"] == 0.92
            assert m.performance_metrics["f1_score"] == 0.90
        finally:
            s.close()

    def test_version_uniqueness(self, patched_db, monkeypatch):
        # version 分钟级碰撞修复: 两次训练 → 不同 version (秒级 + 短随机后缀),
        # 即便 datetime 落在同一秒也由随机段保证唯一。
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)

        r1 = _run_task(train_model_task, _FakeTaskSelf("tm-u1"), "模型U1")
        r2 = _run_task(train_model_task, _FakeTaskSelf("tm-u2"), "模型U2")

        assert r1["version"] != r2["version"]
        assert r1["version"].startswith("v")
        assert r2["version"].startswith("v")


# ═══════════════════════════════════════════════════════════════
# predict_faults_task
# ═══════════════════════════════════════════════════════════════

class TestPredictFaults:

    def test_device_not_found_raises(self, patched_db):
        # 覆盖 _run_db_task 异常路径: raise → rollback → re-raise
        patched_db["session"].commit()
        with pytest.raises(ValueError, match="不存在"):
            _run_task(predict_faults_task, _FakeTaskSelf(), 9999)

    def test_no_telemetry_zero_predictions(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5001)
        db.commit()

        result = _run_task(predict_faults_task, _FakeTaskSelf("pf-1"), 5001)

        assert result["status"] == "completed"
        assert result["device_id"] == 5001
        assert result["prediction_count"] == 0
        assert result["predictions"] == []

    def test_high_temperature_warning(self, patched_db):
        # temp avg > 45 → warning 预测 (走 t.temperature property 映射)
        db = patched_db["session"]
        _dev(db, 5002)
        now = datetime.now(timezone.utc)
        _tele(db, 5002, now - timedelta(hours=1), temp=50)
        _tele(db, 5002, now, temp=60)
        db.commit()

        result = _run_task(predict_faults_task, _FakeTaskSelf("pf-2"), 5002)

        assert result["prediction_count"] == 1
        pred = result["predictions"][0]
        assert pred["type"] == "temperature"
        assert pred["severity"] == "warning"

        s = _fresh_read(patched_db)
        try:
            pa = s.query(PredictionAlert).filter_by(device_id=5002).one()
            assert pa.alert_type == "fault_prediction"
            assert pa.severity == "warning"
            assert pa.confidence == 0.75
        finally:
            s.close()

    def test_low_soc_critical(self, patched_db):
        # min soc < 20 → critical 预测
        db = patched_db["session"]
        _dev(db, 5003)
        now = datetime.now(timezone.utc)
        _tele(db, 5003, now - timedelta(hours=1), soc=10)
        _tele(db, 5003, now, soc=15)
        db.commit()

        result = _run_task(predict_faults_task, _FakeTaskSelf("pf-3"), 5003)

        assert result["prediction_count"] == 1
        pred = result["predictions"][0]
        assert pred["type"] == "battery"
        assert pred["severity"] == "critical"

        s = _fresh_read(patched_db)
        try:
            pa = s.query(PredictionAlert).filter_by(device_id=5003).one()
            assert pa.severity == "critical"
            assert pa.confidence == 0.85
        finally:
            s.close()

    def test_temp_and_soc_alerts_no_phantom_column(self, patched_db):
        # 卡 5b79c57a 回归 guard: 曾读幻影列 t.temperature → AttributeError,
        # 温度+SOC 两分支双失效。真实列 battery_temperature 下, 同一设备
        # 温度偏高 + SOC 过低应同时产出两条预测, 且不再抛 AttributeError。
        db = patched_db["session"]
        _dev(db, 5010)
        now = datetime.now(timezone.utc)
        _tele(db, 5010, now - timedelta(hours=1), soc=10, temp=50)
        _tele(db, 5010, now, soc=15, temp=60)
        db.commit()

        result = _run_task(predict_faults_task, _FakeTaskSelf("pf-10"), 5010)

        assert result["status"] == "completed"
        assert result["prediction_count"] == 2
        by_type = {p["type"]: p for p in result["predictions"]}
        assert by_type["temperature"]["severity"] == "warning"
        assert by_type["battery"]["severity"] == "critical"

        s = _fresh_read(patched_db)
        try:
            alerts = s.query(PredictionAlert).filter_by(device_id=5010).all()
            assert {a.severity for a in alerts} == {"warning", "critical"}
        finally:
            s.close()

    def test_second_run_no_duplicate_alerts(self, patched_db):
        # 卡 2912b49e 去重 guard: 对齐 fleet_alert_service 的 active 去重 ——
        # 同 device_id + alert_type + severity 存在未确认(24h 内)记录则跳过新建。
        # 同一设备连续两次 predict_faults_task: 第一次新增 2 条, 第二次零新增,
        # 且跳过原因记录在返回体 skipped 中。
        db = patched_db["session"]
        _dev(db, 5007)
        now = datetime.now(timezone.utc)
        _tele(db, 5007, now - timedelta(hours=1), soc=10, temp=50)
        _tele(db, 5007, now, soc=15, temp=60)
        db.commit()

        r1 = _run_task(predict_faults_task, _FakeTaskSelf("pf-6a"), 5007)
        assert r1["prediction_count"] == 2
        assert r1["skipped"] == []

        r2 = _run_task(predict_faults_task, _FakeTaskSelf("pf-6b"), 5007)
        assert r2["prediction_count"] == 0
        assert len(r2["skipped"]) == 2
        assert {s["type"] for s in r2["skipped"]} == {"temperature", "battery"}
        assert all("已存在" in s["reason"] for s in r2["skipped"])

        s = _fresh_read(patched_db)
        try:
            alerts = s.query(PredictionAlert).filter_by(device_id=5007).all()
            assert len(alerts) == 2  # 第二次零新增
        finally:
            s.close()

    def test_prediction_days_drives_cutoff(self, patched_db):
        # prediction_days 参数化 cutoff: 回看窗口应随 prediction_days 收缩。
        # 5 天前的温度遥测: prediction_days=1 → 排除(0 预测); =30 → 包含(1 预测)。
        # 回归 guard: 源码曾写死 cutoff=30天 → 两调用都返回 1, 本断言锁定参数生效。
        db = patched_db["session"]
        _dev(db, 5004)
        now = datetime.now(timezone.utc)
        _tele(db, 5004, now - timedelta(days=5), temp=60)
        db.commit()

        r_short = _run_task(predict_faults_task, _FakeTaskSelf("pf-4a"),
                            5004, prediction_days=1)
        assert r_short["prediction_count"] == 0   # 5天前 > 1天窗口 → 排除

        r_long = _run_task(predict_faults_task, _FakeTaskSelf("pf-4b"),
                           5004, prediction_days=30)
        assert r_long["prediction_count"] == 1    # 5天前 < 30天窗口 → 包含

    def test_prediction_days_drives_predicted_time(self, patched_db):
        # prediction_days 参数化 predicted_time 落点: 窗口越大, 预测发生越晚。
        # 比较两 device 的落点差(同存储类型相减, 规避 tz naive/aware 坑),
        # 源码曾写死 +3d → 两落点差为 0, 断言锁定参数生效。
        db = patched_db["session"]
        _dev(db, 5005)
        _dev(db, 5006)
        now = datetime.now(timezone.utc)
        _tele(db, 5005, now, temp=60)
        _tele(db, 5006, now, temp=60)
        db.commit()

        _run_task(predict_faults_task, _FakeTaskSelf("pf-5a"), 5005, prediction_days=7)
        _run_task(predict_faults_task, _FakeTaskSelf("pf-5b"), 5006, prediction_days=14)

        s = _fresh_read(patched_db)
        try:
            pa7 = s.query(PredictionAlert).filter_by(device_id=5005).one()
            pa14 = s.query(PredictionAlert).filter_by(device_id=5006).one()
            diff_days = (pa14.predicted_time - pa7.predicted_time).total_seconds() / 86400
            assert diff_days > 5, f"prediction_days 未生效: 落点差仅 {diff_days}d"
        finally:
            s.close()


# ═══════════════════════════════════════════════════════════════
# cleanup_old_data_task
# ═══════════════════════════════════════════════════════════════

class TestCleanupOldData:

    def test_deletes_old_keeps_new(self, patched_db):
        db = patched_db["session"]
        _dev(db, 6001)
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        new_ts = datetime.now(timezone.utc) - timedelta(days=1)
        # 旧/新遥测各 1 条
        _tele(db, 6001, old_ts)
        _tele(db, 6001, new_ts)
        # 旧告警(已解决, 删) + 新告警(活跃, 留)
        db.add(Alarm(device_id=6001, rule_id=1, status=AlarmStatus.RESOLVED,
                     content="old", level=AlarmLevel.WARNING, alarm_type="t",
                     created_at=old_ts))
        db.add(Alarm(device_id=6001, rule_id=1, status=AlarmStatus.ACTIVE,
                     content="new", level=AlarmLevel.WARNING, alarm_type="t",
                     created_at=new_ts))
        db.commit()

        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-1"), days_old=30)

        assert result["status"] == "completed"
        assert result["deleted_telemetry"] == 1
        assert result["deleted_alarms"] == 1
        assert result["days_old"] == 30

        s = _fresh_read(patched_db)
        try:
            assert s.query(Telemetry).count() == 1   # 仅新遥测留
            assert s.query(Alarm).count() == 1        # 仅活跃告警留
        finally:
            s.close()

    def test_telemetry_deleted_in_chunks(self, patched_db, monkeypatch):
        # 卡 35e0ee7b: > chunk_size 行走多批分块, 全删且走 _delete_in_chunks 范式。
        monkeypatch.setattr(tasks_mod.settings, "RETENTION_DELETE_CHUNK", 3)
        spy_calls = []
        _orig = tasks_mod._delete_in_chunks

        def _spy(db, model, time_col, cutoff, chunk_size, extra_filters=None):
            spy_calls.append((model.__name__, chunk_size))
            return _orig(db, model, time_col, cutoff, chunk_size, extra_filters)

        monkeypatch.setattr(tasks_mod, "_delete_in_chunks", _spy)

        db = patched_db["session"]
        _dev(db, 6002)
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        new_ts = datetime.now(timezone.utc) - timedelta(days=1)
        for _ in range(7):   # 7 行旧遥测 > chunk 3 → 至少 3 批
            _tele(db, 6002, old_ts)
        _tele(db, 6002, new_ts)   # 窗口内新行保留
        db.commit()

        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-2"), days_old=30)

        assert result["deleted_telemetry"] == 7
        # 分块范式生效: 以配置的 chunk_size 调用 (Telemetry 无额外过滤)
        assert ("Telemetry", 3) in spy_calls
        assert ("Alarm", 3) in spy_calls

        s = _fresh_read(patched_db)
        try:
            remain = s.query(Telemetry).all()
            assert len(remain) == 1
            assert remain[0].timestamp >= new_ts.replace(tzinfo=None) - timedelta(seconds=1)
        finally:
            s.close()

    def test_alarm_only_deleted_when_processed(self, patched_db):
        # 卡 35e0ee7b: 旧窗口内仅 resolved/acknowledged (即 status.in_ 白名单) 被删;
        # 未处理 (active) 旧告警保留; 窗口内新告警无论状态保留。
        # 注: AlarmStatus 无 CLOSED 成员, 生产过滤里的 "closed" 字符串实际不匹配
        # 任何行 —— 沿用既有语义, 不在本次卡片扩名单。
        db = patched_db["session"]
        _dev(db, 6003)
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        new_ts = datetime.now(timezone.utc) - timedelta(days=1)

        def _alarm(status, ts, content):
            db.add(Alarm(device_id=6003, rule_id=1, status=status,
                         content=content, level=AlarmLevel.WARNING, alarm_type="t",
                         created_at=ts))

        _alarm(AlarmStatus.RESOLVED, old_ts, "old-resolved")         # 删
        _alarm(AlarmStatus.ACKNOWLEDGED, old_ts, "old-acked")        # 删
        _alarm(AlarmStatus.ACTIVE, old_ts, "old-active")             # 留(未处理)
        _alarm(AlarmStatus.RESOLVED, new_ts, "new-resolved")         # 留(窗口内)
        db.commit()

        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-3"), days_old=30)

        assert result["deleted_alarms"] == 2
        s = _fresh_read(patched_db)
        try:
            contents = {a.content for a in s.query(Alarm).all()}
            assert contents == {"old-active", "new-resolved"}
        finally:
            s.close()

    def test_empty_tables_delete_zero(self, patched_db):
        # 空表: 不报错, 计数 0。
        patched_db["session"].commit()
        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-4"), days_old=30)
        assert result["status"] == "completed"
        assert result["deleted_telemetry"] == 0
        assert result["deleted_alarms"] == 0

    def test_days_old_zero_raises(self, patched_db):
        # 数据安全守卫: days_old=0 → cutoff=now, 删除全量历史遥测, 必须拒绝。
        patched_db["session"].commit()
        with pytest.raises(ValueError, match="days_old"):
            _run_task(cleanup_old_data_task, _FakeTaskSelf(), days_old=0)

    def test_days_old_negative_raises(self, patched_db):
        # 数据安全守卫: 负数 → cutoff 落在未来, 同样删全量, 必须拒绝。
        patched_db["session"].commit()
        with pytest.raises(ValueError, match="days_old"):
            _run_task(cleanup_old_data_task, _FakeTaskSelf(), days_old=-5)


# ═══════════════════════════════════════════════════════════════
# cleanup_old_data_task — V2 拆分表 (卡 515cfc13)
# ═══════════════════════════════════════════════════════════════

class TestCleanupOldDataV2Tables515cfc13:
    """卡 515cfc13: 遥测留存须覆盖 V2 拆分表 telemetry_pv/battery/charger。

    背景: 生产写入已切换到 V2 专表, 旧 Telemetry 表 0 行 —— 只删旧表
    使 30 天留存意图落空 (battery 150万行无限增长)。
    """

    def _seed_v2(self, db, did=6101):
        from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger
        _dev(db, did)
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        new_ts = datetime.now(timezone.utc) - timedelta(days=1)
        for model in (TelemetryPV, TelemetryBattery, TelemetryCharger):
            for ts in (old_ts, old_ts, new_ts):   # 旧2条 + 新1条
                db.add(model(device_id=did, station_id=1, timestamp=ts))
        db.commit()
        return TelemetryPV, TelemetryBattery, TelemetryCharger

    def test_515cfc13_v2_tables_deleted_by_cutoff(self, patched_db):
        # 三张 V2 表 cutoff 之前删、之后留, 返回体含分表计数。
        db = patched_db["session"]
        PV, BAT, CHR = self._seed_v2(db)
        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-v2-1"), days_old=30)

        assert result["status"] == "completed"
        assert result["deleted_telemetry_v2"] == {
            "telemetry_pv": 2, "telemetry_battery": 2, "telemetry_charger": 2,
        }

        s = _fresh_read(patched_db)
        try:
            for model in (PV, BAT, CHR):
                remain = s.query(model).all()
                assert len(remain) == 1, f"{model.__tablename__} 应仅留 1 条新数据"
                # SQLite 落 naive 字符串, 比较参数同样 naive
                assert remain[0].timestamp >= (
                    datetime.now(timezone.utc) - timedelta(days=2)
                ).replace(tzinfo=None)
        finally:
            s.close()

    def test_515cfc13_v2_deleted_in_chunks(self, patched_db, monkeypatch):
        # V2 表同样走 _delete_in_chunks 分块范式 (卡 35e0ee7b), 防长事务锁表。
        monkeypatch.setattr(tasks_mod.settings, "RETENTION_DELETE_CHUNK", 3)
        spy_calls = []
        _orig = tasks_mod._delete_in_chunks

        def _spy(db, model, time_col, cutoff, chunk_size, extra_filters=None):
            spy_calls.append(model.__name__)
            return _orig(db, model, time_col, cutoff, chunk_size, extra_filters)

        monkeypatch.setattr(tasks_mod, "_delete_in_chunks", _spy)

        db = patched_db["session"]
        PV, BAT, CHR = self._seed_v2(db, did=6102)
        for _ in range(7):   # 7 行旧遥测 > chunk 3 → 至少 3 批
            db.add(PV(device_id=6102, station_id=1,
                      timestamp=datetime.now(timezone.utc) - timedelta(days=60)))
        db.commit()

        result = _run_task(cleanup_old_data_task, _FakeTaskSelf("cl-v2-2"), days_old=30)

        assert result["deleted_telemetry_v2"]["telemetry_pv"] == 9   # 2 + 7
        assert "TelemetryPV" in spy_calls
        assert "TelemetryBattery" in spy_calls
        assert "TelemetryCharger" in spy_calls

    def test_515cfc13_days_old_guard_still_enforced(self, patched_db):
        # days_old < 1 守卫在 V2 表加入后仍生效 (0/负数拒绝)。
        db = patched_db["session"]
        self._seed_v2(db, did=6103)
        for bad in (0, -5):
            with pytest.raises(ValueError, match="days_old"):
                _run_task(cleanup_old_data_task, _FakeTaskSelf(), days_old=bad)

        # 守卫拒绝后数据原样保留
        s = _fresh_read(patched_db)
        try:
            from app.models.telemetry_v2 import TelemetryBattery
            assert s.query(TelemetryBattery).count() == 3
        finally:
            s.close()


# ═══════════════════════════════════════════════════════════════
# batch_predict_faults_task
# ═══════════════════════════════════════════════════════════════

class TestBatchPredictFaults:

    def test_empty_devices(self, patched_db):
        patched_db["session"].commit()
        result = _run_task(batch_predict_faults_task, _FakeTaskSelf("bp-0"))
        assert result["status"] == "completed"
        assert result["total_devices"] == 0
        assert result["results"] == []

    def test_station_filter_yields_empty(self, patched_db):
        db = patched_db["session"]
        _dev(db, 6051, station_id=1)
        db.commit()
        # 站点 999 无设备
        result = _run_task(batch_predict_faults_task, _FakeTaskSelf(), station_id=999)
        assert result["total_devices"] == 0
        assert result["results"] == []

    def test_with_devices_runs_each(self, patched_db):
        db = patched_db["session"]
        _dev(db, 7001, station_id=1)
        _dev(db, 7002, station_id=2)
        now = datetime.now(timezone.utc)
        _tele(db, 7001, now, soc=10)   # 低 SOC → 1 条预测
        _tele(db, 7002, now, soc=80)   # 正常 → 0 条预测
        db.commit()

        result = _run_task(batch_predict_faults_task, _FakeTaskSelf("bp-1"))

        assert result["status"] == "completed"
        assert result["total_devices"] == 2
        assert len(result["results"]) == 2
        # 每项应为 predict 正常返回体(含 predictions), 覆盖 line 242 成功 append。
        # 回归 guard: 源码曾因 __wrapped__ 误传 task 首参致 TypeError, 每设备走
        # except 记 failed —— 此断言锁定修复后走成功路径。
        by_dev = {r["device_id"]: r for r in result["results"]}
        assert by_dev[7001]["prediction_count"] == 1   # 低 SOC → 1 条预测
        assert by_dev[7001]["predictions"][0]["type"] == "battery"
        assert by_dev[7002]["prediction_count"] == 0   # 正常 → 无预测
        assert all(r.get("status") == "completed" for r in result["results"])

    def test_per_device_error_captured(self, patched_db, monkeypatch):
        # 覆盖 batch try/except: 单设备预测抛错 → 记 failed 不中断
        db = patched_db["session"]
        _dev(db, 7003)
        db.commit()

        # batch 以 bound-method 语义调用 __wrapped__(device.id, prediction_days=7)
        # (self 自动绑), 故 fake 的签名不含 self。
        def _boom_wrapped(device_id, prediction_days=7):
            raise RuntimeError("predict boom")

        fake_pred = types.SimpleNamespace(__wrapped__=_boom_wrapped)
        monkeypatch.setattr(tasks_mod, "predict_faults_task", fake_pred)

        result = _run_task(batch_predict_faults_task, _FakeTaskSelf("bp-2"))

        assert result["total_devices"] == 1
        assert result["status"] == "completed"
        rec = result["results"][0]
        assert rec["device_id"] == 7003
        assert rec["status"] == "failed"
        assert "predict boom" in rec["error"]

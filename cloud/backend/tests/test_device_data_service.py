"""
DeviceDataService 单元测试

覆盖 app/services/device_data_service.py 的 4 个核心方法：
- get_realtime_data (async): 设备不存在 / 适配器不可用 / 正常采集 / 采集异常
- get_history_data:          空数据 / 时间范围过滤 / 有记录返回扁平列聚合
- get_health_status:         设备不存在 / 正常 / status|health_score|run_hours 缺省
- get_statistics:            无历史数据 / 有记录按指标聚合

Telemetry 为扁平列模型（grid_power_total / inv_power_a / ...），
无独立 `data` JSON 列；Telemetry.data property 把非 None 度量列聚合为字典，
供 get_history_data / get_statistics 的 `record.data` 访问路径使用。
"""

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry
from app.services.device_data_service import DeviceDataService


# ───────────────────────── helpers ─────────────────────────


def _make_station(session, code="ST-TST"):
    st = Station(name="测试站", code=code, address="测试地址", status=StationStatus.NORMAL)
    session.add(st)
    session.flush()
    return st


def _make_device(session, station=None, **over):
    """造一台在线逆变器（含 station），返回已 flush 出 id 的 Device。"""
    if station is None:
        station = _make_station(session)
    base = dict(
        sn="SN-TST-001",
        name="逆变器#测试",
        code="TST001",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=station.id,
        health_score=95.0,
        total_run_hours=12.5,
        device_address=1,
    )
    base.update(over)
    dev = Device(**base)
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


class _FakeAdapter:
    """模拟协议适配器：read_data 返回预设 raw，或抛预设异常。"""

    def __init__(self, raw=None, exc=None):
        self._raw = raw
        self._exc = exc

    async def read_data(self, device_address):
        if self._exc is not None:
            raise self._exc
        return self._raw


class _FakePipeline:
    """模拟解析流水线：execute 返回预设 parsed。"""

    def __init__(self, parsed):
        self._parsed = parsed

    async def execute(self, raw_data):
        return self._parsed


# ───────────────────────── get_health_status ─────────────────────────


def test_health_status_device_not_found(db_session):
    svc = DeviceDataService(db_session)
    assert svc.get_health_status(99999) == {"error": "设备不存在"}


def test_health_status_online_device(db_session):
    dev = _make_device(db_session)
    svc = DeviceDataService(db_session)
    health = svc.get_health_status(dev.id)

    assert health["device_id"] == dev.id
    assert health["device_name"] == "逆变器#测试"
    assert health["status"] == "online"
    assert health["health_score"] == 95.0
    assert health["total_run_hours"] == 12.5
    assert health["is_online"] is True
    assert "timestamp" in health


def test_health_status_fault_device_not_online(db_session):
    """status=FAULT → status="fault"，is_online False（覆盖 `status == "online"` 为 False）

    注：service 内 `device.status.value if device.status else "unknown"` 的 None 分支
    不可达 —— Device.status 列 default=DeviceStatus.ONLINE，ORM 正常路径下永不为 None，
    属于防御性死代码，故此处改测真实可触达的 FAULT 分支。
    """
    dev = _make_device(db_session, status=DeviceStatus.FAULT, sn="SN-TST-FAULT", code="TSTFAULT")
    svc = DeviceDataService(db_session)
    health = svc.get_health_status(dev.id)
    assert health["status"] == "fault"
    assert health["is_online"] is False


def test_health_status_defaults_when_metrics_none(db_session):
    """health_score / total_run_hours 为 None → 分别回退 100.0 / 0"""
    dev = _make_device(
        db_session, health_score=None, total_run_hours=None,
        sn="SN-TST-NULL", code="TSTNULL",
    )
    svc = DeviceDataService(db_session)
    health = svc.get_health_status(dev.id)
    assert health["health_score"] == 100.0
    assert health["total_run_hours"] == 0


# ───────────────────────── get_history_data ─────────────────────────


def test_history_data_empty(db_session):
    """设备无遥测记录 → 空列表（不触发 record.data，正常路径）"""
    dev = _make_device(db_session)
    svc = DeviceDataService(db_session)
    assert svc.get_history_data(dev.id) == []


def test_history_data_custom_range_empty(db_session):
    """自定义 start/end 但无数据 → 空列表"""
    dev = _make_device(db_session)
    svc = DeviceDataService(db_session)
    start = "2026-01-01T00:00:00"
    end = "2026-01-02T00:00:00"
    # service 直接把字符串透传给 SQLAlchemy 比较，SQLite 可按字符串比较
    result = svc.get_history_data(dev.id, start_time=start, end_time=end)
    assert result == []


def test_history_data_records_return_telemetry_data(db_session):
    """设备有遥测记录 → get_history_data 经 record.data 返回扁平列聚合字典。
    Telemetry.data property 排除 id/device_id/timestamp，只含非 None 度量列。"""
    dev = _make_device(db_session, sn="SN-TST-DATA", code="TSTDATA")
    db_session.add(Telemetry(device_id=dev.id, grid_power_total=10.0, battery_soc=80.0))
    db_session.commit()

    svc = DeviceDataService(db_session)
    result = svc.get_history_data(dev.id)

    assert len(result) == 1
    record = result[0]
    assert record["device_id"] == dev.id
    assert record["timestamp"] is not None
    # data 字典含已写入的非 None 度量列
    assert record["data"] == {"grid_power_total": 10.0, "battery_soc": 80.0}
    assert record["data"]["grid_power_total"] == 10.0


# ───────────────────────── get_statistics ─────────────────────────


def test_statistics_no_history(db_session):
    """无历史数据 → {"error": "无历史数据"}"""
    dev = _make_device(db_session)
    svc = DeviceDataService(db_session)
    assert svc.get_statistics(dev.id) == {"error": "无历史数据"}


def test_statistics_records_aggregate_telemetry_metric(db_session):
    """有历史记录 → get_statistics 经 record.data 提取指标并聚合。
    两记录 grid_power_total=10/30，avg=20，count=2。"""
    dev = _make_device(db_session, sn="SN-TST-STAT", code="TSTSTAT")
    db_session.add(Telemetry(device_id=dev.id, grid_power_total=10.0))
    db_session.add(Telemetry(device_id=dev.id, grid_power_total=30.0))
    db_session.commit()

    svc = DeviceDataService(db_session)
    result = svc.get_statistics(dev.id, metric="grid_power_total", aggregation="avg")

    assert result["metric"] == "grid_power_total"
    assert result["aggregation"] == "avg"
    assert result["value"] == 20.0
    assert result["count"] == 2


# ───────────────────────── get_realtime_data ─────────────────────────


async def test_realtime_data_device_not_found(db_session):
    svc = DeviceDataService(db_session)
    result = await svc.get_realtime_data(99999)
    assert result == {"error": "设备不存在"}


async def test_realtime_data_adapter_unavailable(db_session, monkeypatch):
    """get_adapter 返回 None → {"error": "适配器不可用"}"""
    dev = _make_device(db_session)
    monkeypatch.setattr(
        "app.services.device_data_service.get_adapter", lambda *a, **k: None
    )
    svc = DeviceDataService(db_session)
    result = await svc.get_realtime_data(dev.id)
    assert result == {"error": "适配器不可用"}


async def test_realtime_data_success(db_session, monkeypatch):
    """适配器 + 流水线正常 → 返回解析后数据"""
    dev = _make_device(db_session)
    monkeypatch.setattr(
        "app.services.device_data_service.get_adapter",
        lambda *a, **k: _FakeAdapter(raw=b"\x01\x02\x03"),
    )
    monkeypatch.setattr(
        "app.services.device_data_service.create_pipeline",
        lambda *a, **k: _FakePipeline(parsed={"power": 5.0}),
    )
    svc = DeviceDataService(db_session)
    result = await svc.get_realtime_data(dev.id)
    assert result == {"power": 5.0}


async def test_realtime_data_collection_error(db_session, monkeypatch):
    """adapter.read_data 抛异常 → {"error": str(exc)}"""
    dev = _make_device(db_session)
    boom = TimeoutError("读超时")
    monkeypatch.setattr(
        "app.services.device_data_service.get_adapter",
        lambda *a, **k: _FakeAdapter(exc=boom),
    )
    svc = DeviceDataService(db_session)
    result = await svc.get_realtime_data(dev.id)
    assert result.get("error")  # cc2272b84: 底层异常脱敏为通用消息

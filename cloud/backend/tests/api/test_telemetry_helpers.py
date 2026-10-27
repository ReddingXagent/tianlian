"""遥测数据辅助函数测试 (工作卡 be1f5eb4)

覆盖 app/api/v1/telemetry/helpers.py —— 纯函数 / helper, 不走 HTTP, 直接 import 调用:
- MAX_BATCH_SIZE 常量
- _get_telemetry_reader()           TDengine 未启用 → None
- get_region_from_header()          请求头解析, 默认 'default'
- get_pod_from_header()             请求头解析, 默认 'pod-01'
- route_to_telemetry_table()        设备类型 → 遥测表路由 (charger_dc/pv_inverter/meter)
- create_telemetry_record()         列过滤 + station_id 注入 + 新表 region_id/pod_id
- insert_telemetry_rows_with_fallback()  整批成功 / 空列表 / 毒记录逐条隔离
"""
import types

from pydantic import BaseModel

from app.api.v1.telemetry import helpers as H
from app.models.telemetry import Telemetry
from app.models.telemetry_v2 import (
    TelemetryPV, TelemetryBattery, TelemetryCharger,
)


def _fake_device(device_type_value, station_id=1):
    """轻量 device 替身: 仅需 .type.value 与 .station_id (helper 实际只用这两个)。"""
    return types.SimpleNamespace(
        type=types.SimpleNamespace(value=device_type_value),
        station_id=station_id,
    )


class _TelemetryData(BaseModel):
    """模拟遥测上报 payload (含目标表有/无的字段, 验证列过滤)。"""
    device_id: int = 1
    grid_voltage_a: float = 220.0      # TelemetryPV 有, TelemetryCharger 无
    charger_voltage: float = 400.0     # TelemetryCharger 有, TelemetryPV 无
    bogus_field: str = "x"             # 任何表都没有 → 必被过滤


# ═══════════════════════════════════════════════════════════════
# 1. 配置常量 + 查询路由
# ═══════════════════════════════════════════════════════════════

class TestConfig:
    def test_max_batch_size_default(self):
        assert H.MAX_BATCH_SIZE == 500  # 默认 BATCH_MAX_SIZE=500

    def test_get_telemetry_reader_returns_none_when_disabled(self):
        """TDENGINE_ENABLED=False (测试环境) → 走 SQLAlchemy, 返回 None。"""
        assert H._get_telemetry_reader() is None


# ═══════════════════════════════════════════════════════════════
# 2. 请求头解析
# ═══════════════════════════════════════════════════════════════

class TestHeaderHelpers:
    def test_region_default(self):
        assert H.get_region_from_header(None) == "default"

    def test_region_from_value(self):
        assert H.get_region_from_header("east-1") == "east-1"

    def test_pod_default(self):
        assert H.get_pod_from_header(None) == "pod-01"

    def test_pod_from_value(self):
        assert H.get_pod_from_header("pod-99") == "pod-99"


# ═══════════════════════════════════════════════════════════════
# 3. 设备类型 → 遥测表路由
# ═══════════════════════════════════════════════════════════════

class TestRouteToTable:
    def test_charger_dc_routes_to_charger_table(self, db_session):
        dev = _fake_device("charger_dc")
        assert H.route_to_telemetry_table(dev, db_session) is TelemetryCharger

    def test_pv_inverter_routes_to_pv_table(self, db_session):
        dev = _fake_device("pv_inverter")
        assert H.route_to_telemetry_table(dev, db_session) is TelemetryPV

    def test_battery_inverter_routes_to_battery_table(self, db_session):
        dev = _fake_device("battery_inverter")
        assert H.route_to_telemetry_table(dev, db_session) is TelemetryBattery

    def test_unknown_type_falls_back_to_legacy(self, db_session):
        """meter / gateway 等未映射类型 → 旧 Telemetry 表。"""
        dev = _fake_device("meter")
        assert H.route_to_telemetry_table(dev, db_session) is Telemetry


# ═══════════════════════════════════════════════════════════════
# 4. 遥测记录构建 (列过滤 + 字段注入)
# ═══════════════════════════════════════════════════════════════

class TestCreateRecord:
    def test_filters_unknown_columns_for_charger(self, db_session):
        """新表: 仅保留 TelemetryCharger 有的列 + 注入 region_id/pod_id/station_id。"""
        dev = _fake_device("charger_dc", station_id=7)
        rec = H.create_telemetry_record(
            dev, _TelemetryData(device_id=1, charger_voltage=400.0),
            region_id="east", pod_id="pod-5", db=db_session,
        )
        assert isinstance(rec, TelemetryCharger)
        assert rec.station_id == 7
        assert rec.region_id == "east"
        assert rec.pod_id == "pod-5"
        assert rec.charger_voltage == 400.0
        assert getattr(rec, "grid_voltage_a", None) is None  # 该列不存在于 Charger
        assert not hasattr(rec, "bogus_field")  # 非法列被过滤

    def test_filters_unknown_columns_for_pv(self, db_session):
        """PV 表: 保留 grid_voltage_a, 过滤 charger_voltage/bogus_field。"""
        dev = _fake_device("pv_inverter", station_id=3)
        rec = H.create_telemetry_record(
            dev, _TelemetryData(device_id=1, grid_voltage_a=230.0),
            region_id="r", pod_id="p", db=db_session,
        )
        assert isinstance(rec, TelemetryPV)
        assert rec.grid_voltage_a == 230.0
        assert not hasattr(rec, "charger_voltage")

    def test_legacy_table_omits_station_id_when_absent(self, db_session):
        """旧 Telemetry 表无 station_id 列 → 注入前校验 valid_columns, 不再无条件注入。

        修复 (卡 418bbeac): 原 ``data_dict["station_id"] = device.station_id`` 在列过滤后
        无条件注入, 旧表 (meter/gateway 等未映射类型) 无 station_id 列, ``Telemetry(**data_dict)``
        抛 TypeError → 遥测上报 500。现改为 ``if "station_id" in valid_columns`` 守卫:
        旧表路径正常创建记录且不含 station_id; 新表路径 (列过滤 + 注入字段都存在) 不受影响。
        """
        dev = _fake_device("meter", station_id=2)
        rec = H.create_telemetry_record(
            dev, _TelemetryData(device_id=1, grid_voltage_a=220.0),
            region_id="east", pod_id="pod-5", db=db_session,
        )
        assert isinstance(rec, Telemetry)
        # 旧表无 station_id 列 → 记录上不存在该属性, 不再 TypeError
        assert not hasattr(rec, "station_id")
        # 旧表非新表 → 也不注入 region_id/pod_id (model_class == Telemetry 分支)
        assert not hasattr(rec, "region_id")


# ═══════════════════════════════════════════════════════════════
# 5. 批量写入 + 毒记录隔离 (insert_telemetry_rows_with_fallback)
# ═══════════════════════════════════════════════════════════════

class TestInsertFallback:
    def test_empty_rows_returns_zero(self, db_session):
        n, ins, com = H.insert_telemetry_rows_with_fallback(
            db_session, TelemetryCharger, [], {}, "charger",
        )
        assert (n, ins, com) == (0, 0.0, 0.0)

    def test_bulk_success(self, db_session):
        """合法整批 → 全部落库, 无 fallback, 无 error。"""
        from app.models.station import Station
        from app.models.device import Device, DeviceType
        st = Station(name="t站", code="THT1")
        db_session.add(st); db_session.commit(); db_session.refresh(st)
        d1 = Device(sn="SN1", name="d1", code="D1", type=DeviceType.CHARGER_DC, station_id=st.id)
        d2 = Device(sn="SN2", name="d2", code="D2", type=DeviceType.CHARGER_DC, station_id=st.id)
        db_session.add_all([d1, d2]); db_session.commit()
        db_session.refresh(d1); db_session.refresh(d2)

        rows = [
            {"device_id": d1.id, "station_id": st.id, "charger_voltage": 400.0},
            {"device_id": d2.id, "station_id": st.id, "charger_voltage": 410.0},
        ]
        stats = {"errors": []}
        n, ins, com = H.insert_telemetry_rows_with_fallback(
            db_session, TelemetryCharger, rows, stats, "charger",
        )
        assert n == 2
        assert stats["errors"] == []
        assert ins > 0 or com > 0  # 有计时
        # 真实落库
        cnt = db_session.query(TelemetryCharger).count()
        assert cnt >= 2

    def test_poison_record_isolation(self, db_session):
        """整批含毒记录 (device_id 缺失违反 NOT NULL) → fallback 隔离, 合法行仍落库。"""
        from app.models.station import Station
        from app.models.device import Device, DeviceType
        st = Station(name="t站2", code="THT2")
        db_session.add(st); db_session.commit(); db_session.refresh(st)
        d1 = Device(sn="SN3", name="d3", code="D3", type=DeviceType.CHARGER_DC, station_id=st.id)
        db_session.add(d1); db_session.commit(); db_session.refresh(d1)

        rows = [
            {"device_id": d1.id, "station_id": st.id, "charger_voltage": 400.0},  # 合法
            {"station_id": st.id, "charger_voltage": 400.0},                       # 毒: 缺 device_id
        ]
        stats = {"errors": []}
        n, ins, com = H.insert_telemetry_rows_with_fallback(
            db_session, TelemetryCharger, rows, stats, "charger",
        )
        # 合法行落库, 毒行被记录
        assert n == 1
        assert len(stats["errors"]) == 1
        assert "写入失败" in stats["errors"][0]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备数据服务测试 - DeviceDataService

被测: app/services/device_data_service.py (242 行, 原零测试)

设计:
  - 不依赖真实 DB: db 用 MagicMock, side_effect 分流 Device/Telemetry 两条 query 链
  - 不依赖协议适配器: monkeypatch 模块级 get_adapter / create_pipeline 注入 AsyncMock
  - device/telemetry 用 SimpleNamespace + 真实枚举值, 精确驱动每个逻辑分支

覆盖:
- get_realtime_data  设备不存在 / 适配器None / 成功(校验read_data入参) / 采集异常 /
                     config 补充 protocol+device_address
- get_history_data   默认24h(校验时间范围) / 自定义 start+end / 无数据空列表
- get_health_status  设备不存在 / 正常(online) / offline / status=None
- get_statistics     avg / max / min / sum / 无历史 / 无指标 / 未知聚合
- 异常加固 (卡 f4288442): DB 层抛异常时降级返回 (空 dict/空 list), 记 logger.exception
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import device_data_service as svc
from app.services.device_data_service import DeviceDataService
from app.models.device import Device, DeviceStatus, ProtocolType


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def make_device(**kw):
    """构造 fake device (SimpleNamespace + 真实枚举), 属性精确可控。

    device_type 直接设字符串, 模拟 Device.device_type property 的返回值。
    """
    defaults = dict(
        id=1,
        name="测试逆变器",
        status=DeviceStatus.ONLINE,
        health_score=95.0,
        last_heartbeat=datetime(2026, 8, 2, 10, 0, 0),
        total_run_hours=100.0,
        device_type="inverter",
        comm_config={"host": "1.2.3.4"},
        protocol_type=ProtocolType.MODBUS_TCP,
        device_address=7,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def make_telemetry(data, device_id=1, ts=None):
    """构造 fake telemetry record; data 为度量字典 (对应 record.data property)。"""
    return SimpleNamespace(
        data=data,
        device_id=device_id,
        timestamp=ts or datetime(2026, 8, 2, 9, 0, 0),
    )


def make_db(device=None, telemetry_records=None):
    """mock db: side_effect 分流 Device/Telemetry 两条 query 链。

    两条 chain 挂到 db.device_chain / db.telemetry_chain 供断言。
    """
    db = MagicMock()

    device_chain = MagicMock()
    device_chain.filter.return_value.first.return_value = device

    telemetry_chain = MagicMock()
    telemetry_all = telemetry_chain.filter.return_value.order_by.return_value
    telemetry_all.all.return_value = telemetry_records or []

    def _query(model, *args, **kwargs):
        return device_chain if model is Device else telemetry_chain

    db.query.side_effect = _query
    db.device_chain = device_chain
    db.telemetry_chain = telemetry_chain
    return db


def _filter_values(chain):
    """提取 filter() 收到的比较表达式右侧值 (device_id / timestamp 范围)。"""
    call = chain.filter.call_args
    if not call or not call.args:
        return []
    out = []
    for expr in call.args:
        right = getattr(expr, "right", None)
        if right is None:
            continue
        v = getattr(right, "effective_value", None)
        if v is None:
            v = getattr(right, "value", None)
        out.append(v)
    return out


# ═══════════════════════════════════════════════════════════════
# get_realtime_data
# ═══════════════════════════════════════════════════════════════

class TestGetRealtimeData:

    async def test_device_not_found(self):
        db = make_db(device=None)
        result = await DeviceDataService(db).get_realtime_data(99999)
        assert result == {"error": "设备不存在"}

    async def test_adapter_unavailable(self, monkeypatch):
        db = make_db(device=make_device())
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: None)

        result = await DeviceDataService(db).get_realtime_data(1)
        assert result == {"error": "适配器不可用"}

    async def test_success(self, monkeypatch):
        db = make_db(device=make_device())
        adapter = MagicMock()
        adapter.read_data = AsyncMock(return_value={"raw": "0x01"})
        pipeline = MagicMock()
        pipeline.execute = AsyncMock(return_value={"power": 100.0})
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)
        monkeypatch.setattr(svc, "create_pipeline", lambda dt, proto: pipeline)

        result = await DeviceDataService(db).get_realtime_data(1)

        assert result == {"power": 100.0}
        # read_data 收到补充后的 device_address(7)
        adapter.read_data.assert_awaited_once_with(7)
        pipeline.execute.assert_awaited_once()

    async def test_collect_raises(self, monkeypatch):
        db = make_db(device=make_device())
        adapter = MagicMock()
        adapter.read_data = AsyncMock(side_effect=TimeoutError("device timeout"))
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)
        monkeypatch.setattr(svc, "create_pipeline", lambda dt, proto: MagicMock())

        result = await DeviceDataService(db).get_realtime_data(1)
        assert result == {"error": "服务内部错误，请稍后重试"}

    async def test_config_supplements_protocol_and_address(self, monkeypatch):
        # comm_config 无 protocol/device_address, 由 device 字段补充
        db = make_db(device=make_device(comm_config={"host": "1.2.3.4"}))
        captured_adapter = {}
        captured_pipe = {}

        def fake_get_adapter(dt, cfg):
            captured_adapter["dt"] = dt
            captured_adapter["cfg"] = dict(cfg)
            adapter = MagicMock()
            adapter.read_data = AsyncMock(return_value=b"raw")
            return adapter

        def fake_create_pipeline(dt, proto):
            captured_pipe["dt"] = dt
            captured_pipe["proto"] = proto
            pipeline = MagicMock()
            pipeline.execute = AsyncMock(return_value={"ok": True})
            return pipeline

        monkeypatch.setattr(svc, "get_adapter", fake_get_adapter)
        monkeypatch.setattr(svc, "create_pipeline", fake_create_pipeline)

        result = await DeviceDataService(db).get_realtime_data(1)

        assert result == {"ok": True}
        # protocol 从 protocol_type.value 补充; device_address 从 device 字段补充
        assert captured_adapter["cfg"]["protocol"] == ProtocolType.MODBUS_TCP.value
        assert captured_adapter["cfg"]["device_address"] == 7
        assert captured_adapter["cfg"]["host"] == "1.2.3.4"     # 原配置保留
        assert captured_adapter["dt"] == "inverter"             # device_type property
        # create_pipeline 收到补充后的 protocol
        assert captured_pipe["proto"] == ProtocolType.MODBUS_TCP.value


# ═══════════════════════════════════════════════════════════════
# get_history_data
# ═══════════════════════════════════════════════════════════════

class TestGetHistoryData:

    def test_default_24h_range(self):
        records = [
            make_telemetry({"power": 10.0}, ts=datetime(2026, 8, 2, 8, 0)),
            make_telemetry({"power": 20.0}, ts=datetime(2026, 8, 2, 9, 0)),
        ]
        db = make_db(telemetry_records=records)

        before = datetime.now(timezone.utc)
        result = DeviceDataService(db).get_history_data(1)

        # 结构: 每条映射为 {timestamp, data, device_id}, 顺序与 mock 返回一致
        assert len(result) == 2
        assert result[0]["data"] == {"power": 10.0}
        assert result[0]["device_id"] == 1
        assert result[1]["data"] == {"power": 20.0}
        assert "timestamp" in result[0]
        # order_by 意图存在 (mock 不真实排序)
        db.telemetry_chain.filter.return_value.order_by.assert_called_once()

        # 默认时间范围: device_id + start≈now-24h + end≈now
        vals = _filter_values(db.telemetry_chain)
        assert vals[0] == 1
        start, end = vals[1], vals[2]
        assert abs((end - before).total_seconds()) < 5
        assert abs((start - (before - timedelta(hours=24))).total_seconds()) < 5

    def test_custom_time_range(self):
        start = datetime(2026, 7, 1, 0, 0, 0)
        end = datetime(2026, 7, 2, 0, 0, 0)
        records = [make_telemetry({"power": 5.0})]
        db = make_db(telemetry_records=records)

        result = DeviceDataService(db).get_history_data(1, start_time=start, end_time=end)

        assert len(result) == 1
        vals = _filter_values(db.telemetry_chain)
        assert vals[0] == 1
        assert vals[1] == start      # 自定义 start 精确透传
        assert vals[2] == end        # 自定义 end 精确透传

    def test_empty_returns_empty_list(self):
        db = make_db(telemetry_records=[])
        result = DeviceDataService(db).get_history_data(1)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# get_health_status
# ═══════════════════════════════════════════════════════════════

class TestGetHealthStatus:

    def test_device_not_found(self):
        db = make_db(device=None)
        result = DeviceDataService(db).get_health_status(99999)
        assert result == {"error": "设备不存在"}

    def test_online(self):
        db = make_db(device=make_device())
        result = DeviceDataService(db).get_health_status(1)
        assert result["device_id"] == 1
        assert result["device_name"] == "测试逆变器"
        assert result["status"] == "online"
        assert result["health_score"] == 95.0
        assert result["last_heartbeat"] == datetime(2026, 8, 2, 10, 0, 0)
        assert result["total_run_hours"] == 100.0
        assert result["is_online"] is True
        assert "timestamp" in result

    def test_offline_is_not_online(self):
        db = make_db(device=make_device(status=DeviceStatus.OFFLINE))
        result = DeviceDataService(db).get_health_status(1)
        assert result["status"] == "offline"
        assert result["is_online"] is False

    def test_status_none(self):
        # status=None: 兜底 "unknown"; is_online False; 空字段兜底默认值
        db = make_db(device=make_device(status=None, health_score=None, total_run_hours=None))
        result = DeviceDataService(db).get_health_status(1)
        assert result["status"] == "unknown"
        assert result["is_online"] is False
        assert result["health_score"] == 100.0     # None -> or 100.0
        assert result["total_run_hours"] == 0      # None -> or 0


# ═══════════════════════════════════════════════════════════════
# get_statistics
# ═══════════════════════════════════════════════════════════════

class TestGetStatistics:

    @pytest.mark.parametrize("agg,expected", [
        ("avg", 20.0),   # (10+20+30)/3
        ("max", 30.0),
        ("min", 10.0),
        ("sum", 60.0),   # 10+20+30
    ])
    def test_aggregations(self, agg, expected):
        records = [
            make_telemetry({"power": 10.0}),
            make_telemetry({"power": 20.0}),
            make_telemetry({"power": 30.0}),
        ]
        db = make_db(telemetry_records=records)

        result = DeviceDataService(db).get_statistics(1, metric="power", aggregation=agg)

        assert result["value"] == expected
        assert result["metric"] == "power"
        assert result["aggregation"] == agg
        assert result["count"] == 3
        assert result["device_id"] == 1
        assert result["hours"] == 24

    def test_no_history(self):
        db = make_db(telemetry_records=[])
        result = DeviceDataService(db).get_statistics(1)
        assert result == {"error": "无历史数据"}

    def test_no_metric(self):
        # 有历史但 data 不含目标 metric -> values 空
        records = [make_telemetry({"voltage": 220.0})]
        db = make_db(telemetry_records=records)
        result = DeviceDataService(db).get_statistics(1, metric="power")
        assert result == {"error": "无指标数据: power"}

    def test_unknown_aggregation(self):
        records = [make_telemetry({"power": 10.0})]
        db = make_db(telemetry_records=records)
        result = DeviceDataService(db).get_statistics(1, metric="power", aggregation="median")
        assert result == {"error": "未知的聚合方式: median"}

    def test_none_metric_values_skipped(self):
        # data 中指标值为 None 时跳过, 不让 sum([10, None, 30]) 抛 TypeError。
        # 遥测缺失值常见于传感器离线/字段未上报, service 层不应假设上游 data
        # dict 永远不含 None。
        records = [
            make_telemetry({"power": 10.0}),
            make_telemetry({"power": None}),
            make_telemetry({"power": 30.0}),
        ]
        db = make_db(telemetry_records=records)

        result = DeviceDataService(db).get_statistics(1, metric="power", aggregation="avg")

        # 仅 10 + 30 参与, avg = 20, count = 2
        assert result["value"] == 20.0
        assert result["count"] == 2


# ═══════════════════════════════════════════════════════════════
# 异常加固降级 (卡 f4288442)
# ═══════════════════════════════════════════════════════════════

def _db_query_raises():
    """db.query 整体抛异常 (模拟 DB 连接断开/查询失败)。"""
    db = MagicMock()
    db.query.side_effect = RuntimeError("db connection lost")
    return db


class TestExceptionHardening:
    """卡 f4288442: 4 个方法遇 DB 异常时降级返回 (空 dict/空 list), 不向上抛。"""

    async def test_realtime_db_error_returns_error_dict(self):
        db = _db_query_raises()
        result = await DeviceDataService(db).get_realtime_data(1)
        assert result == {"error": "服务内部错误，请稍后重试"}

    def test_history_db_error_returns_empty_list(self):
        db = _db_query_raises()
        result = DeviceDataService(db).get_history_data(1)
        assert result == []

    def test_health_db_error_returns_empty_dict(self):
        db = _db_query_raises()
        result = DeviceDataService(db).get_health_status(1)
        assert result == {}

    def test_statistics_db_error_returns_no_history(self):
        # get_statistics 调 get_history_data; 后者异常降级为 [] → 走「无历史数据」分支
        db = _db_query_raises()
        result = DeviceDataService(db).get_statistics(1)
        assert result == {"error": "无历史数据"}

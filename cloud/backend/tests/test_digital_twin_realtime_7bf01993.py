#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字孪生实时数据永久 mock 缺陷测试 (卡 7bf01993)

背景: digital_twin_handler 两处调用全代码库不存在的 DataCollectorService(),
NameError 被 except Exception 吞掉 → realtime_data 恒走
generate_mock_realtime_data 随机假数据, 真实遥测从未接通。

修复后: 按设备类型查遥测专表 (TelemetryPV/Battery/Charger, 兜底旧表
Telemetry) 最新一条记录构造 realtime_data; 无记录才 fallback mock 且
logger.warning。
"""
import logging
import uuid

import pytest

import app.ws.digital_twin_handler as dth_mod
from app.ws.digital_twin_handler import DigitalTwinHandler


# ─── seed 辅助 (复用 test_ws_coverage 模式) ──────────────────────────

def _patch_dth_session(test_db, monkeypatch):
    # handler 运行时读 app.core.database.SessionLocal, 须 patch 该模块属性
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", test_db["SessionLocal"])
    return test_db["session"]


def _seed_station(db, code):
    from app.models.station import Station, StationStatus
    st = Station(name=f"孪生站{code}", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def _seed_device(db, station_id, *, dtype, status, sn, code):
    from app.models.device import Device
    dev = Device(sn=sn, name=f"设备{code}", code=code, type=dtype,
                 status=status, station_id=station_id)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _seed_pv_telemetry(db, device_id, station_id, **kw):
    from app.models.telemetry_v2 import TelemetryPV
    rec = TelemetryPV(
        device_id=device_id, station_id=station_id,
        pv_power_total=kw.get("pv_power_total", 42.5),
        pv1_voltage=kw.get("pv1_voltage", 650.0),
        pv1_current=kw.get("pv1_current", 15.2),
        inv_temperature=kw.get("inv_temperature", 45.0),
        grid_frequency=kw.get("grid_frequency", 50.0),
        grid_power_factor=kw.get("grid_power_factor", 0.98),
        total_generation=kw.get("total_generation", 12345.0),
        daily_generation=kw.get("daily_generation", 234.0),
    )
    db.add(rec)
    db.commit()
    return rec


class TestRealtimeFromTelemetry:
    """有遥测记录 → realtime_data 用真实值, 不再恒 mock。"""

    def test_device_realtime_uses_pv_telemetry(self, test_db, monkeypatch):
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        suffix = uuid.uuid4().hex[:6]
        st = _seed_station(db, f"RT{suffix}")
        dev = _seed_device(db, st.id, dtype=DeviceType.PV_INVERTER,
                           status=DeviceStatus.ONLINE,
                           sn=f"SN-RT-PV-{suffix}", code=f"RTPV{suffix}")
        _seed_pv_telemetry(db, dev.id, st.id)

        result = DigitalTwinHandler().get_device_realtime_update(dev.id)
        rt = result["realtime_data"]
        assert rt["power_kw"] == pytest.approx(42.5)
        assert rt["voltage_v"] == pytest.approx(650.0)
        assert rt["current_a"] == pytest.approx(15.2)
        assert rt["total_generation_kwh"] == pytest.approx(12345.0)

    def test_station_payload_uses_pv_telemetry(self, test_db, monkeypatch):
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        suffix = uuid.uuid4().hex[:6]
        st = _seed_station(db, f"RS{suffix}")
        dev = _seed_device(db, st.id, dtype=DeviceType.PV_INVERTER,
                           status=DeviceStatus.ONLINE,
                           sn=f"SN-RT-STA-{suffix}", code=f"RTSTA{suffix}")
        _seed_pv_telemetry(db, dev.id, st.id, pv_power_total=7.7)

        result = DigitalTwinHandler().get_station_digital_twin_data(st.id)
        entry = next(d for d in result["devices"] if d["device"]["id"] == dev.id)
        assert entry["realtime_data"]["power_kw"] == pytest.approx(7.7)

    def test_latest_record_wins(self, test_db, monkeypatch):
        db = _patch_dth_session(test_db, monkeypatch)
        from datetime import datetime, timedelta, timezone
        from app.models.device import DeviceType, DeviceStatus
        from app.models.telemetry_v2 import TelemetryPV
        suffix = uuid.uuid4().hex[:6]
        st = _seed_station(db, f"RL{suffix}")
        dev = _seed_device(db, st.id, dtype=DeviceType.PV_INVERTER,
                           status=DeviceStatus.ONLINE,
                           sn=f"SN-RT-LT-{suffix}", code=f"RTLT{suffix}")
        now = datetime.now(timezone.utc)
        db.add(TelemetryPV(device_id=dev.id, station_id=st.id,
                           timestamp=now - timedelta(hours=1),
                           pv_power_total=1.0))
        db.add(TelemetryPV(device_id=dev.id, station_id=st.id,
                           timestamp=now, pv_power_total=99.9))
        db.commit()

        result = DigitalTwinHandler().get_device_realtime_update(dev.id)
        assert result["realtime_data"]["power_kw"] == pytest.approx(99.9)


class TestFallbackMockWithWarning:
    """无遥测记录 → fallback mock, 必须 logger.warning。"""

    def test_device_fallback_mock_warns(self, test_db, monkeypatch, caplog):
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        suffix = uuid.uuid4().hex[:6]
        st = _seed_station(db, f"RF{suffix}")
        dev = _seed_device(db, st.id, dtype=DeviceType.BATTERY,
                           status=DeviceStatus.ONLINE,
                           sn=f"SN-RT-FB-{suffix}", code=f"RTFB{suffix}")

        with caplog.at_level(logging.WARNING, logger=dth_mod.logger.name):
            result = DigitalTwinHandler().get_device_realtime_update(dev.id)
        rt = result["realtime_data"]
        assert "soc_percent" in rt  # battery mock 分支
        assert any("无遥测" in r.message or "fallback" in r.message.lower()
                   or "遥测" in r.message for r in caplog.records)

    def test_station_fallback_mock_warns(self, test_db, monkeypatch, caplog):
        db = _patch_dth_session(test_db, monkeypatch)
        from app.models.device import DeviceType, DeviceStatus
        suffix = uuid.uuid4().hex[:6]
        st = _seed_station(db, f"RW{suffix}")
        _seed_device(db, st.id, dtype=DeviceType.CHARGER_DC,
                     status=DeviceStatus.CHARGING,
                     sn=f"SN-RT-SFB-{suffix}", code=f"RTSFB{suffix}")

        with caplog.at_level(logging.WARNING, logger=dth_mod.logger.name):
            result = DigitalTwinHandler().get_station_digital_twin_data(st.id)
        assert result["devices"]
        assert "output_power_kw" in result["devices"][0]["realtime_data"]
        assert any("遥测" in r.message for r in caplog.records)


class TestNoSwallowedNameErrors:
    """两方法不得抛 NameError/UnboundLocalError。"""

    def test_device_method_clean(self, test_db, monkeypatch):
        _patch_dth_session(test_db, monkeypatch)
        DigitalTwinHandler().get_device_realtime_update(999977)

    def test_station_method_clean(self, test_db, monkeypatch):
        _patch_dth_session(test_db, monkeypatch)
        DigitalTwinHandler().get_station_digital_twin_data(999977)

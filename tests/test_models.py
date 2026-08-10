"""Tests for models/telemetry.py and models/device.py"""



from models.device import DeviceInfo, DeviceStatus, DeviceType, ProtocolType
from models.telemetry import DEVICE_ID_MAP, TelemetryBatch, TelemetryPoint, _load_device_id_map


class TestTelemetryPoint:
    """TelemetryPoint unit tests"""

    def test_telemetry_point_creation(self):
        """Test creating a telemetry point with all fields"""
        point = TelemetryPoint(
            device_id="CHARGER-001",
            power=50.0,
            voltage=220.5,
            current=32.0,
            temperature=45.2,
            energy=1200.0,
            soc=85.0,
            status="normal",
        )
        assert point.device_id == "CHARGER-001"
        assert point.power == 50.0
        assert point.voltage == 220.5
        assert point.current == 32.0
        assert point.temperature == 45.2
        assert point.energy == 1200.0
        assert point.soc == 85.0
        assert point.status == "normal"
        # timestamp should be auto-generated
        assert point.timestamp is not None

    def test_telemetry_point_defaults(self):
        """Test default values"""
        point = TelemetryPoint(device_id="METER-001")
        assert point.power == 0.0
        assert point.voltage == 0.0
        assert point.current == 0.0
        assert point.temperature == 0.0
        assert point.energy == 0.0
        assert point.soc is None
        assert point.status == "normal"

    def test_telemetry_point_to_dict(self):
        """Test to_dict() excludes None values"""
        point = TelemetryPoint(
            device_id="INVERTER-001",
            power=10.5,
            voltage=380.0,
            current=15.8,
            temperature=38.0,
            energy=500.0,
            soc=None,
            status="normal",
        )
        d = point.to_dict()
        assert d["device_id"] == "INVERTER-001"
        assert d["power"] == 10.5
        assert d["voltage"] == 380.0
        assert d["current"] == 15.8
        assert d["temperature"] == 38.0
        assert d["energy"] == 500.0
        assert d["status"] == "normal"
        # soc is None so it should be excluded
        assert "soc" not in d
        # timestamp should be present
        assert "timestamp" in d

    def test_telemetry_point_to_dict_no_none_values(self):
        """Test to_dict() excludes all None values"""
        point = TelemetryPoint(
            device_id="SENSOR-TEMP-01",
            temperature=28.5,
            soc=None,
        )
        d = point.to_dict()
        assert d["device_id"] == "SENSOR-TEMP-01"
        assert d["temperature"] == 28.5
        assert "soc" not in d

    def test_telemetry_point_to_api_payload(self):
        """Test to_api_payload() produces correct cloud V3 API format"""
        point = TelemetryPoint(
            device_id="CHARGER-001",
            timestamp="2026-06-22T12:00:00+00:00",
            power=75.0,
            voltage=230.0,
            current=35.0,
            temperature=42.0,
            energy=1500.0,
            soc=90.0,
            status="charging",
        )
        payload = point.to_api_payload()
        # CHARGER-001 maps to cloud device_id=2
        assert payload["device_id"] == 2
        # Charger fields mapped to charger_* schema
        assert payload["charger_power"] == 75.0
        assert payload["charger_voltage"] == 230.0
        assert payload["charger_current"] == 35.0
        assert payload["charger_soc"] == 90.0
        assert payload["charger_kwh"] == 1500.0
        assert payload["gun_temperature"] == 42.0

    def test_telemetry_point_to_api_payload_zero_values(self):
        """Test to_api_payload with zero values (unknown device → grid fields)"""
        point = TelemetryPoint(device_id="METER-001", timestamp="2026-01-01T00:00:00Z")
        payload = point.to_api_payload()
        # METER-001 not in DEVICE_ID_MAP, stays as string
        assert payload["device_id"] == "METER-001"
        # Zero values are filtered out (None check), so only device_id present
        assert "grid_power_total" not in payload  # 0.0 is falsy, filtered out


class TestDeviceIdMap:
    """DEVICE_ID_MAP and env override tests"""

    def test_default_device_id_map(self):
        """Default DEVICE_ID_MAP has expected entries"""
        assert DEVICE_ID_MAP["modbus-1"] == 1
        assert DEVICE_ID_MAP["CHARGER-001"] == 2
        assert DEVICE_ID_MAP["GW-001"] == 0

    def test_env_override_device_id_map(self, monkeypatch):
        """DEVICE_ID_MAP_JSON env var overrides defaults"""
        monkeypatch.setenv(
            "DEVICE_ID_MAP_JSON",
            '{"modbus-1": 10, "CHARGER-001": 6, "GW-001": 99}',
        )
        new_map = _load_device_id_map()
        assert new_map["modbus-1"] == 10
        assert new_map["CHARGER-001"] == 6
        assert new_map["GW-001"] == 99

    def test_env_override_partial(self, monkeypatch):
        """Partial env override replaces entire map (no merge)"""
        monkeypatch.setenv("DEVICE_ID_MAP_JSON", '{"foo": 42}')
        new_map = _load_device_id_map()
        assert new_map == {"foo": 42}

    def test_env_override_invalid_json(self, monkeypatch):
        """Invalid JSON falls back to defaults"""
        monkeypatch.setenv("DEVICE_ID_MAP_JSON", "not-json")
        new_map = _load_device_id_map()
        assert new_map == DEVICE_ID_MAP

    def test_env_override_non_dict(self, monkeypatch):
        """Non-dict JSON falls back to defaults"""
        monkeypatch.setenv("DEVICE_ID_MAP_JSON", '[1, 2, 3]')
        new_map = _load_device_id_map()
        assert new_map == DEVICE_ID_MAP

    def test_no_env_uses_defaults(self, monkeypatch):
        """No env var → defaults"""
        monkeypatch.delenv("DEVICE_ID_MAP_JSON", raising=False)
        new_map = _load_device_id_map()
        assert new_map == DEVICE_ID_MAP


class TestTelemetryBatch:
    """TelemetryBatch unit tests"""

    def test_telemetry_batch(self):
        """Test creating and adding to a telemetry batch"""
        batch = TelemetryBatch(gateway_id="GW-001")
        assert batch.gateway_id == "GW-001"
        assert len(batch.points) == 0
        assert batch.timestamp is not None

        point1 = TelemetryPoint(device_id="CHARGER-001", power=50.0)
        point2 = TelemetryPoint(device_id="CHARGER-002", power=75.0)
        batch.add(point1)
        batch.add(point2)

        assert len(batch.points) == 2
        assert batch.points[0].device_id == "CHARGER-001"
        assert batch.points[1].device_id == "CHARGER-002"

    def test_telemetry_batch_to_api_payload(self):
        """Test batch to_api_payload (V3 TelemetryBatchReport format)"""
        batch = TelemetryBatch(gateway_id="GW-001", timestamp="2026-06-22T12:00:00Z")
        batch.add(TelemetryPoint(
            device_id="CHARGER-001", timestamp="2026-06-22T12:00:00Z",
            power=50.0, voltage=220.0, current=30.0, temperature=40.0, energy=1000.0,
        ))
        batch.add(TelemetryPoint(
            device_id="modbus-1", timestamp="2026-06-22T12:00:00Z",
            power=-5.0, voltage=380.0, current=10.0, temperature=35.0, energy=200.0,
        ))

        payload = batch.to_api_payload()
        assert payload["pod_id"] == "GW-001"
        assert payload["region_id"] == "default"
        assert len(payload["records"]) == 2
        # CHARGER-001 → device_id=2, charger fields
        assert payload["records"][0]["device_id"] == 2
        assert payload["records"][0]["charger_power"] == 50.0
        # modbus-1 → device_id=1, grid/battery fields
        assert payload["records"][1]["device_id"] == 1
        assert payload["records"][1]["grid_power_total"] == -5.0

    def test_telemetry_batch_empty(self):
        """Test empty batch (V3 format)"""
        batch = TelemetryBatch(gateway_id="GW-002")
        payload = batch.to_api_payload()
        assert payload["pod_id"] == "GW-002"
        assert payload["region_id"] == "default"
        assert payload["records"] == []


class TestDeviceInfo:
    """DeviceInfo unit tests"""

    def test_device_info_creation(self):
        """Test creating a device info with all fields"""
        device = DeviceInfo(
            device_id="CHARGER-001",
            name="Main Charger",
            type=DeviceType.CHARGER,
            protocol=ProtocolType.OCPP,
            station_id="STATION-A",
            model="TL-AC-07kW",
            status=DeviceStatus.ONLINE,
            address="192.168.1.100",
            port=9000,
            unit_id=1,
            config={"max_power": 7000, "phases": 3},
        )
        assert device.device_id == "CHARGER-001"
        assert device.name == "Main Charger"
        assert device.type == DeviceType.CHARGER
        assert device.protocol == ProtocolType.OCPP
        assert device.station_id == "STATION-A"
        assert device.model == "TL-AC-07kW"
        assert device.status == DeviceStatus.ONLINE
        assert device.address == "192.168.1.100"
        assert device.port == 9000
        assert device.unit_id == 1
        assert device.config == {"max_power": 7000, "phases": 3}

    def test_device_info_defaults(self):
        """Test default values for device info"""
        device = DeviceInfo(
            device_id="METER-001",
            name="Main Meter",
            type=DeviceType.METER,
            protocol=ProtocolType.MODBUS_TCP,
        )
        assert device.station_id == ""
        assert device.model == ""
        assert device.status == DeviceStatus.OFFLINE
        assert device.address == ""
        assert device.port == 0
        assert device.unit_id == 1
        assert device.config == {}

    def test_device_info_to_dict(self):
        """Test to_dict() serialization"""
        device = DeviceInfo(
            device_id="BATTERY-001",
            name="Energy Storage",
            type=DeviceType.BATTERY,
            protocol=ProtocolType.MODBUS_TCP,
            status=DeviceStatus.CHARGING,
            address="192.168.1.50",
            port=502,
            unit_id=2,
            config={"capacity": 100, "soc_min": 20},
        )
        d = device.to_dict()
        assert d["device_id"] == "BATTERY-001"
        assert d["name"] == "Energy Storage"
        assert d["type"] == DeviceType.BATTERY
        assert d["protocol"] == ProtocolType.MODBUS_TCP
        assert d["status"] == DeviceStatus.CHARGING
        assert d["address"] == "192.168.1.50"
        assert d["port"] == 502
        assert d["unit_id"] == 2
        assert d["config"] == {"capacity": 100, "soc_min": 20}

    def test_device_info_from_dict(self):
        """Test from_dict() deserialization"""
        data = {
            "device_id": "SENSOR-001",
            "name": "Temperature Sensor",
            "type": DeviceType.SENSOR,
            "protocol": ProtocolType.MQTT,
            "station_id": "STATION-B",
            "model": "TL-TEMP-01",
            "status": DeviceStatus.ONLINE,
            "address": "192.168.1.200",
            "port": 0,
            "unit_id": 1,
            "config": {"range": (-40, 85)},
        }
        device = DeviceInfo.from_dict(data)
        assert device.device_id == "SENSOR-001"
        assert device.type == DeviceType.SENSOR
        assert device.protocol == ProtocolType.MQTT
        assert device.status == DeviceStatus.ONLINE
        assert device.config == {"range": (-40, 85)}


class TestDeviceStatusEnum:
    """DeviceStatus enum tests"""

    def test_device_status_enum(self):
        """Test all device status enum values"""
        assert DeviceStatus.ONLINE.value == "online"
        assert DeviceStatus.OFFLINE.value == "offline"
        assert DeviceStatus.FAULT.value == "fault"
        assert DeviceStatus.CHARGING.value == "charging"
        assert DeviceStatus.IDLE.value == "idle"

    def test_device_status_from_string(self):
        """Test creating DeviceStatus from string"""
        assert DeviceStatus("online") == DeviceStatus.ONLINE
        assert DeviceStatus("offline") == DeviceStatus.OFFLINE
        assert DeviceStatus("fault") == DeviceStatus.FAULT
        assert DeviceStatus("charging") == DeviceStatus.CHARGING
        assert DeviceStatus("idle") == DeviceStatus.IDLE

    def test_device_type_enum(self):
        """Test device type enum values"""
        assert DeviceType.CHARGER.value == "charger"
        assert DeviceType.INVERTER.value == "inverter"
        assert DeviceType.BATTERY.value == "battery"
        assert DeviceType.METER.value == "meter"
        assert DeviceType.SENSOR.value == "sensor"

    def test_protocol_type_enum(self):
        """Test protocol type enum values"""
        assert ProtocolType.OCPP.value == "ocpp"
        assert ProtocolType.MODBUS_TCP.value == "modbus_tcp"
        assert ProtocolType.MODBUS_RTU.value == "modbus_rtu"
        assert ProtocolType.MQTT.value == "mqtt"

"""Tests for config.py"""


from config import (
    GatewayConfig,
)


class TestGatewayConfig:
    """GatewayConfig unit tests"""

    def test_default_config(self):
        """Test default config values"""
        config = GatewayConfig()
        assert config.gateway_id == "GW-001"
        assert config.gateway_name == "RaspberryPi-Gateway"
        assert config.log_level == "INFO"

        # Cloud defaults (updated to production address)
        assert config.cloud.base_url == "http://8.134.106.166"
        assert config.cloud.ws_url == "ws://8.134.106.166/ws/v1"
        assert config.cloud.username == ""
        assert config.cloud.password == ""
        assert config.cloud.token == ""
        assert config.cloud.heartbeat_interval == 30

        # MQTT defaults
        assert config.mqtt.host == "localhost"
        assert config.mqtt.port == 1883
        assert config.mqtt.username == ""
        assert config.mqtt.password == ""
        assert config.mqtt.topic_prefix == "tianlian/gateway"
        assert config.mqtt.qos == 1
        assert config.mqtt.keepalive == 60

        # Modbus defaults
        assert config.modbus.host == "127.0.0.1"
        assert config.modbus.port == 502
        assert config.modbus.unit_id == 1
        assert config.modbus.timeout == 3.0
        assert config.modbus.poll_interval == 5
        assert config.modbus.registers == [0, 1, 2, 3, 4, 5]

        # OCPP defaults
        assert config.ocpp.charger_id == "CHARGER-001"
        assert config.ocpp.ws_url == "ws://localhost:9000"
        assert config.ocpp.heartbeat_interval == 300
        assert config.ocpp.meter_sample_interval == 10

        # Storage defaults
        assert config.storage.db_path == "data/gateway.db"
        assert config.storage.max_cache_size == 10000
        assert config.storage.retry_interval == 30
        assert config.storage.max_retries == 5

        # Local API defaults
        assert config.local_api.host == "0.0.0.0"
        assert config.local_api.port == 8080

    def test_default_config_is_isolated(self):
        """Test that each default config instance is isolated"""
        config1 = GatewayConfig()
        config2 = GatewayConfig()

        # Modifying one should not affect the other
        config2.gateway_id = "GW-002"
        config2.cloud.base_url = "http://custom.example.com/api"

        assert config1.gateway_id == "GW-001"
        assert config2.gateway_id == "GW-002"
        assert config1.cloud.base_url == "http://8.134.106.166"
        assert config2.cloud.base_url == "http://custom.example.com/api"

    def test_config_from_env(self, monkeypatch):
        """Test loading config from environment variables"""
        env_vars = {
            "GATEWAY_ID": "GW-ENV-001",
            "GATEWAY_NAME": "Env-Gateway",
            "CLOUD_BASE_URL": "https://cloud.example.com/api/v2",
            "CLOUD_USERNAME": "admin",
            "CLOUD_PASSWORD": "secret123",
            "MQTT_HOST": "mqtt.example.com",
            "MQTT_PORT": "8883",
            "MODBUS_HOST": "10.0.0.1",
            "MODBUS_PORT": "1502",
            "OCPP_CHARGER_ID": "CHARGER-ENV-001",
            "STORAGE_DB_PATH": "/data/custom/gateway.db",
            "LOG_LEVEL": "DEBUG",
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)

        config = GatewayConfig.from_env()

        assert config.gateway_id == "GW-ENV-001"
        assert config.gateway_name == "Env-Gateway"
        assert config.cloud.base_url == "https://cloud.example.com/api/v2"
        assert config.cloud.username == "admin"
        assert config.cloud.password == "secret123"
        assert config.mqtt.host == "mqtt.example.com"
        assert config.mqtt.port == 8883
        assert config.modbus.host == "10.0.0.1"
        assert config.modbus.port == 1502
        assert config.ocpp.charger_id == "CHARGER-ENV-001"
        assert config.storage.db_path == "/data/custom/gateway.db"
        assert config.log_level == "DEBUG"

        # Non-overridden fields should keep defaults
        assert config.cloud.ws_url == "ws://8.134.106.166/ws/v1"
        assert config.cloud.token == ""
        assert config.cloud.heartbeat_interval == 30
        assert config.mqtt.qos == 1
        assert config.mqtt.keepalive == 60

    def test_config_from_env_partial(self, monkeypatch):
        """Test loading config with only some env vars set"""
        monkeypatch.setenv("GATEWAY_ID", "GW-PARTIAL-001")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        config = GatewayConfig.from_env()
        assert config.gateway_id == "GW-PARTIAL-001"
        assert config.log_level == "WARNING"

        # Unset fields should fall back to defaults
        assert config.gateway_name == "RaspberryPi-Gateway"
        assert config.cloud.base_url == "http://8.134.106.166"
        assert config.modbus.port == 502
"""Edge Gateway Configuration"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class CloudConfig:
    """Cloud API configuration"""
    base_url: str = "http://8.134.106.166"  # 大圣统一入口; paths in cloud_client include /api/v1/
    ws_url: str = "ws://8.134.106.166/ws/v1"
    username: str = ""
    password: str = ""
    token: str = ""
    heartbeat_interval: int = 30  # seconds
    upload_interval: int = 15  # seconds between telemetry batch uploads (T-1202)
    register_on_startup: bool = True  # auto-register gateway with cloud
    deregister_on_shutdown: bool = True  # deregister on graceful shutdown


@dataclass
class MQTTConfig:
    """MQTT broker configuration"""
    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = ""
    topic_prefix: str = "tianlian/gateway"
    qos: int = 1
    keepalive: int = 60
    batch_size: int = 50  # max points per batch publish
    batch_interval: int = 10  # seconds between batch publishes


@dataclass
class ModbusConfig:
    """Modbus device configuration"""
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1
    timeout: float = 3.0
    poll_interval: int = 5  # seconds
    registers: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    use_real_modbus: bool = False  # True = real pymodbus, False = simulated
    retry_count: int = 3  # connection retries before falling back to simulation
    retry_delay: float = 2.0  # seconds between retries


@dataclass
class OCPPConfig:
    """OCPP charger configuration"""
    charger_id: str = "CHARGER-001"
    ws_url: str = "ws://localhost:9000"
    heartbeat_interval: int = 300  # seconds
    meter_sample_interval: int = 10  # seconds
    use_real_charger: bool = False  # True = real OCPP WebSocket, False = simulated
    charger_vendor: str = "Tianlian-Energy"  # vendor for BootNotification
    charger_model: str = "TL-EVSE-3000"  # model for BootNotification


@dataclass
class StorageConfig:
    """Local storage configuration"""
    db_path: str = "data/gateway.db"
    max_cache_size: int = 10000
    retry_interval: int = 30  # seconds between sync attempts
    max_retries: int = 5  # increased from 3 for better resilience
    batch_sync_size: int = 200  # max entries per sync cycle
    cleanup_interval: int = 3600  # seconds between cleanup runs


@dataclass
class LocalAPIConfig:
    """Local debug API configuration"""
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class GatewayConfig:
    """Master gateway configuration"""
    gateway_id: str = field(default_factory=lambda: os.getenv("GATEWAY_ID", "GW-001"))
    gateway_name: str = field(default_factory=lambda: os.getenv("GATEWAY_NAME", "RaspberryPi-Gateway"))
    cloud: CloudConfig = field(default_factory=CloudConfig)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    modbus: ModbusConfig = field(default_factory=ModbusConfig)
    ocpp: OCPPConfig = field(default_factory=OCPPConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    local_api: LocalAPIConfig = field(default_factory=LocalAPIConfig)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load config from environment variables"""
        return cls(
            gateway_id=os.getenv("GATEWAY_ID", "GW-001"),
            gateway_name=os.getenv("GATEWAY_NAME", "RaspberryPi-Gateway"),
            cloud=CloudConfig(
                base_url=os.getenv("CLOUD_BASE_URL", "http://8.134.106.166"),
                username=os.getenv("CLOUD_USERNAME", ""),
                password=os.getenv("CLOUD_PASSWORD", ""),
                register_on_startup=os.getenv("CLOUD_REGISTER", "true").lower() == "true",
                deregister_on_shutdown=os.getenv("CLOUD_DEREGISTER", "true").lower() == "true",
            ),
            mqtt=MQTTConfig(
                host=os.getenv("MQTT_HOST", "localhost"),
                port=int(os.getenv("MQTT_PORT", "1883")),
                client_id=os.getenv("MQTT_CLIENT_ID", ""),
                batch_size=int(os.getenv("MQTT_BATCH_SIZE", "50")),
                batch_interval=int(os.getenv("MQTT_BATCH_INTERVAL", "10")),
            ),
            modbus=ModbusConfig(
                host=os.getenv("MODBUS_HOST", "127.0.0.1"),
                port=int(os.getenv("MODBUS_PORT", "502")),
                use_real_modbus=os.getenv("MODBUS_REAL", "false").lower() == "true",
            ),
            ocpp=OCPPConfig(
                charger_id=os.getenv("OCPP_CHARGER_ID", "CHARGER-001"),
                use_real_charger=os.getenv("OCPP_REAL", "false").lower() == "true",
            ),
            storage=StorageConfig(
                db_path=os.getenv("STORAGE_DB_PATH", "data/gateway.db"),
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

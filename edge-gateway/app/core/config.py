"""
天链 V3 边缘网关 - 核心配置
"""
import os
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    sn: str = "TL-GW-001"
    name: str = "edge-gateway-01"
    model: str = "TL-GW-100"
    manufacturer: str = "天链科技"
    station_id: int = 1
    location: str = ""


class CloudConfig(BaseModel):
    api_base: str = "http://demo.example.com/api/v1"
    api_key: str = ""
    register_endpoint: str = "/gateways/register"
    heartbeat_endpoint: str = "/gateways/heartbeat"
    telemetry_endpoint: str = "/telemetry/report"


class HeartbeatConfig(BaseModel):
    interval_seconds: int = 30
    timeout_seconds: int = 10


class OcppConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9000
    max_connections: int = 100
    heartbeat_interval: int = 300


class ModbusDevice(BaseModel):
    name: str
    host: str
    port: int = 502
    unit_id: int = 1
    device_id: int = 0


class ModbusConfig(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 5
    timeout_seconds: int = 3
    retry_count: int = 3
    devices: List[ModbusDevice] = Field(default_factory=list)


class TelemetryConfig(BaseModel):
    report_interval_seconds: int = 10
    batch_size: int = 100
    max_retries: int = 3


class OfflineBufferConfig(BaseModel):
    enabled: bool = True
    db_path: str = "data/offline_buffer.db"
    max_buffer_size_mb: int = 500
    max_buffer_age_hours: int = 72
    retry_interval_seconds: int = 30


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file: str = "data/gateway.log"


class AppConfig(BaseModel):
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    ocpp: OcppConfig = Field(default_factory=OcppConfig)
    modbus: ModbusConfig = Field(default_factory=ModbusConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    offline_buffer: OfflineBufferConfig = Field(default_factory=OfflineBufferConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载配置文件"""
    if config_path is None:
        # 默认路径: config/settings.yaml (项目根目录)
        base_dir = Path(__file__).parent.parent.parent
        config_path = base_dir / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 环境变量覆盖
    env_prefix = "TL_GATEWAY_"
    for key, value in os.environ.items():
        if key.startswith(env_prefix):
            config_key = key[len(env_prefix):].lower()
            # 支持嵌套键 (用 __ 分隔)
            parts = config_key.split("__")
            target = data
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value

    return AppConfig(**data)


# 全局配置实例
config: AppConfig = load_config()

"""
数字孪生数据处理函数
整合 websocket_digital_twin.py 的数据查询逻辑
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import random
import logging
import threading

# SessionLocal 经 _db_module 运行时属性读取 (同 ws/auth.py:_lookup_active_user_sync,
# fleet_handler, realtime_handler): 确保 conftest 对 SessionLocal 的覆盖能传播到本模块,
# 否则测试期会直连陈旧开发库 tianlian_v3.db (卡 60596021 缺列根因)
from app.core import database as _db_module
from app.models.device import Device
from app.models.station import Station
from app.models.digital_twin import DigitalTwinModel, DigitalTwinScene, ThreeDModelType
from app.models.telemetry import Telemetry
from app.models.telemetry_v2 import get_telemetry_model_by_device_type

logger = logging.getLogger(__name__)

# 卡 ac881e11: 默认初始化段并发防护。DigitalTwinScene.station_id 无唯一约束,
# check-then-insert 竞态会重复建默认场景; 进程内用模块级锁串行化初始化,
# DigitalTwinModel.device_id 有 unique, 跨进程竞态由 IntegrityError 兜底。
_default_init_lock = threading.Lock()


class DigitalTwinHandler:
    """数字孪生数据处理器"""
    
    def get_station_digital_twin_data(self, station_id: int) -> dict:
        """获取站点的数字孪生完整数据"""
        db = _db_module.SessionLocal()
        try:
            # 查询站点
            station = db.query(Station).filter(Station.id == station_id).first()
            if not station:
                return {"error": f"站点 {station_id} 不存在"}
            
            # 查询站点下的所有设备
            devices = db.query(Device).filter(Device.station_id == station_id).all()

            # 卡 ac881e11: 批量预查询全部孪生配置 (一次 IN), 消除逐设备 N+1
            configs_by_device: dict[int, DigitalTwinModel] = {}
            if devices:
                for cfg in db.query(DigitalTwinModel).filter(
                    DigitalTwinModel.device_id.in_([d.id for d in devices])
                ).all():
                    configs_by_device[cfg.device_id] = cfg

            # 默认初始化段: 锁内 check-then-insert, 缺失项统一构造后单次 commit
            # (原实现 scene + 每设备各一事务 → N+1 次 commit)
            scene = None
            with _default_init_lock:
                scene = db.query(DigitalTwinScene).filter(
                    DigitalTwinScene.station_id == station_id
                ).first()

                scene_is_new = False
                if not scene:
                    # 创建默认场景
                    scene = DigitalTwinScene(
                        station_id=station_id,
                        name="default",
                        scene_config={
                            "background_color": "#1a1a1a",
                            "grid_enabled": True,
                            "lighting": {
                                "ambient_intensity": 0.5,
                                "directional_intensity": 1.0,
                                "point_intensity": 0.3
                            },
                            "camera": {
                                "initial_position": {"x": 20, "y": 20, "z": 20},
                                "look_at": {"x": 0, "y": 0, "z": 0}
                            }
                        }
                    )
                    db.add(scene)
                    scene_is_new = True

                new_configs = []
                for device in devices:
                    if device.id not in configs_by_device:
                        twin_config = self.create_default_digital_twin_config(db, device)
                        configs_by_device[device.id] = twin_config
                        new_configs.append(twin_config)

                if scene_is_new or new_configs:
                    db.add_all(new_configs)
                    try:
                        db.commit()
                    except IntegrityError:
                        # 跨进程竞态兜底: device_id unique 被并发插入抢占
                        db.rollback()
                        configs_by_device, scene = self._recover_after_init_race(
                            db, station_id, devices
                        )

            device_list = []
            for device in devices:
                twin_config = configs_by_device[device.id]

                # 获取实时数据 (卡 7bf01993: 接通遥测表, 无记录才 fallback mock)
                realtime_data = self.get_realtime_from_telemetry(db, device)
                if realtime_data is None:
                    logger.warning("设备%d无遥测记录, 站级孪生数据降级 mock", device.id)

                device_list.append({
                    "device": {
                        "id": device.id,
                        "name": device.name,
                        "type": device.type.value if device.type else "unknown",
                        "status": device.status.value if device.status else "offline",
                        "health_score": device.health_score or 100,
                        "model": device.model or "",
                        "location": device.location or "",
                        "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
                        "created_at": device.created_at.isoformat() if device.created_at else None,
                    },
                    "digital_twin_config": {
                        "id": twin_config.id,
                        "model_type": twin_config.model_type.value if twin_config.model_type else "generic",
                        "scale_x": twin_config.scale_x or 1.0,
                        "scale_y": twin_config.scale_y or 1.0,
                        "scale_z": twin_config.scale_z or 1.0,
                        "position_x": twin_config.position_x or 0.0,
                        "position_y": twin_config.position_y or 0.0,
                        "position_z": twin_config.position_z or 0.0,
                        "rotation_x": twin_config.rotation_x or 0.0,
                        "rotation_y": twin_config.rotation_y or 0.0,
                        "rotation_z": twin_config.rotation_z or 0.0,
                        "color_primary": twin_config.color_primary or "#1890ff",
                        "color_secondary": twin_config.color_secondary or "#52c41a",
                        "color_accent": twin_config.color_accent or "#fa8c16",
                        "animations": twin_config.animations or {},
                        "status_mapping": twin_config.status_mapping or {},
                    },
                    "realtime_data": realtime_data or self.generate_mock_realtime_data(device)
                })

            return {
                "station": {
                    "id": station.id,
                    "name": station.name,
                    "address": station.address,
                    "status": station.status or "normal",
                    "latitude": station.lat,   # 列名是 lat/lon (卡 e2ad0b7d: 原 latitude/longitude 属性不存在)
                    "longitude": station.lon,
                    "created_at": station.created_at.isoformat() if station.created_at else None,
                },
                "scene": {
                    "id": scene.id,
                    "name": scene.name,
                    "scene_config": scene.scene_config or {},
                    "created_at": scene.created_at.isoformat() if scene.created_at else None,
                    "updated_at": scene.updated_at.isoformat() if scene.updated_at else None,
                },
                "devices": device_list,
                "update_time": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()

    def _recover_after_init_race(
        self, db: Session, station_id: int, devices: list[Device]
    ) -> tuple[dict[int, DigitalTwinModel], DigitalTwinScene]:
        """初始化 commit 撞 IntegrityError 后的重查兜底 (卡 ac881e11)。

        rollback 已清空本次待写对象; 重新批量查询 scene + 孪生配置,
        仍缺的配置再补一批单次 commit (锁内调用, 竞态窗口已收缩到极小)。
        """
        scene = db.query(DigitalTwinScene).filter(
            DigitalTwinScene.station_id == station_id
        ).first()
        if not scene:
            scene = DigitalTwinScene(
                station_id=station_id,
                name="default",
                scene_config={"background_color": "#1a1a1a"},
            )
            db.add(scene)
            db.commit()

        configs: dict[int, DigitalTwinModel] = {}
        if devices:
            for cfg in db.query(DigitalTwinModel).filter(
                DigitalTwinModel.device_id.in_([d.id for d in devices])
            ).all():
                configs[cfg.device_id] = cfg

        retry = []
        for device in devices:
            if device.id not in configs:
                cfg = self.create_default_digital_twin_config(db, device)
                configs[device.id] = cfg
                retry.append(cfg)
        if retry:
            db.add_all(retry)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                for cfg in db.query(DigitalTwinModel).filter(
                    DigitalTwinModel.device_id.in_([d.id for d in devices])
                ).all():
                    configs[cfg.device_id] = cfg
        return configs, scene

    def get_realtime_from_telemetry(self, db: Session, device: Device) -> Optional[dict]:
        """取设备最新一条遥测记录构造 realtime_data (卡 7bf01993)。

        按设备类型路由遥测专表 (TelemetryPV/Battery/Charger), 未映射类型
        兜底旧 Telemetry 宽表。无记录返回 None → 调用方 fallback mock。
        """
        device_type = device.type.value if device.type else None
        model_cls = get_telemetry_model_by_device_type(device_type)
        if model_cls is None:
            model_cls = Telemetry
        record = (
            db.query(model_cls)
            .filter(model_cls.device_id == device.id)
            .order_by(model_cls.timestamp.desc())
            .first()
        )
        if record is None:
            return None

        data = {
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "status": device.status.value if device.status else "offline",
            "health_score": device.health_score or 100,
        }

        def _pick(*names):
            for n in names:
                v = getattr(record, n, None)
                if v is not None:
                    return v
            return None

        if model_cls is not None and model_cls.__name__ == "TelemetryPV":
            power = _pick("pv_power_total", "grid_power_total")
            data.update({
                "power_kw": power,
                "voltage_v": _pick("pv1_voltage", "grid_voltage_a"),
                "current_a": _pick("pv1_current", "grid_current_a"),
                "temperature_c": _pick("inv_temperature", "internal_temperature"),
                "frequency_hz": record.grid_frequency,
                "power_factor": record.grid_power_factor,
                "total_generation_kwh": record.total_generation,
                "daily_generation_kwh": record.daily_generation,
            })
        elif model_cls.__name__ == "TelemetryBattery":
            power = _pick("battery_power", "grid_power_total")
            data.update({
                "soc_percent": record.battery_soc,
                "voltage_v": record.battery_voltage,
                "current_a": record.battery_current,
                "temperature_c": record.battery_temperature,
                "charge_power_kw": power if (power or 0) >= 0 else 0.0,
                "discharge_power_kw": -power if (power or 0) < 0 else 0.0,
                "total_charge_kwh": record.total_charge,
                "total_discharge_kwh": record.total_discharge,
            })
        elif model_cls.__name__ == "TelemetryCharger":
            data.update({
                "output_power_kw": record.charger_power,
                "voltage_v": record.charger_voltage,
                "current_a": record.charger_current,
                "temperature_c": _pick("gun_temperature", "internal_temperature"),
                "energy_delivered_kwh": record.charger_kwh,
                "vehicle_soc_percent": record.charger_soc,
                "gun_status": record.gun_status,
            })
        else:  # 旧 Telemetry 宽表, 按设备类型就近取列
            if device_type in ("battery", "battery_inverter", "pcs"):
                data.update({
                    "soc_percent": record.battery_soc,
                    "voltage_v": record.battery_voltage,
                    "current_a": record.battery_current,
                    "temperature_c": record.battery_temperature,
                    "charge_power_kw": record.battery_power if (record.battery_power or 0) >= 0 else 0.0,
                    "discharge_power_kw": -record.battery_power if (record.battery_power or 0) < 0 else 0.0,
                })
            elif device_type in ("charger_dc", "charger_ac"):
                data.update({
                    "output_power_kw": record.charger_power,
                    "voltage_v": record.charger_voltage,
                    "current_a": record.charger_current,
                    "temperature_c": record.gun_temperature,
                    "energy_delivered_kwh": record.charger_kwh,
                })
            else:
                data.update({
                    "power_kw": _pick("pv_power_total", "inv_power_total", "grid_power_total"),
                    "voltage_v": _pick("pv1_voltage", "inv_voltage_a", "grid_voltage_a"),
                    "current_a": _pick("pv1_current", "inv_current_a", "grid_current_a"),
                    "temperature_c": _pick("inv_temperature", "internal_temperature"),
                })

        # 剔除 None 度量, 结构与 mock 对齐但只带真实存在的值
        return {k: v for k, v in data.items() if v is not None or k in ("timestamp",)}

    def get_device_realtime_update(self, device_id: int) -> dict:
        db = _db_module.SessionLocal()
        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                return {"error": f"设备 {device_id} 不存在"}
            
            # 获取实时遥测数据 (卡 7bf01993: 接通遥测表, 无记录才 fallback mock)
            realtime_data = self.get_realtime_from_telemetry(db, device)
            if realtime_data is None:
                logger.warning("设备%d无遥测记录, 实时推送降级 mock", device_id)
                realtime_data = self.generate_mock_realtime_data(device)
            
            return {
                "device_id": device_id,
                "device_name": device.name,
                "status": device.status.value if device.status else "offline",
                "health_score": device.health_score or 100,
                "realtime_data": realtime_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()
    
    def create_default_digital_twin_config(self, db: Session, device: Device) -> DigitalTwinModel:
        """创建设备的默认数字孪生配置"""
        # 根据设备类型确定3D模型类型
        device_type_mapping = {
            "inverter": ThreeDModelType.SOLAR_INVERTER,
            "pv_inverter": ThreeDModelType.SOLAR_INVERTER,
            "battery_inverter": ThreeDModelType.BATTERY_INVERTER,
            "battery": ThreeDModelType.BATTERY_RACK,
            "charger_dc": ThreeDModelType.CHARGER_DC,
            "charger_ac": ThreeDModelType.CHARGER_AC,
            "gateway": ThreeDModelType.GATEWAY,
            "pcs": ThreeDModelType.PCS,
            "meter": ThreeDModelType.METER,
        }
        
        # ThreeDModelType 无 GENERIC 成员 (枚举只有 10 种具体模型), 未知类型
        # 回退 GATEWAY 兜底 (卡 e2ad0b7d: 原 ThreeDModelType.GENERIC 抛
        # AttributeError, 杀死 WS station 端点的 initial_data 推送 → 1011 断连)
        model_type = device_type_mapping.get(
            device.type.value if device.type else "gateway",
            ThreeDModelType.GATEWAY
        )

        # 根据设备类型设置默认配置
        default_configs = {
            ThreeDModelType.SOLAR_INVERTER: {
                "scale_x": 1.5, "scale_y": 1.0, "scale_z": 1.0,
                "color_primary": "#1890ff",  # 蓝色
            },
            ThreeDModelType.BATTERY_RACK: {
                "scale_x": 1.0, "scale_y": 1.5, "scale_z": 1.0,
                "color_primary": "#52c41a",  # 绿色
            },
            ThreeDModelType.CHARGER_DC: {
                "scale_x": 0.5, "scale_y": 2.0, "scale_z": 0.5,
                "color_primary": "#faad14",  # 橙色
            },
            ThreeDModelType.GATEWAY: {
                "scale_x": 0.8, "scale_y": 0.8, "scale_z": 0.8,
                "color_primary": "#722ed1",  # 紫色
            },
        }
        
        default_config = default_configs.get(model_type, {
            "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
            "color_primary": "#666666",  # 灰色
        })
        
        # 默认状态映射
        status_mapping = {
            "online": {
                "color": "#52c41a",  # 绿色
                "animation": "pulse",
                "intensity": 0.8
            },
            "offline": {
                "color": "#888888",  # 灰色
                "animation": "none",
                "intensity": 0.3
            },
            "charging": {
                "color": "#faad14",  # 橙色
                "animation": "glow",
                "intensity": 1.0
            },
            "fault": {
                "color": "#ff4d4f",  # 红色
                "animation": "blink",
                "intensity": 1.0
            },
            "maintenance": {
                "color": "#1890ff",  # 蓝色
                "animation": "slow_pulse",
                "intensity": 0.6
            }
        }
        
        config = DigitalTwinModel(
            device_id=device.id,
            model_type=model_type,
            scale_x=default_config["scale_x"],
            scale_y=default_config["scale_y"],
            scale_z=default_config["scale_z"],
            color_primary=default_config["color_primary"],
            color_secondary="#ffffff",
            color_accent="#ff4d4f",
            animations={"default": "idle"},
            status_mapping=status_mapping,
            position_x=0.0,
            position_y=0.0,
            position_z=0.0,
            rotation_x=0.0,
            rotation_y=0.0,
            rotation_z=0.0,
        )
        
        return config
    
    def generate_mock_realtime_data(self, device: Device) -> dict:
        """生成模拟实时数据(开发环境使用)"""
        base_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": device.status.value if device.status else "offline",
            "health_score": device.health_score or 100,
        }
        
        # 根据设备类型添加特定数据
        device_type = device.type.value if device.type else "generic"
        
        if device_type in ["inverter", "pv_inverter"]:
            base_data.update({
                "power_kw": random.uniform(10, 100),
                "voltage_v": random.uniform(200, 800),
                "current_a": random.uniform(10, 200),
                "temperature_c": random.uniform(25, 70),
                "efficiency": random.uniform(0.85, 0.98),
                "frequency_hz": 50.0,
                "power_factor": random.uniform(0.95, 1.0),
                "total_generation_kwh": random.uniform(1000, 50000),
                "daily_generation_kwh": random.uniform(100, 500),
            })
        elif device_type in ["battery", "battery_rack"]:
            base_data.update({
                "soc_percent": random.uniform(20, 100),
                "voltage_v": random.uniform(400, 800),
                "current_a": random.uniform(-100, 100),  # 负值表示放电
                "temperature_c": random.uniform(20, 40),
                "charge_power_kw": random.uniform(0, 50),
                "discharge_power_kw": random.uniform(0, 50),
                "capacity_kwh": random.uniform(100, 500),
                "remaining_kwh": random.uniform(20, 500),
                "cycle_count": random.randint(100, 1000),
            })
        elif device_type in ["charger_dc", "charger_ac"]:
            base_data.update({
                "output_power_kw": random.uniform(0, 120),
                "voltage_v": random.uniform(400, 1000),
                "current_a": random.uniform(0, 300),
                "temperature_c": random.uniform(25, 60),
                "charging_time_min": random.randint(0, 60),
                "energy_delivered_kwh": random.uniform(0, 100),
                "connector_status": "connected" if device.status.value == "online" else "disconnected",
                "max_power_kw": 120.0,
            })
        else:
            # 通用设备数据
            base_data.update({
                "power_kw": random.uniform(0, 10),
                "voltage_v": random.uniform(200, 400),
                "current_a": random.uniform(0, 50),
                "temperature_c": random.uniform(20, 50),
                "operating_hours": random.randint(100, 10000),
                "uptime_percent": random.uniform(95, 100),
            })
        
        return base_data
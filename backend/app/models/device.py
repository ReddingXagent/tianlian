"""
设备模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, ForeignKey, Float, Enum as SQLEnum, Date, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class DeviceType(str, enum.Enum):
    CHARGER_DC = "charger_dc"      # 直流充电桩
    CHARGER_AC = "charger_ac"      # 交流充电桩
    V2G_CHARGER = "v2g_charger"    # V2G双向充电桩
    PV_INVERTER = "pv_inverter"    # 光伏逆变器
    BATTERY_INVERTER = "battery_inverter"  # 储能逆变器（EAHI5-20K）
    PCS = "pcs"                    # 储能变流器（50kW PCS）
    BATTERY = "battery"            # 储能电池柜
    METER = "meter"                # 电表
    GATEWAY = "gateway"            # 网关

class ProtocolType(str, enum.Enum):
    """协议类型 - 基于光储充协议分析"""
    MODBUS_RTU = "modbus_rtu"      # Modbus-RTU（RS485）- 逆变器/PCS
    MQTT = "mqtt"                  # MQTT 3.1.1 - 充电桩
    MODBUS_TCP = "modbus_tcp"      # Modbus-TCP - 网关采集
    CAN = "can"                    # CAN总线 - BMS
    OPCUA = "opcua"                # OPC UA - EMS
    YKC = "ykc"                    # 云快充 V1.6 - 直流充电桩 TCP 直连
    SZBUS = "szbus"                # 深圳巴士 V1.09 - 充电桩 TCP 直连

class DeviceStatus(str, enum.Enum):
    ONLINE = "online"          # 在线
    OFFLINE = "offline"        # 离线
    CHARGING = "charging"      # 充电中
    FAULT = "fault"           # 故障
    MAINTENANCE = "maintenance"  # 维护中

class ProvisionStatus(str, enum.Enum):
    """设备入网状态（任务卡 1256e7fa）。

    - unprovisioned: 已登记、未发放凭证/未接入
    - provisioning:  凭证已生成、待设备首次连接
    - online:        网关侧首次连接成功（gateway/ocpp.py 钩子置位）
    """
    UNPROVISIONED = "unprovisioned"
    PROVISIONING = "provisioning"
    ONLINE = "online"

class Device(Base):
    """设备表 - 扩展协议与通信参数"""
    __tablename__ = "devices"
    
    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    
    # 基础信息
    sn = Column(String(100), unique=True, nullable=False, index=True)  # 序列号
    name = Column(String(100), nullable=False, index=True)
    code = Column(String(50), unique=True, index=True)  # 设备编码
    
    # 类型和型号
    type = Column(SQLEnum(DeviceType), nullable=False, index=True)
    model = Column(String(100))  # 型号（如EAHI5-20K-TH-G3）
    manufacturer = Column(String(100))  # 厂商（易事特）
    brand = Column(String(50))  # 品牌
    
    # ========== 协议相关（新增）==========
    protocol_type = Column(SQLEnum(ProtocolType), index=True)  # 协议类型
    device_address = Column(Integer)  # 设备地址（Modbus从机地址1-247）
    tcu_address = Column(String(50))  # TCU地址（充电桩MQTT）
    
    # 固件信息
    firmware_version = Column(String(20))  # 固件版本
    hardware_version = Column(String(20))  # 硬件版本
    
    # ========== 通信参数（Modbus）==========
    modbus_baudrate = Column(Integer, default=9600)  # 波特率
    modbus_databits = Column(Integer, default=8)  # 数据位
    modbus_parity = Column(String(10), default="none")  # 校验（odd/even/none）
    modbus_stopbits = Column(Integer, default=1)  # 停止位
    modbus_timeout_ms = Column(Integer, default=3000)  # 超时（毫秒）
    modbus_retry_count = Column(Integer, default=2)  # 重试次数
    
    # ========== 通信参数（MQTT）==========
    mqtt_client_id = Column(String(100))  # MQTT客户端ID
    mqtt_qos = Column(Integer, default=1)  # QoS等级
    mqtt_keepalive = Column(Integer, default=60)  # 心跳间隔（秒）

    # ========== 统一通信配置（JSON）==========
    comm_config = Column(JSON)  # 通信配置（支持动态扩展）
    # 示例：{"port": "/dev/ttyUSB0", "baudrate": 9600, "device_address": 1}
    
    # ========== 额定参数 ==========
    rated_power = Column(Float)  # 额定功率 kW
    rated_voltage = Column(Float)  # 额定电压 V
    rated_current = Column(Float)  # 额定电流 A
    gun_count = Column(Integer, default=1)  # 枪数量
    
    # ========== 所属站点 ==========
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    gateway_id = Column(Integer, ForeignKey("gateways.id"), index=True)  # 所属网关

    # ========== 入网状态 + 接入凭证（任务卡 1256e7fa）==========
    # 入网状态：unprovisioned → provisioning(凭证已发放) → online(首次连接成功)
    provision_status = Column(
        SQLEnum(ProvisionStatus, values_callable=lambda x: [e.value for e in x]),
        default=ProvisionStatus.UNPROVISIONED,
        nullable=False,
        index=True,
        comment="入网状态: unprovisioned/provisioning/online",
    )
    # OCPP 接入标识（充电桩 chargeBoxId；创建时默认=sn，与 charging_sessions 的
    # charge_point_id→Device.sn 映射一致，保留独立列供未来分离）
    charge_box_id = Column(String(100), index=True, comment="OCPP chargeBoxId")
    # MQTT 接入凭证（仅创建响应一次性返回明文 password；列存供网关校验连接）
    mqtt_username = Column(String(100), index=True, comment="MQTT 接入用户名")
    mqtt_password = Column(String(200), comment="MQTT 接入密码(一次性下发)")
    # 通用接入令牌（Modbus/REST 等无用户名密码的协议用 token 鉴权）
    auth_token = Column(String(200), comment="通用接入令牌(一次性下发)")
    
    # 位置
    location = Column(String(200))  # 位置描述
    
    # ========== 状态 ==========
    status = Column(SQLEnum(DeviceStatus), default=DeviceStatus.ONLINE)
    health_score = Column(Float, default=100.0)  # 健康度
    last_health_check = Column(DateTime(timezone=True))  # 最后健康检测时间
    last_heartbeat = Column(DateTime(timezone=True))  # 最后心跳时间
    
    # ========== 运行统计 ==========
    total_run_hours = Column(Float, default=0)  # 累积运行小时
    total_charge_kwh = Column(Float, default=0)  # 累积充电电量
    total_discharge_kwh = Column(Float, default=0)  # 累积放电电量
    total_generation_kwh = Column(Float, default=0)  # 累积发电量
    
    # ========== 设备效率 (V3 新增) ==========
    utilization_rate = Column(Float, default=0.0, comment='设备利用率(%)')
    pv_pr_ratio = Column(Float, default=None, nullable=True, comment='光伏PR性能比')
    rated_power_kw = Column(Float, default=None, nullable=True, comment='额定功率(kW)')
    last_runtime_hours = Column(Float, default=0.0, comment='最后运行时长(h)')
    total_runtime_hours = Column(Float, default=0.0, comment='累计运行时长(h)')
    
    # ========== 维护 ==========
    last_maintenance = Column(Date)
    
    # ========== 数字孪生配置 ==========
    digital_twin_config = relationship("DigitalTwinModel", back_populates="device", uselist=False)
    next_maintenance = Column(Date)
    maintenance_interval_days = Column(Integer, default=90)  # 维护周期
    
    # ========== 时间 ==========
    install_date = Column(Date)
    warranty_expire_date = Column(Date)  # 保修到期
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    @property
    def device_type(self):
        """兼容 device_type 调用：将 type 枚举值转为简约字符串"""
        type_map = {
            "pv_inverter": "inverter",
            "battery_inverter": "inverter",
            "charger_dc": "charger",
            "charger_ac": "charger",
            "pcs": "inverter",
            "battery": "battery",
            "meter": "meter",
            "gateway": "gateway",
        }
        return type_map.get(self.type.value if hasattr(self.type, 'value') else self.type, "unknown")

    # 关系
    station = relationship("Station", back_populates="devices")
    gateway = relationship("Gateway", back_populates="devices")
    health_records = relationship("DeviceHealthRecord", back_populates="device", cascade="all, delete-orphan")
    # Phase1: 新增遥测专表关系
    telemetry_pv_records = relationship("TelemetryPV", back_populates="device", cascade="all, delete-orphan")
    telemetry_battery_records = relationship("TelemetryBattery", back_populates="device", cascade="all, delete-orphan")
    telemetry_charger_records = relationship("TelemetryCharger", back_populates="device", cascade="all, delete-orphan")
    # 向后兼容：保留旧表关系
    telemetry_records = relationship("Telemetry", back_populates="device", cascade="all, delete-orphan")
    workorders = relationship("WorkOrder", back_populates="device")
    alarms = relationship("Alarm", back_populates="device")
    analytics_results = relationship("AnalyticsResult", back_populates="device", cascade="all, delete-orphan")
    prediction_alerts = relationship("PredictionAlert", back_populates="device", cascade="all, delete-orphan")
    health_history = relationship("DeviceHealthHistory", back_populates="device", cascade="all, delete-orphan")
    maintenance_records = relationship("MaintenanceRecord", back_populates="device")
    control_logs = relationship("DeviceControlLog", back_populates="device", cascade="all, delete-orphan")
    efficiency_logs = relationship("DeviceEfficiencyLog", back_populates="device", cascade="all, delete-orphan")
    v2g_dispatch_logs = relationship("V2GDispatchLog", back_populates="device", cascade="all, delete-orphan")

class DeviceHealthRecord(Base):
    """设备健康度记录表"""
    __tablename__ = "device_health_records"
    __table_args__ = (
        Index('ix_dhr_device_created', 'device_id', 'created_at'),
        Index('ix_dhr_created_at', 'created_at'),
    )

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    
    # 5 维度评分
    electrical_safe_score = Column(Integer)  # 电气安全 (0-100)
    thermal_score = Column(Integer)  # 热稳定性
    comm_score = Column(Integer)  # 通信可靠性
    power_quality_score = Column(Integer)  # 电能质量
    mechanical_score = Column(Integer)  # 机械寿命
    
    # 总分
    total_score = Column(Float)
    
    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    device = relationship("Device", back_populates="health_records")

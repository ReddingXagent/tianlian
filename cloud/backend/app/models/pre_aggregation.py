"""
天链 V2 Phase1 - 预聚合模型
用于减少实时聚合查询的原始数据扫描量

聚合维度:
- StationHourlyStats: 场站小时聚合
- DeviceDailyStats: 设备日聚合
"""
from datetime import datetime, timedelta
from sqlalchemy import Column, BigInteger, Integer, String, Float, DateTime, ForeignKey, Index, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class StationHourlyStats(Base):
    """场站小时聚合统计表
    
    每小时聚合场站所有设备的关键指标，减少实时查询压力
    """
    __tablename__ = "station_hourly_stats"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, index=True)
    hour = Column(DateTime(timezone=True), nullable=False)  # 聚合小时时间点
    
    # ========== 区域路由字段 ==========
    region_id = Column(String(32), default="default", nullable=False, index=True)
    pod_id = Column(String(32), default="pod-01", nullable=False, index=True)
    
    # ========== 总体功率统计 ==========
    avg_total_power = Column(Float)    # 平均总功率 kW
    max_total_power = Column(Float)    # 最大总功率 kW
    min_total_power = Column(Float)    # 最小总功率 kW
    
    # ========== 光伏统计 ==========
    avg_pv_power = Column(Float)       # 平均光伏功率 kW
    max_pv_power = Column(Float)       # 最大光伏功率 kW
    pv_generation_kwh = Column(Float)  # 光伏发电量 kWh
    
    # ========== 储能统计 ==========
    avg_battery_soc = Column(Float)    # 平均电池SOC %
    avg_battery_power = Column(Float)  # 平均电池功率 kW
    charge_kwh = Column(Float)         # 充电量 kWh
    discharge_kwh = Column(Float)      # 放电量 kWh
    
    # ========== 充电桩统计 ==========
    avg_charger_power = Column(Float)  # 平均充电功率 kW
    max_charger_power = Column(Float)  # 最大充电功率 kW
    charger_kwh = Column(Float)        # 充电电量 kWh
    charging_sessions = Column(Integer, default=0)  # 充电次数
    
    # ========== 温度统计 ==========
    avg_temperature = Column(Float)    # 平均温度 ℃
    max_temperature = Column(Float)    # 最高温度 ℃
    
    # ========== 设备统计 ==========
    device_count = Column(Integer)      # 设备数量
    online_devices = Column(Integer)    # 在线设备数
    fault_devices = Column(Integer)     # 故障设备数
    
    # ========== 数据点统计 ==========
    data_points = Column(Integer)       # 数据点数
    uptime_minutes = Column(Integer)    # 运行时长分钟
    
    # ========== 时间 ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== 复合索引 ==========
    __table_args__ = (
        Index('idx_station_hourly_station_time', 'station_id', 'hour'),
        Index('idx_station_hourly_region', 'region_id', 'hour'),
    )
    
    # 关系
    station = relationship("Station")


class DeviceDailyStats(Base):
    """设备日聚合统计表
    
    每天聚合单个设备的关键指标，用于日报表和历史趋势分析
    """
    __tablename__ = "device_daily_stats"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)  # 聚合日期
    
    # ========== 区域路由字段 ==========
    region_id = Column(String(32), default="default", nullable=False, index=True)
    pod_id = Column(String(32), default="pod-01", nullable=False, index=True)
    
    # ========== 设备类型 ==========
    device_type = Column(String(50), index=True)  # 设备类型
    
    # ========== 功率统计 ==========
    avg_power = Column(Float)       # 平均功率 kW
    max_power = Column(Float)       # 最大功率 kW
    min_power = Column(Float)       # 最小功率 kW
    
    # ========== 光伏设备专用 ==========
    avg_pv_power = Column(Float)    # 平均光伏功率
    pv_generation_kwh = Column(Float)  # 光伏发电量 kWh
    peak_sun_hours = Column(Float)  # 峰值日照小时
    
    # ========== 储能设备专用 ==========
    avg_soc = Column(Float)         # 平均SOC %
    avg_soh = Column(Float)         # 平均SOH %
    charge_kwh = Column(Float)      # 充电量 kWh
    discharge_kwh = Column(Float)   # 放电量 kWh
    cycle_count = Column(Integer, default=0)  # 循环次数
    
    # ========== 充电桩专用 ==========
    avg_charger_power = Column(Float)  # 平均充电功率
    charger_kwh = Column(Float)        # 充电量 kWh
    charging_sessions = Column(Integer, default=0)  # 充电次数
    avg_session_duration = Column(Float)  # 平均充电时长分钟
    
    # ========== 温度统计 ==========
    avg_internal_temp = Column(Float)  # 平均内部温度 ℃
    max_internal_temp = Column(Float)  # 最高内部温度 ℃
    avg_ambient_temp = Column(Float)   # 平均环境温度
    
    # ========== 电能统计 ==========
    total_generation = Column(Float)  # 总发电量 kWh
    total_consumption = Column(Float)  # 总用电量 kWh
    
    # ========== 运行统计 ==========
    uptime_minutes = Column(Integer)    # 运行时长分钟
    downtime_minutes = Column(Integer)   # 停机时长分钟
    data_points = Column(Integer)        # 数据点数
    avg_data_interval_seconds = Column(Float)  # 平均数据间隔
    
    # ========== 健康度 ==========
    avg_health_score = Column(Float)    # 平均健康度
    
    # ========== 时间 ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== 复合索引 ==========
    __table_args__ = (
        Index('idx_device_daily_device_date', 'device_id', 'date'),
        Index('idx_device_daily_station_date', 'station_id', 'date'),
        Index('idx_device_daily_region', 'region_id', 'date'),
        Index('idx_device_daily_type', 'device_type', 'date'),
    )
    
    # 关系
    device = relationship("Device")
    station = relationship("Station")


# ========== 聚合任务函数 ==========

def aggregate_station_hourly(db, station_id: int, hour: datetime, region_id: str = "default"):
    """聚合场站小时数据
    
    Args:
        db: 数据库会话
        station_id: 场站ID
        hour: 聚合小时
        region_id: 区域标识
        
    Returns:
        StationHourlyStats 对象，失败时返回 None
    """
    import logging
    from sqlalchemy import func as sql_func
    from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger
    
    logger = logging.getLogger(__name__)
    
    try:
        hour_start = hour.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        # 光伏聚合
        # ⚠️ daily_generation/daily_charge/daily_discharge/charger_kwh 是 modbus 累计计数器快照,
        #    下方 sum() 把同一计数器翻 N 倍 (口径缺陷)。与 tdengine_writer.query_station_stats /
        #    core/tdengine 连续聚合流三处 SUM 口径一致 → 须立工单三处同步改 (LAST−FIRST, 先按设备求差
        #    再聚合), 禁止单点改。详见 docs/plans/tdengine-cumulative-counter-caliber-fix.md (卡 eedd9431)。
        pv_stats = db.query(
            sql_func.avg(TelemetryPV.grid_power_total).label('avg_power'),
            sql_func.max(TelemetryPV.grid_power_total).label('max_power'),
            sql_func.avg(TelemetryPV.pv_power_total).label('avg_pv'),
            sql_func.max(TelemetryPV.pv_power_total).label('max_pv'),
            sql_func.sum(TelemetryPV.daily_generation).label('gen'),
            sql_func.avg(TelemetryPV.internal_temperature).label('avg_temp'),
            sql_func.max(TelemetryPV.internal_temperature).label('max_temp'),
            sql_func.count().label('count'),
        ).filter(
            TelemetryPV.station_id == station_id,
            TelemetryPV.region_id == region_id,
            TelemetryPV.timestamp >= hour_start,
            TelemetryPV.timestamp < hour_end,
        ).first()
        
        # 储能聚合
        battery_stats = db.query(
            sql_func.avg(TelemetryBattery.battery_soc).label('avg_soc'),
            sql_func.avg(TelemetryBattery.battery_power).label('avg_power'),
            sql_func.sum(TelemetryBattery.daily_charge).label('charge'),
            sql_func.sum(TelemetryBattery.daily_discharge).label('discharge'),
            sql_func.avg(TelemetryBattery.internal_temperature).label('avg_temp'),
            sql_func.max(TelemetryBattery.internal_temperature).label('max_temp'),
            sql_func.count().label('count'),
        ).filter(
            TelemetryBattery.station_id == station_id,
            TelemetryBattery.region_id == region_id,
            TelemetryBattery.timestamp >= hour_start,
            TelemetryBattery.timestamp < hour_end,
        ).first()
        
        # 充电桩聚合
        charger_stats = db.query(
            sql_func.avg(TelemetryCharger.charger_power).label('avg_power'),
            sql_func.max(TelemetryCharger.charger_power).label('max_power'),
            sql_func.sum(TelemetryCharger.charger_kwh).label('kwh'),
            sql_func.avg(TelemetryCharger.internal_temperature).label('avg_temp'),
            sql_func.max(TelemetryCharger.internal_temperature).label('max_temp'),
            sql_func.count().label('count'),
        ).filter(
            TelemetryCharger.station_id == station_id,
            TelemetryCharger.region_id == region_id,
            TelemetryCharger.timestamp >= hour_start,
            TelemetryCharger.timestamp < hour_end,
        ).first()
        
        # 创建聚合记录
        stats = StationHourlyStats(
            station_id=station_id,
            hour=hour_start,
            region_id=region_id,
            pod_id="pod-01",
            avg_pv_power=float(pv_stats.avg_pv or 0),
            max_pv_power=float(pv_stats.max_pv or 0),
            pv_generation_kwh=float(pv_stats.gen or 0),
            avg_battery_soc=float(battery_stats.avg_soc or 0),
            avg_battery_power=float(battery_stats.avg_power or 0),
            charge_kwh=float(battery_stats.charge or 0),
            discharge_kwh=float(battery_stats.discharge or 0),
            avg_charger_power=float(charger_stats.avg_power or 0),
            max_charger_power=float(charger_stats.max_power or 0),
            charger_kwh=float(charger_stats.kwh or 0),
            avg_temperature=float(
                (pv_stats.avg_temp or 0) + (battery_stats.avg_temp or 0) + (charger_stats.avg_temp or 0)
            ) / 3,
            max_temperature=float(max(
                pv_stats.max_temp or 0, battery_stats.max_temp or 0, charger_stats.max_temp or 0
            )),
            data_points=int(
                (pv_stats.count or 0) + (battery_stats.count or 0) + (charger_stats.count or 0)
            ),
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"聚合场站 {station_id} 小时 {hour} 数据失败: {e}")
        return None



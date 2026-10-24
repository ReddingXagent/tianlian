"""
健康度监控服务 - 定时计算 + 告警触发工单
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.workorder import WorkOrder, WorkOrderLevel, WorkOrderStatus
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.telemetry_v2 import (
    TelemetryPV, TelemetryBattery, TelemetryCharger,
    get_telemetry_model_by_device_type,
)
from app.services.health_engine import HealthEngine

_logger = logging.getLogger(__name__)

# 设备类型 -> 遥测专表最新记录字段映射 (engine 输入键 -> 专表列属性, 卡07cdb6af)
# 可得字段随设备类型不同; 无对应列的指标(绝缘电阻/漏电流/通信成功率/插拔次数等)
# 遥测侧不采集, 缺失时由 HealthEngine 取默认值, 详见任务摸底报告。
_TELEMETRY_FIELD_MAPS = {
    TelemetryPV: {
        'temperature': 'internal_temperature',
        'inv_temperature': 'inv_temperature',
        'pv_temperature': 'pv_temperature',
        'voltage': 'grid_voltage_a',
        'current': 'grid_current_a',
        'power_factor': 'grid_power_factor',
        'frequency': 'grid_frequency',
        'run_time': 'run_time',
        'system_status': 'system_status',
    },
    TelemetryBattery: {
        'temperature': 'internal_temperature',
        'battery_temperature': 'battery_temperature',
        'battery_voltage': 'battery_voltage',
        'battery_current': 'battery_current',
        'battery_soc': 'battery_soc',
        'battery_soh': 'battery_soh',
        'voltage': 'grid_voltage_a',
        'current': 'grid_current_a',
        'power_factor': 'grid_power_factor',
        'frequency': 'grid_frequency',
        'run_time': 'run_time',
        'system_status': 'system_status',
    },
    TelemetryCharger: {
        'temperature': 'internal_temperature',
        'ambient_temperature': 'ambient_temperature',
        'gun_temperature': 'gun_temperature',
        'gun_status': 'gun_status',
        'voltage': 'charger_voltage',
        'current': 'charger_current',
        'power_factor': None,  # charger 表无功率因数列, 占位见 _map_telemetry_row
        'charger_soc': 'charger_soc',
        'charger_kwh': 'charger_kwh',
        'run_time': 'run_time',
        'system_status': 'system_status',
    },
}
_TELEMETRY_FIELD_MAPS[TelemetryCharger] = {
    k: v for k, v in _TELEMETRY_FIELD_MAPS[TelemetryCharger].items() if v is not None
}

# mock 数据告警只警告一次 (进程级, 卡07cdb6af)
_mock_warned = False


class HealthMonitor:
    """健康度监控服务"""
    
    def __init__(self):
        self.engine = HealthEngine()
    
    def calculate_all_health(self, db: Session, batch_size: int = 100) -> list:
        """计算所有设备健康度

        分批加载 Device(默认 batch_size=100), 每批 commit 一次, 避免 1000+ 设备
        一次性 .all() 加载导致 OOM。offset 分页基于 Device 表(循环内不删设备, 稳定)。
        DB 异常 → rollback 当前未提交批次 + 记日志 + 返回 [](不抛), 避免拖垮定时任务/
        刷新端点调用方。注意: 每批独立 commit, 异常时已提交的批次不会回滚(任务卡要求)。
        """
        import time
        start = time.time()
        total = 0
        results = []
        try:
            offset = 0
            while True:
                batch = db.query(Device).limit(batch_size).offset(offset).all()
                if not batch:
                    break

                for device in batch:
                    # 优先真实遥测, 无记录回退模拟数据 (卡07cdb6af)
                    device_data = self._collect_device_data(db, device.id, device.type)

                    # 计算健康度
                    score, details = self.engine.calculate_health_score(
                        device_data, device_type=device.type.value
                    )

                    # 更新设备健康度
                    device.health_score = round(score, 2)
                    results.append({
                        'device_id': device.id,
                        'code': device.code,
                        'health_score': score,
                        'details': details,
                        'source': device_data.get('source'),
                    })

                db.commit()
                total += len(batch)
                offset += batch_size

            _logger.info(
                "calculate_all_health 完成: 处理 %d 个设备, 耗时 %.2fs (batch_size=%d)",
                total, time.time() - start, batch_size,
            )
            return results
        except Exception:
            db.rollback()
            _logger.exception(
                "calculate_all_health 失败, 已处理 %d 个设备, 已回滚当前批次, 返回空结果",
                total,
            )
            return []
    
    def check_and_create_alarms(self, db: Session) -> list:
        """检查健康度并自动创建告警和工单（batch优化，避免N+1查询）

        DB 异常 → rollback + 记日志 + 返回 [](不抛), 半途已 add 的告警/工单随回滚丢弃。
        """
        try:
            devices = db.query(Device).all()
            if not devices:
                return []

            created_alarms = []

            # 批量预查询所有活跃健康告警的设备ID（避免N+1）
            existing_alarms = db.query(Alarm.device_id).filter(
                Alarm.device_id.in_([d.id for d in devices]),
                Alarm.status == AlarmStatus.ACTIVE,
                Alarm.alarm_type == 'health'
            ).all()
            devices_with_existing = {row[0] for row in existing_alarms}

            for device in devices:
                score = device.health_score or 100

                if score < 60:  # 严重
                    level = AlarmLevel.CRITICAL
                elif score < 80:  # 警告
                    level = AlarmLevel.WARNING
                else:
                    continue  # 健康，不告警

                # 从预查询的集合中检查（避免N+1）
                if device.id in devices_with_existing:
                    continue

                # 创建告警
                alarm = Alarm(
                    device_id=device.id,
                    station_id=device.station_id,
                    level=level,
                    alarm_type='health',
                    content=f'{device.name} 健康度 {score:.1f}%，需要检修',
                    status=AlarmStatus.ACTIVE,
                )
                db.add(alarm)
                db.flush()

                # 自动创建工单 - 使用UUID确保唯一
                import uuid
                wo_id = f"WO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
                workorder = WorkOrder(
                    id=wo_id,
                    fault_desc=f'设备健康度告警: {device.name} 健康度 {score:.1f}%，需要检修',
                    type='repair',
                    level=WorkOrderLevel.WARNING if score >= 60 else WorkOrderLevel.CRITICAL,
                    station_id=device.station_id,
                    device_id=device.id,
                    status=WorkOrderStatus.PENDING,
                    creator_id=None,  # 后台定时任务自动创建，无用户上下文
                )
                db.add(workorder)

                created_alarms.append({
                    'device': device.name,
                    'score': score,
                    'level': level.value,
                    'workorder_id': wo_id
                })

            db.commit()
            return created_alarms
        except Exception:
            db.rollback()
            _logger.exception("check_and_create_alarms 失败, 已回滚, 返回空结果")
            return []
    
    def get_device_health(self, device_id: int, db: Session) -> dict:
        """获取单个设备健康度

        DB 异常 → rollback + 记日志 + 返回 {}(不抛)。
        """
        try:
            device = db.query(Device).filter(Device.id == device_id).first()
            if not device:
                return {}
            device_data = self._collect_device_data(db, device.id, device.type)
            score, details = self.engine.calculate_health_score(
                device_data, device_type=device.type.value
            )
            return {
                'device_id': device.id,
                'code': device.code,
                'name': device.name,
                'health_score': round(score, 2),
                'details': details,
                'source': device_data.get('source'),
            }
        except Exception:
            db.rollback()
            _logger.exception("get_device_health 失败 device_id=%s, 已回滚, 返回空结果", device_id)
            return {}

    def get_health_trend(self, device_id: int, db: Session, days: int = 7) -> list:
        """获取设备健康度趋势"""
        return []

    def _collect_device_data(self, db: Session, device_id: int, device_type) -> dict:
        """采集设备实时数据: 优先查遥测专表最新记录, 无记录回退模拟数据。

        返回 dict 带 'source' 键 ('telemetry'=真实遥测 / 'mock'=模拟, 卡07cdb6af)。
        遥测侧不采集的指标(绝缘电阻/漏电流/通信成功率/插拔次数等)不在此填充,
        由 HealthEngine 按默认值评分 —— 强行造数会回到假数据老路。
        """
        model_cls = get_telemetry_model_by_device_type(
            device_type.value if hasattr(device_type, 'value') else str(device_type)
        )
        if model_cls is not None:
            try:
                row = (
                    db.query(model_cls)
                    .filter(model_cls.device_id == device_id)
                    .order_by(model_cls.timestamp.desc())
                    .first()
                )
            except Exception:
                _logger.exception(
                    "查询设备最新遥测失败 device_id=%s, 回退模拟数据", device_id
                )
                row = None
            if row is not None:
                data = self._map_telemetry_row(row, model_cls)
                data['source'] = 'telemetry'
                return data
        data = self._generate_mock_data(device_type)
        return data

    @staticmethod
    def _map_telemetry_row(row, model_cls) -> dict:
        """遥测记录 → engine 输入 dict (仅映射真实存在的列, None 值跳过)"""
        mapping = _TELEMETRY_FIELD_MAPS.get(model_cls, {})
        data = {}
        for key, attr in mapping.items():
            value = getattr(row, attr, None)
            if value is not None:
                data[key] = value
        return data

    def _generate_mock_data(self, device_type: str) -> dict:
        """生成模拟的设备实时数据"""
        import random
        global _mock_warned
        if not _mock_warned:
            _mock_warned = True
            _logger.warning(
                "[健康监控] 设备无真实遥测数据, 健康分基于模拟数据计算 "
                "(source=mock, 进程内仅提示一次)"
            )
        
        base = {
            'insulation_resistance': random.uniform(10, 100),
            'leakage_current': random.uniform(0.1, 5.0),
            'temperature': random.uniform(25, 65),
            'voltage': random.uniform(380, 420),
            'current': random.uniform(0, 100),
            'comm_success_rate': random.uniform(95, 100),
            'plug_count': random.randint(0, 5000),
            'power_factor': random.uniform(0.85, 0.99),
            'harmonic_ratio': random.uniform(1, 5),
        }
        
        # 根据设备类型调整模拟温度范围
        if device_type:
            dt_lower = device_type.lower() if hasattr(device_type, 'lower') else device_type.value if hasattr(device_type, 'value') else str(device_type)
        else:
            dt_lower = ''
        
        # 不同类型设备的正常温度范围
        temp_ranges = {
            'pv_inverter': (30, 65),
            'battery_inverter': (30, 65),
            'pcs': (30, 60),
            'battery': (20, 50),
            'charger_dc': (30, 70),
            'charger_ac': (30, 70),
            'meter': (25, 55),
            'gateway': (25, 55),
        }
        temp_min, temp_max = temp_ranges.get(dt_lower, (25, 65))
        base['temperature'] = random.uniform(temp_min, temp_max)
        
        # 模拟一些低健康度设备
        if random.random() < 0.2:
            # 为不同设备类型生成合理的高温
            high_temp_range = {
                'pv_inverter': (75, 95),
                'battery_inverter': (75, 95),
                'pcs': (70, 85),
                'battery': (60, 75),
                'charger_dc': (80, 95),
                'charger_ac': (80, 95),
                'meter': (85, 100),
                'gateway': (85, 100),
            }
            high_min, high_max = high_temp_range.get(dt_lower, (75, 95))
            base['temperature'] = random.uniform(high_min, high_max)
            base['leakage_current'] = random.uniform(5, 15)
            base['comm_success_rate'] = random.uniform(80, 95)
        
        base['source'] = 'mock'
        return base

# 全局实例
health_monitor = HealthMonitor()

def run_health_check(db=None):
    """健康检查定时任务入口
    
    Args:
        db: 可选数据库会话。不传则自动创建新会话。
    """
    # 动态导入以避免测试时模块级引用问题
    if db is None:
        from app.core.database import SessionLocal
        db = SessionLocal()
        own_session = True
    else:
        own_session = False
    try:
        # 1. 计算健康度
        results = health_monitor.calculate_all_health(db)
        logging.getLogger(__name__).info("[健康监控] 更新了 %d 个设备健康度", len(results))
        
        # 2. 检查告警并创建工单
        alarms = health_monitor.check_and_create_alarms(db)
        if alarms:
            logging.getLogger(__name__).info("[健康监控] 创建了 %d 个告警和工单", len(alarms))
            for a in alarms:
                logging.getLogger(__name__).info('  - %s: %.1f%% -> %s', a['device'], a['score'], a['workorder_id'])
        return {'health_results': len(results), 'alarms_created': len(alarms)}
    finally:
        if own_session:
            db.close()

if __name__ == '__main__':
    run_health_check()
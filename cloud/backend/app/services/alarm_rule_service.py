#!/usr/bin/env python3
"""
告警规则引擎 - 定时评估 + 自动触发

由 scheduler.py 定时调用，检查设备遥测数据是否触发了告警规则。
如果触发，自动创建告警记录并可选创建工单。

Phase35: 多级告警 + 聚合 + 升级
- 4个级别: 预警(WARN) / 一般(INFO) / 严重(ERROR) / 紧急(CRITICAL)
- 每个级别不同的通知策略和响应时间要求
- 告警聚合: 同类型5分钟内合并, 防风暴
- 告警升级: 超时未处理自动升级
"""
import logging
import math
import numbers
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.alarm import Alarm, AlarmRule, AlarmRuleLog, AlarmLevel, AlarmStatus
from app.models.telemetry import Telemetry
from app.models.device import Device
from app.services.notification_dispatcher import notification_dispatcher
from app.services.alarm_aggregation import try_aggregate_alarm, SUPPRESSED

logger = logging.getLogger(__name__)


# ============================
# 告警级别定义与策略
# ============================

class AlarmLevelInfo:
    """告警级别信息"""
    def __init__(self, level: AlarmLevel, label: str, priority: int,
                 response_minutes: int, notify_channels: List[str],
                 auto_workorder: bool, color: str):
        self.level = level
        self.label = label
        self.priority = priority  # 数字越大越紧急
        self.response_minutes = response_minutes  # 要求的响应时间(分钟)
        self.notify_channels = notify_channels  # 通知渠道
        self.auto_workorder = auto_workorder  # 是否自动创建工单
        self.color = color  # 显示颜色

    def get_workorder_level(self):
        """获取对应的工单级别"""
        from app.models.workorder import WorkOrderLevel  # 延迟导入避免循环
        if self.level == AlarmLevel.CRITICAL or self.level == AlarmLevel.FATAL:
            return WorkOrderLevel.CRITICAL
        elif self.level == AlarmLevel.WARNING:
            return WorkOrderLevel.WARNING
        else:
            return WorkOrderLevel.INFO

    def should_create_workorder(self, rule=None):
        """判断是否应该自动创建工单

        仅当规则显式开启（auto_create_workorder is True）时覆盖级别策略；
        False/None 一律回落到级别默认。AlarmRule.auto_create_workorder 列
        default=False，规则持久化后恒为 False，若用 `is not None` 判断会让
        规则级 False 永远压过 CRITICAL/FATAL 的级别策略（auto_workorder=True）。
        """
        if rule and rule.auto_create_workorder is True:
            return True
        return self.auto_workorder


# 四个级别的策略
LEVEL_CONFIG = {
    AlarmLevel.INFO: AlarmLevelInfo(
        level=AlarmLevel.INFO,
        label="一般",
        priority=1,
        response_minutes=120,  # 2小时内处理
        notify_channels=['im'],
        auto_workorder=False,
        color="blue",
    ),
    AlarmLevel.WARNING: AlarmLevelInfo(
        level=AlarmLevel.WARNING,
        label="预警",
        priority=2,
        response_minutes=60,  # 1小时内处理
        notify_channels=['im'],
        auto_workorder=False,
        color="yellow",
    ),
    AlarmLevel.CRITICAL: AlarmLevelInfo(
        level=AlarmLevel.CRITICAL,
        label="严重",
        priority=3,
        response_minutes=30,  # 30分钟内处理
        notify_channels=['im', 'email'],
        auto_workorder=True,
        color="red",
    ),
    AlarmLevel.FATAL: AlarmLevelInfo(
        level=AlarmLevel.FATAL,
        label="紧急",
        priority=4,
        response_minutes=15,  # 15分钟内处理
        notify_channels=['im', 'email', 'sms'],
        auto_workorder=True,
        color="red",
    ),
}


def get_level_info(level: AlarmLevel) -> AlarmLevelInfo:
    """获取告警级别策略信息"""
    return LEVEL_CONFIG.get(level, LEVEL_CONFIG[AlarmLevel.INFO])


def _is_real_number(value: Any) -> bool:
    """判断是否为可参与数值比较的有限实数。

    排除 bool(int 子类, 不应做阈值比较) / str / None / NaN / inf。
    用于 _check_threshold 前置校验 —— Python3 中 != / == 跨类型不抛 TypeError 而静默
    返回 bool, 会导致字符串遥测或 NULL 阈值误触发告警风暴, 故比较前须显式校验。
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, numbers.Real):
        return False
    try:
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


class AlarmRuleEngine:
    """告警规则引擎"""

    # ========== 4级通知策略 ==========

    def _get_notify_channels_for_level(self, level: AlarmLevel) -> List[str]:
        """根据告警级别获取通知渠道"""
        level_info = get_level_info(level)
        return level_info.notify_channels

    def _get_response_time_for_level(self, level: AlarmLevel) -> int:
        """获取告警级别要求的响应时间（分钟）"""
        level_info = get_level_info(level)
        return level_info.response_minutes

    def _should_auto_workorder(self, rule: AlarmRule, level: AlarmLevel) -> bool:
        """根据规则配置 + 级别判断是否自动创建工单"""
        level_info = get_level_info(level)
        return level_info.should_create_workorder(rule)

    # ========== 主评估入口 ==========

    def evaluate_all(self, db: Optional[Session] = None, batch_size: int = 100) -> list:
        """评估所有启用的告警规则

        分批加载启用的规则(默认 batch_size=100), 逐批评估, 避免规则量大时一次 .all()
        全量加载导致内存占用过高。语义不变: 仍评估全部 enabled 规则, 单规则异常捕获
        不影响整体; offset 分页基于规则表(评估循环不删规则, 稳定)。
        """
        result = []
        close_db = db is None
        if close_db:
            db = SessionLocal()
        try:
            start = time.time()
            rule_count = 0
            # 全局最新遥测(内部已按 device 分批合并; 评估期间不变, 循环外只取一次)
            latest_telemetry = self._get_latest_telemetry_all(db)

            offset = 0
            while True:
                rules = db.query(AlarmRule).filter(AlarmRule.enabled == True) \
                    .limit(batch_size).offset(offset).all()
                if not rules:
                    break

                for rule in rules:
                    try:
                        rule_result = self._evaluate_rule(rule, db, latest_telemetry)
                        result.append(rule_result)
                    except Exception as e:
                        logger.error("评估告警规则 %s 失败: %s", rule.id, e)
                        result.append({
                            'rule_id': rule.id,
                            'rule_name': rule.name,
                            'triggered': False,
                            'error': '服务内部错误，请稍后重试'
                        })
                rule_count += len(rules)
                offset += batch_size

            logger.info(
                "evaluate_all 完成: 评估 %d 条规则, 耗时 %.2fs (batch_size=%d)",
                rule_count, time.time() - start, batch_size,
            )
        finally:
            if close_db:
                db.close()
        return result

    def evaluate_single_rule(self, rule_id: int, db: Session) -> dict:
        """评估单个告警规则"""
        rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id).first()
        if not rule:
            return {'triggered': False, 'message': '规则不存在'}
        
        latest_telemetry = self._get_latest_telemetry_all(db)
        return self._evaluate_rule(rule, db, latest_telemetry)

    def _get_latest_telemetry_all(self, db: Session, batch_size: int = 1000) -> dict:
        """获取所有设备的最新遥测数据，按device_id索引

        按 device_id 分批查询(默认 batch_size=1000), 逐批合并到 dict, 避免设备+遥测
        规模大时一次 .all() 加载全部遥测行导致 OOM。语义不变: 仍返回每个 device_id
        的最新(timestamp 最大)遥测记录。先 distinct 取 device_id(单列, 内存占用小),
        再按 chunk 求 max(timestamp) 并 join 取行。
        """
        # 子查询：每个device_id的最大timestamp
        from sqlalchemy import func as sqlfunc

        # 轻量取出所有出现过的 device_id（只读单列）
        device_ids = [row[0] for row in db.query(Telemetry.device_id).distinct().all()]

        result: dict = {}
        for start in range(0, len(device_ids), batch_size):
            chunk = device_ids[start:start + batch_size]
            if not chunk:
                break
            subq = db.query(
                Telemetry.device_id,
                sqlfunc.max(Telemetry.timestamp).label('max_ts')
            ).filter(Telemetry.device_id.in_(chunk)) \
                .group_by(Telemetry.device_id).subquery()

            rows = db.query(Telemetry).join(
                subq,
                (Telemetry.device_id == subq.c.device_id) &
                (Telemetry.timestamp == subq.c.max_ts)
            ).filter(Telemetry.device_id.in_(chunk)).all()

            result.update({r.device_id: r for r in rows})

        return result

    def _evaluate_rule(self, rule: AlarmRule, db: Session,
                       latest_telemetry: dict) -> dict:
        """评估一条告警规则，返回触发结果"""
        now = datetime.now(timezone.utc)
        triggered_devices = []
        
        # 确定要检查的设备列表
        target_device_ids = self._get_target_device_ids(rule, db)
        if not target_device_ids:
            return {
                'rule_id': rule.id,
                'rule_name': rule.name,
                'triggered': False,
                'devices': [],
                'checked_at': now.isoformat()
            }

        # 批量预查询沉默期内的设备（避免N+1）
        silenced_devices = self._get_silenced_devices(rule, target_device_ids, db)
        
        for device_id in target_device_ids:
            telemetry = latest_telemetry.get(device_id)
            if not telemetry:
                continue
            
            # 获取指标值
            metric_value = getattr(telemetry, rule.metric, None)
            if metric_value is None:
                continue
            
            # 检查是否触发
            is_triggered = self._check_threshold(metric_value, rule.operator, rule.threshold)
            if not is_triggered:
                continue
            
            # 检查是否在沉默期内（O(1) set lookup）
            if device_id in silenced_devices:
                continue
            
            # 触发告警（含聚合逻辑）
            alarm = self._create_alarm(rule, device_id, metric_value, db)

            # 触发通知分发（使用4级策略）
            # 聚合窗口内仅首次触发派发 (卡 2779d516): aggregation_count > 1 说明
            # 本次触发被聚合到已有告警上 (『5分钟内只发1条』契约), 不重复派发。
            # 升级 (scan_and_escalate) 与 health_monitor 的派发走各自路径, 不受影响。
            if alarm and (alarm.aggregation_count or 1) <= 1:
                channels = self._get_notify_channels_for_level(rule.level)
                notification_dispatcher.dispatch_on_alarm(alarm, db, channels)
            
            triggered_devices.append({
                'device_id': device_id,
                'value': metric_value,
                'alarm_id': alarm.id if alarm else None,
                'level': rule.level.value,
                'aggregated': alarm.aggregation_count > 1 if alarm else False,
            })
        
        return {
            'rule_id': rule.id,
            'rule_name': rule.name,
            'triggered': len(triggered_devices) > 0,
            'devices': triggered_devices,
            'checked_at': now.isoformat()
        }

    def _get_silenced_devices(self, rule: AlarmRule, device_ids: list, db: Session) -> set:
        """批量获取沉默期内的设备ID集合"""
        if not rule.silence_minutes or rule.silence_minutes <= 0:
            return set()
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=rule.silence_minutes)
        rows = db.query(Alarm.device_id).filter(
            Alarm.rule_id == rule.id,
            Alarm.device_id.in_(device_ids),
            Alarm.created_at >= cutoff
        ).all()
        return {row[0] for row in rows}

    def _get_target_device_ids(self, rule: AlarmRule, db: Session) -> list:
        """获取规则适用的设备ID列表"""
        query = db.query(Device.id)
        
        # 指定设备
        if rule.device_ids:
            query = query.filter(Device.id.in_(rule.device_ids))
            return [r[0] for r in query.all()]
        
        # 设备类型过滤
        if rule.device_type:
            query = query.filter(Device.type == rule.device_type)
        
        # 站点过滤
        if rule.station_ids:
            query = query.filter(Device.station_id.in_(rule.station_ids))
        
        return [r[0] for r in query.all()]

    def _check_threshold(self, value: float, operator: str, threshold: float) -> bool:
        """检查阈值条件

        fail-closed: value/threshold 任一非有限实数(字符串 / None / NaN / inf / bool)直接返回 False。
        Python3 中 != / == 跨类型不抛 TypeError 而静默返回 bool:
          'offline' != 80.0 → True (字符串遥测 + != 规则, 告警风暴)
          NaN != 80        → True
          value != None    → True (threshold 列 NULL 时任何遥测都触发)
        仅靠 except TypeError 兜不住上述静默 True, 故比较前必须显式校验数值类型。
        """
        if not _is_real_number(value) or not _is_real_number(threshold):
            return False
        try:
            if operator == '>':
                return value > threshold
            elif operator == '>=':
                return value >= threshold
            elif operator == '<':
                return value < threshold
            elif operator == '<=':
                return value <= threshold
            elif operator == '==' or operator == '=':
                return value == threshold
            elif operator == '!=' or operator == '<>':
                return value != threshold
            return False
        except (TypeError, ValueError):
            return False

    def _is_silenced(self, rule: AlarmRule, device_id: int, db: Session) -> bool:
        """检查是否在沉默期内（同一设备+同一规则，重复告警间隔）"""
        if not rule.silence_minutes or rule.silence_minutes <= 0:
            return False
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=rule.silence_minutes)
        recent = db.query(Alarm).filter(
            Alarm.rule_id == rule.id,
            Alarm.device_id == device_id,
            Alarm.created_at >= cutoff
        ).first()
        return recent is not None

    def _create_alarm(self, rule: AlarmRule, device_id: int,
                      metric_value: float, db: Session):
        """根据规则创建告警记录（含聚合）"""
        # 获取设备所属站点
        device = db.query(Device).filter(Device.id == device_id).first()
        station_id = device.station_id if device else None
        
        # 渲染告警内容模板
        template = rule.alarm_template or "{metric} = {value}, 超过阈值 {threshold}"
        render_ctx = dict(
            metric=rule.metric,
            value=metric_value,
            threshold=rule.threshold,
            operator=rule.operator,
            device_name=device.name if device else f'设备{device_id}',
            rule_name=rule.name,
        )
        try:
            content = template.format(**render_ctx)
        except (KeyError, ValueError, IndexError) as e:
            # 用户配置的模板含未知占位符({device_id}/{foo} → KeyError)或字面花括号({ → ValueError):
            # 异常上抛会被 evaluate_all 捕获, 该规则永久返回"服务内部错误"而静默失效无人察觉。
            # 回落默认模板(仅用已知占位符, 不会再抛), 规则继续评估。
            logger.warning(
                "告警规则[%s]模板渲染失败, 回落默认模板: %s (模板=%r)",
                rule.id, e, rule.alarm_template,
            )
            content = "{metric} = {value}, 超过阈值 {threshold}".format(**render_ctx)
        
        alarm = Alarm(
            device_id=device_id,
            station_id=station_id,
            rule_id=rule.id,
            alarm_type=f"rule_{rule.id}",
            level=rule.level,
            content=content,
            status=AlarmStatus.ACTIVE,
            trigger_metric=rule.metric,
            trigger_value=metric_value,
            trigger_threshold=rule.threshold,
            trigger_operator=rule.operator,
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        
        # 尝试聚合（同类型合并）
        aggregated = try_aggregate_alarm(alarm, db)
        if aggregated is SUPPRESSED:
            # 防风暴抑制 (卡 2779d516): 新告警行已在 try_aggregate_alarm 中删除,
            # 此处直接返回 None, 不写日志/建工单/healing/派发通知 —— 被抑制的
            # 触发零副作用。
            return None
        if aggregated and aggregated.id != alarm.id:
            # 已聚合到已有告警上，删除新创建的告警
            db.delete(alarm)
            db.commit()
            logger.info(
                "[聚合] 告警已合并到 #%s (device=%s, rule=%s)",
                aggregated.id, device_id, rule.id
            )
            return aggregated
        
        logger.info(
            "告警规则[%s]触发: 设备[%s] %s=%s, 级别=%s",
            rule.name, device_id, rule.metric, metric_value, rule.level.value
        )
        
        # 记录评估日志
        log = AlarmRuleLog(
            rule_id=rule.id,
            rule_name=rule.name,
            device_id=device_id,
            device_name=device.name if device else None,
            station_id=station_id,
            metric=rule.metric,
            current_value=metric_value,
            threshold=rule.threshold,
            operator=rule.operator,
            triggered=True,
            alarm_id=alarm.id,
        )
        db.add(log)
        db.commit()
        
        # 根据级别自动创建工单
        level_info = get_level_info(rule.level)
        if level_info.should_create_workorder(rule):
            self._maybe_create_workorder(alarm, rule, device_id, station_id, content, db)
        
        # 触发自愈引擎评估
        try:
            from app.services.healing_engine import healing_engine
            healing_result = healing_engine.evaluate_alarm(alarm, db)
            if healing_result:
                logger.info("告警[%s]触发自愈评估: %s", alarm.id, healing_result.get('status', 'unknown'))
        except Exception as e:
            logger.error("告警自愈评估失败: %s", e)
        
        return alarm

    def _maybe_create_workorder(self, alarm: Alarm, rule: AlarmRule,
                                 device_id: int, station_id: int,
                                 content: str, db: Session):
        """按规则配置 + 级别策略创建工单"""
        try:
            from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus
            level_info = get_level_info(rule.level)
            wo_level = level_info.get_workorder_level()

            # WorkOrder.id 是 String(50) 主键，无默认值/无自增，必须显式生成工单号
            # 格式与 health_monitor.py 一致：WO-{yyyyMMddHHmmss}-{4位hex}
            wo_id = f"WO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
            wo = WorkOrder(
                id=wo_id,
                fault_desc=f'[告警自动创建] {content}',
                type=WorkOrderType.REPAIR,
                level=wo_level,
                status=WorkOrderStatus.PENDING,
                device_id=device_id,
                station_id=station_id,
                creator_id=None,  # 系统自动创建(无真实创建人, 卡片 1236b769)
            )
            db.add(wo)
            db.commit()
            logger.info("告警[%s]自动创建工单[%s] (级别=%s)", alarm.id, wo.id, rule.level.value)
        except Exception as e:
            db.rollback()
            logger.error("告警自动创建工单失败: %s", e)

    def evaluate_device(self, device_id: int, rule_id: int, db: Session) -> dict:
        """为指定设备+规则进行即时评估（供前端手动触发）"""
        rule = db.query(AlarmRule).filter(AlarmRule.id == rule_id, AlarmRule.enabled == True).first()
        if not rule:
            return {'triggered': False, 'message': '规则不存在或已禁用'}
        
        telemetry = db.query(Telemetry).filter(
            Telemetry.device_id == device_id
        ).order_by(Telemetry.timestamp.desc()).first()
        if not telemetry:
            return {'triggered': False, 'message': '设备无遥测数据'}
        
        metric_value = getattr(telemetry, rule.metric, None)
        if metric_value is None:
            return {'triggered': False, 'message': f'遥测数据中找不到指标 {rule.metric}'}
        
        is_triggered = self._check_threshold(metric_value, rule.operator, rule.threshold)
        if not is_triggered:
            return {
                'triggered': False,
                'message': f'{rule.metric}={metric_value}, 阈值{rule.operator}{rule.threshold}, 未触发',
                'device_id': device_id,
                'current_value': metric_value,
                'threshold': rule.threshold,
                'operator': rule.operator
            }
        
        alarm = self._create_alarm(rule, device_id, metric_value, db)
        return {
            'triggered': True,
            'alarm_id': alarm.id,
            'device_id': device_id,
            'current_value': metric_value,
            'threshold': rule.threshold,
            'operator': rule.operator,
            'content': alarm.content,
            'level': rule.level.value
        }

    # ========== 告警升级机制 ==========

    def scan_and_escalate(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        扫描未处理的活跃告警，执行升级
        - WARN → ERROR (30分钟未处理)
        - ERROR → CRITICAL (15分钟未处理)
        - CRITICAL/FATAL 不升级
        每5分钟调用一次
        """
        close_db = db is None
        if close_db:
            db = SessionLocal()
        
        escalated = []
        try:
            now = datetime.now(timezone.utc)
            
            # 查找需要升级的告警
            # 方案A 两级升级链: 不再用 escalated_from.is_(None) 排除已升级者 —— 那会让已升到
            # CRITICAL 的告警永久被排除, CRITICAL→FATAL 第二级在扫描路径变死代码 (与 docstring
            # 两级升级语义矛盾)。FATAL 由下方 level.in_ 条件自然排除, 无需额外过滤。
            pending_alarms = db.query(Alarm).filter(
                Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED, AlarmStatus.PROCESSING]),
                Alarm.level.in_([AlarmLevel.WARNING, AlarmLevel.CRITICAL]),
            ).all()
            
            for alarm in pending_alarms:
                result = self._escalate_single(alarm, now, db)
                if result:
                    escalated.append(result)
            
            if escalated:
                logger.info("[升级扫描] %d 个告警已升级", len(escalated))
        except Exception as e:
            logger.error("[升级扫描] 失败: %s", e)
        finally:
            if close_db:
                db.close()
        
        return escalated

    def _escalate_single(self, alarm: Alarm, now: datetime, db: Session) -> Optional[Dict[str, Any]]:
        """升级单个告警，返回升级结果"""
        # 获取规则（或使用默认超时）
        rule = None
        if alarm.rule_id:
            rule = db.query(AlarmRule).filter(AlarmRule.id == alarm.rule_id).first()
        
        # 确定超时时间: 显式 0 = 立即升级(超时0分钟即满足升级条件), 仅 None 回落默认 30。
        # 原 `if rule and rule.escalation_timeout_minutes` 把显式 0 当 falsy 吞成 30。
        if rule is not None and rule.escalation_timeout_minutes is not None:
            timeout_minutes = rule.escalation_timeout_minutes
        else:
            timeout_minutes = 30
        
        # 两级升级链基准时间 (方案A):
        #   - 第二级 CRITICAL→FATAL: 以 escalated_at(升到 CRITICAL 的时刻)为基准, 衡量
        #     "在 CRITICAL 级别停留超时"; 缺失或非 datetime 则回退 created_at。
        #   - 第一级 WARNING→CRITICAL: 以 created_at(原始触发时刻)为基准。
        baseline = alarm.created_at
        if alarm.level == AlarmLevel.CRITICAL and isinstance(getattr(alarm, "escalated_at", None), datetime):
            baseline = alarm.escalated_at
        if baseline is None:
            return None

        # SQLite 读出的 naive datetime 视为 UTC, 与 aware 的 now 对齐
        # (时区改造 facf21db3 遗漏点: alarm.created_at 落库后读出为 naive)
        if baseline.tzinfo is None and now.tzinfo is not None:
            baseline = baseline.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now - baseline).total_seconds() / 60.0
        
        # 升级规则
        if alarm.level == AlarmLevel.WARNING and elapsed_minutes >= timeout_minutes:
            # WARN → ERROR
            old_level = alarm.level.value
            try:
                alarm.original_level = alarm.original_level or old_level
                alarm.escalated_from = f"{old_level}→{AlarmLevel.CRITICAL.value}"
                alarm.level = AlarmLevel.CRITICAL
                alarm.escalated_at = now
                alarm.content = f"[已升级] {alarm.content} (WARN→ERROR, 超时{int(elapsed_minutes)}分钟)"
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("[升级] 告警 #%s 写库失败: %s", alarm.id, e)
                return None
            logger.info(
                "[升级] 告警 #%s %s→%s (超时 %.1f 分钟)",
                alarm.id, old_level, AlarmLevel.CRITICAL.value, elapsed_minutes
            )
            
            # 升级后触发通知
            channels = self._get_notify_channels_for_level(AlarmLevel.CRITICAL)
            notification_dispatcher.dispatch_on_alarm(alarm, db, channels)
            
            return {
                'alarm_id': alarm.id,
                'device_id': alarm.device_id,
                'from_level': old_level,
                'to_level': AlarmLevel.CRITICAL.value,
                'elapsed_minutes': int(elapsed_minutes),
            }
        
        elif alarm.level == AlarmLevel.CRITICAL and elapsed_minutes >= max(15, timeout_minutes // 2):
            # CRITICAL 15分钟未处理 → 标记为紧急通知
            old_level = alarm.level.value
            try:
                alarm.original_level = alarm.original_level or old_level
                alarm.escalated_from = f"{old_level}→{AlarmLevel.FATAL.value}"
                alarm.level = AlarmLevel.FATAL
                alarm.escalated_at = now
                alarm.content = f"[已升级] {alarm.content} (ERROR→CRITICAL, 超时{int(elapsed_minutes)}分钟)"
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("[升级] 告警 #%s 写库失败: %s", alarm.id, e)
                return None
            logger.info(
                "[升级] 告警 #%s %s→%s (超时 %.1f 分钟)",
                alarm.id, old_level, AlarmLevel.FATAL.value, elapsed_minutes
            )
            
            # 升级后触发更紧急的通知
            channels = self._get_notify_channels_for_level(AlarmLevel.FATAL)
            notification_dispatcher.dispatch_on_alarm(alarm, db, channels)
            
            return {
                'alarm_id': alarm.id,
                'device_id': alarm.device_id,
                'from_level': old_level,
                'to_level': AlarmLevel.FATAL.value,
                'elapsed_minutes': int(elapsed_minutes),
            }
        
        return None

    def escalate_alarm_by_id(self, alarm_id: int, db: Session) -> dict:
        """手动触发指定告警的升级（供API调用）"""
        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            return {'success': False, 'message': '告警不存在'}
        
        if alarm.level == AlarmLevel.FATAL:
            return {'success': False, 'message': '已是最高级别，无需升级'}
        
        result = self._escalate_single(alarm, datetime.now(timezone.utc), db)
        if result:
            return {'success': True, 'data': result}
        
        return {'success': False, 'message': '未达到升级条件'}


# ============================
# 全局引擎实例
# ============================
engine = AlarmRuleEngine()


def evaluate_all_rules():
    """定时任务入口 - 由scheduler.py调用"""
    try:
        results = engine.evaluate_all()
        triggered = [r for r in results if r.get('triggered')]
        if triggered:
            logger.info("告警规则引擎: 评估%d条规则, %d条触发", len(results), len(triggered))
        return results
    except Exception as e:
        logger.exception(f"告警规则引擎执行失败: {e}")
        return []


def scan_and_escalate():
    """定时扫描升级入口 - 由scheduler.py调用"""
    try:
        results = engine.scan_and_escalate()
        if results:
            logger.info("告警升级引擎: %d个告警已升级", len(results))
        return results
    except Exception as e:
        logger.exception(f"告警升级引擎执行失败: {e}")
        return []
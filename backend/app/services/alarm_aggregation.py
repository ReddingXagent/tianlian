"""
告警聚合服务 - 合并同类告警 + 防风暴

功能:
1. 同类型聚合: 相同 device + metric, 5分钟内只发1条
2. 防风暴: 同一类型 30 秒内最多触发 3 次
3. 告警计数 + 首条/末条时间戳
"""
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session

from app.models.alarm import Alarm, AlarmStatus

logger = logging.getLogger(__name__)

# 防风暴抑制哨兵 (卡 2779d516): try_aggregate_alarm 被抑制时返回此对象。
# 旧实现返回 new_alarm 自身, 调用方 (alarm_rule_service._create_alarm) 以
# aggregated.id == alarm.id 判定为「未聚合」走完整路径 → 被抑制的触发反而
# 保留 Alarm 行 + 写日志 + 建工单 + 派发通知, 比聚合分支副作用更重, 防风暴
# 完全失效。改为: 删除刚落库的新告警行并返回 SUPPRESSED, 调用方据此走零副作用路径。
# 用 object() 而非 None/Alarm: None 已被「未聚合(独立新告警)」占用, 哨兵必须
# 与任何 Alarm 实例可区分 (is 判定安全)。
SUPPRESSED = object()

# 聚合窗口配置
AGGREGATION_WINDOW_MINUTES = 5         # 同类告警聚合窗口
ANTI_STORM_WINDOW_SECONDS = 30         # 防风暴窗口
ANTI_STORM_MAX_TRIGGERS = 3            # 防风暴窗口内最大触发次数

# 内存中的防风暴计数器 (device_id, rule_id) -> [timestamps]
# 生产环境建议用 Redis
_storm_counters: Dict[Tuple[int, int], list] = {}
# 保护 _storm_counters 的可重入锁: check_anti_storm 持锁后调用 _clean_storm_counters,
# 后者需重入同一把锁, 故用 RLock 而非 Lock。
_storm_lock = threading.RLock()


def _clean_storm_counters():
    """清理过期的防风暴计数器 (线程安全, _storm_lock 串行化迭代+删除)"""
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=ANTI_STORM_WINDOW_SECONDS)
        with _storm_lock:
            expired = [
                k for k, v in _storm_counters.items()
                if all(ts < cutoff for ts in v)
            ]
            for k in expired:
                del _storm_counters[k]
    except Exception:
        logger.exception("清理防风暴计数器异常")


def check_anti_storm(device_id: int, rule_id: int) -> bool:
    """
    防风暴检查：同一类型 30 秒内最多触发 3 次
    返回 True = 允许触发, False = 被风暴抑制

    异常时返回 True (放行触发) —— 告警域宁可多发不漏发, 避免因计数器异常丢失告警。
    """
    try:
        key = (device_id, rule_id)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=ANTI_STORM_WINDOW_SECONDS)

        # 锁内只做 _storm_counters 的内存读写 (无 DB/await/慢调用);
        # check-then-act (len 读 → append 写) 纳入同一临界区, 防多线程绕过上限。
        # 抑制计数快照出锁后再记日志, 避免 logging handler 阻塞锁。
        with _storm_lock:
            _clean_storm_counters()  # RLock 可重入

            if key not in _storm_counters:
                _storm_counters[key] = []

            # 过滤窗口内记录
            _storm_counters[key] = [ts for ts in _storm_counters[key] if ts >= cutoff]

            current_count = len(_storm_counters[key])
            if current_count >= ANTI_STORM_MAX_TRIGGERS:
                suppressed = True
            else:
                _storm_counters[key].append(now)
                suppressed = False

        if suppressed:
            logger.warning(
                "[防风暴] 抑制告警 device=%s rule=%s 窗口内已触发 %d 次",
                device_id, rule_id, current_count
            )
            return False
        return True
    except Exception:
        logger.exception(
            "防风暴检查异常 device=%s rule=%s，放行触发（宁可多发不漏发）",
            device_id, rule_id,
        )
        return True


def find_aggregatable_alarm(
    device_id: int,
    rule_id: int,
    db: Session,
    exclude_id: Optional[int] = None,
) -> Optional[Alarm]:
    """
    查找可聚合的已有告警：
    - 相同 device + rule
    - 相同级别
    - ACTIVE 状态
    - 在聚合窗口内（5分钟内）

    exclude_id: 排除指定告警(传入新告警自身 id)，避免 order_by(created_at desc)
    把刚落库的新告警查到自身导致自聚合(计数虚高)。detached 新告警 id 为 None 时不排除。

    异常时返回 None —— 视为无可聚合告警, 新告警按独立告警落库, 不丢失。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=AGGREGATION_WINDOW_MINUTES)

        filters = [
            Alarm.device_id == device_id,
            Alarm.rule_id == rule_id,
            Alarm.status == AlarmStatus.ACTIVE,
            Alarm.created_at >= cutoff,
            Alarm.escalated_from.is_(None),  # 不聚合已升级的告警
        ]
        if exclude_id is not None:
            filters.append(Alarm.id != exclude_id)

        return db.query(Alarm).filter(*filters).order_by(Alarm.created_at.desc()).first()
    except Exception:
        logger.exception(
            "查找可聚合告警异常 device=%s rule=%s，返回 None 按新告警处理",
            device_id, rule_id,
        )
        return None


def update_aggregated_alarm(
    alarm: Alarm,
    current_value: float,
    db: Session
) -> Alarm:
    """
    更新聚合告警的计数和时间戳

    异常时回滚事务并返回原 alarm —— 计数可能未更新, 但告警记录本身不丢失。
    """
    try:
        alarm.aggregation_count = (alarm.aggregation_count or 1) + 1
        if alarm.aggregation_last_at is None:
            alarm.aggregation_last_at = datetime.now(timezone.utc)
        else:
            alarm.aggregation_last_at = datetime.now(timezone.utc)

        # 更新触发器值（保留最新值）
        alarm.trigger_value = current_value

        db.commit()
        db.refresh(alarm)

        logger.info(
            "[聚合] 告警 #%s 已聚合 %d 次 (device=%s, rule=%s)",
            alarm.id, alarm.aggregation_count, alarm.device_id, alarm.rule_id
        )

        return alarm
    except Exception:
        logger.exception(
            "更新聚合告警异常 alarm_id=%s，回滚保持原状",
            getattr(alarm, 'id', None),
        )
        try:
            db.rollback()
        except Exception:
            logger.exception(
                "rollback 失败 alarm_id=%s",
                getattr(alarm, 'id', None),
            )
        return alarm


def try_aggregate_alarm(
    new_alarm: Alarm,
    db: Session
) -> Optional[Alarm]:
    """
    尝试聚合告警。
    - 被防风暴抑制: 删除新告警行, 返回 SUPPRESSED 哨兵 (零副作用, 卡 2779d516)
    - 找到可聚合的已有告警: 更新它并返回
    - 否则: 初始化新告警聚合字段, 返回 None (独立新告警)

    异常时兜底初始化 new_alarm 的聚合字段并尝试 commit, 保证告警不丢失, 返回 None。
    """
    try:
        # 先检查防风暴
        if not check_anti_storm(new_alarm.device_id, new_alarm.rule_id):
            # 风暴抑制 (卡 2779d516): 删除刚落库的新告警行并返回 SUPPRESSED 哨兵。
            # 被抑制的触发不产生任何独立记录/日志/工单/通知 (防风暴语义)。
            db.delete(new_alarm)
            db.commit()
            return SUPPRESSED

        # 查找可聚合的告警(排除新告警自身, 防止自聚合)
        existing = find_aggregatable_alarm(
            new_alarm.device_id, new_alarm.rule_id, db,
            exclude_id=new_alarm.id,
        )

        if existing:
            # 更新已有告警
            return update_aggregated_alarm(existing, new_alarm.trigger_value, db)

        # 没有可聚合的，初始化新告警的聚合字段
        new_alarm.aggregation_count = 1
        new_alarm.aggregation_first_at = datetime.now(timezone.utc)
        new_alarm.aggregation_last_at = datetime.now(timezone.utc)
        db.commit()
        return None
    except Exception:
        logger.exception(
            "告警聚合异常，兜底初始化保证不丢失告警 device=%s rule=%s",
            getattr(new_alarm, 'device_id', None),
            getattr(new_alarm, 'rule_id', None),
        )
        # 兜底: 确保新告警带有有效聚合字段并落库, 不丢失告警数据
        try:
            now = datetime.now(timezone.utc)
            if not getattr(new_alarm, 'aggregation_count', None):
                new_alarm.aggregation_count = 1
            if getattr(new_alarm, 'aggregation_first_at', None) is None:
                new_alarm.aggregation_first_at = now
            new_alarm.aggregation_last_at = now
            db.commit()
        except Exception:
            logger.exception(
                "兜底初始化/commit 失败，回滚 device=%s",
                getattr(new_alarm, 'device_id', None),
            )
            try:
                db.rollback()
            except Exception:
                logger.warning("告警聚合回滚失败", exc_info=True)
        return None


def get_aggregation_stats(device_id: int, db: Session) -> dict:
    """
    获取指定设备的告警聚合统计

    异常时返回空列表 —— 统计失败不影响告警本身。
    """
    try:
        from sqlalchemy import func as sqlfunc

        result = db.query(
            Alarm.rule_id,
            sqlfunc.count(Alarm.id).label('total_count'),
            sqlfunc.sum(Alarm.aggregation_count).label('total_aggregated'),
            sqlfunc.min(Alarm.aggregation_first_at).label('first_at'),
            sqlfunc.max(Alarm.aggregation_last_at).label('last_at'),
        ).filter(
            Alarm.device_id == device_id,
            Alarm.status == AlarmStatus.ACTIVE,
            Alarm.aggregation_count > 1,
        ).group_by(Alarm.rule_id).all()

        return [
            {
                'rule_id': r[0],
                'total_alarms': r[1],
                'total_aggregated': r[2] or r[1],
                'first_at': r[3].isoformat() if r[3] else None,
                'last_at': r[4].isoformat() if r[4] else None,
            }
            for r in result
        ]
    except Exception:
        logger.exception(
            "获取告警聚合统计异常 device=%s，返回空列表",
            device_id,
        )
        return []

"""
数据看板服务
实时统计 + 趋势分析 + 运维绩效
Phase5-16: SQL聚合优化 + 缓存装饰器
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_, case, extract
from app.models.station import Station
from app.models.device import Device, DeviceHealthRecord
from app.models.workorder import WorkOrder
from app.models.alarm import Alarm
from app.models.user import User
from app.core.cache import cached
from app.tasks.tz_utils import today_in_biz_tz

# ── 时区契约 ──────────────────────────────────────────────────────────────
# 存储侧统一 UTC:
#   - WorkOrder.finish_time 等业务时间由 datetime.now(timezone.utc) 写入 (UTC)
#   - create_time/updated_at/created_at 由 server_default=func.now() 写入,
#     SQLite 的 CURRENT_TIMESTAMP 即 UTC (见 commit 5c285be8b notifications 时区修复)
# "今日" 口径 (卡 ba16a9ff) 已切换为业务时区 (默认上海) 自然日 —— 与
# app/api/v1/alarms.py:483 (today_in_biz_tz) 同一模式: func.date(UTC时间戳)
# 仍是 UTC 日, 但日期比较基准取业务今天。已知局限 (与 alarms 相同): 凌晨窗口
# 上海 00:00-08:00 完成的工单 func.date=业务昨天, 仍会漏统计该窗口;
# 彻底修复需 DB 层时区转换 (跨库兼容性, 范围外)。
UTC_TZ = timezone.utc

logger = logging.getLogger(__name__)


def _utc_today():
    """返回今日日期 (业务时区自然日, 卡 ba16a9ff; 函数名保留兼容既有引用)。"""
    return today_in_biz_tz()


def _biz_today_bounds_utc_naive() -> tuple:
    """业务今日 [start, end) 半开区间, 换算为 UTC-naive (与落库口径一致, 卡 70202e7b)。

    ba16a9ff 已知局限的彻底修复: ``func.date(UTC时间戳) == 业务今天`` 在上海
    00:00-08:00 窗口 (业务今天 = UTC 昨天) 整体错窗 —— 该窗口内完工的工单
    func.date = UTC 昨天 ≠ 业务今天, today_completed 恒 0。改用区间比较后
    时间戳直接与业务日墙钟窗换算的 UTC-naive 边界比较, 不再依赖 func.date
    的隐式 UTC 截断, 任何时区/任何时刻口径均正确。
    """
    from app.tasks.tz_utils import biz_day_bounds_utc_naive
    return biz_day_bounds_utc_naive(today_in_biz_tz())


def _hours_between(dialect_name, start_col, end_col):
    """返回 (end_col - start_col) 的小时数 SQL 表达式, 方言兼容。

    SQLite  : (julianday(end) - julianday(start)) * 24
    Postgres: EXTRACT(EPOCH FROM (end - start)) / 3600
              (julianday 是 SQLite 专有函数, postgres 下直接报错)

    其余/未知方言保守回落 julianday (与历史行为一致)。
    """
    if dialect_name == "postgresql":
        # timestamptz 相减得 interval, EXTRACT(EPOCH ...) 得秒, /3600 得小时
        return extract("epoch", end_col - start_col) / 3600
    return (func.julianday(end_col) - func.julianday(start_col)) * 24


def _db_dialect(db) -> str:
    """取当前会话实际方言名 (sqlite/postgresql); 取不到则回落 sqlite。"""
    try:
        return db.bind.dialect.name
    except Exception:
        return "sqlite"


# Import SessionLocal lazily to allow test overrides
def _get_db():
    from app.core.database import SessionLocal
    return SessionLocal()

def _station_ids_for_team(db, team_id: Optional[int]) -> Optional[list]:
    """团队站点 id 列表 (卡 820cf187)。team_id=None (admin) → None 表示不过滤。

    Device/Alarm/WorkOrder/DeviceHealthRecord 均无 team_id 列, 统一经
    Station.team_id (或 Device.station_id) 过滤。Alarm.station_id 可空 —
    可空行本就不归属任何团队站点, 团队级过滤语义正确 (与 dashboard.py
    large-screen 卡 e61ac986 同一模式)。
    """
    if team_id is None:
        return None
    return [row[0] for row in db.query(Station.id).filter(Station.team_id == team_id).all()]


def _device_team_filters(db, team_id: Optional[int]) -> list:
    """Device 团队过滤条件列表 (卡 820cf187)。team_id=None (admin) → 空 (不过滤)。"""
    if team_id is None:
        return []
    return [Device.station_id.in_(
        db.query(Station.id).filter(Station.team_id == team_id).subquery()
    )]


def _alarm_team_filters(db, team_id: Optional[int]) -> list:
    """Alarm 团队过滤条件列表 (卡 820cf187)。经 station_id 过滤; station_id 可空行
    不归属任何团队站点, 团队级排除语义正确 (与 dashboard.py e61ac986 一致)。"""
    if team_id is None:
        return []
    return [Alarm.station_id.in_(
        db.query(Station.id).filter(Station.team_id == team_id).subquery()
    )]


def _workorder_team_filters(db, team_id: Optional[int]) -> list:
    """WorkOrder 团队过滤条件列表 (卡 820cf187)。WorkOrder 有 station_id 列, 经其过滤
    (与 dashboard.py e61ac986 的 _wo_q 同一路径)。"""
    if team_id is None:
        return []
    return [WorkOrder.station_id.in_(
        db.query(Station.id).filter(Station.team_id == team_id).subquery()
    )]


class StatsService:
    """数据看板服务"""

    def __init__(self):
        pass

    @cached(ttl=30)
    def get_dashboard_overview(self, team_id: Optional[int] = None) -> Dict:
        """
        获取仪表盘总览数据 (Phase5-16优化: 单次聚合查询替代12次独立count)

        team_id (卡 820cf187): None=admin 全量; 非 None → 仅统计本 team
        (站点直接过滤, 设备/告警/工单经站点归属过滤)。@cached 按 (函数名,args,kwargs)
        建 key, team_id 自然区分缓存, 不跨团队串数据。
        """
        db = _get_db()
        try:
            today = _utc_today()
            station_ids = _station_ids_for_team(db, team_id)

            def _device_q():
                q = db.query(Device)
                if station_ids is not None:
                    q = q.filter(Device.station_id.in_(station_ids))
                return q

            def _alarm_q():
                q = db.query(Alarm)
                if station_ids is not None:
                    q = q.filter(Alarm.station_id.in_(station_ids))
                return q

            def _wo_q():
                q = db.query(WorkOrder)
                if station_ids is not None:
                    q = q.filter(WorkOrder.station_id.in_(station_ids))
                return q

            # Phase5-16: 用单次聚合查询替代 12 次独立 count()
            # 站点统计
            station_q = db.query(
                func.count(Station.id).label('total'),
                func.sum(
                    case(
                        (Station.status == 'normal', 1),
                        else_=0
                    )
                ).label('normal')
            )
            if team_id is not None:
                station_q = station_q.filter(Station.team_id == team_id)
            station_stats = station_q.first()
            total_stations = station_stats.total or 0
            normal_stations = station_stats.normal or 0

            # 设备统计 (单次查询)
            device_stats = _device_q().with_entities(
                func.count(Device.id).label('total'),
                func.avg(Device.health_score).label('avg_health'),
                func.sum(case((Device.status == 'online', 1), else_=0)).label('online'),
                func.sum(case((Device.status == 'offline', 1), else_=0)).label('offline'),
                func.sum(case((Device.status == 'fault', 1), else_=0)).label('fault')
            ).first()
            total_devices = device_stats.total or 0
            online_devices = device_stats.online or 0
            offline_devices = device_stats.offline or 0
            fault_devices = device_stats.fault or 0
            # avg_health 真值可能是 0.0 (设备健康分确为 0), 不能用 `or 100` 吞掉;
            # 仅当聚合无结果 (None=无设备) 时才回落默认 100。
            avg_health = device_stats.avg_health if device_stats.avg_health is not None else 100

            # 告警统计 (单次查询)
            alarm_stats = _alarm_q().with_entities(
                func.count(Alarm.id).label('active'),
                func.sum(
                    case(
                        (and_(Alarm.status == 'active', Alarm.level == 'critical'), 1),
                        else_=0
                    )
                ).label('critical')
            ).filter(Alarm.status == 'active').first()
            active_alarms = alarm_stats.active or 0
            critical_alarms = alarm_stats.critical or 0

            # 工单统计 (单次查询)
            # 卡 70202e7b: today_completed 改业务日 UTC-naive 区间比较,
            # 修 func.date==业务今天 在上海 00:00-08:00 窗口整体错窗
            day_start, day_end = _biz_today_bounds_utc_naive()
            order_stats = _wo_q().with_entities(
                func.sum(case((WorkOrder.status == 'pending', 1), else_=0)).label('pending'),
                func.sum(case((WorkOrder.status == 'processing', 1), else_=0)).label('processing'),
                func.sum(
                    case(
                        (and_(
                            WorkOrder.status == 'completed',
                            WorkOrder.finish_time >= day_start,
                            WorkOrder.finish_time < day_end
                        ), 1),
                        else_=0
                    )
                ).label('today_completed')
            ).first()
            pending_orders = order_stats.pending or 0
            processing_orders = order_stats.processing or 0
            today_completed = order_stats.today_completed or 0

            return {
                'stations': {
                    'total': total_stations,
                    'normal': normal_stations,
                    'rate': round(normal_stations / total_stations * 100, 1) if total_stations else 100
                },
                'devices': {
                    'total': total_devices,
                    'online': online_devices,
                    'offline': offline_devices,
                    'fault': fault_devices,
                    'online_rate': round(online_devices / total_devices * 100, 1) if total_devices else 100
                },
                'health': {
                    # avg_health=0.0 是真实零分, 仅 None (无设备) 才回落 100
                    'average': round(avg_health, 1) if avg_health is not None else 100,
                    'trend': self._calc_health_trend(db, team_id)
                },
                'alarms': {
                    'active': active_alarms,
                    'critical': critical_alarms
                },
                'workorders': {
                    'pending': pending_orders,
                    'processing': processing_orders,
                    'today_completed': today_completed
                },
                'update_time': datetime.now(timezone.utc).isoformat()
            }
        finally:
            db.close()

    def _calc_health_trend(self, db, team_id: Optional[int] = None) -> str:
        """计算健康度趋势（对比昨日）"""
        try:
            # 卡 70202e7b: 业务日 UTC-naive 区间比较, 修 func.date==业务日的凌晨错窗
            today_start, today_end = _biz_today_bounds_utc_naive()
            yesterday_start = today_start - timedelta(days=1)

            # 今天和昨天的平均健康度
            today_avg = db.query(func.avg(Device.health_score)).filter(
                Device.updated_at >= today_start,
                Device.updated_at < today_end,
                *_device_team_filters(db, team_id)
            ).scalar()
            yesterday_avg = db.query(func.avg(Device.health_score)).filter(
                Device.updated_at >= yesterday_start,
                Device.updated_at < today_start,
                *_device_team_filters(db, team_id)
            ).scalar()

            if today_avg is not None and yesterday_avg is not None:
                diff = round(float(today_avg) - float(yesterday_avg), 1)
                return f'+{diff}' if diff >= 0 else str(diff)
        except Exception:
            logger.debug("health diff计算失败", exc_info=True)
        return '+0.0'

    def get_health_trend(self, days: int = 7, team_id: Optional[int] = None) -> List[Dict]:
        """获取健康度趋势 (最近 N 天，从数据库查询; 卡 820cf187: team_id 过滤)"""
        db = _get_db()
        try:
            trend = []
            team_dev_filters = _device_team_filters(db, team_id)
            station_ids = _station_ids_for_team(db, team_id)
            for i in range(days):
                date = datetime.now(UTC_TZ) - timedelta(days=days-i-1)
                date_str = date.strftime('%Y-%m-%d')

                # 从 DeviceHealthRecord 查询，若存在
                try:
                    # 单日可能有多条快照, 取最新一条 (created_at DESC) 代表当日最终
                    # 健康态; 不能用裸 .first() (无 order_by 顺序不定), 也不用 avg
                    # (会把日内已过期的旧快照混进均值)。
                    record = db.query(DeviceHealthRecord).filter(
                        func.date(DeviceHealthRecord.created_at) == date.date(),
                        *([] if station_ids is None else [DeviceHealthRecord.device_id.in_(
                            db.query(Device.id).filter(
                                Device.station_id.in_(station_ids)
                            ).subquery()
                        )])
                    ).order_by(DeviceHealthRecord.created_at.desc()).first()
                    # total_score=0.0 也是真实分数, 用 is not None 判定而非真值判定
                    if record is not None and record.total_score is not None:
                        trend.append({'date': date_str, 'score': round(record.total_score, 1)})
                        continue
                except Exception:
                    logger.debug("DeviceHealthRecord查询降级到Device表", exc_info=True)

                # 退而求其次：从设备表查当日更新的平均健康分
                # 注意用 == (当日) 而非 <= (当日及之前累计, 会让 N 天趋势退化为累计值)
                day_avg = db.query(func.avg(Device.health_score)).filter(
                    func.date(Device.updated_at) == date.date(),
                    *team_dev_filters
                ).scalar()
                # 真有数据才出分; 无数据 (None) 该日记 None, 禁止编造 85+(i%3)*2 假值
                if day_avg is not None:
                    score = round(float(day_avg), 1)
                else:
                    score = None
                trend.append({'date': date_str, 'score': score})
            return trend
        finally:
            db.close()

    @cached(ttl=60)
    def get_alarm_stats(self, days: int = 7, team_id: Optional[int] = None) -> Dict:
        """获取告警统计 (Phase5-16优化: SQL聚合替代Python循环; 卡 820cf187: team_id 过滤)"""
        db = _get_db()
        try:
            since = datetime.now(UTC_TZ) - timedelta(days=days)
            alarm_filters = _alarm_team_filters(db, team_id)

            # Phase5-16: SQL 层聚合替代 Python 循环
            # 按级别统计
            by_level_rows = db.query(
                Alarm.level,
                func.count(Alarm.id)
            ).filter(
                Alarm.created_at >= since,
                *alarm_filters
            ).group_by(Alarm.level).all()
            by_level = {'info': 0, 'warning': 0, 'critical': 0, 'fatal': 0}
            total = 0
            for level, count in by_level_rows:
                try:
                    level_str = level.value if hasattr(level, 'value') else str(level)
                except Exception:
                    level_str = str(level)
                by_level[level_str] = count
                total += count

            # 按类型统计
            by_type_rows = db.query(
                Alarm.alarm_type,
                func.count(Alarm.id)
            ).filter(
                Alarm.created_at >= since,
                *alarm_filters
            ).group_by(Alarm.alarm_type).all()
            by_type = {row[0]: row[1] for row in by_type_rows}

            # 趋势对比
            prev_since = since - timedelta(days=days)
            prev_alarms = db.query(func.count(Alarm.id)).filter(
                Alarm.created_at >= prev_since,
                Alarm.created_at < since,
                *alarm_filters
            ).scalar() or 0
            if prev_alarms > 0:
                pct = round((total - prev_alarms) / prev_alarms * 100, 1)
                trend = 'up' if pct > 0 else 'down' if pct < 0 else 'stable'
            elif total > 0:
                # 0 → N 是激增而非持平; 分母为 0 不可比, pct 记 None
                pct = None
                trend = 'up'
            else:
                pct = 0
                trend = 'stable'

            return {
                'total': total,
                'by_level': by_level,
                'by_type': by_type,
                'trend': trend,
                'trend_pct': pct,
            }
        finally:
            db.close()

    @cached(ttl=60)
    def get_workorder_stats(self, days: int = 7, team_id: Optional[int] = None) -> Dict:
        """获取工单统计 (Phase5-16优化: SQL聚合替代Python循环; 卡 820cf187: team_id 过滤)"""
        db = _get_db()
        try:
            since = datetime.now(UTC_TZ) - timedelta(days=days)
            dialect = _db_dialect(db)
            wo_filters = _workorder_team_filters(db, team_id)

            # Phase5-16: SQL 层聚合
            # 按状态统计
            by_status_rows = db.query(
                WorkOrder.status,
                func.count(WorkOrder.id)
            ).filter(
                WorkOrder.create_time >= since,
                *wo_filters
            ).group_by(WorkOrder.status).all()
            by_status = {row[0]: row[1] for row in by_status_rows}
            total = sum(by_status.values())

            # 按类型统计
            by_type_rows = db.query(
                WorkOrder.type,
                func.count(WorkOrder.id)
            ).filter(
                WorkOrder.create_time >= since,
                *wo_filters
            ).group_by(WorkOrder.type).all()
            by_type = {row[0]: row[1] for row in by_type_rows}

            # 平均响应时间 (SQL聚合, 方言兼容: sqlite julianday / postgres EXTRACT EPOCH)
            avg_response_result = db.query(
                func.avg(_hours_between(dialect, WorkOrder.create_time, WorkOrder.accept_time))
            ).filter(
                WorkOrder.create_time >= since,
                WorkOrder.accept_time.isnot(None),
                *wo_filters
            ).scalar()
            avg_response = round(float(avg_response_result), 1) if avg_response_result is not None else 0

            # 平均完工时间 (SQL聚合, 方言兼容)
            avg_completion_result = db.query(
                func.avg(_hours_between(dialect, WorkOrder.accept_time, WorkOrder.finish_time))
            ).filter(
                WorkOrder.create_time >= since,
                WorkOrder.accept_time.isnot(None),
                WorkOrder.finish_time.isnot(None),
                *wo_filters
            ).scalar()
            avg_completion = round(float(avg_completion_result), 1) if avg_completion_result is not None else 0

            return {
                'total': total,
                'by_status': by_status,
                'by_type': by_type,
                'avg_response_hours': avg_response,
                'avg_completion_hours': avg_completion,
            }
        finally:
            db.close()

    @cached(ttl=120)
    def get_engineer_performance(self, team_id: Optional[int] = None) -> List[Dict]:
        """获取工程师绩效排名 (Phase5-16优化: 批量聚合替代N+1循环查询)

        卡 820cf187: team_id 非 None → 仅返回本 team 的 engineer (User.team_id)。
        """
        db = _get_db()
        try:
            dialect = _db_dialect(db)
            eng_q = db.query(User).filter(User.role == 'engineer')
            if team_id is not None:
                eng_q = eng_q.filter(User.team_id == team_id)
            engineers = eng_q.all()

            if not engineers:
                return []

            engineer_ids = [eng.id for eng in engineers]

            # Phase5-16: 批量聚合查询替代 N+1
            # 工单总数 (按工程师分组)
            total_counts = dict(
                db.query(
                    WorkOrder.assignee_id,
                    func.count(WorkOrder.id)
                ).filter(
                    WorkOrder.assignee_id.in_(engineer_ids)
                ).group_by(WorkOrder.assignee_id).all()
            )

            # 已完成工单数 (按工程师分组)
            completed_counts = dict(
                db.query(
                    WorkOrder.assignee_id,
                    func.count(WorkOrder.id)
                ).filter(
                    and_(
                        WorkOrder.assignee_id.in_(engineer_ids),
                        WorkOrder.status == 'completed'
                    )
                ).group_by(WorkOrder.assignee_id).all()
            )

            # 已完成工单总耗时 (按工程师分组, 仅计算有accept_time和finish_time的)
            completion_hours = dict(
                db.query(
                    WorkOrder.assignee_id,
                    func.sum(_hours_between(dialect, WorkOrder.accept_time, WorkOrder.finish_time))
                ).filter(
                    and_(
                        WorkOrder.assignee_id.in_(engineer_ids),
                        WorkOrder.status == 'completed',
                        WorkOrder.accept_time.isnot(None),
                        WorkOrder.finish_time.isnot(None)
                    )
                ).group_by(WorkOrder.assignee_id).all()
            )

            performance_list = []
            for eng in engineers:
                total = total_counts.get(eng.id, 0)
                completed = completed_counts.get(eng.id, 0)
                completion_rate = completed / total * 100 if total else 0
                total_hours = completion_hours.get(eng.id, 0) or 0
                avg_hours = round(total_hours / completed, 1) if completed and total_hours else 0

                # avg_hours 偏大时 (100 - avg_hours*5) 会变负, score 钳制到 [0, 100]
                raw_score = completion_rate * 0.7 + (100 - avg_hours * 5) * 0.3
                performance_list.append({
                    'id': eng.id,
                    'name': eng.real_name or eng.username,
                    'level': eng.level.value if eng.level else 'junior',
                    'total_orders': total,
                    'completed_orders': completed,
                    'completion_rate': round(completion_rate, 1),
                    'avg_hours': avg_hours,
                    'score': round(max(0, min(100, raw_score)), 1)
                })

            performance_list.sort(key=lambda x: x['score'], reverse=True)
            return performance_list
        finally:
            db.close()


# 单例
stats_service = StatsService()

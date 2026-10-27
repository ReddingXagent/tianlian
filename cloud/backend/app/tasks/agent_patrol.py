"""
天链智能体巡检任务 (设计文档 §5.1)

三类巡检, 全部纯代码逻辑, 不调 LLM:
- patrol_maintenance(team_id): 运维巡检 (设备离线 / 储能SOC / 桩功率异常)
- patrol_operations(team_id):  运营巡检 (异常订单 / 低余额车队 / 场站配置缺失)
- patrol_platform():           平台巡检 (API健康 / 磁盘空间 / Celery队列)

每个发现记录到 agent_memory (category=finding), 不直接调 LLM。
*_all 任务遍历所有活跃 Team 分发对应单租户巡检。

实现约定:
- _run_db_task 动态 import SessionLocal (兼容 conftest test_db override)
- 单个检查项失败不拖垮整轮巡检 (毒记录隔离, try/except 逐项)
- 所有时间用 UTC
"""
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List

import requests
from celery import shared_task
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services import agent_memory_service
from app.tasks._soft_timeout import SoftTimeLimitExceeded  # 卡 411936df

logger = logging.getLogger(__name__)

# 巡检阈值常量 (集中在顶部, 便于调参)
HEARTBEAT_OFFLINE_MINUTES = 10      # 心跳超过该分钟数视为离线
BATTERY_LOW_SOC = 10.0              # 储能 SOC 低于此值告警
ENTERPRISE_LOW_BALANCE = Decimal("100")  # 车队余额告警阈值(元)
ABNORMAL_ORDER_MIN_DURATION = 1     # 订单时长<该分钟数且金额>0 视为异常
PLATFORM_HEALTH_URL = os.getenv(
    "PLATFORM_HEALTH_URL",
    "http://localhost:8000/api/v1/health",
)
DISK_HIGH_USAGE_PCT = 85            # 磁盘使用率告警阈值(%)
CELERY_QUEUE_HIGH = 1000            # Celery 待处理任务告警阈值


# ---------------------------------------------------------------------------
# DB 任务包装器 (动态 import SessionLocal, 兼容测试 override)
# ---------------------------------------------------------------------------
def _as_utc(dt: datetime) -> datetime:
    """把读回的时间归一化为 aware UTC。

    SQLite 不存 tzinfo (DateTime(timezone=True) 在 SQLite 退化为 naive),
    读回的 last_heartbeat/timestamp 为 naive, 直接与 aware 的 now 相减会
    TypeError (naive vs aware)。统一当 UTC 处理 (入库时本就是 UTC 墙钟)。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _run_db_task(func: Callable[[Session], Any]):
    """统一的数据库任务包装器 (参考 maintenance_tasks._run_db_task)。

    与原版的差异: SessionLocal 在函数体内动态 import, 使 conftest test_db
    fixture 的模块级 override 能对本任务生效 (见 memory:
    service-sessionlocal-import-binding)。
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        result = func(db)
        db.commit()
        return result
    except SoftTimeLimitExceeded:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.error("巡检任务执行失败", exc_info=True)
        raise
    finally:
        db.close()


def _get_active_team_ids(db: Session) -> List[int]:
    """获取所有活跃 Team 的 ID (巡检遍历入口)。"""
    from app.models.user import Team
    rows = db.query(Team.id).all()
    return [r[0] for r in rows]


FINDING_SILENCE_HOURS = 1  # 同源 finding 去重静默窗口 (未处理则一直压制)


def _has_recent_finding(db: Session, team_id: int, source: str, related_id: str) -> bool:
    """同 team+source+related_id 是否已有近期(静默窗口内)或未处理的 finding。

    去重参照 fleet_alert_service._has_active_record 先例:
    - status 为 open/acknowledged (未 resolved) → 压制
    - 已 resolved 但仍在静默窗口内 → 压制 (防抖)
    """
    from app.models.agent_memory import AgentMemory
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FINDING_SILENCE_HOURS)
    q = (
        db.query(AgentMemory.id)
        .filter(
            AgentMemory.team_id == team_id,
            AgentMemory.source == source,
            AgentMemory.related_id == str(related_id),
        )
        .filter(
            (AgentMemory.status != "resolved")
            | (AgentMemory.created_at >= cutoff)
        )
    )
    return q.first() is not None


def _save_finding(db: Session, team_id: int, board: str, **kwargs) -> bool:
    """在当前 db 会话内写一条 finding (不自行 commit, 由 _run_db_task 统一提交)。

    幂等去重: 同 team+source+related_id 已有近期未处理 finding 则跳过
    (Celery 每5分钟巡检 + task_acks_late 重投递场景下不会重复刷屏)。
    返回是否实际写入。related_id 为空 (如平台巡检) 时不判重, 保持原行为。
    """
    from app.models.agent_memory import AgentMemory
    source = kwargs.get("source")
    related_id = kwargs.get("related_id")
    if source and related_id is not None:
        try:
            if _has_recent_finding(db, team_id, source, related_id):
                return False
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            # 去重查询失败不阻断巡检, 退化为直接写 (宁可重复不可漏报)
            logger.warning("[巡检] finding 去重查询失败 team=%s source=%s", team_id, source, exc_info=True)
    db.add(AgentMemory(
        team_id=team_id,
        board=board,
        category="finding",
        **kwargs,
    ))
    return True


def _latest_telemetry_rows(db: Session, model, device_ids: List[int]) -> list:
    """按 device_id 取每设备最新一条遥测行 (窗口子查询, 避免全表历史行扫描)。

    返回去重后的最新行列表, 同设备多条历史行只取 timestamp 最大的一条。
    SQLite/PG 兼容: 纯标准窗口函数子查询, 无行锁。
    """
    from sqlalchemy.orm import aliased

    latest_ts = (
        db.query(
            model.device_id,
            func.max(model.timestamp).label("max_ts"),
        )
        .filter(model.device_id.in_(device_ids))
        .group_by(model.device_id)
        .subquery()
    )
    row_alias = aliased(model)
    return (
        db.query(model)
        .join(
            latest_ts,
            (model.device_id == latest_ts.c.device_id)
            & (model.timestamp == latest_ts.c.max_ts),
        )
        # 同设备同 timestamp 并列时按 id 去重, 每设备只留一行
        .distinct(model.device_id)
        .all()
    ) if _supports_distinct_on(db) else _latest_telemetry_rows_fallback(db, model, device_ids, row_alias, latest_ts)


def _supports_distinct_on(db: Session) -> bool:
    """DISTINCT ON 仅 PG 支持, SQLite 需走 fallback。"""
    return db.get_bind().dialect.name == "postgresql"


def _latest_telemetry_rows_fallback(db: Session, model, device_ids, row_alias, latest_ts):
    """SQLite 兼容: join 后同设备可能多行, 内存按 device_id 取 id 最大一条。"""
    rows = (
        db.query(model)
        .join(
            latest_ts,
            (model.device_id == latest_ts.c.device_id)
            & (model.timestamp == latest_ts.c.max_ts),
        )
        .all()
    )
    best: Dict[int, Any] = {}
    for r in rows:
        if r.device_id not in best or r.id > best[r.device_id].id:
            best[r.device_id] = r
    return list(best.values())


# ---------------------------------------------------------------------------
# 1. 运维巡检
# ---------------------------------------------------------------------------
def _patrol_maintenance_single(team_id: int) -> Dict[str, Any]:
    """单租户运维巡检 (内部实现, 供 *_all 与 @shared_task 共用)。

    返回 {"findings": N, "checks": {...}}
    """
    findings_count = {"value": 0}

    def _execute(db: Session) -> Dict[str, Any]:
        from app.models.device import Device
        from app.models.station import Station
        from app.models.telemetry_v2 import TelemetryBattery, TelemetryCharger
        from app.models.charging_order import ChargingOrder, OrderStatus

        checks: Dict[str, int] = {}
        now = datetime.now(timezone.utc)
        offline_cutoff = now - timedelta(minutes=HEARTBEAT_OFFLINE_MINUTES)

        # 本租户所有设备 (经 Station.team_id 关联)
        team_device_ids = [
            d.id for d in
            db.query(Device.id)
            .join(Station, Device.station_id == Station.id)
            .filter(Station.team_id == team_id)
            .all()
        ]

        # --- 检查1: 设备离线 (心跳超10分钟 且 状态非 offline) ---
        offline_cnt = 0
        try:
            offline_devices = (
                db.query(Device)
                .join(Station, Device.station_id == Station.id)
                .filter(Station.team_id == team_id)
                .filter(Device.last_heartbeat.isnot(None))
                .filter(Device.last_heartbeat < offline_cutoff)
                .filter(Device.status != "offline")
                .all()
            )
            for dev in offline_devices:
                hb = _as_utc(dev.last_heartbeat)
                minutes = int((now - hb).total_seconds() // 60) if hb else 0
                _save_finding(
                    db, team_id, "maintenance",
                    source="patrol:device_offline",
                    title=f"设备离线: {dev.name}({dev.sn})",
                    content=f"设备 {dev.sn} 已 {minutes} 分钟无心跳 (状态仍为 {dev.status})",
                    severity="warning" if minutes < 30 else "critical",
                    related_type="device",
                    related_id=str(dev.id),
                    importance=0.8,
                )
                offline_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运维巡检] 设备离线检查失败 team=%s", team_id, exc_info=True)
        checks["device_offline"] = offline_cnt

        # --- 检查2: 储能 SOC 异常 (< 阈值, per-device 最新值) ---
        soc_cnt = 0
        try:
            latest_battery = _latest_telemetry_rows(db, TelemetryBattery, team_device_ids) if team_device_ids else []
            low_soc = [r for r in latest_battery if (r.battery_soc or 0) < BATTERY_LOW_SOC]
            for row in low_soc:
                _save_finding(
                    db, team_id, "maintenance",
                    source="patrol:battery_low_soc",
                    title=f"储能SOC过低: 设备 {row.device_id}",
                    content=f"储能设备 {row.device_id} SOC={row.battery_soc:.1f}% < {BATTERY_LOW_SOC}%",
                    severity="critical",
                    related_type="device",
                    related_id=str(row.device_id),
                    importance=0.9,
                )
                soc_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运维巡检] 储能SOC检查失败 team=%s", team_id, exc_info=True)
        checks["battery_low_soc"] = soc_cnt

        # --- 检查3: 桩功率异常 (有活跃订单但功率为0) ---
        power_cnt = 0
        try:
            # 活跃订单关联的设备
            active_order_device_ids = [
                o.device_id for o in
                db.query(ChargingOrder.device_id)
                .filter(ChargingOrder.order_status == OrderStatus.CHARGING)
                .filter(ChargingOrder.device_id.in_(team_device_ids) if team_device_ids else False)
                .distinct()
                .all()
            ]
            if active_order_device_ids:
                # per-device 最新值: 同设备多条遥测行只看最新一条, 避免历史行重复触发
                latest_charger = _latest_telemetry_rows(db, TelemetryCharger, active_order_device_ids)
                zero_power = [
                    r for r in latest_charger
                    if (r.charger_power == 0) or (r.charger_power is None)
                ]
                for row in zero_power:
                    _save_finding(
                        db, team_id, "maintenance",
                        source="patrol:charger_zero_power",
                        title=f"充电桩功率异常: 设备 {row.device_id}",
                        content=f"设备 {row.device_id} 有活跃订单但功率为0",
                        severity="warning",
                        related_type="device",
                        related_id=str(row.device_id),
                        importance=0.7,
                    )
                    power_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运维巡检] 桩功率检查失败 team=%s", team_id, exc_info=True)
        checks["charger_zero_power"] = power_cnt

        findings_count["value"] = sum(checks.values())
        return {"findings": findings_count["value"], "checks": checks}

    return _run_db_task(_execute)


@shared_task(name="agent.patrol.maintenance")
def patrol_maintenance(team_id: int) -> Dict[str, Any]:
    """运维巡检 (单租户) — 每5分钟。"""
    logger.info("[巡检] 运维巡检开始 team=%s", team_id)
    return _patrol_maintenance_single(team_id)


@shared_task(name="agent.patrol.maintenance_all")
def patrol_maintenance_all() -> Dict[str, Any]:
    """运维巡检 (全租户) — 遍历活跃 Team 分发。"""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        team_ids = _get_active_team_ids(db)
    finally:
        db.close()

    total_findings = 0
    for tid in team_ids:
        try:
            r = _patrol_maintenance_single(tid)
            total_findings += r.get("findings", 0)
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.error("[运维巡检] team=%s 失败", tid, exc_info=True)
    return {"total_teams": len(team_ids), "total_findings": total_findings}


# ---------------------------------------------------------------------------
# 2. 运营巡检
# ---------------------------------------------------------------------------
def _patrol_operations_single(team_id: int) -> Dict[str, Any]:
    """单租户运营巡检。"""

    def _execute(db: Session) -> Dict[str, Any]:
        from app.models.enterprise import Enterprise
        from app.models.station import Station
        from app.models.charging_order import ChargingOrder, OrderStatus

        checks: Dict[str, int] = {}
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # --- 检查1: 异常订单 (金额>0 但时长<1分钟) ---
        abnormal_cnt = 0
        try:
            team_station_ids = [
                s.id for s in
                db.query(Station.id).filter(Station.team_id == team_id).all()
            ]
            abnormal_orders = (
                db.query(ChargingOrder)
                .filter(ChargingOrder.station_id.in_(team_station_ids) if team_station_ids else False)
                .filter(ChargingOrder.total_amount > 0)
                .filter(ChargingOrder.duration_minutes < ABNORMAL_ORDER_MIN_DURATION)
                .filter(ChargingOrder.order_status.in_([OrderStatus.COMPLETED]))
                .all()
            )
            for o in abnormal_orders:
                _save_finding(
                    db, team_id, "operations",
                    source="patrol:abnormal_order",
                    title=f"异常订单: {o.order_no}",
                    content=(
                        f"订单 {o.order_no} 金额 {o.total_amount} 元但时长仅 "
                        f"{o.duration_minutes} 分钟"
                    ),
                    severity="warning",
                    related_type="order",
                    related_id=str(o.id),
                    importance=0.6,
                )
                abnormal_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运营巡检] 异常订单检查失败 team=%s", team_id, exc_info=True)
        checks["abnormal_order"] = abnormal_cnt

        # --- 检查2: 低余额车队 (< 100元) ---
        low_balance_cnt = 0
        try:
            low_balance_fleets = (
                db.query(Enterprise)
                .filter(Enterprise.owner_team_id == team_id)
                .filter(Enterprise.balance < ENTERPRISE_LOW_BALANCE)
                .all()
            )
            for ent in low_balance_fleets:
                _save_finding(
                    db, team_id, "operations",
                    source="patrol:low_balance_fleet",
                    title=f"车队余额不足: {ent.name}",
                    content=f"车队 {ent.name}({ent.code}) 余额仅 {ent.balance} 元",
                    severity="critical",
                    related_type="enterprise",
                    related_id=str(ent.id),
                    importance=0.85,
                )
                low_balance_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运营巡检] 低余额车队检查失败 team=%s", team_id, exc_info=True)
        checks["low_balance_fleet"] = low_balance_cnt

        # --- 检查3: 场站配置缺失 (关键字段为空) ---
        config_missing_cnt = 0
        try:
            from sqlalchemy import or_
            stations = (
                db.query(Station)
                .filter(Station.team_id == team_id)
                .filter(
                    or_(
                        Station.total_power.is_(None),
                        Station.total_power == 0,
                        Station.address.is_(None),
                        Station.address == "",
                    )
                )
                .all()
            )
            for st in stations:
                missing = []
                if not st.total_power:
                    missing.append("总功率")
                if not st.address:
                    missing.append("地址")
                _save_finding(
                    db, team_id, "operations",
                    source="patrol:station_config_missing",
                    title=f"场站配置缺失: {st.name}",
                    content=f"场站 {st.name}({st.code}) 缺失: {'/'.join(missing)}",
                    severity="info",
                    related_type="station",
                    related_id=str(st.id),
                    importance=0.4,
                )
                config_missing_cnt += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.warning("[运营巡检] 场站配置检查失败 team=%s", team_id, exc_info=True)
        checks["station_config_missing"] = config_missing_cnt

        return {"findings": sum(checks.values()), "checks": checks}

    return _run_db_task(_execute)


@shared_task(name="agent.patrol.operations")
def patrol_operations(team_id: int) -> Dict[str, Any]:
    """运营巡检 (单租户) — 每10分钟。"""
    logger.info("[巡检] 运营巡检开始 team=%s", team_id)
    return _patrol_operations_single(team_id)


@shared_task(name="agent.patrol.operations_all")
def patrol_operations_all() -> Dict[str, Any]:
    """运营巡检 (全租户) — 遍历活跃 Team 分发。"""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        team_ids = _get_active_team_ids(db)
    finally:
        db.close()

    total_findings = 0
    for tid in team_ids:
        try:
            r = _patrol_operations_single(tid)
            total_findings += r.get("findings", 0)
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            logger.error("[运营巡检] team=%s 失败", tid, exc_info=True)
    return {"total_teams": len(team_ids), "total_findings": total_findings}


# ---------------------------------------------------------------------------
# 3. 平台巡检 (不按租户)
# ---------------------------------------------------------------------------
def _patrol_platform_single() -> Dict[str, Any]:
    """平台巡检: API健康 / 磁盘空间 / Celery队列。finding 落库用第一个活跃 team。"""

    def _execute(db: Session) -> Dict[str, Any]:
        checks: Dict[str, Any] = {}

        # 平台 finding 需要 team_id 落库 (agent_memory.team_id NOT NULL);
        # 取第一个活跃 team 作为载体, 平台级问题本就跨租户可见。
        from app.models.user import Team
        carrier_team = db.query(Team.id).first()
        carrier_team_id = carrier_team[0] if carrier_team else None

        # --- 检查1: API 健康 ---
        api_status = "healthy"
        try:
            resp = requests.get(PLATFORM_HEALTH_URL, timeout=5)
            if resp.status_code != 200:
                api_status = f"unhealthy(http={resp.status_code})"
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            api_status = f"unreachable({type(e).__name__})"
        checks["api_health"] = api_status
        if api_status != "healthy" and carrier_team_id:
            _save_finding(
                db, carrier_team_id, "admin",
                source="patrol:api_health",
                title=f"API健康检查异常: {api_status}",
                content=f"健康端点 {PLATFORM_HEALTH_URL} 返回 {api_status}",
                severity="critical",
                related_type="system",
                importance=0.95,
            )

        # --- 检查2: 磁盘空间 ---
        disk_status = "ok"
        disk_used_pct = 0.0
        try:
            usage = shutil.disk_usage("/")
            disk_used_pct = (usage.used / usage.total) * 100 if usage.total else 0
            if disk_used_pct >= DISK_HIGH_USAGE_PCT:
                disk_status = f"high({disk_used_pct:.1f}%)"
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            disk_status = "unknown"
        checks["disk_usage"] = disk_status
        if disk_status not in ("ok", "unknown") and carrier_team_id:
            _save_finding(
                db, carrier_team_id, "admin",
                source="patrol:disk_usage",
                title=f"磁盘空间告警: {disk_used_pct:.1f}%",
                content=f"根分区使用率 {disk_used_pct:.1f}% 超过阈值 {DISK_HIGH_USAGE_PCT}%",
                severity="warning",
                related_type="system",
                importance=0.7,
            )

        # --- 检查3: Celery 队列堆积 ---
        queue_status = "ok"
        active_count = 0
        try:
            from app.core.celery_app import celery_app, CELERY_AVAILABLE
            if CELERY_AVAILABLE:
                inspector = celery_app.control.inspect()
                active = inspector.active() or {}
                active_count = sum(len(v) for v in active.values())
                if active_count > CELERY_QUEUE_HIGH:
                    queue_status = f"backlog({active_count})"
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            queue_status = "inspect_failed"
        checks["celery_queue"] = queue_status
        if queue_status not in ("ok", "inspect_failed") and carrier_team_id:
            _save_finding(
                db, carrier_team_id, "admin",
                source="patrol:celery_queue",
                title=f"Celery队列堆积: {active_count} 个活跃任务",
                content=f"Celery 活跃任务 {active_count} 超过阈值 {CELERY_QUEUE_HIGH}",
                severity="warning",
                related_type="system",
                importance=0.6,
            )

        # 统计本轮落库的 finding 数 (非健康检查项数)
        finding_keys = ("api_health", "disk_usage", "celery_queue")
        findings_n = sum(1 for k in finding_keys if checks.get(k) not in (
            "healthy", "ok", "unknown", "inspect_failed", ""
        ))
        return {"findings": findings_n, "checks": checks}

    return _run_db_task(_execute)


@shared_task(name="agent.patrol.platform")
def patrol_platform() -> Dict[str, Any]:
    """平台巡检 — 每30分钟, 不按租户。"""
    logger.info("[巡检] 平台巡检开始")
    return _patrol_platform_single()

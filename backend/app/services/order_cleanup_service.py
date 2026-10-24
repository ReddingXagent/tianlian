"""充电订单 pending 超时清理服务 (卡 6ff02fd2, 契约 §7.1)

契约 §7.1: 创建订单后云端下发 OCPP RemoteStart, 若 charger 无 StartTransaction 确认,
order_status 停留在 pending。本服务扫描超时 pending 订单 → 标记 cancelled, 防止僵尸订单
长期占用 connector / 阻塞用户重新建单。

入口:
- cleanup_stale_pending_orders(db, timeout_minutes=10): 批量清理超时 pending 订单。
- cancel_stale_pending_for_user(db, user_id, timeout_minutes=10): 单用户清理, 供建单防御逻辑用。
- cancel_stale_pending_for_connector(db, device_id, connector_id, timeout_minutes=10):
  按 connector 清理, 供 create_order CONNECTOR_BUSY 分支跨用户即时豁免 (卡 eb9f824b)。

时区: ChargingOrder.created_at 存 UTC; SQLite 读回为 naive (无 tzinfo), 比较前统一补 UTC。
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.charging_order import ChargingOrder, OrderStatus
from app.services import ocpp_dispatch

logger = logging.getLogger(__name__)

# pending 超时取消的原因标记 (区别于用户主动取消的 user_manual / 停止充电的 full 等)
_PENDING_TIMEOUT_REASON = "pending_timeout"


def _ensure_aware_utc(dt: datetime) -> datetime:
    """naive datetime 视为 UTC 并补 tzinfo; aware 原样返回。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def cleanup_stale_pending_orders(db: Session, timeout_minutes: int = 10) -> dict:
    """扫描 pending 状态超过 timeout_minutes 的订单, 标记为 cancelled。

    Args:
        db: SQLAlchemy Session (调用方负责事务边界; 本函数内部 commit)。
        timeout_minutes: pending 超时阈值 (分钟), 默认 10。

    Returns:
        {"cancelled": N} —— 本次清理的订单数。

    异常保护: 查询/写库抛异常时 rollback + 记录 + 返回 {"cancelled": 0} (卡 a6e2e562),
    不阻塞调用方 (定时任务/建单防御)。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale = (
            db.query(ChargingOrder)
            .filter(ChargingOrder.order_status == OrderStatus.PENDING)
            .all()
        )
        now = datetime.now(timezone.utc)
        cancelled = 0
        for order in stale:
            created = _ensure_aware_utc(order.created_at)
            if created < cutoff:
                order.order_status = OrderStatus.CANCELLED
                order.end_time = now
                order.stop_reason = _PENDING_TIMEOUT_REASON
                cancelled += 1
                # pending→cancelled: best-effort 撤销已 accepted 的 RemoteStart
                # (卡 e18ce31e)。pending 必经 create_order RemoteStart accepted (§7.1);
                # 开关 false 时 remote_stop_best_effort 天然 no-op (零回归), 开关 true
                # 走真下发, 失败仅日志不阻塞清理、不回滚。下发走独立 adapter, 先于 commit。
                ocpp_dispatch.remote_stop_best_effort(order)
                logger.info(
                    "pending 超时清理: order_no=%s user_id=%s created_at=%s 超时 %s 分钟 → cancelled",
                    order.order_no, order.user_id, created.isoformat(), timeout_minutes,
                )
        if cancelled:
            db.commit()
        return {"cancelled": cancelled}
    except Exception:
        db.rollback()
        logger.exception("pending 超时清理失败 timeout_minutes=%s", timeout_minutes)
        return {"cancelled": 0}


def cancel_stale_pending_for_user(db: Session, user_id: int, timeout_minutes: int = 10) -> int:
    """取消指定用户 pending 超过 timeout_minutes 的订单, 供 create_order 防御逻辑调用。

    与 cleanup_stale_pending_orders 区别: 仅作用于单用户, 用于建单前清理该用户僵尸订单,
    避免旧 pending 永久阻塞新订单。

    Returns:
        取消的订单数。

    异常保护: 查询/写库抛异常时 rollback + 记录 + 返回 0 (卡 a6e2e562),
    不阻塞建单主流程。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        rows = (
            db.query(ChargingOrder)
            .filter(
                ChargingOrder.user_id == user_id,
                ChargingOrder.order_status == OrderStatus.PENDING,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        cancelled = 0
        for order in rows:
            created = _ensure_aware_utc(order.created_at)
            if created < cutoff:
                order.order_status = OrderStatus.CANCELLED
                order.end_time = now
                order.stop_reason = _PENDING_TIMEOUT_REASON
                cancelled += 1
                # pending→cancelled: best-effort 撤销已 accepted 的 RemoteStart
                # (卡 e18ce31e)。pending 必经 create_order RemoteStart accepted (§7.1);
                # 开关 false 时 remote_stop_best_effort 天然 no-op (零回归), 开关 true
                # 走真下发, 失败仅日志不阻塞清理、不回滚。下发走独立 adapter, 先于 commit。
                ocpp_dispatch.remote_stop_best_effort(order)
                logger.info(
                    "建单防御: 取消用户 %s 的超时 pending 订单 order_no=%s (created %s)",
                    user_id, order.order_no, created.isoformat(),
                )
        if cancelled:
            db.commit()
        return cancelled
    except Exception:
        db.rollback()
        logger.exception("建单防御清理失败 user_id=%s timeout_minutes=%s", user_id, timeout_minutes)
        return 0


def cancel_stale_pending_for_connector(
    db: Session, device_id: int, connector_id: int, timeout_minutes: int = 10
) -> int:
    """取消指定 device+connector 上 pending 超过 timeout_minutes 的订单 (卡 eb9f824b)。

    供 create_order CONNECTOR_BUSY 分支调用: 他人僵尸 pending 占桩时即时清理,
    跨用户阻塞无需等待 5min beat 任务。charging 是真实充电中, 不在查询范围。
    异常保护与 cancel_stale_pending_for_user 一致 (rollback + 记录 + 返回 0)。
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        rows = (
            db.query(ChargingOrder)
            .filter(
                ChargingOrder.device_id == device_id,
                ChargingOrder.connector_id == connector_id,
                ChargingOrder.order_status == OrderStatus.PENDING,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        cancelled = 0
        for order in rows:
            created = _ensure_aware_utc(order.created_at)
            if created < cutoff:
                order.order_status = OrderStatus.CANCELLED
                order.end_time = now
                order.stop_reason = _PENDING_TIMEOUT_REASON
                cancelled += 1
                # pending→cancelled: best-effort 撤销已 accepted 的 RemoteStart
                # (卡 e18ce31e)。pending 必经 create_order RemoteStart accepted (§7.1);
                # 开关 false 时 remote_stop_best_effort 天然 no-op (零回归), 开关 true
                # 走真下发, 失败仅日志不阻塞清理、不回滚。下发走独立 adapter, 先于 commit。
                ocpp_dispatch.remote_stop_best_effort(order)
                logger.info(
                    "占桩豁免: 取消 device=%s connector=%s 的超时 pending 订单 order_no=%s (created %s)",
                    device_id, connector_id, order.order_no, created.isoformat(),
                )
        if cancelled:
            db.commit()
        return cancelled
    except Exception:
        db.rollback()
        logger.exception(
            "占桩豁免清理失败 device_id=%s connector_id=%s timeout_minutes=%s",
            device_id, connector_id, timeout_minutes,
        )
        return 0

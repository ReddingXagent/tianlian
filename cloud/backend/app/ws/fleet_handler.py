"""
车队实时数据处理器 - Phase40 WebSocket 实时推送

为 fleet WebSocket 端点提供排队队列 / V2G 计划状态的快照查询。
复用 charging_queue / fleet_v2g 模型的查询逻辑，产出轻量统计快照；
前端收到推送后通过 REST 拉取完整明细 (WS 作为变更通知 + 准实时快照)。
"""
from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy import func

from app.core import database
from app.models.charging_queue import ChargingQueue
from app.models.fleet_v2g import FleetV2GPlan


class FleetRealtimeHandler:
    """车队实时数据处理器"""

    # ─── 充电排队队列快照 ───

    def get_charging_queue_snapshot(self, station_id: int) -> dict:
        """获取指定电站的充电队列实时快照。

        返回:
            station_id, total, status_counts, waiting_count, charging_count,
            avg_wait_minutes, timestamp
        """
        db = database.SessionLocal()
        try:
            rows = (
                db.query(ChargingQueue.status, func.count(ChargingQueue.id))
                .filter(ChargingQueue.station_id == station_id)
                .group_by(ChargingQueue.status)
                .all()
            )
            status_counts = {status: cnt for status, cnt in rows}

            waiting_rows = db.query(ChargingQueue).filter(
                ChargingQueue.station_id == station_id,
                ChargingQueue.status == "waiting",
            ).all()
            avg_wait = (
                sum(r.estimated_wait_minutes or 0 for r in waiting_rows) / len(waiting_rows)
                if waiting_rows else 0
            )

            total = sum(status_counts.values())
            return {
                "station_id": station_id,
                "total": total,
                "status_counts": status_counts,
                "waiting_count": status_counts.get("waiting", 0),
                "charging_count": status_counts.get("charging", 0),
                "avg_wait_minutes": round(avg_wait, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()

    # ─── V2G 计划状态快照 ───

    def get_v2g_snapshot(self, enterprise_id: int) -> dict:
        """获取指定企业的 V2G 计划状态实时快照。

        返回:
            enterprise_id, total_plans, plan_status_counts, timestamp
        """
        db = database.SessionLocal()
        try:
            rows = (
                db.query(FleetV2GPlan.status, func.count(FleetV2GPlan.id))
                .filter(FleetV2GPlan.enterprise_id == enterprise_id)
                .group_by(FleetV2GPlan.status)
                .all()
            )
            plan_status_counts = defaultdict(int)
            for status, cnt in rows:
                key = status.value if hasattr(status, "value") else str(status)
                plan_status_counts[key] += cnt

            total_plans = sum(plan_status_counts.values())
            return {
                "enterprise_id": enterprise_id,
                "total_plans": total_plans,
                "plan_status_counts": dict(plan_status_counts),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            db.close()

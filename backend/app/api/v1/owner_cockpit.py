"""
天链V3 — 经营驾驶舱 (Owner Cockpit)

面向"充电站拥有者/投资人"视角的聚合数据端点, 聚合收入 / 利用率 / 毛利 / ROI 四类
经营指标。现有 RBAC 无独立 owner 角色, 本模块先对 admin/operator 可见:
  - admin / super_admin: 平台级, 跨团队全见 (is_platform_admin 豁免 team 过滤);
  - operator 等团队级角色: 仅本 team 站点 (team_scope 过滤), 跨团队 station_id → 404。

与 operate/orders、operate/settlement、dashboard 的区别: 后三者偏运营/运维明细,
本模块把"我的场站赚多少 / 利用率多少 / 毛利多少 / 多久回本"做成单一聚合视图。

==== 指标口径 (caliber) ====
  收入 revenue         : Σ paid_amount, 仅 order_status=COMPLETED & payment_status=PAID
  售电量 energy_kwh    : Σ charged_kwh (同上订单过滤)
  购电成本 purchase_cost: Σ charged_kwh × purchase_price
                         默认 0.60 元/kWh (国内一般工商业电价合理估值, Query 可配)。
                         ⚠ 口径简化: 按平台统一购电价估算, 未计光伏自发自用对购电量
                         的抵扣 (光储充场站的 PV 自用会降低实际购电量, 后续若引入
                         energy_report 的 PV 发电量可细化为 net_purchase = max(0, 充电量-PV)。
  毛利 gross_margin    : revenue - purchase_cost (未扣场站折旧/人工/租金等固定成本,
                         属贡献毛利/contribution margin, 非净利润)
  利用率 utilization   : Σ duration_minutes / (Σ gun_count × num_days × 1440) × 100
                         枪位时间利用率; 无 gun_count 的场站不计入分母。
  ROI% roi_rate        : 累计毛利(全时段, 不受时间窗限制) / Σ station.total_cost × 100
  回本月 payback_months: Σ total_cost / 月均毛利; 月均毛利 = 累计毛利 / 运营月数;
                         月均<=0 → null (无法回本)

投资额口径: 复用 Station.total_cost (站点总成本, 元)。Station 无独立 investment/capex
字段, total_cost 即建站投资额的最佳代理。未填 total_cost 的站点 ROI/payback 为 null。

==== 异常保护 (卡 c8d1c0f4) ====
本端点聚合站桩/订单/收益/趋势多表, 任意查询失败不应让整端点 500 崩溃并泄露堆栈。
handler 体包 try/except: HTTPException (404 等) 透传; 其余异常 logger.exception 记录
后返回 JSONResponse(500) 通用消息 (与 operate/revenue_stats 同风格, 不泄露内部路径)。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import team_scope, assert_station_team_access
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus,
)
from app.models.station import Station
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/owner-cockpit",
    tags=["经营驾驶舱"],
    dependencies=[Depends(get_current_user)],
)

# 默认购电价 (元/kWh): 国内一般工商业电价合理估值, 见模块 docstring 口径说明。
DEFAULT_PURCHASE_PRICE = 0.60


def _parse_date(value: Optional[str], default: datetime) -> datetime:
    """解析 YYYY-MM-DD; 空值用 default。"""
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d")


@router.get("/overview")
def get_owner_cockpit_overview(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD, 默认近30天"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD, 默认今天"),
    station_id: Optional[int] = Query(None, description="指定站点; 跨团队 → 404"),
    purchase_price: float = Query(
        DEFAULT_PURCHASE_PRICE, ge=0, description="购电单价 元/kWh, 默认 0.60"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """经营驾驶舱聚合视图: 收入 / 利用率 / 毛利 / ROI。

    返回 summary(KPI) + investment(ROI/回本) + stations(按场站明细) +
    trend(按日序列, 供前端趋势图) + caliber(口径说明)。

    任意聚合查询异常 → logger.exception 记录后返回 500 通用消息, 不泄露堆栈。
    """
    try:
        now = datetime.now(timezone.utc)
        start_dt = _parse_date(start_date, now - timedelta(days=30))
        end_dt = _parse_date(end_date, now)
        # 时间窗含首尾两整天: 订单 created_at ∈ [start_dt, end_dt + 1天)
        next_day = end_dt + timedelta(days=1)
        num_days = max(1, (end_dt - start_dt).days + 1)
        range_minutes = num_days * 24 * 60

        # ── 1. 站点集合 (team 隔离) ──
        tid = team_scope(user)
        st_q = db.query(
            Station.id, Station.name, Station.gun_count,
            Station.total_cost, Station.created_at,
        )
        if tid is not None:
            st_q = st_q.filter(Station.team_id == tid)
        if station_id is not None:
            # 跨团队 / 不存在 → 404 (不泄露存在), 置于查询外
            assert_station_team_access(db, station_id, user)
            st_q = st_q.filter(Station.id == station_id)
        stations = st_q.all()
        station_ids = [s.id for s in stations]

        # ── 2. 订单聚合 (completed + paid) ──
        def _agg_query(*filters):
            """按 station_id 聚合 收入/电量/时长/订单数 (仅 completed+paid)。"""
            q = (
                db.query(
                    ChargingOrder.station_id,
                    func.coalesce(func.sum(ChargingOrder.paid_amount), 0).label("revenue"),
                    func.coalesce(func.sum(ChargingOrder.charged_kwh), 0).label("energy"),
                    func.coalesce(func.sum(ChargingOrder.duration_minutes), 0).label("duration"),
                    func.count(ChargingOrder.id).label("orders"),
                )
                .filter(
                    ChargingOrder.order_status == OrderStatus.COMPLETED,
                    ChargingOrder.payment_status == OrderPaymentStatus.PAID,
                )
                .filter(*filters)
                .group_by(ChargingOrder.station_id)
            )
            return q.all()

        range_map, cum_map = {}, {}
        if station_ids:
            # 区间内聚合
            for r in _agg_query(
                ChargingOrder.station_id.in_(station_ids),
                ChargingOrder.created_at >= start_dt,
                ChargingOrder.created_at < next_day,
            ):
                range_map[r.station_id] = r
            # 全时段累计聚合 (算 ROI 用)
            for r in _agg_query(ChargingOrder.station_id.in_(station_ids)):
                cum_map[r.station_id] = r

        # ── 3. summary ──
        revenue = sum(float(r.revenue or 0) for r in range_map.values())
        energy = sum(float(r.energy or 0) for r in range_map.values())
        order_count = sum(int(r.orders or 0) for r in range_map.values())
        duration = sum(float(r.duration or 0) for r in range_map.values())
        purchase_cost = energy * purchase_price
        gross_margin = revenue - purchase_cost
        gross_margin_rate = (gross_margin / revenue * 100) if revenue > 0 else 0.0
        avg_per_order = (revenue / order_count) if order_count > 0 else 0.0
        total_guns = sum((s.gun_count or 0) for s in stations)
        utilization_rate = (
            duration / (total_guns * range_minutes) * 100
            if total_guns > 0 and range_minutes > 0 else 0.0
        )

        # ── 4. investment / ROI / 回本 ──
        cum_revenue = sum(float(r.revenue or 0) for r in cum_map.values())
        cum_energy = sum(float(r.energy or 0) for r in cum_map.values())
        cumulative_gross_margin = cum_revenue - cum_energy * purchase_price
        cost_values = [float(s.total_cost) for s in stations if s.total_cost is not None]
        has_cost = len(cost_values) > 0
        total_cost = sum(cost_values) if has_cost else 0.0
        roi_rate = (cumulative_gross_margin / total_cost * 100) if (has_cost and total_cost > 0) else None
        payback_months = None
        if has_cost and stations:
            createds = [s.created_at for s in stations if s.created_at]
            if createds:
                earliest = min(createds)
                if earliest.tzinfo is None:
                    earliest = earliest.replace(tzinfo=timezone.utc)
                months = max(1.0, (now - earliest).days / 30.0)
                monthly_avg = cumulative_gross_margin / months
                payback_months = (total_cost / monthly_avg) if monthly_avg > 0 else None

        # ── 5. stations 明细 ──
        station_items = []
        for s in stations:
            r = range_map.get(s.id)
            c = cum_map.get(s.id)
            s_rev = float(r.revenue or 0) if r else 0.0
            s_en = float(r.energy or 0) if r else 0.0
            s_dur = float(r.duration or 0) if r else 0.0
            s_ord = int(r.orders or 0) if r else 0
            s_gm = s_rev - s_en * purchase_price
            c_rev = float(c.revenue or 0) if c else 0.0
            c_en = float(c.energy or 0) if c else 0.0
            s_cum_gm = c_rev - c_en * purchase_price
            cost = float(s.total_cost) if s.total_cost is not None else None
            s_roi = (s_cum_gm / cost * 100) if (cost and cost > 0) else None
            guns = s.gun_count or 0
            s_util = (s_dur / (guns * range_minutes) * 100) if (guns > 0 and range_minutes > 0) else 0.0
            station_items.append({
                "station_id": s.id,
                "station_name": s.name,
                "revenue": round(s_rev, 2),
                "energy_kwh": round(s_en, 2),
                "order_count": s_ord,
                "duration_minutes": round(s_dur, 2),
                "gross_margin": round(s_gm, 2),
                "gross_margin_rate": round((s_gm / s_rev * 100) if s_rev > 0 else 0.0, 2),
                "utilization_rate": round(s_util, 2),
                "gun_count": guns,
                "total_cost": round(cost, 2) if cost is not None else None,
                "cumulative_gross_margin": round(s_cum_gm, 2),
                "roi_rate": round(s_roi, 2) if s_roi is not None else None,
            })

        # ── 6. trend 按日序列 ──
        trend = []
        if station_ids:
            trend_rows = (
                db.query(
                    func.date(ChargingOrder.created_at).label("d"),
                    func.sum(ChargingOrder.paid_amount).label("revenue"),
                    func.sum(ChargingOrder.charged_kwh).label("energy"),
                )
                .filter(
                    ChargingOrder.order_status == OrderStatus.COMPLETED,
                    ChargingOrder.payment_status == OrderPaymentStatus.PAID,
                    ChargingOrder.station_id.in_(station_ids),
                    ChargingOrder.created_at >= start_dt,
                    ChargingOrder.created_at < next_day,
                )
                .group_by("d")
                .order_by("d")
                .all()
            )
            for tr in trend_rows:
                t_rev = float(tr.revenue or 0)
                t_en = float(tr.energy or 0)
                trend.append({
                    "date": tr.d,
                    "revenue": round(t_rev, 2),
                    "energy_kwh": round(t_en, 2),
                    "gross_margin": round(t_rev - t_en * purchase_price, 2),
                })

        return success_response({
            "period": {
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
            },
            "caliber": {
                "revenue": "Σ paid_amount (order_status=COMPLETED & payment_status=PAID)",
                "purchase_cost": f"Σ charged_kwh × purchase_price ({purchase_price} 元/kWh, 平台统一购电价; 未计 PV 自发自用抵扣)",
                "gross_margin": "revenue - purchase_cost (贡献毛利, 未扣折旧/人工/租金等固定成本)",
                "utilization_rate": "Σ duration_minutes / (Σ gun_count × num_days × 1440) × 100",
                "roi_rate": "累计毛利(全时段) / Σ station.total_cost × 100",
                "payback_months": "Σ total_cost / 月均毛利; 月均毛利<=0 → null",
                "investment_field": "station.total_cost (站点总成本/建站投资额)",
                "num_days": num_days,
            },
            "summary": {
                "revenue": round(revenue, 2),
                "energy_kwh": round(energy, 2),
                "order_count": order_count,
                "avg_per_order": round(avg_per_order, 2),
                "purchase_cost": round(purchase_cost, 2),
                "gross_margin": round(gross_margin, 2),
                "gross_margin_rate": round(gross_margin_rate, 2),
                "utilization_rate": round(utilization_rate, 4),
            },
            "investment": {
                "total_cost": round(total_cost, 2) if has_cost else None,
                "cumulative_gross_margin": round(cumulative_gross_margin, 2),
                "roi_rate": round(roi_rate, 4) if roi_rate is not None else None,
                "payback_months": round(payback_months, 1) if payback_months is not None else None,
            },
            "stations": station_items,
            "trend": trend,
        })
    except HTTPException:
        # 404 (跨团队/不存在站点) 等业务异常透传, 保持语义化状态码
        raise
    except Exception:
        # 聚合查询异常: 记录堆栈供排查, 对外返回通用消息 (不泄露内部路径/SQL)
        logger.exception("get_owner_cockpit_overview 聚合异常")
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请稍后重试"},
        )

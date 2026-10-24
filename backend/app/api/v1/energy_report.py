"""
能耗分析报表 API

功能:
- 发电量/充电量/放电量趋势
- 收益计算(售电收益/充电服务费/放电站收益)
- 按日/周/月/年维度统计
- 站点/设备维度对比

卡 6bc6f3f1: 废弃日期算术/random 假数据, 接真实 Telemetry 聚合。
- 充电量口径复用卡 36c6b919/e8e4331cb: charger_kwh 累计差值优先,
  无则 avg(grid_power_total)×时长回退。
- 发电量: pv_power_total (无则 pv1_power+pv2_power) 梯形积分。
- 放电量: total_discharge/daily_discharge 累计差值, 无则 0。
- 电价: 查 PricingRule (active) 均值, 无配置用系统默认并在 price_info 标注
  source="default"。
- 同比: 上一周期同窗真实聚合, 上期为 0 时 yoy=null (除零守卫)。
时间口径: 落库 naive-UTC (与 tz_utils 统一口径一致)。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, load_only

from app.core.database import get_db
from app.api.deps import assert_station_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.core.response import success_response, error_response
from app.models.device import Device
from app.models.pricing_rule import PricingRule
from app.models.station import Station
from app.models.telemetry import Telemetry
from app.models.user import User
from app.tasks.tz_utils import get_biz_tz, now_in_biz_tz

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# 系统默认电价(元/kWh), 无 PricingRule 配置时回退并在 price_info 标注 source="default"
DEFAULT_FEED_IN_TARIFF = 0.42
DEFAULT_CHARGING_PRICE = 0.85
DEFAULT_DISCHARGE_PRICE = 0.42


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(dt: datetime) -> datetime:
    """业务时区墙钟 datetime → UTC-naive (落库口径)。"""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _local_naive(ts: datetime) -> datetime:
    """UTC-naive 落库时间 → 业务时区墙钟 naive (供 .date()/分桶取标签)。"""
    return ts.replace(tzinfo=timezone.utc).astimezone(get_biz_tz()).replace(tzinfo=None)


def _utc_naive(dt: datetime) -> datetime:
    """任意 datetime 归一为 UTC-naive (落库口径)。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _device_ids(db: Session, station_id: Optional[int],
                team_id: Optional[int] = None) -> List[int]:
    """station_id 过滤下参与聚合的设备 id 列表 (无匹配返回空 → 聚合为 0)。

    卡 e61ac986: team_id 非 None 时 join Station 强制本 team 站点范围
    (团队级用户防水平越权; admin 传 None 保持全量)。
    """
    q = db.query(Device.id).join(Station, Device.station_id == Station.id)
    if station_id is not None:
        q = q.filter(Device.station_id == station_id)
    if team_id is not None:
        q = q.filter(Station.team_id == team_id)
    return [row[0] for row in q.all()]


def _resolve_scope(db: Session, station_id: Optional[int],
                   user: User) -> Tuple[Optional[int], List[int]]:
    """团队级用户聚合范围 (卡 e61ac986)。

    显式 station_id 先做站点归属校验 (跨团队→404 由 assert 抛出);
    返回 (team_id, device_ids): admin → (None, 全量设备), 团队级 →
    (tid, 本 team 设备)。"""
    tid = team_scope(user)
    if station_id is not None:
        assert_station_team_access(db, station_id, user)
    return tid, _device_ids(db, station_id, tid)


def _bucket_totals(rows: List[Telemetry]) -> Dict[str, float]:
    """单个时间桶内按设备聚合 → {pv, charge, discharge}。

    与卡 36c6b919/e8e4331cb 口径一致:
    - 充电量: charger_kwh 累计差值(末-首, clamp≥0); 无该列则
      avg(grid_power_total)×(末-首)时长 回退。
    - 发电量: pv_power_total(无则 pv1+pv2) 相邻采样梯形积分。
    - 放电量: total_discharge 累计差值, 无则 daily_discharge 差值, 均无则 0。
    """
    by_device: Dict[int, List[Telemetry]] = {}
    for t in rows:
        by_device.setdefault(t.device_id, []).append(t)

    pv = charge = discharge = 0.0
    for dev_rows in by_device.values():
        dev_rows.sort(key=lambda t: t.timestamp)

        # 充电量
        kwh_values = [t.charger_kwh for t in dev_rows if t.charger_kwh is not None]
        if kwh_values:
            charge += max(0.0, kwh_values[-1] - kwh_values[0])
        else:
            grid_values = [
                (t.timestamp, t.grid_power_total)
                for t in dev_rows if t.grid_power_total is not None
            ]
            if len(grid_values) >= 2:
                avg_power = sum(v for _, v in grid_values) / len(grid_values)
                hours = (
                    grid_values[-1][0] - grid_values[0][0]
                ).total_seconds() / 3600
                charge += avg_power * max(0.0, hours)

        # 发电量: 梯形积分
        pv_points = [
            (t.timestamp, t.pv_power_total if t.pv_power_total is not None
             else ((t.pv1_power or 0.0) + (t.pv2_power or 0.0)))
            for t in dev_rows
        ]
        pv_points = [(ts, p) for ts, p in pv_points if ts is not None]
        for (ts0, p0), (ts1, p1) in zip(pv_points, pv_points[1:]):
            hours = (ts1 - ts0).total_seconds() / 3600
            pv += (p0 + p1) / 2 * hours

        # 放电量: 累计计数器差值
        td_values = [t.total_discharge for t in dev_rows if t.total_discharge is not None]
        if td_values:
            discharge += max(0.0, td_values[-1] - td_values[0])
        else:
            dd_values = [t.daily_discharge for t in dev_rows if t.daily_discharge is not None]
            if dd_values:
                discharge += max(0.0, dd_values[-1] - dd_values[0])

    return {"pv": pv, "charge": charge, "discharge": discharge}


def _period_amounts(db: Session, device_ids: List[int],
                    start: datetime, end: datetime) -> Dict[str, float]:
    """[start, end) 窗口聚合 (summary/同比共用)。"""
    if not device_ids or end <= start:
        return {"pv": 0.0, "charge": 0.0, "discharge": 0.0}
    rows = (
        db.query(Telemetry)
        # 卡 45659336: load_only 列裁剪 (对齐卡 7c1c396d/27eb37e6), 仅加载
        # _bucket_totals 实读列 + id (缺主键会回退加载全部列, 裁剪失效)
        .options(
            load_only(
                Telemetry.id,
                Telemetry.device_id,
                Telemetry.timestamp,
                Telemetry.charger_kwh,
                Telemetry.grid_power_total,
                Telemetry.pv_power_total,
                Telemetry.pv1_power,
                Telemetry.pv2_power,
                Telemetry.total_discharge,
                Telemetry.daily_discharge,
            )
        )
        .filter(
            Telemetry.device_id.in_(device_ids),
            Telemetry.timestamp >= start,
            Telemetry.timestamp < end,
        )
        .all()
    )
    if not rows:
        return {"pv": 0.0, "charge": 0.0, "discharge": 0.0}
    return _bucket_totals(rows)


def _get_prices(db: Session) -> Dict[str, object]:
    """电价来源: active PricingRule 均值优先, 无则系统默认。

    口径假设: electricity_price 均值 → 上网/放电电价, service_fee_rate 均值
    → 充电服务费。PricingRule 是分时电价, 报表汇总取规则均值作代表价。
    """
    rules = db.query(PricingRule).filter(PricingRule.is_active == True).all()  # noqa: E712
    if rules:
        elec = sum(float(r.electricity_price or 0) for r in rules) / len(rules)
        svc = sum(float(r.service_fee_rate or 0) for r in rules) / len(rules)
        return {
            "feed_in_tariff": round(elec, 4),
            "charging_price": round(svc, 4),
            "discharge_price": round(elec, 4),
            "source": "pricing_rules",
        }
    return {
        "feed_in_tariff": DEFAULT_FEED_IN_TARIFF,
        "charging_price": DEFAULT_CHARGING_PRICE,
        "discharge_price": DEFAULT_DISCHARGE_PRICE,
        "source": "default",
    }


def _revenues(totals: Dict[str, float], prices: Dict[str, object]) -> Dict[str, float]:
    pv_rev = round(totals["pv"] * prices["feed_in_tariff"], 2)
    charge_rev = round(totals["charge"] * prices["charging_price"], 2)
    discharge_rev = round(totals["discharge"] * prices["discharge_price"], 2)
    return {
        "pv_revenue": pv_rev,
        "charging_revenue": charge_rev,
        "discharge_revenue": discharge_rev,
        "total_revenue": round(pv_rev + charge_rev + discharge_rev, 2),
    }


@router.get("/trend")
def get_energy_trend(
    station_id: Optional[int] = Query(None, description="按站点筛选"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取发电量/充电量/放电量趋势数据 (真实 Telemetry 聚合)

    按日/周/月桶聚合 charger_kwh/pv 功率积分; 无数据的桶不输出(空库返回空列表)。
    日期/桶界均按业务时区(上海)墙钟切 (卡20cb47ed)。
    """
    today_local = now_in_biz_tz().replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = today_local - timedelta(days=30)
    end_local = today_local

    if start_date:
        try:
            # 挂业务时区: 与 aware 的 today_local 可比 (卡 05ccb577: 修复单侧参数 naive/aware 500)
            start_local = datetime.strptime(
                start_date, "%Y-%m-%d").replace(tzinfo=get_biz_tz())
        except ValueError:
            return error_response(code=400, message="开始日期格式错误, 使用 YYYY-MM-DD")

    if end_date:
        try:
            end_local = datetime.strptime(
                end_date, "%Y-%m-%d").replace(tzinfo=get_biz_tz())
        except ValueError:
            return error_response(code=400, message="结束日期格式错误, 使用 YYYY-MM-DD")

    # 卡 05ccb577: 日期跨度上限, 防全量遥测拉取(读放大/内存风险)
    if start_date and end_date and (end_local - start_local).days > 366:
        return error_response(
            code=400, message="日期跨度不能超过 366 天")

    # 墙钟日界 → UTC-naive 查询窗 [start, end+1d)
    start = _as_utc_naive(start_local.replace(tzinfo=get_biz_tz()))
    window_end = _as_utc_naive(
        (end_local + timedelta(days=1)).replace(tzinfo=get_biz_tz()))

    if end_local < start_local:
        return success_response(data={
            "trend": [],
            "granularity": granularity,
            "period": {"start": start_local.strftime("%Y-%m-%d"),
                       "end": end_local.strftime("%Y-%m-%d")},
        })

    device_ids = _resolve_scope(db, station_id, user)[1]
    rows = []
    if device_ids:
        rows = (
            db.query(Telemetry)
            # 卡 45659336: load_only 列裁剪 (对齐卡 7c1c396d/27eb37e6), 仅加载
            # _bucket_totals 实读列 + id (缺主键会回退加载全部列, 裁剪失效)
            .options(
                load_only(
                    Telemetry.id,
                    Telemetry.device_id,
                    Telemetry.timestamp,
                    Telemetry.charger_kwh,
                    Telemetry.grid_power_total,
                    Telemetry.pv_power_total,
                    Telemetry.pv1_power,
                    Telemetry.pv2_power,
                    Telemetry.total_discharge,
                    Telemetry.daily_discharge,
                )
            )
            .filter(
                Telemetry.device_id.in_(device_ids),
                Telemetry.timestamp >= start,
                Telemetry.timestamp < window_end,
            )
            .all()
        )

    # 分桶: 按业务时区墙钟切桶界 (上海日界, 卡20cb47ed)
    # 卡 d386c813: 累计计数器 (charger_kwh/放电计数) 差值按相邻采样对计算并
    # 归属较晚样本所在桶 —— 先分桶再桶内取末-首差值会把跨桶边界区间的电量
    # 丢弃 (如 23:30→00:30 采样对分属两桶, 两桶各自差值均归零, 周期总和
    # 不守恒)。瞬时功率积分 (pv) 维持桶内口径, 稀疏采样下跨桶外推会捏造能量。
    def _bucket_key(ts_naive: datetime) -> Tuple:
        local = _local_naive(ts_naive)
        if granularity == "month":
            return (local.year, local.month)
        if granularity == "week":
            monday = local.date() - timedelta(days=local.weekday())
            return (monday.isocalendar()[0], monday.isocalendar()[1])
        return (local.year, local.month, local.day)

    def _pv_power(t: Telemetry) -> Optional[float]:
        if t.pv_power_total is not None:
            return t.pv_power_total
        if t.pv1_power is not None or t.pv2_power is not None:
            return (t.pv1_power or 0.0) + (t.pv2_power or 0.0)
        return None

    buckets: Dict[Tuple, Dict[str, float]] = {}
    pv_points: Dict[Tuple[int, Tuple], List[Tuple[datetime, float]]] = {}
    grid_points: Dict[Tuple[int, Tuple], List[Tuple[datetime, float]]] = {}
    bucket_has_kwh: Dict[Tuple[int, Tuple], bool] = {}

    by_device: Dict[int, List[Telemetry]] = {}
    for t in rows:
        if t.timestamp is None:
            continue
        by_device.setdefault(t.device_id, []).append(t)

    for dev_id, dev_rows in by_device.items():
        dev_rows.sort(key=lambda t: t.timestamp)
        # 每指标流式 last-value: 同设备指标列可能分属不同行 (如 charger_kwh 与
        # total_discharge 各自单独上报), 各指标独立记上一非空值再对当前样本
        # 取差值, 归属当前样本所在桶。
        prev_charge: Optional[float] = None
        prev_discharge: Optional[Tuple[str, float]] = None
        for t in dev_rows:
            key = _bucket_key(_utc_naive(t.timestamp))
            totals = buckets.setdefault(
                key, {"pv": 0.0, "charge": 0.0, "discharge": 0.0})
            pv = _pv_power(t)
            if pv is not None:
                pv_points.setdefault((dev_id, key), []).append(
                    (t.timestamp, pv))
            if t.grid_power_total is not None:
                grid_points.setdefault((dev_id, key), []).append(
                    (t.timestamp, t.grid_power_total))

            # 充电量: charger_kwh 差值
            if t.charger_kwh is not None:
                if prev_charge is not None:
                    totals["charge"] += max(
                        0.0, t.charger_kwh - prev_charge)
                prev_charge = t.charger_kwh
                bucket_has_kwh[(dev_id, key)] = True

            # 放电量: total_discharge 优先, 其次 daily_discharge 差值
            if t.total_discharge is not None:
                if prev_discharge is not None and prev_discharge[0] == "total":
                    totals["discharge"] += max(
                        0.0, t.total_discharge - prev_discharge[1])
                prev_discharge = ("total", t.total_discharge)
            elif t.daily_discharge is not None:
                if prev_discharge is not None and prev_discharge[0] == "daily":
                    totals["discharge"] += max(
                        0.0, t.daily_discharge - prev_discharge[1])
                prev_discharge = ("daily", t.daily_discharge)

    # 发电量: 桶内相邻采样梯形积分 (口径不变)
    for (dev_id, key), points in pv_points.items():
        points.sort(key=lambda p: p[0])
        for (ts0, p0), (ts1, p1) in zip(points, points[1:]):
            hours = (ts1 - ts0).total_seconds() / 3600
            buckets[key]["pv"] += (p0 + p1) / 2 * hours

    # 充电量回退: 桶内全程无 charger_kwh 的设备用 grid_power 梯形积分 (口径不变)
    for (dev_id, key), points in grid_points.items():
        if bucket_has_kwh.get((dev_id, key)):
            continue
        points.sort(key=lambda p: p[0])
        for (ts0, p0), (ts1, p1) in zip(points, points[1:]):
            hours = (ts1 - ts0).total_seconds() / 3600
            buckets[key]["charge"] += max(0.0, (p0 + p1) / 2 * hours)

    def _label(key: Tuple) -> str:
        if granularity == "month":
            return f"{key[0]:04d}-{key[1]:02d}"
        if granularity == "week":
            return f"{key[0]}-W{key[1]:02d}"
        return f"{key[0]:04d}-{key[1]:02d}-{key[2]:02d}"

    prices = _get_prices(db)
    trend_data = []
    for key in sorted(buckets):
        totals = buckets[key]
        revs = _revenues(totals, prices)
        trend_data.append({
            "date": _label(key),
            "pv_generation": round(totals["pv"], 1),
            "charging_amount": round(totals["charge"], 1),
            "discharge_amount": round(totals["discharge"], 1),
            "pv_revenue": revs["pv_revenue"],
            "charging_revenue": revs["charging_revenue"],
            "discharge_revenue": revs["discharge_revenue"],
            "total_revenue": revs["total_revenue"],
        })

    return success_response(data={
        "trend": trend_data,
        "granularity": granularity,
        "period": {"start": start_local.strftime("%Y-%m-%d"),
                   "end": end_local.strftime("%Y-%m-%d")},
    })


@router.get("/summary")
def get_energy_summary(
    station_id: Optional[int] = Query(None, description="按站点筛选"),
    period: str = Query("month", pattern="^(day|week|month|year)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    能耗汇总统计 + 收益计算 (真实聚合)

    周期边界按业务时区(上海)墙钟切; 当前周期 [start, now) 真实聚合;
    同比取上一等长周期, 上期为 0 时 yoy=null (卡20cb47ed)。
    """
    now_local = now_in_biz_tz()

    if period == "day":
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_local = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # year
        start_local = now_local.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    tz = get_biz_tz()
    start = _as_utc_naive(start_local.replace(tzinfo=tz))
    now = _as_utc_naive(now_local)
    days = (now_local.date() - start_local.date()).days + 1
    prev_end = start
    prev_start = _as_utc_naive(
        (start_local - (now_local - start_local)).replace(tzinfo=tz))

    device_ids = _resolve_scope(db, station_id, user)[1]
    totals = _period_amounts(db, device_ids, start, now)
    prev_totals = _period_amounts(db, device_ids, prev_start, prev_end)

    prices = _get_prices(db)
    revs = _revenues(totals, prices)
    prev_revs = _revenues(prev_totals, prices)

    def _yoy(cur: float, prev: float) -> Optional[float]:
        if prev == 0:
            return None
        return round((cur - prev) / prev * 100, 1)

    return success_response(data={
        "period": period,
        "days": days,
        "pv_generation": round(totals["pv"], 1),
        "charging_amount": round(totals["charge"], 1),
        "discharge_amount": round(totals["discharge"], 1),
        "pv_revenue": revs["pv_revenue"],
        "charging_revenue": revs["charging_revenue"],
        "discharge_revenue": revs["discharge_revenue"],
        "total_revenue": revs["total_revenue"],
        "yoy": {
            "pv_generation_yoy": _yoy(totals["pv"], prev_totals["pv"]),
            "charging_amount_yoy": _yoy(totals["charge"], prev_totals["charge"]),
            "discharge_amount_yoy": _yoy(totals["discharge"], prev_totals["discharge"]),
            "total_revenue_yoy": _yoy(revs["total_revenue"], prev_revs["total_revenue"]),
        },
        "price_info": prices,
    })


@router.get("/station-compare")
def get_station_energy_compare(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    站点能耗对比排行 (近 30 天真实聚合, 按总收益降序; 无数据站点不输出)
    """
    end = _now_naive()
    start = end - timedelta(days=30)
    prices = _get_prices(db)

    stations_q = db.query(Station)
    tid = team_scope(user)
    if tid is not None:  # 卡 e61ac986: 团队级仅本 team 站点
        stations_q = stations_q.filter(Station.team_id == tid)
    stations_list = stations_q.all()
    result = []
    for st in stations_list:
        ids = _device_ids(db, st.id)
        if not ids:
            continue
        rows = (
            db.query(Telemetry)
            # 卡 45659336: load_only 列裁剪 (对齐卡 7c1c396d/27eb37e6), 仅加载
            # _bucket_totals 实读列 + id (缺主键会回退加载全部列, 裁剪失效)
            .options(
                load_only(
                    Telemetry.id,
                    Telemetry.device_id,
                    Telemetry.timestamp,
                    Telemetry.charger_kwh,
                    Telemetry.grid_power_total,
                    Telemetry.pv_power_total,
                    Telemetry.pv1_power,
                    Telemetry.pv2_power,
                    Telemetry.total_discharge,
                    Telemetry.daily_discharge,
                )
            )
            .filter(
                Telemetry.device_id.in_(ids),
                Telemetry.timestamp >= start,
                Telemetry.timestamp < end,
            )
            .all()
        )
        if not rows:
            continue
        totals = _bucket_totals(rows)
        revs = _revenues(totals, prices)
        result.append({
            "station_id": st.id,
            "name": st.name,
            "pv_gen": round(totals["pv"], 1),
            "charge": round(totals["charge"], 1),
            "discharge": round(totals["discharge"], 1),
            "revenue": revs["total_revenue"],
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return success_response(data={
        "stations": result,
        "totals": {
            "pv_generation": round(sum(s["pv_gen"] for s in result), 1),
            "charging_amount": round(sum(s["charge"] for s in result), 1),
            "discharge_amount": round(sum(s["discharge"] for s in result), 1),
            "total_revenue": round(sum(s["revenue"] for s in result), 2),
        },
    })

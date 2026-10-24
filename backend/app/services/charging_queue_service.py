"""
充电队列排序服务 - priority_criteria 权重计算引擎

支持的字段:
  - priority:        手动优先级 (数字越小越优先)
  - arrival_time:    到达时间 (越早越优先 / FIFO)
  - required_energy: 需求能量 (越大越优先 / 越小越优先)
  - target_soc:      目标SOC (越低越优先 / 越高越优先)
  - current_soc:     当前SOC (越低越优先)

priority_criteria JSON 格式:
  [
    {"field": "priority", "weight": 100, "direction": "asc"},
    {"field": "arrival_time", "weight": 50, "direction": "asc"},
    {"field": "required_energy", "weight": 30, "direction": "desc"}
  ]
"""
import math
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.charging_queue import ChargingQueue, ChargingQueueRule, ChargingQueueStatus
from app.models.device import Device, DeviceStatus, DeviceType


# ─── 默认排序规则 ───
# priority 权重须保证: 同集合内 priority 归一化差 ≥ (w_arrival/w_priority) 时
# 优先级主导而非被到达时间罚分盖过。取 w_arrival/w_priority = 0.25 →
# priority 只要拉开 25% 量程即主导, 覆盖常规分级 (如 10/50/100); 同优先级
# 时 arrival_time 仍作 FIFO tiebreak (语义由归一化保证)。
DEFAULT_PRIORITY_CRITERIA = [
    {"field": "priority", "weight": 100, "direction": "asc"},
    {"field": "arrival_time", "weight": 25, "direction": "asc"},
]


def _parse_criteria(criteria_raw: Any) -> List[Dict[str, Any]]:
    """解析并验证 priority_criteria JSON"""
    if not criteria_raw:
        return list(DEFAULT_PRIORITY_CRITERIA)

    if isinstance(criteria_raw, str):
        import json
        try:
            criteria_raw = json.loads(criteria_raw)
        except (json.JSONDecodeError, TypeError):
            return list(DEFAULT_PRIORITY_CRITERIA)

    if not isinstance(criteria_raw, list):
        return list(DEFAULT_PRIORITY_CRITERIA)

    validated = []
    for item in criteria_raw:
        if not isinstance(item, dict):
            continue
        field = item.get("field", "")
        direction = item.get("direction", "asc")
        # 安全解析 weight: 非数字('abc'/dict/list)抛 ValueError/TypeError,
        # NaN/inf 非有限数也按非法处理 → 该项跳过; 全非法时由末尾回退默认
        try:
            weight = float(item.get("weight", 1))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(weight):
            continue
        if field and weight > 0 and direction in ("asc", "desc"):
            validated.append({
                "field": field,
                "weight": weight,
                "direction": direction,
            })

    return validated if validated else list(DEFAULT_PRIORITY_CRITERIA)


def _get_field_value(entry: ChargingQueue, field: str) -> float:
    """从队列条目中提取字段值用于排序"""
    if field == "priority":
        # 0 是合法显式值(最高优先级), 仅 None 视为未设置回退 100
        return float(entry.priority if entry.priority is not None else 100)
    if field == "arrival_time":
        dt = entry.arrival_time or datetime.now(timezone.utc)
        # 转为 epoch 分钟级别
        if isinstance(dt, datetime):
            return dt.timestamp() / 60.0
        return float(dt) / 60.0 if dt else 0.0
    if field in ("required_energy", "required_energy_kwh"):
        return float(entry.required_energy_kwh or 0)
    if field == "target_soc":
        return float(entry.target_soc or 0.8)
    if field == "current_soc":
        return float(entry.current_soc or 0.0)
    return 0.0


def _normalize(raw: float, rng: Optional[tuple]) -> float:
    """min-max 归一化到 [0,1]; rng 为 None 时返回原值 (直调无集合上下文, 保持旧语义)。
    hi==lo (单值/常量字段) 时返回 0.5 常数映射, 避免除零且对所有条目贡献一致。"""
    if rng is None:
        return raw
    lo, hi = rng
    if hi <= lo:
        return 0.5
    return (raw - lo) / (hi - lo)


def compute_sort_score(
    entry: ChargingQueue,
    criteria: List[Dict[str, Any]],
    field_ranges: Optional[Dict[str, tuple]] = None,
) -> float:
    """
    计算综合排序分数。分数越低 → 越优先。

    对每个标准项:
      - asc:  值越小 → 贡献越低 (越优先)
      - desc: 值越大 → 贡献越低 (越优先)

    field_ranges: {field: (min, max)} 集合级归一化范围 (由 sort_queue 对全量
    entries 统计后传入)。跨量纲字段 (如 arrival_time 的 epoch 绝对分钟 ~2.97e7
    vs priority 的 1~100) 不归一化会互相碾压, 使 weight 配置失效。
    缺省时退化为原值加权 (兼容直调, 单字段或同量纲场景语义不变)。

    返回加权综合分数。
    """
    # 权重非负化: 负权重 clip 为 0, 防止 sum<0 使 total_weight 为负反转排序语义
    # (负数 truthy, `or 1.0` 兜不住; compute_sort_score 是公开函数, 直接调用
    # 绕过 _parse_criteria 的 weight>0 过滤, 须在此自保)
    weights = [max(0.0, float(c["weight"])) for c in criteria]
    total_weight = sum(weights) or 1.0
    score = 0.0

    for c, weight in zip(criteria, weights):
        raw = _normalize(
            _get_field_value(entry, c["field"]),
            field_ranges.get(c["field"]) if field_ranges else None,
        )
        direction = c["direction"]

        if direction == "asc":
            # 值越小越好 → 直接用值 (小值→低分→优先)
            score += (raw * weight) / total_weight
        else:
            # desc: 值越大越好 → 取反 (大值→低分→优先)
            score += (-raw * weight) / total_weight

    return score


def sort_queue(entries: List[ChargingQueue], criteria: List[Dict[str, Any]]) -> List[ChargingQueue]:
    """按优先级规则排序队列条目 (稳定排序)"""
    if not entries:
        return []
    parsed = _parse_criteria(criteria)
    # 集合级 min-max 归一化: 消除跨量纲权重发散 (arrival_time epoch 分钟 ~2.97e7
    # 会碾压 priority 1~100 约 15 万倍, 使排序退化为纯 FIFO)
    fields = list({c["field"] for c in parsed})
    field_ranges: Dict[str, tuple] = {}
    for f in fields:
        vals = [_get_field_value(e, f) for e in entries]
        field_ranges[f] = (min(vals), max(vals))
    # stable sort by computed score
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda pair: (compute_sort_score(pair[1], parsed, field_ranges), pair[0]))
    return [e for _, e in indexed]


def get_active_rule(db: Session, enterprise_id: int = 0, station_id: Optional[int] = None) -> ChargingQueueRule:
    """获取生效中的排序规则"""
    # 优先匹配 station 级别
    if station_id:
        rule = db.query(ChargingQueueRule).filter(
            ChargingQueueRule.enable == True,
            ChargingQueueRule.enterprise_id == enterprise_id,
            ChargingQueueRule.station_id == station_id,
        ).first()
        if rule:
            return rule

    # 再匹配企业级别 (station_id is None)
    rule = db.query(ChargingQueueRule).filter(
        ChargingQueueRule.enable == True,
        ChargingQueueRule.enterprise_id == enterprise_id,
        ChargingQueueRule.station_id.is_(None),
    ).first()
    if rule:
        return rule

    # fallback: 全局规则 (enterprise_id=0)
    rule = db.query(ChargingQueueRule).filter(
        ChargingQueueRule.enable == True,
        ChargingQueueRule.enterprise_id == 0,
        ChargingQueueRule.station_id.is_(None),
    ).first()

    return rule


def recalculate_priorities(db: Session, station_id: int, criteria: List[Dict[str, Any]]) -> List[ChargingQueue]:
    """
    重新计算并更新指定电站的等待队列优先级。
    不修改 priority 字段，而是按 score 排序返回有序列表。
    同时更新 estimated_wait_minutes。
    """
    waiting = db.query(ChargingQueue).filter(
        ChargingQueue.station_id == station_id,
        ChargingQueue.status == ChargingQueueStatus.WAITING.value,
    ).all()

    sorted_entries = sort_queue(waiting, criteria)

    # 统计该站可用充电桩数 (在线的 DC/AC/V2G 桩), 多桩场站等待时间按桩数分摊;
    # pile_count<=0 或查询异常时退化为单桩串行估算
    try:
        pile_count = db.query(Device).filter(
            Device.station_id == station_id,
            Device.status == DeviceStatus.ONLINE,
            Device.type.in_((DeviceType.CHARGER_DC, DeviceType.CHARGER_AC, DeviceType.V2G_CHARGER)),
        ).count()
    except Exception:
        pile_count = 0
    if pile_count <= 0:
        pile_count = 1

    # 更新预计等待时间 (每个充电桩平均 30 分钟, 排在 piles 个并行车位后)
    avg_charge_min = 30
    for i, entry in enumerate(sorted_entries):
        entry.estimated_wait_minutes = (i // pile_count) * avg_charge_min

    db.flush()
    return sorted_entries

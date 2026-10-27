"""通知事件作用域矩阵 (卡 8d98ebe3)

account_type × event_domain 过滤: 不同账户类型只接收其职责域内的事件通知, 杜绝错配
(如司机收设备故障告警、平台管理员收充电计费事件)。与 app/core/scope_matrix.py 的
team_type 矩阵正交 —— 那里按 Team.type 治理「配置域访问权限」, 这里按账户类型治理
「通知事件可见域」。

⚠ 接入状态 (卡 acdfef44 排查结论): 本矩阵在派发/站内收件箱链路尚未接入 ——
event_domain 与 account_type 两维在生产代码中均无取值源 (Notification 只有
type: alarm/order/work_order/system; User 只有 role, 无 account_type 字段)。
接入前置决策与映射方案见
docs/plans/notification-scope-deadcode-investigation-acdfef44.md。在取值源
落地前, 本模块仅作为矩阵规范与单测对象, 不产生运行时过滤效果。

account_type 维度:
  - platform_admin:    平台管理员 (安全/认证/权限)
  - platform_operator: 运营方 (全域运营)
  - fleet_operator:    车队运营方 (计费 + 站点运营)
  - engineer:          运维工程师 (设备故障 + 站点运维)
  - driver:            司机 (本人充电计费)

event_domain 维度:
  - system_security:   安全/认证/权限事件
  - site_operation:    站点运营事件
  - equipment_fault:   设备故障告警
  - charging_billing:  充电/计费事件
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

# 允许的账户类型 (未登记 → 空白名单, 最小权限)
ALLOWED_ACCOUNT_TYPES = (
    "platform_admin",
    "platform_operator",
    "fleet_operator",
    "engineer",
    "driver",
)

# 允许的事件域
ALLOWED_EVENT_DOMAINS = (
    "system_security",
    "site_operation",
    "equipment_fault",
    "charging_billing",
)

# account_type → 可见 event_domain 白名单
# - platform_admin 只收 system_security (平台管理员职责聚焦安全)
# - platform_operator 全域运营 (覆盖四域)
# - fleet_operator 计费 + 站点运营
# - engineer 设备故障 + 站点运维
# - driver 仅本人充电计费
ACCOUNT_EVENT_SCOPE_MATRIX: Dict[str, List[str]] = {
    "platform_admin": ["system_security"],
    "platform_operator": [
        "system_security",
        "site_operation",
        "equipment_fault",
        "charging_billing",
    ],
    "fleet_operator": ["charging_billing", "site_operation"],
    "engineer": ["equipment_fault", "site_operation"],
    "driver": ["charging_billing"],
}


def _event_domain(event: Any) -> Optional[str]:
    """从事件提取 event_domain (兼容 dict 与对象)。"""
    if isinstance(event, dict):
        return event.get("event_domain")
    return getattr(event, "event_domain", None)


def filter_events_for_account(
    events: Union[List[Dict[str, Any]], List[Any]],
    account_type: Optional[str],
) -> List[Any]:
    """按账户类型过滤事件列表, 仅保留其可见 event_domain 内的事件。

    - account_type 未登记 / None → 返回空列表 (最小权限, 不泄露);
    - 事件的 event_domain 不在该账户白名单内 → 丢弃;
    - 事件无 event_domain 或域值非法 → 丢弃;
    - 保持原顺序。
    """
    if account_type is None:
        return []
    allowed = ACCOUNT_EVENT_SCOPE_MATRIX.get(account_type)
    if not allowed:
        return []
    allowed_set = set(allowed)
    return [ev for ev in events if _event_domain(ev) in allowed_set]

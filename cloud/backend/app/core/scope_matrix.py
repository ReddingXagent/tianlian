"""配置/日志/通知事件的三张作用域矩阵 — 工作卡 cf614348。

组织层级: 平台 → 运营公司(ops_company) → 运维团队(maintenance_team)/车队(fleet)。
不同 Team.type 可访问的「配置域 / 日志域 / 通知事件域」由这里的矩阵收口,
供请求处理层 (app/api/deps.assert_config_domain_access 等) 做按 type 的强制校验,
杜绝「车队账户改运营公司支付配置」「运维团队读平台发票通道」之类的越权。

约定:
- 平台管理员 (platform_admin) 取值 ``"*"`` → 全放行;
- 其余 key 为 TeamType 字面值 (ops_company / maintenance_team / fleet), 取值为该
  type 允许访问的域白名单 list[str];
- 未登记的 type → 空白名单 (最小权限, 显式拒绝)。
"""
from typing import Dict, List, Optional, Union

# TeamType 字面值常量 (避免与 enum 循环导入)
PLATFORM_ADMIN = "platform_admin"
OPS_COMPANY = "ops_company"
MAINTENANCE_TEAM = "maintenance_team"
FLEET = "fleet"

# 配置域: 发票/支付/通知/电价/能量/系统 等业务配置归属
CONFIG_SCOPE_MATRIX: Dict[str, Union[str, List[str]]] = {
    PLATFORM_ADMIN: "*",
    OPS_COMPANY: ["invoice", "payment", "notification", "tariff", "energy", "system"],
    MAINTENANCE_TEAM: ["notification", "alarm", "workorder"],
    FLEET: ["notification_basic"],
}

# 日志域: 各 type 可查看的日志/审计类别
LOG_SCOPE_MATRIX: Dict[str, Union[str, List[str]]] = {
    PLATFORM_ADMIN: "*",
    OPS_COMPANY: ["order", "config", "finance", "device", "operation"],
    MAINTENANCE_TEAM: ["device", "workorder", "inspection"],
    FLEET: ["charging", "billing", "wallet"],
}

# 通知事件域: 各 type 关心的告警/事件类型
NOTIFY_EVENT_SCOPE_MATRIX: Dict[str, Union[str, List[str]]] = {
    PLATFORM_ADMIN: "*",
    OPS_COMPANY: ["device_down", "order_anomaly", "revenue_anomaly"],
    MAINTENANCE_TEAM: ["fault", "offline", "maintenance_due"],
    FLEET: ["charging_complete", "balance_low", "bill_generated"],
}


def get_team_config_scope(team_type: Optional[str]) -> Union[str, List[str]]:
    """按 team_type 返回可访问的配置域白名单。

    - 平台管理员 / 已登记 type → 矩阵中的值 (``"*"`` 或 list);
    - 未知 / None → 空列表 (最小权限, 全拒绝)。

    返回 ``"*"`` 表示全放行, 调用方需显式判等。
    """
    if team_type is None:
        return []
    return CONFIG_SCOPE_MATRIX.get(team_type, [])

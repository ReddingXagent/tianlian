# 子卡：通知事件作用域矩阵接入前置决策（母卡 acdfef44）

> 石猴 2026-08-22 夜班。排查结论：**矩阵设计完整但两维取值源均不存在，接入需先拍板契约，本轮不臆造接入。**

## 排查证据（卡 acdfef44 第 1 项全部完成）

### 链路：产生 → 路由 → 用户可见

| 环节 | 文件 | 事实 |
|------|------|------|
| 事件产生 | `notification_dispatcher.py dispatch/dispatch_on_alarm` | 告警驱动，按 `NotificationRule`+级别选**渠道**（im/email/sms/im-b/logger），无接收人维度、无 event_domain |
| 站内落库 | `api/v1/notifications.py /send` | 仅 `type=system` 固定值；模型字段为 `type`（alarm/order/work_order/system） |
| 用户可见 | `api/v1/notifications.py _inbox_query` | 隔离键 = (recipient_type, recipient_id) + team_id，**无任何域过滤** |

### 两个无解维（卡第 4 条触发条件，逐条命中）

1. **event_domain 取值源根本未定义**
   - 全仓生产代码 `grep event_domain` 仅命中 `notification_scope.py` 自身
   - `Notification.type` 的 4 值（alarm/order/work_order/system）与矩阵 4 域（system_security/site_operation/equipment_fault/charging_billing）**两套不相交分类法**，任何 `type→event_domain` 映射都是新契约
2. **account_type 取值源未定义**
   - `User` 无 account_type 字段；有 `role`（super_admin/admin/dispatcher/station_master/engineer/operator/viewer/technician/auditor）+ `Team.type`（ops_company/maintenance_team/fleet）
   - 9 值 role → 5 类 account_type 映射同样无人拍板过

### 为什么不能"先接了再说"

若在收件箱读侧自行拍映射（如 `system→system_security`、engineer→engineer）：engineer 白名单 = [equipment_fault, site_operation]，现有站内信全部 `type=system` → **存量消息对 engineer 整体不可见**，`tests/test_notifications_inbox.py` 全线崩塌。这是可见性契约变更，不是代码补线。

## 待大圣拍板的三个决策（拍板后即可接入，工作量小）

1. **event_domain 挂在哪**：建议 `Notification` 加列（schema 变更，走 Alembic + 迁移回填），或读侧派生映射表（零 schema 但契约固化在代码）
2. **type→event_domain 映射**（若走派生）：建议 alarm→equipment_fault / order→charging_billing / work_order→site_operation / system→system_security
3. **role→account_type 映射**：建议 super_admin→platform_admin / admin→platform_operator / dispatcher+station_master+operator→fleet_operator 或 site_operation 类 / engineer+technician→engineer / viewer+auditor→待定 / driver——注意 **User.role 里根本没有 driver**，司机侧在 C 端（business user），矩阵的 driver 行需确认是否指 C 端用户体系

## 本轮落地

- `notification_scope.py` 模块头补"未接入"显式标注，防止后续误判已生效
- 新增本子卡文档
- 新鲜测试证据：`tests/services/test_notification_scope.py`（矩阵单测仍绿，等待接入）

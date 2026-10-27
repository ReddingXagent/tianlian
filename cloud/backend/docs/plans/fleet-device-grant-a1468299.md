# 车队三级授权（公司→场站→设备桩级白名单）— 卡 a1468299

## 目标
运营公司给其创建的车队（Enterprise）授权：① 一个/多个场站 ② 甚至特定场站的特定充电设备（桩）。
充电启动链路按授权范围校验，设备不在白名单 → 403。

## 现状
- `enterprise_stations` M2M + `FleetChargingPolicy.allowed_station_ids` 已有**场站级**。
- 缺**设备级**授权。
- `POST /charging-sessions`（OCPP ingestion，VIN→企业车）**完全没有 scope 校验**。

## 设计决策：Option A（独立授权表）✅
选 **A. 新建 `EnterpriseDeviceGrant` 表**，非 B（FleetChargingPolicy 加 JSON 字段）。

理由：
1. **语义清晰**：授权（grant，"能用什么"）与策略（policy，"限额/时段"）是两类关注点。
   `FleetChargingPolicy` 已承载日限额/时段/站点白名单，再塞 device_ids 会混淆并使
   `/check` 逻辑膨胀。
2. **device_id NULL/NOT NULL 天然表达两级**：NULL=整站授权（该站所有桩），非空=桩级白名单。
3. **可查询 + 外键约束**：`device_id → devices.id`、`station_id → stations.id` 强制引用完整性，
   且能校验"设备确实属于该站点"。JSON 数组做不到。
4. **与现有 `enterprise_stations` M2M 同构**：表式建模，团队已熟悉。
5. 新管理 API 命名为 `/operate/fleet-grants`（grants），与表名一致。

## 模型 `EnterpriseDeviceGrant`（`app/models/enterprise_device_grant.py`）
| 列 | 类型 | 说明 |
|----|------|------|
| id | PK | |
| enterprise_id | FK enterprises.id | 授权给哪个车队 |
| station_id | FK stations.id | 授权场站 |
| device_id | FK devices.id **nullable** | NULL=整站；非空=桩级 |
| note | String(200) nullable | 备注 |
| created_at | DateTime | |

- 唯一索引 `(enterprise_id, station_id, device_id)`。
- **坑**：SQL 唯一索引对 NULL 不去重（NULL≠NULL），故"整站授权"(device_id=NULL)
  重复需**应用层去重**（创建前查同 enterprise+station 的整站授权 → 409）。

## 授权语义（核心）— `fleet_grant_service.is_device_authorized`
```
企业无任何授权记录 → 放行（未配置=不限，向后兼容，保 baseline）
有授权记录 → 设备须被覆盖：
  · 整站授权(device_id IS NULL 且 station_id == device.station_id) → 该站所有桩放行
  · 桩级授权(device_id == device.id) → 仅该桩
  · 否则 → 拒绝
仅企业车(有 enterprise)受约束；个人/散客不受限。
```
"无授权=放行"由现有测试 `test_vin_match_enterprise_deduction`（无授权企业车充电期望 200）证实必需。

## 充电 scope 校验注入点
`app/api/v1/charging_sessions.py::report_charging_session`，在 `_resolve_user` 拿到 `enterprise` 后、
建单前插入守卫：`enterprise` 非 None → `is_device_authorized` → 拒绝则 403。
（`POST /charging-orders` 是运营手动建单，非车队 VIN 链路，不纳入。）

## 管理API（运营公司视角）— `app/api/v1/operate/fleet_grants.py`，挂载 prefix `/operate`
- `POST /operate/fleet-grants`：建授权。校验 `assert_enterprise_team_access`（当前用户 team=
  企业 owner_team）+ `assert_station_team_access`（站点属同 team）+ device.station_id 一致性。
- `GET /operate/fleet-grants?enterprise_id=`：列授权（按 enterprise 团队隔离）。
- `DELETE /operate/fleet-grants/{id}`：删授权（经 grant→enterprise 团队校验）。
- 路由依赖 `require_write_permission("fleet:manage")`，与 fleet_charging_policies 一致。

## 企业详情返回授权范围
`enterprises.py::get_enterprise` 详情响应附 `device_grants` 摘要（按站点分组）；
列表级授权视图由 `GET /operate/fleet-grants?enterprise_id=` 提供，避免列表 N+1。

## 测试 `tests/test_fleet_grants.py`
覆盖：场站级授权→充电允许 / 桩级白名单（授权桩允许+未授权桩拒绝）/ 越权公司授权拒绝 /
充电启动未授权→403 / 整站授权兼容 / grant CRUD + 404 + 重复整站→409。

## 验收
- `python3 -m pytest tests/ -x -q --timeout=30` 全 GREEN（baseline 8885）。
- 测试建表用 `Base.metadata.create_all`（conftest），新模型注册到 `app/models/__init__.py`
  即自动建表，**无需 Alembic migration**。

# 天链V3 移动端 API 地图（定稿）

> 卡片：`e853ddfd`（移动端联调-②）
> 维护：石猴（后端） / 猴王（移动端联调）
> 前缀基准：所有端点统一挂载在 **`/api/v1`** 下（全文路径均已含此前缀，可直接拷贝）

## 0. 为什么有这份文档

移动端实测出现大量 404，经逐文件核实路由，**绝大多数是路径写错，不是缺端点**。本文是大圣定稿的「路径校正地图」落地，给移动端一份可直接联调的权威清单。

核心纠偏一句话：站点不叫 sites、遥测没有裸根、孪生用中划线、运维看板叫 ops-dashboard。

---

## 1. 全局约定

| 项 | 值 |
|---|---|
| Base URL | `https://<host>/api/v1` |
| 协议 | HTTP / HTTPS |
| 数据格式 | `application/json`（登录接口除外，见 §3.1） |
| 字符编码 | UTF-8 |
| 时间戳 | Unix 秒（UTC），响应信封里的 `timestamp` |

### 1.1 统一响应信封（`app/core/response.py`）

**所有**成功响应都是这个结构，前端只取 `.data` 一层：

```json
{
  "code": 200,
  "message": "success",
  "data": { "": "" },
  "timestamp": 1750000000
}
```

分页响应的 `data` 固定为：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  },
  "timestamp": 1750000000
}
```

> ⚠️ 前端适配铁律：永远解一层 `.data`。列表数据在 `data.items`，不要直接遍历顶层。

错误响应同样走信封，`code` 为 4xx/5xx，错误信息在 `message`。

---

## 2. 鉴权机制（重要）

系统有 **三层**鉴权，按端点不同：

| 鉴权方式 | 怎么传 | 适用端点 | 说明 |
|---|---|---|---|
| **公开** | 无需 token | `/auth/register`、`/auth/login`、SMS、密码重置等 | 在 `is_public_path` 白名单内豁免 |
| **用户 Bearer** | `Authorization: Bearer <token>` | 站点、设备、告警、运维看板等绝大多数读/写接口 | 走 `get_current_user`，校验 JWT |
| **网关或用户** | `X-API-Key: <key>` **或** `Authorization: Bearer <token>` | **telemetry 全系** | 走 `get_current_gateway_or_user`，两种凭证任一即可 |
| **全局兜底** | `Authorization: Bearer <token>` | digital-twin 全系等无显式依赖的端点 | 走 `enforce_auth`，有合法 Bearer 即放行 |

### 2.1 全局强制认证

`app/api/v1/__init__.py:90`：

```python
api_router = APIRouter(dependencies=[Depends(enforce_auth)])
```

**所有** `/api/v1/*` 端点默认要求 Bearer token，白名单（`app/api/v1/auth.py` 的 `is_public_path`）内部豁免。白名单包含：健康检查、扫码报修、遥测上报、Pod 矩阵、Alertmanager 回调、认证公开端点。

### 2.2 移动端怎么拿 token

移动端用户登录后，拿 **用户 Bearer token** 即可访问**全部**业务端点（包括 telemetry —— 用户 Bearer 同样放行）。只有「真实网关设备上报」才需要 `X-API-Key`。

> 结论：移动端联调只需一个用户 Bearer token，无需申请 API Key。

---

## 3. 认证模块（`/auth`）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/auth/register` | 公开 | 注册，body 见 §3.2 |
| POST | `/api/v1/auth/login` | 公开 | 用户名密码登录，**OAuth2 表单**，返回 `data.token` |
| POST | `/api/v1/auth/sms/send` | 公开 | 发送短信验证码 |
| POST | `/api/v1/auth/sms/verify` | 公开 | 校验短信验证码 |
| POST | `/api/v1/auth/sms/login` | 公开 | 短信验证码登录 |
| POST | `/api/v1/auth/password-reset` | 公开 | 密码重置 |
| POST | `/api/v1/auth/refresh` | 公开 | 刷新 token |
| POST | `/api/v1/auth/logout` | 公开 | 登出 |

### 3.1 登录请求格式（关键坑）

登录走 **OAuth2PasswordRequestForm**，**不是 JSON**，要用 `application/x-www-form-urlencoded`：

```
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=mobile_test&password=Tianlian2026!
```

登录成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": "12",
      "username": "mobile_test",
      "real_name": "移动端测试管理员",
      "role": "admin"
    }
  },
  "timestamp": 1750000000
}
```

> ⚠️ **token 在 `data.token`，不是顶层 `access_token`**。前端取 `response.data.token` 后塞进 `Authorization: Bearer <token>`。

### 3.2 注册请求字段（`UserCreate`，`auth.py:55`）

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `username` | string | ✅ | — | 登录用户名 |
| `password` | string | ✅ | — | 明文密码（后端 bcrypt 存储） |
| `real_name` | string | ✅ | — | **真实姓名，必填** |
| `phone` | string | ❌ | null | 手机号 |
| `email` | email | ❌ | null | 邮箱（需合法 email 格式） |
| `role` | string | ❌ | **`technician`** | 角色，默认技术员 |

> ⚠️ `real_name` 必填、`role` 默认 `technician`。移动端注册不带 `real_name` 会被 Pydantic 拒绝（422）。

---

## 4. 站点模块（`/stations`）

> 路由前缀 `/stations`，**router 级** `get_current_user`（用户 Bearer）。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/stations` | 用户 Bearer | 站点列表 |
| GET | `/api/v1/stations/{station_id}` | 用户 Bearer | 站点详情 |
| POST | `/api/v1/stations` | 用户 Bearer | 创建站点 |
| PUT | `/api/v1/stations/{station_id}` | 用户 Bearer | 更新站点 |
| PUT | `/api/v1/stations/{station_id}/assign` | 用户 Bearer | 分配站点 |
| DELETE | `/api/v1/stations/{station_id}` | 用户 Bearer | 删除站点 |

> 🚫 **没有 `/sites`**。所有「站点」相关一律走 `/stations`。

---

## 5. 设备模块（`/devices`）

> 路由前缀 `/devices`，**router 级** `get_current_user`（用户 Bearer）。移动端常用端点：

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/devices` | 用户 Bearer | 设备列表 |
| GET | `/api/v1/devices/{device_id}` | 用户 Bearer | 设备详情 |
| POST | `/api/v1/devices` | 用户 Bearer | 创建设备 |
| PUT | `/api/v1/devices/{device_id}` | 用户 Bearer | 更新设备 |
| DELETE | `/api/v1/devices/{device_id}` | 用户 Bearer | 删除设备 |
| GET | `/api/v1/devices/{device_id}/health` | 用户 Bearer | 设备健康状态 |
| GET | `/api/v1/devices/{device_id}/health/history` | 用户 Bearer | 健康历史 |
| GET | `/api/v1/devices/{device_id}/efficiency` | 用户 Bearer | 设备效率 |
| GET | `/api/v1/devices/{device_id}/maintenance-plan` | 用户 Bearer | 维护计划 |
| GET | `/api/v1/devices/{device_id}/maintenance-records` | 用户 Bearer | 维护记录 |
| GET | `/api/v1/devices/{device_id}/config` | 用户 Bearer | 设备配置 |
| GET | `/api/v1/devices/maintenance-due` | 用户 Bearer | 待维护设备列表 |
| POST | `/api/v1/devices/{device_id}/control` | 用户 Bearer | 设备控制 |

---

## 6. 遥测模块（`/telemetry`） — 重点纠偏

> 路由前缀 `/telemetry`，**无裸根**。每个端点单独带 `get_current_gateway_or_user`（`X-API-Key` 或用户 Bearer 均可）。

### 6.1 查询端点（移动端常用）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/telemetry/device/{device_id}/latest` | 网关或用户 | **设备最新状态**（即「state/latest」，无独立 state 路由） |
| GET | `/api/v1/telemetry/device/{device_id}/history` | 网关或用户 | 设备遥测历史 |
| GET | `/api/v1/telemetry/device/{device_id}/stats` | 网关或用户 | 设备遥测统计 |
| GET | `/api/v1/telemetry/station/{station_id}/overview` | 网关或用户 | 站点遥测概览 |

### 6.2 上报端点（网关/设备用，移动端一般不调）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/telemetry/report` | 网关或用户 | 单条遥测上报 |
| POST | `/api/v1/telemetry/batch-report` | 网关或用户 | **离线批量回写**（设备缓存后补传） |
| POST | `/api/v1/telemetry/device/{device_id}/simulate` | 网关或用户 | 模拟数据（测试用） |

> 🚫 **`/telemetry` 没有裸根**：`GET /api/v1/telemetry`、`POST /api/v1/telemetry` 都是 404。
> 🚫 **没有 `/telemetry/state/latest`**。取最新状态用 `/telemetry/device/{device_id}/latest`。

---

## 7. 告警模块（`/alarms`）

> 路由前缀 `/alarms`，**router 级** `get_current_user`（用户 Bearer）。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/alarms` | 用户 Bearer | 告警列表 |
| GET | `/api/v1/alarms/{alarm_id}` | 用户 Bearer | 告警详情 |
| GET | `/api/v1/alarms/stats/summary` | 用户 Bearer | 告警统计摘要 |
| GET | `/api/v1/alarms/rule-logs` | 用户 Bearer | 规则命中日志 |
| GET | `/api/v1/alarms/{alarm_id}/notifications` | 用户 Bearer | 告警通知记录 |
| PUT | `/api/v1/alarms/{alarm_id}/ack` | 用户 Bearer | **确认**告警 |
| PUT | `/api/v1/alarms/{alarm_id}/resolve` | 用户 Bearer | **解决**告警 |
| PUT | `/api/v1/alarms/{alarm_id}/ignore` | 用户 Bearer | **忽略**告警 |
| POST | `/api/v1/alarms` | 用户 Bearer | 创建告警 |
| GET | `/api/v1/alarms/rules` | 用户 Bearer | 告警规则列表 |
| POST | `/api/v1/alarms/rules` | 用户 Bearer | 创建规则 |
| GET | `/api/v1/alarms/rules/{rule_id}` | 用户 Bearer | 规则详情 |
| PUT | `/api/v1/alarms/rules/{rule_id}` | 用户 Bearer | 更新规则 |
| DELETE | `/api/v1/alarms/rules/{rule_id}` | 用户 Bearer | 删除规则 |
| PUT | `/api/v1/alarms/rules/{rule_id}/toggle` | 用户 Bearer | 启停规则 |

> ✅ `/alarms` 路径正确，无需改动。

---

## 8. 数字孪生模块（`/digital-twin`） — 中划线

> 路由前缀 `/digital-twin`（**中划线，不是下划线**）。端点无显式 Depends，靠**全局 enforce_auth** 兜底（用户 Bearer 即可）。

### 8.1 场景（scenes）— 完整 CRUD

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/digital-twin/scenes` | 用户 Bearer | 场景列表 |
| POST | `/api/v1/digital-twin/scenes` | 用户 Bearer | 创建场景 |
| GET | `/api/v1/digital-twin/scenes/{scene_id}` | 用户 Bearer | 场景详情 |
| PUT | `/api/v1/digital-twin/scenes/{scene_id}` | 用户 Bearer | 更新场景 |
| DELETE | `/api/v1/digital-twin/scenes/{scene_id}` | 用户 Bearer | 删除场景 |
| GET | `/api/v1/digital-twin/scenes/{scene_id}/layout` | 用户 Bearer | 场景布局 |

### 8.2 模型（models）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/digital-twin/models` | 用户 Bearer | 模型列表 |
| POST | `/api/v1/digital-twin/models` | 用户 Bearer | 创建模型 |
| GET | `/api/v1/digital-twin/models/{model_id}` | 用户 Bearer | 模型详情 |
| PUT | `/api/v1/digital-twin/models/{model_id}` | 用户 Bearer | 更新模型 |
| DELETE | `/api/v1/digital-twin/models/{model_id}` | 用户 Bearer | 删除模型 |

### 8.3 数据点 / 实时 / 初始化

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/digital-twin/data-points` | 用户 Bearer | 数据点列表 |
| POST | `/api/v1/digital-twin/data-points` | 用户 Bearer | 创建数据点 |
| PUT | `/api/v1/digital-twin/data-points/{dp_id}` | 用户 Bearer | 更新数据点 |
| DELETE | `/api/v1/digital-twin/data-points/{dp_id}` | 用户 Bearer | 删除数据点 |
| GET | `/api/v1/digital-twin/realtime` | 用户 Bearer | 实时孪生数据 |
| POST | `/api/v1/digital-twin/init-default` | 用户 Bearer | 初始化默认场景/模型 |

> 🚫 `/digital_twin/models`（下划线）= 404。必须用中划线 `/digital-twin/models`。
> 🚫 `/scenes`（独立根）= 404。必须用 `/digital-twin/scenes`。

### 8.4 `/scenes` 是否需要独立端点 — 评估结论

**结论：不需要。** `/digital-twin/scenes` 已提供完整能力：

- 列表 / 详情 / 创建 / 更新 / 删除 五件套齐全
- 额外提供 `GET /scenes/{id}/layout`（布局读取）
- 与 models、data-points、realtime 同属 digital-twin 命名空间，语义内聚

移动端所有「场景」需求均可由 `/digital-twin/scenes*` 满足，**无需**也**不应**新增独立 `/scenes` 根路由（会破坏 digital-twin 命名空间一致性）。

---

## 9. 运维看板模块（`/ops-dashboard`）

> 路由前缀 `/ops-dashboard`，**router 级** `get_current_user`（用户 Bearer）。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/ops-dashboard/topology` | 用户 Bearer | 全网拓扑 |
| GET | `/api/v1/ops-dashboard/overview` | 用户 Bearer | 运维概览 |
| GET | `/api/v1/ops-dashboard/health-scores` | 用户 Bearer | 健康评分 |
| GET | `/api/v1/ops-dashboard/event-stream` | 用户 Bearer | 事件流 |

> 🚫 `/ops/topology` = 404。必须用 `/ops-dashboard/topology`。

---

## 10. 常见错误路径 → 正确路径对照表

> 联调 404 先查这张表。

| ❌ 错误路径（404） | ✅ 正确路径 | 模块 |
|---|---|---|
| `GET /api/v1/sites` | `GET /api/v1/stations` | 站点 |
| `GET /api/v1/sites/{id}` | `GET /api/v1/stations/{id}` | 站点 |
| `POST /api/v1/sites` | `POST /api/v1/stations` | 站点 |
| `GET /api/v1/telemetry`（裸根） | `GET /api/v1/telemetry/device/{id}/latest` | 遥测 |
| `GET /api/v1/telemetry/state/latest` | `GET /api/v1/telemetry/device/{id}/latest` | 遥测 |
| `POST /api/v1/telemetry`（裸根） | `POST /api/v1/telemetry/report` 或 `/batch-report` | 遥测 |
| `GET /api/v1/scenes` | `GET /api/v1/digital-twin/scenes` | 数字孪生 |
| `GET /api/v1/scenes/{id}/layout` | `GET /api/v1/digital-twin/scenes/{id}/layout` | 数字孪生 |
| `GET /api/v1/digital_twin/models`（下划线） | `GET /api/v1/digital-twin/models`（中划线） | 数字孪生 |
| `GET /api/v1/ops/topology` | `GET /api/v1/ops-dashboard/topology` | 运维看板 |
| `GET /api/v1/ops/overview` | `GET /api/v1/ops-dashboard/overview` | 运维看板 |
| `GET /api/v1/ops/health-scores` | `GET /api/v1/ops-dashboard/health-scores` | 运维看板 |

---

## 11. 联调账号（种子数据）

来源：`scripts/seed_mobile_test_user.py`（commit `32fdddd3a`）。两个账号状态均为 `active`，密码 bcrypt 存储。

| 用户名 | 密码 | 角色 | 用途 |
|---|---|---|---|
| `mobile_test` | `Tianlian2026!` | ADMIN | 管理员 / 监控 APP 联调 |
| `mobile_operator` | `Tianlian2026!` | OPERATOR | 工程师 APP 联调 |

### 11.1 一键获取 token（curl）

```bash
# 登录拿 token
curl -s -X POST https://<host>/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=mobile_test&password=Tianlian2026!"
# → response.data.token

# 带 token 调业务接口
curl -s https://<host>/api/v1/stations \
  -H "Authorization: Bearer <token>"
```

### 11.2 重新播种（如账号被清）

```bash
cd backend
python scripts/seed_mobile_test_user.py
```

---

## 12. 附：响应字段速查

| 接口 | 关键响应字段（均在 `.data` 下） |
|---|---|
| `/auth/login` | `token`, `user.{id,username,real_name,role}` |
| `/auth/register` | `id, username, real_name, phone, email, role` |
| `/stations` 列表 | 分页：`items[].{id,name,...}`, `total,page,page_size` |
| `/telemetry/device/{id}/latest` | 最新一条遥测状态对象 |
| `/telemetry/station/{id}/overview` | 站点级聚合概览 |
| `/ops-dashboard/topology` | 全网节点 + 连接关系 |
| `/digital-twin/scenes/{id}/layout` | 场景布局定义 |

---

## 13. 变更记录

| 日期 | 版本 | 作者 | 内容 |
|---|---|---|---|
| 2026-07-26 | v1.0 | 石猴 | 初版定稿，覆盖 7 大模块 + 路径校正对照表 + /scenes 评估 |

---

**核实依据**：本文所有路径、前缀、鉴权依赖均经源码逐文件核实（`app/api/v1/__init__.py` 挂载点 + 各路由文件 `APIRouter` 定义 + `@router.*` 装饰器 + `app/api/v1/auth.py` 鉴权函数 + `app/core/response.py` 信封）。

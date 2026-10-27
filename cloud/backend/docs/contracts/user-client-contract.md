# 用户端云端契约（user-mp / user-app ↔ tianlian-cloud）

**版本**: 2026-08-17-v1.4（§5.4 增补 void 红冲端点 + voided 标记字段——卡 f42bdf5a，R1 方案b：status 三态不变，只增不破；08-16-v1.3：§8 增补 P2 §8.6 车辆管理/§8.7 收藏场站卡 36396f29、A1/C1 修订 §5 status 统一小写 + invoice_id 定型 int——丁哥拍板；此前 08-15 新增§8 P1，v1.2 曾新增第7节充电生命周期）
**状态**: 大圣 ↔ 猴王 双方确认基线（丁哥 2026-08-07 定案：统一小程序/App + 多租户动态品牌 + IM-B服务商模式）
**Base URL**: `https://{tianlian-domain}/api/v1`（HTTPS 域名待备案接入，当前过渡期 http://demo.example.com）
**说明**: ① station 响应携带 branding；② pay 响应严格按 `wx.requestPayment` 规范；③ 进件端点 + 商户状态字段。进件模块 mock 先行，服务商资质到位后切真。

---

## 1. 场站响应 + branding（动态品牌）

### 1.1 GET /stations/{station_id}

响应在原场站对象上新增 `branding` 对象（列表接口 GET /stations 同样携带轻量版）：

```json
{
  "id": "st_0001",
  "name": "甘天地光储充示范站",
  "tenant_id": "t_001",
  "branding": {
    "operator_name": "某某新能源",
    "logo_url": "https://cdn.tianlian.example/brands/t_001/logo.png",
    "service_phone": "400-888-0001",
    "theme_color": "#00A86B",
    "source": "tenant"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| branding.operator_name | string | 运营商展示名称 |
| branding.logo_url | string | logo 绝对 URL（远程渲染，不打包进端侧代码） |
| branding.service_phone | string | 客服电话 |
| branding.theme_color | string | 主题色 hex，端侧注入 CSS 变量 |
| branding.source | enum | `tenant`=租户配置 / `default`=天链默认品牌（降级） |

**降级规则**: 租户未配置品牌时，云端返回天链默认品牌且 `source=default`，端侧无需判空。
**缓存**: `Cache-Control: public, max-age=300`；端侧本地缓存 + TTL，拉取失败继续用上次缓存或默认品牌。
**品牌录入**: ops 运营后台（团队级），非端侧职责。

---

## 2. 支付（wx.requestPayment 规范）

### 2.1 POST /business/payments/prepay

请求：

```json
{
  "order_id": "ord_20260807_0001",
  "openid": "oXXXXXXXXXXXXXXXX",
  "scene": "miniprogram"
}
```

| 字段 | 说明 |
|------|------|
| scene | `miniprogram`（小程序 appid）/ `app`（IM-B开放平台移动应用 appid），决定下单 appid |

响应 200（**端侧拿到 data 原样传入 `wx.requestPayment`，不做任何加工/签名**）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "timeStamp": "1786047000",
    "nonceStr": "5K8264ILTKCH16CQ2502SI8ZNMTM67VS",
    "package": "prepay_id=wx20260807abcdefg",
    "signType": "RSA",
    "paySign": "oR9d8PuhnIc+YZ8cBHFCwfgpaK9gd7vaRvkYD7rthRAZ1xNnN..."
  }
}
```

- 后端以**服务商身份**统一下单：`sp_mchid`（天链服务商号）+ `sub_mchid`（场站运营商特约商户号），`appid` 按 scene 选择。
- `paySign` = RSA(SHA256withRSA) 对 `appId\ntimeStamp\nnonceStr\npackage\n` 签名，仅云端持有商户 API 私钥。
- 错误响应：`code!=0` + `message`（如 `SUB_MCH_NOT_READY` 子商户未就绪、`ORDER_CLOSED`）。

### 2.2 支付回调（IM-B → 云端，非端侧接口）

`POST /business/payments/notify`：IM-B加密通知，云端验签解密后更新订单状态，并向 `sub_mchid` 结算（IM-B直清，平台不碰资金）。

### 2.3 订单/支付状态查询

`GET /business/orders/{order_id}` 响应包含：

```json
{
  "order_id": "ord_20260807_0001",
  "payment_status": "UNPAID|PAID|REFUNDING|REFUNDED|CLOSED",
  "transaction_id": "4200001234202608071234567890",
  "paid_at": "2026-08-07T04:20:00+08:00"
}
```

---

## 3. 特约商户进件 + 商户状态（ops 侧）

### 3.1 POST /ops/merchants/applyment

请求（按 merchant_type 裁剪材料）：

```json
{
  "merchant_type": "micro_merchant",
  "merchant_name": "张某某",
  "contact": { "name": "张某某", "phone": "138****0001" },
  "id_card": { "name": "张某某", "number": "***************001" },
  "settlement": {
    "account_type": "personal",
    "bank_name": "招商银行",
    "account_number": "************1234"
  },
  "station_ids": ["st_0001"]
}
```

| merchant_type | 说明 | 材料要求 |
|---------------|------|----------|
| micro_merchant | 小微商户 | 仅身份证 + 个人银行卡（无营业执照） |
| individual_business | 个体工商户 | 执照 + 法人身份证，可结算法人个人卡 |
| enterprise | 企业 | 执照 + 对公账户 |

响应 202：

```json
{ "code": 0, "data": { "business_code": "APL_20260807_0001", "applyment_state": "AUDITING" } }
```

### 3.2 GET /ops/merchants/applyment/{business_code}

```json
{
  "business_code": "APL_20260807_0001",
  "merchant_type": "micro_merchant",
  "merchant_name": "张某某",
  "applyment_state": "AUDITING",
  "sub_mchid": null,
  "reject_reason": null,
  "legal_validation_url": null,
  "updated_at": "2026-08-07T04:20:00+08:00"
}
```

**applyment_state 枚举**（对齐IM-B applyment4sub 状态）：

| 状态 | IM-B原值 | 含义 |
|------|----------|------|
| APPLYMENT_EDITING | APPLYMENT_EDITING | 资料编辑中（被驳回后可重新提交） |
| AUDITING | APPLYMENT_AUDITING | 审核中 |
| TO_BE_SIGNED | TO_BE_SIGNED | 待账户验证/法人验证 |
| SIGNING | SIGNING | 开通权限中 |
| FINISH | FINISH | 完成 → `sub_mchid` 生效，可收款 |
| REJECTED | REJECTED | 已驳回 → 见 `reject_reason` |
| FROZEN | FROZEN | 已冻结 |

### 3.3 GET /ops/merchants（商户列表，按团队隔离）

```json
{
  "items": [
    {
      "business_code": "APL_20260807_0001",
      "merchant_name": "张某某",
      "merchant_type": "micro_merchant",
      "applyment_state": "FINISH",
      "sub_mchid": "2490000001",
      "merchant_status": "ACTIVE",
      "settlement": { "account_type": "personal", "bank_name": "招商银行", "account_last4": "1234" },
      "profit_sharing_enabled": false,
      "station_ids": ["st_0001"]
    }
  ],
  "total": 1
}
```

**merchant_status（运行态，独立于进件状态）**: `ACTIVE`（可收款）/ `FROZEN`（禁收，prepay 返回 `SUB_MCH_FROZEN`）/ `PENDING`（进件未完成）。

---

## 4. 平台服务费预留（暂不启用）

- 数据模型：`platform_fee_config { tenant_id, enabled, rate_bp, scope: all|whitelist, user_ids[] }`，管理端预留 CRUD。
- 实现路线：IM-B官方**分账**（profitsharing），天链服务商号为分账接收方，在支付成功回调后发起；比例上限 30%，需特约商户签分账协议（进件流程附带）。
- 当前 `enabled=false`，端侧与支付流程**零感知**；prepay 响应不体现抽佣。

---

## 5. 开票（手动开票流程）

**流程**: 用户对已支付订单提交开票申请（端侧不感知手动/自动，只管提交与接收结果）→ 运营商若未开通发票代开通道，线下手动开票 → 在 Web 运营平台 /operate/invoices 把发票文件上传到该开票申请项 → 状态变 ISSUED，云端自动推送（订阅消息/App push/邮件）→ 用户端展示"已收到发票"，支持**保存/转发/发送到邮箱**。

**通道字段**: 商户/租户级 `invoice_mode: manual|auto`，当前全为 `manual`；将来接通发票代开（电子发票API）后切 `auto`，接口结构不变。

### 5.1 POST /business/invoices（用户提交开票申请）

```json
{
  "order_ids": ["ord_20260807_0001"],
  "title_type": "personal|company",
  "title_name": "个人 / 某某科技有限公司",
  "tax_number": "91110000XXXXXXXX",   // company 必填
  "receive_email": "user@example.com", // 选填，填了则开票后自动发邮件
  "remark": ""
}
```

校验：仅 `payment_status=PAID` 且未开过票的订单；金额自动汇总。响应 202：

```json
{ "code": 0, "data": { "invoice_id": 123, "status": "pending", "amount": 12800 } }
```

### 5.2 GET /business/invoices（用户申请列表）/ GET /business/invoices/{invoice_id}（详情）

```json
{
  "invoice_id": 123,
  "status": "pending|issued|rejected",
  "amount": 12800,
  "title_type": "company",
  "title_name": "某某科技有限公司",
  "tax_number": "91110000XXXXXXXX",
  "order_ids": ["ord_20260807_0001"],
  "created_at": "2026-08-07T04:30:00+08:00",
  "issued_at": null,
  "reject_reason": null,
  "invoice_file": {
    "file_url": "https://cdn.tianlian.example/invoices/inv_0001.pdf",
    "file_type": "pdf|ofd|image",
    "file_name": "电子发票（普通发票）_inv_0001.pdf"
  }
}
```

`invoice_file` 仅 `status=ISSUED` 时返回；列表接口为轻量版（无 invoice_file）。

### 5.3 POST /business/invoices/{invoice_id}/send-email（用户端补发/改发邮箱）

```json
{ "email": "user@example.com" }
```

响应 `{ code: 0, data: { sent: true } }`。云端以附件（≤10MB）或下载链接形式发送。

### 5.4 ops 侧（运营商手动开票）

**入口**：Web 运营管理平台 `/operate/invoices`（现有发票管理页：待审核/已开发票/抬头管理/开票平台设置），"待审核"项增加**手动开票**操作（上传发票文件），不在终端侧 App 实现。

- `GET /ops/invoice-requests?status=pending`：待开票列表（按团队/运营商隔离，含金额、抬头、税号、订单明细）
- `POST /ops/invoice-requests/{invoice_id}/upload`：multipart 上传发票文件（PDF/OFD/jpg/png，≤10MB）→ `status=ISSUED`，记录 `issuer`/`issued_at`，触发用户通知
- `POST /ops/invoice-requests/{invoice_id}/reject`：`{ "reject_reason": "..." }` → `REJECTED`，用户可对同一订单重新申请
- `POST /ops/invoice-requests/{invoice_id}/void`：`{ "reason": "..." }` → 红冲已开发票（卡 f42bdf5a，R1 方案b）。仅 `ISSUED` 可红冲；重复红冲 → 400。**status 三态不变**，红冲只在响应新增可选字段 `voided: true` + `void_reason`/`voided_by`/`voided_at`（契约只增不破；§5.2 列表/详情同样携带这组字段，未红冲恒 `voided: false`），端侧展示语义为「已开具（已红冲）」。红冲不动金额与发票文件（保留原票追溯）

### 5.5 通知与端侧交互

- 开票完成云端推送：小程序订阅消息 / App push；填了 receive_email 的自动发邮件
- 端侧"已收到发票"卡片操作：**保存**（下载 file_url 到本地）、**转发**（IM-B分享 file_url 或文件）、**发送到邮箱**（调 5.3）
- 文件 URL 带签名时效（建议 2h），过期端侧重新拉详情获取新 URL

---

## 6. 通用约定

- 认证：沿用现有 Bearer Token（用户端为 C 端用户 token，端点前缀 `/business/*`；运营端 `/ops/*` 走团队权限）。
- 响应包裹：`{ code, message, data }`，`code=0` 成功。
- 金额：分为单位整数。时间：ISO8601 带时区。
- mock 阶段：进件与支付端点返回 mock 数据（状态机模拟 AUDITING→FINISH），契约结构不变；服务商凭证到位后仅切后端实现。
- 变更管理：契约变更须双方（大圣/猴王）确认并升版本号。

---

## 7. 充电生命周期（C端核心业务）

**背景**: 用户扫码/选桩 → 云端创建订单 + 下发 OCPP RemoteStart → 充电中实时轮询 → 用户主动停/充满自停 → 计费结算 → 跳转支付（§2 prepay）。

**订单状态机** (`order_status` 字段):

```
PENDING → CHARGING → COMPLETED
   │         │
   └→ CANCELLED  └→ FAILED
```

| 状态 | 含义 | 触发 |
|------|------|------|
| pending | 订单已建，充电未开始 | POST /orders 创建成功 |
| charging | 充电进行中 | OCPP StartTransaction 确认 |
| completed | 充电结束，费用已算 | OCPP StopTransaction / 充满 / 用户停 |
| cancelled | 用户充电前取消 | 充电未开始时用户取消 |
| failed | 异常终止 | 设备故障 / 通信超时 |

### 7.1 POST /business/orders（创建充电订单）

用户扫码或选桩后调用，创建订单并下发充电指令。

请求：

```json
{
  "station_id": 1,
  "device_id": 10,
  "connector_id": 1,
  "vehicle_id": null,
  "plate_number": null,
  "user_type": "app",
  "remark": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| station_id | int | ✅ | 场站ID |
| device_id | int | ✅ | 充电设备ID |
| connector_id | int | ✅ | 枪号（OCPP connectorId） |
| vehicle_id | int | | 车辆ID（已绑定车辆时传） |
| plate_number | string | | 车牌号（未注册车辆填写） |
| user_type | string | | `app`=App用户 / `card`=刷卡用户，默认 app |
| remark | string | | 备注 |

响应 201：

```json
{
  "code": 0,
  "data": {
    "order_id": "TL20260808143000001",
    "order_status": "pending",
    "payment_status": "unpaid",
    "station_id": 1,
    "station_name": "甘天地光储充示范站",
    "device_id": 10,
    "connector_id": 1,
    "created_at": "2026-08-08T14:30:00+08:00"
  }
}
```

**业务校验**:
- connector 可用（设备在线、无占用）→ 否则 `code=1, message=CONNECTOR_BUSY / OFFLINE`
- 用户无未完成订单（`order_status in (pending, charging)`）→ 否则 `code=1, message=EXISTING_ORDER`
- 云端下发 OCPP RemoteStartTransaction；若 10s 内 charger 无 StartTransaction 确认，`order_status` 保持 pending，端侧轮询 7.3 获取最终状态

### 7.2 POST /business/orders/{order_id}/stop（停止充电）

用户主动停止充电。云端下发 OCPP StopTransaction，返回最终状态。

请求：无 body。

响应 200：

```json
{
  "code": 0,
  "data": {
    "order_id": "TL20260808143000001",
    "order_status": "completed",
    "charged_kwh": 23.50,
    "duration_minutes": 45,
    "total_amount": 3525,
    "stop_reason": "user_manual"
  }
}
```

| stop_reason | 说明 |
|-------------|------|
| user_manual | 用户主动停止 |
| full | 充满自停 |
| balance_low | 余额不足停止 |
| fault | 设备故障 |
| timeout | 超时自动停止 |

**幂等**: 同一 order_id 重复调用返回当前状态，不重复下发 StopTransaction。
**前置校验**: `order_status` 非 `charging` 时返回 `code=1, message=ORDER_NOT_CHARGING`。

### 7.3 GET /business/orders/{order_id}/status（充电实时状态）

充电中端侧高频轮询（建议 5-10s），获取实时电量、SOC、预估费用。

响应 200：

```json
{
  "code": 0,
  "data": {
    "order_id": "TL20260808143000001",
    "order_status": "charging",
    "charged_kwh": 12.30,
    "start_soc": 35.0,
    "current_soc": 58.0,
    "duration_minutes": 23,
    "power_kw": 60.5,
    "estimated_cost": 1845,
    "start_time": "2026-08-08T14:31:00+08:00",
    "updated_at": "2026-08-08T14:54:00+08:00"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| charged_kwh | number | 已充电量(kWh)，精度2位 |
| start_soc | number? | 起始SOC%，可能为空 |
| current_soc | number? | 当前SOC%，可能为空 |
| power_kw | number? | 当前功率(kW)，非充电中为 null |
| estimated_cost | int | 预估费用（分），基于已充电量 × 当前时段单价 |
| duration_minutes | int | 充电时长(分钟) |

### 7.4 GET /business/orders（用户订单列表）

分页查询当前用户的充电订单历史。

请求参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| status | string? | 过滤：pending/charging/completed/cancelled/failed，不传=全部 |
| station_id | int? | 过滤场站 |
| start_date | string? | 起始日期 YYYY-MM-DD |
| end_date | string? | 截止日期 YYYY-MM-DD |
| page | int | 默认 1 |
| page_size | int | 默认 20，最大 100 |

响应 200：

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "order_id": "TL20260808143000001",
        "order_status": "completed",
        "payment_status": "paid",
        "station_id": 1,
        "station_name": "甘天地光储充示范站",
        "device_id": 10,
        "connector_id": 1,
        "charged_kwh": 23.50,
        "total_amount": 3525,
        "paid_amount": 3525,
        "start_time": "2026-08-08T14:31:00+08:00",
        "end_time": "2026-08-08T15:16:00+08:00",
        "duration_minutes": 45,
        "created_at": "2026-08-08T14:30:00+08:00"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
  }
}
```

### 7.5 POST /business/orders/{order_id}/cancel（取消订单）

仅 `order_status=pending` 且充电未实际开始时可取消。

请求：无 body。

响应 200：

```json
{
  "code": 0,
  "data": {
    "order_id": "TL20260808143000001",
    "order_status": "cancelled"
  }
}
```

**前置校验**: 非 pending 状态 → `code=1, message=CANNOT_CANCEL`。

### 7.6 充电完成 → 支付流程

充电完成（`order_status=completed`）后，`payment_status` 为 `unpaid`。端侧自动跳转支付：

1. 调 `POST /business/payments/prepay`（§2.1）传入 `order_id` + `openid` 拉起IM-B支付
2. 支付成功 → `payment_status` 变为 `paid`（IM-B回调更新）
3. 用户可在「订单列表」查看历史订单及支付状态

**企业账户/车队余额支付**: 余额扣减在服务端自动完成，端侧不调 prepay，`payment_status` 直接变 `paid`，响应 `payment_method=enterprise/balance`。

### 7.7 订单详情 GET /business/orders/{order_id}

扩展现有 §2.3 的订单查询，返回充电+费用完整明细：

```json
{
  "code": 0,
  "data": {
    "order_id": "TL20260808143000001",
    "order_status": "completed",
    "payment_status": "paid",
    "station_id": 1,
    "station_name": "甘天地光储充示范站",
    "device_id": 10,
    "connector_id": 1,
    "user_type": "app",
    "plate_number": "京A12345",
    "charged_kwh": 23.50,
    "electricity_fee": 2100,
    "service_fee": 1200,
    "parking_fee": 0,
    "idle_penalty": 225,
    "total_amount": 3525,
    "discount_amount": 0,
    "paid_amount": 3525,
    "payment_method": "im-b",
    "start_time": "2026-08-08T14:31:00+08:00",
    "end_time": "2026-08-08T15:16:00+08:00",
    "duration_minutes": 45,
    "start_soc": 35.0,
    "end_soc": 100.0,
    "stop_reason": "full",
    "transaction_id": "4200001234202608081234567890",
    "paid_at": "2026-08-08T15:18:00+08:00",
    "created_at": "2026-08-08T14:30:00+08:00"
  }
}
```

**注意**: §2.3 定义的轻量查询（仅 payment_status/transaction_id/paid_at）保持兼容，§7.7 为完整明细。端侧按需选择调用。

---

## 8. C端用户体系（auth / user / 设备token）

> **状态**: v1.3-draft §8 v0.1（大圣起草 2026-08-15 23:50，丁哥授权自主决策；待猴王确认后升正式版本）
> **原则**: C端用户与运营侧 User/RBAC 完全隔离——独立表 + 独立 token，C端登录不获得任何运营端权限。
> **本期范围 P1**: §8.1 / §8.3 / §8.4 + 后端 PushProvider 抽象；§8.2 预留；钱包缓期；订单端点身份切换另行升版。
> **本期范围 P2**: §8.6 车辆管理 / §8.7 收藏场站（卡 36396f29）；钱包仍缓期。

### 8.0 用户模型（后端 `end_users` 表）

| 字段 | 说明 |
|------|------|
| id | 主键 |
| wx_openid | IM-B openid，unique；新 openid 首登自动注册 |
| wx_unionid | 可空，开放平台打通预留 |
| nickname / avatar_url | 资料 |
| phone | 可空；绑定后可作登录凭证 |
| user_type | `app` \| `card` \| `vin` \| `interconnect` \| `enterprise`（统计口径，默认 app） |
| status | `active` \| `disabled` |
| created_at / updated_at | |

### 8.1 POST /business/auth/wx-login

请求: `{ "code": "<wx.login() code>", "app_id": "可选，默认平台小程序" }`

流程: code2session；**凭证未配置 → mock 模式**：openid = `mock_<sha1(code)前16位>`，响应附 `is_mock: true`（端侧联调不阻塞）。

响应:
```json
{ "code": 0, "data": {
  "token": "<JWT>", "token_type": "Bearer", "expires_in": 43200, "is_mock": true,
  "is_new": true,
  "user": { "end_user_id": 1001, "nickname": "", "avatar_url": "", "phone": null, "user_type": "app" }
} }
```

- JWT: `sub=end_user_id, aud="end_user", exp=now+12h`；**与运营 token 不互换（aud 隔离）**。

### 8.2 POST /business/auth/phone-login（P1 预留，暂不实现）

`{ "phone": "...", "sms_code": "..." }` → 响应结构同 §8.1。

### 8.3 用户资料

- `GET /business/user/me` → `{ end_user_id, nickname, avatar_url, phone, user_type, created_at }`
- `PATCH /business/user/me` `{ nickname?, avatar_url? }` → 更新后返回完整 profile
- `POST /business/user/phone-bind` `{ phone, sms_code }`（短信未配置 → mock 校验码 `123456`，响应附 `is_mock: true`）

### 8.4 设备 token 注册（App push 通道，§5.5 依赖）

- `POST /business/devices/token` `{ "platform": "ios"|"android", "device_token": "...", "app_version": "..." }` — 幂等：同 end_user+platform 覆盖更新；响应 `{ "registered": true }`
- `DELETE /business/devices/token` `{ platform }` → 注销
- 后端 `PushProvider` 抽象接口: `send(end_user_id, title, body, payload)` → 默认 log/no-op 降级（同 wx_subscribe_msg best-effort 模式）；厂商选定后仅加适配器。

### 8.5 兼容与切换

- 现有 `/business/orders|payments|invoices` 仍用运营 token（`get_current_user`），§8 P1 零侵入。
- 订单端点切换 end_user token 的时点与 `end_user_id ↔ ChargingOrder.user_id` 映射，另行决策升版。
- 运营后台 `/users/by-type` 与 `stats.by_user_type` 在 §8 落地后改查 `end_users.user_type`（恢复真实统计，卡 310533ca）。

### 8.6 车辆管理（§8 P2，卡 36396f29）

> 鉴权: `get_current_end_user`（aud=end_user JWT，运营 token 调用一律 401，同 §8.1 隔离）。
> 数据模型: 独立表 `end_user_vehicles`（不复用运营侧 `vehicles` 表 —— 该表车牌/VIN 全局 unique 且绑 `driver_id→users.id`/`tenant_id`，属车队管理域；C 端同名车牌属不同用户属正常场景，复用会双模型漂移）。
> 隔离: 仅本人车辆可见/可操作；非本人 `vehicle_id` 一律 404（不泄露存在性，与 §7 订单隔离口径一致）。
> team scoping 参照 business_orders: C 端车辆是 end_user 私有资产，无团队维度（不校验 team_id）。

| 端点 | 说明 |
|------|------|
| GET /business/vehicles | 本人车辆列表（分页 page/page_size，默认 1/20） |
| POST /business/vehicles | 添加车辆（`plate_number` 必填；`vin` 可空） |
| DELETE /business/vehicles/{vehicle_id} | 删除车辆（删除默认车辆后无默认，不自动顶替） |
| PATCH /business/vehicles/{vehicle_id}/default | 设为默认车辆 |

**POST /business/vehicles** 请求:
```json
{ "plate_number": "川A12345", "vin": "LSVAA1234EXXXXXXX", "brand": "可选", "model": "可选" }
```
- `plate_number`: 必填 1-20 字符，strip 后非空；同 end_user 内唯一（重复 → 409 `VEHICLE_DUPLICATE_PLATE`）。
- `vin`: 可空；传则 17 位大写（非 17 位 → 422）。
- 响应 `data`: 车辆对象 `{ vehicle_id, plate_number, vin, brand, model, is_default, created_at }`。
- 首辆车自动 `is_default=true`；之后添加默认为 false。

**GET /business/vehicles** 响应 `data`: `{ items: [车辆对象], total, page, page_size }`，按 `is_default desc, id desc` 排序（默认车在前）。

**PATCH .../default**: 幂等（已是默认直接返回 200 车辆对象）；同时清除原默认。他人车辆 404。

**DELETE**: 成功 `data` = `{ deleted: true, vehicle_id }`；他人车辆/不存在 → 404。

**错误码**:
| HTTP | 场景 | 契约语义 |
|------|------|---------|
| 401 | 无 token / 运营 token / aud 不符 | C端端点鉴权（HTTPException，同 §8.1） |
| 404 | vehicle_id 非本人或不存在 | 不泄露存在性 |
| 409 | 同用户重复车牌 | `VEHICLE_DUPLICATE_PLATE` |
| 422 | plate_number 空 / vin 非 17 位 | FastAPI 校验 |

### 8.7 收藏场站（§8 P2，卡 36396f29）

> 鉴权/隔离同 §8.6。
> 数据模型: 新表 `end_user_favorites`，`(end_user_id, station_id)` unique —— 一人一站一条。
> 收藏针对全局公开场站（§1 列表口径），无 team 维度。

| 端点 | 说明 |
|------|------|
| GET /business/favorites | 收藏列表（含场站摘要，分页） |
| POST /business/favorites | 收藏 `{ "station_id": 1 }` —— **幂等**：已收藏返回成功（`already: true`），不报错 |
| DELETE /business/favorites/{station_id} | 取消收藏 —— **幂等**：未收藏也返回成功（`deleted: false`） |

**GET /business/favorites** 响应 `data`: `{ items: [{ favorite_id, station_id, created_at, station: { 场站摘要 } }], total, page, page_size }`。

`station` 摘要字段参照 §1（轻量）: `id, name, address, city, status, total_power, gun_count`；场站已被物理删除时 `station: null`（收藏行保留，端侧可提示“场站已下线”）。按收藏时间倒序（新收藏在前）。

**POST**: `station_id` 不存在 → 404（HTTPException；收藏必须指向真实场站，非幂等范围）。新收藏 `data` = `{ favorite_id, station_id, already: false }`；重复收藏 `already: true` 并返回原 favorite_id。

**DELETE /{station_id}**: 成功 `data` = `{ station_id, deleted: true|false }`（false=本来就没有）。

**错误码**:
| HTTP | 场景 | 契约语义 |
|------|------|---------|
| 401 | 无 token / 运营 token / aud 不符 | 同 §8.6 |
| 404 | POST 收藏不存在的 station_id | 场站必须真实存在 |
| 422 | station_id 缺失/非法 | FastAPI 校验 |

> 幂等语义定案: 收藏/取消均幂等返回成功（端侧无需先查再写，规避并发双击/重试的报错路径）；“重复收藏”不设独立错误码。

---

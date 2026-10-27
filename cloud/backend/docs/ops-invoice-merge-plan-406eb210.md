# OpsInvoice 双体系合并摸底报告（卡 406eb210）

> 决策：丁哥拍板 **B1 — 下线旧体系，只留 InvoiceRequest**。
> 本报告为 Phase 1 摸底产物；Phase 2 迁移方案与执行见文末。

## 0. 结论先行

**可以安全迁移，但要分两刀切，且旧数据不做行级迁移（只读归档）。**

1. 两体系**唯一真实重叠** = 「运营处理开票申请」工作流。旧体系的 C 端申请入口（`POST /operate/invoices`）从未被任何 C 端代码调用（全仓 `OpsInvoice(` 写入点仅 `app/api/v1/operate/ops_invoice.py:249` 一处 + 测试），`apply_source=app` 只是模型注释里的设想，**没有 C 端 App 走过这条路** —— C 端真实入口是新体系 `POST /business/invoices`（契约 §5.1）。
2. 旧体系独有能力 = **抬头 CRUD**（`InvoiceTitle` 表，独立于 `OpsInvoice`，可整体保留）+ **红冲 void**（新体系没有，需补端点）。
3. 语义差异（金额单位元 vs 分、状态机 5 态 vs 3 态、team 隔离模型完全不同）使**行级数据迁移到 `invoice_requests` 不可行也无必要** —— 旧表行只可能是运营手工建的测试性数据。正确做法：**表保留、路由下线、数据只读归档**。
4. 前端 7 文件中只有 3 个文件 + 1 个 API 对象真正指向旧体系，切换面很小。

---

## 1. 两体系完整映射表

### 1.1 旧体系（/operate 前缀，`ops_invoice.py`，2026-07 建，SPEC §2.5+§4）

| 端点 | 方法 | 功能 | 权限 | 前端消费 |
|---|---|---|---|---|
| `/operate/invoices/titles` | GET | 抬头列表（user→team 过滤） | get_current_user（team 内） | `InvoiceTitles.tsx` |
| `/operate/invoices/titles` | POST | 建抬头 | require_platform_admin | 同上 |
| `/operate/invoices/titles/{id}` | PUT/DELETE | 改/删抬头 | require_platform_admin | 同上 |
| `/operate/invoices` | GET | 发票列表（全状态） | require_platform_admin | `IssuedInvoices.tsx` |
| `/operate/invoices/pending` | GET | 待审核列表 | require_platform_admin | `PendingInvoices.tsx` |
| `/operate/invoices` | POST | **提交申请**（运营手工建） | require_platform_admin | ❌ 无页面调用 |
| `/operate/invoices/{id}/review` | PUT | 审核（approved→REVIEWED / 驳→REJECTED） | require_platform_admin | `PendingInvoices.tsx` |
| `/operate/invoices/{id}/issue` | PUT | 开具（填 invoice_no/pdf_url） | require_platform_admin | ❌ 无页面调用 |
| `/operate/invoices/{id}/void` | PUT | **红冲**（仅 ISSUED 可红冲） | require_platform_admin | `IssuedInvoices.tsx` |
| `/operate/invoices/{id}` | GET | 详情 | require_platform_admin | ❌ 无页面调用 |

模型 `OpsInvoice`（表 `ops_invoices`）：金额 **元** `Numeric(12,2)`；状态机 5 态 `pending→reviewed→issued→voided/rejected`；无 team_id 列（发票本体平台级）；关联 `invoice_title_id`；冗余 title_name/tax_id。

### 1.2 新体系（/ops 前缀，`ops_invoice_request.py`，2026-08-07 建，卡 a09f8a21，契约 §5.4）

| 端点 | 方法 | 功能 | 权限 | 前端消费 |
|---|---|---|---|---|
| `/ops/invoice-requests` | GET | 申请列表（**team 隔离**，admin 全量） | require_permission("operate:manage") | `ManualInvoiceRequests.tsx` |
| `/ops/invoice-requests/{id}/upload` | POST | multipart 上传发票文件→ISSUED+通知 | 同上 + 限流 10/min | 同上 |
| `/ops/invoice-requests/{id}/reject` | POST | 拒绝→REJECTED（用户可重申） | 同上 + 限流 30/min | 同上 |

模型 `InvoiceRequest`（表 `invoice_requests`）：金额 **分** `Integer`；状态机 3 态 `pending→issued/rejected`；`team_id` FK（创建时由订单 station→team 捕获）；`order_ids` 存 order_no JSON 数组；发票文件落盘 `uploads/invoices/` + magic bytes 校验；通知钩子（订阅消息/App push/邮件）。

### 1.3 C 端 /business/invoices 与新体系的关系：**同一张表的两面**

`business_invoices.py` 是 C 端入口（契约 §5），与 `/ops/invoice-requests` **共用 `InvoiceRequest` 模型和 `invoice_request_service`**：

| C 端端点 | 功能 | 对应运营端 |
|---|---|---|
| `POST /business/invoices` | 用户提交申请（PAID+未开票校验，金额自动汇总成分） | 生成 PENDING 行 → 运营在 /ops 处理 |
| `GET /business/invoices` | 用户申请列表（轻量） | — |
| `GET /business/invoices/{id}` | 详情（ISSUED 返回签名 file_url 2h） | — |
| `POST /business/invoices/{id}/send-email` | 补发/改发邮箱（9/h 限流） | — |
| `GET /business/invoice-file?token=` | 文件下载（签名令牌白名单免登录） | — |

**C 端与新体系是闭环，与旧体系零交集。** 旧体系的 `POST /operate/invoices`（apply_source 字段暗示想接 C 端）从未实现 C 端入口 —— C 端从第一天就走 `/business/invoices`。

### 1.4 关键差异对照

| 维度 | 旧 OpsInvoice | 新 InvoiceRequest |
|---|---|---|
| 金额 | 元 `Numeric(12,2)` | 分 `Integer`（契约 §6） |
| 状态机 | pending→reviewed→issued→voided/rejected | pending→issued/rejected |
| 审核语义 | 两步：review（人审）+issue（开发票）分立 | 一步：upload 即开具 |
| team 隔离 | 无 team_id；发票本体平台级 admin only | team_id FK + assert_team_access（跨 team→404） |
| 申请来源 | 运营手工 POST（无 C 端入口） | C 端 /business/invoices 真实入口 |
| 发票载体 | invoice_no/invoice_code/pdf_url 三字段 | 落盘文件+file_type（magic bytes 校验） |
| 通知 | 无 | 订阅消息+App push+邮件 |
| 限流 | 无 | 60/min、10/min、30/min |
| 抬头关联 | invoice_title_id FK + 冗余字段 | title_type/title_name/tax_number 内联（不关联 InvoiceTitle 表） |

## 2. 线上存量数据查询 SQL（只写 SQL，不连库）

```sql
-- 2.1 行数与状态分布（判定存量规模；若全为 0/手工测试行 → 归档即可）
SELECT status, COUNT(*) AS cnt,
       MIN(created_at) AS earliest, MAX(created_at) AS latest,
       SUM(CASE WHEN apply_source = 'app' THEN 1 ELSE 0 END) AS from_app
FROM ops_invoices
GROUP BY status
ORDER BY cnt DESC;

-- 2.2 总行数
SELECT COUNT(*) FROM ops_invoices;

-- 2.3 非 pending 的行（若 issued/reviewed 有真实数据需人工确认后再下线路由）
SELECT id, apply_source, title_name, amount, status,
       invoice_no, issued_by, created_at
FROM ops_invoices
WHERE status IN ('issued', 'reviewed')
ORDER BY created_at DESC;

-- 2.4 新体系对照（迁移后旧 PENDING 是否还有未处理工单）
SELECT status, COUNT(*) FROM invoice_requests GROUP BY status;

-- 2.5 抬头表规模（保留能力，不动数据）
SELECT COUNT(*) FROM invoice_titles;
```

**判定标准**：2.1 中若 `from_app` 全为 0 且总行数极小（预期 <100，全部为运营手工建的测试数据），确认归档策略。若存在 `status='issued'` 的真实发票记录，需丁哥确认后再下线 —— 但下线路由不影响已开具记录的留存（表不删）。

## 3. 重叠功能清单与迁移方案

### 3.1 功能重叠矩阵

| 功能 | 旧体系 | 新体系 | 处置 |
|---|---|---|---|
| 申请列表 | `/operate/invoices`+`/pending` | `/ops/invoice-requests?status=` | **新体系覆盖**（多了 team 隔离） |
| 审核 | review（approved/rejected 两步） | reject（一步拒绝） | 新体系 reject 等价旧"驳回"；旧"审核通过"在新体系即 upload，**无需单独审核步** |
| 开具 | issue（填号+URL） | upload（传文件） | **语义不同**：旧填号码、新传文件。契约 §5 定的是传文件，以新为准 |
| 拒绝 | review(approved=false) | reject | 等价，新体系覆盖 |
| 红冲 void | ✅ | ❌ **缺失** | **需新增** `/ops/invoice-requests/{id}/void` |
| 抬头 CRUD | `/operate/invoices/titles` | ❌（title 内联在申请单） | **独立保留**（InvoiceTitle 表与新体系无 FK 依赖，路由不动） |
| 手工建申请 | POST `/operate/invoices` | ❌（只处理 C 端来的） | **下线**（运营不该替用户申请发票；如需补录属新需求） |

### 3.2 数据迁移方案：**不迁行，只读归档**

**理由**：
- `OpsInvoice` 的写入点全仓仅 1 处（`ops_invoice.py:249`，运营手工 POST），C 端从未写入 → 存量行只可能是运营自建的测试/演示数据，无 C 端用户资产。
- 两表金额单位（元/分）、状态机（5态/3态）、订单关联（自由 JSON/受控 order_no 数组）语义不兼容，行级迁移会产生"翻译损耗"（reviewed 态无处安放、pdf_url 无对应落盘文件、order_ids 格式不受控），迁出来的行在新体系里是残废数据。
- `invoice_titles` 表独立保留，零迁移。

**归档动作**（Phase 2）：
1. 表 `ops_invoices` **保留不删**（历史数据可查， alembic 无 drop）。
2. 旧路由 `/operate/invoices*`（除 titles 族）**标 deprecated 保留一个版本**（响应头 `Deprecation: true` + `Sunset` 头 + OpenAPI `deprecated=true`），下个版本移除。
3. titles 族路由保留原路径不动（前端 `InvoiceTitles.tsx` 继续用）。

### 3.3 红冲能力迁入新体系（Phase 2 增量）

新体系模型需加列（alembic 增量迁移）：
- `void_reason VARCHAR(500) NULL`
- `voided_by INTEGER NULL`
- `voided_at DATETIME NULL`

新端点 `POST /ops/invoice-requests/{id}/void`：
- 仅 `ISSUED` 可红冲（对齐旧体系守卫）
- body `{reason}`，限流 30/min
- team 隔离同 upload/reject（assert_team_access）
- 红冲后 C 端详情仍可见（status=voided 不在契约 3 态内 → **需与丁哥确认 C 端展示语义**，见 §6 风险）

⚠️ **注意**：加 voided 态会突破契约 §5 的 3 态状态机（pending/issued/rejected）。契约 v1.3 刚定稿（08-16，关联本卡）。**这是唯一需要丁哥拍板的点**：(a) 红冲进入 status 第 4 态（改契约）；(b) 红冲只作废文件引用+备注，status 保持 issued 加 `voided=true` 标记字段（不改状态机）。

## 4. 前端切换方案

### 4.1 现状（7 文件涉及，其中真切换面 4 处）

| 文件 | 现指向 | 处置 |
|---|---|---|
| `src/api/settlement.ts` | `opsInvoiceAPI` 对象（旧 8 方法） | **删除 `opsInvoiceAPI`**，`invoiceTitleAPI`/`invoicePlatformAPI`/`opsInvoiceRequestAPI` 不动 |
| `src/pages/Operate/Invoices/PendingInvoices.tsx` | `opsInvoiceAPI.pending/review` | **整页删除**，"待审核" tab 只留 `ManualInvoiceRequests`（其列表=新体系 pending） |
| `src/pages/Operate/Invoices/IssuedInvoices.tsx` | `opsInvoiceAPI.list/void` | **改指新体系**：list→`opsInvoiceRequestAPI.list({status:'issued'})`，红冲→新 void 端点；列映射（amount 分→元、title_name、invoice_file_name 等） |
| `src/pages/Operate/Invoices/ManualInvoiceRequests.tsx` | `opsInvoiceRequestAPI` | 不动（已新体系） |
| `src/pages/Operate/Invoices/InvoiceTitles.tsx` | `invoiceTitleAPI` | 不动（titles 保留） |
| `src/pages/Operate/Invoices/InvoicePlatforms.tsx` | `invoicePlatformAPI` | 不动（开票平台配置独立域） |
| `src/pages/Operate/Invoices/index.tsx` | tab 容器 | 微调：pending tab 移除 PendingInvoicesPage 引用 |

测试文件 3 个：`invoices.test.tsx`（删旧两页用例+新增切换后用例）、`manual-invoice-requests.test.tsx`（不动）、`settlement-pages.test.tsx`（settlement 域，查是否引用 opsInvoiceAPI）。

### 4.2 切换后页面结构

```
发票管理 /operate/invoices
├── tab 待审核   → ManualInvoiceRequests（新体系 pending 列表 + upload/reject）
├── tab 已开发票 → IssuedInvoices（改指新体系 issued + void）
├── tab 发票抬头 → InvoiceTitles（不变）
└── tab 开票平台 → InvoicePlatforms（不变）
```

### 4.3 UI 语义变化（需丁哥知悉）

- "待审核"列表数据源从旧 OpsInvoice.pending → 新 InvoiceRequest(pending)，**申请人字段从 applicant_name（自由文本）变为 user_id**（需 join 出用户名或显示 ID）。
- 金额展示：旧页 `¥xx.xx`（元）→ 新体系返回 `amount`(分)+`amount_yuan`(元)，用 amount_yuan。
- 旧"审核通过→开具"两步操作在新体系合并为"上传发票文件"一步 —— 契约 §5.4 定的设计，运营侧无需先审核再开票。

## 5. Phase 2 执行计划（TDD）

**前置**：§2 SQL 结果由大圣/丁哥在线上跑，确认无真实 issued 数据后方可执行 5.3 下线。

1. **行为锁定测试（RED→GREEN 基线）**：现有 `tests/api/test_ops_invoice_request.py` + `tests/test_invoice_request.py` 已锁新体系行为；补红冲端点测试（TDD 先行）。
2. **模型加列**（alembic 增量 + `_has_table` 幂等模式）：void_reason/voided_by/voided_at。
3. **新 void 端点**：`ops_invoice_request.py` + service `void_invoice_request`（守卫：仅 ISSUED；team 隔离；通知钩子可选）。
4. **旧路由 deprecated**：发票本体族端点加 `deprecated=True` + 响应头（middleware 或逐端点），titles 族不动。**本版本不移除**。
5. **前端切换**（§4.1）+ 测试更新。
6. **全量验证**：`pytest` 全绿（12705+）+ `npx tsc --noEmit` + `npx vitest run` 全绿。

## 6. 风险与开放问题（需丁哥/大圣拍板）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| R1 | 红冲是否作为 status 第 4 态（突破契约 §5 3 态机，契约 v1.3 昨日刚定稿） | C 端状态展示、契约文档 | 建议 (b)：status 保持 issued + 独立 voided 标记字段，契约只增不破 |
| R2 | 线上 ops_invoices 是否存在真实 issued 记录 | 下线路由不影响数据留存，但若有真实红冲需求需先迁 void 能力 | 跑 §2 SQL 确认；void 端点先行上线再下线旧路由 |
| R3 | 旧 `POST /operate/invoices` 手工建申请能力消失 | 运营无法替用户补录发票申请 | 若有此需求属新功能（新体系加 ops 侧 create 端点），默认不做 |
| R4 | 旧路由 deprecated 期间（1 个版本）旧前端未发版会有双写窗口 | 无：两体系写不同表，不存在数据双写；只存在 UI 入口并存 | 前后端同仓同版本发布，风险极低 |
| R5 | `IssuedInvoices` 列适配（invoice_no/invoice_code/pdf_url 三列在新体系无对应） | 已开发票页列变化 | 显示 invoice_file_name + 下载链接（/business/invoice-file 签名 URL 或 ops 侧加下载端点） |

## 7. 附：全仓引用盘点（96 处口径核实）

- 后端 Python `OpsInvoice` 精确引用：**33 处 / 10 文件**（模型 3、路由 1、`models/__init__`+`spec_tables` 注释 2、测试 5 文件）。96 为大圣端 grep 口径（含 `OpsInvoiceStatus/Type`、字符串 "ops_invoice" 路径、注释等），实际代码面更小。
- 前端：`opsInvoiceAPI` 消费 2 页面 + 1 API 定义 + 1 测试 mock。
- 无其他服务/脚本引用旧表（`grep OpsInvoice(` 写入点全仓 1 处）。

---
*摸底人：石猴（AI 编码助手）· 2026-08-16 · 卡 406eb210*

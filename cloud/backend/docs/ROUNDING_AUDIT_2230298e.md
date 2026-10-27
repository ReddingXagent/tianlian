# 金额舍入审计 — 调研文档（卡 2230298e 缺口3）

> ⚠️ 本文仅调研，**未改动任何舍入代码**。是否统一舍入模式 / 精度策略，由丁哥决策。

## 背景

本卡缺口1 是「负折扣加价语义」导致 **明细合计 ≠ paid_amount** 的财务边界错误（已修：负折扣 raise）。
排查中发现另一类同源隐患——**舍入**——也可能让「逐项 quantize 后求和」≠「求和后 quantize」，
在 `.005` 边界相差 1 分。此为独立隐患，单列影响面供决策，不在本卡静默全仓改动。

## 当前舍入模式

全仓 17 处 `quantize(Decimal("0.0x"))` **均未显式传 `rounding=` 参数**，
统一走 Python `decimal` 模块全局上下文默认值：

```
ROUND_HALF_EVEN  （四舍六入五成双 / 银行家舍入）
```

验证：`python3 -c "import decimal; print(decimal.getcontext().rounding)"` → `ROUND_HALF_EVEN`。

金融场景常见的另一候选是 `ROUND_HALF_UP`（四舍五入，符合多数用户直觉）。
两者仅在「末位正好 5 且前位为偶/奇」时差 1 分（如 `2.345` → HALF_EVEN 得 `2.34`，HALF_UP 得 `2.35`）。

## 影响面清单（grep -rn 'quantize' app/）

| # | 文件:行 | 表达式摘要 | 精度 | 用途 |
|---|---------|-----------|------|------|
| 1 | `app/api/v1/order_fees.py:149` | `kwh*price` | 2 (0.01) | settle 尖/平/谷电费 |
| 2 | `order_fees.py:163` | `energy_total*service_fee_rate` | 2 | 服务费 |
| 3 | `order_fees.py:178` | `parking_hours*parking_rate` | 2 | 停车费 |
| 4 | `order_fees.py:191` | `occupancy_minutes*occupancy_rate` | 2 | 占用费 |
| 5 | `order_fees.py:205` | `reservation_minutes*reservation_rate` | 2 | 预约费 |
| 6 | `order_fees.py:223` | `discount_amount` | 2 | 折扣（已加 ge=0/le=100000） |
| 7 | `order_fees.py:224` | `coupon_amount` | 2 | 优惠券 |
| 8 | `order_fees.py:225` | `points_amount` | 2 | 积分 |
| 9 | `order_fees.py:227` | `total_amount` | 2 | 订单总额 |
| 10 | `order_fees.py:305` | `refund_amount` | 2 | 退款金额 |
| 11 | `app/api/v1/charging_sessions.py:143` | `wh / WH_PER_KWH` | 2 | 充电量(kWh) |
| 12 | `app/api/v1/operate/enterprise_recharge.py:171` | `balance + amount` | 2 | 企业余额入账 |
| 13 | `app/api/v1/operate/ops_settlement.py:360` | `total_amount * ratio` | 2 | 分账己方收入 |
| 14 | `app/services/billing_engine.py:151` | `share * total_kwh` | **4 (0.0001)** | 分时电量（保金额精度） |
| 15 | `billing_engine.py:172` | `merged_fee / merged_energy` | **6 (0.000001)** | 加权平均单价（对齐 OrderFeeItem.unit_price 列） |
| 16 | `billing_engine.py:506` | `seg.kwh` | **4 (0.0001)** | 明细 quantity |
| 17 | `app/services/enterprise_balance_service.py:134` | `current_balance - amount` | 2 | 企业余额扣款 |

另：`app/services/billing.py` 用 `_TWO_PLACES = Decimal("0.01")` 经 `_quantize_or_zero()` 统一量化（2 位），属同一族。

## 关键观察

1. **精度不统一**：金额基本 2 位，但 `billing_engine` 的电量用 4 位、单价用 6 位。
   代码注释表明这是**有意为之**（4 位电量参与 fee 计算保精度；6 位单价对齐 DB 列 `OrderFeeItem.unit_price`），
   非笔误。若统一需先确认展示与对账链路。

2. **「逐项量化后求和」的尾部误差**：`order_fees.py` 先对 5 项费用各自 quantize 再相加（141-227 行），
   `billing.py` 的 `calculate_total_order` 同样先量化各项再求和 `total_amount`。
   多项各含 `*.xx5` 时，量化后求和 与 原始求和后量化 可能差 1~几分 → **明细合计 ≠ total_amount**
   （与缺口1 的「明细合计 ≠ paid_amount」属同一问题族，但根因不同：缺口1 是负折扣语义，这里是浮点尾部）。

3. **HALF_EVEN vs HALF_UP**：当前 HALF_EVEN。若财务/发票侧要求「四舍五入」直觉，
   需全局 `decimal.getcontext().rounding = decimal.ROUND_HALF_UP`（影响范围广，需回归对账）。

## 决策待选项（供丁哥定夺）

- **A. 维持现状**：HALF_EVEN + 混合精度。已知有尾部 1 分级偏差可能，但在 5 项费用场景概率低。
- **B. 统一舍入模式**：全局切 HALF_UP（符合直觉），需全量对账回归。
- **C. 统一求和策略**：改为「原始 Decimal 求和 → 末尾一次性 quantize」，消除逐项量化累积误差。
- **B + C 组合**：最彻底，改动面最大。

本卡不动；后续如要改，建议单独开卡 + 对账回归。

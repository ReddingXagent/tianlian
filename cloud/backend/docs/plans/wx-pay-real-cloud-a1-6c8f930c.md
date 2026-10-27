# IM-B支付真云化 A1 — 凭证无关改造 (卡 6c8f930c)

> 计划文档。TDD: 每步先写测试看红, 再实现看绿。

## 背景 (现状证据)

- `payment.py:151` `amount_fen = 0` (mock 金额=0): 真实回调流会把 `paid_amount` 落成 0 元。
- `client.py:139-154` 工厂固定返回 `MockWxPayClient`, 真实客户端不存在。
- 资金缺口: `handle_notify` SUCCESS 分支不校验回调金额 vs `PaymentOrder.amount_fen`。

## 三块改动

### 1. 金额真实化 (payment.py)

`prepay()` 的 `amount_fen` 从业务订单取应付金额 (分):

- 口径: `ChargingOrder.total_amount − discount_amount − coupon_amount − points_amount`
- 元→分: `Decimal` `ROUND_HALF_UP`; `None` 当 0; 负数钳 0 (对齐 `billing_engine.py` 实收口径)
- 抽公共函数 `compute_amount_fen(co)` (纯函数, 便于边界单测)
- 订单行缺失 (纯支付测试场景) → 0 (与 `_lookup_merchant_by_order` 容错一致)

### 2. RealWxPayClient 骨架 (real_client.py, 新文件)

- 按 `WxPayClient` 抽象实现 v3: `unified_order` / `query_order` / `refund` / `verify_and_decrypt_notify` / `generate_sub_mchid`
- 凭证只从 `settings`/env 读 (`WX_PAY_MODE`, `WX_PAY_SP_MCHID`, `WX_PAY_PRIVATE_KEY_PATH`, `WX_PAY_CERT_SERIAL`, `WX_PAY_APIV3_KEY`, `WX_PAY_APPID_MINIPROGRAM`, `WX_PAY_APPID_APP`, `WX_PAY_NOTIFY_URL`)
- HTTP 传输注入打桩 (构造参数 `transport`/`signer`/`verifier` 可替换)
- 验签 (平台证书验签) 用构造的假密钥对测试向量单测
- AES-256-GCM 解密 resource (APIv3 key)
- 底层异常 → `WxPayError` (client.py docstring 既有约定)

### 3. 工厂切换 (client.py)

- `WX_PAY_MODE=real|mock`, 默认 mock (现有调用方零改动)
- `real` + 凭证缺失 → 抛 `WxPayError` (fail-loud, 不静默回退 mock — mock 假 paySign 混进真实支付流比宕掉更危险)
- `mock` 模式不要求凭证 (现有测试环境零配置)
- 单例双检锁保持不变

### 4. 资金安全缺口修复 (payment.py handle_notify)

SUCCESS 分支落 PAID 前校验:
- 回调金额 vs `PaymentOrder.amount_fen` (等值才落; `mock_client` 明细契约: `amount.total`)
- `notify` 回传 `appid`/`sub_mchid` (`NotifyResult` 增两字段, 默认 None; mock 客户端从明文 body 取) 与订单比对
- 不一致 → 拒绝落 PAID + `logger.error` 告警 + 状态不动 + ACK SUCCESS (同构回调重试无意义, 与未知单 ACK 先例一致; `notify_count` 照常累加)

## 不做

- 真实凭证接入联调 (等丁哥)
- `openid` 改从 `User.openid` 取 (依赖真实 wx-login)
- `resolve_sub_mchid` 跳过 merchant_status 校验问题 (A2 范围)

## 验收

1. `.venv/bin/python -m pytest -q -n0 --timeout=120` 全绿 (基线 12798)
2. 新增测试文件覆盖: 金额口径/边界/工厂切换/回调金额校验
3. `npx tsc --noEmit` (前端不受影响时声明)
4. commit 带卡号 6c8f930c, 只 commit 不 push

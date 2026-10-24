# JPush 极光推送适配器 (卡 7f601f7f)

丁哥 22:28 拍板选型。基础设施已就绪：PushProvider 抽象 (base.py)、
device token 注册端点、invoice_notification 分发层 (卡 5a280e1a)。

## 范围

1. **JPushProvider** (`app/services/push/jpush_provider.py`)
   - REST v3 `POST https://api.jpush.cn/v3/push`，Basic auth = AppKey:MasterSecret
   - audience 用 `registration_id` 数组定向（device_token 即 RegistrationID）
   - notification: android{title,alert,extras} + ios{alert,extras}，extras 带
     invoice_id/status/amount
   - 失败重试 1 次（5xx/网络异常；4xx 不重试）；errcode 1011 → 失效 token 信号
   - 1011 信号通道：duck-typed `drain_invalid_tokens()` — 上层
     `_push_app_notification` 每轮 send 后检查并清理库中失效 token
     （不改 PushProvider 接口，LogPushProvider 不实现 → getattr 默认空）
2. **配置** `config.py`: JIGUANG_APP_KEY / JIGUANG_MASTER_SECRET /
   JIGUANG_ENABLED，pydantic BaseSettings 从 env 读，未配置 → LogPushProvider
   no-op 降级（与现有语义一致）
3. **注册表** `push/__init__.py`: `create_provider()` 工厂 + 惰性判定，
   `_push_app_notification` 经 `get_push_provider()` 接入（不硬绑）
4. **端点扩展** `POST /business/devices/token` 接受 `provider` 可选字段
   （当前仅 "jpush"，None 向后兼容）。只校验不落列——落列需 Alembic 迁移
   （数据库变更红线，另卡处理）；当前唯一真实厂商 JPush，分发时全部
   token 视为 RegistrationID
5. **INFO 顺带修复** `resolve_device_targets` 过滤 DISABLED 用户

## 测试

- respx 未装且不引新依赖 → 注入式 FakeClient（wx_subscribe_msg 同源惯例）
- 覆盖：成功 / 重试后成功 / 全部失败 / 4xx 不重试 / 1011 清理 /
  未配置降级 / 端点 provider 字段校验 / DISABLED 过滤 / 注册表接线

## 明确不做

- 真实送达冒烟（等丁哥配 .env 后另轮）
- provider 列持久化迁移（另卡）
- 凭证不进代码/测试/日志

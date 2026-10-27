"""
配置管理
"""
import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("app.config")

# git 公开默认 SECRET_KEY (卡 75a0069e): 任何与该串相同的配置视为未改默认值,
# 生产环境拒绝启动 (公开串签 JWT = token 可伪造)。
_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production-tianlian-v3"


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "天链光储充运维系统"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = True
    # 部署环境标识 (卡 75a0069e): production 时启动安全守卫收紧
    # (SECRET_KEY 默认值拒绝启动等)。默认 development。
    ENVIRONMENT: str = "development"
    
    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    
    # 数据保留/日志表清理 (卡 0364c10e, maintenance.cleanup_retention_logs):
    # 高增长日志表按窗口过期, 防无限膨胀 (2026-07-25 云端磁盘 100% 事故先例)。
    # 资金/业务表 (charging_orders/settlements/invoices 等) 一律不在清理范围。
    # 默认依据:
    #   通知类 90d — 运营回溯窗口一个季度足够;
    #   控制指令 180d — 半年纠纷取证窗口;
    #   审计日志 365d — 合规需长留但非无限;
    #   效率/能量流水 365d — 支撑同比分析(年对齐);
    #   告警规则/值班/审批日志 180d — 低频表, 半年回溯。
    RETENTION_NOTIFICATIONS_DAYS: int = 90
    RETENTION_NOTIFICATION_LOGS_DAYS: int = 90
    RETENTION_DEVICE_CONTROL_LOGS_DAYS: int = 180
    RETENTION_AUDIT_LOGS_DAYS: int = 365
    RETENTION_DEVICE_EFFICIENCY_LOGS_DAYS: int = 365
    RETENTION_ENERGY_FLOW_LOG_DAYS: int = 365
    RETENTION_ALARM_RULE_LOGS_DAYS: int = 180
    RETENTION_ON_CALL_LOGS_DAYS: int = 180
    RETENTION_RUNBOOK_APPROVAL_LOGS_DAYS: int = 180
    # 分批删除批大小 (按 PK id range chunk, 每批独立 commit, 防大事务长锁)
    RETENTION_DELETE_CHUNK: int = 1000

    # 数据库
    DB_TYPE: str = "sqlite"  # sqlite | postgres
    DATABASE_URL: str = "sqlite:///./tianlian_v3.db"
    DATABASE_URL_DEV: str = "sqlite:///./tianlian_v3.db"
    
    # PostgreSQL 连接池 (仅 postgres 模式)
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_PRE_PING: bool = True
    
    # JWT (SECRET_KEY 必须通过环境变量提供; 开发环境使用默认值)
    # RFC 7518 §3.2 要求 HMAC key ≥32 字节; 生产 SECRET_KEY 必须满足。
    SECRET_KEY: str = "dev-secret-key-change-in-production-tianlian-v3"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # 双 Key 灰度轮换 (卡 a89269c9):
    #   SECRET_KEY_NEW — 新密钥; 配置后 create_access_token 改用新 key 签发,
    #     验证先试新 key。未配置(None)时不启用双 key, 退化为 SECRET_KEY 单 key,
    #     行为与改造前完全一致。
    #   SECRET_KEY_OLD — 旧密钥; 仅用于验证回退 (新 key 失败再试旧 key), 保证
    #     轮换窗口内存量 token 不失效。未配置(None)时回退到 SECRET_KEY。
    # 轮换步骤: ① 配置 SECRET_KEY_NEW=新值(≥32字节) → ② 等存量 token 过期 →
    #   ③ 将新值落到 SECRET_KEY 并清空 SECRET_KEY_NEW/OLD。
    # 解析逻辑(fallback to SECRET_KEY)集中在 app/core/jwt_utils.py, 避免分散维护。
    SECRET_KEY_NEW: Optional[str] = None
    SECRET_KEY_OLD: Optional[str] = None
    
    # Redis (可选)
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    
    # MQTT (可选)
    MQTT_BROKER: Optional[str] = "mqtt://localhost:1883"
    
    # 短信 (可选)
    SMS_SIGN_NAME: Optional[str] = "天链科技"
    # 卡 5f1c5f45: C端短信验证码演示模式守卫。卡 75a0069e 改 fail-safe:
    # SMS_DEV_MODE 默认 False (演示环境显式 opt-in), SMS_DEV_CODE 默认 None
    # (模式开而码未配置 → 启动即报错, 杜绝默认固定码后门)。
    # SMS_DEV_MODE=True 时 phone-bind 允许 SMS_DEV_CODE 固定验证码通过 (演示兼容,
    # 命中打 warning 留审计痕迹); 生产置 False, 此时任何固定码不得通过,
    # 校验端点与真实通道未接入行为一致返回 501。
    SMS_DEV_MODE: bool = False
    SMS_DEV_CODE: Optional[str] = None
    
    # 上传 (可选)
    UPLOAD_DIR: Optional[str] = "./uploads"
    MAX_FILE_SIZE: Optional[int] = 10485760

    # 云端对外可访问域名 (卡 283c1f12, 契约 §5.5):
    # 用于拼接 C 端发票文件下载签名 URL (开票完成/补发邮件正文链接)。
    # 未配置(None/空)时 invoice_request_service._noop_base 回退为相对路径并记
    # warning 告警运维, 不再硬编码假域名 tianlian.example; 生产须配置为对外可访问
    # 的 https 域名 (如 https://api.tianlian.cn), 否则邮件内下载链接无主机不可点击。
    PUBLIC_BASE_URL: Optional[str] = None
    
    # IM告警通知 (Phase19)
    IM_WEBHOOK_URL: Optional[str] = None  # 自定义机器人 Webhook
    IM_APP_ID: Optional[str] = None       # IM应用 App ID (可选)
    IM_APP_SECRET: Optional[str] = None   # IM应用 App Secret (可选)
    IM_NOTIFY_USER_ID: Optional[str] = None  # 告警通知用户 Open ID (可选)
    # 自定义机器人签名密钥 (卡 9fbc00ce): 机器人开启「签名校验」后 body 必须带
    # timestamp+sign (im_notify._build_signed_payload); 未配置(None)不签名
    # 保持历史行为完全兼容。
    IM_SECRET: Optional[str] = None

    # Alertmanager webhook 认证密钥 (Phase17 安全加固 da16d511)
    # POST /alert-webhook 校验请求头 X-Webhook-Secret 或 query ?secret= 与此值。
    # 未配置(None/空)时端点拒绝所有请求并告警，强制生产配置以杜绝伪造 critical 告警
    # 刷屏IM（通知通道 DoS）。不保留裸奔兼容。
    ALERT_WEBHOOK_SECRET: Optional[str] = None

    # Pod 间通信共享密钥 (D2 安全加固 卡69acc93c)
    # /pod register/heartbeat/routes/stations + /cross query/internal/query/routes
    # 校验请求头 X-Pod-Secret 与此值。未配置(None/空)时上述写/查询端点拒绝所有
    # 请求并告警，强制生产配置以杜绝伪造 Pod 注册/心跳污染路由表 (Redis)、
    # 或跨 Pod 查询窃取场站/设备拓扑。与 ALERT_WEBHOOK_SECRET 同源，不保留裸奔兼容。
    POD_COMM_SHARED_SECRET: Optional[str] = None

    # Pod 配置 (Phase2 - 矩阵路由层)
    POD_LOCAL_ONLY: bool = True  # 是否单Pod模式（默认 true）
    POD_ID: str = "pod-01"       # 本 Pod ID
    REGION_ID: str = "default"   # 区域 ID
    POD_ENDPOINT: str = "http://localhost:8000"  # Pod 访问地址
    POD_HEARTBEAT_INTERVAL: int = 30  # 心跳间隔（秒）
    
    # YKC 云快充网关 (任务卡 9a5d070e):
    # 桩主动 TCP 直连平台, 监听端口按 YKC 1.x 约定 8767。
    # 默认关闭, 云端经环境变量 YKC_GATEWAY_ENABLED=true 开启。
    YKC_GATEWAY_ENABLED: bool = False
    YKC_GATEWAY_HOST: str = "0.0.0.0"
    YKC_GATEWAY_PORT: int = 8767
    # SZBus 深圳巴士协议网关 V1.09 (2026-10-09 大圣, 桩 13800000100001 接入):
    # 桩主动 TCP 直连平台, 监听端口默认 8767 (与 YKC 二选一, 同端口互斥)。
    # 默认关闭, 云端经环境变量 SZBUS_GATEWAY_ENABLED=true 开启。
    SZBUS_GATEWAY_ENABLED: bool = False
    SZBUS_GATEWAY_HOST: str = "0.0.0.0"
    SZBUS_GATEWAY_PORT: int = 8767
    SZBUS_ELECTRICITY_PRICE: float = 0.6   # 元/度 (签到应答/计费模板下发)
    SZBUS_SERVICE_PRICE: float = 1.0       # 元/度
    SZBUS_BALANCE_THRESHOLD: float = 1.0   # 元 余额阈值
    SZBUS_DEFAULT_BALANCE: float = 9999.0  # 元 鉴权返回余额

    # TDengine 配置 (Phase3 - 时序引擎集成)
    TDENGINE_ENABLED: bool = False  # 默认关闭，不影响现有系统
    TDENGINE_URL: str = "http://localhost:6041"
    TDENGINE_USER: str = "root"
    TDENGINE_PASS: str = "taosdata"
    TDENGINE_DB: str = "tianlian"

    # 分时电价窗口时区 (卡 9912ba63):
    # VPP 电价时段 (尖峰10-12 / 高峰8-10,18-21 / 低谷23-6) 按工商业本地时间定义。
    # 旧实现 datetime.now() 取 naive 本地时间, 容器默认 UTC 部署时窗口整体错位 8h
    # (上海10点尖峰被当成 UTC10点 = 上海18点高峰尾)。显式锁定电价时区, 跨时区部署
    # 仍选中同一窗口。取值须为 IANA 时区名 (zoneinfo 可解析), 默认 Asia/Shanghai。
    PRICING_TIMEZONE: str = "Asia/Shanghai"

    # 通知静默时段时区 (卡 ac0a7aa7, 与电价卡 9912ba63 同根):
    # NotificationConfig.quiet_start/quiet_end (如 22:00-08:00) 按用户本地时间定义。
    # 旧 _is_quiet_time 用 datetime.now() 取 naive 本地时间, 容器默认 UTC 部署时窗口
    # 整体错位 8h (上海 22:00 静默被当 UTC22:00 = 上海 06:00)。优先用 per-config
    # NotificationConfig.timezone (模型已有但旧实现未用), 缺省回退此全局。IANA 名, 默认上海。
    NOTIFICATION_TIMEZONE: str = "Asia/Shanghai"

    # 值班排班时区 (卡 cea77711, 与电价卡 9912ba63/通知卡 ac0a7aa7 同根):
    # on_call regenerate_shifts 的 start_from (如 2026-01-01T09:00:00) 按用户本地时间
    # 定义。旧 _generate_shifts_for_rule 对 naive 输入 replace(tzinfo=utc) 把本地墙钟当
    # UTC, 容器 UTC 部署时班次整体错位 8h (上海 09:00 被存成 UTC09:00 = 上海 17:00)。
    # naive start_from 按此时区解释再转 UTC 落库; aware 输入原样尊重。IANA 名, 默认上海。
    ONCALL_TIMEZONE: str = "Asia/Shanghai"

    # SZBus 对时字段时区 (卡 b4788b6b, 与电价卡 9912ba63 同根):
    # CP56Time2A 协议语义=墙钟字段, 深圳巴士桩按北京墙钟理解对时/工作参数(0x12)下发。
    # 旧实现 datetime.now() 取容器本地时间, 云端 UTC 容器部署时桩被对成 UTC 墙钟
    # = 慢上海 8h, 桩端显示/桩端峰谷计费错位。显式锁定对时时区, 跨时区部署不再
    # 错位。取值须为 IANA 时区名 (zoneinfo 可解析), 默认 Asia/Shanghai。
    SZBUS_DEVICE_TIMEZONE: str = "Asia/Shanghai"

    # YKC 云快充桩时间字段时区 (卡 3364cef4, 与 SZBus 卡 b4788b6b 同族):
    # CP56Time2A 协议语义=墙钟字段, 云快充 YKC 1.x 桩按北京墙钟打包 0x3B 交易记录
    # start/end/trade 时间。旧实现按 UTC 解 → decode 后错位 8h 直达下游遥测。
    # 显式锁定桩业务时区, 跨时区部署不再错位。取值须为 IANA 时区名
    # (zoneinfo 可解析, 非法回退 Asia/Shanghai), 默认 Asia/Shanghai。
    YKC_DEVICE_TIMEZONE: str = "Asia/Shanghai"

    # 告警升级链 SMS 升级阈值 (卡 8d98ebe3):
    # 告警触发即时IM/企微通知, 未确认经此时长 (分钟) 后升级短信通知 on_call 值班人,
    # 再经同样时长升级语音外呼桩。默认 15min。AlarmEscalationTracker 读取。
    ALARM_SMS_ESCALATE_MIN: int = 15

    # 业务日时区 (卡 c42ac99a, 时区缺陷族第4弹, 同根 9912ba63/ac0a7aa7/cea77711):
    # celery beat 按 Asia/Shanghai 墙钟触发日批 (settlement 01:00 / carbon 02:00 /
    # revenue 02:30 / station 02:40 / carbon-monthly 每月1号 03:00), 但任务体用
    # date.today() 取容器本地日期 → 云端 UTC 部署时业务日整体错位 8h (上海 01:00 =
    # UTC 前日 17:00, date.today() 取到 UTC 前日 → 结算"上海前天"而非"上海昨天")。
    # 日批"补前一天"语义按此时区计算业务日。IANA 名, 默认上海, 环境变量可覆盖。
    BUSINESS_TIMEZONE: str = "Asia/Shanghai"

    # IM-B小程序订阅消息推送 (卡 3591ea8f, 契约 §5.5 开票通知):
    # 小程序 APPID + secret 用于取 access_token 发订阅消息。未配置(None/空)时
    # wx_subscribe_msg 优雅降级为日志 (开发/测试零配置可用), 不发不抛。生产配置后
    # 开票完成/拒绝自动推送订阅消息到用户 openid (经 payment_orders 解析)。
    WX_MP_APPID: Optional[str] = None
    WX_MP_SECRET: Optional[str] = None
    # 订阅消息模板 ID (小程序后台配置, 见 wx_subscribe_msg / invoice_notification):
    # 开具 / 拒绝 两类通知各一。None → invoice_notification 跳过发送降级日志, 不抛。
    WX_INVOICE_ISSUED_TPL: Optional[str] = None
    WX_INVOICE_REJECTED_TPL: Optional[str] = None

    # JPush 极光推送 (卡 7f601f7f, 契约§5.5 App push 通道):
    # AppKey + MasterSecret 来自极光控制台, 经环境变量注入 (严禁硬编码/落日志)。
    # 未配置或 ENABLED=False → push registry 保持 LogPushProvider no-op 降级,
    # 开发/测试零配置可用; 生产配置后开票通知按 device token (RegistrationID)
    # 经 REST v3 真实推送。凭证只进 Basic auth, 不写日志/异常栈。
    JIGUANG_APP_KEY: Optional[str] = None
    JIGUANG_MASTER_SECRET: Optional[str] = None
    JIGUANG_ENABLED: bool = False

    # 字段级加密密钥 (电子发票自动开票 / 敏感配置加密存储):
    # 用于 crypto_utils.Fernet 加密 InvoicePlatformConfig.private_key_enc 等。
    # 取值须为合法 Fernet key (32 字节 urlsafe base64, Fernet.generate_key() 生成)。
    # 未配置(None)时, crypto_utils 从 SECRET_KEY 经 HKDF-SHA256 派生 32 字节 key,
    # 开发零配置可用; 生产建议显式配置独立密钥 (轮换 SECRET_KEY 不会波及已加密字段)。
    FIELD_ENCRYPTION_KEY: Optional[str] = None

    # IM-B服务商支付真实客户端 (卡 6c8f930c A1, 凭证无关骨架):
    # WX_PAY_MODE: mock(默认, 现有调用方零改动) | real(真实IM-B支付 v3)。
    # real 模式凭证齐备校验 fail-loud: 任一必需项缺失 → WxPayError (不静默回退
    # mock, mock 假 paySign 混进真实支付流比启动报错更危险)。凭证只从 env 读,
    # 严禁硬编码/落日志。
    WX_PAY_MODE: str = "mock"
    WX_PAY_SP_MCHID: Optional[str] = None            # 服务商商户号
    WX_PAY_PRIVATE_KEY_PATH: Optional[str] = None    # 商户 API 私钥 PEM 文件路径
    WX_PAY_CERT_SERIAL: Optional[str] = None         # 商户 API 证书序列号
    WX_PAY_APIV3_KEY: Optional[str] = None           # APIv3 密钥 (32 字节 hex, 回调解密)
    WX_PAY_APPID_MINIPROGRAM: Optional[str] = None   # 小程序 appid (scene=miniprogram)
    WX_PAY_APPID_APP: Optional[str] = None           # 开放平台移动应用 appid (scene=app)
    WX_PAY_NOTIFY_URL: Optional[str] = None          # 支付回调地址 (统一下单传入)

    # VPP 调度器模拟数据开关 (卡 1b2f4cc4):
    # simulate(默认): 单例首调加载 5 个模拟站点, 开发/测试零配置可用。
    # 生产部署设 VPP_SIMULATE=0 关闭, 避免模拟站点污染真实调度。
    VPP_SIMULATE: str = "1"

    # OCPP 真下发开关 (卡 87d6f7b9, 契约 §7.1/§7.2):
    # false(默认): business_orders 走 mock (设备在线即 accepted), 现有行为零破坏。
    # true: 经 OCPPAdapter 真实下发 RemoteStart/StopTransaction, 按真实结果
    # (accepted/rejected/offline/timeout) 驱动订单状态与错误码。
    OCPP_REMOTE_DISPATCH_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 允许额外字段

    @model_validator(mode="after")
    def _secure_defaults_guard(self) -> "Settings":
        """卡 75a0069e: 启动期安全守卫 (fail-safe)。

        1. SECRET_KEY 为 git 公开默认值时: 判定生产 (ENVIRONMENT=production, 或
           DEBUG=False 且 DATABASE_URL 非 sqlite) → 拒绝启动; 纯开发 (sqlite) 仅
           warning。公开串签 JWT = token 可伪造, 必须显式覆盖。
        2. SMS_DEV_MODE=True 而 SMS_DEV_CODE 未配置 → 报错 (演示模式必须显式
           配置固定码, 不留默认码后门)。
        3. SMS_DEV_MODE=True 启动打显著 warning (审计痕迹)。
        """
        is_prod = self.ENVIRONMENT == "production" or (
            not self.DEBUG and not self.DATABASE_URL.startswith("sqlite")
        )
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            if is_prod:
                raise ValueError(
                    "SECRET_KEY 仍为 git 公开默认值, 生产环境拒绝启动 "
                    "(公开串签 JWT = token 可伪造); 请在 .env 配置独立强随机 SECRET_KEY "
                    "(≥32 字节) 或设 ENVIRONMENT/DEBUG/DATABASE_URL 明确开发形态"
                )
            logger.warning(
                "SECRET_KEY 为 git 公开默认值, 仅限开发环境; "
                "生产部署必须显式配置独立强随机 SECRET_KEY (≥32 字节)"
            )
        if self.SMS_DEV_MODE:
            if not self.SMS_DEV_CODE:
                raise ValueError(
                    "SMS_DEV_MODE=True 而 SMS_DEV_CODE 未配置: 演示模式必须显式"
                    "配置固定验证码, 不提供默认码 (不留固定码后门)"
                )
            logger.warning(
                "SMS_DEV_MODE=True (演示模式): C端手机验证码接受固定码 "
                "SMS_DEV_CODE 通过, 严禁生产环境开启"
            )
        return self

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
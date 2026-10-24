# 安全加固检查清单 — 天链 V3

## API 限流 ✅

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 全局限流 1000 req/min | ✅ 已实现 | SlowAPI default_limits |
| 登录端点 5 req/min | ✅ 可配置 | rate_limits.login |
| POST/PUT/DELETE 100 req/min | ✅ 可配置 | rate_limits.write |
| 敏感操作 10 req/min | ✅ 可配置 | rate_limits.sensitive |
| 限流响应格式 | ✅ 自动 | SlowAPI 返回 429 + Retry-After |

### 端点限流使用方式
```python
from app.core.rate_limit import limiter, rate_limits

# 登录端点
@router.post("/login")
@limiter.limit(rate_limits["login"])
async def login(...):
    pass

# 写操作端点
@router.post("/devices")
@limiter.limit(rate_limits["write"])
async def create_device(...):
    pass
```

## 安全头 ✅

| 检查项 | 值 | 状态 |
|--------|-----|------|
| X-Content-Type-Options | nosniff | ✅ 已启用 |
| X-Frame-Options | DENY | ✅ 已启用 |
| X-XSS-Protection | 1; mode=block | ✅ 已启用 |
| Strict-Transport-Security | max-age=31536000; includeSubDomains | ✅ 生产环境自动启用 |
| Referrer-Policy | strict-origin-when-cross-origin | ✅ 已启用 |
| Server 头隐藏 | 已移除 | ✅ 已启用 |

## 其他安全措施

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 请求体大小限制 | ✅ 10MB | 防止大 payload 攻击 |
| CORS 白名单 | ✅ | 已配置，禁止通配符 + credentials |
| JWT 认证 | ✅ | API 路由统一鉴权 |
| 错误信息不泄露 | ✅ | 500 错误不返回内部详情（生产环境） |
| 生产环境文档关闭 | ✅ | docs_url/redoc_url None |
| Sentry 错误监控 | ✅ | send_default_pii=false |

## 启动验证

```bash
# 1. 检查安全头
curl -I http://localhost:8080/

# 预期输出包含:
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# X-XSS-Protection: 1; mode=block

# 2. 检查限流（快速连续请求登录接口）
for i in {1..6}; do
  curl -s -X POST http://localhost:8080/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test"}' \
    -w "\nHTTP %{http_code}\n"
done
# 第6次应返回 429

# 3. 安全扫描建议
# - 使用 OWASP ZAP 或 Burp Suite 综合扫描
# - 使用 bandit 扫描 Python 代码
pip install bandit && bandit -r backend/app/
```
# Sentry 错误监控接入指南 — 天链 V3

## 1. 注册 Sentry 账号并创建项目

### 1.1 注册
1. 打开 [sentry.io](https://sentry.io)
2. 点击 **Sign Up**，推荐使用 GitHub/GitLab 账号登录
3. 免费版支持 5000 errors/month，足够小项目使用

### 1.2 创建项目
1. 登录后进入 **Projects** 页面，点击 **Create Project**
2. 选择平台：**FastAPI** (或搜索 FastAPI)
3. 设置项目名称（如 `tianlian-v3-backend`）
4. Team 默认为自己的 team
5. 点击 **Create Project**

### 1.3 获取 DSN
1. 项目创建完成后，Sentry 会显示客户端配置页面
2. 复制 **DSN** 地址，格式类似：
   ```
   https://xxx@sentry.io/12345
   ```
3. 或进入 **Settings → Client Keys (DSN)** 查看

## 2. 配置天链 V3

### 2.1 设置环境变量
编辑 `backend/.env` 添加以下配置：

```bash
# Sentry 错误监控
SENTRY_DSN=https://your-key@sentry.io/your-project-id
SENTRY_ENABLED=true
SENTRY_ENVIRONMENT=development    # 或 production
SENTRY_TRACES_SAMPLE_RATE=1.0    # 开发环境 100%，生产环境建议 0.1
```

### 2.2 启动应用
```bash
cd backend
source venv/bin/activate
python -m app.main
```

启动成功后日志会输出：
```
Sentry 已初始化: env=development, traces_sample_rate=1.0
```

## 3. 验证

1. 故意触发一个异常（如访问不存在的接口）
2. 打开 Sentry 项目页面，查看 **Issues** 标签
3. 应该能看到捕获的错误记录

## 4. 注意事项

| 项目 | 说明 |
|------|------|
| **开发环境** | SENTRY_ENABLED=false 可禁用 Sentry，避免干扰 |
| **生产环境** | traces_sample_rate 建议 0.1~0.3，避免采样过多 |
| **敏感信息** | SDK 默认 send_default_pii=false，不发送用户个人信息 |
| **免费限制** | 免费版 5000 events/month，超过需要升级 |
| **告警配置** | 可在 Sentry 项目设置中配置邮件/Slack 告警通知 |
| **性能监控** | traces_sample_rate 控制 Performance 采样 |

## 5. 常见问题

### Q: 启动报错 "Sentry DSN 未配置"
**A:** 检查 `.env` 中是否设置了 `SENTRY_DSN` 和 `SENTRY_ENABLED=true`

### Q: Sentry 收不到错误
**A:**
- 检查 `SENTRY_ENABLED=true` 是否生效
- 检查 DSN 是否复制正确（无空格/换行）
- 检查服务器能否访问 `sentry.io`（防火墙/代理）

### Q: 如何暂时关闭 Sentry
**A:** 设置 `SENTRY_ENABLED=false` 并重启应用
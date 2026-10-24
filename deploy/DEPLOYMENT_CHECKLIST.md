# 🚀 天链 V3 生产部署检查清单

**创建时间**: 2026-04-04 04:22  
**状态**: 🔄 进行中  
**优先级**: P1 (高)

## 📊 当前系统状态

### ✅ 本地开发环境运行正常
| 服务 | 地址 | 状态 | 检查时间 |
|------|------|------|----------|
| 后端 API | http://localhost:8080 | ✅ 运行正常 | 2026-04-04 04:22 |
| 前端 Web | http://localhost:3004 | ✅ 运行正常 | 2026-04-04 04:22 |
| 数据库 | SQLite (tianlian_v3.db) | ✅ 7个设备 | 2026-04-04 04:22 |

### 🔧 部署准备状态
| 项目 | 状态 | 备注 |
|------|------|------|
| 部署脚本 | ✅ 完成 | `deploy/production.sh` |
| 服务器脚本 | ✅ 完成 | `deploy/server-setup.sh` |
| 部署计划 | ✅ 完成 | `deploy/PRODUCTION_PLAN.md` |
| 环境配置 | ✅ 完成 | `backend/.env` |
| 数据库迁移 | ⚠️ 待准备 | SQLite → PostgreSQL |
| 域名配置 | ❌ 未配置 | 需要购买域名 |
| SSL证书 | ❌ 未配置 | Let's Encrypt |
| 服务器 | ❌ 未准备 | 需要云服务器 |

## 🎯 下一步行动 (按 HEARTBEAT.md 要求)

### 1. 服务器准备 (需要用户提供信息)
**状态**: ❌ 等待用户提供服务器信息

**需要的信息**:
- [ ] 云服务器提供商 (云服务商/服务商B云/其他)
- [ ] 服务器规格 (CPU/内存/存储)
- [ ] 服务器 IP 地址
- [ ] SSH 访问凭据
- [ ] 域名 (可选，推荐)
- [ ] 预算限制

### 2. 部署方案选择
**方案 A: 云服务器部署** (推荐)
- 优点: 稳定、可扩展、有技术支持
- 成本: 约 ¥100-300/月 (2核4G)
- 适合: 正式生产环境

**方案 B: 本地服务器部署**
- 优点: 成本低、数据本地化
- 缺点: 需要固定IP、网络稳定性
- 适合: 内部测试环境

**方案 C: Docker 容器部署**
- 优点: 部署简单、环境一致
- 适合: 有 Docker 经验的团队

### 3. 技术准备 (我可以完成的部分)

#### ✅ 已完成
1. **代码打包**: 前端/后端/移动端代码已准备
2. **部署脚本**: 自动化部署脚本已编写
3. **配置管理**: 环境配置文件已准备
4. **数据库设计**: SQLite 数据库已运行

#### 🔄 进行中
1. **数据库迁移脚本**: 需要编写 SQLite → PostgreSQL 迁移脚本
2. **监控配置**: 需要配置系统监控和告警
3. **备份策略**: 需要制定数据备份计划

#### ❌ 待完成 (需要用户决策)
1. **服务器选择**: 需要确定服务器提供商和规格
2. **域名注册**: 需要注册域名并配置 DNS
3. **SSL证书**: 需要申请和配置 HTTPS
4. **访问控制**: 需要确定用户访问权限

## 🔧 技术实施步骤

### 阶段 1: 服务器初始化 (预计: 30分钟)
```bash
# 1. 登录服务器
ssh root@your-server-ip

# 2. 运行初始化脚本
cd deploy
./server-setup.sh

# 3. 安装依赖
apt update && apt install -y \
  postgresql postgresql-contrib \
  redis-server \
  nginx \
  python3.11 python3.11-venv \
  nodejs npm
```

### 阶段 2: 数据库迁移 (预计: 15分钟)
```bash
# 1. 创建 PostgreSQL 数据库
sudo -u postgres psql << SQL
CREATE DATABASE tianlian_v3;
CREATE USER tianlian WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE tianlian_v3 TO tianlian;
SQL

# 2. 导出 SQLite 数据
sqlite3 tianlian_v3.db .dump > tianlian_dump.sql

# 3. 导入到 PostgreSQL (需要转换)
# 需要编写转换脚本
```

### 阶段 3: 后端部署 (预计: 20分钟)
```bash
# 1. 复制代码到服务器
scp -r backend/ root@your-server-ip:/opt/tianlian/

# 2. 配置 Python 环境
cd /opt/tianlian
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 配置生产环境
cp .env.example .env.production
# 编辑 .env.production 配置生产参数

# 4. 启动服务
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app \
  --bind 127.0.0.1:8000 \
  --daemon
```

### 阶段 4: 前端部署 (预计: 15分钟)
```bash
# 1. 构建前端
cd frontend
npm run build

# 2. 配置 Nginx
sudo cp -r dist/* /var/www/tianlian/
sudo nano /etc/nginx/sites-available/tianlian

# 3. 配置 HTTPS
sudo certbot --nginx -d tianlian.yourdomain.com
```

### 阶段 5: 移动端部署 (预计: 30分钟)
```bash
# 1. 构建 iOS 应用 (需要 macOS)
cd mobile
npx expo prebuild --platform ios

# 2. 使用 Xcode 构建
xcodebuild -workspace ios/app.xcworkspace \
  -scheme app \
  -configuration Release \
  -archivePath app.xcarchive \
  archive

# 3. 导出 IPA
xcodebuild -exportArchive \
  -archivePath app.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath ./
```

## 📋 部署验证清单

### 部署后验证
- [ ] 后端 API 可访问: `https://tianlian.yourdomain.com/api/v1/health`
- [ ] 前端页面可访问: `https://tianlian.yourdomain.com`
- [ ] 数据库连接正常: PostgreSQL 运行正常
- [ ] Redis 缓存正常: Redis 连接正常
- [ ] SSL 证书有效: HTTPS 访问正常
- [ ] 移动端可安装: iOS/Android 应用可安装

### 功能验证
- [ ] 用户登录/注册功能正常
- [ ] 设备管理功能正常
- [ ] 实时监控功能正常
- [ ] 告警通知功能正常
- [ ] 工单管理功能正常
- [ ] 数据统计功能正常

## 🚨 风险与应对

### 技术风险
1. **数据库迁移失败**
   - 应对: 准备回滚方案，先测试迁移脚本

2. **服务器配置错误**
   - 应对: 使用配置管理工具，记录所有配置变更

3. **网络连接问题**
   - 应对: 配置多区域部署，使用 CDN 加速

### 业务风险
1. **数据丢失风险**
   - 应对: 实施定期备份，测试恢复流程

2. **服务中断风险**
   - 应对: 配置监控告警，准备应急预案

3. **安全风险**
   - 应对: 实施安全扫描，定期更新依赖

## 📞 联系信息

**部署负责人**: 大圣 (AI 助手)  
**技术支持**: 丁哥  
**紧急联系人**: 丁哥 (157****3673)  
**部署时间**: 待定 (建议周末低峰期)

## 📝 部署记录

| 时间 | 操作 | 状态 | 负责人 |
|------|------|------|--------|
| 2026-04-04 04:22 | 创建部署检查清单 | ✅ 完成 | 大圣 |
| 2026-04-04 04:22 | 检查本地环境 | ✅ 完成 | 大圣 |
| 待定 | 获取服务器信息 | ❌ 等待 | 丁哥 |
| 待定 | 服务器初始化 | ❌ 等待 | 大圣 |
| 待定 | 数据库迁移 | ❌ 等待 | 大圣 |
| 待定 | 后端部署 | ❌ 等待 | 大圣 |
| 待定 | 前端部署 | ❌ 等待 | 大圣 |
| 待定 | 移动端部署 | ❌ 等待 | 大圣 |
| 待定 | 部署验证 | ❌ 等待 | 大圣 |

---

**下一步**: 等待用户提供服务器信息，然后开始部署实施。
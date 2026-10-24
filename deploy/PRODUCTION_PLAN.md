# 天链 V3 生产环境部署计划

**创建时间**: 2026-04-03 11:56  
**状态**: 📋 待部署  
**当前环境**: 本地开发 (localhost)

---

## 📊 当前系统状态

### 服务运行状态
| 服务 | 地址 | 状态 |
|------|------|------|
| 后端 API | http://localhost:8080 | ✅ 运行正常 |
| 前端 Web | http://localhost:3004 | ✅ 运行正常 |
| 移动端 | mobile/dist/ | ✅ 打包完成 |
| 数据库 | SQLite (tianlian_v3.db) | ✅ 运行正常 |

### 业务数据
- 站点：3 个 (100% 在线)
- 设备：7 个 (100% 在线)
- 健康度：99.9 分
- 告警：0 个
- 工单：0 个

---

## 🚀 生产部署方案

### 方案 A: 云服务器部署 (推荐)

**目标服务器**: 云服务商/服务商B云 Ubuntu 22.04

#### 前置准备
1. [ ] 购买云服务器 (2 核 4G 起步)
2. [ ] 配置域名 (tianlian.xxx.com)
3. [ ] 配置 SSL 证书 (Let's Encrypt)
4. [ ] 配置服务器防火墙

#### 部署步骤

**1. 服务器初始化**
```bash
# 运行初始化脚本
cd deploy
./server-setup.sh
```

**2. 数据库迁移 (SQLite → PostgreSQL)**
```bash
# 安装 PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# 创建数据库
sudo -u postgres psql << SQL
CREATE DATABASE tianlian_v3;
CREATE USER tianlian WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE tianlian_v3 TO tianlian;
SQL

# 修改后端配置
# backend/app/core/config.py
# DATABASE_URL = "postgresql://tianlian:password@localhost/tianlian_v3"
```

**3. 后端部署**
```bash
# 创建 Python 虚拟环境
python3.11 -m venv /opt/tianlian/venv
source /opt/tianlian/venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 配置生产参数

# 使用 Gunicorn 启动
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app \
  --bind 127.0.0.1:8000 \
  --daemon

# 配置 systemd 服务
sudo systemctl enable tianlian-api
sudo systemctl start tianlian-api
```

**4. 前端部署**
```bash
# 构建生产版本
cd frontend
npm run build

# 复制到 Nginx 目录
sudo cp -r dist/* /var/www/tianlian/

# 配置 Nginx
sudo nano /etc/nginx/sites-available/tianlian
```

**Nginx 配置示例**:
```nginx
server {
    listen 80;
    server_name tianlian.xxx.com;

    location / {
        root /var/www/tianlian;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**5. 配置 HTTPS**
```bash
sudo certbot --nginx -d tianlian.xxx.com
```

---

### 方案 B: 本地服务器部署 (测试用)

**适用场景**: 内网测试、演示环境

#### 部署步骤

**1. 固定 IP 地址**
```bash
# 在路由器配置静态 DHCP 或手动设置
# 建议 IP: 192.168.1.100
```

**2. 后端部署**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

**3. 前端部署**
```bash
cd frontend
npm run build
# 使用 Nginx 或 serve 托管
npx serve -s dist -l 3000
```

**4. 移动端部署**
```bash
# 方式 1: Expo Go (开发测试)
cd mobile
npx expo start

# 方式 2: 构建 APK
npx eas build --platform android --profile production
```

---

### 方案 C: Docker 容器化部署 (推荐)

**优势**: 环境一致、易扩展、易维护

#### Docker Compose 配置

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: tianlian_v3
      POSTGRES_USER: tianlian
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://tianlian:${DB_PASSWORD}@db/tianlian_v3
    depends_on:
      - db
    ports:
      - "8000:8000"

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "80:80"

volumes:
  postgres_data:
```

**部署命令**:
```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

---

## 📋 部署检查清单

### 部署前
- [ ] 代码已合并到 main 分支
- [ ] 所有测试通过
- [ ] 环境变量配置完成
- [ ] 数据库备份完成
- [ ] 域名解析配置
- [ ] SSL 证书准备

### 部署中
- [ ] 服务器初始化
- [ ] 数据库迁移
- [ ] 后端服务启动
- [ ] 前端构建部署
- [ ] Nginx 配置
- [ ] HTTPS 配置

### 部署后
- [ ] 访问测试 (HTTP/HTTPS)
- [ ] API 接口测试
- [ ] 登录功能测试
- [ ] 核心功能测试
- [ ] 性能测试
- [ ] 监控告警配置

---

## 🔧 运维配置

### 日志管理
```bash
# 后端日志
journalctl -u tianlian-api -f

# Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### 监控告警
- [ ] 配置服务器监控 (CPU/内存/磁盘)
- [ ] 配置服务健康检查
- [ ] 配置告警通知 (邮件/短信/钉钉)

### 备份策略
```bash
# 数据库备份 (每日凌晨 3 点)
0 3 * * * pg_dump tianlian_v3 > /backup/tianlian_$(date +\%Y\%m\%d).sql

# 代码备份
git push origin main
```

---

## 📱 移动端发布

### iOS
1. 需要 macOS + Xcode
2. 配置 Apple Developer 账号
3. 构建 IPA 文件
4. 提交 App Store 审核

### Android
1. 使用 EAS Build
2. 配置 Google Play 账号
3. 构建 AAB/APK 文件
4. 提交 Google Play 审核

**快速构建命令**:
```bash
# Android
npx eas build --platform android --profile production

# iOS
npx eas build --platform ios --profile production
```

---

## 🎯 下一步行动

1. **确定部署方案** (云/本地/Docker)
2. **准备服务器资源**
3. **配置域名和 SSL**
4. **执行部署脚本**
5. **验证功能**
6. **配置监控告警**

---

**文档作者**: 大圣 🐵  
**更新时间**: 2026-04-03 11:56

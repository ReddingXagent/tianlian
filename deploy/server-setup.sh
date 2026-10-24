#!/bin/bash
# 服务器初始化脚本 (Ubuntu 22.04)

# 更新系统
apt update && apt upgrade -y

# 安装 Python 3.11
apt install -y python3.11 python3.11-venv python3.11-dev

# 安装 PostgreSQL
apt install -y postgresql postgresql-contrib

# 配置 PostgreSQL
sudo -u postgres psql << SQL
CREATE DATABASE tianlian_v3;
CREATE USER tianlian WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE tianlian_v3 TO tianlian;
ALTER USER tianlian CREATEDB;
SQL

# 安装 Redis
apt install -y redis-server

# 安装 Nginx
apt install -y nginx

# 安装 Certbot (HTTPS)
apt install -y certbot python3-certbot-nginx

# 配置防火墙
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "✅ 服务器初始化完成"

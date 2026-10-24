# ─── 天链V3 前端 Dockerfile ───
# 多阶段构建: 构建阶段 + 生产运行阶段

# ─── Stage 1: 构建 ───
FROM node:20.18-alpine AS builder

WORKDIR /app

# 复制 package.json 和 lock 文件
COPY package*.json ./

# 安装依赖
RUN npm ci

# 复制源码
COPY . .

# 构建生产版本
RUN npm run build

# ─── Stage 2: 生产运行 ───
FROM nginx:1.27-alpine

LABEL maintainer="天链团队"
LABEL description="天链光储充运维系统 V3 前端"

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 创建非 root 用户 (nginx 已有 nginx 用户)
RUN chown -R nginx:nginx /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

# nginx 前台运行
CMD ["nginx", "-g", "daemon off;"]
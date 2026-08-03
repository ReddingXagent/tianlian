# 天链V3 边缘网关 — 多阶段 Dockerfile
# 构建: docker build -t tianlian-edge-gateway .
# 运行: docker run -d --name gateway --env-file .env -p 8080:8080 tianlian-edge-gateway
# compose: docker compose up -d

FROM --platform=$BUILDPLATFORM python:3.10-slim AS base

# 元信息
LABEL org.opencontainers.image.title="TianLian Edge Gateway"
LABEL org.opencontainers.image.description="天链V3 边缘网关 — Modbus/OCPP/MQTT 适配 + 云端同步"
LABEL org.opencontainers.image.source="https://192.168.31.100:2222/volume1/homes/MonkeyKing/repos/tianlian-edge-gateway.git"
LABEL org.opencontainers.image.licenses="Proprietary"

# 构建参数（支持多架构: docker buildx build --platform linux/arm64,linux/amd64）
ARG TARGETPLATFORM
RUN echo "Building for $TARGETPLATFORM"

# 系统依赖（ss/fuser 用于 deploy.sh 端口检测；curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl iproute2 procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依赖层（缓存优化：requirements.txt 单独 COPY）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 数据目录（SQLite DB 挂载点）
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# 健康检查（容器内每 30s curl /health）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

EXPOSE 8080

# 非 root 运行
RUN useradd -r -s /bin/false gateway && chown -R gateway:gateway /app
USER gateway

CMD ["python3", "main.py"]

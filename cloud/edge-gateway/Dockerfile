# 天链 V3 边缘网关
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p data

# 暴露端口
# 8080: 管理 API
# 9000: OCPP WebSocket
EXPOSE 8080 9000

# 启动
CMD ["python", "-m", "app.main"]

#!/bin/bash
set -e
echo "=== 天链V3 边缘网关 测试套件 ==="
echo ""

echo "1️⃣  安装依赖..."
pip install --break-system-packages -q aiohttp paho-mqtt pymodbus ocpp fastapi uvicorn pydantic aiosqlite pytest pytest-asyncio websockets coverage 2>/dev/null

echo "2️⃣  运行单元测试..."
cd "$(dirname "$0")/.."
python -m pytest tests/ -v --tb=short 2>&1 || true

echo ""
echo "3️⃣  覆盖率报告..."
coverage run -m pytest tests/ -q 2>/dev/null
coverage report -m 2>&1 || true

echo ""
echo "=== 完成 ==="

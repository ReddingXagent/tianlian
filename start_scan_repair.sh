#!/bin/bash
# 扫码报修功能启动脚本

echo "🚀 启动天链扫码报修功能..."

# 启动后端
echo "1. 启动后端服务..."
cd /Users/xxx/.openclaw/workspace/projects/tianlian-v3/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# 等待后端启动
sleep 2

# 启动前端
echo "2. 启动前端服务..."
cd /Users/xxx/.openclaw/workspace/projects/tianlian-v3/frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ 服务启动成功！"
echo ""
echo "📋 访问地址:"
echo "  - 前端: http://localhost:3005"
echo "  - 扫码页面: http://localhost:3005/scan"
echo "  - 后端API: http://localhost:8000"
echo "  - API文档: http://localhost:8000/docs"
echo ""
echo "🔍 测试设备编码:"
echo "  - TL-DEV001 (直流充电桩01)"
echo "  - TL-DEV002 (交流充电桩01)"
echo ""
echo "⚠️ 按 Ctrl+C 停止服务"

# 等待子进程
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
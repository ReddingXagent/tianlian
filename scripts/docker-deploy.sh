#!/bin/bash
# ─── 天链V3 Docker 一键部署脚本 ───
set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   天链V3 Docker 容器化部署工具           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# 检查 Docker 是否安装
check_prerequisites() {
    echo -e "${YELLOW}[1/6] 检查前置条件...${NC}"

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装，请先安装 Docker${NC}"
        exit 1
    fi
    echo -e "  ✅ Docker $(docker --version | awk '{print $3}' | sed 's/,//')"

    if ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Compose 未安装，请先安装 Docker Compose${NC}"
        exit 1
    fi
    echo -e "  ✅ Docker Compose 已安装"

    echo -e "${GREEN}  前置条件检查通过${NC}"
}

# 准备环境文件
prepare_env() {
    echo ""
    echo -e "${YELLOW}[2/6] 准备环境配置...${NC}"

    if [ ! -f .env.docker ]; then
        echo -e "${RED}❌ .env.docker 不存在${NC}"
        exit 1
    fi

    # 检查是否存在 .env，不存在则从 .env.docker 复制
    if [ ! -f .env ] && [ -f .env.docker ]; then
        cp .env.docker .env
        echo -e "${YELLOW}  ⚠️  已从 .env.docker 创建 .env，请检查并修改配置${NC}"
    fi

    echo -e "  ✅ 环境配置文件就绪"
}

# 构建镜像
build_images() {
    echo ""
    echo -e "${YELLOW}[3/6] 构建 Docker 镜像...${NC}"

    docker compose build --pull --no-cache backend frontend

    echo -e "${GREEN}  ✅ 镜像构建完成${NC}"
}

# 启动服务
start_services() {
    echo ""
    echo -e "${YELLOW}[4/6] 启动服务...${NC}"

    docker compose up -d

    echo -e "${GREEN}  ✅ 服务已启动${NC}"
}

# 健康检查
health_check() {
    echo ""
    echo -e "${YELLOW}[5/6] 健康检查...${NC}"

    # 等待后端启动
    echo "  等待后端就绪..."
    for i in {1..30}; do
        if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
            echo -e "  ✅ 后端健康: $(curl -s http://localhost:8000/api/v1/health)"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo -e "${RED}  ❌ 后端启动超时${NC}"
            echo -e "  查看日志: docker compose logs backend"
            exit 1
        fi
        sleep 2
    done

    # 等待前端就绪
    echo "  等待前端就绪..."
    for i in {1..15}; do
        if curl -sf http://localhost:3004/ > /dev/null 2>&1; then
            echo -e "  ✅ 前端就绪 (端口 3004)"
            break
        fi
        if [ "$i" -eq 15 ]; then
            echo -e "${YELLOW}  ⚠️  前端启动超时，请检查: docker compose logs frontend${NC}"
        fi
        sleep 2
    done
}

# 显示信息
show_info() {
    echo ""
    echo -e "${YELLOW}[6/6] 部署信息${NC}"
    echo ""
    echo -e "  ${GREEN}╔════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║  🎉 天链V3 部署成功！         ║${NC}"
    echo -e "  ${GREEN}╠════════════════════════════════╣${NC}"
    echo -e "  ${GREEN}║  前端: http://localhost:3004   ║${NC}"
    echo -e "  ${GREEN}║  API:  http://localhost:8000   ║${NC}"
    echo -e "  ${GREEN}║  API文档: http://localhost:8000/docs  ║${NC}"
    echo -e "  ${GREEN}╚════════════════════════════════╝${NC}"
    echo ""
    echo "  常用命令:"
    echo "    查看日志: docker compose logs -f"
    echo "    查看状态: docker compose ps"
    echo "    停止服务: docker compose down"
    echo "    重启服务: docker compose restart"
    echo "    完全清理: docker compose down -v"
}

# ─── 子命令处理 ───
case "${1:-deploy}" in
    deploy)
        check_prerequisites
        prepare_env
        build_images
        start_services
        health_check
        show_info
        ;;
    start)
        echo -e "${BLUE}启动天链V3服务...${NC}"
        docker compose up -d
        health_check
        show_info
        ;;
    stop)
        echo -e "${YELLOW}停止天链V3服务...${NC}"
        docker compose down
        echo -e "${GREEN}✅ 服务已停止${NC}"
        ;;
    restart)
        echo -e "${BLUE}重启天链V3服务...${NC}"
        docker compose restart
        health_check
        echo -e "${GREEN}✅ 服务已重启${NC}"
        ;;
    logs)
        docker compose logs -f "${2:-}"
        ;;
    status)
        echo -e "${BLUE}天链V3 服务状态:${NC}"
        docker compose ps
        echo ""
        echo -e "${BLUE}健康检查:${NC}"
        if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
            echo -e "  ✅ 后端: $(curl -s http://localhost:8000/api/v1/health)"
        else
            echo -e "  ❌ 后端不可达"
        fi
        if curl -sf http://localhost:3004/ > /dev/null 2>&1; then
            echo -e "  ✅ 前端可达 (端口 3004)"
        else
            echo -e "  ❌ 前端不可达"
        fi
        ;;
    clean)
        echo -e "${RED}即将清理所有资源（包括数据卷）...${NC}"
        read -p "确认? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker compose down -v
            docker compose -f docker-compose.full.yml down -v 2>/dev/null || true
            echo -e "${GREEN}✅ 清理完成${NC}"
        else
            echo "已取消"
        fi
        ;;
    *)
        echo "用法: $0 {deploy|start|stop|restart|logs|status|clean}"
        echo ""
        echo "  deploy  - 一键构建+部署 (默认)"
        echo "  start   - 启动已有服务"
        echo "  stop    - 停止服务"
        echo "  restart - 重启服务"
        echo "  logs    - 查看日志 (可选指定服务名)"
        echo "  status  - 查看状态和健康检查"
        echo "  clean   - 完全清理 (含数据卷)"
        exit 1
        ;;
esac
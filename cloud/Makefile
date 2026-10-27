PACKAGE_NAME = tianlian-v3

.PHONY: dev build deploy deploy-dry backend test db-migrate check lint changelog changelog-latest openapi openapi-check openapi-diff help

# 本地开发
dev:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

backend:
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

# 部署 (改进版，带健康检查/回滚)
deploy:
	bash deploy.sh

deploy-dry:
	bash deploy.sh --dry-run

deploy-ci:
	bash scripts/ci-deploy.sh $(BRANCH)

# 数据库迁移 (改进版，带备份/索引创建/验证)
db-migrate:
	bash scripts/db-migrate.sh

db-migrate-dry:
	bash scripts/db-migrate.sh --dry-run

# 测试 (改进版，conftest.py自动处理import路径)
test:
	cd backend && python3 -m pytest tests/ -v --tb=short

test-quiet:
	cd backend && python3 -m pytest tests/ -q --tb=line

test-cov:
	cd backend && python3 -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

# 代码检查
check:
	cd frontend && npx tsc --noEmit

lint:
	cd frontend && npx eslint src/ --ext .ts,.tsx 2>/dev/null || echo "(eslint not configured)"

# 备份数据库
backup-db:
	bash scripts/backup-db.sh

# Changelog 生成
changelog:
	python3 scripts/generate-changelog.py

changelog-latest:
	python3 scripts/generate-changelog.py --latest

changelog-dry:
	python3 scripts/generate-changelog.py --dry-run

# OpenAPI 文档生成
openapi:
	bash scripts/generate-openapi.sh

openapi-check:
	bash scripts/generate-openapi.sh --check

openapi-diff:
	bash scripts/generate-openapi.sh --diff

# 帮助
help:
	@echo '天链V3 开发/部署命令'
	@echo ''
	@echo '  make dev         - 启动前端开发服务器'
	@echo '  make build       - 构建前端'
	@echo '  make backend     - 启动后端开发服务器'
	@echo '  make deploy      - 一键构建+部署到云服务器 (带健康检查/自动回滚)'
	@echo '  make deploy-dry  - 仅构建不上传 (dry-run)'
	@echo '  make deploy-ci   - CI/CD部署 (需指定 BRANCH=xxx)'
	@echo '  make test        - 运行后端pytest测试 (conftest.py自动处理import)'
	@echo '  make test-quiet  - 快速运行测试(简要输出)'
	@echo '  make test-cov    - 运行测试+覆盖率报告'
	@echo '  make db-migrate  - 数据库迁移 (备份+索引创建+验证)'
	@echo '  make db-migrate-dry - 仅预览数据库迁移操作'
	@echo '  make check       - TypeScript类型检查'
	@echo '  make lint        - ESLint检查'
	@echo '  make changelog       - 生成完整 CHANGELOG.md'
	@echo '  make changelog-latest - 仅生成最近版本变更'
	@echo '  make changelog-dry   - 预览 changelog (不写入文件)'
	@echo '  make openapi         - 生成 OpenAPI 文档 (需后端依赖)'
	@echo '  make openapi-check   - 检查 OpenAPI 文档是否一致'
	@echo '  make openapi-diff    - 生成 OpenAPI 文档变更报告'
	@echo '  make backup-db   - 备份数据库文件'
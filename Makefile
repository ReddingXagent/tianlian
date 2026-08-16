# 天链V3 边缘网关 — 开发快捷命令
.PHONY: venv install run test lint coverage check deploy-names-check deploy-endpoints-check api-port-check env-keys-check log-paths-check data-paths-check entry-file-check health-probes-check python-version-check template-render-check backup-restore-check pid-file-check start-interpreter-check env-file-check compile-check clean deploy deploy-rollback deploy-restore-db systemd-install systemd-start systemd-stop systemd-status systemd-restart systemd-logs docker-build docker-up docker-down docker-logs docker-shell

VENV=.venv
PYTHON=$(VENV)/bin/python

venv:
	python3 -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install -r requirements.txt

run:
	$(PYTHON) main.py

test:
	$(VENV)/bin/pytest -x -q --timeout=30

# F1232: coverage门禁固化 — F1231定版生产代码100%基线(1627 stmts全绿)
# 限定生产模块(--cov=...), tests/目录不进分母; --cov-fail-under=100防倒退
coverage:
	$(VENV)/bin/pytest -q --timeout=120 --cov=main.py --cov=config.py --cov=db_migration.py \
	--cov=adapters --cov=api --cov=models --cov=storage \
	--cov-fail-under=100 --cov-report=term-missing

lint:
	$(VENV)/bin/ruff check .

check: deploy-names-check deploy-endpoints-check api-port-check env-keys-check log-paths-check data-paths-check entry-file-check health-probes-check python-version-check template-render-check backup-restore-check pid-file-check start-interpreter-check env-file-check compile-check lint test

# F236: 部署同名源一致性守卫(unit三源/logrotate双源对账, 防SYSTEMD_MODE探测失配)
deploy-names-check:
	@bash scripts/check-deploy-names.sh

# F243: 部署探测端点一致性守卫(deploy.sh探测路径↔api/server.py路由声明对账)
deploy-endpoints-check:
	@bash scripts/check-deploy-endpoints.sh

# F249: API端口多源一致性守卫(config.py声明侧↔deploy.sh/compose/Dockerfile探测发布侧对账)
api-port-check:
	@bash scripts/check-api-port.sh

# F255: 环境变量键名双源一致性守卫(config.py os.getenv读取侧↔.env.example模板侧对账)
env-keys-check:
	@bash scripts/check-env-keys.sh

# F261: 日志路径漂移守卫(logrotate轮转目标↔写侧声明三源对账; F341扩全域字面量写读点扫描)
log-paths-check:
	@bash scripts/check-log-paths.sh

# F267: 数据持久化路径多源一致性守卫(config.py db_path声明↔Dockerfile VOLUME/compose挂载/deploy.sh备份glob对账)
data-paths-check:
	@bash scripts/check-data-paths.sh

# F273: 入口文件多源一致性守卫(unit/Dockerfile/Makefile/watchdog/deploy.sh启动与探测/pgrep匹配模式对账)
entry-file-check:
	@bash scripts/check-entry-file.sh

# F280: 健康探测路径多源一致性守卫(deploy.sh/watchdog/Dockerfile HEALTHCHECK探测路径↔server.py路由声明对账)
health-probes-check:
	@bash scripts/check-health-probes.sh

# F287: Python版本多源一致性守卫(ci.yml/Dockerfile/pyproject target/deploy.sh执行+提示/DEPLOYMENT.md/README.md对账)
python-version-check:
	@bash scripts/check-python-version.sh

# F295: 部署模板渲染路径一致性守卫(Makefile sed模式↔unit/logrotate模板路径字面量对账, 堵静默no-op)
template-render-check:
	@bash scripts/check-template-render.sh

# F301: 备份写读对账守卫(备份写模式↔回滚/保留读glob双向匹配+DB_FILE↔config.py db_path, 堵回滚现场无备份可用)
backup-restore-check:
	@bash scripts/check-backup-restore.sh

# F308: pid文件写读对账守卫(deploy.sh写读↔watchdog PID_FILE四源同名+目录段同基准, 堵pid交接静默失效双启撞端口)
pid-file-check:
	@bash scripts/check-pid-file.sh

# F314: 启动解释器多源对账守卫(deploy.sh/watchdog/systemd unit/Dockerfile四生产源解释器token归一化相等, Makefile dev venv源豁免)
start-interpreter-check:
	@bash scripts/check-start-interpreter.sh

# F326: .env凭据语义多源对账守卫(unit EnvironmentFile无'-'前缀+basename ↔ compose env_file basename ↔ .gitignore精确保护条目)
env-file-check:
	@bash scripts/check-env-file.sh

# F365: 编译检查(CI compileall本地化, Makefile↔ci.yml parity, 本地make check即覆盖CI编译门控)
compile-check:
	$(PYTHON) -m compileall main.py config.py adapters/ api/ models/ storage/ -q

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	rm -f .coverage; \
	rm -rf .pytest_cache

deploy:
	bash deploy.sh

systemd-install:
	@# unit/logrotate模板内路径为Pi默认值, 安装时渲染为当前仓库目录, 防非默认部署路径静默失配(F211)
	@sed "s|/home/tl/tianlian-edge-gateway-v3|$(CURDIR)|g" systemd/tianlian-gateway.service > .tianlian-gateway.service.rendered
	@sed "s|/home/tl/tianlian-edge-gateway-v3|$(CURDIR)|g" systemd/logrotate.conf > .tianlian-gateway.logrotate.rendered
	sudo cp .tianlian-gateway.service.rendered /etc/systemd/system/tianlian-gateway.service
	sudo cp .tianlian-gateway.logrotate.rendered /etc/logrotate.d/tianlian-gateway
	@rm -f .tianlian-gateway.service.rendered .tianlian-gateway.logrotate.rendered
	sudo systemctl daemon-reload
	sudo systemctl enable tianlian-gateway

systemd-start:
	sudo systemctl start tianlian-gateway

systemd-stop:
	sudo systemctl stop tianlian-gateway

systemd-restart:
	sudo systemctl restart tianlian-gateway

systemd-status:
	sudo systemctl status tianlian-gateway

systemd-logs:
	sudo journalctl -u tianlian-gateway -f -n 100

# --- Docker ---
docker-build:
	docker build -t tianlian-edge-gateway:latest .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

docker-shell:
	docker exec -it tianlian-gateway bash

# --- 回滚（委托 deploy.sh rollback，单一源，含 stash 保护） ---
deploy-rollback:
	@echo "⚠️ 回滚到指定版本: REV=目标好版本(revert其后所有提交, 非只撤REV一个)"
	@if [ -z "$(REV)" ]; then echo "❌ 用法: make deploy-rollback REV=<commit-hash>"; git log --oneline -5; exit 1; fi
	@bash deploy.sh rollback "$(REV)"

deploy-restore-db:
	@echo "恢复迁移前数据库备份: BAK=备份文件(缺省用最新一份)"
	@bash deploy.sh restore-db $(BAK)

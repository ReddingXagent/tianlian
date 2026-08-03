# 天链V3 边缘网关 — 开发快捷命令
.PHONY: venv install run test lint check clean deploy deploy-rollback systemd-install systemd-start systemd-stop systemd-status systemd-restart systemd-logs docker-build docker-up docker-down docker-logs docker-shell

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

lint:
	$(VENV)/bin/ruff check .

check: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	rm -f .coverage; \
	rm -rf .pytest_cache

deploy:
	bash deploy.sh

systemd-install:
	sudo cp systemd/tianlian-gateway.service /etc/systemd/system/
	sudo cp systemd/logrotate.conf /etc/logrotate.d/tianlian-gateway
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

# --- 回滚 ---
deploy-rollback:
	@echo "⚠️ 回滚到指定版本: REV=目标好版本(revert其后所有提交, 非只撤REV一个)"
	@git log --oneline -5
	@echo ""
	@echo "指定回滚目标: make deploy-rollback REV=<commit-hash>"
	@if [ -z "$(REV)" ]; then echo "❌ 用法: make deploy-rollback REV=<commit-hash>"; exit 1; fi
	@git rev-parse --verify "$(REV)^{commit}" >/dev/null 2>&1 || { echo "❌ 无效commit: $(REV)"; exit 1; }
	@N=$$(git rev-list --count $(REV)..HEAD); \
	if [ "$$N" -eq 0 ]; then echo "ℹ️ REV就是当前HEAD, 无需回滚"; exit 0; fi; \
	echo "revert其后 $$N 个提交:"; git rev-list --oneline $(REV)..HEAD; \
	git revert --no-commit $(REV)..HEAD || { echo "❌ revert冲突, 已自动中止"; git revert --abort; exit 1; }; \
	echo "已revert, 工作区=REV状态; bash deploy.sh 验证后 git commit 并 push"

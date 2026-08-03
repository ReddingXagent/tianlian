# DEPLOYMENT.md — 天链V3 边缘网关部署运行手册

生产环境: 树莓派 `192.168.31.10`（user=tl），仓库目录 `/home/tl/tianlian-edge-gateway-v3`，端口 `8080`。

## 部署方式对比

| 方式 | 命令 | 适用场景 | 现状 |
|------|------|----------|------|
| **deploy.sh 裸跑** | `bash deploy.sh` | Pi 生产现状，nohup + gateway.log | ✅ 生产在用 |
| **systemd** | `make systemd-install` | 开机自启 + journal 日志 | ✅ 可选升级 |
| **Docker** | `docker compose up -d` | 容器化/多机复制 | ✅ 镜像未在生产验证 |

## 方式一: deploy.sh（生产现状）

```bash
cd /home/tl/tianlian-edge-gateway-v3
bash deploy.sh              # 一键部署(git同步→装依赖→杀旧→等端口→启动→健康轮询)
bash deploy.sh status       # PID/健康检查/状态API/日志尾
bash deploy.sh rollback <hash>   # 回滚到hash版本(revert其后全部提交)再重新部署
```

行为要点:
- `.env` 存在即保留（不会覆盖真实 CLOUD_TOKEN），缺失才生成模板
- Pi→NAS 无免密时 git fetch 自动降级为部署当前代码（不阻塞）
- 杀旧进程后等待 8080 端口释放（最多 10s），启动后健康轮询最多 15s，失败自动重试 1 次
- 进程启动/匹配统一用绝对路径（`$REPO_DIR/main.py`）：pgrep 精确命中本网关，`status` 不会误报其他目录的 main.py
- Python 版本预检：低于 3.10 告警（不阻断，兼容老环境）
- `rollback <hash>` = 回滚到 hash 这个好版本：revert 其后全部提交（非只撤 hash 一个），工作区即 hash 状态；无效commit/REV即HEAD/revert冲突（自动abort）均有防护
- 回滚前未提交改动自动 stash 保护：失败时自动 `git stash pop` 真正恢复现场；成功时保留在 `stash@{0}` 并提示（可手动 pop 找回）
- 回滚范围含 merge commit 时 revert 会失败（需 `-m`）→ 自动中止并提示手动逐段 `git revert -m 1 <merge-hash>`
- `make deploy-rollback REV=<hash>` 委托 `deploy.sh rollback`（单一源，防护一致）
- 日志: `gateway.log`（仓库根），PID: `.pid`

## 方式二: systemd

```bash
make systemd-install        # 复制 unit + logrotate + enable
make systemd-start|stop|restart|status|logs
```

⚠️ **踩坑记录（勿回退）**: unit 里 **禁止 `ProtectHome=read-only`** — SQLite DB (`data/gateway.db`) 在 `/home` 下，只读 /home 会导致 `attempt to write a readonly database` 全面写库失败。unit 已置 `ProtectHome=false` 并留注释。

详见 `systemd/README.md`。唯一 unit 源为 `systemd/tianlian-gateway.service`（根目录旧版 `tianlian-edge-gateway.service` 已移除 — 无安全加固且 Restart=on-failure+StartLimit 崩溃3次后不再拉起，误装会导致网关永久下线）。

## 方式三: Docker

```bash
make docker-build           # 本地构建镜像
make docker-up              # compose 启动(--build)
make docker-logs / docker-down / docker-shell
# 多架构: docker buildx build --platform linux/arm64,linux/amd64
```

要点: 数据卷 `gateway-data` 持久化 SQLite；HEALTHCHECK 每 30s 探 `/health`；非 root 运行；时区挂载 Asia/Shanghai。

## 守护与观测

- **watchdog**（无 systemd 时）: `crontab -e` → `*/2 * * * * /home/tl/tianlian-edge-gateway-v3/scripts/watchdog.sh`
  健康检查失败→进程死则重启，卡死则 kill 重启，连续 3 次失败告警放弃本轮。
  （修复记录: REPO_DIR 曾误指向 scripts/ 导致 pgrep 永不匹配，已改为仓库根）
- **健康检查**: `curl http://<pi>:8080/health` → 200
- **状态 API**: `curl http://<pi>:8080/api/v1/status`

## 部署前门禁

```bash
make check                  # ruff lint + pytest(本地)
```
GitHub Actions CI 对每次 push 把关: lint+compile+test+coverage ‖ **Docker镜像构建+容器内import冒烟**（docker job，验证Dockerfile/依赖可成镜像，不推送）。

## 已知问题 / 备忘

- Pi→NAS 无免密 fetch → deploy.sh 设计内降级；Pi 端代码可能落后（需人工 pull 或配免密）
- CLOUD_TOKEN 由云端（大圣 tianlian-v3）签发，当前长期 token 存 Pi `.env`，勿提交入库
- 云端 pod API 曾现 403 "Invalid pod secret" → 云端侧问题，找大圣排查

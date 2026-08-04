# TianLian Edge Gateway — systemd 部署

## 安装 systemd 服务（树莓派上执行）

```bash
# 推荐: 一条命令安装 unit + logrotate, 路径自动渲染为当前仓库目录(F211)
make systemd-install

# 启动服务
sudo systemctl start tianlian-gateway

# 查看状态
sudo systemctl status tianlian-gateway
```

> 模板文件内的 `/home/tl/tianlian-edge-gateway-v3` 是 Pi 默认路径；
> `make systemd-install` 安装时会 sed 渲染为当前仓库目录，无需手改。
> 手动安装（不推荐，需自行改路径）: `sudo cp systemd/tianlian-gateway.service /etc/systemd/system/`
> 后 `sudo nano` 修改 WorkingDirectory/EnvironmentFile 为实际路径，再 daemon-reload + enable。

## 常用命令

| 操作 | 命令 |
|------|------|
| 启动 | `sudo systemctl start tianlian-gateway` |
| 停止 | `sudo systemctl stop tianlian-gateway` |
| 重启 | `sudo systemctl restart tianlian-gateway` |
| 状态 | `sudo systemctl status tianlian-gateway` |
| 日志 | `sudo journalctl -u tianlian-gateway -f` |
| 最近100行 | `sudo journalctl -u tianlian-gateway -n 100` |

## 配置说明

- **Type=simple**: main.py 是前台进程，符合 simple 类型
- **Restart=always + RestartSec=5**: 崩溃后 5 秒自动重启
- **EnvironmentFile**: 从 .env 加载环境变量（CLOUD_TOKEN 等）
- **NoNewPrivileges + ProtectSystem**: 安全加固，限制写权限
- **network-online.target**: 确保网络就绪后再启动

## 从 deploy.sh 迁移

如果之前用 deploy.sh 部署：
1. 先停旧进程: `kill $(cat .pid)` 或 `pkill -f main.py`
2. 确认端口释放: `ss -tlnp | grep 8080`
3. 按上面步骤安装 systemd 服务
4. 验证: `curl http://localhost:8080/health`

deploy.sh 仍保留，适合首次部署和调试使用。systemd 适合日常稳定运行。

# 天链 V2 Nginx 网关配置说明

## 目录结构

```
deploy/nginx/
├── gateway.conf      # 多Pod路由配置模板
└── README.md         # 本说明文档
```

## 配置说明

### 1. Upstream 定义

每个 Pod 定义为一个 upstream：

```nginx
upstream pod-default {
    server demo.example.com:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}
```

参数说明：
- `max_fails=3`: 3次失败后标记为不可用
- `fail_timeout=30s`: 30秒后重新尝试
- `keepalive=32`: 保持32个长连接

### 2. 区域路由规则

通过 `X-Region-ID` header 路由到对应 Pod：

```nginx
set $backend "pod-default";

if ($http_x_region_id = "south-china") {
    set $backend "pod-south";
}
```

客户端请求时需带上 header：

```bash
curl -H "X-Region-ID: south-china" https://api.tianlian.com/api/v1/stations
```

### 3. WebSocket 路由

WebSocket 使用相同路由规则，但需要特殊配置：

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

超时设置为 3600秒（1小时），支持长连接。

### 4. 内部通信

`/internal/` 路径仅允许内网访问，用于 Pod 间内部调用：

```nginx
allow 10.0.0.0/8;
allow 172.16.0.0/12;
deny all;
```

## 部署步骤

### 1. 安装 Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS
sudo yum install nginx
```

### 2. 复制配置文件

```bash
# 复制配置到 Nginx 目录
sudo cp deploy/nginx/gateway.conf /etc/nginx/sites-available/tianlian-gateway

# 创建软链接启用
sudo ln -s /etc/nginx/sites-available/tianlian-gateway /etc/nginx/sites-enabled/

# 移除默认配置（可选）
sudo rm /etc/nginx/sites-enabled/default
```

### 3. 测试配置

```bash
# 测试语法
sudo nginx -t

# 重载配置
sudo nginx -s reload
```

### 4. 验证路由

```bash
# 默认区域
curl -I http://api.tianlian.com/api/v1/pod/health

# 华南区域（需要配置真实 Pod）
curl -H "X-Region-ID: south-china" -I http://api.tianlian.com/api/v1/pod/health
```

## 多 Pod 扩展

### 添加新区域 Pod

1. 在 `gateway.conf` 添加 upstream：

```nginx
upstream pod-southwest {
    server 10.0.4.1:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}
```

2. 添加路由规则：

```nginx
if ($http_x_region_id = "southwest-china") {
    set $backend "pod-southwest";
}
```

3. 重载 Nginx：

```bash
sudo nginx -s reload
```

### 备用 Pod 配置

支持主备模式：

```nginx
upstream pod-south {
    server 10.0.1.1:8000 max_fails=3 fail_timeout=30s;
    server 10.0.1.2:8000 max_fails=3 fail_timeout=30s backup;
    keepalive 32;
}
```

`backup` 标记的 Pod 仅在主 Pod 不可用时启用。

## 健康检查

### 被动检查（默认）

Nginx 自动检测 upstream 失败：
- 连接失败、超时、5xx 错误计入 `max_fails`
- 达到 `max_fails` 后暂停 `fail_timeout` 时间

### 主动检查（需要模块）

安装 `nginx-upstream-check-module`：

```nginx
upstream pod-default {
    server demo.example.com:8000;
    check interval=3000 rise=2 fall=3 timeout=1000 type=http;
    check_http_send "GET /api/v1/pod/health HTTP/1.0\r\n\r\n";
    check_http_expect_alive http_2xx http_3xx;
}
```

参数说明：
- `interval=3000`: 每3秒检查一次
- `rise=2`: 2次成功后标记为健康
- `fall=3`: 3次失败后标记为不健康

## HTTPS 配置

### 1. 获取证书

使用 Let's Encrypt：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.tianlian.com
```

### 2. 手动配置

```nginx
server {
    listen 443 ssl http2;
    server_name api.tianlian.com;
    
    ssl_certificate /etc/nginx/ssl/tianlian.crt;
    ssl_certificate_key /etc/nginx/ssl/tianlian.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
}
```

## 监控与日志

### 日志位置

- 访问日志: `/var/log/nginx/tianlian-access.log`
- 错误日志: `/var/log/nginx/tianlian-error.log`

### 日志格式

自定义格式包含 region 和 pod 信息：

```nginx
log_format tianlian '$remote_addr - $remote_user [$time_local] '
                     '"$request" $status $body_bytes_sent '
                     '"$http_referer" "$http_user_agent" '
                     'region=$http_x_region_id pod=$upstream_addr';
```

### Prometheus 监控

可使用 `nginx-prometheus-exporter` 导出指标：

```bash
docker run -d --name nginx-exporter \
    -p 9113:9113 \
    nginx/nginx-prometheus-exporter:latest \
    -nginx.scrape-uri=http://nginx:8080/stub_status
```

需要在 Nginx 配置中启用 stub_status：

```nginx
location /nginx_status {
    stub_status on;
    allow 127.0.0.1;
    deny all;
}
```

## 故障排查

### 常见问题

1. **路由不生效**
   - 检查 header 是否正确传递
   - 检查 upstream 是否定义

2. **Pod 连接失败**
   - 检查 Pod 是否启动
   - 检查防火墙规则
   - 检查端口是否监听

3. **WebSocket 断开**
   - 检查超时配置
   - 检查 Connection header

### 调试命令

```bash
# 查看 upstream 状态
curl http://localhost/nginx_status

# 查看 Nginx 错误日志
tail -f /var/log/nginx/tianlian-error.log

# 测试特定路由
curl -H "X-Region-ID: south-china" -v http://api.tianlian.com/api/v1/pod/health
```

## 性能调优

### 连接池

使用 `keepalive` 保持长连接：

```nginx
upstream pod-default {
    server demo.example.com:8000;
    keepalive 32;  # 根据并发量调整
}
```

### 缓冲

```nginx
proxy_buffering on;
proxy_buffer_size 4k;
proxy_buffers 8 16k;
proxy_busy_buffers_size 32k;
```

### 超时

根据业务调整：

```nginx
proxy_connect_timeout 10s;   # 连接超时
proxy_send_timeout 60s;      # 发送超时
proxy_read_timeout 60s;      # 读取超时
```

## 安全配置

### 限制访问

```nginx
# 仅允许特定 IP
allow 10.0.0.0/8;
deny all;
```

### 防止 SSRF

```nginx
# 禁止访问私有 IP
resolver 8.8.8.8;
set $upstream_host $host;
proxy_pass http://$upstream_host;
```

### Rate Limiting

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

location /api/v1/ {
    limit_req zone=api_limit burst=20 nodelay;
    # ...
}
```

## 版本信息

- Nginx 版本: 1.18+ (推荐 1.24+)
- 支持特性: HTTP/1.1, WebSocket, SSL/TLS, Upstream

## 相关文档

- [Nginx 官方文档](https://nginx.org/en/docs/)
- [Upstream 模块](https://nginx.org/en/docs/http/ngx_http_upstream_module.html)
- [Proxy 模块](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
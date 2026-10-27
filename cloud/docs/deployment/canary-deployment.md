# 生产环境灰度发布策略

## 概述

天链V3 支持灰度发布，可在不影响全部用户的情况下验证新版本。

## 灰度策略

### 1. 基于权重的流量分配

```nginx
# Nginx 配置示例
upstream stable {
    server 127.0.0.1:8000;
}

upstream canary {
    server 127.0.0.1:8001;
}

split_clients "${remote_addr}" $variant {
    95%     stable;
    *       canary;
}

server {
    location /api/ {
        proxy_pass http://$variant;
    }
}
```

### 2. 基于用户特征的灰度

```python
# 后端灰度判断逻辑
def is_canary_user(user_id: int, canary_percentage: int = 5) -> bool:
    """基于用户ID哈希判断是否灰度用户"""
    import hashlib
    hash_val = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
    return hash_val % 100 < canary_percentage
```

### 3. 基于 Header 的灰度

```nginx
# 特定Header进入灰度
map $http_x_canary_version $upstream {
    default stable;
    "v2"    canary;
}
```

## 实施步骤

### 阶段1: 准备灰度环境

```bash
# 1. 部署灰度版本到独立端口
docker run -d --name tianlian-canary \
  -p 8001:8000 \
  -e DATABASE_URL=postgresql://... \
  -e FEATURE_FLAG=canary \
  tianlian:v2.0.0-canary

# 2. 配置 Nginx 灰度规则
sudo nginx -t && sudo nginx -s reload
```

### 阶段2: 灰度发布流程

| 阶段 | 灰度比例 | 持续时间 | 检查项 |
|------|---------|---------|--------|
| 内测 | 1% | 2小时 | 错误率、延迟 |
| 小流量 | 5% | 24小时 | 核心业务指标 |
| 中流量 | 20% | 48小时 | 用户反馈 |
| 大流量 | 50% | 24小时 | 全量监控 |
| 全量 | 100% | - | 稳定运行 |

### 阶段3: 监控指标

```yaml
# 灰度监控指标
metrics:
  - error_rate: < 0.1%
  - p99_latency: < 500ms
  - success_rate: > 99.9%
  - business_kpi: 无异常波动
```

### 阶段4: 回滚策略

```bash
# 快速回滚脚本
#!/bin/bash
# rollback.sh

# 1. 停止灰度流量
echo "停止灰度流量..."
sudo sed -i 's/canary/stable/g' /etc/nginx/conf.d/canary.conf
sudo nginx -s reload

# 2. 验证稳定版本
sleep 5
curl -sf http://localhost/api/v1/health || exit 1

# 3. 停止灰度容器
docker stop tianlian-canary
docker rm tianlian-canary

echo "回滚完成"
```

## 配置管理

### 数据库灰度配置

```python
# app/core/canary.py
from pydantic import BaseSettings

class CanaryConfig(BaseSettings):
    ENABLE_CANARY: bool = False
    CANARY_PERCENTAGE: int = 0  # 0-100
    CANARY_VERSION: str = "v2.0.0"
    CANARY_FEATURES: list = []
    
    # 白名单用户 (强制进入灰度)
    CANARY_WHITELIST: list = []
    
    # 黑名单用户 (强制不进灰度)
    CANARY_BLACKLIST: []
```

### 动态调整灰度比例

```bash
# 通过 API 动态调整
curl -X POST http://admin-api/api/v1/canary/config \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "canary_percentage": 10,
    "canary_version": "v2.0.0"
  }'
```

## 当前实施状态

- [x] 灰度策略文档
- [ ] Nginx 配置部署
- [ ] 灰度环境搭建
- [ ] 监控告警配置
- [ ] 自动化回滚脚本

## 注意事项

1. **数据库兼容性**: 灰度版本需兼容当前数据库结构
2. **Session 共享**: 灰度和稳定版本需共享 Session
3. **缓存一致性**: Redis 缓存需兼容新旧版本
4. **日志分离**: 灰度版本日志需单独收集分析

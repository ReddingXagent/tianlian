# WebSocket 端点标准化方案

## 背景
天链V3系统现有多个WebSocket端点，路径不统一，前端连接方式不一致。为提升可维护性和实时通信质量，需要标准化WebSocket架构。

## 现状分析

### 后端端点 (3个独立文件)
1. **`/api/v1/ws/realtime`** - `websocket.py`
   - 通用实时数据推送
   - 基本连接管理

2. **`/api/v1/ws/digital-twin`** - `websocket_digital_twin.py`
   - 数字孪生专用
   - 站级/设备级订阅
   - 复杂连接管理

3. **`/api/v1/ws/dashboard`** - 疑似缺失
   - 前端Dashboard页面使用

### 前端连接问题
- 硬编码地址: `ws://localhost:8000/api/v1/ws/dashboard`
- 缺少生产/开发环境切换
- 错误处理和重连策略不一致

### 移动端
- React Native WebSocket实现需检查
- 与Web端共享连接策略

## 标准化目标

### 1. 统一路由前缀
```
旧: /api/v1/ws/*
新: /ws/v1/*

理由:
- WebSocket与REST API解耦
- 简化Nginx代理配置
- 便于监控和日志分离
```

### 2. 统一连接管理器
- 合并三个WebSocket实现
- 统一连接状态管理
- 统一消息格式

### 3. 环境配置
- 开发: `ws://localhost:8000/ws/v1/...`
- 生产: `wss://demo.example.com/ws/v1/...`
- 环境变量控制

### 4. 消息协议标准化
```json
{
  "type": "connected|data|error|heartbeat",
  "channel": "realtime|digital_twin|alerts|workorders",
  "payload": {},
  "timestamp": "ISO8601",
  "id": "optional-message-id"
}
```

## 实施步骤

### Phase 1: 后端重构
1. 创建统一WebSocket路由模块 `backend/app/ws/`
2. 迁移现有三个端点到统一模块
3. 更新路由前缀到 `/ws/v1/`
4. 统一连接管理器和消息格式

### Phase 2: 前端适配
1. 更新 `useWebSocket` Hook支持新地址
2. 环境变量配置WebSocket基础URL
3. 更新Dashboard等页面连接地址
4. 统一错误处理和重连逻辑

### Phase 3: 移动端适配
1. 检查React Native WebSocket实现
2. 与环境变量集成
3. 测试连接稳定性

### Phase 4: 部署更新
1. Nginx配置更新WebSocket代理
2. 后端重启验证
3. 全链路测试

## 技术细节

### 后端实现要点
```python
# backend/app/ws/__init__.py
class WebSocketManager:
    """统一WebSocket连接管理器"""
    
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {
            'realtime': [],
            'digital_twin': [],
            'alerts': [],
            'workorders': []
        }
        self.subscriptions: Dict[str, Dict[str, Set[WebSocket]]] = {}
    
    async def connect(self, websocket: WebSocket, channel: str):
        """连接特定频道"""
        pass
    
    async def broadcast(self, channel: str, message: dict):
        """广播到频道"""
        pass

# 路由注册
router = APIRouter(prefix="/ws/v1")
```

### 前端配置
```typescript
// frontend/.env
VITE_WS_BASE_URL=ws://localhost:8000/ws/v1

// frontend/src/config/ws.ts
export const WS_CONFIG = {
  baseUrl: import.meta.env.VITE_WS_BASE_URL,
  reconnectInterval: 3000,
  maxReconnectAttempts: 5,
  heartbeatInterval: 30000
} as const;
```

### Nginx配置更新
```nginx
# 新增WebSocket路由
location /ws/v1/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "Upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

## 测试计划

### 功能测试
1. ✅ 连接建立和断开
2. ✅ 多频道订阅/取消订阅
3. ✅ 消息发送和接收
4. ✅ 错误处理和重连

### 性能测试
1. ✅ 并发连接数 (目标: 500+)
2. ✅ 消息延迟 (目标: <100ms)
3. ✅ 内存和CPU使用率

### 集成测试
1. ✅ 前端页面集成测试
2. ✅ 移动端集成测试
3. ✅ 生产部署测试

## 回滚方案

1. 保留旧路由 `/api/v1/ws/*` 一段时间
2. 双路由并行，逐步迁移
3. 出现问题可快速回退

## 时间估算

| 阶段 | 时间 | 负责人 |
|------|------|--------|
| Phase 1: 后端重构 | 2天 | 石猴 |
| Phase 2: 前端适配 | 1天 | 石猴 |
| Phase 3: 移动端适配 | 1天 | 石猴 |
| Phase 4: 部署测试 | 0.5天 | 大圣 |
| **总计** | **4.5天** | |

## 成功标准

1. ✅ 所有WebSocket端点使用统一前缀 `/ws/v1/`
2. ✅ 前后端连接稳定，无硬编码地址
3. ✅ 错误处理和重连机制统一
4. ✅ 生产环境WebSocket连接正常
5. ✅ 性能指标达标（延迟<100ms，并发500+）

---

**更新历史**:
- 2026-05-25: 创建标准化方案文档
- 2026-05-25: 开始实施Phase 1
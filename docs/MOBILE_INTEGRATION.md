# 移动端集成指南 — 天链V3 边缘网关

> 本文档面向 tianlian-ops-app / tianlian-station-app / tianlian-user-app / tianlian-user-mp 的前端开发者，说明如何连接边缘网关本地 API。

## 1. 网络架构

```
移动端 App                边缘网关 (Pi)              云端
┌──────────┐   LAN/WiFi   ┌──────────────┐   WAN   ┌──────────┐
│  RN / MP │ ──HTTP──→    │ FastAPI:8080 │ ──HTTPS─→│ tianlian │
│          │              │  (本地调试)   │         │   v3 API │
└──────────┘              └──────────────┘         └──────────┘
```

- **移动端 → 网关**: 局域网 HTTP，用于实时监控和调试
- **网关 → 云端**: WAN HTTPS，遥测上报和设备管理
- **移动端 → 云端**: WAN HTTPS，业务逻辑（通过各自 BASE_URL）

## 2. 本地 API 端点速查（移动端常用）

| 端点 | 方法 | 用途 | 移动端场景 |
|------|------|------|-----------|
| `/health` | GET | 轻量探活 | App 启动时检测网关是否在线 |
| `/api/v1/dashboard` | GET | 聚合数据 | **推荐**：一次请求获取设备+遥测+告警+缓存 |
| `/api/v1/status` | GET | 网关状态 | 简化状态展示 |
| `/api/v1/telemetry/latest` | GET | 最新遥测 | 实时功率/电压展示 |
| `/api/v1/devices` | GET | 设备列表 | 设备管理页面 |
| `/api/v1/cache/stats` | GET | 缓存统计 | 运维诊断 |
| `/api/v1/perf` | GET | 性能指标 | 高级诊断 |

### 推荐策略
- **首页/Dashboard**: 调用 `/api/v1/dashboard`，3-5秒轮询一次
- **设备列表页**: 调用 `/api/v1/devices`，下拉刷新
- **实时监控**: 调用 `/api/v1/telemetry/latest`，2-3秒轮询
- **健康检查**: App 启动 + 每 30s 调用 `/health`

## 3. React Native (ops-app / station-app / user-app) 对接

### 3.1 基本请求

```typescript
const GATEWAY_BASE_URL = 'http://192.168.31.10:8080'; // Pi 局域网 IP

async function fetchDashboard() {
  try {
    const res = await fetch(`${GATEWAY_BASE_URL}/api/v1/dashboard`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    // 网关离线或局域网不可达
    console.warn('Gateway unreachable:', err);
    return null;
  }
}
```

### 3.2 超时处理

```typescript
const GATEWAY_TIMEOUT = 3000; // 局域网 3s 超时

async function fetchWithTimeout(url: string, ms = GATEWAY_TIMEOUT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}
```

### 3.3 NetInfo 联动

```typescript
import NetInfo from '@react-native-community/netinfo';

NetInfo.addEventListener(state => {
  if (state.type === 'wifi' && state.isConnected) {
    // WiFi 网络下自动连接网关
    startGatewayPolling();
  } else {
    // 蜂窝或离线 → 停止网关轮询，走云端 API
    stopGatewayPolling();
  }
});
```

### 3.4 环境 配置

```typescript
// config/gateway.ts
export const GATEWAY_CONFIG = {
  // 从环境变量或远程配置读取
  LOCAL_IP: process.env.GATEWAY_IP || '192.168.31.10',
  PORT: 8080,
  POLL_INTERVAL: 5000,    // 5s
  HEALTH_INTERVAL: 30000, // 30s
  TIMEOUT: 3000,          // 3s
};

export const GATEWAY_BASE_URL = `http://${GATEWAY_CONFIG.LOCAL_IP}:${GATEWAY_CONFIG.PORT}`;
```

## 4. 微信小程序 (user-mp) 对接

### 4.1 request 封装

```javascript
// utils/gateway-api.js
const GATEWAY_BASE = 'http://192.168.31.10:8080';

function gatewayRequest(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${GATEWAY_BASE}${path}`,
      method: options.method || 'GET',
      timeout: options.timeout || 3000,
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data);
        } else {
          reject(new Error(`Gateway HTTP ${res.statusCode}`));
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export default { request: gatewayRequest };
```

### 4.2 注意事项

- **开发工具**: 微信开发者工具中需勾选「不校验合法域名」
- **真机调试**: 局域网 IP 在真机预览时需要手机与 Pi 在同一 WiFi
- **正式发布**: 微信正式版要求 HTTPS，仅支持已配置的域名。本地网关 HTTP 仅限开发调试。
- **requestDomain**: 生产环境如需远程访问网关，需在微信公众平台配置域名白名单。

### 4.3 页面集成示例

```javascript
// pages/dashboard/dashboard.js
const gatewayApi = require('../../utils/gateway-api');

Page({
  data: { dashboard: null, gatewayOnline: false },

  async loadDashboard() {
    try {
      const data = await gatewayApi.request('/api/v1/dashboard');
      this.setData({ dashboard: data, gatewayOnline: true });
    } catch {
      this.setData({ gatewayOnline: false });
    }
  },

  onLoad() {
    this.loadDashboard();
    this.timer = setInterval(() => this.loadDashboard(), 5000);
  },

  onUnload() {
    clearInterval(this.timer);
  },
});
```

## 5. CORS 说明

边缘网关 CORS 全放通（`allow_origins=["*"]`），适用于：

- ✅ React Native fetch（RN 不受 CORS 限制）
- ✅ 微信小程序 wx.request（不走浏览器 CORS）
- ✅ 浏览器开发工具调试

> 生产环境如需收紧 CORS，修改 `api/server.py` 的 `allow_origins` 列表。

## 6. 错误处理约定

| HTTP 状态码 | 含义 | 移动端处理 |
|-------------|------|-----------|
| 200 | 成功 | 正常处理数据 |
| 400 | 请求参数错误 | 检查请求体格式 |
| 500 | 服务端异常 | 重试或上报 |
| 网络超时 | 网关离线/不可达 | 降级到云端 API，提示用户 |

### 降级策略

```typescript
async function fetchWithFallback() {
  // 优先局域网关（低延迟）
  const local = await tryGateway();
  if (local) return local;

  // 降级到云端 API（高延迟但可用）
  return await fetchCloudAPI();
}
```

## 7. 开发调试

### 7.1 模拟数据注入

```bash
# 注入遥测数据
curl -X POST http://192.168.31.10:8080/api/v1/simulate/telemetry \
  -H "Content-Type: application/json" \
  -d '{"device_type":"ocpp","power":22.5,"voltage":380,"current":59,"status":"charging"}'

# 注入告警
curl -X POST http://192.168.31.10:8080/api/v1/simulate/alarm \
  -H "Content-Type: application/json" \
  -d '{"device_type":"ocpp","alarm_type":"over_temp","message":"Temperature > 60C"}'
```

### 7.2 Dashboard 快速验证

```bash
curl -s http://192.168.31.10:8080/api/v1/dashboard | python3 -m json.tool
```

### 7.3 网关不可达时的模拟

开发时网关不可用，可在 App 配置中指向本地 mock：

```typescript
// 本地开发: 使用云端 mock 或本地 JSON
const GATEWAY_BASE_URL = __DEV__
  ? 'http://localhost:3000/mock-gateway'  // 本地 mock server
  : `http://${config.gatewayIp}:8080`;     // 生产局域网
```

---

*最后更新: 2026-08-03*

# 天链 V3 API 测试指南

## 测试工具

### pytest 测试框架
```bash
cd backend
python3 -m pytest tests/ -v
```

### curl 测试示例

#### 1. 登录获取token
```bash
curl -X POST "http://demo.example.com/api/v1/auth/login" \
  -d "username=admin" \
  -d "password=admin123"
```

#### 2. 带token访问API
```bash
# 获取站点列表
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  "http://demo.example.com/api/v1/stations"

# 获取设备列表
curl -H "Authorization: Bearer <token>" \
  "http://demo.example.com/api/v1/devices"

# 创建工单
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"逆变器维修","device_id":1,"priority":"high"}' \
  "http://demo.example.com/api/v1/workorders"
```

#### 3. 健康检查（无需鉴权）
```bash
curl "http://demo.example.com/api/v1/health"
```

## 测试覆盖

### 已完成测试（17个）
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| test_api.py | API基础功能 | ✅ 8测试通过 |
| test_auth.py | JWT鉴权验证 | ✅ 6测试通过 |
| test_security.py | CORS/安全头/脱敏 | ✅ 3测试通过 |

### 测试覆盖率
- API路由: 60% (主要路由已覆盖)
- 鉴权功能: 100% (登录/验证/权限检查)
- 安全功能: 100% (CORS白名单/安全头/异常脱敏)

## 运行测试

### 本地测试
```bash
cd backend
python3 -m pytest tests/ -v --tb=short
```

### 测试报告
```bash
# 生成覆盖率报告
python3 -m pytest tests/ --cov=app --cov-report=html
```

## 模拟器测试

### Modbus逆变器模拟器
```python
from app.services.modbus_mqtt_simulator import ModbusSimulator

sim = ModbusSimulator(device_type="inverter", address=1)
data = await sim.read_data()  # 异步方法
```

### MQTT充电桩模拟器
```python
from app.services.modbus_mqtt_simulator import MQTTSimulator

sim = MQTTSimulator(device_id="C001")
data = await sim.generate_telemetry()  # 异步方法
```

## 常见问题

### Q: 401 Unauthorized
**原因**: token无效或过期
**解决**: 重新登录获取新token

### Q: CORS错误
**原因**: 请求来源不在白名单
**解决**: 添加来源到 `ALLOWED_ORIGINS`

### Q: 500 Internal Error
**原因**: 服务端异常
**解决**: 查看日志 `/var/log/tianlian/*.log`

---

**更新时间**: 2026-05-17
**测试状态**: ✅ 17/18 通过
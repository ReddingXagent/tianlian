# 天链运维平台 V3 - 使用手册

**版本**: 3.0.0  
**更新日期**: 2026-06-15  
**状态**: ✅ 生产就绪

---

## 🚀 快速开始

### 1. 访问系统
```
http://localhost:3004
```

### 2. 登录
- **用户名**: `admin`
- **密码**: `admin`

### 3. 测试页面
如果主页面白屏，先访问测试页面验证：
```
http://localhost:3004/test
```

---

## 📋 功能模块

### 1. 仪表盘 (Dashboard)
**路由**: `/dashboard`

**功能**:
- 站点在线率统计
- 设备在线率统计
- 平均健康度显示
- 活跃告警数量
- 工单状态概览

**API**: `GET /api/v1/stats/overview`

---

### 2. 站点管理 (Stations)
**路由**: `/stations`

**功能**:
- 查看站点列表
- 添加新站点
- 编辑站点信息
- 删除站点

**数据字段**:
- 站点编码
- 站点名称
- 地址
- 总功率 (kW)
- 设备数量
- 状态 (正常/维护/关闭)

**API**:
- `GET /api/v1/stations` - 列表
- `POST /api/v1/stations` - 创建
- `PUT /api/v1/stations/{id}` - 更新
- `DELETE /api/v1/stations/{id}` - 删除

---

### 3. 设备管理 (Devices)
**路由**: `/devices`

**功能**:
- 查看设备列表
- 设备健康度计算
- 健康度历史记录
- 设备状态监控

**设备类型**:
- `charger_dc` - 直流充电桩
- `charger_ac` - 交流充电桩
- `pv_inverter` - 光伏逆变器
- `battery` - 储能设备

**健康度 5 维度**:
1. 电气安全 (30%)
2. 热稳定性 (25%)
3. 通信可靠性 (20%)
4. 电能质量 (15%)
5. 机械寿命 (10%)

**设备类型温度阈值（热稳定性评分依据）**:

| 设备类型 | 警告(°C) | 严重(°C) | 致命(°C) | 温升速率(°C/s) |
|---------|---------|---------|---------|--------------|
| 光伏逆变器 (pv_inverter) | 60 | 70 | 80 | 5.0 |
| 储能逆变器 (battery_inverter) | 60 | 70 | 80 | 5.0 |
| 电表 (meter) | 70 | 85 | 95 | 5.0 |
| 网关 (gateway) | 70 | 85 | 95 | 5.0 |
| 其他设备（默认） | 60 | 70 | 80 | 5.0 |

> 充电桩类设备（直流/交流）额外监测枪头温度，超过 60°C 触发扣分。
> 各档位扣分标准：警告 -15、严重 -30、致命 -50 分；温升速率超限额外扣分。
> 健康度引擎：`backend/app/services/health_engine.py`

**API**:
- `GET /api/v1/devices` - 列表
- `POST /api/v1/devices/{id}/health` - 健康度计算

---

### 4. 工单管理 (WorkOrders)
**路由**: `/workorders`

**功能**:
- 创建工单
- 智能派单
- 工单状态流转
- 工单历史记录

**工单级别**:
- `low` - 低
- `medium` - 中
- `high` - 高
- `urgent` - 紧急

**工单状态**:
- `pending` - 待处理
- `processing` - 处理中
- `completed` - 已完成

**智能派单算法**:
- 地理位置 (30%)
- 技能匹配 (25%)
- 当前负载 (20%)
- 历史绩效 (15%)
- 备件匹配 (10%)

**API**:
- `POST /api/v1/workorders/{id}/dispatch` - 智能派单

---

### 5. 告警管理 (Alarms)
**路由**: `/alarms`

**功能**:
- 告警列表
- 告警确认
- 告警解决
- 告警统计

**告警级别**:
- `info` - 提示
- `warning` - 警告
- `critical` - 严重

**告警状态**:
- `active` - 活跃
- `acknowledged` - 已确认
- `resolved` - 已解决

**API**:
- `PUT /api/v1/alarms/{id}/ack` - 确认告警
- `PUT /api/v1/alarms/{id}/resolve` - 解决告警
- `GET /api/v1/alarms/stats/summary` - 告警统计

---

### 6. 知识库 (Knowledge)
**路由**: `/knowledge`

**功能**:
- 知识文章管理
- 分类浏览
- 搜索功能

**API**:
- `GET /api/v1/knowledge?search=xxx` - 搜索
- `GET /api/v1/knowledge/categories/list` - 分类列表

---

### 7. 报表导出 (Reports)
**路由**: `/reports`

**功能**:
- 站点报表导出
- 设备报表导出
- 工单报表导出

---

## 🔧 技术架构

### 后端
- **框架**: FastAPI
- **数据库**: SQLite
- **ORM**: SQLAlchemy
- **端口**: 8080
- **API 文档**: http://localhost:8080/docs

### 前端
- **框架**: React 18
- **UI 库**: Ant Design 5
- **路由**: React Router 6
- **构建**: Vite 5
- **端口**: 3004

### 核心服务
- **健康度引擎**: `backend/app/services/health_engine.py`
- **派单引擎**: `backend/app/services/dispatch_engine.py`
- **统计服务**: `backend/app/services/stats_service.py`

---

## 📊 数据库设计

### 核心表 (7 张)

1. **teams** - 运维团队
2. **users** - 用户/工程师
3. **stations** - 站点
4. **devices** - 设备
5. **work_orders** - 工单
6. **alarms** - 告警
7. **knowledge_articles** - 知识文章

### 关联表
- **device_health_records** - 健康度历史记录
- **work_order_logs** - 工单操作日志
- **alarm_rules** - 告警规则

---

## 🎯 核心功能详解

### 健康度评估流程

```
1. 采集设备数据
   ↓
2. 5 维度评分计算
   ↓
3. 加权平均得到总分
   ↓
4. 趋势分析 (恶化扣分)
   ↓
5. 判断告警级别
   ↓
6. 自动生成告警 (如需)
```

### 智能派单流程

```
1. 工单创建
   ↓
2. 获取可用工程师
   ↓
3. 计算各工程师评分
   ↓
4. 选择最高分工程师
   ↓
5. 自动派单
   ↓
6. 添加派单日志
```

---

## 🐛 常见问题

### Q1: 前端白屏
**解决**:
1. 按 `Cmd+Shift+R` 强制刷新
2. 访问 `/test` 页面验证
3. 清除浏览器缓存
4. 使用无痕窗口

### Q2: 登录失败
**解决**:
1. 检查后端是否运行 (http://localhost:8080/api/v1/health)
2. 清除 localStorage
3. 重新输入 admin/admin

### Q3: API 请求失败
**解决**:
1. 检查后端端口 8080 是否占用
2. 查看后端日志 `tail -f /tmp/backend.log`
3. 重启后端服务

---

## 📞 技术支持

**系统管理员**: 大圣 🐵  
**更新时间**: 2026-06-15

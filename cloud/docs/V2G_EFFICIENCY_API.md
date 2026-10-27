# 天链V3 新增 V2G+效率 API 文档

云端已部署 (http://demo.example.com)，供移动端适配参考。

---

## 一、设备效率

### GET /api/v1/devices/{device_id}/efficiency
返回单设备的三类效率数据+30天趋势。

```json
{
  "code": 200,
  "data": {
    "device_id": "xxx",
    "utilization": {
      "current": 72.5,
      "trend": [{"date": "2026-07-01", "value": 71.0}, ...]
    },
    "charge_efficiency": {
      "current": 94.2,
      "trend": [...]
    },
    "generation_efficiency": {
      "current": 85.3,
      "pv_pr": 0.82,
      "trend": [...]
    }
  }
}
```

---

## 二、效率报表

| 端点 | 说明 |
|------|------|
| GET /api/v1/reports/utilization | 各站点/类型利用率排名 + 低利用率预警(<30%) + 过载标记(>90%) |
| GET /api/v1/reports/efficiency | 充电效率排名 + 异常低效设备预警 |
| GET /api/v1/reports/generation | 光伏PR性能比排名 + 实际vs理论峰值对比 |
| GET /api/v1/reports/v2g | V2G运营数据(充放电量/调度次数/削峰填谷/收益) |

---

## 三、V2G 调度

### POST /api/v1/devices/{device_id}/v2g/dispatch
下发充放电调度指令

请求体：
```json
{
  "dispatch_type": "charge",
  "target_power_kw": 50.0
}
```
dispatch_type: charge | discharge | standby

响应：
```json
{
  "code": 200,
  "data": {
    "id": "uuid",
    "status": "pending",
    "dispatch_type": "charge",
    "target_power_kw": 50.0
  }
}
```

### GET /api/v1/devices/{device_id}/v2g/dispatch/history
查询调度历史，支持分页 (?page=1&pageSize=20)

---

## 四、移动端适配建议

### 站长APP
- 首页效率概览：调 /reports/utilization /reports/efficiency /reports/generation 聚合三个平均值
- 设备详情效率区：调 /devices/{id}/efficiency
- V2G设备：额外显示充放电模式/功率

### 工程师APP
- V2G设备诊断：GET /devices (筛选 type=v2g_charger) + GET /devices/{id}/efficiency
- V2G调度操作：POST /devices/{id}/v2g/dispatch + GET dispatch/history

---

所有端点需 Header: `Authorization: Bearer <token>`
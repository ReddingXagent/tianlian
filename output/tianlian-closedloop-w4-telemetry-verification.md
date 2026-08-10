# W4 闭环：Telemetry 非空 Payload 真实上报验证

**日期**: 2026-08-11 07:25 (Asia/Shanghai)
**验证人**: 猴王自驱 (F779)
**Token状态**: 有效 (10年长期token, HTTP 200)

## 1. 验证目标

验证 edge-gateway telemetry batch-report 上报链路在非空 payload 下的真实云端行为。

## 2. 测试结果

### 2.1 储能逆变器 (modbus-1 → device_id=1)

**Payload**:
```json
{
  "device_id": 1,
  "grid_voltage_a": 220.5,
  "grid_power_a": 7.0,
  "grid_power_total": 7.0,
  "battery_voltage": 220.5,
  "battery_temperature": 42.3,
  "battery_soc": 85.2,
  "ambient_temperature": 42.3
}
```

**响应**: HTTP 200 ✅
```json
{"code":200,"message":"批量上报成功,共 1 条","data":{"total_received":1,"total_success":1,"stats":{"pv":0,"battery":1,"charger":0,"legacy":0,"errors":[]}}}
```

### 2.2 充电桩 (device_id=6, TL-CHG-240KW-006)

**Payload**:
```json
{
  "device_id": 6,
  "charger_voltage": 400.2,
  "charger_current": 32.0,
  "charger_power": 12.8,
  "charger_soc": 65.0,
  "charger_kwh": 150.5,
  "gun_temperature": 38.2
}
```

**响应**: HTTP 200 ✅
```json
{"code":200,"message":"批量上报成功,共 1 条","data":{"total_received":1,"total_success":1,"stats":{"pv":0,"battery":0,"charger":1,"legacy":0,"errors":[]}}}
```

### 2.3 多设备批量上报

**3条记录**: modbus-1(id=1) + CHARGER-001(id=2) + GW-001(id=0)

**响应**: HTTP 200 (部分成功)
```json
{
  "total_received": 3,
  "total_success": 2,
  "stats": {"pv": 1, "battery": 1, "charger": 0, "errors": ["设备 0 不存在"]}
}
```

**关键发现**: device_id=0 (GW-001) 在云端不存在，被拒。id=2 (TL-INV-3000-002, pv_inverter) 被归类为 pv 而非 charger。

### 2.4 错误格式验证

**空字符串 device_id**: HTTP 422 — `Input should be a valid integer`

## 3. DEVICE_ID_MAP 映射分析

| Edge Gateway 设备 | DEVICE_ID_MAP | 云端实际设备 | 类型匹配 |
|---|---|---|---|
| modbus-1 | → 1 | TL-BAT-100AH-001 (battery_inverter) | ✅ 正确 |
| CHARGER-001 | → 2 | TL-INV-3000-002 (pv_inverter) | ❌ 错误！应为 charger_dc |
| GW-001 | → 0 | (不存在) | ❌ 需注册网关设备 |

### 正确的充电桩映射应为
- CHARGER-001 → device_id=6 (TL-CHG-240KW-006, charger_dc) 或其他 charger_dc 类型设备

### 根因
DEVICE_ID_MAP 硬编码的映射是开发期假设值，与云端实际注册的设备不匹配。生产部署时需要根据实际设备表调整。

## 4. 云端行为总结

| 场景 | HTTP | 结果 |
|---|---|---|
| 非空 records + 有效 device_id | 200 | ✅ 成功计入 |
| 非空 records + 无效 device_id | 200 | ⚠️ 部分成功, errors 列出无效设备 |
| device_id 为字符串 | 422 | ❌ 校验失败 |
| 空数组 records | 500 | ❌ 后端空指针 (已知bug) |

## 5. 待办

- [ ] 修正 DEVICE_ID_MAP: CHARGER-001 → 实际 charger_dc 设备 ID
- [ ] 注册 GW-001 为云端设备或使用已注册设备 ID
- [ ] 考虑将 DEVICE_ID_MAP 改为环境变量配置 (部署灵活)
- [ ] 修复空 records 500 bug (需大圣配合)

## 6. 结论

Telemetry 非空 payload 上报链路 **已验证通畅**。云端正确接收并分类处理 battery/charger/pv 遥测数据。
主要风险是 DEVICE_ID_MAP 映射与生产设备不匹配，需部署时校正。

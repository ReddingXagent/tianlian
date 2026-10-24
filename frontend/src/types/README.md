# TypeScript 类型定义

## 文件说明

### `index.ts`
完整的所有业务实体TypeScript接口定义，包含所有详细的字段和相关的请求/响应接口。

### `core.ts`
精简的核心类型定义，包含最常用的实体和枚举，适合快速导入。

## 使用方法

### 导入完整类型
```typescript
import { User, Device, Alarm, ApiResponse, PaginatedData } from '@/types';
```

### 导入精简类型
```typescript
import { User, Device, DeviceStatus } from '@/types/core';
```

### 类型替换示例

替换前：
```typescript
const user: any = response.data;
```

替换后：
```typescript
import { User } from '@/types';

const user: User = response.data;
```

## 类型层次结构

### 1. 通用类型
- `ApiResponse<T>` - 标准API响应格式
- `PaginatedData<T>` - 分页数据格式
- `PaginatedResponse<T>` - 分页API响应

### 2. 用户相关
- `User` - 用户信息
- `UserRole` - 用户角色枚举
- `LoginResponse` - 登录响应
- `UserCreateRequest` / `UserUpdateRequest` - 创建/更新用户请求

### 3. 站点相关
- `Station` - 站点信息
- `StationStatus` - 站点状态枚举

### 4. 设备相关
- `Device` - 设备信息
- `DeviceType` - 设备类型枚举
- `DeviceStatus` - 设备状态枚举
- `DeviceCreateRequest` / `DeviceUpdateRequest` - 创建/更新设备请求

### 5. 告警相关
- `Alarm` - 告警信息
- `AlarmLevel` - 告警级别枚举
- `AlarmStatus` - 告警状态枚举

### 6. 工单相关
- `WorkOrder` - 工单信息
- `WorkOrderType` - 工单类型枚举
- `WorkOrderStatus` - 工单状态枚举
- `WorkOrderPriority` - 工单优先级枚举

### 7. 统计相关
- `StatsOverview` - 统计数据概览
- `DailyStats` - 每日统计数据

### 8. 运维团队
- `Tenant` - 运维团队（平台管理）信息
- `TenantStatus` - 团队状态枚举

### 9. 知识库
- `KnowledgeArticle` - 知识库文章

### 10. 网关
- `Gateway` - 网关设备信息

## 最佳实践

### 1. 避免使用 `any` 类型
尽量使用具体的接口类型，提高代码可维护性。

### 2. 使用枚举替代字符串常量
```typescript
// 不推荐
const status: string = 'online';

// 推荐
import { DeviceStatus } from '@/types';
const status: DeviceStatus = 'online';
```

### 3. 使用类型别名
```typescript
import { ApiResponse, User } from '@/types';

type UserResponse = ApiResponse<User>;
```

### 4. 组件 Props 类型定义
```typescript
import { Device } from '@/types';

interface DeviceCardProps {
  device: Device;
  onEdit?: (device: Device) => void;
  onDelete?: (deviceId: number) => void;
}
```

## 后续优化

1. **逐步替换**：分模块逐步替换现有代码中的 `any` 类型
2. **类型检查**：启用 TypeScript 严格模式，发现潜在的类型错误
3. **类型生成**：考虑从后端 OpenAPI/Swagger 自动生成类型定义
4. **类型测试**：编写类型测试，确保类型定义的正确性

## 注意事项

1. 类型定义基于当前后端API返回的实际字段，如有调整需要同步更新
2. 所有可选字段都已标注 `?`，避免类型不匹配错误
3. 日期字段统一使用 `string` 类型（ISO 8601格式）
4. 枚举类型与实际API返回值保持一致
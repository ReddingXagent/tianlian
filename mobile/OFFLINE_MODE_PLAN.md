# 离线模式实现方案

**任务**: workspace-gbx9 (阶段 3: P2 - 离线模式)  
**创建时间**: 2026-04-03 13:00  
**优先级**: P2

---

## 🎯 目标

实现移动端离线数据缓存和网络恢复同步，确保用户在无网络环境下仍可查看历史数据，网络恢复后自动同步。

---

## 📋 功能需求

### 1. 离线数据缓存
- [ ] 设备列表缓存 (7 个设备)
- [ ] 站点列表缓存 (3 个站点)
- [ ] 工单列表缓存
- [ ] 告警列表缓存
- [ ] 知识库文章缓存

### 2. 网络状态检测
- [ ] 实时监测网络连接状态
- [ ] 网络切换时自动触发同步
- [ ] 显示网络状态指示器

### 3. 数据同步策略
- [ ] 启动时检查网络并同步
- [ ] 下拉手动刷新
- [ ] 后台定时同步 (可选)
- [ ] 冲突解决策略

### 4. 用户体验
- [ ] 离线模式提示
- [ ] 数据过期提示
- [ ] 同步进度指示
- [ ] 同步失败重试

---

## 🏗️ 技术架构

### 技术选型

| 功能 | 技术方案 | 说明 |
|------|---------|------|
| **本地存储** | `@react-native-async-storage/async-storage` | Expo 支持，简单易用 |
| **网络检测** | `@react-native-community/netinfo` | Expo 内置支持 |
| **状态管理** | React Context + Hooks | 轻量级，无需额外依赖 |
| **数据同步** | 自定义同步服务 | 灵活控制同步逻辑 |

### 目录结构

```
mobile/src/
├── services/
│   ├── api.ts              # API 客户端封装
│   ├── cache.ts            # 本地缓存服务
│   └── sync.ts             # 数据同步服务
├── store/
│   ├── OfflineContext.tsx  # 离线状态 Context
│   └── useOffline.ts       # 离线 Hook
├── hooks/
│   ├── useNetwork.ts       # 网络状态 Hook
│   └── useSync.ts          # 同步 Hook
├── components/
│   └── NetworkStatus.tsx   # 网络状态指示器
└── screens/
    ├── HomeScreen.tsx      # 集成离线功能
    └── DevicesScreen.tsx   # 集成离线功能
```

---

## 🔧 实现步骤

### Step 1: 安装依赖

```bash
cd mobile

# 本地存储
npx expo install @react-native-async-storage/async-storage

# 网络状态 (Expo 已内置)
npx expo install @react-native-community/netinfo
```

### Step 2: 创建 API 服务层

**文件**: `src/services/api.ts`

```typescript
import axios from 'axios';

const API_BASE_URL = 'http://192.168.1.102:8080/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器 - 添加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// API 方法封装
export const deviceApi = {
  getAll: () => api.get('/devices'),
  getById: (id: string) => api.get(`/devices/${id}`),
};

export const stationApi = {
  getAll: () => api.get('/stations'),
};

export const workOrderApi = {
  getAll: () => api.get('/workorders'),
  create: (data: any) => api.post('/workorders', data),
};

export const alarmApi = {
  getAll: () => api.get('/alarms'),
};
```

### Step 3: 创建缓存服务

**文件**: `src/services/cache.ts`

```typescript
import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_PREFIX = '@tianlian_';
const CACHE_EXPIRY = 5 * 60 * 1000; // 5 分钟过期

interface CachedData<T> {
  data: T;
  timestamp: number;
}

export const cache = {
  // 保存数据
  async set<T>(key: string, data: T): Promise<void> {
    const cached: CachedData<T> = {
      data,
      timestamp: Date.now(),
    };
    await AsyncStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(cached));
  },

  // 获取数据
  async get<T>(key: string): Promise<T | null> {
    const item = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`);
    if (!item) return null;

    const cached: CachedData<T> = JSON.parse(item);
    
    // 检查是否过期
    if (Date.now() - cached.timestamp > CACHE_EXPIRY) {
      await this.remove(key);
      return null;
    }

    return cached.data;
  },

  // 删除数据
  async remove(key: string): Promise<void> {
    await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`);
  },

  // 清空所有缓存
  async clear(): Promise<void> {
    const keys = await AsyncStorage.getAllKeys();
    const tianlianKeys = keys.filter(key => key.startsWith(CACHE_PREFIX));
    await AsyncStorage.multiRemove(tianlianKeys);
  },

  // 检查数据是否存在且未过期
  async isValid(key: string): Promise<boolean> {
    const data = await this.get(key);
    return data !== null;
  },
};
```

### Step 4: 创建网络状态 Hook

**文件**: `src/hooks/useNetwork.ts`

```typescript
import { useState, useEffect } from 'react';
import NetInfo from '@react-native-community/netinfo';

export interface NetworkState {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  type: string | null;
}

export const useNetwork = () => {
  const [networkState, setNetworkState] = useState<NetworkState>({
    isConnected: false,
    isInternetReachable: null,
    type: null,
  });

  useEffect(() => {
    // 订阅网络状态变化
    const unsubscribe = NetInfo.addEventListener((state) => {
      setNetworkState({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        type: state.type,
      });
    });

    // 初始检查
    NetInfo.fetch().then((state) => {
      setNetworkState({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        type: state.type,
      });
    });

    return unsubscribe;
  }, []);

  return networkState;
};
```

### Step 5: 创建同步服务

**文件**: `src/services/sync.ts`

```typescript
import { api, deviceApi, stationApi, workOrderApi, alarmApi } from './api';
import { cache } from './cache';

export interface SyncResult {
  success: boolean;
  syncedAt: number;
  errors?: string[];
}

export interface SyncStatus {
  isSyncing: boolean;
  lastSyncTime: number | null;
  pendingChanges: number;
}

class SyncService {
  private isSyncing = false;
  private lastSyncTime: number | null = null;
  private pendingChanges: any[] = [];

  // 全量同步
  async fullSync(): Promise<SyncResult> {
    if (this.isSyncing) {
      return { success: false, syncedAt: 0, errors: ['同步进行中'] };
    }

    this.isSyncing = true;
    const errors: string[] = [];

    try {
      // 同步设备
      try {
        const devices = await deviceApi.getAll();
        await cache.set('devices', devices.data);
      } catch (e) {
        errors.push('设备同步失败');
      }

      // 同步站点
      try {
        const stations = await stationApi.getAll();
        await cache.set('stations', stations.data);
      } catch (e) {
        errors.push('站点同步失败');
      }

      // 同步工单
      try {
        const workOrders = await workOrderApi.getAll();
        await cache.set('workOrders', workOrders.data);
      } catch (e) {
        errors.push('工单同步失败');
      }

      // 同步告警
      try {
        const alarms = await alarmApi.getAll();
        await cache.set('alarms', alarms.data);
      } catch (e) {
        errors.push('告警同步失败');
      }

      this.lastSyncTime = Date.now();
      return {
        success: errors.length === 0,
        syncedAt: this.lastSyncTime,
        errors: errors.length > 0 ? errors : undefined,
      };
    } finally {
      this.isSyncing = false;
    }
  }

  // 获取同步状态
  getStatus(): SyncStatus {
    return {
      isSyncing: this.isSyncing,
      lastSyncTime: this.lastSyncTime,
      pendingChanges: this.pendingChanges.length,
    };
  }

  // 添加待同步变更 (用于离线操作)
  addPendingChange(change: any) {
    this.pendingChanges.push(change);
  }

  // 同步待处理变更
  async syncPendingChanges(): Promise<void> {
    // TODO: 实现离线操作同步
    console.log('同步待处理变更:', this.pendingChanges);
  }
}

export const syncService = new SyncService();
```

### Step 6: 创建离线 Context

**文件**: `src/store/OfflineContext.tsx`

```typescript
import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNetwork } from '../hooks/useNetwork';
import { syncService } from '../services/sync';
import { cache } from '../services/cache';

interface OfflineContextType {
  isConnected: boolean;
  isSyncing: boolean;
  lastSyncTime: number | null;
  triggerSync: () => Promise<void>;
  getCachedData: <T>(key: string) => Promise<T | null>;
}

const OfflineContext = createContext<OfflineContextType | undefined>(undefined);

export const OfflineProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isConnected } = useNetwork();
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<number | null>(null);

  // 网络恢复时自动同步
  useEffect(() => {
    if (isConnected) {
      triggerSync();
    }
  }, [isConnected]);

  const triggerSync = async () => {
    if (isSyncing || !isConnected) return;
    
    setIsSyncing(true);
    try {
      const result = await syncService.fullSync();
      if (result.success) {
        setLastSyncTime(result.syncedAt);
      }
    } finally {
      setIsSyncing(false);
    }
  };

  const getCachedData = async <T,>(key: string): Promise<T | null> => {
    return cache.get<T>(key);
  };

  return (
    <OfflineContext.Provider
      value={{
        isConnected,
        isSyncing,
        lastSyncTime,
        triggerSync,
        getCachedData,
      }}
    >
      {children}
    </OfflineContext.Provider>
  );
};

export const useOffline = () => {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error('useOffline must be used within OfflineProvider');
  }
  return context;
};
```

### Step 7: 创建网络状态组件

**文件**: `src/components/NetworkStatus.tsx`

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useOffline } from '../store/OfflineContext';

export const NetworkStatus: React.FC = () => {
  const { isConnected, isSyncing, lastSyncTime } = useOffline();

  if (isConnected && !isSyncing) return null;

  return (
    <View style={[
      styles.container,
      { backgroundColor: isConnected ? '#e6f7ff' : '#fff1f0' }
    ]}>
      <Text style={styles.text}>
        {isSyncing ? '🔄 同步中...' : isConnected ? '✅ 已连接' : '❌ 离线模式'}
      </Text>
      {lastSyncTime && (
        <Text style={styles.subtext}>
          上次同步：{new Date(lastSyncTime).toLocaleTimeString()}
        </Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    padding: 8,
    alignItems: 'center',
  },
  text: {
    fontSize: 12,
    fontWeight: '500',
  },
  subtext: {
    fontSize: 10,
    color: '#666',
    marginTop: 2,
  },
});
```

### Step 8: 集成到应用

**文件**: `mobile/App.tsx` (修改)

```typescript
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { OfflineProvider } from './src/store/OfflineContext';
import { NetworkStatus } from './src/components/NetworkStatus';
import AppNavigator from './src/navigation/AppNavigator';

export default function App() {
  return (
    <OfflineProvider>
      <NavigationContainer>
        <NetworkStatus />
        <AppNavigator />
      </NavigationContainer>
    </OfflineProvider>
  );
}
```

**文件**: `mobile/src/screens/DevicesScreen.tsx` (修改示例)

```typescript
import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl } from 'react-native';
import { useOffline } from '../store/OfflineContext';
import { deviceApi } from '../services/api';
import { cache } from '../services/cache';

interface Device {
  id: string;
  name: string;
  type: string;
  status: string;
  online: boolean;
}

const DevicesScreen = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const { isConnected, triggerSync, getCachedData } = useOffline();

  // 加载数据
  const loadData = async () => {
    setLoading(true);
    try {
      if (isConnected) {
        // 在线：从 API 获取
        const response = await deviceApi.getAll();
        const data = response.data;
        setDevices(data);
        await cache.set('devices', data);
      } else {
        // 离线：从缓存获取
        const cached = await getCachedData<Device[]>('devices');
        if (cached) {
          setDevices(cached);
        }
      }
    } catch (error) {
      console.error('加载设备失败:', error);
      // 失败时尝试从缓存加载
      const cached = await getCachedData<Device[]>('devices');
      if (cached) {
        setDevices(cached);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [isConnected]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData();
    }
  };

  const renderItem = ({ item }: { item: Device }) => (
    <TouchableOpacity style={styles.item}>
      <View style={styles.itemLeft}>
        <Text style={styles.itemName}>{item.name}</Text>
        <Text style={styles.itemType}>{item.type}</Text>
      </View>
      <View style={styles.itemRight}>
        <View style={[styles.statusDot, { backgroundColor: item.online ? '#52c41a' : '#ff4d4f' }]} />
        <Text style={[styles.statusText, { color: item.online ? '#52c41a' : '#ff4d4f' }]}>
          {item.online ? '在线' : '离线'}
        </Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={devices}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={handleRefresh}
            enabled={isConnected}
          />
        }
        ListEmptyComponent={
          !isConnected && devices.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>离线且无缓存数据</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  list: {
    padding: 16,
  },
  item: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemLeft: {
    flex: 1,
  },
  itemName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
  },
  itemType: {
    fontSize: 14,
    color: '#666',
    marginTop: 4,
  },
  itemRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusText: {
    fontSize: 14,
  },
  empty: {
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
  },
});

export default DevicesScreen;
```

---

## 📦 依赖安装

```bash
cd mobile

# 安装依赖
npx expo install @react-native-async-storage/async-storage
npm install axios

# 网络状态 Expo 已内置，无需额外安装
```

---

## ✅ 验收标准

1. **离线浏览**: 无网络时可查看上次缓存的设备/站点/工单数据
2. **自动同步**: 网络恢复时自动触发数据同步
3. **手动刷新**: 下拉刷新可更新数据 (仅在线时)
4. **状态提示**: 显示网络状态和同步状态
5. **缓存过期**: 5 分钟后缓存自动过期，提示用户刷新

---

## 🎯 下一步

1. 安装依赖
2. 创建服务层文件
3. 创建 Context 和 Hooks
4. 修改现有屏幕组件
5. 测试离线场景
6. 更新任务状态

---

**文档作者**: 大圣 🐵  
**更新时间**: 2026-04-03 13:00

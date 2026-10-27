import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, ActivityIndicator } from 'react-native';
import { useOffline } from '../store/OfflineContext';
import { deviceApi, reportsApi } from '../services/api';
import { cache } from '../services/cache';

interface Device {
  id: string;
  name: string;
  type: string;
  status: string;
  online: boolean;
}

const getUtilizationColor = (val: number): { bg: string; text: string } => {
  if (val < 30) return { bg: '#fff7e6', text: '#fa8c16' };
  if (val > 90) return { bg: '#fff1f0', text: '#ff4d4f' };
  return { bg: '#f6ffed', text: '#52c41a' };
};

const DevicesScreen = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [utilizationMap, setUtilizationMap] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { isConnected, triggerSync, getCachedData } = useOffline();

  // 加载利用率数据
  const loadUtilizationData = useCallback(async () => {
    if (!isConnected) return;
    const cacheKey = 'deviceUtilizationMap';
    try {
      const res = await reportsApi.getUtilization();
      const data = res.data?.data || res.data || [];
      if (Array.isArray(data)) {
        const map: Record<string, number> = {};
        data.forEach((item: any) => {
          const deviceId = item.deviceId || item.id;
          const rate = item.rate ?? item.utilization ?? item.value;
          if (deviceId && rate !== undefined) {
            map[deviceId] = Number(rate);
          }
        });
        setUtilizationMap(map);
        await cache.set(cacheKey, map);
      }
    } catch (error: any) {
      console.error('[Devices] Load utilization error:', error.message);
      // 尝试缓存
      const cached = await getCachedData<Record<string, number>>(cacheKey);
      if (cached) setUtilizationMap(cached);
    }
  }, [isConnected, getCachedData]);

  // 加载数据
  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      if (isConnected) {
        // 在线：从 API 获取
        console.log('[Devices] Loading from API...');
        const response = await deviceApi.getAll();
        const data = response.data;
        setDevices(data);
        await cache.set('devices', data);
        console.log(`[Devices] Loaded ${data.length} devices from API`);
        // 同步加载利用率数据（不阻塞）
        loadUtilizationData();
      } else {
        // 离线：从缓存获取
        console.log('[Devices] Loading from cache (offline)...');
        const cached = await getCachedData<Device[]>('devices');
        if (cached) {
          setDevices(cached);
          console.log(`[Devices] Loaded ${cached.length} devices from cache`);
        } else {
          console.warn('[Devices] No cache available');
        }
      }
    } catch (error: any) {
      console.error('[Devices] Load error:', error.message);
      // 失败时尝试从缓存加载
      const cached = await getCachedData<Device[]>('devices');
      if (cached) {
        setDevices(cached);
        console.log(`[Devices] Fallback: loaded ${cached.length} devices from cache`);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected, getCachedData, loadUtilizationData]);

  useEffect(() => {
    loadData();
  }, [isConnected, loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const renderItem = ({ item }: { item: Device }) => {
    const utilRate = utilizationMap[item.id];
    const utilColors = utilRate !== undefined ? getUtilizationColor(utilRate) : null;

    return (
      <TouchableOpacity style={styles.item}>
        <View style={styles.itemMain}>
          <View style={styles.itemLeft}>
            <Text style={styles.itemName}>{item.name}</Text>
            <Text style={styles.itemType}>{item.type}</Text>
            {item.status !== '正常' && (
              <Text style={[styles.statusText, { color: '#ff4d4f' }]}>
                {item.status}
              </Text>
            )}
          </View>
          <View style={styles.itemRight}>
            <View style={[styles.statusDot, { backgroundColor: item.online ? '#52c41a' : '#ff4d4f' }]} />
            <Text style={[styles.statusText, { color: item.online ? '#52c41a' : '#ff4d4f' }]}>
              {item.online ? '在线' : '离线'}
            </Text>
          </View>
        </View>
        {utilRate !== undefined && utilColors && (
          <View style={[styles.utilBadge, { backgroundColor: utilColors.bg }]}>
            <Text style={[styles.utilBadgeText, { color: utilColors.text }]}>
              利用率 {utilRate}%
            </Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载设备列表...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={devices}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            enabled={isConnected}
            colors={['#1890ff']}
          />
        }
        ListEmptyComponent={
          !isConnected && devices.length === 0 ? (
            <View style={styles.centerContainer}>
              <Text style={styles.emptyIcon}>📭</Text>
              <Text style={styles.emptyText}>离线且无缓存数据</Text>
              <Text style={styles.emptySubtext}>请连接网络后刷新</Text>
            </View>
          ) : devices.length === 0 ? (
            <View style={styles.centerContainer}>
              <Text style={styles.emptyIcon}>📭</Text>
              <Text style={styles.emptyText}>暂无设备</Text>
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
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  item: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  itemMain: {
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
  statusText: {
    fontSize: 12,
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
  loadingText: {
    marginTop: 16,
    color: '#999',
    fontSize: 14,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#ccc',
  },
  utilBadge: {
    alignSelf: 'flex-end',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    marginTop: 10,
  },
  utilBadgeText: {
    fontSize: 11,
    fontWeight: '600',
  },
});

export default DevicesScreen;

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useOffline } from '../store/OfflineContext';
import { cache } from '../services/cache';
import { workOrderApi } from '../services/api';

interface WorkOrder {
  id: string;
  title: string;
  priority: string;
  status: string;
  created_at: string;
}

const priorityColors: Record<string, string> = {
  urgent: '#ff4d4f',
  high: '#faad14',
  medium: '#1890ff',
  low: '#52c41a',
};

const statusLabels: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
};

const WorkOrdersScreen = ({ navigation }: any) => {
  const { isConnected } = useOffline();
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchWorkOrders = useCallback(async (forceRefresh = false) => {
    const cacheKey = 'workOrders';

    try {
      // 离线时只读缓存
      if (!isConnected) {
        const cached = await cache.get<WorkOrder[]>(cacheKey);
        if (cached) {
          setWorkOrders(cached);
        }
        setLoading(false);
        return;
      }

      // 在线时请求API
      if (forceRefresh || isConnected) {
        const response = await workOrderApi.getAll();
        const data = response.data as WorkOrder[];
        setWorkOrders(data);
        await cache.set(cacheKey, data);
      }
    } catch (error: unknown) {
      console.error('获取工单失败:', error);
      // 失败时尝试读取缓存
      const cached = await cache.get<WorkOrder[]>(cacheKey);
      if (cached) {
        setWorkOrders(cached);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected]);

  useEffect(() => {
    fetchWorkOrders();
  }, [fetchWorkOrders]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    fetchWorkOrders(true);
  }, [fetchWorkOrders]);

  const handlePress = (item: WorkOrder) => {
    navigation.navigate('WorkOrderDetail', { id: item.id });
  };

  const renderItem = ({ item }: { item: WorkOrder }) => (
    <TouchableOpacity style={styles.item} onPress={() => handlePress(item)}>
      <View style={styles.header}>
        <View style={[styles.priorityDot, { backgroundColor: priorityColors[item.priority] || '#999' }]} />
        <Text style={styles.title} numberOfLines={1}>{item.title}</Text>
      </View>
      <View style={styles.footer}>
        <Text style={styles.time}>{item.created_at}</Text>
        <View style={[styles.statusBadge, { backgroundColor: item.status === 'completed' ? '#f6ffed' : item.status === 'processing' ? '#e6f7ff' : '#fffbe6' }]}>
          <Text style={[styles.statusText, { color: item.status === 'completed' ? '#52c41a' : item.status === 'processing' ? '#1890ff' : '#faad14' }]}>
            {statusLabels[item.status] || item.status}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={workOrders}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={['#1890ff']}
          />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>暂无工单数据</Text>
          </View>
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
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  list: {
    padding: 16,
  },
  item: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  priorityDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 8,
  },
  title: {
    flex: 1,
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  time: {
    fontSize: 12,
    color: '#999',
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '500',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
  },
});

export default WorkOrdersScreen;
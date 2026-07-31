import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useWorkOrderStore } from '../store/workOrderStore';
import { WorkOrder, WorkOrderStatus, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import WorkOrderCard from '../components/WorkOrderCard';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const STATUS_FILTERS: { key: WorkOrderStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待接单' },
  { key: 'in_progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已取消' },
];

const WorkOrderListScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { orders, loading, error, total, fetchOrders } = useWorkOrderStore();
  const [activeFilter, setActiveFilter] = useState<WorkOrderStatus | 'all'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      await fetchOrders(
        activeFilter === 'all' ? undefined : { status: activeFilter }
      );
      if (isRefresh) setRefreshing(false);
    },
    [fetchOrders, activeFilter]
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [activeFilter, loadData]);

  const handleOrderPress = (order: WorkOrder) => {
    navigation.navigate('WorkOrderDetail', { orderId: order.id });
  };

  const handleCreateOrder = () => {
    navigation.navigate('WorkOrderCreate');
  };

  const renderOrderItem = ({ item }: { item: WorkOrder }) => (
    <WorkOrderCard order={item} onPress={handleOrderPress} />
  );

  if (loading && orders.length === 0) {
    return <LoadingSpinner text="加载工单列表..." />;
  }

  return (
    <View style={styles.container}>
      {/* 顶部操作栏 */}
      <View style={styles.headerBar}>
        <Text style={styles.headerTitle}>
          工单管理
          {total > 0 && (
            <Text style={styles.headerCount}> ({total})</Text>
          )}
        </Text>
        <TouchableOpacity
          style={styles.createBtn}
          onPress={handleCreateOrder}
          activeOpacity={0.7}
        >
          <Text style={styles.createBtnText}>+ 新建</Text>
        </TouchableOpacity>
      </View>

      {/* 状态筛选 */}
      <ScrollableFilter
        filters={STATUS_FILTERS}
        active={activeFilter}
        onSelect={setActiveFilter}
      />

      {error && orders.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => loadData()}
        />
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderOrderItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => loadData(true)}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
          ListEmptyComponent={
            <EmptyState
              icon="📋"
              title="暂无工单"
              message={
                activeFilter === 'all'
                  ? '当前没有工单'
                  : `没有${STATUS_FILTERS.find((f) => f.key === activeFilter)?.label}工单`
              }
            />
          }
          ListFooterComponent={
            orders.length > 0 ? (
              <Text style={styles.totalText}>
                共 {total} 条工单
              </Text>
            ) : null
          }
        />
      )}
    </View>
  );
};

// 可滚动筛选条组件
const ScrollableFilter: React.FC<{
  filters: { key: string; label: string }[];
  active: string;
  onSelect: (key: WorkOrderStatus | 'all') => void;
}> = ({ filters, active, onSelect }) => (
  <View style={styles.filterContainer}>
    {filters.map((f) => (
      <TouchableOpacity
        key={f.key}
        style={[
          styles.filterBtn,
          active === f.key && styles.filterBtnActive,
        ]}
        onPress={() => onSelect(f.key as WorkOrderStatus | 'all')}
      >
        <Text
          style={[
            styles.filterBtnText,
            active === f.key && styles.filterBtnTextActive,
          ]}
        >
          {f.label}
        </Text>
      </TouchableOpacity>
    ))}
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  headerBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  headerCount: {
    fontSize: 14,
    color: '#999',
    fontWeight: '400',
  },
  createBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  createBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  filterContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  filterBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
    backgroundColor: '#f0f0f0',
  },
  filterBtnActive: {
    backgroundColor: '#1a73e8',
  },
  filterBtnText: {
    fontSize: 13,
    color: '#666',
    fontWeight: '500',
  },
  filterBtnTextActive: {
    color: '#fff',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  totalText: {
    textAlign: 'center',
    fontSize: 13,
    color: '#999',
    paddingVertical: 12,
  },
});

export default WorkOrderListScreen;

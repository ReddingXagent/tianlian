import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation, useIsFocused } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useOrderStore } from '../store/orderStore';
import { Order, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ORDER_STATUS_FILTERS = [
  { key: '', label: '全部' },
  { key: 'charging', label: '充电中' },
  { key: 'completed', label: '已完成' },
  { key: 'unpaid', label: '未支付' },
];

const OrderListScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { orders, loading, error, fetchOrders, loadMoreOrders, hasMore, loadingMore } =
    useOrderStore();
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState('');

  // 移动端质量基线: 订单为主Tab, 切Tab保活不重建,
  // 充电状态随时在变 → 回焦时静默刷新。
  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      fetchOrders({ status: activeFilter || undefined });
    }
  }, [isFocused, activeFilter]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchOrders({ status: activeFilter || undefined });
    setRefreshing(false);
  }, [activeFilter]);

  const handleOrderPress = (order: Order) => {
    if (order.status === 'charging') {
      navigation.navigate('Charging', { orderId: order.id });
    } else if (order.paymentStatus === 'unpaid') {
      navigation.navigate('Payment', { orderId: order.id, amount: order.amount });
    } else {
      navigation.navigate('OrderDetail', { orderId: order.id });
    }
  };

  const renderOrderItem = ({ item }: { item: Order }) => {
    const timeText = item.startTime
      ? new Date(item.startTime).toLocaleString('zh-CN', {
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })
      : '-';

    return (
      <TouchableOpacity
        style={styles.orderCard}
        onPress={() => handleOrderPress(item)}
        activeOpacity={0.7}
      >
        <View style={styles.orderHeader}>
          <Text style={styles.orderStation} numberOfLines={1}>{item.stationName}</Text>
          <StatusBadge status={item.status === 'completed' && item.paymentStatus === 'unpaid' ? 'unpaid' : item.status} />
        </View>
        <Text style={styles.orderNo}>订单号: {item.orderNo}</Text>
        <View style={styles.orderMeta}>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>充电量</Text>
            <Text style={styles.metaValue}>{item.energy.toFixed(2)} kWh</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>时长</Text>
            <Text style={styles.metaValue}>{item.duration} 分钟</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>费用</Text>
            <Text style={[styles.metaValue, { color: '#e65100', fontWeight: '700' }]}>
              ¥{item.amount.toFixed(2)}
            </Text>
          </View>
        </View>
        <Text style={styles.orderTime}>{timeText}</Text>
      </TouchableOpacity>
    );
  };

  if (loading && orders.length === 0) {
    return <LoadingSpinner text="加载订单..." />;
  }

  // 首屏拉取失败不能伪装成"暂无订单"(F221): store已有error态但此前未渲染,
  // 网络失败时用户被误导点"去充电"。仅无数据时切错误页, 刷新失败保留已有列表(F209模式)。
  if (error && orders.length === 0) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => fetchOrders({ status: activeFilter || undefined })}
      />
    );
  }

  return (
    <View style={styles.container}>
      {/* 筛选栏 */}
      <View style={styles.filterRow}>
        {ORDER_STATUS_FILTERS.map((filter) => (
          <TouchableOpacity
            key={filter.key}
            style={[styles.filterBtn, activeFilter === filter.key && styles.filterBtnActive]}
            onPress={() => setActiveFilter(filter.key)}
          >
            <Text
              style={[
                styles.filterBtnText,
                activeFilter === filter.key && styles.filterBtnTextActive,
              ]}
            >
              {filter.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {orders.length === 0 ? (
        <EmptyState
          icon="📋"
          title="暂无订单"
          message="您还没有充电记录"
          actionLabel="去充电"
          onAction={() => navigation.navigate('Main', { screen: 'Scan' })}
        />
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderOrderItem}
          contentContainerStyle={styles.listContent}
          onEndReached={loadMoreOrders}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loadingMore ? (
              <ActivityIndicator color="#1a73e8" style={styles.footer} />
            ) : !hasMore && orders.length > 0 ? (
              <Text style={styles.footerText}>没有更多了</Text>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  filterRow: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  filterBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f5f6fa',
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
  orderCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  orderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  orderStation: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  orderNo: {
    fontSize: 12,
    color: '#999',
    marginBottom: 10,
  },
  orderMeta: {
    flexDirection: 'row',
    backgroundColor: '#f5f6fa',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
  },
  metaItem: {
    flex: 1,
    alignItems: 'center',
  },
  metaLabel: {
    fontSize: 11,
    color: '#999',
    marginBottom: 2,
  },
  metaValue: {
    fontSize: 13,
    color: '#333',
    fontWeight: '500',
  },
  orderTime: {
    fontSize: 12,
    color: '#bbb',
  },
  footer: {
    marginVertical: 12,
  },
  footerText: {
    textAlign: 'center',
    fontSize: 12,
    color: '#bbb',
    marginVertical: 12,
  },
});

export default OrderListScreen;
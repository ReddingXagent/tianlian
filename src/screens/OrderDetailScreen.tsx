import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useRoute, RouteProp, useNavigation, useIsFocused } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useOrderStore } from '../store/orderStore';
import { RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { formatDateTime, formatMoney, formatEnergy } from '../utils/format';

type OrderDetailRouteProp = RouteProp<RootStackParamList, 'OrderDetail'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const OrderDetailScreen: React.FC = () => {
  const route = useRoute<OrderDetailRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { orderId } = route.params;
  const { selectedOrder, loading, error, fetchOrderDetail, cancelOrder } = useOrderStore();

  // 移动端质量基线(F170/F176同型收尾): 订单状态(充电中/已完成/已取消)
  // 会在离开页面期间变化 → 回焦静默重拉。
  const isFocused = useIsFocused();
  useEffect(() => {
    if (isFocused) {
      fetchOrderDetail(orderId);
    }
  }, [isFocused, orderId, fetchOrderDetail]);

  const handleCancelOrder = () => {
    Alert.alert(
      '取消订单',
      '确定要取消此订单吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定',
          style: 'destructive',
          onPress: async () => {
            try {
              await cancelOrder(orderId);
              Alert.alert('成功', '订单已取消');
            } catch {
              Alert.alert('失败', '取消失败，请重试');
            }
          },
        },
      ]
    );
  };

  const handlePay = () => {
    if (selectedOrder) {
      navigation.navigate('Payment', { orderId: selectedOrder.id, amount: selectedOrder.amount });
    }
  };

  if (loading && !selectedOrder) {
    return <LoadingSpinner text="加载订单详情..." />;
  }

  if (error && !selectedOrder) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => fetchOrderDetail(orderId)}
      />
    );
  }

  const order = selectedOrder;
  if (!order) return null;

  const startTime = formatDateTime(order.startTime);
  const endTime = formatDateTime(order.endTime);

  const statusMap: Record<string, string> = {
    charging: 'charging',
    completed: order.paymentStatus === 'unpaid' ? 'unpaid' : 'completed',
    cancelled: 'cancelled',
    timeout: 'timeout',
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* 订单状态 */}
      <View style={styles.statusCard}>
        <StatusBadge status={statusMap[order.status] || order.status} />
        <Text style={styles.statusAmount}>¥{formatMoney(order.amount)}</Text>
        <Text style={styles.statusNo}>订单号: {order.orderNo}</Text>
      </View>

      {/* 充电信息 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>充电信息</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>充电站点</Text>
            <Text style={styles.infoValue}>{order.stationName}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>充电桩</Text>
            <Text style={styles.infoValue}>{order.chargerName}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>车牌号</Text>
            <Text style={styles.infoValue}>{order.vehiclePlate || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>充电量</Text>
            <Text style={styles.infoValue}>{formatEnergy(order.energy)} kWh</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>充电时长</Text>
            <Text style={styles.infoValue}>{order.duration} 分钟</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>开始时间</Text>
            <Text style={styles.infoValue}>{startTime}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.infoLabel}>结束时间</Text>
            <Text style={styles.infoValue}>{endTime}</Text>
          </View>
        </View>
      </View>

      {/* 费用明细 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>费用明细</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>充电费用</Text>
            <Text style={styles.infoValue}>¥{formatMoney(order.amount)}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>优惠减免</Text>
            <Text style={[styles.infoValue, { color: '#2e7d32' }]}>
              -¥{formatMoney(order.couponDiscount)}
            </Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.infoLabel}>实付金额</Text>
            <Text style={[styles.infoValue, { color: '#e65100', fontWeight: '700' }]}>
              ¥{formatMoney(order.amount - order.couponDiscount)}
            </Text>
          </View>
        </View>
      </View>

      {/* 操作按钮 */}
      {order.status === 'charging' && (
        <TouchableOpacity style={styles.cancelBtn} onPress={handleCancelOrder} activeOpacity={0.7}>
          <Text style={styles.cancelBtnText}>取消订单</Text>
        </TouchableOpacity>
      )}
      {order.paymentStatus === 'unpaid' && order.status !== 'charging' && (
        <TouchableOpacity style={styles.payBtn} onPress={handlePay} activeOpacity={0.7}>
          <Text style={styles.payBtnText}>去支付</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  statusCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
  statusAmount: {
    fontSize: 36,
    fontWeight: '700',
    color: '#e65100',
    marginTop: 8,
  },
  statusNo: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#999',
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  cancelBtn: {
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#fce4ec',
  },
  cancelBtnText: {
    fontSize: 16,
    color: '#c62828',
    fontWeight: '500',
  },
  payBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  payBtnText: {
    fontSize: 16,
    color: '#fff',
    fontWeight: '600',
  },
});

export default OrderDetailScreen;
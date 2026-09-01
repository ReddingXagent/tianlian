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
import { useWorkOrderList } from '../hooks/useWorkOrderList';
import { WorkOrder, WorkOrderStatus, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import WorkOrderCard from '../components/WorkOrderCard';
import { useTheme } from '../hooks/useTheme';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const STATUS_FILTERS: { key: WorkOrderStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待接单' },
  { key: 'in_progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已取消' },
];

const WorkOrderListScreen: React.FC = () => {
  const { colors } = useTheme();
  const navigation = useNavigation<NavigationProp>();
  const { orders, loading, error, total, activeFilter, refreshing, setActiveFilter, loadData } =
    useWorkOrderList();

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
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      {/* 顶部操作栏 */}
      <View style={[styles.headerBar, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>
          工单管理
          {total > 0 && (
            <Text style={[styles.headerCount, { color: colors.textSecondary }]}> ({total})</Text>
          )}
        </Text>
        <TouchableOpacity
          style={[styles.createBtn, { backgroundColor: colors.primary }]}
          onPress={handleCreateOrder}
          activeOpacity={0.7}
         accessibilityRole="button">
          <Text style={[styles.createBtnText, { color: colors.onPrimary }]}>+ 新建</Text>
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
              colors={[colors.primary]}
              tintColor={colors.primary}
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
              <Text style={[styles.totalText, { color: colors.textSecondary }]}>
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
}> = ({ filters, active, onSelect }) => {
  const { colors } = useTheme();
  return (
    <View style={[styles.filterContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
      {filters.map((f) => (
        <TouchableOpacity
          key={f.key}
          style={[
            styles.filterBtn,
            { backgroundColor: colors.divider },
            active === f.key && { backgroundColor: colors.primary },
          ]}
          onPress={() => onSelect(f.key as WorkOrderStatus | 'all')}
         accessibilityRole="button">
          <Text
            style={[
              styles.filterBtnText,
              { color: colors.textSecondary },
              active === f.key && { color: colors.onPrimary },
            ]}
          >
            {f.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  headerBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  headerCount: {
    fontSize: 14,
    fontWeight: '400',
  },
  createBtn: {
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  createBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  filterContainer: {
    flexDirection: 'row',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
  },
  filterBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
  },
  filterBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  totalText: {
    textAlign: 'center',
    fontSize: 13,
    paddingVertical: 12,
  },
});

export default WorkOrderListScreen;

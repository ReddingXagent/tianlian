import { useEffect, useState, useCallback } from 'react';
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
import { useInspectionStore } from '../store/inspectionStore';
import { InspectionTask, InspectionStatus, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const STATUS_FILTERS: { key: InspectionStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待巡检' },
  { key: 'in_progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'overdue', label: '已逾期' },
];

const TYPE_LABELS: Record<string, string> = {
  daily: '日检',
  weekly: '周检',
  monthly: '月检',
  quarterly: '季检',
  annual: '年检',
  special: '特检',
};

const InspectionListScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { tasks, loading, error, total, fetchTasks } = useInspectionStore();
  const [activeFilter, setActiveFilter] = useState<InspectionStatus | 'all'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const loadCore = useCallback(
    () =>
      fetchTasks(
        activeFilter === 'all' ? undefined : { status: activeFilter }
      ),
    [fetchTasks, activeFilter]
  );

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      try {
        await loadCore();
      } finally {
        if (isRefresh) setRefreshing(false);
      }
    },
    [loadCore]
  );

  useEffect(() => {
    void loadCore();
  }, [loadCore]);

  const handleTaskPress = (task: InspectionTask) => {
    navigation.navigate('InspectionDetail', { taskId: task.id });
  };

  const renderItem = ({ item }: { item: InspectionTask }) => (
    <TouchableOpacity
      style={styles.card}
      onPress={() => handleTaskPress(item)}
      activeOpacity={0.7}
    >
      <View style={styles.cardHeader}>
        <View style={styles.cardTitleRow}>
          <Text style={styles.cardTitle} numberOfLines={1}>
            {item.description}
          </Text>
          <StatusBadge status={item.status} />
        </View>
        <View style={styles.cardMeta}>
          <View style={styles.typeBadge}>
            <Text style={styles.typeText}>{TYPE_LABELS[item.type] || item.type}</Text>
          </View>
          <Text style={styles.cardMetaText}>{item.stationName}</Text>
          <Text style={styles.cardMetaText}>·</Text>
          <Text style={styles.cardMetaText}>{item.deviceName}</Text>
        </View>
      </View>
      <View style={styles.cardFooter}>
        <Text style={styles.dateText}>
          计划日期: {new Date(item.scheduledDate).toLocaleDateString('zh-CN')}
        </Text>
        <Text style={styles.itemCount}>
          {item.items?.length || 0} 项检查
        </Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && tasks.length === 0) {
    return <LoadingSpinner text="加载巡检任务..." />;
  }

  return (
    <View style={styles.container}>
      <View style={styles.filterContainer}>
        {STATUS_FILTERS.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[styles.filterBtn, activeFilter === f.key && styles.filterBtnActive]}
            onPress={() => setActiveFilter(f.key)}
          >
            <Text style={[styles.filterBtnText, activeFilter === f.key && styles.filterBtnTextActive]}>
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {error && tasks.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => loadData()}
        />
      ) : (
        <FlatList
          data={tasks}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
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
            <EmptyState icon="🔍" title="暂无巡检任务" message="当前没有巡检任务" />
          }
          ListFooterComponent={
            tasks.length > 0 ? (
              <Text style={styles.totalText}>共 {total} 条巡检任务</Text>
            ) : null
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
  card: {
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
  cardHeader: {
    marginBottom: 10,
  },
  cardTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  typeBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: '#e3f2fd',
    borderRadius: 4,
  },
  typeText: {
    fontSize: 11,
    color: '#1565c0',
    fontWeight: '500',
  },
  cardMetaText: {
    fontSize: 12,
    color: '#999',
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  dateText: {
    fontSize: 12,
    color: '#999',
  },
  itemCount: {
    fontSize: 12,
    color: '#1a73e8',
    fontWeight: '500',
  },
  totalText: {
    textAlign: 'center',
    fontSize: 13,
    color: '#999',
    paddingVertical: 12,
  },
});

export default InspectionListScreen;

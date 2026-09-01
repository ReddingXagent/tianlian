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
import { useTheme } from '../hooks/useTheme';
import { useInspectionList } from '../hooks/useInspectionList';
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
  const { colors } = useTheme();
  const { tasks, loading, error, total, activeFilter, refreshing, setActiveFilter, loadData } =
    useInspectionList();

  const handleTaskPress = (task: InspectionTask) => {
    navigation.navigate('InspectionDetail', { taskId: task.id });
  };

  const renderItem = ({ item }: { item: InspectionTask }) => (
    <TouchableOpacity
      style={[styles.card, { backgroundColor: colors.cardBg }]}
      onPress={() => handleTaskPress(item)}
      activeOpacity={0.7}
     accessibilityRole="button">
      <View style={styles.cardHeader}>
        <View style={styles.cardTitleRow}>
          <Text style={[styles.cardTitle, { color: colors.textPrimary }]} numberOfLines={1}>
            {item.description}
          </Text>
          <StatusBadge status={item.status} />
        </View>
        <View style={styles.cardMeta}>
          <View style={[styles.typeBadge, { backgroundColor: colors.infoBg }]}>
            <Text style={[styles.typeText, { color: colors.info }]}>{TYPE_LABELS[item.type] || item.type}</Text>
          </View>
          <Text style={[styles.cardMetaText, { color: colors.textSecondary }]}>{item.stationName}</Text>
          <Text style={[styles.cardMetaText, { color: colors.textSecondary }]}>·</Text>
          <Text style={[styles.cardMetaText, { color: colors.textSecondary }]}>{item.deviceName}</Text>
        </View>
      </View>
      <View style={[styles.cardFooter, { borderTopColor: colors.divider }]}>
        <Text style={[styles.dateText, { color: colors.textSecondary }]}>
          计划日期: {new Date(item.scheduledDate).toLocaleDateString('zh-CN')}
        </Text>
        <Text style={[styles.itemCount, { color: colors.primary }]}>
          {item.items?.length || 0} 项检查
        </Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && tasks.length === 0) {
    return <LoadingSpinner text="加载巡检任务..." />;
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      <View style={[styles.filterContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        {STATUS_FILTERS.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[styles.filterBtn, { backgroundColor: colors.neutralBg }, activeFilter === f.key && { backgroundColor: colors.primary }]}
            onPress={() => setActiveFilter(f.key)}
           accessibilityRole="button">
            <Text style={[styles.filterBtnText, { color: colors.textSecondary }, activeFilter === f.key && { color: colors.onPrimary }]}>
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
              colors={[colors.primary]}
              tintColor={colors.primary}
            />
          }
          ListEmptyComponent={
            <EmptyState icon="🔍" title="暂无巡检任务" message="当前没有巡检任务" />
          }
          ListFooterComponent={
            tasks.length > 0 ? (
              <Text style={[styles.totalText, { color: colors.textSecondary }]}>共 {total} 条巡检任务</Text>
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
  card: {
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
    borderRadius: 4,
  },
  typeText: {
    fontSize: 11,
    fontWeight: '500',
  },
  cardMetaText: {
    fontSize: 12,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
  },
  dateText: {
    fontSize: 12,
  },
  itemCount: {
    fontSize: 12,
    fontWeight: '500',
  },
  totalText: {
    textAlign: 'center',
    fontSize: 13,
    paddingVertical: 12,
  },
});

export default InspectionListScreen;

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useRoute, RouteProp, useNavigation } from '@react-navigation/native';
import { alarmApi } from '../services/api';
import { Alarm, RootStackParamList, AlarmLevel, AlarmStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type AlarmListRouteProp = RouteProp<RootStackParamList, 'AlarmList'>;

const LEVEL_ICON: Record<AlarmLevel, string> = {
  critical: '🔴',
  warning: '🟡',
  info: '🔵',
};

const ALARM_TYPE_LABEL: Record<string, string> = {
  device_fault: '设备故障',
  power_anomaly: '功率异常',
  communication_loss: '通信中断',
  temperature_warning: '温度预警',
  other: '其他',
};

const LEVEL_FILTERS: Array<{ key: AlarmLevel | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'critical', label: '严重' },
  { key: 'warning', label: '警告' },
  { key: 'info', label: '信息' },
];

const STATUS_FILTERS: Array<{ key: AlarmStatus | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'unhandled', label: '未处理' },
  { key: 'processing', label: '处理中' },
  { key: 'resolved', label: '已解决' },
];

const AlarmListScreen: React.FC = () => {
  const route = useRoute<AlarmListRouteProp>();
  const navigation = useNavigation();
  const stationId = route.params?.stationId;

  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [levelFilter, setLevelFilter] = useState<AlarmLevel | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<AlarmStatus | 'all'>('all');
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (isRefresh = false, p = 1) => {
    if (isRefresh) {
      setRefreshing(true);
    } else if (p === 1) {
      setLoading(true);
    }
    setError(null);

    try {
      const params: Record<string, any> = { page: p, pageSize: 20 };
      if (stationId) params.stationId = stationId;
      if (levelFilter !== 'all') params.level = levelFilter;
      if (statusFilter !== 'all') params.status = statusFilter;

      const response = await alarmApi.getList(params);
      const data = response.data;

      if (p === 1) {
        setAlarms(data.items);
      } else {
        setAlarms((prev) => [...prev, ...data.items]);
      }
      setTotal(data.total);
      setPage(p);
    } catch {
      setError('加载告警列表失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [stationId, levelFilter, statusFilter]);

  useEffect(() => {
    fetchData(false, 1);
  }, [fetchData]);

  const handleLoadMore = () => {
    if (alarms.length < total && !loading) {
      fetchData(false, page + 1);
    }
  };

  const handleFilterChange = (filterType: 'level' | 'status', value: any) => {
    if (filterType === 'level') {
      setLevelFilter(value);
    } else {
      setStatusFilter(value);
    }
    setPage(1);
    setAlarms([]);
  };

  const formatTime = (dateStr: string): string => {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}小时前`;
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const renderAlarmItem = ({ item }: { item: Alarm }) => (
    <TouchableOpacity style={styles.alarmCard} activeOpacity={0.7}>
      <View style={styles.alarmHeader}>
        <View style={styles.alarmTitleRow}>
          <Text style={styles.alarmLevelIcon}>{LEVEL_ICON[item.level] || '⚪'}</Text>
          <Text style={styles.alarmTitle} numberOfLines={1}>{item.title}</Text>
        </View>
        <StatusBadge status={item.status} />
      </View>

      <Text style={styles.alarmDescription} numberOfLines={2}>
        {item.description}
      </Text>

      <View style={styles.alarmMeta}>
        <Text style={styles.alarmStation}>{item.stationName}</Text>
        {item.deviceName && (
          <Text style={styles.alarmDevice}>· {item.deviceName}</Text>
        )}
      </View>

      <View style={styles.alarmFooter}>
        <Text style={styles.alarmType}>
          {ALARM_TYPE_LABEL[item.type] || item.type}
        </Text>
        <Text style={styles.alarmTime}>{formatTime(item.createdAt)}</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* 筛选栏 */}
      <View style={styles.filtersContainer}>
        {/* 级别筛选 */}
        <View style={styles.filterRow}>
          {LEVEL_FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, levelFilter === f.key && styles.filterChipActive]}
              onPress={() => handleFilterChange('level', f.key)}
            >
              <Text style={[styles.filterChipText, levelFilter === f.key && styles.filterChipTextActive]}>
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        {/* 状态筛选 */}
        <View style={styles.filterRow}>
          {STATUS_FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, statusFilter === f.key && styles.filterChipActive]}
              onPress={() => handleFilterChange('status', f.key)}
            >
              <Text style={[styles.filterChipText, statusFilter === f.key && styles.filterChipTextActive]}>
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {loading && alarms.length === 0 ? (
        <LoadingSpinner text="加载告警列表..." />
      ) : error && alarms.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => fetchData(false, 1)}
        />
      ) : (
        <FlatList
          data={alarms}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderAlarmItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchData(true, 1)}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          ListEmptyComponent={
            <EmptyState
              icon="✅"
              title="暂无告警"
              message="当前没有符合条件的告警记录"
            />
          }
          ListFooterComponent={
            alarms.length > 0 && alarms.length < total ? (
              <View style={styles.loadingMore}>
                <LoadingSpinner text="加载更多..." size="small" />
              </View>
            ) : alarms.length >= total && total > 0 ? (
              <Text style={styles.footerText}>已显示全部 {total} 条告警</Text>
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
  filtersContainer: {
    backgroundColor: '#fff',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  filterRow: {
    flexDirection: 'row',
    marginBottom: 6,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f5f6fa',
    marginRight: 8,
  },
  filterChipActive: {
    backgroundColor: '#1a73e8',
  },
  filterChipText: {
    fontSize: 13,
    color: '#666',
  },
  filterChipTextActive: {
    color: '#fff',
    fontWeight: '500',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  alarmCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  alarmHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  alarmTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
  },
  alarmLevelIcon: {
    fontSize: 16,
    marginRight: 8,
  },
  alarmTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  alarmDescription: {
    fontSize: 13,
    color: '#666',
    lineHeight: 20,
    marginBottom: 8,
  },
  alarmMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  alarmStation: {
    fontSize: 12,
    color: '#999',
  },
  alarmDevice: {
    fontSize: 12,
    color: '#999',
  },
  alarmFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  alarmType: {
    fontSize: 12,
    color: '#1a73e8',
    fontWeight: '500',
  },
  alarmTime: {
    fontSize: 12,
    color: '#bbb',
  },
  loadingMore: {
    paddingVertical: 16,
  },
  footerText: {
    textAlign: 'center',
    color: '#bbb',
    fontSize: 12,
    paddingVertical: 16,
  },
});

export default AlarmListScreen;
import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useDashboardStore } from '../store/dashboardStore';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

const PERIODS: { key: 'week' | 'month' | 'quarter'; label: string }[] = [
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
  { key: 'quarter', label: '季' },
];

const DashboardScreen: React.FC = () => {
  const { data, loading, error, selectedPeriod, fetchDashboard, setPeriod } =
    useDashboardStore();
  const [refreshing, setRefreshing] = useState(false);

  const loadCore = useCallback(
    () => fetchDashboard(),
    [fetchDashboard]
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

  if (loading && !data) {
    return <LoadingSpinner text="加载看板数据..." />;
  }

  if (error && !data) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重新加载"
        onAction={() => loadData()}
      />
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadData(true)}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* Period selector */}
      <View style={styles.periodContainer}>
        {PERIODS.map((p) => (
          <TouchableOpacity
            key={p.key}
            style={[styles.periodBtn, selectedPeriod === p.key && styles.periodBtnActive]}
            onPress={() => setPeriod(p.key)}
           accessibilityRole="button">
            <Text style={[styles.periodBtnText, selectedPeriod === p.key && styles.periodBtnTextActive]}>
              {p.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Stats Overview */}
      <Text style={styles.sectionTitle}>工单统计</Text>
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: '#e3f2fd' }]}>
          <Text style={[styles.statNumber, { color: '#1565c0' }]}>{data?.stats.totalOrders ?? '-'}</Text>
          <Text style={styles.statLabel}>总工单</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#e8f5e9' }]}>
          <Text style={[styles.statNumber, { color: '#2e7d32' }]}>{data?.stats.completedOrders ?? '-'}</Text>
          <Text style={styles.statLabel}>已完成</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fff8e1' }]}>
          <Text style={[styles.statNumber, { color: '#f57f17' }]}>{data?.stats.pendingOrders ?? '-'}</Text>
          <Text style={styles.statLabel}>待处理</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#f3e5f5' }]}>
          <Text style={[styles.statNumber, { color: '#7b1fa2' }]}>{data?.stats.avgCompletionHours ?? '-'}h</Text>
          <Text style={styles.statLabel}>平均完成</Text>
        </View>
      </View>

      {/* On-time rate */}
      <View style={styles.rateCard}>
        <Text style={styles.rateLabel}>按时完成率</Text>
        <Text style={styles.rateNumber}>{data?.stats.onTimeRate ?? '-'}%</Text>
        <View style={styles.rateBarBg}>
          <View style={[styles.rateBarFill, { width: `${Math.min(data?.stats.onTimeRate ?? 0, 100)}%` }]} />
        </View>
      </View>

      {/* Device Health */}
      <Text style={styles.sectionTitle}>设备健康度</Text>
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: '#e8f5e9' }]}>
          <Text style={[styles.statNumber, { color: '#2e7d32' }]}>{data?.deviceHealth.online ?? '-'}</Text>
          <Text style={styles.statLabel}>在线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fce4ec' }]}>
          <Text style={[styles.statNumber, { color: '#c62828' }]}>{data?.deviceHealth.offline ?? '-'}</Text>
          <Text style={styles.statLabel}>离线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fff3e0' }]}>
          <Text style={[styles.statNumber, { color: '#e65100' }]}>{data?.deviceHealth.fault ?? '-'}</Text>
          <Text style={styles.statLabel}>故障</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#e3f2fd' }]}>
          <Text style={[styles.statNumber, { color: '#1565c0' }]}>{data?.deviceHealth.onlineRate ?? '-'}%</Text>
          <Text style={styles.statLabel}>在线率</Text>
        </View>
      </View>

      {/* Alarm Trends */}
      <Text style={styles.sectionTitle}>告警趋势</Text>
      <View style={styles.chartCard}>
        {data?.alarmTrends && data.alarmTrends.length > 0 ? (
          <View>
            <View style={styles.legendRow}>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#c62828' }]} />
                <Text style={styles.legendText}>严重</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#e65100' }]} />
                <Text style={styles.legendText}>警告</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#1565c0' }]} />
                <Text style={styles.legendText}>信息</Text>
              </View>
            </View>
            <View style={styles.chartRow}>
              {data.alarmTrends.map((trend) => (
                <View key={trend.date} style={styles.chartCol}>
                  <View style={styles.stackedBar}>
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.critical * 5), backgroundColor: '#c62828' }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.warning * 5), backgroundColor: '#e65100' }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.info * 5), backgroundColor: '#1565c0' }]} />
                  </View>
                  <Text style={styles.chartLabel}>{trend.date.slice(5)}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : (
          <Text style={styles.noDataText}>暂无告警趋势数据</Text>
        )}
      </View>

      {/* Work Order Trends */}
      <Text style={styles.sectionTitle}>工单趋势</Text>
      <View style={styles.chartCard}>
        {data?.workOrderTrends && data.workOrderTrends.length > 0 ? (
          <View>
            <View style={styles.legendRow}>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#1565c0' }]} />
                <Text style={styles.legendText}>新建</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#2e7d32' }]} />
                <Text style={styles.legendText}>完成</Text>
              </View>
            </View>
            <View style={styles.chartRow}>
              {data.workOrderTrends.map((trend) => (
                <View key={trend.date} style={styles.chartCol}>
                  <View style={styles.stackedBar}>
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.created * 3), backgroundColor: '#1565c0' }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.completed * 3), backgroundColor: '#2e7d32' }]} />
                  </View>
                  <Text style={styles.chartLabel}>{trend.date.slice(5)}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : (
          <Text style={styles.noDataText}>暂无工单趋势数据</Text>
        )}
      </View>

      {/* Top Fault Devices */}
      <Text style={styles.sectionTitle}>故障设备 Top 5</Text>
      <View style={styles.topListCard}>
        {data?.topFaultDevices && data.topFaultDevices.length > 0 ? (
          data.topFaultDevices.map((device, idx) => (
            <View key={device.deviceId} style={[styles.topItem, idx < (data?.topFaultDevices?.length || 1) - 1 && styles.topItemBorder]}>
              <View style={styles.topRank}>
                <Text style={[styles.topRankText, idx < 3 && { color: '#c62828' }]}>{idx + 1}</Text>
              </View>
              <View style={styles.topInfo}>
                <Text style={styles.topName} numberOfLines={1}>{device.deviceName}</Text>
                <Text style={styles.topStation} numberOfLines={1}>{device.stationName}</Text>
              </View>
              <View style={styles.topFaultBadge}>
                <Text style={styles.topFaultText}>{device.faultCount}次</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.noDataText}>暂无故障设备数据</Text>
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f6fa' },
  content: { padding: 16, paddingBottom: 40 },
  periodContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 4,
    marginBottom: 16,
  },
  periodBtn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 8 },
  periodBtnActive: { backgroundColor: '#1a73e8' },
  periodBtnText: { fontSize: 14, fontWeight: '500', color: '#666' },
  periodBtnTextActive: { color: '#fff' },
  sectionTitle: { fontSize: 18, fontWeight: '600', color: '#333', marginBottom: 12, marginTop: 8 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 8 },
  statCard: { width: '47%', borderRadius: 12, padding: 16, alignItems: 'center' },
  statNumber: { fontSize: 28, fontWeight: 'bold' },
  statLabel: { fontSize: 13, color: '#666', marginTop: 4 },
  rateCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  rateLabel: { fontSize: 14, color: '#999', marginBottom: 4 },
  rateNumber: { fontSize: 36, fontWeight: 'bold', color: '#2e7d32', marginBottom: 10 },
  rateBarBg: { height: 8, backgroundColor: '#e0e0e0', borderRadius: 4, overflow: 'hidden' },
  rateBarFill: { height: 8, backgroundColor: '#2e7d32', borderRadius: 4 },
  chartCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  legendRow: { flexDirection: 'row', justifyContent: 'center', gap: 16, marginBottom: 12 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { fontSize: 12, color: '#666' },
  chartRow: { flexDirection: 'row', justifyContent: 'space-around', alignItems: 'flex-end' },
  chartCol: { alignItems: 'center', gap: 4 },
  stackedBar: { flexDirection: 'column', alignItems: 'center', gap: 1 },
  stackSegment: { width: 16, borderRadius: 2, minHeight: 2 },
  chartLabel: { fontSize: 10, color: '#999' },
  noDataText: { textAlign: 'center', fontSize: 14, color: '#999', paddingVertical: 16 },
  topListCard: { backgroundColor: '#fff', borderRadius: 12, padding: 4, marginBottom: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  topItem: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  topItemBorder: { borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  topRank: { width: 28, height: 28, borderRadius: 14, backgroundColor: '#f5f5f5', justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  topRankText: { fontSize: 14, fontWeight: 'bold', color: '#666' },
  topInfo: { flex: 1, marginRight: 12 },
  topName: { fontSize: 14, fontWeight: '500', color: '#333' },
  topStation: { fontSize: 12, color: '#999', marginTop: 2 },
  topFaultBadge: { paddingHorizontal: 10, paddingVertical: 4, backgroundColor: '#fce4ec', borderRadius: 12 },
  topFaultText: { fontSize: 12, fontWeight: '500', color: '#c62828' },
});

export default DashboardScreen;

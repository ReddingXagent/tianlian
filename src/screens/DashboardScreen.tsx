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
import { useTheme } from '../hooks/useTheme';

const PERIODS: { key: 'week' | 'month' | 'quarter'; label: string }[] = [
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
  { key: 'quarter', label: '季' },
];

const DashboardScreen: React.FC = () => {
  const { colors } = useTheme();
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
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadData(true)}
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* Period selector */}
      <View style={[styles.periodContainer, { backgroundColor: colors.cardBg }]}>
        {PERIODS.map((p) => (
          <TouchableOpacity
            key={p.key}
            style={[styles.periodBtn, { backgroundColor: selectedPeriod === p.key ? colors.primary : 'transparent' }]}
            onPress={() => setPeriod(p.key)}
           accessibilityRole="button">
            <Text style={[styles.periodBtnText, { color: selectedPeriod === p.key ? colors.onPrimary : colors.textSecondary }]}>
              {p.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Stats Overview */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>工单统计</Text>
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: colors.infoBg }]}>
          <Text style={[styles.statNumber, { color: colors.info }]}>{data?.stats.totalOrders ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>总工单</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.successBg }]}>
          <Text style={[styles.statNumber, { color: colors.success }]}>{data?.stats.completedOrders ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>已完成</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.warningAmberBg }]}>
          <Text style={[styles.statNumber, { color: colors.warningAmber }]}>{data?.stats.pendingOrders ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>待处理</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.purpleBg }]}>
          <Text style={[styles.statNumber, { color: colors.purple }]}>{data?.stats.avgCompletionHours ?? '-'}h</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>平均完成</Text>
        </View>
      </View>

      {/* On-time rate */}
      <View style={[styles.rateCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.rateLabel, { color: colors.textSecondary }]}>按时完成率</Text>
        <Text style={[styles.rateNumber, { color: colors.success }]}>{data?.stats.onTimeRate ?? '-'}%</Text>
        <View style={[styles.rateBarBg, { backgroundColor: colors.neutralBg }]}>
          <View style={[styles.rateBarFill, { backgroundColor: colors.success, width: `${Math.min(data?.stats.onTimeRate ?? 0, 100)}%` }]} />
        </View>
      </View>

      {/* Device Health */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>设备健康度</Text>
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: colors.successBg }]}>
          <Text style={[styles.statNumber, { color: colors.success }]}>{data?.deviceHealth.online ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>在线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.errorBg }]}>
          <Text style={[styles.statNumber, { color: colors.error }]}>{data?.deviceHealth.offline ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>离线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.warningBg }]}>
          <Text style={[styles.statNumber, { color: colors.warning }]}>{data?.deviceHealth.fault ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>故障</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.infoBg }]}>
          <Text style={[styles.statNumber, { color: colors.info }]}>{data?.deviceHealth.onlineRate ?? '-'}%</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>在线率</Text>
        </View>
      </View>

      {/* Alarm Trends */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>告警趋势</Text>
      <View style={[styles.chartCard, { backgroundColor: colors.cardBg }]}>
        {data?.alarmTrends && data.alarmTrends.length > 0 ? (
          <View>
            <View style={styles.legendRow}>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: colors.error }]} />
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>严重</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: colors.warning }]} />
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>警告</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: colors.info }]} />
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>信息</Text>
              </View>
            </View>
            <View style={styles.chartRow}>
              {data.alarmTrends.map((trend) => (
                <View key={trend.date} style={styles.chartCol}>
                  <View style={styles.stackedBar}>
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.critical * 5), backgroundColor: colors.error }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.warning * 5), backgroundColor: colors.warning }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.info * 5), backgroundColor: colors.info }]} />
                  </View>
                  <Text style={[styles.chartLabel, { color: colors.textSecondary }]}>{trend.date.slice(5)}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : (
          <Text style={[styles.noDataText, { color: colors.textSecondary }]}>暂无告警趋势数据</Text>
        )}
      </View>

      {/* Work Order Trends */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>工单趋势</Text>
      <View style={[styles.chartCard, { backgroundColor: colors.cardBg }]}>
        {data?.workOrderTrends && data.workOrderTrends.length > 0 ? (
          <View>
            <View style={styles.legendRow}>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: colors.info }]} />
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>新建</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: colors.success }]} />
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>完成</Text>
              </View>
            </View>
            <View style={styles.chartRow}>
              {data.workOrderTrends.map((trend) => (
                <View key={trend.date} style={styles.chartCol}>
                  <View style={styles.stackedBar}>
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.created * 3), backgroundColor: colors.info }]} />
                    <View style={[styles.stackSegment, { height: Math.max(2, trend.completed * 3), backgroundColor: colors.success }]} />
                  </View>
                  <Text style={[styles.chartLabel, { color: colors.textSecondary }]}>{trend.date.slice(5)}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : (
          <Text style={[styles.noDataText, { color: colors.textSecondary }]}>暂无工单趋势数据</Text>
        )}
      </View>

      {/* Top Fault Devices */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>故障设备 Top 5</Text>
      <View style={[styles.topListCard, { backgroundColor: colors.cardBg }]}>
        {data?.topFaultDevices && data.topFaultDevices.length > 0 ? (
          data.topFaultDevices.map((device, idx) => (
            <View key={device.deviceId} style={[styles.topItem, idx < data.topFaultDevices.length - 1 && { borderBottomWidth: 1, borderBottomColor: colors.divider }]}>
              <View style={[styles.topRank, { backgroundColor: colors.neutralBg }]}>
                <Text style={[styles.topRankText, { color: colors.textSecondary }, idx < 3 && { color: colors.error }]}>{idx + 1}</Text>
              </View>
              <View style={styles.topInfo}>
                <Text style={[styles.topName, { color: colors.textPrimary }]} numberOfLines={1}>{device.deviceName}</Text>
                <Text style={[styles.topStation, { color: colors.textSecondary }]} numberOfLines={1}>{device.stationName}</Text>
              </View>
              <View style={[styles.topFaultBadge, { backgroundColor: colors.errorBg }]}>
                <Text style={[styles.topFaultText, { color: colors.error }]}>{device.faultCount}次</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={[styles.noDataText, { color: colors.textSecondary }]}>暂无故障设备数据</Text>
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  periodContainer: {
    flexDirection: 'row',
    borderRadius: 10,
    padding: 4,
    marginBottom: 16,
  },
  periodBtn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 8 },
  periodBtnText: { fontSize: 14, fontWeight: '500' },
  sectionTitle: { fontSize: 18, fontWeight: '600', marginBottom: 12, marginTop: 8 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 8 },
  statCard: { width: '47%', borderRadius: 12, padding: 16, alignItems: 'center' },
  statNumber: { fontSize: 28, fontWeight: 'bold' },
  statLabel: { fontSize: 13, marginTop: 4 },
  rateCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  rateLabel: { fontSize: 14, marginBottom: 4 },
  rateNumber: { fontSize: 36, fontWeight: 'bold', marginBottom: 10 },
  rateBarBg: { height: 8, borderRadius: 4, overflow: 'hidden' },
  rateBarFill: { height: 8, borderRadius: 4 },
  chartCard: {
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
  legendText: { fontSize: 12 },
  chartRow: { flexDirection: 'row', justifyContent: 'space-around', alignItems: 'flex-end' },
  chartCol: { alignItems: 'center', gap: 4 },
  stackedBar: { flexDirection: 'column', alignItems: 'center', gap: 1 },
  stackSegment: { width: 16, borderRadius: 2, minHeight: 2 },
  chartLabel: { fontSize: 10 },
  noDataText: { textAlign: 'center', fontSize: 14, paddingVertical: 16 },
  topListCard: { borderRadius: 12, padding: 4, marginBottom: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  topItem: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  topRank: { width: 28, height: 28, borderRadius: 14, justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  topRankText: { fontSize: 14, fontWeight: 'bold' },
  topInfo: { flex: 1, marginRight: 12 },
  topName: { fontSize: 14, fontWeight: '500' },
  topStation: { fontSize: 12, marginTop: 2 },
  topFaultBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  topFaultText: { fontSize: 12, fontWeight: '500' },
});

export default DashboardScreen;

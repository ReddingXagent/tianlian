import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, RefreshControl,
  ScrollView, ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../store/authStore';
import { useDashboard } from '../hooks/useDashboard';
import { RootStackParamList } from '../types';
import { useTheme } from '../hooks/useTheme';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function DashboardScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NavProp>();
  const { user } = useAuthStore();
  const { stats, refreshing, loading, refresh, stations } = useDashboard();

  if (loading && !refreshing) {
    return (
      <View style={[styles.center, { backgroundColor: colors.pageBg }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const onlineStations = stations.filter((s) => s.status === 'online').length;

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.primary} />}
    >
      {/* 欢迎区 */}
      <View style={styles.welcome}>
        <Text style={[styles.greeting, { color: colors.textPrimary }]}>你好，{user?.nickname || user?.username || '站长'}</Text>
        <Text style={[styles.dateText, { color: colors.textSecondary }]}>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</Text>
      </View>

      {/* 统计卡片 */}
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { backgroundColor: colors.cardBg, borderLeftColor: colors.primary }]}>
          <Text style={[styles.statValue, { color: colors.textPrimary }]}>{stats?.totalStations ?? stations.length}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>总站点</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.cardBg, borderLeftColor: colors.success }]}>
          <Text style={[styles.statValue, { color: colors.textPrimary }]}>{stats?.onlineStations ?? onlineStations}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>在线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.cardBg, borderLeftColor: colors.error }]}>
          <Text style={[styles.statValue, { color: colors.textPrimary }]}>{stats?.unhandledAlarms ?? '-'}</Text>
          <Text style={[styles.statLabel, { color: colors.textSecondary }]}>待处理告警</Text>
        </View>
      </View>

      {/* 营收摘要 */}
      {stats?.revenueSummary && (
        <View style={[styles.revenueCard, { backgroundColor: colors.cardBg }]}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>营收概览</Text>
          <View style={styles.revenueRow}>
            <View style={styles.revenueItem}>
              <Text style={[styles.revenueAmount, { color: colors.primary }]}>¥{stats.revenueSummary.today.toFixed(2)}</Text>
              <Text style={[styles.revenueLabel, { color: colors.textSecondary }]}>今日</Text>
            </View>
            <View style={styles.revenueItem}>
              <Text style={[styles.revenueAmount, { color: colors.primary }]}>¥{stats.revenueSummary.week.toFixed(2)}</Text>
              <Text style={[styles.revenueLabel, { color: colors.textSecondary }]}>本周</Text>
            </View>
            <View style={styles.revenueItem}>
              <Text style={[styles.revenueAmount, { color: colors.primary }]}>¥{stats.revenueSummary.month.toFixed(2)}</Text>
              <Text style={[styles.revenueLabel, { color: colors.textSecondary }]}>本月</Text>
            </View>
          </View>
        </View>
      )}

      {/* 快捷入口 */}
      <View style={styles.quickActions}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>快捷操作</Text>
        <View style={styles.actionGrid}>
          <TouchableOpacity
            style={[styles.actionItem, { backgroundColor: colors.cardBg }]}
            onPress={() => navigation.navigate('Stations' as never)}
           accessibilityRole="button">
            <Text style={styles.actionIcon}>📍</Text>
            <Text style={[styles.actionText, { color: colors.textSecondary }]}>站点管理</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionItem, { backgroundColor: colors.cardBg }]}
            onPress={() => navigation.navigate('AlarmList' as never)}
           accessibilityRole="button">
            <Text style={styles.actionIcon}>🔔</Text>
            <Text style={[styles.actionText, { color: colors.textSecondary }]}>告警查看</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionItem, { backgroundColor: colors.cardBg }]}
            onPress={() => navigation.navigate('WorkOrder' as never)}
           accessibilityRole="button">
            <Text style={styles.actionIcon}>📋</Text>
            <Text style={[styles.actionText, { color: colors.textSecondary }]}>工单管理</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionItem, { backgroundColor: colors.cardBg }]}
            onPress={() => navigation.navigate('Revenue' as never)}
           accessibilityRole="button">
            <Text style={styles.actionIcon}>💰</Text>
            <Text style={[styles.actionText, { color: colors.textSecondary }]}>营收统计</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 站点列表预览 */}
      <View style={styles.stationPreview}>
        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>我的站点</Text>
          <TouchableOpacity onPress={() => navigation.navigate('Stations' as never)} accessibilityRole="button">
            <Text style={[styles.seeAll, { color: colors.primary }]}>查看全部 →</Text>
          </TouchableOpacity>
        </View>
        {stations.slice(0, 3).map((station) => (
          <TouchableOpacity
            key={station.id}
            style={[styles.stationItem, { backgroundColor: colors.cardBg }]}
            onPress={() => navigation.navigate('StationDetail', { stationId: station.id })}
           accessibilityRole="button">
            <View style={styles.stationInfo}>
              <Text style={[styles.stationName, { color: colors.textPrimary }]}>{station.name}</Text>
              <Text style={[styles.stationAddr, { color: colors.textMuted }]}>{station.address}</Text>
            </View>
            <View style={[styles.statusBadge, { backgroundColor: station.status === 'online' ? colors.successBg : colors.errorBg }]}>
              <Text style={[styles.statusText, { color: station.status === 'online' ? colors.success : colors.error }]}>{station.status === 'online' ? '在线' : '离线'}</Text>
            </View>
          </TouchableOpacity>
        ))}
        {stations.length === 0 && (
          <Text style={[styles.emptyText, { color: colors.textMuted }]}>暂无站点数据</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  welcome: { padding: 20, paddingTop: 10 },
  greeting: { fontSize: 24, fontWeight: 'bold' },
  dateText: { fontSize: 14, marginTop: 4 },
  statsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 12 },
  statCard: {
    flex: 1, borderRadius: 12, padding: 16,
    borderLeftWidth: 3,
  },
  statValue: { fontSize: 28, fontWeight: 'bold' },
  statLabel: { fontSize: 12, marginTop: 4 },
  revenueCard: { margin: 16, borderRadius: 12, padding: 20 },
  sectionTitle: { fontSize: 16, fontWeight: '600', marginBottom: 12 },
  revenueRow: { flexDirection: 'row', justifyContent: 'space-around' },
  revenueItem: { alignItems: 'center' },
  revenueAmount: { fontSize: 20, fontWeight: 'bold' },
  revenueLabel: { fontSize: 12, marginTop: 4 },
  quickActions: { padding: 16 },
  actionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  actionItem: {
    width: '47%', borderRadius: 12,
    padding: 20, alignItems: 'center', gap: 8,
  },
  actionIcon: { fontSize: 32 },
  actionText: { fontSize: 14 },
  stationPreview: { padding: 16, paddingBottom: 40 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  seeAll: { fontSize: 14 },
  stationItem: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    borderRadius: 10, padding: 16, marginBottom: 8,
  },
  stationInfo: { flex: 1 },
  stationName: { fontSize: 16, fontWeight: '600' },
  stationAddr: { fontSize: 12, marginTop: 4 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusText: { fontSize: 12 },
  emptyText: { textAlign: 'center', paddingVertical: 20 },
});

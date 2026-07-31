/* eslint-disable react-hooks/set-state-in-effect */
import React, { useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, RefreshControl,
  ScrollView, ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../store/authStore';
import { useStationStore } from '../store/stationStore';
import { useWorkOrderStore } from '../store/workOrderStore';
import { dashboardApi } from '../services/api';
import { RootStackParamList, DashboardStats } from '../types';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function DashboardScreen() {
  const navigation = useNavigation<NavProp>();
  const { user } = useAuthStore();
  const { stations, fetchStations } = useStationStore();
  const { fetchOrders } = useWorkOrderStore();
  const [refreshing, setRefreshing] = React.useState(false);
  const [stats, setStats] = React.useState<DashboardStats | null>(null);
  const [loading, setLoading] = React.useState(true);

  const loadDashboard = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        fetchStations({ page: 1, pageSize: 100 }),
        fetchOrders({ page: 1, pageSize: 5 }),
      ]);
      try {
        const resp = await dashboardApi.getStats();
        setStats(resp.data);
      } catch {
        // Stats API may not be ready
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchStations, fetchOrders]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  if (loading && !refreshing) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#4ECDC4" />
      </View>
    );
  }

  const onlineStations = stations.filter((s) => s.status === 'online').length;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadDashboard} tintColor="#4ECDC4" />}
    >
      {/* 欢迎区 */}
      <View style={styles.welcome}>
        <Text style={styles.greeting}>你好，{user?.nickname || user?.username || '站长'}</Text>
        <Text style={styles.dateText}>{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</Text>
      </View>

      {/* 统计卡片 */}
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { borderLeftColor: '#4ECDC4' }]}>
          <Text style={styles.statValue}>{stats?.totalStations ?? stations.length}</Text>
          <Text style={styles.statLabel}>总站点</Text>
        </View>
        <View style={[styles.statCard, { borderLeftColor: '#27ae60' }]}>
          <Text style={styles.statValue}>{stats?.onlineStations ?? onlineStations}</Text>
          <Text style={styles.statLabel}>在线</Text>
        </View>
        <View style={[styles.statCard, { borderLeftColor: '#e74c3c' }]}>
          <Text style={styles.statValue}>{stats?.unhandledAlarms ?? '-'}</Text>
          <Text style={styles.statLabel}>待处理告警</Text>
        </View>
      </View>

      {/* 营收摘要 */}
      {stats?.revenueSummary && (
        <View style={styles.revenueCard}>
          <Text style={styles.sectionTitle}>营收概览</Text>
          <View style={styles.revenueRow}>
            <View style={styles.revenueItem}>
              <Text style={styles.revenueAmount}>¥{stats.revenueSummary.today.toFixed(2)}</Text>
              <Text style={styles.revenueLabel}>今日</Text>
            </View>
            <View style={styles.revenueItem}>
              <Text style={styles.revenueAmount}>¥{stats.revenueSummary.week.toFixed(2)}</Text>
              <Text style={styles.revenueLabel}>本周</Text>
            </View>
            <View style={styles.revenueItem}>
              <Text style={styles.revenueAmount}>¥{stats.revenueSummary.month.toFixed(2)}</Text>
              <Text style={styles.revenueLabel}>本月</Text>
            </View>
          </View>
        </View>
      )}

      {/* 快捷入口 */}
      <View style={styles.quickActions}>
        <Text style={styles.sectionTitle}>快捷操作</Text>
        <View style={styles.actionGrid}>
          <TouchableOpacity
            style={styles.actionItem}
            onPress={() => navigation.navigate('Stations' as never)}
          >
            <Text style={styles.actionIcon}>📍</Text>
            <Text style={styles.actionText}>站点管理</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionItem}
            onPress={() => navigation.navigate('AlarmList' as never)}
          >
            <Text style={styles.actionIcon}>🔔</Text>
            <Text style={styles.actionText}>告警查看</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionItem}
            onPress={() => navigation.navigate('WorkOrder' as never)}
          >
            <Text style={styles.actionIcon}>📋</Text>
            <Text style={styles.actionText}>工单管理</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionItem}
            onPress={() => navigation.navigate('Revenue' as never)}
          >
            <Text style={styles.actionIcon}>💰</Text>
            <Text style={styles.actionText}>营收统计</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 站点列表预览 */}
      <View style={styles.stationPreview}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>我的站点</Text>
          <TouchableOpacity onPress={() => navigation.navigate('Stations' as never)}>
            <Text style={styles.seeAll}>查看全部 →</Text>
          </TouchableOpacity>
        </View>
        {stations.slice(0, 3).map((station) => (
          <TouchableOpacity
            key={station.id}
            style={styles.stationItem}
            onPress={() => navigation.navigate('StationDetail', { stationId: station.id })}
          >
            <View style={styles.stationInfo}>
              <Text style={styles.stationName}>{station.name}</Text>
              <Text style={styles.stationAddr}>{station.address}</Text>
            </View>
            <View style={[styles.statusBadge, station.status === 'online' ? styles.statusOnline : styles.statusOffline]}>
              <Text style={styles.statusText}>{station.status === 'online' ? '在线' : '离线'}</Text>
            </View>
          </TouchableOpacity>
        ))}
        {stations.length === 0 && (
          <Text style={styles.emptyText}>暂无站点数据</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f0f23' },
  welcome: { padding: 20, paddingTop: 10 },
  greeting: { fontSize: 24, fontWeight: 'bold', color: '#fff' },
  dateText: { fontSize: 14, color: '#888', marginTop: 4 },
  statsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 12 },
  statCard: {
    flex: 1, backgroundColor: '#1a1a2e', borderRadius: 12, padding: 16,
    borderLeftWidth: 3,
  },
  statValue: { fontSize: 28, fontWeight: 'bold', color: '#fff' },
  statLabel: { fontSize: 12, color: '#888', marginTop: 4 },
  revenueCard: { margin: 16, backgroundColor: '#1a1a2e', borderRadius: 12, padding: 20 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#fff', marginBottom: 12 },
  revenueRow: { flexDirection: 'row', justifyContent: 'space-around' },
  revenueItem: { alignItems: 'center' },
  revenueAmount: { fontSize: 20, fontWeight: 'bold', color: '#4ECDC4' },
  revenueLabel: { fontSize: 12, color: '#888', marginTop: 4 },
  quickActions: { padding: 16 },
  actionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  actionItem: {
    width: '47%', backgroundColor: '#1a1a2e', borderRadius: 12,
    padding: 20, alignItems: 'center', gap: 8,
  },
  actionIcon: { fontSize: 32 },
  actionText: { fontSize: 14, color: '#ccc' },
  stationPreview: { padding: 16, paddingBottom: 40 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  seeAll: { fontSize: 14, color: '#4ECDC4' },
  stationItem: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: '#1a1a2e', borderRadius: 10, padding: 16, marginBottom: 8,
  },
  stationInfo: { flex: 1 },
  stationName: { fontSize: 16, fontWeight: '600', color: '#fff' },
  stationAddr: { fontSize: 12, color: '#666', marginTop: 4 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusOnline: { backgroundColor: 'rgba(39,174,96,0.2)' },
  statusOffline: { backgroundColor: 'rgba(231,76,60,0.2)' },
  statusText: { fontSize: 12, color: '#fff' },
  emptyText: { color: '#666', textAlign: 'center', paddingVertical: 20 },
});

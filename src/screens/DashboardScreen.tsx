import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { dashboardApi } from '../services/api';
import { DashboardStats, Alarm, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

const DashboardScreen: React.FC = () => {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentAlarms, setRecentAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [statsRes, alarmsRes] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getRecentAlarms(5),
      ]);
      setStats(statsRes.data);
      setRecentAlarms(alarmsRes.data);
    } catch {
      setError('加载数据失败，请下拉刷新重试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading && !refreshing) {
    return <LoadingSpinner text="加载仪表盘..." />;
  }

  if (error && !stats) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重新加载"
        onAction={() => fetchData()}
      />
    );
  }

  const alarmLevelIcon = (level: string) => {
    switch (level) {
      case 'critical': return '🔴';
      case 'warning': return '🟡';
      case 'info': return '🔵';
      default: return '⚪';
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => fetchData(true)}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* 站点概览 */}
      <Text style={styles.sectionTitle}>站点概览</Text>
      <View style={styles.statsGrid}>
        <View style={[styles.statCard, { backgroundColor: '#e3f2fd' }]}>
          <Text style={[styles.statNumber, { color: '#1565c0' }]}>
            {stats?.totalStations ?? '-'}
          </Text>
          <Text style={styles.statLabel}>总站点</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#e8f5e9' }]}>
          <Text style={[styles.statNumber, { color: '#2e7d32' }]}>
            {stats?.onlineStations ?? '-'}
          </Text>
          <Text style={styles.statLabel}>在线</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fce4ec' }]}>
          <Text style={[styles.statNumber, { color: '#c62828' }]}>
            {stats?.unhandledAlarms ?? '-'}
          </Text>
          <Text style={styles.statLabel}>未处理告警</Text>
        </View>
      </View>

      {/* 营收摘要 */}
      <Text style={styles.sectionTitle}>营收摘要</Text>
      <View style={styles.revenueCard}>
        <View style={styles.revenueRow}>
          <View style={styles.revenueItem}>
            <Text style={styles.revenueLabel}>今日</Text>
            <Text style={styles.revenueAmount}>
              ¥{(stats?.revenueSummary?.today ?? 0).toFixed(2)}
            </Text>
          </View>
          <View style={styles.revenueDivider} />
          <View style={styles.revenueItem}>
            <Text style={styles.revenueLabel}>本周</Text>
            <Text style={styles.revenueAmount}>
              ¥{(stats?.revenueSummary?.week ?? 0).toFixed(2)}
            </Text>
          </View>
        </View>
        <View style={styles.revenueDividerHorizontal} />
        <View style={styles.revenueRow}>
          <View style={styles.revenueItem}>
            <Text style={styles.revenueLabel}>本月</Text>
            <Text style={styles.revenueAmount}>
              ¥{(stats?.revenueSummary?.month ?? 0).toFixed(2)}
            </Text>
          </View>
          <View style={styles.revenueDivider} />
          <View style={styles.revenueItem}>
            <Text style={styles.revenueLabel}>累计</Text>
            <Text style={[styles.revenueAmount, { color: '#1a73e8' }]}>
              ¥{(stats?.revenueSummary?.total ?? 0).toFixed(2)}
            </Text>
          </View>
        </View>
      </View>

      {/* 快速入口 */}
      <Text style={styles.sectionTitle}>快捷操作</Text>
      <View style={styles.quickActions}>
        <TouchableOpacity
          style={styles.quickActionCard}
          onPress={() => navigation.navigate('AlarmList', {})}
          activeOpacity={0.7}
        >
          <Text style={styles.quickActionIcon}>🔔</Text>
          <Text style={styles.quickActionLabel}>告警列表</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickActionCard}
          onPress={() => navigation.navigate('NotificationCenter')}
          activeOpacity={0.7}
        >
          <Text style={styles.quickActionIcon}>📬</Text>
          <Text style={styles.quickActionLabel}>消息中心</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickActionCard}
          onPress={() => navigation.navigate('Revenue')}
          activeOpacity={0.7}
        >
          <Text style={styles.quickActionIcon}>💰</Text>
          <Text style={styles.quickActionLabel}>营收统计</Text>
        </TouchableOpacity>
      </View>

      {/* 最近告警 */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>最近告警</Text>
        <TouchableOpacity onPress={() => navigation.navigate('AlarmList', {})}>
          <Text style={styles.viewAll}>查看全部</Text>
        </TouchableOpacity>
      </View>
      {recentAlarms.length === 0 ? (
        <View style={styles.emptyAlarm}>
          <Text style={styles.emptyAlarmText}>暂无告警</Text>
        </View>
      ) : (
        recentAlarms.map((alarm) => (
          <View key={alarm.id} style={styles.alarmItem}>
            <Text style={styles.alarmIcon}>{alarmLevelIcon(alarm.level)}</Text>
            <View style={styles.alarmContent}>
              <Text style={styles.alarmTitle} numberOfLines={1}>
                {alarm.title}
              </Text>
              <Text style={styles.alarmStation} numberOfLines={1}>
                {alarm.stationName}
              </Text>
            </View>
            <StatusBadge status={alarm.level as 'critical' | 'warning' | 'info'} />
          </View>
        ))
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
    paddingBottom: 32,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 12,
    marginTop: 8,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
    marginTop: 8,
  },
  viewAll: {
    fontSize: 14,
    color: '#1a73e8',
  },
  statsGrid: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
  },
  statCard: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statNumber: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  statLabel: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
  revenueCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 8,
  },
  revenueRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  revenueItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 8,
  },
  revenueLabel: {
    fontSize: 13,
    color: '#999',
    marginBottom: 4,
  },
  revenueAmount: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  revenueDivider: {
    width: 1,
    height: 40,
    backgroundColor: '#eee',
  },
  revenueDividerHorizontal: {
    height: 1,
    backgroundColor: '#eee',
  },
  emptyAlarm: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  emptyAlarmText: {
    color: '#999',
    fontSize: 14,
  },
  alarmItem: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  alarmIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  alarmContent: {
    flex: 1,
    marginRight: 8,
  },
  alarmTitle: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
    marginBottom: 2,
  },
  alarmStation: {
    fontSize: 12,
    color: '#999',
  },
  quickActions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
  },
  quickActionCard: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  quickActionIcon: {
    fontSize: 24,
    marginBottom: 6,
  },
  quickActionLabel: {
    fontSize: 12,
    color: '#666',
    fontWeight: '500',
  },
});

export default DashboardScreen;
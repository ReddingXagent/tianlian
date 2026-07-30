import React, { useCallback } from 'react';
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
import { workbenchApi } from '../services/api';
import {
  WorkOrder,
  RootStackParamList,
  MainTabParamList,
} from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import WorkOrderCard from '../components/WorkOrderCard';
import { usePolling } from '../hooks/usePolling';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const QUICK_ACTIONS = [
  { key: 'scan', icon: '📷', label: '扫码签到', route: 'Scan' as const },
  { key: 'monitor', icon: '📊', label: '设备监控', route: 'Monitor' as const },
  { key: 'knowledge', icon: '📚', label: '知识库', route: 'Knowledge' as const },
  { key: 'diagnosis', icon: '🔍', label: '故障诊断', route: 'Diagnosis' as const },
];

const WorkbenchScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  // 并行获取工作台数据，15秒自动轮询
  const fetcher = useCallback(async () => {
    const [statsRes, ordersRes, alarmsRes] = await Promise.all([
      workbenchApi.getStats(),
      workbenchApi.getPendingOrders(5),
      workbenchApi.getRecentAlarms(5),
    ]);
    return {
      stats: statsRes.data,
      pendingOrders: ordersRes.data,
      recentAlarms: alarmsRes.data,
    };
  }, []);

  const { data, loading, error, refresh } = usePolling(fetcher, {
    interval: 15_000,
    enabled: true,
  });

  const stats = data?.stats ?? null;
  const pendingOrders = data?.pendingOrders ?? [];
  const recentAlarms = data?.recentAlarms ?? [];
  const refreshing = loading && stats !== null;

  const handleOrderPress = (order: WorkOrder) => {
    navigation.navigate('WorkOrderDetail', { orderId: order.id });
  };

  const handleNavigateTab = (screen: keyof MainTabParamList) => {
    navigation.navigate('Main', { screen } as never);
  };

  const handleNavigate = (route: keyof RootStackParamList) => {
    navigation.navigate(route as never);
  };

  if (loading && !stats) {
    return <LoadingSpinner text="加载工作台..." />;
  }

  if (error && !stats) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error.message}
        actionLabel="重新加载"
        onAction={refresh}
      />
    );
  }

  const alarmLevelIcon = (level: string) => {
    switch (level) {
      case 'critical':
        return '🔴';
      case 'warning':
        return '🟡';
      case 'info':
        return '🔵';
      default:
        return '⚪';
    }
  };

  // 统计工单紧急度
  const urgentCount = pendingOrders.filter((o) => o.priority === 'urgent').length;
  const highCount = pendingOrders.filter((o) => o.priority === 'high').length;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={refresh}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* 统计概览 */}
      <Text style={styles.sectionTitle}>今日概览</Text>
      <View style={styles.statsGrid}>
        <TouchableOpacity
          style={[styles.statCard, { backgroundColor: '#fff8e1' }]}
          activeOpacity={0.7}
          onPress={() => handleNavigateTab('WorkOrders')}
        >
          <Text style={[styles.statNumber, { color: '#f57f17' }]}>
            {stats?.pendingOrders ?? '-'}
          </Text>
          <Text style={styles.statLabel}>待处理工单</Text>
        </TouchableOpacity>
        <View style={[styles.statCard, { backgroundColor: '#e3f2fd' }]}>
          <Text style={[styles.statNumber, { color: '#1565c0' }]}>
            {stats?.inProgressOrders ?? '-'}
          </Text>
          <Text style={styles.statLabel}>进行中</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#e8f5e9' }]}>
          <Text style={[styles.statNumber, { color: '#2e7d32' }]}>
            {stats?.todayCompleted ?? '-'}
          </Text>
          <Text style={styles.statLabel}>今日完成</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fce4ec' }]}>
          <Text style={[styles.statNumber, { color: '#c62828' }]}>
            {stats?.unhandledAlarms ?? '-'}
          </Text>
          <Text style={styles.statLabel}>未处理告警</Text>
        </View>
      </View>

      {/* 紧急度汇总条 */}
      {(urgentCount > 0 || highCount > 0) && (
        <View style={styles.urgencyBar}>
          {urgentCount > 0 && (
            <View style={styles.urgencyItem}>
              <StatusBadge status="urgent" />
              <Text style={styles.urgencyCount}>{urgentCount}条紧急</Text>
            </View>
          )}
          {highCount > 0 && (
            <View style={styles.urgencyItem}>
              <StatusBadge status="high" />
              <Text style={styles.urgencyCount}>{highCount}条高优</Text>
            </View>
          )}
        </View>
      )}

      {/* 快捷入口 */}
      <Text style={styles.sectionTitle}>快捷操作</Text>
      <View style={styles.quickActions}>
        {QUICK_ACTIONS.map((action) => (
          <TouchableOpacity
            key={action.key}
            style={styles.quickActionBtn}
            onPress={() => {
              if (action.route === 'Scan' || action.route === 'Monitor') {
                handleNavigateTab(action.route);
              } else {
                handleNavigate(action.route as keyof RootStackParamList);
              }
            }}
            activeOpacity={0.7}
          >
            <Text style={styles.quickActionIcon}>{action.icon}</Text>
            <Text style={styles.quickActionLabel}>{action.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* 待办工单 */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>待办工单</Text>
        <TouchableOpacity onPress={() => handleNavigateTab('WorkOrders')}>
          <Text style={styles.viewAll}>
            查看全部 {stats && stats.pendingOrders > 0 ? `(${stats.pendingOrders})` : ''}
          </Text>
        </TouchableOpacity>
      </View>
      {pendingOrders.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>🎉</Text>
          <Text style={styles.emptyText}>暂无待办工单</Text>
        </View>
      ) : (
        pendingOrders.map((order) => (
          <WorkOrderCard
            key={order.id}
            order={order}
            onPress={handleOrderPress}
            compact
          />
        ))
      )}

      {/* 最近告警 */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>最近告警</Text>
        {stats && stats.criticalAlarms > 0 && (
          <Text style={styles.criticalBadge}>
            🔴 {stats.criticalAlarms}条严重
          </Text>
        )}
      </View>
      {recentAlarms.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>✅</Text>
          <Text style={styles.emptyText}>暂无告警</Text>
        </View>
      ) : (
        recentAlarms.map((alarm) => (
          <View key={alarm.id} style={styles.alarmItem}>
            <Text style={styles.alarmIcon}>
              {alarmLevelIcon(alarm.level)}
            </Text>
            <View style={styles.alarmContent}>
              <Text style={styles.alarmTitle} numberOfLines={1}>
                {alarm.title}
              </Text>
              <Text style={styles.alarmStation} numberOfLines={1}>
                {alarm.stationName}
              </Text>
            </View>
            <StatusBadge
              status={alarm.level as 'critical' | 'warning' | 'info'}
            />
          </View>
        ))
      )}

      {/* 底部间距 */}
      <View style={{ height: 20 }} />
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
  criticalBadge: {
    fontSize: 12,
    color: '#c62828',
    fontWeight: '500',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 8,
  },
  statCard: {
    width: '47%',
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
  urgencyBar: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 8,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  urgencyItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  urgencyCount: {
    fontSize: 12,
    color: '#666',
  },
  quickActions: {
    flexDirection: 'row',
    marginBottom: 8,
    gap: 10,
  },
  quickActionBtn: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  quickActionIcon: {
    fontSize: 28,
    marginBottom: 6,
  },
  quickActionLabel: {
    fontSize: 12,
    color: '#666',
    fontWeight: '500',
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    marginBottom: 8,
  },
  emptyIcon: {
    fontSize: 32,
    marginBottom: 8,
  },
  emptyText: {
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
});

export default WorkbenchScreen;

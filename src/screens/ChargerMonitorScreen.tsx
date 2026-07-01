import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { chargerApi } from '../services/api';
import { ChargerStatus, ChargerMonitorSummary, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import ChargerTrendChart from '../components/ChargerTrendChart';
import { usePolling } from '../hooks/usePolling';

type ChargerMonitorRouteProp = RouteProp<RootStackParamList, 'ChargerMonitor'>;

const CONNECTOR_STATUS_LABEL: Record<string, { label: string; icon: string; color: string }> = {
  idle:      { label: '空闲', icon: '⚪', color: '#999' },
  connected: { label: '已连接', icon: '🔵', color: '#1565c0' },
  charging:  { label: '充电中', icon: '⚡', color: '#2e7d32' },
  fault:     { label: '故障', icon: '🔴', color: '#c62828' },
  suspended: { label: '暂停', icon: '🟡', color: '#f57f17' },
};

const ChargerMonitorScreen: React.FC = () => {
  const route = useRoute<ChargerMonitorRouteProp>();
  const { stationId, stationName } = route.params;

  const [expandedChargerId, setExpandedChargerId] = useState<number | null>(null);

  // 并行获取充电桩列表+汇总，10秒自动轮询
  const fetcher = useCallback(async () => {
    const [chargersRes, summaryRes] = await Promise.all([
      chargerApi.getMonitorList(stationId),
      chargerApi.getMonitorSummary(stationId),
    ]);
    return { chargers: chargersRes.data, summary: summaryRes.data };
  }, [stationId]);

  const { data, loading, error, refresh } = usePolling(fetcher, {
    interval: 10_000,
    enabled: !!stationId,
  });

  const chargers = data?.chargers ?? [];
  const summary = data?.summary ?? null;
  const refreshing = loading && chargers.length > 0;

  if (loading && chargers.length === 0) {
    return <LoadingSpinner text="加载监控面板..." />;
  }

  if (error && chargers.length === 0) {
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

  const getConnectorConfig = (status: string) => {
    return CONNECTOR_STATUS_LABEL[status] || { label: status, icon: '❓', color: '#999' };
  };

  const formatDuration = (minutes: number): string => {
    if (minutes < 60) return `${minutes}分钟`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
  };

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
      {/* 站点名称 */}
      <Text style={styles.stationName}>{stationName}</Text>

      {/* 汇总卡片 */}
      {summary && (
        <View style={styles.summaryGrid}>
          <View style={[styles.summaryCard, { backgroundColor: '#e3f2fd' }]}>
            <Text style={styles.summaryNumber}>{summary.chargingCount}</Text>
            <Text style={styles.summaryLabel}>充电中</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#f5f5f5' }]}>
            <Text style={styles.summaryNumber}>{summary.idleCount}</Text>
            <Text style={styles.summaryLabel}>空闲</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#fce4ec' }]}>
            <Text style={[styles.summaryNumber, { color: '#c62828' }]}>{summary.faultCount}</Text>
            <Text style={styles.summaryLabel}>故障</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#e8f5e9' }]}>
            <Text style={[styles.summaryNumber, { color: '#2e7d32' }]}>
              {summary.totalPower.toFixed(1)}
            </Text>
            <Text style={styles.summaryLabel}>总功率kW</Text>
          </View>
        </View>
      )}

      {/* 今日统计 */}
      {summary && (
        <View style={styles.todayStats}>
          <View style={styles.todayItem}>
            <Text style={styles.todayValue}>{summary.todayEnergy.toFixed(0)}</Text>
            <Text style={styles.todayLabel}>今日充电 kWh</Text>
          </View>
          <View style={styles.todayDivider} />
          <View style={styles.todayItem}>
            <Text style={styles.todayValue}>{summary.todaySessions}</Text>
            <Text style={styles.todayLabel}>今日充电次数</Text>
          </View>
          <View style={styles.todayDivider} />
          <View style={styles.todayItem}>
            <Text style={styles.todayValue}>{summary.avgPowerPerCharger.toFixed(1)}</Text>
            <Text style={styles.todayLabel}>平均功率 kW</Text>
          </View>
        </View>
      )}

      {/* 充电桩列表 */}
      <Text style={styles.sectionTitle}>充电桩实时状态</Text>
      {chargers.length === 0 ? (
        <EmptyState icon="🔌" title="暂无充电桩" message="该站点暂无充电桩设备" />
      ) : (
        chargers.map((charger) => {
          const connectorConfig = getConnectorConfig(charger.connectorStatus);
          return (
            <View key={charger.id} style={styles.chargerCard}>
              {/* 头部（点击展开/收起实时趋势） */}
              <TouchableOpacity
                style={styles.chargerHeader}
                activeOpacity={0.7}
                onPress={() =>
                  setExpandedChargerId((prev) => (prev === charger.id ? null : charger.id))
                }
              >
                <View style={styles.chargerNameRow}>
                  <Text style={styles.chargerIcon}>🔌</Text>
                  <Text style={styles.chargerName} numberOfLines={1}>
                    {charger.deviceName}
                  </Text>
                </View>
                <View style={styles.headerRight}>
                  <StatusBadge status={charger.connectorStatus as any} label={connectorConfig.label} />
                  <Text style={styles.trendToggle}>
                    {expandedChargerId === charger.id ? '收起 ▴' : '趋势 ▾'}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* 实时数据 */}
              <View style={styles.metricsGrid}>
                <View style={styles.metricItem}>
                  <Text style={styles.metricValue}>
                    {charger.power.toFixed(1)}
                  </Text>
                  <Text style={styles.metricUnit}>kW</Text>
                  <Text style={styles.metricLabel}>功率</Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricValue}>
                    {charger.voltage.toFixed(0)}
                  </Text>
                  <Text style={styles.metricUnit}>V</Text>
                  <Text style={styles.metricLabel}>电压</Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={styles.metricValue}>
                    {charger.current.toFixed(1)}
                  </Text>
                  <Text style={styles.metricUnit}>A</Text>
                  <Text style={styles.metricLabel}>电流</Text>
                </View>
                <View style={styles.metricItem}>
                  <Text style={[styles.metricValue, {
                    color: charger.temperature > 60 ? '#c62828' : charger.temperature > 45 ? '#f57f17' : '#333',
                  }]}>
                    {charger.temperature.toFixed(0)}
                  </Text>
                  <Text style={styles.metricUnit}>°C</Text>
                  <Text style={styles.metricLabel}>温度</Text>
                </View>
              </View>

              {/* 会话信息 */}
              {(charger.state === 'charging' || charger.state === 'suspended') && (
                <View style={styles.sessionInfo}>
                  <Text style={styles.sessionText}>
                    ⏱ {formatDuration(charger.sessionDuration)} ·
                    本会话 {charger.sessionEnergy.toFixed(1)} kWh
                    {charger.soc != null ? ` · 电量 ${Math.round(charger.soc)}%` : ''}
                  </Text>
                </View>
              )}

              {/* 故障信息 */}
              {charger.faultCode && (
                <View style={styles.faultInfo}>
                  <Text style={styles.faultIcon}>⚠️</Text>
                  <View style={styles.faultContent}>
                    <Text style={styles.faultCode}>故障码: {charger.faultCode}</Text>
                    <Text style={styles.faultMessage} numberOfLines={2}>
                      {charger.faultMessage}
                    </Text>
                  </View>
                </View>
              )}

              {/* 展开时显示实时趋势曲线 */}
              {expandedChargerId === charger.id && (
                <ChargerTrendChart deviceId={charger.deviceId} deviceName={charger.deviceName} />
              )}
            </View>
          );
        })
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
  stationName: {
    fontSize: 14,
    color: '#999',
    marginBottom: 12,
  },
  summaryGrid: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  summaryCard: {
    flex: 1,
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
  },
  summaryNumber: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#333',
  },
  summaryLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  todayStats: {
    flexDirection: 'row',
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
  todayItem: {
    flex: 1,
    alignItems: 'center',
  },
  todayValue: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1a73e8',
  },
  todayLabel: {
    fontSize: 11,
    color: '#999',
    marginTop: 4,
  },
  todayDivider: {
    width: 1,
    height: 36,
    backgroundColor: '#eee',
    marginHorizontal: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 12,
  },
  chargerCard: {
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
  chargerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  trendToggle: {
    fontSize: 12,
    color: '#1a73e8',
    fontWeight: '500',
  },
  chargerNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
  },
  chargerIcon: {
    fontSize: 18,
    marginRight: 8,
  },
  chargerName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#fafafa',
    borderRadius: 8,
    padding: 10,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
  },
  metricUnit: {
    fontSize: 11,
    color: '#999',
    marginTop: 2,
  },
  metricLabel: {
    fontSize: 11,
    color: '#bbb',
    marginTop: 2,
  },
  sessionInfo: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  sessionText: {
    fontSize: 13,
    color: '#666',
  },
  faultInfo: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#fce4ec',
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  faultIcon: {
    fontSize: 16,
    marginRight: 8,
    marginTop: 1,
  },
  faultContent: {
    flex: 1,
  },
  faultCode: {
    fontSize: 13,
    fontWeight: '500',
    color: '#c62828',
    marginBottom: 2,
  },
  faultMessage: {
    fontSize: 12,
    color: '#999',
    lineHeight: 18,
  },
});

export default ChargerMonitorScreen;
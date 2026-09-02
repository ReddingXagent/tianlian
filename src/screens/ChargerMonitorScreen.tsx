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
import { RootStackParamList } from '../types';
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import ChargerTrendChart from '../components/ChargerTrendChart';
import { usePolling } from '../hooks/usePolling';

type ChargerMonitorRouteProp = RouteProp<RootStackParamList, 'ChargerMonitor'>;

// 枪口状态配置: 标签/图标/语义色键(运行时随主题解析)
const CONNECTOR_STATUS_LABEL: Record<string, { label: string; icon: string; color: keyof ThemeColors }> = {
  idle:      { label: '空闲', icon: '⚪', color: 'textSecondary' },
  connected: { label: '已连接', icon: '🔵', color: 'info' },
  charging:  { label: '充电中', icon: '⚡', color: 'success' },
  fault:     { label: '故障', icon: '🔴', color: 'error' },
  suspended: { label: '暂停', icon: '🟡', color: 'warningAmber' },
};

const FALLBACK_CONNECTOR_CONFIG: { label: string; icon: string; color: keyof ThemeColors } = {
  label: '',
  icon: '❓',
  color: 'textSecondary',
};

const ChargerMonitorScreen: React.FC = () => {
  const { colors } = useTheme();
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
    return CONNECTOR_STATUS_LABEL[status] || { ...FALLBACK_CONNECTOR_CONFIG, label: status };
  };

  const formatDuration = (minutes: number): string => {
    if (minutes < 60) return `${minutes}分钟`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={refresh}
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* 站点名称 */}
      <Text style={[styles.stationName, { color: colors.textSecondary }]}>{stationName}</Text>

      {/* 汇总卡片 */}
      {summary && (
        <View style={styles.summaryGrid}>
          <View style={[styles.summaryCard, { backgroundColor: colors.infoBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.textPrimary }]}>{summary.chargingCount}</Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>充电中</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.neutralBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.textPrimary }]}>{summary.idleCount}</Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>空闲</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.errorBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.error }]}>{summary.faultCount}</Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>故障</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.successBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.success }]}>
              {summary.totalPower.toFixed(1)}
            </Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>总功率kW</Text>
          </View>
        </View>
      )}

      {/* 今日统计 */}
      {summary && (
        <View style={[styles.todayStats, { backgroundColor: colors.cardBg }]}>
          <View style={styles.todayItem}>
            <Text style={[styles.todayValue, { color: colors.primary }]}>{summary.todayEnergy.toFixed(0)}</Text>
            <Text style={[styles.todayLabel, { color: colors.textSecondary }]}>今日充电 kWh</Text>
          </View>
          <View style={[styles.todayDivider, { backgroundColor: colors.divider }]} />
          <View style={styles.todayItem}>
            <Text style={[styles.todayValue, { color: colors.primary }]}>{summary.todaySessions}</Text>
            <Text style={[styles.todayLabel, { color: colors.textSecondary }]}>今日充电次数</Text>
          </View>
          <View style={[styles.todayDivider, { backgroundColor: colors.divider }]} />
          <View style={styles.todayItem}>
            <Text style={[styles.todayValue, { color: colors.primary }]}>{summary.avgPowerPerCharger.toFixed(1)}</Text>
            <Text style={[styles.todayLabel, { color: colors.textSecondary }]}>平均功率 kW</Text>
          </View>
        </View>
      )}

      {/* 充电桩列表 */}
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>充电桩实时状态</Text>
      {chargers.length === 0 ? (
        <EmptyState icon="🔌" title="暂无充电桩" message="该站点暂无充电桩设备" />
      ) : (
        chargers.map((charger) => {
          const connectorConfig = getConnectorConfig(charger.connectorStatus);
          return (
            <View key={charger.id} style={[styles.chargerCard, { backgroundColor: colors.cardBg }]}>
              testID={`charger-card-${charger.id}`}
              {/* 头部（点击展开/收起实时趋势） */}
              <TouchableOpacity
                style={styles.chargerHeader}
                activeOpacity={0.7}
                onPress={() =>
                  setExpandedChargerId((prev) => (prev === charger.id ? null : charger.id))
                }
               accessibilityRole="button">
                <View style={styles.chargerNameRow}>
                  <Text style={styles.chargerIcon}>🔌</Text>
                  <Text style={[styles.chargerName, { color: colors.textPrimary }]} numberOfLines={1}>
                    {charger.deviceName}
                  </Text>
                </View>
                <View style={styles.headerRight}>
                  <StatusBadge status={charger.connectorStatus} label={connectorConfig.label} />
                  <Text style={[styles.trendToggle, { color: colors.primary }]}>
                    {expandedChargerId === charger.id ? '收起 ▴' : '趋势 ▾'}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* 实时数据 */}
              <View style={styles.metricsGrid}>
                <View style={[styles.metricItem, { backgroundColor: colors.inputBg }]}>
                  <Text style={[styles.metricValue, { color: colors.textPrimary }]}>
                    {charger.power.toFixed(1)}
                  </Text>
                  <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>kW</Text>
                  <Text style={[styles.metricLabel, { color: colors.textMuted }]}>功率</Text>
                </View>
                <View style={[styles.metricItem, { backgroundColor: colors.inputBg }]}>
                  <Text style={[styles.metricValue, { color: colors.textPrimary }]}>
                    {charger.voltage.toFixed(0)}
                  </Text>
                  <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>V</Text>
                  <Text style={[styles.metricLabel, { color: colors.textMuted }]}>电压</Text>
                </View>
                <View style={[styles.metricItem, { backgroundColor: colors.inputBg }]}>
                  <Text style={[styles.metricValue, { color: colors.textPrimary }]}>
                    {charger.current.toFixed(1)}
                  </Text>
                  <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>A</Text>
                  <Text style={[styles.metricLabel, { color: colors.textMuted }]}>电流</Text>
                </View>
                <View style={[styles.metricItem, { backgroundColor: colors.inputBg }]}>
                  <Text style={[styles.metricValue, {
                    color: charger.temperature > 60 ? colors.error : charger.temperature > 45 ? colors.warningAmber : colors.textPrimary,
                  }]}>
                    {charger.temperature.toFixed(0)}
                  </Text>
                  <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>°C</Text>
                  <Text style={[styles.metricLabel, { color: colors.textMuted }]}>温度</Text>
                </View>
              </View>

              {/* 会话信息 */}
              {(charger.state === 'charging' || charger.state === 'suspended') && (
                <View style={[styles.sessionInfo, { borderTopColor: colors.divider }]}>
                  <Text style={[styles.sessionText, { color: colors.textSecondary }]}>
                    ⏱ {formatDuration(charger.sessionDuration)} ·
                    本会话 {charger.sessionEnergy.toFixed(1)} kWh
                    {charger.soc != null ? ` · 电量 ${Math.round(charger.soc)}%` : ''}
                  </Text>
                </View>
              )}

              {/* 故障信息 */}
              {charger.faultCode && (
                <View style={[styles.faultInfo, { borderTopColor: colors.errorBg }]}>
                  <Text style={styles.faultIcon}>⚠️</Text>
                  <View style={styles.faultContent}>
                    <Text style={[styles.faultCode, { color: colors.error }]}>故障码: {charger.faultCode}</Text>
                    <Text style={[styles.faultMessage, { color: colors.textSecondary }]} numberOfLines={2}>
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
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  stationName: {
    fontSize: 14,
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
  },
  summaryLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  todayStats: {
    flexDirection: 'row',
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
  },
  todayLabel: {
    fontSize: 11,
    marginTop: 4,
  },
  todayDivider: {
    width: 1,
    height: 36,
    marginHorizontal: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  chargerCard: {
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
    flex: 1,
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 8,
    padding: 10,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: '700',
  },
  metricUnit: {
    fontSize: 11,
    marginTop: 2,
  },
  metricLabel: {
    fontSize: 11,
    marginTop: 2,
  },
  sessionInfo: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
  },
  sessionText: {
    fontSize: 13,
  },
  faultInfo: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
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
    marginBottom: 2,
  },
  faultMessage: {
    fontSize: 12,
    lineHeight: 18,
  },
});

export default ChargerMonitorScreen;

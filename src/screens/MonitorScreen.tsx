import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { Device, Alarm, RealtimeOverview, RealtimeDeviceStatus } from '../types';
import { type StatusType } from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { useMonitorData, type MonitorTab } from '../hooks/useMonitorData';
import { useTheme } from '../hooks/useTheme';

const TABS: { key: MonitorTab; label: string }[] = [
  { key: 'devices', label: '实时监控' },
  { key: 'faults', label: '故障设备' },
  { key: 'alarms', label: '严重告警' },
];

const MonitorScreen: React.FC = () => {
  const {
    summary,
    devices,
    faultDevices,
    criticalAlarms,
    realtimeOverview,
    loading,
    refreshing,
    error,
    fetchAll,
    startPolling,
  } = useMonitorData();
  const { colors } = useTheme();

  const [activeTab, setActiveTab] = useState<MonitorTab>('devices');

  // 轮询生命周期随 activeTab + devices 变化
  useEffect(() => {
    const cleanup = startPolling(activeTab === 'devices');
    return cleanup;
  }, [activeTab, devices.length, startPolling]);

  if (loading && !refreshing) {
    return <LoadingSpinner text="加载监控数据..." />;
  }

  if (error && !summary) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重新加载"
        onAction={() => fetchAll()}
      />
    );
  }

  const getRealtimeDevice = (
    deviceId: number,
  overview: RealtimeOverview | null,
  deviceList: Device[],
  ): RealtimeDeviceStatus | undefined => {
    if (!overview) return undefined;
    // 优先从 overview 匹配，兜底从 deviceList 本地状态推断
    return overview.devices.find((d) => d.id === deviceId);
  };

  const renderMetricsBar = (rt?: RealtimeDeviceStatus) => {
    if (!rt) {
      return <Text style={[styles.metricsNoData, { color: colors.textMuted }]}>遥测数据加载中...</Text>;
    }
    return (
      <View style={[styles.metricsRow, { backgroundColor: colors.pageBg }]}>
        <View style={styles.metricItem}>
          <Text style={[styles.metricValue, { color: colors.textPrimary }]}>{rt.power.toFixed(1)}</Text>
          <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>kW</Text>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>功率</Text>
        </View>
      </View>
    );
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      <ScrollView
        style={styles.scrollContainer}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => fetchAll(true)}
            colors={[colors.primary]}
            tintColor={colors.primary}
          />
        }
      >
        {/* 监控概览 */}
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>监控概览</Text>
        <View style={styles.summaryGrid}>
          <View style={[styles.summaryCard, { backgroundColor: colors.infoBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.info }]}>
              {summary?.totalDevices ?? '-'}
            </Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>总设备</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.successBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.success }]}>
              {summary?.onlineDevices ?? '-'}
            </Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>在线</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.warningBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.warning }]}>
              {summary?.faultDevices ?? '-'}
            </Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>故障</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: colors.errorBg }]}>
            <Text style={[styles.summaryNumber, { color: colors.error }]}>
              {summary?.criticalAlarms ?? '-'}
            </Text>
            <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>严重告警</Text>
          </View>
        </View>

        {/* Tab 切换 */}
        <View style={[styles.tabContainer, { backgroundColor: colors.cardBg }]}>
          {TABS.map((tab) => (
            <TouchableOpacity
              testID={`monitor-tab-${tab.key}`}
              key={tab.key}
              style={[
                styles.tab,
                activeTab === tab.key && { backgroundColor: colors.primary },
              ]}
              onPress={() => setActiveTab(tab.key)}
              accessibilityRole="button">
              <Text
                style={[
                  styles.tabText,
                  { color: activeTab === tab.key ? colors.onPrimary : colors.textSecondary },
                ]}
              >
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 实时总览 */}
        {activeTab === 'devices' && realtimeOverview && (
          <View style={[styles.realtimeOverviewBar, { backgroundColor: colors.pageBg }]}>
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: colors.textPrimary }]}>{realtimeOverview.totalPower.toFixed(1)}</Text>
              <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>kW</Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>总功率</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: realtimeOverview.powerTrend >= 0 ? colors.success : colors.warning }]}>
                {realtimeOverview.powerTrend >= 0 ? '↑' : '↓'} {Math.abs(realtimeOverview.powerTrend).toFixed(1)}%
              </Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>趋势</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: colors.textPrimary }]}>{realtimeOverview.efficiency.toFixed(1)}</Text>
              <Text style={[styles.metricUnit, { color: colors.textSecondary }]}>%</Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>效率</Text>
            </View>
          </View>
        )}

        {/* 实时监控列表 */}
        {activeTab === 'devices' && (
          devices.length === 0 ? (
            <EmptyState
              icon="📡"
              title="暂无设备"
              message="当前没有监控设备"
            />
          ) : (
            devices.map((device) => {
              const rt = getRealtimeDevice(device.id, realtimeOverview, devices);
              return (
                <View key={device.id} style={[styles.deviceCard, { backgroundColor: colors.cardBg }]}>
                  <View style={styles.deviceHeader}>
                    <View style={styles.deviceNameRow}>
                      <Text style={[styles.deviceName, { color: colors.textPrimary }]} numberOfLines={1}>
                        {device.name}
                      </Text>
                      <StatusBadge status={(rt?.status || device.status) as StatusType} />
                    </View>
                    <Text style={[styles.deviceMeta, { color: colors.textSecondary }]}>
                      {device.stationName || `站点#${device.stationId}`} · {device.model}
                    </Text>
                  </View>
                  {renderMetricsBar(rt)}
                  <Text style={[styles.deviceUpdateTime, { color: colors.textMuted }]}>
                    最后更新: {realtimeOverview?.updateTime
                      ? new Date(realtimeOverview.updateTime).toLocaleTimeString('zh-CN')
                      : device.lastHeartbeat
                        ? new Date(device.lastHeartbeat).toLocaleTimeString('zh-CN')
                        : '-'}
                  </Text>
                </View>
              );
            })
          )
        )}

        {/* 故障设备列表 */}
        {activeTab === 'faults' && (
          faultDevices.length === 0 ? (
            <EmptyState
              icon="✅"
              title="暂无故障设备"
              message="当前所有设备运行正常"
            />
          ) : (
            faultDevices.map((device: Device) => (
              <View key={device.id} style={[styles.itemCard, { backgroundColor: colors.cardBg }]}>
                <View style={styles.itemHeader}>
                  <Text style={[styles.itemName, { color: colors.textPrimary }]} numberOfLines={1}>
                    {device.name}
                  </Text>
                  <StatusBadge status="fault" />
                </View>
                <Text style={[styles.itemMeta, { color: colors.textSecondary }]}>
                  {device.stationName || `站点ID: ${device.stationId}`} ·{' '}
                  {device.model}
                </Text>
                <Text style={[styles.itemTime, { color: colors.textMuted }]}>
                  最后心跳: {device.lastHeartbeat
                    ? new Date(device.lastHeartbeat).toLocaleString('zh-CN')
                    : '-'}
                </Text>
              </View>
            ))
          )
        )}

        {/* 严重告警列表 */}
        {activeTab === 'alarms' && (
          criticalAlarms.length === 0 ? (
            <EmptyState
              icon="✅"
              title="暂无严重告警"
              message="当前没有严重级别告警"
            />
          ) : (
            criticalAlarms.map((alarm: Alarm) => (
              <View key={alarm.id} style={[styles.itemCard, { backgroundColor: colors.cardBg }]}>
                <View style={styles.itemHeader}>
                  <Text style={[styles.itemName, { color: colors.textPrimary }]} numberOfLines={1}>
                    {alarm.title}
                  </Text>
                  <StatusBadge status="critical" />
                </View>
                <Text style={[styles.itemMeta, { color: colors.textSecondary }]} numberOfLines={2}>
                  {alarm.description}
                </Text>
                <View style={styles.itemFooter}>
                  <Text style={[styles.itemStation, { color: colors.textSecondary }]}>
                    {alarm.stationName}
                  </Text>
                  <Text style={[styles.itemTime, { color: colors.textMuted }]}>
                    {new Date(alarm.createdAt).toLocaleString('zh-CN')}
                  </Text>
                </View>
              </View>
            ))
          )
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContainer: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
    marginTop: 8,
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 16,
  },
  summaryCard: {
    width: '47%',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  summaryNumber: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  summaryLabel: {
    fontSize: 13,
    marginTop: 4,
  },
  tabContainer: {
    flexDirection: 'row',
    borderRadius: 12,
    padding: 4,
    marginBottom: 12,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
  },
  deviceCard: {
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  deviceHeader: {
    marginBottom: 10,
  },
  deviceNameRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  deviceName: {
    fontSize: 15,
    fontWeight: '600',
    flex: 1,
    marginRight: 8,
  },
  deviceMeta: {
    fontSize: 12,
  },
  metricsRow: {
    flexDirection: 'row',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
    gap: 4,
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
  },
  metricValue: {
    fontSize: 18,
    fontWeight: '700',
  },
  metricUnit: {
    fontSize: 11,
    marginTop: 1,
  },
  metricLabel: {
    fontSize: 11,
    marginTop: 2,
  },
  metricsNoData: {
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: 8,
  },
  deviceUpdateTime: {
    fontSize: 11,
  },
  itemCard: {
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  itemName: {
    fontSize: 15,
    fontWeight: '500',
    flex: 1,
    marginRight: 8,
  },
  itemMeta: {
    fontSize: 13,
    marginBottom: 4,
    lineHeight: 18,
  },
  itemFooter: {
    marginTop: 6,
  },
  itemStation: {
    fontSize: 12,
    marginBottom: 2,
  },
  itemTime: {
    fontSize: 12,
  },
  realtimeOverviewBar: {
    flexDirection: 'row',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
});

export default MonitorScreen;

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { monitorApi, deviceMonitorApi } from '../services/api';
import { MonitorSummary, Device, Alarm, RealtimeOverview, RealtimeDeviceStatus } from '../types';
import { type StatusType } from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type MonitorTab = 'devices' | 'faults' | 'alarms';

const TABS: { key: MonitorTab; label: string }[] = [
  { key: 'devices', label: '实时监控' },
  { key: 'faults', label: '故障设备' },
  { key: 'alarms', label: '严重告警' },
];

const MonitorScreen: React.FC = () => {
  const [summary, setSummary] = useState<MonitorSummary | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [realtimeOverview, setRealtimeOverview] = useState<RealtimeOverview | null>(null);
  const [faultDevices, setFaultDevices] = useState<Device[]>([]);
  const [criticalAlarms, setCriticalAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<MonitorTab>('devices');
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [summaryRes, devicesRes, faultsRes, alarmsRes] = await Promise.all([
        monitorApi.getSummary(),
        deviceMonitorApi.getDeviceStatusList({ pageSize: 50 }),
        monitorApi.getFaultDevices({ pageSize: 20 }),
        monitorApi.getCriticalAlarms({ pageSize: 20 }),
      ]);
      setSummary(summaryRes.data);
      setDevices(devicesRes.data.items);
      setFaultDevices(faultsRes.data.items);
      setCriticalAlarms(alarmsRes.data.items);
    } catch {
      setError('加载监控数据失败，请下拉刷新重试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchRealtimeMetrics = useCallback(async () => {
    if (devices.length === 0) return;
    try {
      const res = await deviceMonitorApi.getRealtimeOverview();
      setRealtimeOverview(res.data);
    } catch {
      // 实时数据获取失败，静默处理
    }
  }, [devices]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (activeTab === 'devices' && devices.length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchRealtimeMetrics();
      refreshTimer.current = setInterval(fetchRealtimeMetrics, 10000);
    }
    return () => {
      if (refreshTimer.current) {
        clearInterval(refreshTimer.current);
        refreshTimer.current = null;
      }
    };
  }, [activeTab, devices.length, fetchRealtimeMetrics]);

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
        onAction={() => fetchData()}
      />
    );
  }

  const getRealtimeDevice = (deviceId: number): RealtimeDeviceStatus | undefined => {
    return realtimeOverview?.devices.find((d) => d.id === deviceId);
  };

  const renderMetricsBar = (rt?: RealtimeDeviceStatus) => {
    if (!rt) {
      return <Text style={styles.metricsNoData}>遥测数据加载中...</Text>;
    }
    return (
      <View style={styles.metricsRow}>
        <View style={styles.metricItem}>
          <Text style={styles.metricValue}>{rt.power.toFixed(1)}</Text>
          <Text style={styles.metricUnit}>kW</Text>
          <Text style={styles.metricLabel}>功率</Text>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollContainer}
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
        {/* 监控概览 */}
        <Text style={styles.sectionTitle}>监控概览</Text>
        <View style={styles.summaryGrid}>
          <View style={[styles.summaryCard, { backgroundColor: '#e3f2fd' }]}>
            <Text style={[styles.summaryNumber, { color: '#1565c0' }]}>
              {summary?.totalDevices ?? '-'}
            </Text>
            <Text style={styles.summaryLabel}>总设备</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#e8f5e9' }]}>
            <Text style={[styles.summaryNumber, { color: '#2e7d32' }]}>
              {summary?.onlineDevices ?? '-'}
            </Text>
            <Text style={styles.summaryLabel}>在线</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#fff3e0' }]}>
            <Text style={[styles.summaryNumber, { color: '#e65100' }]}>
              {summary?.faultDevices ?? '-'}
            </Text>
            <Text style={styles.summaryLabel}>故障</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#fce4ec' }]}>
            <Text style={[styles.summaryNumber, { color: '#c62828' }]}>
              {summary?.criticalAlarms ?? '-'}
            </Text>
            <Text style={styles.summaryLabel}>严重告警</Text>
          </View>
        </View>

        {/* Tab 切换 */}
        <View style={styles.tabContainer}>
          {TABS.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tab, activeTab === tab.key && styles.tabActive]}
              onPress={() => setActiveTab(tab.key)}
            >
              <Text
                style={[
                  styles.tabText,
                  activeTab === tab.key && styles.tabTextActive,
                ]}
              >
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* 实时总览 */}
        {activeTab === 'devices' && realtimeOverview && (
          <View style={styles.realtimeOverviewBar}>
            <View style={styles.metricItem}>
              <Text style={styles.metricValue}>{realtimeOverview.totalPower.toFixed(1)}</Text>
              <Text style={styles.metricUnit}>kW</Text>
              <Text style={styles.metricLabel}>总功率</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={[styles.metricValue, { color: realtimeOverview.powerTrend >= 0 ? '#2e7d32' : '#e65100' }]}>
                {realtimeOverview.powerTrend >= 0 ? '↑' : '↓'} {Math.abs(realtimeOverview.powerTrend).toFixed(1)}%
              </Text>
              <Text style={styles.metricLabel}>趋势</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={styles.metricValue}>{realtimeOverview.efficiency.toFixed(1)}</Text>
              <Text style={styles.metricUnit}>%</Text>
              <Text style={styles.metricLabel}>效率</Text>
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
              const rt = getRealtimeDevice(device.id);
              return (
                <View key={device.id} style={styles.deviceCard}>
                  <View style={styles.deviceHeader}>
                    <View style={styles.deviceNameRow}>
                      <Text style={styles.deviceName} numberOfLines={1}>
                        {device.name}
                      </Text>
                      <StatusBadge status={(rt?.status || device.status) as StatusType} />
                    </View>
                    <Text style={styles.deviceMeta}>
                      {device.stationName || `站点#${device.stationId}`} · {device.model}
                    </Text>
                  </View>
                  {renderMetricsBar(rt)}
                  <Text style={styles.deviceUpdateTime}>
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
            faultDevices.map((device) => (
              <View key={device.id} style={styles.itemCard}>
                <View style={styles.itemHeader}>
                  <Text style={styles.itemName} numberOfLines={1}>
                    {device.name}
                  </Text>
                  <StatusBadge status="fault" />
                </View>
                <Text style={styles.itemMeta}>
                  {device.stationName || `站点ID: ${device.stationId}`} ·{' '}
                  {device.model}
                </Text>
                <Text style={styles.itemTime}>
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
            criticalAlarms.map((alarm) => (
              <View key={alarm.id} style={styles.itemCard}>
                <View style={styles.itemHeader}>
                  <Text style={styles.itemName} numberOfLines={1}>
                    {alarm.title}
                  </Text>
                  <StatusBadge status="critical" />
                </View>
                <Text style={styles.itemMeta} numberOfLines={2}>
                  {alarm.description}
                </Text>
                <View style={styles.itemFooter}>
                  <Text style={styles.itemStation}>
                    {alarm.stationName}
                  </Text>
                  <Text style={styles.itemTime}>
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
    backgroundColor: '#f5f6fa',
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
    color: '#333',
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
    color: '#666',
    marginTop: 4,
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
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
  tabActive: {
    backgroundColor: '#1a73e8',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#666',
  },
  tabTextActive: {
    color: '#fff',
  },
  deviceCard: {
    backgroundColor: '#fff',
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
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  deviceMeta: {
    fontSize: 12,
    color: '#999',
  },
  metricsRow: {
    flexDirection: 'row',
    backgroundColor: '#f5f6fa',
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
    color: '#333',
  },
  metricUnit: {
    fontSize: 11,
    color: '#999',
    marginTop: 1,
  },
  metricLabel: {
    fontSize: 11,
    color: '#999',
    marginTop: 2,
  },
  metricsNoData: {
    fontSize: 12,
    color: '#bbb',
    textAlign: 'center',
    paddingVertical: 8,
  },
  deviceUpdateTime: {
    fontSize: 11,
    color: '#bbb',
  },
  itemCard: {
    backgroundColor: '#fff',
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
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  itemMeta: {
    fontSize: 13,
    color: '#999',
    marginBottom: 4,
    lineHeight: 18,
  },
  itemFooter: {
    marginTop: 6,
  },
  itemStation: {
    fontSize: 12,
    color: '#999',
    marginBottom: 2,
  },
  itemTime: {
    fontSize: 12,
    color: '#bbb',
  },
  realtimeOverviewBar: {
    flexDirection: 'row',
    backgroundColor: '#f5f7fa',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
});

export default MonitorScreen;

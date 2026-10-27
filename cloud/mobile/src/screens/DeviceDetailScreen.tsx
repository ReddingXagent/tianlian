import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../../App';
import { useOffline } from '../store/OfflineContext';
import { deviceApi } from '../services/api';
import { cache } from '../services/cache';

interface RouteParams {
  deviceId: string;
}

interface DeviceDetail {
  id: string;
  name: string;
  model: string;
  sn: string;
  stationId: string;
  stationName: string;
  type: string;
  status: string;
  online: boolean;
  healthScore: number;
  lastMaintenance: string;
  nextMaintenance: string;
}

interface DeviceEfficiency {
  utilization: number;
  chargingEfficiency: number;
  generationEfficiency: number;
  isV2G: boolean;
  v2g?: V2GInfo;
}

interface V2GInfo {
  chargeDischargeMode: string;
  realTimePower: number;
  dispatchStatus: string;
}

interface MaintenanceRecord {
  id: string;
  date: string;
  type: string;
  description: string;
  engineer: string;
}

const DeviceDetailScreen = ({ route }: { route: { params: RouteParams } }) => {
  const { deviceId } = route.params;
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, 'DeviceDetail'>>();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [maintenanceRecords, setMaintenanceRecords] = useState<MaintenanceRecord[]>([]);
  const [efficiency, setEfficiency] = useState<DeviceEfficiency | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { isConnected, triggerSync, getCachedData } = useOffline();

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      if (isConnected) {
        const deviceRes = await deviceApi.getById(deviceId);
        const deviceData = deviceRes.data;

        // 获取维护记录
        const recordsRes = await deviceApi.getMaintenanceRecords(deviceId);
        const recordsData = recordsRes.data;

        // 获取效率数据
        let effData: DeviceEfficiency | null = null;
        try {
          const effRes = await deviceApi.getEfficiency(deviceId);
          const rawEff = effRes.data?.data || effRes.data;
          effData = {
            utilization: rawEff?.utilization ?? rawEff?.utilizationRate ?? 0,
            chargingEfficiency: rawEff?.chargingEfficiency ?? rawEff?.chargeEfficiency ?? 0,
            generationEfficiency: rawEff?.generationEfficiency ?? rawEff?.prValue ?? 0,
            isV2G: rawEff?.isV2G ?? false,
            v2g: rawEff?.v2g
              ? {
                  chargeDischargeMode: rawEff.v2g.chargeDischargeMode || rawEff.v2g.mode || '',
                  realTimePower: rawEff.v2g.realTimePower || rawEff.v2g.power || 0,
                  dispatchStatus: rawEff.v2g.dispatchStatus || rawEff.v2g.status || '',
                }
              : undefined,
          };
        } catch (effErr: any) {
          console.error('[DeviceDetail] Load efficiency error:', effErr.message);
        }

        setDevice(deviceData);
        setMaintenanceRecords(recordsData || []);
        if (effData) setEfficiency(effData);

        // 缓存数据
        await cache.set(`device_${deviceId}`, deviceData);
        await cache.set(`device_${deviceId}_maintenance`, recordsData || []);
        if (effData) await cache.set(`device_${deviceId}_efficiency`, effData);
      } else {
        // 离线模式
        const cachedDevice = await getCachedData<DeviceDetail>(`device_${deviceId}`);
        const cachedRecords = await getCachedData<MaintenanceRecord[]>(`device_${deviceId}_maintenance`);
        const cachedEff = await getCachedData<DeviceEfficiency>(`device_${deviceId}_efficiency`);

        if (cachedDevice) setDevice(cachedDevice);
        if (cachedRecords) setMaintenanceRecords(cachedRecords);
        if (cachedEff) setEfficiency(cachedEff);
      }
    } catch (error: any) {
      console.error('[DeviceDetail] Load error:', error.message);
      // 尝试从缓存加载
      const cachedDevice = await getCachedData<DeviceDetail>(`device_${deviceId}`);
      const cachedRecords = await getCachedData<MaintenanceRecord[]>(`device_${deviceId}_maintenance`);
      const cachedEff = await getCachedData<DeviceEfficiency>(`device_${deviceId}_efficiency`);

      if (cachedDevice) setDevice(cachedDevice);
      if (cachedRecords) setMaintenanceRecords(cachedRecords);
      if (cachedEff) setEfficiency(cachedEff);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [deviceId, isConnected, getCachedData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const handleReportRepair = () => {
    // 导航到报修页面，传递设备信息
    navigation.navigate('WorkOrders', {
      deviceId,
      deviceName: device?.name,
    });
  };

  const getHealthColor = (score: number) => {
    if (score >= 80) return '#52c41a';
    if (score >= 60) return '#faad14';
    return '#ff4d4f';
  };

  const getUtilizationColor = (val: number) => {
    if (val < 30) return '#faad14';
    if (val > 90) return '#ff4d4f';
    return '#52c41a';
  };

  const getEfficiencyColor = (val: number) => {
    if (val >= 80) return '#52c41a';
    if (val >= 60) return '#faad14';
    return '#ff4d4f';
  };

  const getV2GModeColor = (mode: string) => {
    switch (mode) {
      case '充电中': return '#52c41a';
      case '放电中': return '#1890ff';
      case '待机': return '#999';
      default: return '#666';
    }
  };

  const getDispatchStatusColor = (status: string) => {
    switch (status) {
      case '已调度': return '#52c41a';
      case '等待调度': return '#faad14';
      case '未调度': return '#999';
      default: return '#666';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '正常':
        return '#52c41a';
      case '告警':
        return '#faad14';
      case '故障':
        return '#ff4d4f';
      default:
        return '#999';
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载设备详情...</Text>
      </View>
    );
  }

  if (!device) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyIcon}>📭</Text>
        <Text style={styles.emptyText}>暂无数据</Text>
        {!isConnected && <Text style={styles.emptySubtext}>请连接网络后刷新</Text>}
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            enabled={isConnected}
            colors={['#1890ff']}
          />
        }
      >
        {/* 基本信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>基本信息</Text>
          <View style={styles.card}>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>设备名称</Text>
              <Text style={styles.infoValue}>{device.name}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>设备型号</Text>
              <Text style={styles.infoValue}>{device.model}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>序列号</Text>
              <Text style={styles.infoValue}>{device.sn}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>所属站点</Text>
              <Text style={styles.infoValue}>{device.stationName}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>设备类型</Text>
              <Text style={styles.infoValue}>{device.type}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>状态</Text>
              <View style={styles.statusRow}>
                <View
                  style={[
                    styles.statusDot,
                    { backgroundColor: device.online ? '#52c41a' : '#ff4d4f' },
                  ]}
                />
                <View style={[styles.statusBadge, { backgroundColor: getStatusColor(device.status) + '20' }]}>
                  <Text style={[styles.statusText, { color: getStatusColor(device.status) }]}>
                    {device.status}
                  </Text>
                </View>
              </View>
            </View>
          </View>
        </View>

        {/* 健康度评分 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>健康度评分</Text>
          <View style={styles.card}>
            <View style={styles.healthContainer}>
              <View style={[styles.healthCircle, { borderColor: getHealthColor(device.healthScore) }]}>
                <Text style={[styles.healthScore, { color: getHealthColor(device.healthScore) }]}>
                  {device.healthScore}
                </Text>
              </View>
              <Text style={styles.healthLabel}>
                {device.healthScore >= 80 ? '良好' : device.healthScore >= 60 ? '一般' : '需维护'}
              </Text>
            </View>
            {device.healthScore < 80 && (
              <Text style={styles.healthHint}>
                建议尽快安排检修维护
              </Text>
            )}
          </View>
        </View>

        {/* 运行效率 */}
        {efficiency && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>运行效率</Text>
            <View style={styles.card}>
              <View style={styles.efficiencyGrid}>
                <View style={styles.efficiencyItem}>
                  <Text style={styles.efficiencyItemLabel}>设备利用率</Text>
                  <Text style={[styles.efficiencyItemValue, { color: getUtilizationColor(efficiency.utilization) }]}>
                    {efficiency.utilization}%
                  </Text>
                </View>
                <View style={styles.efficiencyItem}>
                  <Text style={styles.efficiencyItemLabel}>充电效率</Text>
                  <Text style={[styles.efficiencyItemValue, { color: getEfficiencyColor(efficiency.chargingEfficiency) }]}>
                    {efficiency.chargingEfficiency}%
                  </Text>
                </View>
                <View style={styles.efficiencyItem}>
                  <Text style={styles.efficiencyItemLabel}>发电效率 (PR)</Text>
                  <Text style={[styles.efficiencyItemValue, { color: getEfficiencyColor(efficiency.generationEfficiency) }]}>
                    {efficiency.generationEfficiency}
                  </Text>
                </View>
              </View>
            </View>
          </View>
        )}

        {/* V2G信息 */}
        {efficiency?.isV2G && efficiency.v2g && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>V2G 调度信息</Text>
            <View style={styles.card}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>充放电模式</Text>
                <View style={[styles.v2gModeBadge, { backgroundColor: getV2GModeColor(efficiency.v2g.chargeDischargeMode) + '20' }]}>
                  <Text style={[styles.v2gModeText, { color: getV2GModeColor(efficiency.v2g.chargeDischargeMode) }]}>
                    {efficiency.v2g.chargeDischargeMode}
                  </Text>
                </View>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>实时功率</Text>
                <Text style={styles.infoValue}>{efficiency.v2g.realTimePower} kW</Text>
              </View>
              <View style={[styles.infoRow, styles.infoRowLast]}>
                <Text style={styles.infoLabel}>调度状态</Text>
                <View style={[styles.v2gModeBadge, { backgroundColor: getDispatchStatusColor(efficiency.v2g.dispatchStatus) + '20' }]}>
                  <Text style={[styles.v2gModeText, { color: getDispatchStatusColor(efficiency.v2g.dispatchStatus) }]}>
                    {efficiency.v2g.dispatchStatus}
                  </Text>
                </View>
              </View>
            </View>
          </View>
        )}

        {/* 维护信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>维护信息</Text>
          <View style={styles.card}>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>上次维护</Text>
              <Text style={styles.infoValue}>{device.lastMaintenance || '暂无记录'}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>下次维护</Text>
              <Text style={styles.infoValue}>{device.nextMaintenance || '待安排'}</Text>
            </View>
          </View>
        </View>

        {/* 维护记录 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>维护记录</Text>
          {maintenanceRecords.length === 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyText}>暂无维护记录</Text>
            </View>
          ) : (
            maintenanceRecords.map((record) => (
              <View key={record.id} style={styles.recordItem}>
                <View style={styles.recordLeft}>
                  <Text style={styles.recordType}>{record.type}</Text>
                  <Text style={styles.recordDesc}>{record.description}</Text>
                  <Text style={styles.recordEngineer}>工程师: {record.engineer}</Text>
                </View>
                <Text style={styles.recordDate}>{record.date}</Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* 报修按钮 */}
      <View style={styles.bottomBar}>
        <TouchableOpacity style={styles.reportButton} onPress={handleReportRepair}>
          <Text style={styles.reportButtonText}>申请报修</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#666',
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
    flex: 1,
    textAlign: 'right',
  },
  infoRowLast: {
    borderBottomWidth: 0,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  healthContainer: {
    alignItems: 'center',
    paddingVertical: 16,
  },
  healthCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    borderWidth: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  healthScore: {
    fontSize: 32,
    fontWeight: 'bold',
  },
  healthLabel: {
    fontSize: 16,
    color: '#666',
    marginTop: 8,
  },
  healthHint: {
    textAlign: 'center',
    color: '#faad14',
    fontSize: 14,
    marginTop: 12,
  },
  efficiencyGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  efficiencyItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 8,
  },
  efficiencyItemLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 6,
  },
  efficiencyItemValue: {
    fontSize: 22,
    fontWeight: 'bold',
  },
  v2gModeBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  v2gModeText: {
    fontSize: 13,
    fontWeight: '500',
  },
  recordItem: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  recordLeft: {
    flex: 1,
  },
  recordType: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
    marginBottom: 4,
  },
  recordDesc: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  recordEngineer: {
    fontSize: 12,
    color: '#999',
  },
  recordDate: {
    fontSize: 12,
    color: '#999',
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  bottomBar: {
    padding: 16,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  reportButton: {
    backgroundColor: '#1890ff',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  reportButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '500',
  },
  loadingText: {
    marginTop: 16,
    color: '#999',
    fontSize: 14,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#ccc',
  },
});

export default DeviceDetailScreen;
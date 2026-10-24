import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  FlatList,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/AppNavigator';
import { v2gApi } from '../services/api';
import type { V2GDevice, V2GEfficiency, V2GEfficiencyTrend } from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'V2GDiagnosis'>;

// 效率阈值
const EFFICIENCY_THRESHOLD = 85;
const HEALTH_THRESHOLD = 70;

const V2GDiagnosisScreen: React.FC<Props> = ({ navigation }) => {
  const [devices, setDevices] = useState<V2GDevice[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<V2GDevice | null>(null);
  const [efficiency, setEfficiency] = useState<V2GEfficiency | null>(null);
  const [trends, setTrends] = useState<V2GEfficiencyTrend[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadDevices = useCallback(async () => {
    try {
      setLoading(true);
      const data = await v2gApi.getDevices();
      setDevices(data);
    } catch (error: any) {
      console.error('Load V2G devices error:', error);
      setDevices(getMockDevices());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDevices();
  }, [loadDevices]);

  const loadDeviceDetail = useCallback(async (device: V2GDevice) => {
    setSelectedDevice(device);
    try {
      setDetailLoading(true);
      const [effData, trendData] = await Promise.all([
        v2gApi.getEfficiency(device.id),
        v2gApi.getEfficiencyTrend(device.id),
      ]);
      setEfficiency(effData);
      setTrends(trendData);
    } catch (error: any) {
      console.error('Load device detail error:', error);
      setEfficiency(getMockEfficiency(device.id));
      setTrends(getMockTrends());
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // 模拟数据
  const getMockDevices = (): V2GDevice[] => [
    {
      id: 'V2G001',
      name: 'V2G充电桩A01',
      type: 'v2g_charger',
      status: 'online',
      stationId: 'S001',
      stationName: '朝阳充电站',
      ratedPower: 60,
      batteryCapacity: 100,
      currentPower: 0,
      efficiency: 92.5,
      healthScore: 88,
      lastMaintenance: '2026-06-15',
    },
    {
      id: 'V2G002',
      name: 'V2G充电桩A02',
      type: 'v2g_charger',
      status: 'charging',
      stationId: 'S001',
      stationName: '朝阳充电站',
      ratedPower: 60,
      batteryCapacity: 100,
      currentPower: 45,
      efficiency: 78.3,
      healthScore: 65,
      lastMaintenance: '2026-05-20',
    },
    {
      id: 'V2G003',
      name: 'V2G充电桩B01',
      type: 'v2g_charger',
      status: 'offline',
      stationId: 'S002',
      stationName: '海淀储能站',
      ratedPower: 120,
      batteryCapacity: 200,
      currentPower: 0,
      efficiency: 0,
      healthScore: 0,
      lastMaintenance: '2026-04-10',
    },
  ];

  const getMockEfficiency = (deviceId: string): V2GEfficiency => {
    if (deviceId === 'V2G001') {
      return {
        deviceId,
        chargeEfficiency: 93.2,
        dischargeEfficiency: 91.8,
        conversionEfficiency: 85.6,
        healthScore: 88,
        temperature: 32.5,
        cycleCount: 1240,
        timestamp: '2026-07-07 00:00:00',
      };
    }
    return {
      deviceId,
      chargeEfficiency: 80.1,
      dischargeEfficiency: 76.5,
      conversionEfficiency: 61.3,
      healthScore: 65,
      temperature: 38.2,
      cycleCount: 3280,
      timestamp: '2026-07-07 00:00:00',
    };
  };

  const getMockTrends = (): V2GEfficiencyTrend[] => [
    { date: '07-01', chargeEfficiency: 93.5, dischargeEfficiency: 92.0, conversionEfficiency: 86.0 },
    { date: '07-02', chargeEfficiency: 93.0, dischargeEfficiency: 91.5, conversionEfficiency: 85.5 },
    { date: '07-03', chargeEfficiency: 92.8, dischargeEfficiency: 91.3, conversionEfficiency: 85.2 },
    { date: '07-04', chargeEfficiency: 93.1, dischargeEfficiency: 91.7, conversionEfficiency: 85.4 },
    { date: '07-05', chargeEfficiency: 93.3, dischargeEfficiency: 91.9, conversionEfficiency: 85.8 },
    { date: '07-06', chargeEfficiency: 93.2, dischargeEfficiency: 91.8, conversionEfficiency: 85.6 },
  ];

  const getStatusInfo = (status: string) => {
    switch (status) {
      case 'online': return { color: '#52c41a', label: '在线' };
      case 'charging': return { color: '#1890ff', label: '充电中' };
      case 'discharging': return { color: '#faad14', label: '放电中' };
      case 'standby': return { color: '#999', label: '待机' };
      case 'offline': return { color: '#ff4d4f', label: '离线' };
      default: return { color: '#999', label: '未知' };
    }
  };

  const getHealthColor = (score: number) => {
    if (score >= 80) return '#52c41a';
    if (score >= 60) return '#faad14';
    return '#ff4d4f';
  };

  const isAbnormal = (val: number, threshold: number) => val < threshold;

  // 返回设备列表
  const handleBack = () => {
    setSelectedDevice(null);
    setEfficiency(null);
    setTrends([]);
  };

  // ========== 设备列表视图 ==========
  if (!selectedDevice) {
    return (
      <ScrollView
        style={styles.container}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={loadDevices} colors={['#1890ff']} />
        }
      >
        <Text style={styles.sectionTitle}>V2G 设备列表</Text>
        <Text style={styles.sectionHint}>点击设备查看诊断详情</Text>

        {devices.map((device) => {
          const status = getStatusInfo(device.status);
          const healthColor = getHealthColor(device.healthScore);
          return (
            <TouchableOpacity
              key={device.id}
              style={styles.deviceCard}
              onPress={() => loadDeviceDetail(device)}
            >
              <View style={styles.deviceHeader}>
                <Text style={styles.deviceName}>{device.name}</Text>
                <View style={[styles.statusTag, { backgroundColor: status.color }]}>
                  <Text style={styles.statusText}>{status.label}</Text>
                </View>
              </View>
              <View style={styles.deviceInfo}>
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>站点</Text>
                  <Text style={styles.infoValue}>{device.stationName}</Text>
                </View>
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>额定功率</Text>
                  <Text style={styles.infoValue}>{device.ratedPower} kW</Text>
                </View>
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>电池容量</Text>
                  <Text style={styles.infoValue}>{device.batteryCapacity} kWh</Text>
                </View>
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>效率</Text>
                  <Text style={[
                    styles.infoValue,
                    isAbnormal(device.efficiency, EFFICIENCY_THRESHOLD) && device.efficiency > 0 && styles.abnormalText,
                  ]}>
                    {device.efficiency > 0 ? `${device.efficiency}%` : 'N/A'}
                  </Text>
                </View>
                <View style={styles.infoRow}>
                  <Text style={styles.infoLabel}>健康度</Text>
                  <Text style={[styles.infoValue, { color: healthColor }]}>
                    {device.healthScore > 0 ? `${device.healthScore}分` : 'N/A'}
                  </Text>
                </View>
              </View>
              {(device.efficiency > 0 && device.efficiency < EFFICIENCY_THRESHOLD) && (
                <View style={styles.alertBanner}>
                  <Text style={styles.alertText}>⚠️ 效率异常 - 低于{`${EFFICIENCY_THRESHOLD}%`}阈值</Text>
                </View>
              )}
              {device.healthScore > 0 && device.healthScore < HEALTH_THRESHOLD && (
                <View style={styles.alertBanner}>
                  <Text style={styles.alertText}>⚠️ 电池健康度偏低</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}

        {devices.length === 0 && !loading && (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>暂无 V2G 设备</Text>
          </View>
        )}
      </ScrollView>
    );
  }

  // ========== 诊断详情视图 ==========
  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={detailLoading}
          onRefresh={() => loadDeviceDetail(selectedDevice)}
          colors={['#1890ff']}
        />
      }
    >
      {/* 返回按钮 */}
      <TouchableOpacity style={styles.backButton} onPress={handleBack}>
        <Text style={styles.backText}>← 返回设备列表</Text>
      </TouchableOpacity>

      {/* 设备标题 */}
      <View style={styles.detailHeader}>
        <Text style={styles.detailDeviceName}>{selectedDevice.name}</Text>
        <Text style={styles.detailStation}>{selectedDevice.stationName}</Text>
      </View>

      {/* 充放电效率测试 */}
      <View style={styles.section}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>⚡ 充放电效率测试</Text>
          
          <View style={styles.efficiencyRow}>
            <View style={styles.efficiencyItem}>
              <Text style={styles.efficiencyLabel}>充电效率</Text>
              <Text style={[
                styles.efficiencyValue,
                efficiency && isAbnormal(efficiency.chargeEfficiency, EFFICIENCY_THRESHOLD) && styles.abnormalText,
              ]}>
                {efficiency ? `${efficiency.chargeEfficiency}%` : '--'}
              </Text>
              {efficiency && isAbnormal(efficiency.chargeEfficiency, EFFICIENCY_THRESHOLD) && (
                <Text style={styles.abnormalHint}>低于阈值{`${EFFICIENCY_THRESHOLD}%`}</Text>
              )}
            </View>
            <View style={styles.efficiencyDivider} />
            <View style={styles.efficiencyItem}>
              <Text style={styles.efficiencyLabel}>放电效率</Text>
              <Text style={[
                styles.efficiencyValue,
                efficiency && isAbnormal(efficiency.dischargeEfficiency, EFFICIENCY_THRESHOLD) && styles.abnormalText,
              ]}>
                {efficiency ? `${efficiency.dischargeEfficiency}%` : '--'}
              </Text>
              {efficiency && isAbnormal(efficiency.dischargeEfficiency, EFFICIENCY_THRESHOLD) && (
                <Text style={styles.abnormalHint}>低于阈值{`${EFFICIENCY_THRESHOLD}%`}</Text>
              )}
            </View>
            <View style={styles.efficiencyDivider} />
            <View style={styles.efficiencyItem}>
              <Text style={styles.efficiencyLabel}>转换效率</Text>
              <Text style={[
                styles.efficiencyValue,
                efficiency && isAbnormal(efficiency.conversionEfficiency, EFFICIENCY_THRESHOLD) && styles.abnormalText,
              ]}>
                {efficiency ? `${efficiency.conversionEfficiency}%` : '--'}
              </Text>
              {efficiency && isAbnormal(efficiency.conversionEfficiency, EFFICIENCY_THRESHOLD) && (
                <Text style={styles.abnormalHint}>低于阈值{`${EFFICIENCY_THRESHOLD}%`}</Text>
              )}
            </View>
          </View>

          {efficiency && (
            <View style={styles.detailInfo}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>电池温度</Text>
                <Text style={styles.infoValue}>{efficiency.temperature}°C</Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>循环次数</Text>
                <Text style={styles.infoValue}>{efficiency.cycleCount} 次</Text>
              </View>
            </View>
          )}
        </View>
      </View>

      {/* 电池健康度评估 */}
      <View style={styles.section}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🔋 电池健康度评估</Text>
          {efficiency ? (
            <>
              <View style={styles.healthContainer}>
                <View style={styles.healthCircle}>
                  <Text style={[styles.healthValue, { color: getHealthColor(efficiency.healthScore) }]}>
                    {efficiency.healthScore}
                  </Text>
                  <Text style={styles.healthUnit}>分</Text>
                </View>
                <View style={styles.healthInfo}>
                  <Text style={styles.healthStatus}>
                    {efficiency.healthScore >= 80 ? '✅ 健康' : efficiency.healthScore >= 60 ? '⚠️ 一般' : '🔴 需维护'}
                  </Text>
                  <Text style={styles.healthHint}>
                    {efficiency.healthScore >= 80
                      ? '电池状态良好，各项指标正常'
                      : efficiency.healthScore >= 60
                      ? '建议关注充放电效率变化'
                      : '建议尽快安排维护检修'}
                  </Text>
                </View>
              </View>
              <View style={styles.healthBarBg}>
                <View
                  style={[
                    styles.healthBarFill,
                    { width: `${efficiency.healthScore}%`, backgroundColor: getHealthColor(efficiency.healthScore) },
                  ]}
                />
              </View>
            </>
          ) : (
            <View style={styles.loadingBox}>
              <Text style={styles.loadingText}>加载中...</Text>
            </View>
          )}
        </View>
      </View>

      {/* 最近效率趋势 */}
      <View style={styles.section}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📈 最近效率趋势</Text>
          {trends.length > 0 ? (
            <>
              {trends.map((trend, idx) => (
                <View key={idx} style={styles.trendRow}>
                  <Text style={styles.trendDate}>{trend.date}</Text>
                  <View style={styles.trendBars}>
                    <View style={styles.trendBarItem}>
                      <Text style={styles.trendBarLabel}>充电</Text>
                      <View style={styles.trendBarBg}>
                        <View
                          style={[
                            styles.trendBarFill,
                            {
                              width: `${trend.chargeEfficiency}%`,
                              backgroundColor: trend.chargeEfficiency >= EFFICIENCY_THRESHOLD ? '#52c41a' : '#ff4d4f',
                            },
                          ]}
                        />
                      </View>
                      <Text style={styles.trendBarValue}>{trend.chargeEfficiency}%</Text>
                    </View>
                    <View style={styles.trendBarItem}>
                      <Text style={styles.trendBarLabel}>放电</Text>
                      <View style={styles.trendBarBg}>
                        <View
                          style={[
                            styles.trendBarFill,
                            {
                              width: `${trend.dischargeEfficiency}%`,
                              backgroundColor: trend.dischargeEfficiency >= EFFICIENCY_THRESHOLD ? '#52c41a' : '#ff4d4f',
                            },
                          ]}
                        />
                      </View>
                      <Text style={styles.trendBarValue}>{trend.dischargeEfficiency}%</Text>
                    </View>
                    <View style={styles.trendBarItem}>
                      <Text style={styles.trendBarLabel}>转换</Text>
                      <View style={styles.trendBarBg}>
                        <View
                          style={[
                            styles.trendBarFill,
                            {
                              width: `${trend.conversionEfficiency}%`,
                              backgroundColor: trend.conversionEfficiency >= EFFICIENCY_THRESHOLD ? '#52c41a' : '#ff4d4f',
                            },
                          ]}
                        />
                      </View>
                      <Text style={styles.trendBarValue}>{trend.conversionEfficiency}%</Text>
                    </View>
                  </View>
                </View>
              ))}
            </>
          ) : (
            <View style={styles.loadingBox}>
              <Text style={styles.loadingText}>暂无趋势数据</Text>
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1a1a2e',
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  sectionHint: {
    fontSize: 13,
    color: '#999',
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 12,
  },
  section: {
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  deviceCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  deviceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  deviceName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    flex: 1,
  },
  statusTag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  deviceInfo: {
    gap: 8,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLabel: {
    fontSize: 13,
    color: '#999',
  },
  infoValue: {
    fontSize: 13,
    color: '#333',
    fontWeight: '500',
  },
  abnormalText: {
    color: '#ff4d4f',
    fontWeight: 'bold',
  },
  alertBanner: {
    backgroundColor: '#fff2f0',
    borderWidth: 1,
    borderColor: '#ffccc7',
    borderRadius: 6,
    padding: 8,
    marginTop: 10,
  },
  alertText: {
    fontSize: 12,
    color: '#ff4d4f',
  },
  emptyContainer: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: '#999',
  },
  // 详情视图
  backButton: {
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backText: {
    fontSize: 15,
    color: '#1890ff',
  },
  detailHeader: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  detailDeviceName: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1a1a2e',
  },
  detailStation: {
    fontSize: 14,
    color: '#999',
    marginTop: 4,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 16,
  },
  efficiencyRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    marginBottom: 16,
  },
  efficiencyItem: {
    alignItems: 'center',
    flex: 1,
  },
  efficiencyDivider: {
    width: 1,
    height: 40,
    backgroundColor: '#e0e0e0',
  },
  efficiencyLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 6,
  },
  efficiencyValue: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 4,
  },
  abnormalHint: {
    fontSize: 10,
    color: '#ff4d4f',
  },
  detailInfo: {
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
    paddingTop: 12,
    gap: 8,
  },
  healthContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  healthCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#f0f5ff',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 20,
  },
  healthValue: {
    fontSize: 32,
    fontWeight: 'bold',
  },
  healthUnit: {
    fontSize: 12,
    color: '#999',
  },
  healthInfo: {
    flex: 1,
  },
  healthStatus: {
    fontSize: 16,
    marginBottom: 6,
  },
  healthHint: {
    fontSize: 12,
    color: '#999',
    lineHeight: 18,
  },
  healthBarBg: {
    height: 8,
    backgroundColor: '#f0f0f0',
    borderRadius: 4,
    overflow: 'hidden',
  },
  healthBarFill: {
    height: 8,
    borderRadius: 4,
  },
  loadingBox: {
    paddingVertical: 20,
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 14,
    color: '#999',
  },
  trendRow: {
    marginBottom: 12,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f5f5f5',
  },
  trendDate: {
    fontSize: 13,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  trendBars: {
    gap: 6,
  },
  trendBarItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  trendBarLabel: {
    fontSize: 12,
    color: '#999',
    width: 30,
  },
  trendBarBg: {
    flex: 1,
    height: 16,
    backgroundColor: '#f0f0f0',
    borderRadius: 8,
    overflow: 'hidden',
    marginHorizontal: 8,
  },
  trendBarFill: {
    height: 16,
    borderRadius: 8,
  },
  trendBarValue: {
    fontSize: 12,
    color: '#333',
    fontWeight: '600',
    width: 36,
    textAlign: 'right',
  },
});

export default V2GDiagnosisScreen;
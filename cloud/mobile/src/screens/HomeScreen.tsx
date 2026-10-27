import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  FlatList,
} from 'react-native';
import { Picker } from '@react-native-picker/picker';
import { useOffline } from '../store/OfflineContext';
import { cache } from '../services/cache';
import { statsApi, stationApi, alarmApi, workOrderApi, reportsApi } from '../services/api';

interface Station {
  id: string;
  name: string;
  address: string;
  status: string;
  deviceCount: number;
  onlineCount: number;
  capacity: string;
}

interface StatsOverview {
  totalDevices: number;
  onlineDevices: number;
  alarmCount: number;
  pendingWorkOrders: number;
}

interface Alarm {
  id: string;
  title: string;
  level: string;
  status: string;
  deviceName: string;
  stationName: string;
  createdAt: string;
  description?: string;
}

interface WorkOrder {
  id: string;
  title: string;
  priority: string;
  status: string;
  created_at: string;
}

interface EfficiencyOverview {
  utilization: { avg: number; trend: number };
  charging: { avg: number; trend: number };
  generation: { avg: number; trend: number };
}

const statusColors: Record<string, string> = {
  online: '#52c41a',
  offline: '#ff4d4f',
  fault: '#faad14',
  maintenance: '#1890ff',
  正常: '#52c41a',
  告警: '#faad14',
  离线: '#ff4d4f',
  维护中: '#1890ff',
};

const statusLabels: Record<string, string> = {
  online: '在线',
  offline: '离线',
  fault: '故障',
  maintenance: '维护中',
  正常: '正常',
  告警: '告警',
  离线: '离线',
  维护中: '维护中',
};

const levelColors: Record<string, string> = {
  critical: '#ff4d4f',
  warning: '#faad14',
  info: '#1890ff',
};

const levelLabels: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
};

const HomeScreen = ({ navigation }: any) => {
  const { isConnected, getCachedData } = useOffline();
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const [stations, setStations] = useState<Station[]>([]);
  const [stats, setStats] = useState<StatsOverview>({
    totalDevices: 0,
    onlineDevices: 0,
    alarmCount: 0,
    pendingWorkOrders: 0,
  });
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [efficiencyData, setEfficiencyData] = useState<EfficiencyOverview>({
    utilization: { avg: 0, trend: 0 },
    charging: { avg: 0, trend: 0 },
    generation: { avg: 0, trend: 0 },
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 加载站点列表
  const loadStations = useCallback(async () => {
    try {
      if (isConnected) {
        const response = await stationApi.getAll();
        const data = response.data?.data || response.data || [];
        const list = Array.isArray(data) ? data : [];
        setStations(list);
        await cache.set('stations', list);
        // 默认选择第一个站点
        if (list.length > 0 && !selectedStationId) {
          setSelectedStationId(list[0].id);
        }
      } else {
        const cached = await getCachedData<Station[]>('stations');
        if (cached) {
          setStations(cached);
          if (cached.length > 0 && !selectedStationId) {
            setSelectedStationId(cached[0].id);
          }
        }
      }
    } catch (error: any) {
      console.error('[Home] Load stations error:', error.message);
      const cached = await getCachedData<Station[]>('stations');
      if (cached) {
        setStations(cached);
        if (cached.length > 0 && !selectedStationId) {
          setSelectedStationId(cached[0].id);
        }
      }
    }
  }, [isConnected, getCachedData, selectedStationId]);

  // 加载统计数据
  const loadStats = useCallback(async () => {
    const cacheKey = `statsOverview_${selectedStationId || 'all'}`;

    try {
      if (!isConnected) {
        const cached = await cache.get<StatsOverview>(cacheKey);
        if (cached) {
          setStats(cached);
          return;
        }
      }

      if (isConnected) {
        // 这里可以传 stationId 参数给后端，暂时用全局统计
        const response = await statsApi.overview();
        const data = response.data as StatsOverview;
        setStats(data);
        await cache.set(cacheKey, data);
      }
    } catch (error: unknown) {
      console.error('获取统计数据失败:', error);
      const cached = await cache.get<StatsOverview>(cacheKey);
      if (cached) {
        setStats(cached);
      }
    }
  }, [selectedStationId, isConnected]);

  // 加载告警数据
  const loadAlarms = useCallback(async () => {
    const cacheKey = `alarms_${selectedStationId || 'all'}`;

    try {
      if (!isConnected) {
        const cached = await cache.get<Alarm[]>(cacheKey);
        if (cached) {
          setAlarms(cached);
          return;
        }
      }

      if (isConnected) {
        const response = await alarmApi.getAll();
        const data = response.data?.data || response.data || [];
        const list = Array.isArray(data) ? data : [];
        // 如果选中了特定站点，筛选该站点的告警
        const filtered = selectedStationId
          ? list.filter((a: Alarm) => a.stationName && a.stationName.includes(stations.find(s => s.id === selectedStationId)?.name || ''))
          : list.slice(0, 5); // 只显示前5条
        setAlarms(filtered);
        await cache.set(cacheKey, filtered);
      }
    } catch (error: any) {
      console.error('[Home] Load alarms error:', error.message);
      const cached = await cache.get<Alarm[]>(cacheKey);
      if (cached) {
        setAlarms(cached);
      }
    }
  }, [selectedStationId, isConnected, stations]);

  // 加载效率数据
  const loadEfficiencyData = useCallback(async () => {
    const cacheKey = `efficiencyOverview_${selectedStationId || 'all'}`;

    try {
      if (!isConnected) {
        const cached = await cache.get<EfficiencyOverview>(cacheKey);
        if (cached) {
          setEfficiencyData(cached);
          return;
        }
      }

      if (isConnected) {
        const [utilRes, effRes, genRes] = await Promise.all([
          reportsApi.getUtilization(),
          reportsApi.getEfficiency(),
          reportsApi.getGeneration(),
        ]);

        const extractAvgTrend = (res: any): { avg: number; trend: number } => {
          const data = res.data?.data || res.data;
          if (Array.isArray(data) && data.length > 0) {
            const avg = data.reduce((sum: number, d: any) => sum + (d.rate || d.value || 0), 0) / data.length;
            const trend = data[0]?.trend || data[0]?.change || 0;
            return { avg: Math.round(avg * 10) / 10, trend };
          }
          if (data?.avg !== undefined) {
            return { avg: Math.round(data.avg * 10) / 10, trend: data.trend || data.change || 0 };
          }
          return { avg: 0, trend: 0 };
        };

        const overview: EfficiencyOverview = {
          utilization: extractAvgTrend(utilRes),
          charging: extractAvgTrend(effRes),
          generation: extractAvgTrend(genRes),
        };

        setEfficiencyData(overview);
        await cache.set(cacheKey, overview);
      }
    } catch (error: any) {
      console.error('[Home] Load efficiency error:', error.message);
      const cached = await cache.get<EfficiencyOverview>(cacheKey);
      if (cached) {
        setEfficiencyData(cached);
      }
    }
  }, [selectedStationId, isConnected]);

  // 组合加载
  const loadAllData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    await Promise.all([
      loadStations(),
      loadStats(),
      loadAlarms(),
      loadEfficiencyData(),
    ]);

    setLoading(false);
    setRefreshing(false);
  }, [loadStations, loadStats, loadAlarms, loadEfficiencyData]);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // 站点切换处理
  const handleStationChange = (newStationId: string) => {
    setSelectedStationId(newStationId);
    loadStats();
    loadAlarms();
  };

  const selectedStation = useMemo(() => 
    stations.find(s => s.id === selectedStationId) || null, 
    [stations, selectedStationId]
  );

  // 快速操作按钮
  const quickActions = [
    { name: '报修', key: 'Repair', icon: '🔧', color: '#1890ff', action: () => navigation.navigate('WorkOrders') },
    { name: '巡检', key: 'Inspection', icon: '📋', color: '#52c41a', action: () => navigation.navigate('WorkOrders') },
    { name: '联系运维', key: 'Contact', icon: '📞', color: '#722ed1', action: () => Alert.alert('联系运维', '拨打运维热线: 400-800-XXXX') },
  ];

  // 状态栏高度
  const statusBarHeight = 44; // iOS 默认，Android 会自动适配

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadAllData(true)}
          colors={['#1890ff']}
        />
      }
    >
      {/* 状态栏占位 */}
      <View style={{ height: statusBarHeight }} />
      
      {/* 站点选择器 */}
      <View style={styles.stationSelectorContainer}>
        <View style={styles.stationSelector}>
          <Text style={styles.stationSelectorLabel}>当前站点</Text>
          <Picker
            selectedValue={selectedStationId || ''}
            onValueChange={handleStationChange}
            style={styles.picker}
            mode="dropdown"
            itemStyle={styles.pickerItem}
          >
            <Picker.Item label="全部站点" value="" />
            {stations.map((station) => (
              <Picker.Item key={station.id} label={station.name} value={station.id} />
            ))}
          </Picker>
        </View>
      </View>

      {/* 我的站点列表 */}
      {stations.length > 0 && (
        <View style={styles.myStationsSection}>
          <Text style={styles.sectionTitle}>我的站点</Text>
          <FlatList
            data={stations}
            renderItem={({ item }) => (
              <TouchableOpacity
                style={[
                  styles.stationCard,
                  selectedStationId === item.id && styles.stationCardSelected,
                ]}
                onPress={() => handleStationChange(item.id)}
              >
                <View style={styles.stationCardHeader}>
                  <View
                    style={[
                      styles.statusDot,
                      { backgroundColor: statusColors[item.status] || '#999' },
                    ]}
                  />
                  <Text style={styles.stationCardName}>{item.name}</Text>
                </View>
                <Text style={styles.stationCardAddress}>{item.address}</Text>
                <View style={styles.stationCardStats}>
                  <Text style={styles.stationCardStat}>
                    <Text style={styles.statValue}>{item.onlineCount}</Text> / {item.deviceCount} 设备在线
                  </Text>
                  <View
                    style={[
                      styles.statusBadge,
                      { backgroundColor: (statusColors[item.status] || '#999') + '20' },
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusText,
                        { color: statusColors[item.status] || '#999' },
                      ]}
                    >
                      {statusLabels[item.status] || item.status}
                    </Text>
                  </View>
                </View>
              </TouchableOpacity>
            )}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.stationList}
            showsHorizontalScrollIndicator={false}
            horizontal
          />
        </View>
      )}

      {/* 今日概览 - 关键指标卡片 */}
      <View style={styles.statsSection}>
        <Text style={styles.sectionTitle}>今日概览</Text>
        <View style={styles.statsGrid}>
          <View style={styles.statCard}>
            <Text style={styles.statCardLabel}>设备总数</Text>
            <Text style={styles.statCardValue}>{stats.totalDevices}</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statCardLabel}>运行正常</Text>
            <Text style={[styles.statCardValue, { color: '#52c41a' }]}>{stats.onlineDevices}</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statCardLabel}>待处理告警</Text>
            <Text style={[styles.statCardValue, { color: '#ff4d4f' }]}>{stats.alarmCount}</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statCardLabel}>进行中工单</Text>
            <Text style={[styles.statCardValue, { color: '#1890ff' }]}>{stats.pendingWorkOrders}</Text>
          </View>
        </View>
      </View>

      {/* 运行效率概览 */}
      <View style={styles.efficiencySection}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>运行效率概览</Text>
          <TouchableOpacity
            style={styles.viewAllBtn}
            onPress={() => navigation.navigate('Devices')}
          >
            <Text style={styles.viewAllText}>查看详情</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.efficiencyGrid}>
          {/* 设备利用率 */}
          <View style={styles.efficiencyCard}>
            <View style={styles.efficiencyIconWrap}>
              <Text style={styles.efficiencyIcon}>⚡</Text>
            </View>
            <Text style={styles.efficiencyCardLabel}>设备利用率</Text>
            <Text style={styles.efficiencyCardValue}>{efficiencyData.utilization.avg}%</Text>
            {efficiencyData.utilization.trend !== 0 && (
              <View style={styles.trendRow}>
                <Text style={[styles.trendArrow, { color: efficiencyData.utilization.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {efficiencyData.utilization.trend > 0 ? '↑' : '↓'}
                </Text>
                <Text style={[styles.trendValue, { color: efficiencyData.utilization.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {Math.abs(efficiencyData.utilization.trend)}%
                </Text>
              </View>
            )}
          </View>

          {/* 充电效率 */}
          <View style={styles.efficiencyCard}>
            <View style={styles.efficiencyIconWrap}>
              <Text style={styles.efficiencyIcon}>🔋</Text>
            </View>
            <Text style={styles.efficiencyCardLabel}>充电效率</Text>
            <Text style={styles.efficiencyCardValue}>{efficiencyData.charging.avg}%</Text>
            {efficiencyData.charging.trend !== 0 && (
              <View style={styles.trendRow}>
                <Text style={[styles.trendArrow, { color: efficiencyData.charging.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {efficiencyData.charging.trend > 0 ? '↑' : '↓'}
                </Text>
                <Text style={[styles.trendValue, { color: efficiencyData.charging.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {Math.abs(efficiencyData.charging.trend)}%
                </Text>
              </View>
            )}
          </View>

          {/* 发电效率 */}
          <View style={styles.efficiencyCard}>
            <View style={styles.efficiencyIconWrap}>
              <Text style={styles.efficiencyIcon}>☀️</Text>
            </View>
            <Text style={styles.efficiencyCardLabel}>发电效率</Text>
            <Text style={styles.efficiencyCardValue}>{efficiencyData.generation.avg}%</Text>
            {efficiencyData.generation.trend !== 0 && (
              <View style={styles.trendRow}>
                <Text style={[styles.trendArrow, { color: efficiencyData.generation.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {efficiencyData.generation.trend > 0 ? '↑' : '↓'}
                </Text>
                <Text style={[styles.trendValue, { color: efficiencyData.generation.trend > 0 ? '#52c41a' : '#ff4d4f' }]}>
                  {Math.abs(efficiencyData.generation.trend)}%
                </Text>
              </View>
            )}
          </View>
        </View>
      </View>

      {/* 待关注事项 - 告警列表 */}
      {alarms.length > 0 && (
        <View style={styles.alarmsSection}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>待关注事项</Text>
            <TouchableOpacity
              style={styles.viewAllBtn}
              onPress={() => navigation.navigate('Alarms')}
            >
              <Text style={styles.viewAllText}>查看全部</Text>
            </TouchableOpacity>
          </View>
          <FlatList
            data={alarms}
            renderItem={({ item }) => (
              <TouchableOpacity
                style={styles.alarmItem}
                onPress={() => navigation.navigate('Alarms')}
              >
                <View style={styles.alarmItemHeader}>
                  <View
                    style={[
                      styles.levelBadge,
                      { backgroundColor: (levelColors[item.level] || '#1890ff') + '20' },
                    ]}
                  >
                    <Text
                      style={[
                        styles.levelText,
                        { color: levelColors[item.level] || '#1890ff' },
                      ]}
                    >
                      {levelLabels[item.level] || item.level}
                    </Text>
                  </View>
                  <Text style={styles.alarmTime}>{item.createdAt}</Text>
                </View>
                <Text style={styles.alarmTitle}>{item.title}</Text>
                <View style={styles.alarmMeta}>
                  <Text style={styles.alarmMetaText}>{item.stationName}</Text>
                  <Text style={styles.alarmMetaText}>{item.deviceName}</Text>
                </View>
              </TouchableOpacity>
            )}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.alarmList}
            showsVerticalScrollIndicator={false}
          />
        </View>
      )}

      {/* 快速操作 */}
      <View style={styles.quickActionsSection}>
        <Text style={styles.sectionTitle}>快速操作</Text>
        <View style={styles.quickActionsGrid}>
          {quickActions.map((action) => (
            <TouchableOpacity
              key={action.key}
              style={[styles.quickActionBtn, { borderColor: action.color }]}
              onPress={action.action}
            >
              <Text style={styles.quickActionIcon}>{action.icon}</Text>
              <Text
                style={[
                  styles.quickActionText,
                  { color: action.color },
                ]}
              >
                {action.name}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* 底部安全间距 */}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
};

import { RefreshControl, Alert } from 'react-native';

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 16,
    color: '#999',
    fontSize: 14,
  },
  stationSelectorContainer: {
    padding: 16,
    paddingTop: 8,
  },
  stationSelector: {
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: '#e8e8e8',
  },
  stationSelectorLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  picker: {
    height: 44,
    color: '#333',
  },
  pickerItem: {
    fontSize: 16,
    color: '#333',
  },
  myStationsSection: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 12,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  viewAllBtn: {
    padding: 4,
  },
  viewAllText: {
    fontSize: 13,
    color: '#1890ff',
  },
  stationList: {
    paddingRight: 16,
  },
  stationCard: {
    width: 200,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginRight: 12,
    borderWidth: 1,
    borderColor: '#e8e8e8',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  stationCardSelected: {
    borderColor: '#1890ff',
    borderWidth: 2,
  },
  stationCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  stationCardName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  stationCardAddress: {
    fontSize: 12,
    color: '#999',
    marginBottom: 8,
  },
  stationCardStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  stationCardStat: {
    fontSize: 12,
    color: '#666',
  },
  statValue: {
    fontWeight: '600',
    color: '#333',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  statusText: {
    fontSize: 11,
    fontWeight: '500',
  },
  statsSection: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -6,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    maxWidth: '50%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 6,
    marginBottom: 12,
    alignItems: 'center',
  },
  statCardLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  statCardValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1a1a2e',
  },
  alarmsSection: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  alarmList: {
    paddingBottom: 8,
  },
  alarmItem: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderLeftWidth: 4,
    borderLeftColor: '#ff4d4f',
  },
  alarmItemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  levelBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  levelText: {
    fontSize: 11,
    fontWeight: '600',
  },
  alarmTime: {
    fontSize: 11,
    color: '#999',
  },
  alarmTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 6,
  },
  alarmMeta: {
    flexDirection: 'row',
    gap: 12,
  },
  alarmMetaText: {
    fontSize: 12,
    color: '#999',
  },
  efficiencySection: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  efficiencyGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  efficiencyCard: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 4,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  efficiencyIconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#f0f5ff',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  efficiencyIcon: {
    fontSize: 18,
  },
  efficiencyCardLabel: {
    fontSize: 11,
    color: '#999',
    marginBottom: 4,
  },
  efficiencyCardValue: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 4,
  },
  trendRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  trendArrow: {
    fontSize: 12,
    fontWeight: 'bold',
    marginRight: 2,
  },
  trendValue: {
    fontSize: 11,
    fontWeight: '500',
  },
  quickActionsSection: {
    padding: 16,
    paddingBottom: 32,
  },
  quickActionsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  quickActionBtn: {
    flex: 1,
    maxWidth: 90,
    alignItems: 'center',
    paddingVertical: 20,
    borderRadius: 12,
    borderWidth: 1.5,
    backgroundColor: '#fff',
  },
  quickActionIcon: {
    fontSize: 28,
    marginBottom: 8,
  },
  quickActionText: {
    fontSize: 14,
    fontWeight: '500',
  },
});

export default HomeScreen;
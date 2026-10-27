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
import { useOffline } from '../store/OfflineContext';
import { stationApi, deviceApi, workOrderApi } from '../services/api';
import { cache } from '../services/cache';

interface RouteParams {
  stationId: string;
}

interface StationDetail {
  id: string;
  name: string;
  address: string;
  capacity: string;
  operationDate: string;
  maintenanceTeam: string;
  status: string;
}

interface DeviceStats {
  pv: { total: number; online: number; offline: number };
  storage: { total: number; online: number; offline: number };
  charger: { total: number; online: number; offline: number };
}

interface WorkOrder {
  id: string;
  title: string;
  status: string;
  level: string;
  createdAt: string;
}

const StationDetailScreen = ({ route }: { route: { params: RouteParams } }) => {
  const { stationId } = route.params;
  const [station, setStation] = useState<StationDetail | null>(null);
  const [deviceStats, setDeviceStats] = useState<DeviceStats | null>(null);
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
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
        const [stationRes, devicesRes, workOrdersRes] = await Promise.all([
          stationApi.getById(stationId),
          deviceApi.getAll(),
          workOrderApi.getAll(),
        ]);

        // C端信封 {code:0, data:{公开视图+branding}}; 映射到本地展示模型
        const raw = stationRes.data?.data || stationRes.data || {};
        const stationData: StationDetail = {
          id: String(raw.id ?? stationId),
          name: raw.name || '-',
          address: raw.address || '-',
          capacity: raw.total_power != null ? `${raw.total_power}kW` : (raw.capacity || '-'),
          operationDate: raw.operationDate || '-',
          maintenanceTeam: raw.branding?.operator_name || raw.operator_name || raw.maintenanceTeam || '-',
          status: raw.status || '-',
        };
        const devicesData = devicesRes.data;
        const workOrdersData = workOrdersRes.data;

        setStation(stationData);

        // 计算设备统计
        const stats: DeviceStats = {
          pv: { total: 0, online: 0, offline: 0 },
          storage: { total: 0, online: 0, offline: 0 },
          charger: { total: 0, online: 0, offline: 0 },
        };

        devicesData.forEach((device: any) => {
          if (device.stationId === stationId) {
            const type = device.type.toLowerCase();
            const key = type.includes('光伏') || type.includes('pv') ? 'pv' :
                       type.includes('储能') || type.includes('storage') ? 'storage' : 'charger';
            stats[key].total++;
            if (device.online) stats[key].online++;
            else stats[key].offline++;
          }
        });

        setDeviceStats(stats);

        // 筛选该站点的最近工单
        const recentOrders = workOrdersData
          .filter((wo: any) => wo.stationId === stationId)
          .slice(0, 5);
        setWorkOrders(recentOrders);

        // 缓存数据
        await cache.set(`station_${stationId}`, stationData);
        await cache.set(`station_${stationId}_devices`, stats);
        await cache.set(`station_${stationId}_workorders`, recentOrders);
      } else {
        // 离线模式
        const cachedStation = await getCachedData<StationDetail>(`station_${stationId}`);
        const cachedStats = await getCachedData<DeviceStats>(`station_${stationId}_devices`);
        const cachedOrders = await getCachedData<WorkOrder[]>(`station_${stationId}_workorders`);

        if (cachedStation) setStation(cachedStation);
        if (cachedStats) setDeviceStats(cachedStats);
        if (cachedOrders) setWorkOrders(cachedOrders);
      }
    } catch (error: any) {
      console.error('[StationDetail] Load error:', error.message);
      // 尝试从缓存加载
      const cachedStation = await getCachedData<StationDetail>(`station_${stationId}`);
      const cachedStats = await getCachedData<DeviceStats>(`station_${stationId}_devices`);
      const cachedOrders = await getCachedData<WorkOrder[]>(`station_${stationId}_workorders`);

      if (cachedStation) setStation(cachedStation);
      if (cachedStats) setDeviceStats(cachedStats);
      if (cachedOrders) setWorkOrders(cachedOrders);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [stationId, isConnected, getCachedData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '正常':
      case '已完成':
        return '#52c41a';
      case '告警':
      case '处理中':
        return '#faad14';
      case '故障':
      case '待处理':
        return '#ff4d4f';
      default:
        return '#999';
    }
  };

  const renderDeviceStats = (title: string, stats: { total: number; online: number; offline: number }) => (
    <View style={styles.statsCard}>
      <Text style={styles.statsTitle}>{title}</Text>
      <View style={styles.statsRow}>
        <Text style={styles.statsLabel}>总数</Text>
        <Text style={styles.statsValue}>{stats.total}</Text>
      </View>
      <View style={styles.statsRow}>
        <Text style={[styles.statsLabel, { color: '#52c41a' }]}>在线</Text>
        <Text style={[styles.statsValue, { color: '#52c41a' }]}>{stats.online}</Text>
      </View>
      <View style={styles.statsRow}>
        <Text style={[styles.statsLabel, { color: '#ff4d4f' }]}>离线</Text>
        <Text style={[styles.statsValue, { color: '#ff4d4f' }]}>{stats.offline}</Text>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载站点详情...</Text>
      </View>
    );
  }

  if (!station) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyIcon}>📭</Text>
        <Text style={styles.emptyText}>暂无数据</Text>
        {!isConnected && <Text style={styles.emptySubtext}>请连接网络后刷新</Text>}
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
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
            <Text style={styles.infoLabel}>站点名称</Text>
            <Text style={styles.infoValue}>{station.name}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>地址</Text>
            <Text style={styles.infoValue}>{station.address}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>容量</Text>
            <Text style={styles.infoValue}>{station.capacity}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>投运日期</Text>
            <Text style={styles.infoValue}>{station.operationDate}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>运维团队</Text>
            <Text style={styles.infoValue}>{station.maintenanceTeam}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>状态</Text>
            <View style={[styles.statusBadge, { backgroundColor: getStatusColor(station.status) + '20' }]}>
              <Text style={[styles.statusText, { color: getStatusColor(station.status) }]}>
                {station.status}
              </Text>
            </View>
          </View>
        </View>
      </View>

      {/* 设备分布统计 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>设备分布统计</Text>
        {deviceStats && (
          <View style={styles.statsGrid}>
            {renderDeviceStats('光伏设备', deviceStats.pv)}
            {renderDeviceStats('储能设备', deviceStats.storage)}
            {renderDeviceStats('充电设备', deviceStats.charger)}
          </View>
        )}
      </View>

      {/* 最近工单 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>最近工单</Text>
        {workOrders.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>暂无工单</Text>
          </View>
        ) : (
          workOrders.map((wo) => (
            <TouchableOpacity key={wo.id} style={styles.workOrderItem}>
              <View style={styles.woLeft}>
                <Text style={styles.woTitle}>{wo.title}</Text>
                <Text style={styles.woDate}>{wo.createdAt}</Text>
              </View>
              <View style={styles.woRight}>
                <View style={[styles.woBadge, { backgroundColor: getStatusColor(wo.status) + '20' }]}>
                  <Text style={[styles.woStatus, { color: getStatusColor(wo.status) }]}>{wo.status}</Text>
                </View>
                <Text style={styles.woLevel}>级别: {wo.level}</Text>
              </View>
            </TouchableOpacity>
          ))
        )}
      </View>
    </ScrollView>
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
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -8,
  },
  statsCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 8,
    marginBottom: 12,
  },
  statsTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 12,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  statsLabel: {
    fontSize: 14,
    color: '#666',
  },
  statsValue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
  },
  workOrderItem: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  woLeft: {
    flex: 1,
  },
  woTitle: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
    marginBottom: 4,
  },
  woDate: {
    fontSize: 12,
    color: '#999',
  },
  woRight: {
    alignItems: 'flex-end',
  },
  woBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
    marginBottom: 4,
  },
  woStatus: {
    fontSize: 12,
    fontWeight: '500',
  },
  woLevel: {
    fontSize: 12,
    color: '#666',
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
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

export default StationDetailScreen;
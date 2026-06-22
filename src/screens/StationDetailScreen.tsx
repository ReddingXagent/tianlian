import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useRoute, RouteProp, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationStore } from '../store/stationStore';
import { RootStackParamList, Device, Alarm } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type StationDetailRouteProp = RouteProp<RootStackParamList, 'StationDetail'>;

const StationDetailScreen: React.FC = () => {
  const route = useRoute<StationDetailRouteProp>();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { stationId } = route.params;
  const {
    selectedStation,
    devices,
    alarms,
    loading,
    error,
    fetchStationDetail,
    fetchStationDevices,
    fetchStationAlarms,
  } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'devices' | 'alarms'>('devices');

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    await Promise.all([
      fetchStationDetail(stationId),
      fetchStationDevices(stationId),
      fetchStationAlarms(stationId),
    ]);
    if (isRefresh) setRefreshing(false);
  }, [stationId, fetchStationDetail, fetchStationDevices, fetchStationAlarms]);

  useEffect(() => {
    loadData();
  }, [stationId]);

  if (loading && !selectedStation) {
    return <LoadingSpinner text="加载站点详情..." />;
  }

  if (error && !selectedStation) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => loadData()}
      />
    );
  }

  const station = selectedStation;

  const renderDeviceItem = (device: Device) => (
    <View key={device.id} style={styles.itemCard}>
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{device.name}</Text>
        <StatusBadge status={device.status} />
      </View>
      <Text style={styles.itemMeta}>型号: {device.model}</Text>
      <Text style={styles.itemMeta}>厂商: {device.manufacturer}</Text>
      <Text style={styles.itemMeta}>类型: {deviceTypeLabel(device.type)}</Text>
    </View>
  );

  const renderAlarmItem = (alarm: Alarm) => (
    <View key={alarm.id} style={styles.itemCard}>
      <View style={styles.itemHeader}>
        <Text style={styles.itemName} numberOfLines={1}>{alarm.title}</Text>
        <StatusBadge status={alarm.level} />
      </View>
      <Text style={styles.itemMeta} numberOfLines={2}>{alarm.description}</Text>
      <View style={styles.itemFooter}>
        <StatusBadge status={alarm.status} />
        <Text style={styles.itemTime}>
          {new Date(alarm.createdAt).toLocaleString('zh-CN')}
        </Text>
      </View>
    </View>
  );

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadData(true)}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* 站点信息卡片 */}
      <View style={styles.infoCard}>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>站点名称</Text>
          <Text style={styles.infoValue}>{station?.name}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>站点编号</Text>
          <Text style={styles.infoValue}>{station?.code}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>状态</Text>
          <StatusBadge status={station?.status ?? 'offline'} />
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>地址</Text>
          <Text style={[styles.infoValue, styles.infoAddress]}>{station?.address}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>设备数量</Text>
          <Text style={styles.infoValue}>{station?.deviceCount} 台</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>在线设备</Text>
          <Text style={[styles.infoValue, { color: '#2e7d32' }]}>
            {station?.onlineDeviceCount} 台
          </Text>
        </View>
        <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
          <Text style={styles.infoLabel}>告警数量</Text>
          <Text style={[styles.infoValue, { color: station && station.alarmCount > 0 ? '#c62828' : '#2e7d32' }]}>
            {station?.alarmCount} 条
          </Text>
        </View>
      </View>

      {/* 监控面板入口 */}
      <TouchableOpacity
        style={styles.monitorButton}
        onPress={() => navigation.navigate('ChargerMonitor', { stationId, stationName: station?.name || '' })}
        activeOpacity={0.7}
      >
        <Text style={styles.monitorButtonIcon}>⚡</Text>
        <View style={styles.monitorButtonContent}>
          <Text style={styles.monitorButtonTitle}>充电桩实时监控</Text>
          <Text style={styles.monitorButtonDesc}>查看充电桩功率、温度、状态等实时数据</Text>
        </View>
        <Text style={styles.monitorButtonArrow}>›</Text>
      </TouchableOpacity>

      {/* Tab 切换 */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'devices' && styles.tabActive]}
          onPress={() => setActiveTab('devices')}
        >
          <Text style={[styles.tabText, activeTab === 'devices' && styles.tabTextActive]}>
            设备列表
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'alarms' && styles.tabActive]}
          onPress={() => setActiveTab('alarms')}
        >
          <Text style={[styles.tabText, activeTab === 'alarms' && styles.tabTextActive]}>
            告警记录
          </Text>
        </TouchableOpacity>
      </View>

      {/* 列表内容 */}
      {activeTab === 'devices' ? (
        devices.length === 0 ? (
          <EmptyState icon="🔌" title="暂无设备" message="该站点暂无关联设备" />
        ) : (
          devices.map(renderDeviceItem)
        )
      ) : (
        alarms.length === 0 ? (
          <EmptyState icon="✅" title="暂无告警" message="该站点目前没有告警记录" />
        ) : (
          alarms.map(renderAlarmItem)
        )
      )}
    </ScrollView>
  );
};

const deviceTypeLabel = (type: string): string => {
  const map: Record<string, string> = {
    charger: '充电桩',
    battery: '电池',
    inverter: '逆变器',
    sensor: '传感器',
    other: '其他',
  };
  return map[type] || type;
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
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#999',
    flex: 1,
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
    flex: 2,
    textAlign: 'right',
  },
  infoAddress: {
    fontSize: 13,
    color: '#666',
  },
  monitorButton: {
    flexDirection: 'row',
    alignItems: 'center',
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
  monitorButtonIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  monitorButtonContent: {
    flex: 1,
  },
  monitorButtonTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    marginBottom: 2,
  },
  monitorButtonDesc: {
    fontSize: 12,
    color: '#999',
  },
  monitorButtonArrow: {
    fontSize: 20,
    color: '#ccc',
    marginLeft: 8,
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
    marginBottom: 2,
  },
  itemFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
  },
  itemTime: {
    fontSize: 12,
    color: '#bbb',
  },
});

export default StationDetailScreen;
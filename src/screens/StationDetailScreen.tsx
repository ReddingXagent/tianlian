import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  ScrollView, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import { useStationStore } from '../store/stationStore';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../types';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function StationDetailScreen() {
  const route = useRoute();
  const navigation = useNavigation<NavProp>();
  const { stationId } = route.params as { stationId: number };
  const { selectedStation, devices, alarms, loading, fetchStationDetail, fetchStationDevices, fetchStationAlarms } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([
      fetchStationDetail(stationId),
      fetchStationDevices(stationId),
      fetchStationAlarms(stationId),
    ]);
    setRefreshing(false);
  }, [stationId, fetchStationDetail, fetchStationDevices, fetchStationAlarms]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading && !selectedStation) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#4ECDC4" /></View>;
  }

  const station = selectedStation;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor="#4ECDC4" />}
    >
      {/* 站点信息头部 */}
      <View style={styles.headerCard}>
        <Text style={styles.stationName}>{station?.name}</Text>
        <Text style={styles.stationCode}>编码: {station?.code}</Text>
        <Text style={styles.stationAddr}>{station?.address}</Text>
        <View style={styles.statusRow}>
          <View style={[styles.badge, station?.status === 'online' ? styles.badgeOnline : styles.badgeOffline]}>
            <Text style={styles.badgeText}>{station?.status === 'online' ? '在线' : '离线'}</Text>
          </View>
        </View>
      </View>

      {/* 快捷操作 */}
      <View style={styles.actionsRow}>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('DeviceList', { stationId, stationName: station?.name || '站点' })}
        >
          <Text style={styles.actionIcon}>🔌</Text>
          <Text style={styles.actionLabel}>设备</Text>
          <Text style={styles.actionCount}>{devices.length}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('AlarmList', { stationId })}
        >
          <Text style={styles.actionIcon}>🔔</Text>
          <Text style={styles.actionLabel}>告警</Text>
          <Text style={styles.actionCount}>{alarms.length}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('WorkOrder', { stationId })}
        >
          <Text style={styles.actionIcon}>📋</Text>
          <Text style={styles.actionLabel}>工单</Text>
        </TouchableOpacity>
      </View>

      {/* 设备列表 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>设备列表 ({devices.length})</Text>
        {devices.slice(0, 5).map((device) => (
          <View key={device.id} style={styles.deviceItem}>
            <View style={styles.deviceInfo}>
              <Text style={styles.deviceName}>{device.name}</Text>
              <Text style={styles.deviceModel}>{device.model}</Text>
            </View>
            <View style={[styles.dot, device.status === 'online' ? styles.dotOnline : device.status === 'fault' ? styles.dotFault : styles.dotOffline]} />
          </View>
        ))}
        {devices.length === 0 && <Text style={styles.emptyText}>暂无设备</Text>}
        {devices.length > 5 && (
          <TouchableOpacity onPress={() => navigation.navigate('DeviceList', { stationId, stationName: station?.name || '站点' })}>
            <Text style={styles.seeAll}>查看全部设备 →</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* 最近告警 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>最近告警</Text>
        {alarms.slice(0, 3).map((alarm) => (
          <View key={alarm.id} style={styles.alarmItem}>
            <View style={[styles.alarmLevel, alarm.level === 'critical' ? styles.alarmCritical : styles.alarmWarning]} />
            <View style={styles.alarmInfo}>
              <Text style={styles.alarmTitle}>{alarm.title}</Text>
              <Text style={styles.alarmTime}>{new Date(alarm.createdAt).toLocaleString('zh-CN')}</Text>
            </View>
          </View>
        ))}
        {alarms.length === 0 && <Text style={styles.emptyText}>无告警 🎉</Text>}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  headerCard: { padding: 20, backgroundColor: '#1a1a2e', margin: 16, borderRadius: 12 },
  stationName: { fontSize: 22, fontWeight: 'bold', color: '#fff' },
  stationCode: { fontSize: 13, color: '#666', marginTop: 4 },
  stationAddr: { fontSize: 14, color: '#888', marginTop: 4 },
  statusRow: { flexDirection: 'row', marginTop: 12 },
  badge: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 8 },
  badgeOnline: { backgroundColor: 'rgba(39,174,96,0.25)' },
  badgeOffline: { backgroundColor: 'rgba(231,76,60,0.25)' },
  badgeText: { fontSize: 12, color: '#fff' },
  actionsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 12, marginBottom: 8 },
  actionBtn: { flex: 1, backgroundColor: '#1a1a2e', borderRadius: 12, padding: 16, alignItems: 'center', gap: 4 },
  actionIcon: { fontSize: 28 },
  actionLabel: { fontSize: 13, color: '#ccc' },
  actionCount: { fontSize: 11, color: '#666' },
  section: { padding: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#fff', marginBottom: 12 },
  deviceItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1a1a2e', borderRadius: 10, padding: 14, marginBottom: 8 },
  deviceInfo: { flex: 1 },
  deviceName: { fontSize: 15, color: '#fff', fontWeight: '500' },
  deviceModel: { fontSize: 12, color: '#666', marginTop: 2 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  dotOnline: { backgroundColor: '#27ae60' },
  dotFault: { backgroundColor: '#e74c3c' },
  dotOffline: { backgroundColor: '#666' },
  alarmItem: { flexDirection: 'row', backgroundColor: '#1a1a2e', borderRadius: 10, padding: 14, marginBottom: 8, gap: 12 },
  alarmLevel: { width: 4, borderRadius: 2 },
  alarmCritical: { backgroundColor: '#e74c3c' },
  alarmWarning: { backgroundColor: '#f39c12' },
  alarmInfo: { flex: 1 },
  alarmTitle: { fontSize: 14, color: '#fff' },
  alarmTime: { fontSize: 12, color: '#666', marginTop: 4 },
  emptyText: { color: '#666', textAlign: 'center', paddingVertical: 16 },
  seeAll: { color: '#4ECDC4', fontSize: 14, textAlign: 'center', paddingVertical: 12 },
});

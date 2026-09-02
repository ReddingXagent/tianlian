import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  ScrollView, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import { useStationStore } from '../store/stationStore';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../types';
import { useTheme } from '../hooks/useTheme';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function StationDetailScreen() {
  const { colors } = useTheme();
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
    // F1203: 微任务解耦 effect 直调 async
    Promise.resolve().then(() => loadData());
  }, [loadData]);

  if (loading && !selectedStation) {
    return <View style={[styles.center, { backgroundColor: colors.pageBg }]}><ActivityIndicator size="large" color={colors.primary} /></View>;
  }

  const station = selectedStation;

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor={colors.primary} />}
    >
      {/* 站点信息头部 */}
      <View style={[styles.headerCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.stationName, { color: colors.textPrimary }]}>{station?.name}</Text>
        <Text style={[styles.stationCode, { color: colors.textMuted }]}>编码: {station?.code}</Text>
        <Text style={[styles.stationAddr, { color: colors.textSecondary }]}>{station?.address}</Text>
        <View style={styles.statusRow}>
          <View style={[styles.badge, { backgroundColor: station?.status === 'online' ? colors.successBg : colors.errorBg }]}>
            <Text style={[styles.badgeText, { color: station?.status === 'online' ? colors.success : colors.error }]}>{station?.status === 'online' ? '在线' : '离线'}</Text>
          </View>
        </View>
      </View>

      {/* 快捷操作 */}
      <View style={styles.actionsRow}>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.cardBg }]}
          onPress={() => navigation.navigate('DeviceList', { stationId, stationName: station?.name || '站点' })}
         testID="stationdetail-action-devices"
         accessibilityRole="button">
          <Text style={styles.actionIcon}>🔌</Text>
          <Text style={[styles.actionLabel, { color: colors.textSecondary }]}>设备</Text>
          <Text style={[styles.actionCount, { color: colors.textMuted }]}>{devices.length}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.cardBg }]}
          onPress={() => navigation.navigate('AlarmList', { stationId })}
         testID="stationdetail-action-alarms"
         accessibilityRole="button">
          <Text style={styles.actionIcon}>🔔</Text>
          <Text style={[styles.actionLabel, { color: colors.textSecondary }]}>告警</Text>
          <Text style={[styles.actionCount, { color: colors.textMuted }]}>{alarms.length}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.cardBg }]}
          onPress={() => navigation.navigate('WorkOrder', { stationId })}
         testID="stationdetail-action-workorders"
         accessibilityRole="button">
          <Text style={styles.actionIcon}>📋</Text>
          <Text style={[styles.actionLabel, { color: colors.textSecondary }]}>工单</Text>
        </TouchableOpacity>
      </View>

      {/* 设备列表 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>设备列表 ({devices.length})</Text>
        {devices.slice(0, 5).map((device) => (
          <View key={device.id} style={[styles.deviceItem, { backgroundColor: colors.cardBg }]}>
            testID={`stationdetail-device-${device.id}`}
            <View style={styles.deviceInfo}>
              <Text style={[styles.deviceName, { color: colors.textPrimary }]}>{device.name}</Text>
              <Text style={[styles.deviceModel, { color: colors.textMuted }]}>{device.model}</Text>
            </View>
            <View style={[styles.dot, { backgroundColor: device.status === 'online' ? colors.success : device.status === 'fault' ? colors.error : colors.textMuted }]} />
          </View>
        ))}
        {devices.length === 0 && <Text style={[styles.emptyText, { color: colors.textMuted }]}>暂无设备</Text>}
        {devices.length > 5 && (
          <TouchableOpacity onPress={() => navigation.navigate('DeviceList', { stationId, stationName: station?.name || '站点' })} accessibilityRole="button"
            testID="stationdetail-see-all-devices"
          >
            <Text style={[styles.seeAll, { color: colors.primary }]}>查看全部设备 →</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* 最近告警 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>最近告警</Text>
        {alarms.slice(0, 3).map((alarm) => (
          <View key={alarm.id} style={[styles.alarmItem, { backgroundColor: colors.cardBg }]}>
            testID={`stationdetail-alarm-${alarm.id}`}
            <View style={[styles.alarmLevel, { backgroundColor: alarm.level === 'critical' ? colors.error : colors.warning }]} />
            <View style={styles.alarmInfo}>
              <Text style={[styles.alarmTitle, { color: colors.textPrimary }]}>{alarm.title}</Text>
              <Text style={[styles.alarmTime, { color: colors.textMuted }]}>{new Date(alarm.createdAt).toLocaleString('zh-CN')}</Text>
            </View>
          </View>
        ))}
        {alarms.length === 0 && <Text style={[styles.emptyText, { color: colors.textMuted }]}>无告警 🎉</Text>}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  headerCard: { padding: 20, margin: 16, borderRadius: 12 },
  stationName: { fontSize: 22, fontWeight: 'bold' },
  stationCode: { fontSize: 13, marginTop: 4 },
  stationAddr: { fontSize: 14, marginTop: 4 },
  statusRow: { flexDirection: 'row', marginTop: 12 },
  badge: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 8 },
  badgeText: { fontSize: 12 },
  actionsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 12, marginBottom: 8 },
  actionBtn: { flex: 1, borderRadius: 12, padding: 16, alignItems: 'center', gap: 4 },
  actionIcon: { fontSize: 28 },
  actionLabel: { fontSize: 13 },
  actionCount: { fontSize: 11 },
  section: { padding: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '600', marginBottom: 12 },
  deviceItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderRadius: 10, padding: 14, marginBottom: 8 },
  deviceInfo: { flex: 1 },
  deviceName: { fontSize: 15, fontWeight: '500' },
  deviceModel: { fontSize: 12, marginTop: 2 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  alarmItem: { flexDirection: 'row', borderRadius: 10, padding: 14, marginBottom: 8, gap: 12 },
  alarmLevel: { width: 4, borderRadius: 2 },
  alarmInfo: { flex: 1 },
  alarmTitle: { fontSize: 14 },
  alarmTime: { fontSize: 12, marginTop: 4 },
  emptyText: { textAlign: 'center', paddingVertical: 16 },
  seeAll: { fontSize: 14, textAlign: 'center', paddingVertical: 12 },
});

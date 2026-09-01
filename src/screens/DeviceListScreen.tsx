import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, FlatList, StyleSheet, RefreshControl, ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import { useStationStore } from '../store/stationStore';
import { Device } from '../types';
import { useTheme } from '../hooks/useTheme';


export default function DeviceListScreen() {
  const { colors } = useTheme();
  const route = useRoute();
  const { stationId } = route.params as { stationId: number };
  const { devices, loading, fetchStationDevices } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    await fetchStationDevices(stationId);
    setRefreshing(false);
  }, [stationId, fetchStationDevices]);

  useEffect(() => {
    // F1203: 微任务解耦 effect 直调 async
    Promise.resolve().then(() => loadData());
  }, [loadData]);

  // 状态点: 在线=success / 故障=error / 离线=textMuted(原#666)
  const dotColor = (status: Device['status']) =>
    status === 'online' ? colors.success : status === 'fault' ? colors.error : colors.textMuted;
  // 标签底: 在线=successBg / 离线(或故障)=errorBg(原rgba状态底)
  const tagBg = (status: Device['status']) =>
    status === 'online' ? colors.successBg : colors.errorBg;

  const renderItem = ({ item }: { item: Device }) => (
    <TouchableOpacity style={[styles.card, { backgroundColor: colors.cardBg }]}>
      <View style={styles.cardHeader}>
        <View>
          <Text style={[styles.deviceName, { color: colors.textPrimary }]}>{item.name}</Text>
          <Text style={[styles.deviceCode, { color: colors.textMuted }]}>{item.code} · {item.model}</Text>
        </View>
        <View style={[styles.statusDot, { backgroundColor: dotColor(item.status) }]} />
      </View>
      <View style={styles.tagRow}>
        <View style={[styles.tag, { backgroundColor: colors.infoBg }]}><Text style={[styles.tagText, { color: colors.textSecondary }]}>{deviceTypeLabel(item.type)}</Text></View>
        <View style={[styles.tag, { backgroundColor: tagBg(item.status) }]}>
          <Text style={[styles.tagText, { color: colors.textSecondary }]}>{item.status === 'online' ? '在线' : item.status === 'fault' ? '故障' : '离线'}</Text>
        </View>
      </View>
      <Text style={[styles.heartbeat, { color: colors.textSecondary }]}>最后心跳: {new Date(item.lastHeartbeat).toLocaleString('zh-CN')}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      {loading && !refreshing ? (
        <View style={styles.center}><ActivityIndicator size="large" color={colors.primary} /></View>
      ) : (
        <FlatList
          data={devices}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor={colors.primary} />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={<View style={styles.center}><Text style={[styles.emptyText, { color: colors.textMuted }]}>暂无设备</Text></View>}
        />
      )}
    </View>
  );
}

function deviceTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    charger: '充电桩', battery: '储能', inverter: '逆变器', sensor: '传感器', other: '其他',
  };
  return labels[type] || type;
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  card: { borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  deviceName: { fontSize: 16, fontWeight: '600' },
  deviceCode: { fontSize: 12, marginTop: 4 },
  statusDot: { width: 12, height: 12, borderRadius: 6, marginTop: 6 },
  tagRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  tag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  tagText: { fontSize: 12 },
  heartbeat: { fontSize: 12, marginTop: 10 },
  emptyText: { fontSize: 15 },
});

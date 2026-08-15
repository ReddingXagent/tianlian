import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, FlatList, StyleSheet, RefreshControl, ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import { useStationStore } from '../store/stationStore';
import { Device } from '../types';


export default function DeviceListScreen() {
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
    loadData();
  }, [loadData]);

  const renderItem = ({ item }: { item: Device }) => (
    <TouchableOpacity style={styles.card}>
      <View style={styles.cardHeader}>
        <View>
          <Text style={styles.deviceName}>{item.name}</Text>
          <Text style={styles.deviceCode}>{item.code} · {item.model}</Text>
        </View>
        <View style={[styles.statusDot, item.status === 'online' ? styles.dotOnline : item.status === 'fault' ? styles.dotFault : styles.dotOffline]} />
      </View>
      <View style={styles.tagRow}>
        <View style={[styles.tag, styles.tagType]}><Text style={styles.tagText}>{deviceTypeLabel(item.type)}</Text></View>
        <View style={[styles.tag, item.status === 'online' ? styles.tagOnline : styles.tagOffline]}>
          <Text style={styles.tagText}>{item.status === 'online' ? '在线' : item.status === 'fault' ? '故障' : '离线'}</Text>
        </View>
      </View>
      <Text style={styles.heartbeat}>最后心跳: {new Date(item.lastHeartbeat).toLocaleString('zh-CN')}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {loading && !refreshing ? (
        <View style={styles.center}><ActivityIndicator size="large" color="#4ECDC4" /></View>
      ) : (
        <FlatList
          data={devices}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor="#4ECDC4" />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={<View style={styles.center}><Text style={styles.emptyText}>暂无设备</Text></View>}
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
  container: { flex: 1, backgroundColor: '#0f0f23' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  card: { backgroundColor: '#1a1a2e', borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  deviceName: { fontSize: 16, fontWeight: '600', color: '#fff' },
  deviceCode: { fontSize: 12, color: '#666', marginTop: 4 },
  statusDot: { width: 12, height: 12, borderRadius: 6, marginTop: 6 },
  dotOnline: { backgroundColor: '#27ae60' },
  dotFault: { backgroundColor: '#e74c3c' },
  dotOffline: { backgroundColor: '#666' },
  tagRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  tag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  tagType: { backgroundColor: 'rgba(78,205,196,0.15)' },
  tagOnline: { backgroundColor: 'rgba(39,174,96,0.2)' },
  tagOffline: { backgroundColor: 'rgba(231,76,60,0.2)' },
  tagText: { fontSize: 12, color: '#ccc' },
  heartbeat: { fontSize: 12, color: '#555', marginTop: 10 },
  emptyText: { color: '#666', fontSize: 15 },
});

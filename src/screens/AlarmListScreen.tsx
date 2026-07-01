import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, FlatList, StyleSheet, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import { alarmApi } from '../services/api';
import { Alarm, AlarmStatus, AlarmLevel } from '../types';

export default function AlarmListScreen() {
  const route = useRoute();
  const params = route.params as { stationId?: number } | undefined;
  const stationId = params?.stationId;
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<AlarmStatus | 'all'>('all');

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      const resp = await alarmApi.getList({
        stationId,
        status: filter === 'all' ? undefined : filter,
        page: 1, pageSize: 50,
      });
      setAlarms(resp.data.items);
    } catch {
      // API not ready
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [stationId, filter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const levelColor = (level: AlarmLevel) => {
    if (level === 'critical') return '#e74c3c';
    if (level === 'warning') return '#f39c12';
    return '#3498db';
  };

  const levelText = (level: AlarmLevel) => {
    if (level === 'critical') return '严重';
    if (level === 'warning') return '警告';
    return '信息';
  };

  const statusText = (status: AlarmStatus) => {
    if (status === 'unhandled') return '未处理';
    if (status === 'processing') return '处理中';
    return '已解决';
  };

  const renderItem = ({ item }: { item: Alarm }) => (
    <View style={styles.card}>
      <View style={[styles.levelBar, { backgroundColor: levelColor(item.level) }]} />
      <View style={styles.cardBody}>
        <View style={styles.cardHeader}>
          <Text style={styles.title}>{item.title}</Text>
          <Text style={[styles.levelTag, { color: levelColor(item.level) }]}>{levelText(item.level)}</Text>
        </View>
        <Text style={styles.desc}>{item.description}</Text>
        <View style={styles.cardFooter}>
          <Text style={styles.statusText}>{statusText(item.status)}</Text>
          <Text style={styles.time}>{new Date(item.createdAt).toLocaleString('zh-CN')}</Text>
        </View>
      </View>
    </View>
  );

  const filters: Array<{ key: AlarmStatus | 'all'; label: string }> = [
    { key: 'all', label: '全部' },
    { key: 'unhandled', label: '未处理' },
    { key: 'processing', label: '处理中' },
    { key: 'resolved', label: '已解决' },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.filterRow}>
        {filters.map((f) => (
          <React.Fragment key={f.key}>
            <View
              style={[styles.filterChip, filter === f.key && styles.filterChipActive]}
            >
              <Text
                style={[styles.filterText, filter === f.key && styles.filterTextActive]}
                onPress={() => setFilter(f.key)}
              >
                {f.label}
              </Text>
            </View>
          </React.Fragment>
        ))}
      </View>

      {loading && !refreshing ? (
        <View style={styles.center}><ActivityIndicator size="large" color="#4ECDC4" /></View>
      ) : (
        <FlatList
          data={alarms}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor="#4ECDC4" />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={<View style={styles.center}><Text style={styles.emptyText}>暂无告警 🎉</Text></View>}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  filterRow: { flexDirection: 'row', padding: 12, gap: 8 },
  filterChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, backgroundColor: '#1a1a2e' },
  filterChipActive: { backgroundColor: '#4ECDC4' },
  filterText: { fontSize: 13, color: '#888' },
  filterTextActive: { color: '#0f0f23', fontWeight: '600' },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: { flexDirection: 'row', backgroundColor: '#1a1a2e', borderRadius: 12, marginBottom: 10, overflow: 'hidden' },
  levelBar: { width: 4 },
  cardBody: { flex: 1, padding: 14 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  title: { fontSize: 15, fontWeight: '600', color: '#fff', flex: 1 },
  levelTag: { fontSize: 12, fontWeight: '600', marginLeft: 8 },
  desc: { fontSize: 13, color: '#999', marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  statusText: { fontSize: 12, color: '#666' },
  time: { fontSize: 12, color: '#555' },
  emptyText: { color: '#666', fontSize: 15 },
});

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useOffline } from '../store/OfflineContext';
import { stationApi } from '../services/api';
import { cache } from '../services/cache';

interface Station {
  id: string;
  name: string;
  address: string;
  status: string;
  deviceCount: number;
  onlineCount: number;
  capacity: string;
}

const statusColors: Record<string, string> = {
  online: '#52c41a',
  offline: '#ff4d4f',
  fault: '#faad14',
  maintenance: '#1890ff',
};

const statusLabels: Record<string, string> = {
  online: '在线',
  offline: '离线',
  fault: '故障',
  maintenance: '维护中',
};

const StationsScreen = () => {
  const navigation = useNavigation<any>();
  const [stations, setStations] = useState<Station[]>([]);
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
        const response = await stationApi.getAll();
        // C端信封 {code:0, data:{items,total,page,page_size}}
        const envelope = response.data?.data || response.data || {};
        const list = Array.isArray(envelope) ? envelope : (envelope?.items || []);
        setStations(list);
        await cache.set('stations', list);
      } else {
        const cached = await getCachedData<Station[]>('stations');
        if (cached) {
          setStations(cached);
        }
      }
    } catch (error: any) {
      console.error('[Stations] Load error:', error.message);
      const cached = await getCachedData<Station[]>('stations');
      if (cached) setStations(cached);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected, getCachedData]);

  useEffect(() => { loadData(); }, [loadData]);

  const renderItem = ({ item }: { item: Station }) => (
    <TouchableOpacity
      style={styles.item}
      onPress={() => navigation.navigate('StationDetail', { stationId: item.id })}
    >
      <View style={styles.itemHeader}>
        <View style={[styles.statusDot, { backgroundColor: statusColors[item.status] || '#999' }]} />
        <Text style={styles.name}>{item.name}</Text>
      </View>
      <Text style={styles.address}>{item.address}</Text>
      <View style={styles.stats}>
        <Text style={styles.stat}>容量: {item.capacity}</Text>
        <Text style={styles.stat}>设备: {item.onlineCount}/{item.deviceCount} 在线</Text>
      </View>
      <View style={[styles.statusBadge, { backgroundColor: statusColors[item.status] + '20' }]}>
        <Text style={[styles.statusText, { color: statusColors[item.status] || '#999' }]}>
          {statusLabels[item.status] || item.status}
        </Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && !refreshing) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1a1a2e" />
        <Text style={styles.loadingText}>加载站点列表...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={stations}
        renderItem={renderItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => loadData(true)} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>暂无站点数据</Text>
          </View>
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, color: '#666', fontSize: 14 },
  list: { padding: 12 },
  item: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
    position: 'relative',
  },
  itemHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  statusDot: { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  name: { fontSize: 16, fontWeight: '600', color: '#333' },
  address: { fontSize: 13, color: '#999', marginBottom: 8 },
  stats: { flexDirection: 'row', justifyContent: 'flex-start', gap: 16 },
  stat: { fontSize: 12, color: '#666' },
  statusBadge: {
    position: 'absolute',
    top: 16,
    right: 16,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  statusText: { fontSize: 11, fontWeight: '500' },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 14, color: '#999' },
});

export default StationsScreen;

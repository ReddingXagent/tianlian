/* eslint-disable react-hooks/set-state-in-effect */
import React, { useEffect, useCallback, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  FlatList, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationStore } from '../store/stationStore';
import { RootStackParamList, Station } from '../types';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function StationListScreen() {
  const navigation = useNavigation<NavProp>();
  const { stations, loading, fetchStations } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');

  const loadData = useCallback(async (searchKey?: string) => {
    setRefreshing(true);
    await fetchStations({ page: 1, pageSize: 100, search: searchKey });
    setRefreshing(false);
  }, [fetchStations]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearch = () => {
    loadData(search);
  };

  const renderItem = ({ item }: { item: Station }) => (
    <TouchableOpacity
      style={styles.card}
      onPress={() => navigation.navigate('StationDetail', { stationId: item.id })}
     accessibilityRole="button">
      <View style={styles.cardHeader}>
        <Text style={styles.stationName}>{item.name}</Text>
        <View style={[styles.badge, item.status === 'online' ? styles.badgeOnline : item.status === 'maintenance' ? styles.badgeMaint : styles.badgeOffline]}>
          <Text style={styles.badgeText}>
            {item.status === 'online' ? '在线' : item.status === 'maintenance' ? '维护中' : '离线'}
          </Text>
        </View>
      </View>
      <Text style={styles.address}>{item.address}</Text>
      <View style={styles.cardFooter}>
        <Text style={styles.meta}>设备 {item.deviceCount} | 在线 {item.onlineDeviceCount}</Text>
        {item.alarmCount > 0 && (
          <Text style={styles.alarmBadge}>告警 {item.alarmCount}</Text>
        )}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          placeholder="搜索站点名称..."
          placeholderTextColor="#666"
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
        />
      </View>

      {loading && !refreshing ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#4ECDC4" />
        </View>
      ) : (
        <FlatList
          data={stations}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadData()} tintColor="#4ECDC4" />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={styles.emptyText}>暂无站点数据</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  searchBar: { padding: 16 },
  searchInput: {
    backgroundColor: '#1a1a2e', borderRadius: 10, paddingHorizontal: 16,
    paddingVertical: 12, fontSize: 15, color: '#fff',
  },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: {
    backgroundColor: '#1a1a2e', borderRadius: 12, padding: 16, marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  stationName: { fontSize: 17, fontWeight: '600', color: '#fff', flex: 1 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeOnline: { backgroundColor: 'rgba(39,174,96,0.25)' },
  badgeMaint: { backgroundColor: 'rgba(243,156,18,0.25)' },
  badgeOffline: { backgroundColor: 'rgba(231,76,60,0.25)' },
  badgeText: { fontSize: 12, color: '#fff', fontWeight: '500' },
  address: { fontSize: 13, color: '#666', marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  meta: { fontSize: 13, color: '#888' },
  alarmBadge: { fontSize: 12, color: '#e74c3c', fontWeight: '500' },
  emptyText: { color: '#666', fontSize: 15 },
});

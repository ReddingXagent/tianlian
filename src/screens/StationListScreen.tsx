import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationStore } from '../store/stationStore';
import { Station, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StationListScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { stations, loading, error, fetchStations } = useStationStore();
  const [search, setSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    }
    await fetchStations(search ? { search } : undefined);
    if (isRefresh) {
      setRefreshing(false);
    }
  }, [fetchStations, search]);

  useEffect(() => {
    loadData();
  }, []);

  const handleSearch = (text: string) => {
    setSearch(text);
    if (searchTimeout) clearTimeout(searchTimeout);
    const timeout = setTimeout(() => {
      fetchStations(text ? { search: text } : undefined);
    }, 500);
    setSearchTimeout(timeout);
  };

  const handleStationPress = (station: Station) => {
    navigation.navigate('StationDetail', { stationId: station.id });
  };

  const renderStationItem = ({ item }: { item: Station }) => (
    <TouchableOpacity
      style={styles.stationCard}
      onPress={() => handleStationPress(item)}
      activeOpacity={0.7}
    >
      <View style={styles.stationHeader}>
        <Text style={styles.stationName} numberOfLines={1}>
          {item.name}
        </Text>
        <StatusBadge status={item.status} />
      </View>
      <Text style={styles.stationCode}>编号: {item.code}</Text>
      <Text style={styles.stationAddress} numberOfLines={1}>
        {item.address}
      </Text>
      <View style={styles.stationFooter}>
        <Text style={styles.stationMeta}>
          📟 {item.deviceCount}台设备 · 🟢 {item.onlineDeviceCount}在线
        </Text>
        {item.alarmCount > 0 && (
          <Text style={styles.alarmCount}>
            🔴 {item.alarmCount}条告警
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );

  if (loading && stations.length === 0) {
    return <LoadingSpinner text="加载站点列表..." />;
  }

  return (
    <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="搜索站点名称或编号..."
          placeholderTextColor="#999"
          value={search}
          onChangeText={handleSearch}
          clearButtonMode="while-editing"
        />
      </View>

      {error && stations.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => loadData()}
        />
      ) : (
        <FlatList
          data={stations}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderStationItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => loadData(true)}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
          ListEmptyComponent={
            <EmptyState
              icon="📡"
              title={search ? '未找到站点' : '暂无站点'}
              message={search ? `未找到包含"${search}"的站点` : '当前没有可管理的站点'}
            />
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  searchInput: {
    backgroundColor: '#f5f6fa',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  stationCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  stationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  stationName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  stationCode: {
    fontSize: 13,
    color: '#999',
    marginBottom: 4,
  },
  stationAddress: {
    fontSize: 13,
    color: '#666',
    marginBottom: 10,
  },
  stationFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  stationMeta: {
    fontSize: 12,
    color: '#999',
  },
  alarmCount: {
    fontSize: 12,
    color: '#c62828',
    fontWeight: '500',
  },
});

export default StationListScreen;
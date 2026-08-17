import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useNavigation, useIsFocused } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationStore } from '../store/stationStore';
import { useActiveCharging } from '../hooks/useChargingPolling';
import { RootStackParamList, Station } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import StationCard from '../components/StationCard';
import MapView from '../components/MapView';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const HomeScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const {
    stations,
    loading,
    refreshing,
    error,
    fetchStations,
    refreshStations,
    searchStations,
  } = useStationStore();
  const [searchText, setSearchText] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  // 检测进行中的充电会话, 有则顶部显示续充入口
  const { activeOrderId } = useActiveCharging();
  useEffect(() => {
    if (activeOrderId) {
      navigation.navigate('Charging', { orderId: activeOrderId });
    }
  }, [activeOrderId, navigation]);

  // 移动端质量基线: Home为主Tab, 切Tab后组件保活不重建,
  // 此前仅mount时拉取一次 → 切走再切回时站点状态(空闲/占用)是陈旧的。
  // useIsFocused回焦静默刷新; 搜索态不刷, 避免冲掉搜索结果。
  const isFocused = useIsFocused();
  const hasSearchRef = useRef(false);
  useEffect(() => {
    hasSearchRef.current = searchText.trim().length > 0;
  }, [searchText]);

  useEffect(() => {
    if (isFocused && !hasSearchRef.current) {
      fetchStations();
    }
  }, [isFocused, fetchStations]);

  const handleSearch = useCallback(async () => {
    const keyword = searchText.trim();
    if (!keyword) {
      fetchStations();
      return;
    }
    setIsSearching(true);
    await searchStations(keyword);
    setIsSearching(false);
  }, [searchText, fetchStations, searchStations]);

  const handleStationPress = useCallback((station: Station) => {
    navigation.navigate('StationDetail', { stationId: station.id });
  }, [navigation]);

  const handleRefresh = useCallback(() => {
    if (searchText.trim()) {
      searchStations(searchText.trim());
    } else {
      refreshStations();
    }
  }, [searchText, searchStations, refreshStations]);

  return (
    <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchContainer}>
        <View style={styles.searchRow}>
          <TextInput
            style={styles.searchInput}
            placeholder="搜索充电站..."
            placeholderTextColor="#999"
            value={searchText}
            onChangeText={setSearchText}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
          <TouchableOpacity accessibilityRole="button"
            style={styles.searchBtn}
            onPress={handleSearch}
            activeOpacity={0.7}
          >
            <Text style={styles.searchBtnText}>
              {isSearching ? '...' : '搜索'}
            </Text>
          </TouchableOpacity>
        </View>
        {searchText.trim() ? (
          <TouchableOpacity accessibilityRole="button"
            style={styles.clearSearchBtn}
            onPress={() => {
              setSearchText('');
              fetchStations();
            }}
          >
            <Text style={styles.clearSearchText}>清除搜索</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      {/* 站点列表 */}
      {loading && stations.length === 0 ? (
        <LoadingSpinner text="加载附近站点..." />
      ) : error && stations.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重试"
          onAction={() => fetchStations()}
        />
      ) : stations.length === 0 ? (
        <EmptyState
          icon="📡"
          title="附近暂无站点"
          message={searchText.trim() ? '未找到匹配的站点，试试其他关键词' : '当前附近没有充电站'}
          actionLabel={searchText.trim() ? undefined : '刷新'}
          onAction={searchText.trim() ? undefined : () => fetchStations()}
        />
      ) : (
        <ScrollView
          style={styles.list}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
        >
          {/* 站点地图(模拟): MapView自组件落地起零挂载(F228同款死代码),
              此前此处仅静态占位文案——挂载后可视化站点分布/可用状态, 点marker直达详情 */}
          <MapView
            stations={stations}
            onStationPress={handleStationPress}
            height={220}
          />

          {stations.map((station) => (
            <StationCard
              key={station.id}
              station={station}
              onPress={handleStationPress}
            />
          ))}
        </ScrollView>
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
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  searchRow: {
    flexDirection: 'row',
    gap: 10,
  },
  searchInput: {
    flex: 1,
    backgroundColor: '#f5f6fa',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
  },
  searchBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '500',
  },
  clearSearchBtn: {
    alignItems: 'center',
    marginTop: 8,
  },
  clearSearchText: {
    fontSize: 13,
    color: '#1a73e8',
  },
  list: {
    flex: 1,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
});

export default HomeScreen;
import React from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  FlatList, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationList } from '../hooks/useStationList';
import { RootStackParamList, Station } from '../types';
import { useTheme } from '../hooks/useTheme';

type NavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

export default function StationListScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NavProp>();
  const { loading, refreshing, search, setSearch, filteredStations, refresh } = useStationList();

  // 站点状态徽标底色(原 rgba 状态底 → 语义色): 在线=successBg / 维护=warningAmberBg / 离线=errorBg
  const badgeBg = (status: Station['status']) =>
    status === 'online' ? colors.successBg
      : status === 'maintenance' ? colors.warningAmberBg
      : colors.errorBg;

  const renderItem = ({ item }: { item: Station }) => (
    <TouchableOpacity
      style={[styles.card, { backgroundColor: colors.cardBg }]}
      onPress={() => navigation.navigate('StationDetail', { stationId: item.id })}
     accessibilityRole="button" testID={`station-card-${item.id}`}>
      <View style={styles.cardHeader}>
        <Text style={[styles.stationName, { color: colors.textPrimary }]}>{item.name}</Text>
        <View style={[styles.badge, { backgroundColor: badgeBg(item.status) }]}>
          <Text style={[styles.badgeText, { color: colors.textPrimary }]}>
            {item.status === 'online' ? '在线' : item.status === 'maintenance' ? '维护中' : '离线'}
          </Text>
        </View>
      </View>
      <Text style={[styles.address, { color: colors.textMuted }]}>{item.address}</Text>
      <View style={styles.cardFooter}>
        <Text style={[styles.meta, { color: colors.textSecondary }]}>设备 {item.deviceCount} | 在线 {item.onlineDeviceCount}</Text>
        {item.alarmCount > 0 && (
          <Text style={[styles.alarmBadge, { color: colors.error }]}>告警 {item.alarmCount}</Text>
        )}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      <View style={styles.searchBar}>
        <TextInput
          style={[styles.searchInput, { backgroundColor: colors.inputBg, color: colors.textPrimary }]}
          placeholder="搜索站点名称..."
          placeholderTextColor={colors.textMuted}
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={refresh}
          testID="station-search-input"
          returnKeyType="search"
        />
      </View>

      {loading && !refreshing ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : (
        <FlatList
          data={filteredStations}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          testID="station-list"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.primary} />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={[styles.emptyText, { color: colors.textMuted }]}>暂无站点数据</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  searchBar: { padding: 16 },
  searchInput: {
    borderRadius: 10, paddingHorizontal: 16,
    paddingVertical: 12, fontSize: 15,
  },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: {
    borderRadius: 12, padding: 16, marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  stationName: { fontSize: 17, fontWeight: '600', flex: 1 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeText: { fontSize: 12, fontWeight: '500' },
  address: { fontSize: 13, marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  meta: { fontSize: 13 },
  alarmBadge: { fontSize: 12, fontWeight: '500' },
  emptyText: { fontSize: 15 },
});

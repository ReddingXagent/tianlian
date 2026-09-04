import React from 'react';
import {
  View, Text, FlatList, StyleSheet, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useAlarms } from '../hooks/useAlarms';
import { Alarm, AlarmLevel, AlarmStatus } from '../types';
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';

// 告警级别 → 语义色键(深色模式: 值改语义键, 运行时经 colors[key] 解析随主题翻转)
const LEVEL_COLOR_KEYS: Record<AlarmLevel, keyof ThemeColors> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
};

export default function AlarmListScreen() {
  const { colors } = useTheme();
  const { alarms, loading, refreshing, filter, setFilter, refresh } = useAlarms();

  const levelColor = (level: AlarmLevel) => colors[LEVEL_COLOR_KEYS[level]];

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
    <View style={[styles.card, { backgroundColor: colors.cardBg }]} testID={`alarm-card-${item.id}`}>
      <View style={[styles.levelBar, { backgroundColor: levelColor(item.level) }]} />
      <View style={styles.cardBody}>
        <View style={styles.cardHeader}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>{item.title}</Text>
          <Text style={[styles.levelTag, { color: levelColor(item.level) }]}>{levelText(item.level)}</Text>
        </View>
        <Text style={[styles.desc, { color: colors.textSecondary }]}>{item.description}</Text>
        <View style={styles.cardFooter}>
          <Text style={[styles.statusText, { color: colors.textMuted }]}>{statusText(item.status)}</Text>
          <Text style={[styles.time, { color: colors.textSecondary }]}>{new Date(item.createdAt).toLocaleString('zh-CN')}</Text>
        </View>
      </View>
    </View>
  );

  const filters: { key: AlarmStatus | 'all'; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'unhandled', label: '未处理' },
    { key: 'processing', label: '处理中' },
    { key: 'resolved', label: '已解决' },
  ];

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      <View style={styles.filterRow}>
        {filters.map((f) => (
          <React.Fragment key={f.key}>
            <View
              style={[styles.filterChip, { backgroundColor: colors.cardBg }, filter === f.key && { backgroundColor: colors.primary }]}
            testID={`alarm-filter-${f.key}`}
            >
              <Text
                style={[styles.filterText, { color: colors.textSecondary }, filter === f.key && { color: colors.onPrimary, fontWeight: '600' as const }]}
                onPress={() => setFilter(f.key)}
              >
                {f.label}
              </Text>
            </View>
          </React.Fragment>
        ))}
      </View>

      {loading && !refreshing ? (
        <View style={styles.center}><ActivityIndicator size="large" color={colors.primary} /></View>
      ) : (
        <FlatList
          data={alarms}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.primary} />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={<View style={styles.center}><Text style={[styles.emptyText, { color: colors.textMuted }]}>暂无告警 🎉</Text></View>}
        testID="alarm-list"
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  filterRow: { flexDirection: 'row', padding: 12, gap: 8 },
  filterChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20 },
  filterText: { fontSize: 13 },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: { flexDirection: 'row', borderRadius: 12, marginBottom: 10, overflow: 'hidden' },
  levelBar: { width: 4 },
  cardBody: { flex: 1, padding: 14 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  title: { fontSize: 15, fontWeight: '600', flex: 1 },
  levelTag: { fontSize: 12, fontWeight: '600', marginLeft: 8 },
  desc: { fontSize: 13, marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  statusText: { fontSize: 12 },
  time: { fontSize: 12 },
  emptyText: { fontSize: 15 },
});

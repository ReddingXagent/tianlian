import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  RefreshControl, ActivityIndicator, Modal, TextInput, Alert
} from 'react-native';
import { useOffline } from '../store/OfflineContext';
import { alarmApi } from '../services/api';
import { cache } from '../services/cache';

interface Alarm {
  id: string;
  title: string;
  level: string;
  status: string;
  deviceName: string;
  stationName: string;
  createdAt: string;
  description?: string;
}

const levelColors: Record<string, string> = {
  critical: '#ff4d4f',
  warning: '#faad14',
  info: '#1890ff',
};

const levelLabels: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
};

const statusLabels: Record<string, string> = {
  active: '待处理',
  acknowledged: '已确认',
  resolved: '已解决',
};

const AlarmsScreen = () => {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [showFilter, setShowFilter] = useState(false);
  const { isConnected, triggerSync, getCachedData } = useOffline();

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      if (isConnected) {
        const response = await alarmApi.getAll();
        const data = response.data?.data || response.data || [];
        const list = Array.isArray(data) ? data : [];
        setAlarms(list);
        await cache.set('alarms', list);
      } else {
        const cached = await getCachedData<Alarm[]>('alarms');
        if (cached) setAlarms(cached);
      }
    } catch (error: any) {
      console.error('[Alarms] Load error:', error.message);
      const cached = await getCachedData<Alarm[]>('alarms');
      if (cached) setAlarms(cached);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected, getCachedData]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleConfirm = async (id: string) => {
    if (!isConnected) {
      Alert.alert('离线模式', '请连接网络后确认告警');
      return;
    }
    try {
      await alarmApi.confirm(id);
      setAlarms(prev => prev.map(a => a.id === id ? { ...a, status: 'acknowledged' } : a));
    } catch (e: any) {
      Alert.alert('操作失败', e.message);
    }
  };

  const handleResolve = async (id: string) => {
    if (!isConnected) {
      Alert.alert('离线模式', '请连接网络后解决告警');
      return;
    }
    try {
      await alarmApi.resolve(id);
      setAlarms(prev => prev.map(a => a.id === id ? { ...a, status: 'resolved' } : a));
    } catch (e: any) {
      Alert.alert('操作失败', e.message);
    }
  };

  const filtered = filter === 'all'
    ? alarms
    : alarms.filter(a => a.level === filter);

  const counts = {
    all: alarms.length,
    critical: alarms.filter(a => a.level === 'critical').length,
    warning: alarms.filter(a => a.level === 'warning').length,
    info: alarms.filter(a => a.level === 'info').length,
  };

  const renderItem = ({ item }: { item: Alarm }) => (
    <View style={styles.item}>
      <View style={styles.itemHeader}>
        <View style={[styles.levelBadge, { backgroundColor: levelColors[item.level] + '20' }]}>
          <Text style={[styles.levelText, { color: levelColors[item.level] }]}>
            {levelLabels[item.level] || item.level}
          </Text>
        </View>
        <Text style={[styles.statusLabel, {
          color: item.status === 'active' ? '#ff4d4f' : item.status === 'acknowledged' ? '#faad14' : '#52c41a'
        }]}>
          {statusLabels[item.status] || item.status}
        </Text>
      </View>

      <Text style={styles.title}>{item.title}</Text>
      {item.description ? <Text style={styles.desc} numberOfLines={2}>{item.description}</Text> : null}

      <View style={styles.meta}>
        <Text style={styles.metaText}>{item.stationName}</Text>
        <Text style={styles.metaText}>{item.deviceName}</Text>
        <Text style={styles.metaText}>{item.createdAt}</Text>
      </View>

      {item.status === 'active' && (
        <View style={styles.actions}>
          <TouchableOpacity style={[styles.btn, styles.btnConfirm]} onPress={() => handleConfirm(item.id)}>
            <Text style={styles.btnText}>确认</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.btn, styles.btnResolve]} onPress={() => handleResolve(item.id)}>
            <Text style={[styles.btnText, { color: '#fff' }]}>解决</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );

  const filterTabs = [
    { key: 'all', label: `全部(${counts.all})` },
    { key: 'critical', label: `严重(${counts.critical})`, color: levelColors.critical },
    { key: 'warning', label: `警告(${counts.warning})`, color: levelColors.warning },
    { key: 'info', label: `提示(${counts.info})`, color: levelColors.info },
  ];

  if (loading && !refreshing) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#1a1a2e" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.filterRow}>
        {filterTabs.map(t => (
          <TouchableOpacity
            key={t.key}
            style={[styles.filterTab, filter === t.key && { backgroundColor: (t.color || '#1a1a2e') + '20', borderColor: t.color || '#1a1a2e' }]}
            onPress={() => setFilter(t.key)}
          >
            <Text style={[styles.filterText, { color: t.color || '#666' }, filter === t.key && { fontWeight: '700' }]}>
              {t.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={filtered}
        renderItem={renderItem}
        keyExtractor={item => item.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadData(true)} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>暂无告警</Text>
          </View>
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  filterRow: { flexDirection: 'row', padding: 12, gap: 8 },
  filterTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: '#ddd' },
  filterText: { fontSize: 12, color: '#666' },
  list: { paddingHorizontal: 12, paddingBottom: 24 },
  item: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 10 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  levelBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  levelText: { fontSize: 11, fontWeight: '600' },
  statusLabel: { fontSize: 12, fontWeight: '500' },
  title: { fontSize: 15, fontWeight: '600', color: '#333', marginBottom: 4 },
  desc: { fontSize: 13, color: '#666', marginBottom: 8 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metaText: { fontSize: 11, color: '#999' },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#f0f0f0' },
  btn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 6 },
  btnConfirm: { backgroundColor: '#e6f7ff', borderWidth: 1, borderColor: '#1890ff' },
  btnResolve: { backgroundColor: '#52c41a' },
  btnText: { fontSize: 13, fontWeight: '500', color: '#1890ff' },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 14, color: '#999' },
});

export default AlarmsScreen;

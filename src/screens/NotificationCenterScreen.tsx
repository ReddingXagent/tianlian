import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ScrollView,
  Alert,
} from 'react-native';
import { notificationApi } from '../services/api';
import { AppNotification, NotificationType } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

type ReadFilter = 'all' | 'unread';
type TypeFilter = NotificationType | 'all';

const NOTIFICATION_ICON: Record<string, string> = {
  alarm: '🔴',
  work_order: '📋',
  system: '⚙️',
  device: '🔌',
  revenue: '💰',
};

const NOTIFICATION_TYPE_LABEL: Record<string, string> = {
  alarm: '告警通知',
  work_order: '工单通知',
  system: '系统通知',
  device: '设备通知',
  revenue: '营收通知',
};

// 类型筛选 chip 配置
const TYPE_FILTER_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'alarm', label: '告警' },
  { value: 'work_order', label: '工单' },
  { value: 'device', label: '设备' },
  { value: 'revenue', label: '营收' },
  { value: 'system', label: '系统' },
];

const NotificationCenterScreen: React.FC = () => {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [readFilter, setReadFilter] = useState<ReadFilter>('all');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');

  // 客户端双重筛选：已读状态 + 通知类型
  const filteredNotifications = useMemo(() => {
    return notifications.filter((n) => {
      if (readFilter === 'unread' && n.isRead) return false;
      if (typeFilter !== 'all' && n.type !== typeFilter) return false;
      return true;
    });
  }, [notifications, readFilter, typeFilter]);

  const fetchData = useCallback(async (isRefresh = false, p = 1) => {
    if (isRefresh) {
      setRefreshing(true);
    } else if (p === 1) {
      setLoading(true);
    }
    setError(null);

    try {
      const [notifRes, unreadRes] = await Promise.all([
        notificationApi.getList({ page: p, pageSize: 20 }),
        notificationApi.getUnreadCount(),
      ]);
      const data = notifRes.data;

      if (p === 1) {
        setNotifications(data.items);
      } else {
        setNotifications((prev) => [...prev, ...data.items]);
      }
      setTotal(data.total);
      setPage(p);
      setUnreadCount(unreadRes.data.count);
    } catch {
      setError('加载通知失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    // F1203: 微任务解耦 effect 直调 async
    Promise.resolve().then(() => fetchData(false, 1));
  }, [fetchData]);

  const handleLoadMore = () => {
    if (notifications.length < total && !loading) {
      fetchData(false, page + 1);
    }
  };

  const handleMarkAsRead = async (id: number) => {
    try {
      await notificationApi.markAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, isRead: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // 静默处理
    }
  };

  const handleMarkAllAsRead = () => {
    Alert.alert('标记已读', '确定要将所有通知标记为已读？', [
      { text: '取消', style: 'cancel' },
      {
        text: '标记已读',
        onPress: async () => {
          try {
            await notificationApi.markAllAsRead();
            setNotifications((prev) =>
              prev.map((n) => ({ ...n, isRead: true }))
            );
            setUnreadCount(0);
          } catch {
            // 静默处理
          }
        },
      },
    ]);
  };

  const formatTime = (dateStr: string): string => {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}小时前`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay < 7) return `${diffDay}天前`;
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const renderNotificationItem = ({ item }: { item: AppNotification }) => (
    <TouchableOpacity
      style={[styles.notifCard, !item.isRead && styles.notifCardUnread]}
      activeOpacity={0.7}
      onPress={() => !item.isRead && handleMarkAsRead(item.id)}
     accessibilityRole="button">
      <View style={styles.notifRow}>
        <Text style={styles.notifIcon}>
          {NOTIFICATION_ICON[item.type] || '📢'}
        </Text>
        <View style={styles.notifContent}>
          <View style={styles.notifHeader}>
            <Text style={[styles.notifTitle, !item.isRead && styles.notifTitleUnread]}>
              {item.title}
            </Text>
            {!item.isRead && <View style={styles.unreadDot} />}
          </View>
          <Text style={styles.notifMessage} numberOfLines={2}>
            {item.message}
          </Text>
          <View style={styles.notifFooter}>
            <Text style={styles.notifType}>
              {NOTIFICATION_TYPE_LABEL[item.type] || item.type}
            </Text>
            <Text style={styles.notifTime}>{formatTime(item.createdAt)}</Text>
          </View>
        </View>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* 操作栏 */}
      {unreadCount > 0 && (
        <View style={styles.actionBar}>
          <Text style={styles.unreadText}>{unreadCount} 条未读</Text>
          <TouchableOpacity onPress={handleMarkAllAsRead} accessibilityRole="button">
            <Text style={styles.markAllText}>全部标记已读</Text>
          </TouchableOpacity>
        </View>
      )}

      {loading && notifications.length === 0 ? (
        <LoadingSpinner text="加载通知列表..." />
      ) : error && notifications.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => fetchData(false, 1)}
        />
      ) : (
        <View style={styles.listWrapper}>
          {/* 筛选栏：已读状态 + 类型 */}
          <View style={styles.filterBar}>
            <View style={styles.readSegment}>
              <TouchableOpacity
                style={[styles.readSegBtn, readFilter === 'all' && styles.readSegBtnActive]}
                onPress={() => setReadFilter('all')}
               accessibilityRole="button">
                <Text style={[styles.readSegText, readFilter === 'all' && styles.readSegTextActive]}>
                  全部
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.readSegBtn, readFilter === 'unread' && styles.readSegBtnActive]}
                onPress={() => setReadFilter('unread')}
               accessibilityRole="button">
                <Text style={[styles.readSegText, readFilter === 'unread' && styles.readSegTextActive]}>
                  未读{unreadCount > 0 ? ` ${unreadCount}` : ''}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.typeFilterRow}
            contentContainerStyle={styles.typeFilterContent}
          >
            {TYPE_FILTER_OPTIONS.map((opt) => {
              const active = typeFilter === opt.value;
              return (
                <TouchableOpacity
                  key={opt.value}
                  style={[styles.typeChip, active && styles.typeChipActive]}
                  onPress={() => setTypeFilter(opt.value)}
                 accessibilityRole="button">
                  <Text style={[styles.typeChipText, active && styles.typeChipTextActive]}>
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <FlatList
            data={filteredNotifications}
            keyExtractor={(item) => String(item.id)}
            renderItem={renderNotificationItem}
            contentContainerStyle={styles.listContent}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={() => fetchData(true, 1)}
                colors={['#1a73e8']}
                tintColor="#1a73e8"
              />
            }
            onEndReached={handleLoadMore}
            onEndReachedThreshold={0.3}
            ListEmptyComponent={
              notifications.length === 0 ? (
                <EmptyState icon="🔔" title="暂无通知" message="当前没有任何通知消息" />
              ) : (
                <EmptyState
                  icon="🔍"
                  title="无匹配通知"
                  message="当前筛选条件下没有通知，试试切换筛选条件"
                />
              )
            }
            ListFooterComponent={
              notifications.length > 0 && notifications.length < total ? (
                <View style={styles.loadingMore}>
                  <LoadingSpinner text="加载更多..." size="small" />
                </View>
              ) : notifications.length >= total && total > 0 ? (
                <Text style={styles.footerText}>已显示全部 {total} 条通知</Text>
              ) : null
            }
          />
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  unreadText: {
    fontSize: 14,
    color: '#1a73e8',
    fontWeight: '500',
  },
  markAllText: {
    fontSize: 14,
    color: '#1a73e8',
  },
  listWrapper: {
    flex: 1,
  },
  filterBar: {
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  readSegment: {
    flexDirection: 'row',
    backgroundColor: '#f0f2f5',
    borderRadius: 8,
    padding: 3,
  },
  readSegBtn: {
    flex: 1,
    paddingVertical: 7,
    borderRadius: 6,
    alignItems: 'center',
  },
  readSegBtnActive: {
    backgroundColor: '#1a73e8',
  },
  readSegText: {
    fontSize: 13,
    color: '#666',
    fontWeight: '500',
  },
  readSegTextActive: {
    color: '#fff',
    fontWeight: '700',
  },
  typeFilterRow: {
    flexGrow: 0,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  typeFilterContent: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  typeChip: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
    backgroundColor: '#f0f2f5',
    marginRight: 4,
  },
  typeChipActive: {
    backgroundColor: '#1a73e8',
  },
  typeChipText: {
    fontSize: 12,
    color: '#666',
  },
  typeChipTextActive: {
    color: '#fff',
    fontWeight: '600',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  notifCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  notifCardUnread: {
    backgroundColor: '#f0f6ff',
    borderLeftWidth: 3,
    borderLeftColor: '#1a73e8',
  },
  notifRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  notifIcon: {
    fontSize: 20,
    marginRight: 12,
    marginTop: 2,
  },
  notifContent: {
    flex: 1,
  },
  notifHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  notifTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: '#333',
    flex: 1,
  },
  notifTitleUnread: {
    fontWeight: '700',
    color: '#1a73e8',
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#1a73e8',
    marginLeft: 6,
  },
  notifMessage: {
    fontSize: 13,
    color: '#666',
    lineHeight: 19,
    marginBottom: 8,
  },
  notifFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  notifType: {
    fontSize: 11,
    color: '#999',
    backgroundColor: '#f0f0f0',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
  notifTime: {
    fontSize: 11,
    color: '#bbb',
  },
  loadingMore: {
    paddingVertical: 16,
  },
  footerText: {
    textAlign: 'center',
    color: '#bbb',
    fontSize: 12,
    paddingVertical: 16,
  },
});

export default NotificationCenterScreen;
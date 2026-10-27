import React from 'react';
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
import { useNotifications } from '../hooks/useNotifications';
import { NotificationType } from '../types';
import { useTheme } from '../hooks/useTheme';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

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

const TYPE_FILTER_OPTIONS: { value: NotificationType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'alarm', label: '告警' },
  { value: 'work_order', label: '工单' },
  { value: 'device', label: '设备' },
  { value: 'revenue', label: '营收' },
  { value: 'system', label: '系统' },
];

const NotificationCenterScreen: React.FC = () => {
  const { colors } = useTheme();
  const {
    notifications,
    filteredNotifications,
    loading,
    refreshing,
    total,
    unreadCount,
    error,
    readFilter,
    typeFilter,
    setReadFilter,
    setTypeFilter,
    fetchData,
    handleLoadMore,
    markAsRead,
    markAllAsRead,
  } = useNotifications();

  const handleMarkAllAsRead = () => {
    Alert.alert('标记已读', '确定要将所有通知标记为已读？', [
      { text: '取消', style: 'cancel' },
      {
        text: '标记已读',
        onPress: () => { void markAllAsRead(); },
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

  const renderNotificationItem = ({ item }: { item: import('../types').AppNotification }) => (
    <TouchableOpacity
      style={[
        styles.notifCard,
        { backgroundColor: colors.cardBg },
        !item.isRead && styles.notifCardUnread,
        !item.isRead && { backgroundColor: colors.infoBg, borderLeftColor: colors.primary },
      ]}
      activeOpacity={0.7}
      onPress={() => !item.isRead && markAsRead(item.id)}
     accessibilityRole="button">
      <View style={styles.notifRow}>
        <Text style={styles.notifIcon}>
          {NOTIFICATION_ICON[item.type] || '📢'}
        </Text>
        <View style={styles.notifContent}>
          <View style={styles.notifHeader}>
            <Text
              style={[
                styles.notifTitle,
                { color: item.isRead ? colors.textPrimary : colors.primary },
                !item.isRead && styles.notifTitleUnread,
              ]}
            >
              {item.title}
            </Text>
            {!item.isRead && <View style={[styles.unreadDot, { backgroundColor: colors.primary }]} />}
          </View>
          <Text style={[styles.notifMessage, { color: colors.textSecondary }]} numberOfLines={2}>
            {item.message}
          </Text>
          <View style={styles.notifFooter}>
            <Text style={[styles.notifType, { color: colors.textMuted, backgroundColor: colors.neutralBg }]}>
              {NOTIFICATION_TYPE_LABEL[item.type] || item.type}
            </Text>
            <Text style={[styles.notifTime, { color: colors.textMuted }]}>
              {formatTime(item.createdAt)}
            </Text>
          </View>
        </View>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      {/* 操作栏 */}
      {unreadCount > 0 && (
        <View style={[styles.actionBar, { backgroundColor: colors.cardBg, borderBottomColor: colors.divider }]}>
          <Text style={[styles.unreadText, { color: colors.primary }]}>{unreadCount} 条未读</Text>
          <TouchableOpacity onPress={handleMarkAllAsRead} accessibilityRole="button"
            testID="notification-mark-all-btn"
          >
            <Text style={[styles.markAllText, { color: colors.primary }]}>全部标记已读</Text>
          </TouchableOpacity>
        </View>
      )}

      {loading && filteredNotifications.length === 0 ? (
        <LoadingSpinner text="加载通知列表..." />
      ) : error && filteredNotifications.length === 0 ? (
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
          <View style={[styles.filterBar, { backgroundColor: colors.cardBg, borderBottomColor: colors.divider }]}>
            <View style={[styles.readSegment, { backgroundColor: colors.neutralBg }]}>
              <TouchableOpacity
                style={[styles.readSegBtn, readFilter === 'all' && { backgroundColor: colors.primary }]}
                onPress={() => setReadFilter('all')}
               testID="notification-filter-all"
               accessibilityRole="button">
                <Text
                  style={[
                    styles.readSegText,
                    { color: colors.textSecondary },
                    readFilter === 'all' && { color: colors.onPrimary, fontWeight: '700' },
                  ]}
                >
                  全部
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.readSegBtn, readFilter === 'unread' && { backgroundColor: colors.primary }]}
                onPress={() => setReadFilter('unread')}
               testID="notification-filter-unread"
               accessibilityRole="button">
                <Text
                  style={[
                    styles.readSegText,
                    { color: colors.textSecondary },
                    readFilter === 'unread' && { color: colors.onPrimary, fontWeight: '700' },
                  ]}
                >
                  未读{unreadCount > 0 ? ` ${unreadCount}` : ''}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={[styles.typeFilterRow, { backgroundColor: colors.cardBg, borderBottomColor: colors.divider }]}
            contentContainerStyle={styles.typeFilterContent}
          >
            {TYPE_FILTER_OPTIONS.map((opt) => {
              const active = typeFilter === opt.value;
              return (
                <TouchableOpacity
                  key={opt.value}
                  style={[styles.typeChip, { backgroundColor: colors.neutralBg }, active && { backgroundColor: colors.primary }]}
                  onPress={() => setTypeFilter(opt.value)}
                 testID={`notification-type-${opt.value}`}
                 accessibilityRole="button">
                  <Text
                    style={[
                      styles.typeChipText,
                      { color: colors.textSecondary },
                      active && { color: colors.onPrimary, fontWeight: '600' },
                    ]}
                  >
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
                colors={[colors.primary]}
                tintColor={colors.primary}
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
              filteredNotifications.length > 0 && filteredNotifications.length < total ? (
                <View style={styles.loadingMore}>
                  <LoadingSpinner text="加载更多..." size="small" />
                </View>
              ) : filteredNotifications.length >= total && total > 0 ? (
                <Text style={[styles.footerText, { color: colors.textMuted }]}>
                  已显示全部 {total} 条通知
                </Text>
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
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  unreadText: {
    fontSize: 14,
    fontWeight: '500',
  },
  markAllText: {
    fontSize: 14,
  },
  listWrapper: {
    flex: 1,
  },
  filterBar: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  readSegment: {
    flexDirection: 'row',
    borderRadius: 8,
    padding: 3,
  },
  readSegBtn: {
    flex: 1,
    paddingVertical: 7,
    borderRadius: 6,
    alignItems: 'center',
  },
  readSegText: {
    fontSize: 13,
    fontWeight: '500',
  },
  typeFilterRow: {
    flexGrow: 0,
    borderBottomWidth: 1,
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
    marginRight: 4,
  },
  typeChipText: {
    fontSize: 12,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  notifCard: {
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
    borderLeftWidth: 3,
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
    flex: 1,
  },
  notifTitleUnread: {
    fontWeight: '700',
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: 6,
  },
  notifMessage: {
    fontSize: 13,
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
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
  notifTime: {
    fontSize: 11,
  },
  loadingMore: {
    paddingVertical: 16,
  },
  footerText: {
    textAlign: 'center',
    fontSize: 12,
    paddingVertical: 16,
  },
});

export default NotificationCenterScreen;

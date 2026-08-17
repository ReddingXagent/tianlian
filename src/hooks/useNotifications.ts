import { useState, useCallback, useEffect, useMemo } from 'react';
import { notificationApi } from '../services/api';
import { AppNotification, NotificationType } from '../types';

type ReadFilter = 'all' | 'unread';
type TypeFilter = NotificationType | 'all';

interface UseNotificationsReturn {
  notifications: AppNotification[];
  filteredNotifications: AppNotification[];
  loading: boolean;
  refreshing: boolean;
  page: number;
  total: number;
  unreadCount: number;
  error: string | null;
  readFilter: ReadFilter;
  typeFilter: TypeFilter;
  setReadFilter: (f: ReadFilter) => void;
  setTypeFilter: (f: TypeFilter) => void;
  fetchData: (isRefresh?: boolean, p?: number) => Promise<void>;
  handleLoadMore: () => void;
  markAsRead: (id: number) => Promise<void>;
  markAllAsRead: () => Promise<boolean>;
}

export function useNotifications(): UseNotificationsReturn {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [readFilter, setReadFilter] = useState<ReadFilter>('all');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');

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
    Promise.resolve().then(() => fetchData(false, 1));
  }, [fetchData]);

  const handleLoadMore = () => {
    if (notifications.length < total && !loading) {
      fetchData(false, page + 1);
    }
  };

  const markAsRead = async (id: number) => {
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

  const markAllAsRead = async (): Promise<boolean> => {
    try {
      await notificationApi.markAllAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })));
      setUnreadCount(0);
      return true;
    } catch {
      return false;
    }
  };

  return {
    notifications,
    filteredNotifications,
    loading,
    refreshing,
    page,
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
  };
}

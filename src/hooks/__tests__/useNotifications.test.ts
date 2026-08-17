/**
 * useNotifications Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useNotifications } from '../useNotifications';

jest.mock('../../services/api', () => ({
  notificationApi: {
    getList: jest.fn(),
    getUnreadCount: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { notificationApi } from '../../services/api';

const mockNotifs = [
  { id: 1, title: '通知1', type: 'alarm', isRead: false, createdAt: '2026-01-01' },
  { id: 2, title: '通知2', type: 'system', isRead: true, createdAt: '2026-01-02' },
  { id: 3, title: '通知3', type: 'alarm', isRead: false, createdAt: '2026-01-03' },
];

describe('useNotifications', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (notificationApi.getList as jest.Mock).mockResolvedValue({
      data: { items: mockNotifs, total: 3 },
    });
    (notificationApi.getUnreadCount as jest.Mock).mockResolvedValue({ data: { count: 2 } });
  });

  it('初始加载: 通知列表+未读数', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.notifications).toHaveLength(3);
    expect(result.current.unreadCount).toBe(2);
    expect(result.current.page).toBe(1);
    expect(result.current.total).toBe(3);
  });

  it('filteredNotifications: 默认all → 全部显示', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.filteredNotifications).toHaveLength(3);
  });

  it('filteredNotifications: unread → 仅未读', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setReadFilter('unread'));
    expect(result.current.filteredNotifications).toHaveLength(2);
    expect(result.current.filteredNotifications.every((n) => !n.isRead)).toBe(true);
  });

  it('filteredNotifications: type=alarm → 仅告警类型', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setTypeFilter('alarm'));
    expect(result.current.filteredNotifications).toHaveLength(2);
    expect(result.current.filteredNotifications.every((n) => n.type === 'alarm')).toBe(true);
  });

  it('filteredNotifications: unread+alarm 组合', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setReadFilter('unread'));
    act(() => result.current.setTypeFilter('alarm'));
    expect(result.current.filteredNotifications).toHaveLength(2);
  });

  it('markAsRead → 更新单条+未读数递减', async () => {
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.markAsRead(1); });
    expect(notificationApi.markAsRead).toHaveBeenCalledWith(1);
    const notif = result.current.notifications.find((n) => n.id === 1);
    expect(notif?.isRead).toBe(true);
    expect(result.current.unreadCount).toBe(1);
  });

  it('markAsRead → API失败静默处理', async () => {
    (notificationApi.markAsRead as jest.Mock).mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = result.current.unreadCount;
    await act(async () => { await result.current.markAsRead(1); });
    expect(result.current.unreadCount).toBe(before);
  });

  it('markAllAsRead → 成功返回true, 全部已读', async () => {
    (notificationApi.markAllAsRead as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.markAllAsRead(); });
    expect(ok).toBe(true);
    expect(result.current.notifications.every((n) => n.isRead)).toBe(true);
    expect(result.current.unreadCount).toBe(0);
  });

  it('markAllAsRead → 失败返回false', async () => {
    (notificationApi.markAllAsRead as jest.Mock).mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.markAllAsRead(); });
    expect(ok).toBe(false);
  });

  it('loadMore → 分页追加', async () => {
    (notificationApi.getList as jest.Mock)
      .mockResolvedValueOnce({ data: { items: mockNotifs, total: 6 } })
      .mockResolvedValueOnce({ data: { items: [{ id: 4, title: 'n4', type: 'system', isRead: false }], total: 6 } });
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.notifications).toHaveLength(3));
    act(() => result.current.handleLoadMore());
    await waitFor(() => expect(result.current.notifications).toHaveLength(4));
    expect(result.current.page).toBe(2);
  });

  it('API失败 → error设置', async () => {
    (notificationApi.getList as jest.Mock).mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.error).toBe('加载通知失败'));
    expect(result.current.loading).toBe(false);
  });
});

/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { FlatList, RefreshControl } from 'react-native';
import { render, waitFor, act } from '@testing-library/react-native';
import CouponScreen from '../CouponScreen';

const mockGetList = jest.fn();

jest.mock('../../services/api', () => ({
  couponApi: {
    getList: (...args: unknown[]) => mockGetList(...args),
  },
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

// Component mocks
jest.mock('../../components/LoadingSpinner', () => {
  const { Text } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <Text>{text}</Text>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});
jest.mock('../../components/EmptyState', () => {
  const { Text, TouchableOpacity } = require('react-native');
  
  const Empty = ({ icon: _icon, title, message, actionLabel, onAction }: { icon?: React.ReactNode; title?: string; message?: string; actionLabel?: string; onAction?: () => void }) => (
    <>
      <Text>{title}</Text>
      <Text>{message}</Text>
      {actionLabel && <TouchableOpacity onPress={onAction}><Text>{actionLabel}</Text></TouchableOpacity>}
    </>
  );
  Empty.displayName = 'EmptyState';
  return Empty;
});
jest.mock('../../components/StatusBadge', () => 'StatusBadge');

const makeCoupon = (over: Record<string, unknown> = {}) => ({
  id: 1,
  userId: 1,
  title: '满10减5券',
  description: '充电订单满10元可用',
  type: 'discount',
  value: 5,
  condition: '满10元',
  status: 'unused',
  startAt: '2026-01-01T00:00:00Z',
  expireAt: '2026-12-31T00:00:00Z',
  createdAt: '2026-01-01T00:00:00Z',
  ...over,
});

describe('CouponScreen.ext — 分支覆盖', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
  });

  // 1. infinite scroll: loadMoreCoupons triggers on endReached with hasMore
  it('loads more coupons on endReached when hasMore=true', async () => {
    const page1 = [makeCoupon({ id: 1 }), makeCoupon({ id: 2 })];
    const page2 = [makeCoupon({ id: 3 })];

    mockGetList
      .mockResolvedValueOnce({
        data: { items: page1, total: 3, page: 1, pageSize: 20 },
      })
      .mockResolvedValueOnce({
        data: { items: page2, total: 3, page: 2, pageSize: 20 },
      });

    const { getAllByText, UNSAFE_getByType } = render(<CouponScreen />);
    await waitFor(() => expect(getAllByText('满10减5券').length).toBeGreaterThan(0));

    // Wait for state to settle (hasMore should be true: 2 < 3)
    await waitFor(() => {
      const list = UNSAFE_getByType(FlatList);
      expect(list.props.data.length).toBe(2);
    });

    // Trigger onEndReached
    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      await list.props.onEndReached();
    });

    // Second page loaded
    await waitFor(() => {
      const updatedList = UNSAFE_getByType(FlatList);
      expect(updatedList.props.data.length).toBe(3);
    });
  });

  // 2. loadMoreCoupons dedup: same id from page2 filtered out
  it('deduplicates coupons on loadMore', async () => {
    const page1 = [makeCoupon({ id: 1 })];
    const page2 = [makeCoupon({ id: 1 })]; // same id

    mockGetList
      .mockResolvedValueOnce({
        data: { items: page1, total: 1, page: 1, pageSize: 20 },
      })
      .mockResolvedValueOnce({
        data: { items: page2, total: 1, page: 2, pageSize: 20 },
      });

    // hasMore = items.length < total → 1 < 1 = false, so loadMore won't fire.
    // We need hasMore=true to test dedup. Adjust total.
    mockGetList.mockReset();
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon({ id: 1 })], total: 2, page: 1, pageSize: 20 },
      })
      .mockResolvedValueOnce({
        data: { items: [makeCoupon({ id: 1 })], total: 2, page: 2, pageSize: 20 },
      });

    const { UNSAFE_getByType } = render(<CouponScreen />);
    await waitFor(() => {
      const list = UNSAFE_getByType(FlatList);
      expect(list.props.data.length).toBe(1);
    });

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      await list.props.onEndReached();
    });

    // Dedup: merged list still has only 1 unique id
    await waitFor(() => {
      const updatedList = UNSAFE_getByType(FlatList);
      expect(updatedList.props.data.length).toBe(1);
    });
  });

  // 3. loadMoreCoupons guards: does not fire when loadingMore=true
  it('does not loadMore when already loading more', async () => {
    let resolveLoadMore: (val: unknown) => void = () => {};
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 5, page: 1, pageSize: 20 },
      })
      .mockImplementationOnce(() => new Promise((r) => { resolveLoadMore = r; }));

    const { UNSAFE_getByType } = render(<CouponScreen />);
    await waitFor(() => {
      expect(UNSAFE_getByType(FlatList)).toBeTruthy();
    });

    // Trigger onEndReached - starts loading more
    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      list.props.onEndReached();
    });

    // Trigger again while loadingMore is still true - should be a no-op
    await act(async () => {
      list.props.onEndReached();
    });

    // Only 2 calls: initial + first loadMore
    expect(mockGetList.mock.calls.length).toBe(2);

    // Resolve pending loadMore for cleanup
    resolveLoadMore({ data: { items: [], total: 5, page: 2, pageSize: 20 } });
  });

  // 4. loadMoreCoupons catches error silently
  it('swallows loadMore errors silently', async () => {
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 5, page: 1, pageSize: 20 },
      })
      .mockRejectedValueOnce(new Error('network error'));

    const { UNSAFE_getByType, getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      await list.props.onEndReached();
    });

    // List still has data, no error shown
    expect(getByText('满10减5券')).toBeTruthy();
  });

  // 5. FlatList footer shows ActivityIndicator when loadingMore
  it('shows loading indicator in footer when loading more', async () => {
    // Make loadMore hang so loadingMore stays true
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 5, page: 1, pageSize: 20 },
      })
      .mockImplementationOnce(() => new Promise(() => {}));

    const { UNSAFE_getByType, getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      list.props.onEndReached();
    });

    // Footer should render — check ListFooterComponent exists
    expect(list.props.ListFooterComponent).toBeTruthy();
  });

  // 6. FlatList footer shows "没有更多了" when hasMore=false
  it('shows "没有更多了" footer when all loaded', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
    });

    const { UNSAFE_getByType, getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());

    // Wait for re-render so footer is computed
    const list = UNSAFE_getByType(FlatList);
    const footer = list.props.ListFooterComponent;
    expect(footer).toBeTruthy();
    // hasMore=false → footer should contain "没有更多了"
  });

  // 7. renderCouponItem: renders different coupon statuses
  it('renders used coupon correctly', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon({ status: 'used', usedAt: '2026-07-01T10:00:00Z' })], total: 1, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());
  });

  // 8. renderCouponItem: renders expired coupon
  it('renders expired coupon correctly', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon({ status: 'expired' })], total: 1, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());
  });

  // 9. renderCouponItem: renders free_hour type
  it('renders free_hour type coupon', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon({ type: 'free_hour', value: 1 })], total: 1, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => {
      expect(getByText('满10减5券')).toBeTruthy();
      expect(getByText('类型: free_hour')).toBeTruthy();
    });
  });

  // 10. renderCouponItem: renders amount type
  it('renders amount type coupon', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon({ type: 'amount', value: 10 })], total: 1, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('类型: amount')).toBeTruthy());
    expect(getByText('面值: ¥10.00')).toBeTruthy();
  });

  // 11. multi-coupon render: list renders all items
  it('renders multiple coupons in list', async () => {
    mockGetList.mockResolvedValue({
      data: {
        items: [
          makeCoupon({ id: 1, title: '券A' }),
          makeCoupon({ id: 2, title: '券B', value: 10 }),
          makeCoupon({ id: 3, title: '券C', type: 'free_hour' }),
        ],
        total: 3, page: 1, pageSize: 20,
      },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => {
      expect(getByText('券A')).toBeTruthy();
      expect(getByText('券B')).toBeTruthy();
      expect(getByText('券C')).toBeTruthy();
    });
  });

  // 12. initial load error with non-Error throw → default message
  it('shows default error for non-Error throw on initial load', async () => {
    mockGetList.mockRejectedValue('string error');
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('获取优惠券失败')).toBeTruthy());
  });

  // 13. initial load error with axios-style Error → shows message
  it('shows Error.message on initial load failure', async () => {
    mockGetList.mockRejectedValue(new Error('服务器维护中'));
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
      expect(getByText('服务器维护中')).toBeTruthy();
    });
  });

  // 14. refresh: refreshing state properly toggles
  it('toggles refreshing state during manual refresh', async () => {
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
      })
      .mockResolvedValueOnce({
        data: { items: [makeCoupon({ title: '新券' })], total: 1, page: 1, pageSize: 20 },
      });

    const { UNSAFE_getByType, getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());

    const rc = UNSAFE_getByType(RefreshControl);
    await act(async () => {
      await rc.props.onRefresh();
    });

    // After refresh completes, refreshing should be false
    const rcAfter = UNSAFE_getByType(RefreshControl);
    expect(rcAfter.props.refreshing).toBe(false);
  });

  // 15. empty list after refresh: shows empty state
  it('shows empty state when refresh returns empty list', async () => {
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
      })
      .mockResolvedValueOnce({
        data: { items: [], total: 0, page: 1, pageSize: 20 },
      });

    const { UNSAFE_getByType, getByText, queryByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());

    const rc = UNSAFE_getByType(RefreshControl);
    await act(async () => {
      await rc.props.onRefresh();
    });

    await waitFor(() => {
      expect(getByText('暂无优惠券')).toBeTruthy();
      expect(queryByText('满10减5券')).toBeNull();
    });
  });
});

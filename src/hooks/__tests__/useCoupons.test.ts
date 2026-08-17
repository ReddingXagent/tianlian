import { renderHook, act, waitFor } from '@testing-library/react-native';
import { couponApi } from '../../services/api';
import { useCoupons } from '../useCoupons';
import { Coupon } from '../../types';

jest.mock('../../services/api', () => ({
  couponApi: {
    getList: jest.fn(),
  },
}));

const mockCoupon = (id: number): Coupon => ({
  id,
  code: `C${id}`,
  name: `优惠券${id}`,
  type: 'discount',
  status: 'active',
  value: 10,
  minAmount: 50,
  expireDate: '2026-12-31',
} as never);

const mockResponse = (items: Coupon[], total: number, page: number) => ({
  data: { items, total, page },
});

describe('useCoupons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should load coupons on mount', async () => {
    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(1), mockCoupon(2)], 2, 1)
    );

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.coupons).toHaveLength(2);
    expect(result.current.error).toBeNull();
    expect(result.current.hasMore).toBe(false);
  });

  it('should set error on load failure', async () => {
    (couponApi.getList as jest.Mock).mockRejectedValue(new Error('网络错误'));

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('网络错误');
    expect(result.current.coupons).toEqual([]);
  });

  it('should set error with default message on non-Error throw', async () => {
    (couponApi.getList as jest.Mock).mockRejectedValue('string error');

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取优惠券失败');
  });

  it('should set hasMore when items < total', async () => {
    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(1)], 5, 1)
    );

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.hasMore).toBe(true);
  });

  it('should load more coupons and dedupe', async () => {
    const page1 = [mockCoupon(1), mockCoupon(2)];
    const page2 = [mockCoupon(2), mockCoupon(3)]; // dup id=2

    (couponApi.getList as jest.Mock)
      .mockResolvedValueOnce(mockResponse(page1, 3, 1))
      .mockResolvedValueOnce(mockResponse(page2, 3, 2));

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.loadMoreCoupons();
    });

    expect(result.current.coupons).toHaveLength(3); // 1,2,3 deduped
    expect(result.current.hasMore).toBe(false); // 3 === 3
  });

  it('should not load more when hasMore is false', async () => {
    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(1)], 1, 1)
    );

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.loadMoreCoupons();
    });

    expect(couponApi.getList).toHaveBeenCalledTimes(1);
  });

  it('should handle refresh', async () => {
    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(1)], 1, 1)
    );

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(2)], 1, 1)
    );

    await act(async () => {
      await result.current.handleRefresh();
    });

    expect(result.current.refreshing).toBe(false);
    expect(result.current.coupons[0].id).toBe(2);
  });

  it('should silently handle loadMore failure', async () => {
    (couponApi.getList as jest.Mock).mockResolvedValue(
      mockResponse([mockCoupon(1)], 5, 1)
    );

    const { result } = renderHook(() => useCoupons());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    (couponApi.getList as jest.Mock).mockRejectedValue(new Error('fail'));

    await act(async () => {
      await result.current.loadMoreCoupons();
    });

    expect(result.current.loadingMore).toBe(false);
    expect(result.current.coupons).toHaveLength(1); // unchanged
  });
});

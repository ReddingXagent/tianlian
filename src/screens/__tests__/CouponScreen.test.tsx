import React from 'react';
import { RefreshControl } from 'react-native';
import { render, waitFor, fireEvent, act } from '@testing-library/react-native';
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

describe('CouponScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
  });

  it('加载成功后渲染优惠券列表', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());
    expect(getByText('充电订单满10元可用')).toBeTruthy();
    expect(getByText('面值: ¥5.00')).toBeTruthy();
  });

  it('空列表显示空态', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 20 },
    });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('暂无优惠券')).toBeTruthy());
  });

  it('加载失败显示错误态并可重试', async () => {
    mockGetList
      .mockRejectedValueOnce(new Error('网络异常'))
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
      });
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('加载失败')).toBeTruthy());
    expect(getByText('网络异常')).toBeTruthy();
    fireEvent.press(getByText('重试'));
    await waitFor(() => expect(getByText('满10减5券')).toBeTruthy());
  });

  it('非Error异常回退默认错误文案', async () => {
    mockGetList.mockRejectedValue('boom');
    const { getByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByText('获取优惠券失败')).toBeTruthy());
  });

  it('下拉刷新重拉时列表保持可见(不切整屏spinner)', async () => {
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
      })
      .mockImplementationOnce(() => new Promise(() => {})); // 第二刷挂起
    const utils = render(<CouponScreen />);
    await waitFor(() => expect(utils.getByText('满10减5券')).toBeTruthy());
    const rc = utils.UNSAFE_getByType(RefreshControl);
    await act(async () => {
      void rc.props.onRefresh();
    });
    // 刷新中: 列表仍在, 不切整屏spinner
    expect(utils.getByText('满10减5券')).toBeTruthy();
    expect(utils.queryByText('加载优惠券...')).toBeNull();
  });

  it('刷新失败时保留已有列表(不切错误页)', async () => {
    mockGetList
      .mockResolvedValueOnce({
        data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
      })
      .mockRejectedValueOnce(new Error('网络异常'));
    const utils = render(<CouponScreen />);
    await waitFor(() => expect(utils.getByText('满10减5券')).toBeTruthy());
    const rc = utils.UNSAFE_getByType(RefreshControl);
    await act(async () => {
      await rc.props.onRefresh();
    });
    // 刷新失败: 列表仍在, 不切错误页, refreshing复位
    expect(utils.getByText('满10减5券')).toBeTruthy();
    expect(utils.queryByText('加载失败')).toBeNull();
    const rcAfter = utils.UNSAFE_getByType(RefreshControl);
    expect(rcAfter.props.refreshing).toBe(false);
  });

  // --- F215: 回焦静默刷新对齐(F170/F209模式) ---
  it('回焦时重新拉取优惠券(用券后券状态可能已变化)', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
    });
    const utils = render(<CouponScreen />);
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(1));

    mockFocused = false;
    utils.rerender(<CouponScreen />);
    expect(mockGetList).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(<CouponScreen />);
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
  });

  // ── testID guard (F3688同款: 防testID误写JSX children假绿) ──
  it('renders testID anchors as props (not visible text)', async () => {
    mockGetList.mockResolvedValue({
      data: { items: [makeCoupon()], total: 1, page: 1, pageSize: 20 },
    });
    const { getByTestId, queryByText } = render(<CouponScreen />);
    await waitFor(() => expect(getByTestId('coupon-list')).toBeTruthy());
    expect(queryByText('testID=coupon-list')).toBeNull();
  });
});

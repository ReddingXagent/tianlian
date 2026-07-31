import React from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react-native';
import CouponScreen from '../CouponScreen';

const mockGetList = jest.fn();

jest.mock('../../services/api', () => ({
  couponApi: {
    getList: (...args: unknown[]) => mockGetList(...args),
  },
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
});

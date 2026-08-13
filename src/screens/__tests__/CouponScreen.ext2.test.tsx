import React from 'react';
import { render, act } from '@testing-library/react-native';
import CouponScreen from '../CouponScreen';

const mockGetList = jest.fn();

jest.mock('../../services/api', () => ({
  couponApi: {
    getList: (...args: unknown[]) => mockGetList(...args),
  },
}));

jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => true,
}));

describe('CouponScreen.ext2 — 卸载竞态分支', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetList.mockReturnValue(new Promise(() => {}));
  });

  it('cancels pending focus-load when unmounted before microtask flush', async () => {
    const view = render(<CouponScreen />);
    view.unmount();
    await act(async () => {});
    // 卸载先于微任务冲刷 → cancelled=true, 不应发起列表请求
    expect(mockGetList).not.toHaveBeenCalled();
  });
});

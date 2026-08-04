import React from 'react';
import { RefreshControl } from 'react-native';
import { render, waitFor, act, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import WalletScreen from '../WalletScreen';

// --- mocks ---
const mockGetRecords = jest.fn();
const mockRecharge = jest.fn();
const mockGetProfile = jest.fn();

jest.mock('../../services/api', () => ({
  walletApi: {
    getRecords: (...args: unknown[]) => mockGetRecords(...args),
    recharge: (...args: unknown[]) => mockRecharge(...args),
  },
  authApi: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
  },
}));

const mockUser = {
  id: 1,
  phone: '13800001111',
  nickname: '测试用户',
  balance: 150.0,
};

const mockSetUser = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: mockUser,
    setUser: mockSetUser,
  }),
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

describe('WalletScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockGetProfile.mockResolvedValue({ data: { id: 1, phone: '138', nickname: 'u', balance: 200 } });
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <WalletScreen />
      </SafeAreaProvider>
    );

  it('renders account balance label', () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    const { getByText } = renderScreen();
    expect(getByText('账户余额')).toBeTruthy();
  });

  it('renders balance amount ¥150.00', () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    const { getByText } = renderScreen();
    expect(getByText('¥150.00')).toBeTruthy();
  });

  it('renders 充值 button', () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    const { getByText } = renderScreen();
    expect(getByText('充值')).toBeTruthy();
  });

  it('renders 交易记录 section title', () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    const { getByText } = renderScreen();
    expect(getByText('交易记录')).toBeTruthy();
  });

  it('calls getRecords on mount', () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    renderScreen();
    expect(mockGetRecords).toHaveBeenCalledTimes(1);
  });

  it('renders records after load', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [
          {
            id: 2,
            type: 'consume',
            amount: 12.5,
            balance: 100,
            description: '充电消费',
            createdAt: '2025-01-02T14:00:00Z',
          },
        ],
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('充电消费')).toBeTruthy());
  });

  it('refetches records + profile when screen regains focus (回焦刷新余额/流水)', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [] } });
    const utils = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><WalletScreen /></SafeAreaProvider>);
    expect(mockGetRecords).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(<SafeAreaProvider><WalletScreen /></SafeAreaProvider>);
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(mockSetUser).toHaveBeenCalledWith({ id: 1, phone: '138', nickname: 'u', balance: 200 })
    );
  });

  // --- F209: 下拉刷新对齐(订单/优惠券/首页/站点详情均有, 钱包此前缺失) ---
  const recordFixture = {
    id: 2,
    type: 'consume',
    amount: 12.5,
    balance: 100,
    description: '充电消费',
    createdAt: '2025-01-02T14:00:00Z',
  };

  it('下拉刷新重拉流水+余额(refreshControl onRefresh 双拉并复位 refreshing)', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [recordFixture] } });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('充电消费')).toBeTruthy());
    expect(mockGetRecords).toHaveBeenCalledTimes(1);
    expect(mockGetProfile).toHaveBeenCalledTimes(1);

    const rc = utils.UNSAFE_getByType(RefreshControl);
    await act(async () => {
      await rc.props.onRefresh();
    });

    expect(mockGetRecords).toHaveBeenCalledTimes(2);
    expect(mockGetProfile).toHaveBeenCalledTimes(2);
    // refreshing 状态复位, spinner 收起
    const rcAfter = utils.UNSAFE_getByType(RefreshControl);
    expect(rcAfter.props.refreshing).toBe(false);
  });

  it('下拉刷新期间列表保持可见(不整屏切spinner)', async () => {
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: [recordFixture] } });
      // 第二刷挂起: 模拟刷新中, 验证列表不被LoadingSpinner替换
      return new Promise(() => {});
    });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('充电消费')).toBeTruthy());

    const rc = utils.UNSAFE_getByType(RefreshControl);
    act(() => {
      void rc.props.onRefresh();
    });

    // 刷新中: refreshing=true 且已有记录仍可见(资金页不能闪白屏)
    const rcRefreshing = utils.UNSAFE_getByType(RefreshControl);
    expect(rcRefreshing.props.refreshing).toBe(true);
    expect(utils.getByText('充电消费')).toBeTruthy();
  });

  // --- F221: 首屏拉取失败不能伪装成"暂无记录" ---
  it('首屏拉取失败显示加载失败+重试(而非"暂无记录")', async () => {
    mockGetRecords.mockRejectedValue(new Error('网络异常'));
    const { getByText, queryByText } = renderScreen();
    await waitFor(() => expect(getByText('加载失败')).toBeTruthy());
    expect(getByText('网络异常')).toBeTruthy();
    expect(getByText('重试')).toBeTruthy();
    expect(queryByText('暂无记录')).toBeNull();
  });

  it('点击重试重新拉取并恢复流水列表', async () => {
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.reject(new Error('网络异常'));
      return Promise.resolve({ data: { items: [recordFixture], page: 1, total: 1 } });
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('加载失败')).toBeTruthy());

    fireEvent.press(getByText('重试'));
    await waitFor(() => expect(getByText('充电消费')).toBeTruthy());
    expect(mockGetRecords).toHaveBeenCalledTimes(2);
  });

  it('有流水时回焦重拉失败保留列表可见(不整屏切错误页)', async () => {
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: [recordFixture], page: 1, total: 1 } });
      return Promise.reject(new Error('回焦失败'));
    });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('充电消费')).toBeTruthy());

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><WalletScreen /></SafeAreaProvider>);
    mockFocused = true;
    utils.rerender(<SafeAreaProvider><WalletScreen /></SafeAreaProvider>);

    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(2));
    expect(utils.getByText('充电消费')).toBeTruthy();
    expect(utils.queryByText('加载失败')).toBeNull();
  });
});

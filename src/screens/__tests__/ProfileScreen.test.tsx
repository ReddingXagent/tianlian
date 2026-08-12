import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ProfileScreen from '../ProfileScreen';

// --- mocks ---
const mockGetUserStats = jest.fn();
const mockGetProfile = jest.fn();

jest.mock('../../services/api', () => ({
  statsApi: {
    getUserStats: (...args: unknown[]) => mockGetUserStats(...args),
  },
  authApi: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
  },
}));

const mockUser = {
  id: 1,
  phone: '13800001111',
  nickname: '测试用户',
  balance: 88.5,
};

const mockLogout = jest.fn().mockResolvedValue(undefined);
const mockSetUser = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: mockUser,
    logout: mockLogout,
    setUser: mockSetUser,
  }),
}));

let mockFocused = true;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: jest.fn(),
  }),
  useIsFocused: () => mockFocused,
}));

describe('ProfileScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <ProfileScreen />
      </SafeAreaProvider>
    );

  it('renders user nickname', () => {
    const { getByText } = renderScreen();
    expect(getByText('测试用户')).toBeTruthy();
  });

  it('renders user phone', () => {
    const { getByText } = renderScreen();
    expect(getByText('13800001111')).toBeTruthy();
  });

  it('renders balance', () => {
    const { getByText } = renderScreen();
    expect(getByText('¥88.50')).toBeTruthy();
  });

  it('renders version text', () => {
    const { getByText } = renderScreen();
    expect(getByText('天链充电 v1.0.0')).toBeTruthy();
  });

  it('renders menu items (车辆管理, 我的钱包, 我的优惠券)', () => {
    const { getByText } = renderScreen();
    expect(getByText('车辆管理')).toBeTruthy();
    expect(getByText('我的钱包')).toBeTruthy();
    expect(getByText('我的优惠券')).toBeTruthy();
  });

  it('renders 退出登录 button', () => {
    const { getByText } = renderScreen();
    expect(getByText('退出登录')).toBeTruthy();
  });

  it('calls getUserStats on mount', async () => {
    mockGetUserStats.mockResolvedValue({ data: { totalOrders: 12, totalEnergy: 340.5, couponCount: 3 } });
    renderScreen();
    await waitFor(() => expect(mockGetUserStats).toHaveBeenCalledTimes(1));
  });

  it('renders stats after load', async () => {
    mockGetUserStats.mockResolvedValue({ data: { totalOrders: 12, totalEnergy: 340.5, couponCount: 3 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('12')).toBeTruthy());
  });

  it('renders 消息通知 and 关于我们', () => {
    const { getByText } = renderScreen();
    expect(getByText('消息通知')).toBeTruthy();
    expect(getByText('关于我们')).toBeTruthy();
  });

  it('refetches stats when tab regains focus (回焦刷新)', async () => {
    mockGetUserStats.mockResolvedValue({ data: {} });
    const utils = renderScreen();
    await waitFor(() => expect(mockGetUserStats).toHaveBeenCalledTimes(1));

    mockFocused = false;
    utils.rerender(
      <SafeAreaProvider>
        <ProfileScreen />
      </SafeAreaProvider>
    );
    expect(mockGetUserStats).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(
      <SafeAreaProvider>
        <ProfileScreen />
      </SafeAreaProvider>
    );
    await waitFor(() => expect(mockGetUserStats).toHaveBeenCalledTimes(2));
  });

  it('silently refreshes profile (余额) on focus', async () => {
    mockGetUserStats.mockResolvedValue({ data: {} });
    mockGetProfile.mockResolvedValue({ data: { ...mockUser, balance: 100 } });
    renderScreen();
    await waitFor(() => expect(mockGetProfile).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(mockSetUser).toHaveBeenCalledWith({ ...mockUser, balance: 100 })
    );
  });

  it('profile refresh failure does not break stats', async () => {
    mockGetUserStats.mockResolvedValue({ data: { totalOrders: 5, totalEnergy: 0, couponCount: 0 } });
    mockGetProfile.mockRejectedValue(new Error('network'));
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('5')).toBeTruthy());
  });
});

import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ProfileScreen from '../ProfileScreen';

// --- mocks ---
const mockGetUserStats = jest.fn();

jest.mock('../../services/api', () => ({
  statsApi: {
    getUserStats: (...args: unknown[]) => mockGetUserStats(...args),
  },
}));

const mockUser = {
  id: 1,
  phone: '13800001111',
  nickname: '测试用户',
  balance: 88.5,
};

const mockLogout = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: mockUser,
    logout: mockLogout,
  }),
}));

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: jest.fn(),
  }),
}));

describe('ProfileScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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

  it('calls getUserStats on mount', () => {
    mockGetUserStats.mockResolvedValue({ data: { totalOrders: 12, totalEnergy: 340.5, couponCount: 3 } });
    renderScreen();
    expect(mockGetUserStats).toHaveBeenCalledTimes(1);
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
});

import React from 'react';
import { render, act } from '@testing-library/react-native';
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

// user 为 null 的边界态: 覆盖 user?.balance 空值链与 || 0 兜底分支
jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: null,
    setUser: jest.fn(),
  }),
}));

// useIsFocused 走 jest.setup 全局 mock(恒 true)

describe('WalletScreen.ext4 — user为null边界 + 卸载竞态', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetRecords.mockReturnValue(new Promise(() => {}));
    mockGetProfile.mockReturnValue(new Promise(() => {}));
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <WalletScreen />
      </SafeAreaProvider>
    );

  it('renders balance fallback ¥0.00 when user is null', () => {
    const { getByText } = renderScreen();
    expect(getByText('账户余额')).toBeTruthy();
    expect(getByText('¥0.00')).toBeTruthy();
  });

  it('cancels pending focus-refresh when unmounted before microtask flush', async () => {
    const view = renderScreen();
    view.unmount();
    await act(async () => {});
    // 卸载先于微任务冲刷 → cancelled=true, 不应再发起任何请求
    expect(mockGetRecords).not.toHaveBeenCalled();
    expect(mockGetProfile).not.toHaveBeenCalled();
    expect(mockRecharge).not.toHaveBeenCalled();
  });
});

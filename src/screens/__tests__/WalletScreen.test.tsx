import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import WalletScreen from '../WalletScreen';

// --- mocks ---
const mockGetRecords = jest.fn();
const mockRecharge = jest.fn();

jest.mock('../../services/api', () => ({
  walletApi: {
    getRecords: (...args: unknown[]) => mockGetRecords(...args),
    recharge: (...args: unknown[]) => mockRecharge(...args),
  },
  authApi: {
    getProfile: jest.fn().mockResolvedValue({ data: { id: 1, phone: '138', nickname: 'u', balance: 200 } }),
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
});

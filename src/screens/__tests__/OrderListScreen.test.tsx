import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import OrderListScreen from '../OrderListScreen';

// --- mocks ---
const mockOrders = [
  {
    id: 1,
    orderNo: 'ORD-001',
    userId: 1,
    stationId: 1,
    stationName: '测试充电站',
    chargerId: 1,
    chargerName: '1号桩',
    status: 'charging',
    startTime: '2025-01-01T10:00:00Z',
    amount: 0,
    paymentStatus: 'pending',
    energy: 0,
    duration: 0,
  },
  {
    id: 2,
    orderNo: 'ORD-002',
    userId: 1,
    stationId: 2,
    stationName: '另一个站',
    chargerId: 3,
    chargerName: '3号桩',
    status: 'completed',
    startTime: '2025-01-01T08:00:00Z',
    endTime: '2025-01-01T09:00:00Z',
    amount: 25.5,
    paymentStatus: 'paid',
    energy: 20.5,
    duration: 3600,
  },
];

const mockFetchOrders = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/orderStore', () => ({
  useOrderStore: () => ({
    orders: mockOrders,
    loading: false,
    fetchOrders: mockFetchOrders,
  }),
}));

const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');
jest.mock('../../components/LoadingSpinner', () => 'LoadingSpinner');
jest.mock('../../components/EmptyState', () => 'EmptyState');

describe('OrderListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <OrderListScreen />
      </SafeAreaProvider>
    );

  it('renders filter labels', () => {
    const { getByText } = renderScreen();
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('充电中')).toBeTruthy();
    expect(getByText('已完成')).toBeTruthy();
    expect(getByText('未支付')).toBeTruthy();
  });

  it('renders order numbers with prefix', () => {
    const { getByText } = renderScreen();
    expect(getByText('订单号: ORD-001')).toBeTruthy();
    expect(getByText('订单号: ORD-002')).toBeTruthy();
  });

  it('renders station names in orders', () => {
    const { getByText } = renderScreen();
    expect(getByText('测试充电站')).toBeTruthy();
    expect(getByText('另一个站')).toBeTruthy();
  });

  it('calls fetchOrders on mount', () => {
    renderScreen();
    expect(mockFetchOrders).toHaveBeenCalled();
  });
});

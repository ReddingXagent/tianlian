import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import OrderDetailScreen from '../OrderDetailScreen';

const mockNavigate = jest.fn();
let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: { orderId: 99 } }),
  useIsFocused: () => mockFocused,
}));

// Store factory — return same ref so require() matches component's reference
const mockFetchOrderDetail = jest.fn();
const mockCancelOrder = jest.fn();
const mockOrder = {
  id: 99, orderNo: 'ORD-2026-001', userId: 1, stationId: 1,
  stationName: '测试充电站', chargerId: 1, chargerName: '1号桩',
  status: 'completed', startTime: '2026-08-03T10:00:00Z',
  endTime: '2026-08-03T11:00:00Z', duration: 60, energy: 15.5,
  power: 30, voltage: 400, current: 75, amount: 18.6,
  couponDiscount: 2.0, paymentStatus: 'unpaid',
  createdAt: '2026-08-03T10:00:00Z', updatedAt: '2026-08-03T11:00:00Z',
};

jest.mock('../../store/orderStore', () => ({
  useOrderStore: () => ({
    selectedOrder: mockOrder, loading: false, error: null,
    fetchOrderDetail: mockFetchOrderDetail, cancelOrder: mockCancelOrder,
  }),
}));

jest.mock('../../components/LoadingSpinner', () => {
  const { Text } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <Text>{text}</Text>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});
jest.mock('../../components/StatusBadge', () => 'StatusBadge');
jest.mock('../../components/EmptyState', () => {
  const { Text } = require('react-native');
  const Empty = ({ title, message }: any) => (<><Text>{title}</Text><Text>{message}</Text></>);
  Empty.displayName = 'EmptyState';
  return Empty;
});

describe('OrderDetailScreen', () => {
  beforeEach(() => { jest.clearAllMocks(); mockFocused = true; });

  const renderScreen = () =>
    render(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);

  it('calls fetchOrderDetail on mount', () => {
    renderScreen();
    expect(mockFetchOrderDetail).toHaveBeenCalledWith(99);
  });

  it('renders order number', async () => {
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText(/ORD-2026-001/)).toBeTruthy());
  });

  it('renders station and charger info', async () => {
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('测试充电站')).toBeTruthy();
      expect(getByText('1号桩')).toBeTruthy();
    });
  });

  it('renders energy and duration', async () => {
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('15.50 kWh')).toBeTruthy();
      expect(getByText('60 分钟')).toBeTruthy();
    });
  });

  it('renders fee breakdown', async () => {
    const { getAllByText, getByText } = renderScreen();
    await waitFor(() => {
      // ¥18.60 appears in both status card and fee detail — use getAllByText
      expect(getAllByText('¥18.60').length).toBeGreaterThanOrEqual(1);
      expect(getByText('-¥2.00')).toBeTruthy();
      expect(getByText('¥16.60')).toBeTruthy();
    });
  });

  it('renders pay button for unpaid order', async () => {
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('去支付')).toBeTruthy());
  });

  it('navigates to payment on pay button press', async () => {
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('去支付')).toBeTruthy());
    fireEvent.press(getByText('去支付'));
    expect(mockNavigate).toHaveBeenCalledWith('Payment', { orderId: 99, amount: 18.6 });
  });

  it('refetches order detail when screen regains focus (回焦刷新)', () => {
    const utils = renderScreen();
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(1);

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);
    expect(mockFetchOrderDetail).toHaveBeenCalledTimes(2);
  });
});
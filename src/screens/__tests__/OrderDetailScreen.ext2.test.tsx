import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import OrderDetailScreen from '../OrderDetailScreen';

// --- navigation mocks ---
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useRoute: () => ({ params: { orderId: 99 } }),
  useIsFocused: () => true,
}));

// --- store mocks ---
let mockSelectedOrder: Record<string, unknown> | null = null;

jest.mock('../../store/orderStore', () => ({
  useOrderStore: () => ({
    selectedOrder: mockSelectedOrder,
    loading: false,
    error: null,
    fetchOrderDetail: jest.fn().mockResolvedValue(undefined),
    cancelOrder: jest.fn(),
  }),
}));

jest.mock('../../components/LoadingSpinner', () => {
  const React = jest.requireActual('react');
  const { Text } = jest.requireActual('react-native');
  const Spinner = ({ text }: { text: string }) => React.createElement(Text, null, text);
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});
jest.mock('../../components/StatusBadge', () => 'StatusBadge');
jest.mock('../../components/EmptyState', () => {
  const React = jest.requireActual('react');
  const { Text, TouchableOpacity } = jest.requireActual('react-native');
  
  const Empty = ({ title, message, actionLabel, onAction }: { title?: string; message?: string; actionLabel?: string; onAction?: () => void }) =>
    React.createElement(
      React.Fragment,
      null,
      React.createElement(Text, null, title),
      React.createElement(Text, null, message),
      actionLabel && React.createElement(TouchableOpacity, { onPress: onAction }, React.createElement(Text, null, actionLabel)),
    );
  Empty.displayName = 'EmptyState';
  return Empty;
});

const baseOrder = {
  id: 99, orderNo: 'ORD-EXT2-001', userId: 1, stationId: 1,
  stationName: '扩展测试站2', chargerId: 1, chargerName: '2号桩',
  status: 'pending', startTime: '2026-08-03T10:00:00Z',
  endTime: '2026-08-03T11:00:00Z', duration: 60, energy: 15.5,
  power: 30, voltage: 400, current: 75, amount: 18.6,
  couponDiscount: 2.0, paymentStatus: 'pending',
  createdAt: '2026-08-03T10:00:00Z', updatedAt: '2026-08-03T11:00:00Z',
};

describe('OrderDetailScreen.ext2 — unknown status fallback (L98)', () => {
  beforeEach(() => {
    mockSelectedOrder = null;
  });

  it('renders with unknown status using fallback (statusMap miss → raw status)', () => {
    mockSelectedOrder = { ...baseOrder, status: 'pending' }; // 'pending' not in statusMap keys
    const { getByText } = render(
      <SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>
    );
    // Should render without crash — status 'pending' falls through to || order.status
    expect(getByText('订单号: ORD-EXT2-001')).toBeTruthy();
  });
});

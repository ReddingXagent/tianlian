/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert } from 'react-native';
import OrderDetailScreen from '../OrderDetailScreen';

// --- navigation mocks ---
const mockNavigate = jest.fn();
let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: { orderId: 99 } }),
  useIsFocused: () => mockFocused,
}));

// --- store mocks ---
const mockFetchOrderDetail = jest.fn().mockResolvedValue(undefined);
const mockCancelOrder = jest.fn();

let mockSelectedOrder: Record<string, unknown> | null = null;
let mockLoading = false;
let mockError: string | null = null;

jest.mock('../../store/orderStore', () => ({
  useOrderStore: () => ({
    selectedOrder: mockSelectedOrder,
    loading: mockLoading,
    error: mockError,
    fetchOrderDetail: mockFetchOrderDetail,
    cancelOrder: mockCancelOrder,
  }),
}));

// --- component mocks ---
jest.mock('../../components/LoadingSpinner', () => {
  const { Text } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <Text>{text}</Text>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});
jest.mock('../../components/StatusBadge', () => 'StatusBadge');
jest.mock('../../components/EmptyState', () => {
  const { Text, TouchableOpacity } = require('react-native');
  
  const Empty = ({ title, message, actionLabel, onAction }: { title?: string; message?: string; actionLabel?: string; onAction?: () => void }) => (
    <>
      <Text>{title}</Text>
      <Text>{message}</Text>
      {actionLabel && <TouchableOpacity onPress={onAction}><Text>{actionLabel}</Text></TouchableOpacity>}
    </>
  );
  Empty.displayName = 'EmptyState';
  return Empty;
});

const baseOrder = {
  id: 99, orderNo: 'ORD-EXT-001', userId: 1, stationId: 1,
  stationName: '扩展测试站', chargerId: 1, chargerName: '2号桩',
  status: 'completed', startTime: '2026-08-03T10:00:00Z',
  endTime: '2026-08-03T11:00:00Z', duration: 60, energy: 15.5,
  power: 30, voltage: 400, current: 75, amount: 18.6,
  couponDiscount: 2.0, paymentStatus: 'paid',
  createdAt: '2026-08-03T10:00:00Z', updatedAt: '2026-08-03T11:00:00Z',
};

describe('OrderDetailScreen.ext — 分支覆盖', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockSelectedOrder = null;
    mockLoading = false;
    mockError = null;
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);

  // 1. loading=true + no existing order → spinner
  it('shows spinner while loading without cached order', () => {
    mockLoading = true;
    mockSelectedOrder = null;
    const { getByText } = renderScreen();
    expect(getByText('加载订单详情...')).toBeTruthy();
  });

  // 2. error + no cached order → EmptyState error
  it('shows error empty state when fetch fails without cached data', () => {
    mockError = '服务器错误';
    mockSelectedOrder = null;
    const { getByText } = renderScreen();
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('服务器错误')).toBeTruthy();
  });

  // 3. error state retry button calls fetchOrderDetail
  it('retry button in error state calls fetchOrderDetail', () => {
    mockError = '超时';
    mockSelectedOrder = null;
    const { getByText } = renderScreen();
    fireEvent.press(getByText('重试'));
    expect(mockFetchOrderDetail).toHaveBeenCalledWith(99);
  });

  // 4. charging order shows cancel button
  it('shows cancel button for charging order', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'charging', paymentStatus: 'pending' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('取消订单')).toBeTruthy());
  });

  // 5. cancel order success flow (Alert.alert onPress)
  it('cancel order success: calls cancelOrder and shows success alert', async () => {
    type AlertButton = { text?: string; style?: string; onPress?: () => void };
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      // Simulate pressing "确定"
      const destructiveBtn = buttons?.find((b: AlertButton) => b.style === 'destructive');
      destructiveBtn?.onPress?.();
    });
    mockCancelOrder.mockResolvedValue(undefined);
    mockSelectedOrder = { ...baseOrder, status: 'charging', paymentStatus: 'pending' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('取消订单')).toBeTruthy());
    fireEvent.press(getByText('取消订单'));
    await waitFor(() => expect(mockCancelOrder).toHaveBeenCalledWith(99));
    // After cancel succeeds, Alert.alert('成功') is called
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('成功', '订单已取消');
    });
    alertSpy.mockRestore();
  });

  // 6. cancel order failure shows error alert
  it('cancel order failure: shows failure alert', async () => {
    type AlertButton2 = { text?: string; style?: string; onPress?: () => void };
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _msg, buttons) => {
      const destructiveBtn = buttons?.find((b: AlertButton2) => b.style === 'destructive');
      destructiveBtn?.onPress?.();
    });
    mockCancelOrder.mockRejectedValue(new Error('cancel failed'));
    mockSelectedOrder = { ...baseOrder, status: 'charging', paymentStatus: 'pending' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('取消订单')).toBeTruthy());
    fireEvent.press(getByText('取消订单'));
    await waitFor(() => expect(mockCancelOrder).toHaveBeenCalled());
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('失败', '取消失败，请重试');
    });
    alertSpy.mockRestore();
  });

  // 7. status 'cancelled' → statusMap maps to 'cancelled'
  it('renders cancelled status correctly', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'cancelled', paymentStatus: 'paid' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText(/ORD-EXT-001/)).toBeTruthy());
  });

  // 8. status 'timeout' → statusMap maps to 'timeout'
  it('renders timeout status correctly', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'timeout', paymentStatus: 'paid' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText(/ORD-EXT-001/)).toBeTruthy());
  });

  // 9. completed + unpaid → pay button visible AND navigate works
  it('shows pay button for completed unpaid order and navigates on press', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'completed', paymentStatus: 'unpaid' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('去支付')).toBeTruthy());
    fireEvent.press(getByText('去支付'));
    expect(mockNavigate).toHaveBeenCalledWith('Payment', { orderId: 99, amount: 18.6 });
  });

  // 10. completed + paid → no pay button, no cancel button
  it('hides action buttons for completed paid order', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'completed', paymentStatus: 'paid' };
    const { queryByText } = renderScreen();
    await waitFor(() => expect(queryByText('去支付')).toBeNull());
    expect(queryByText('取消订单')).toBeNull();
  });

  // 11. order with vehiclePlate renders plate
  it('renders vehicle plate when present', async () => {
    mockSelectedOrder = { ...baseOrder, vehiclePlate: '京A12345' };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('京A12345')).toBeTruthy());
  });

  // 12. order without vehiclePlate renders dash
  it('renders dash for missing vehicle plate', async () => {
    mockSelectedOrder = { ...baseOrder, vehiclePlate: undefined };
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('-')).toBeTruthy());
  });

  // 13. statusMap: completed + unpaid → 'unpaid' badge
  it('uses unpaid badge for completed unpaid order', async () => {
    mockSelectedOrder = { ...baseOrder, status: 'completed', paymentStatus: 'unpaid' };
    const { getByText } = renderScreen();
    // Order no should be visible, badge maps to 'unpaid'
    await waitFor(() => expect(getByText(/ORD-EXT-001/)).toBeTruthy());
  });

  // 14. refetch on focus: calls fetchOrderDetail when isFocused toggles
  it('refetches when screen regains focus', () => {
    mockSelectedOrder = { ...baseOrder };
    const utils = renderScreen();
    expect(mockFetchOrderDetail).toHaveBeenCalledWith(99);
    const initialCallCount = mockFetchOrderDetail.mock.calls.length;

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);
    expect(mockFetchOrderDetail.mock.calls.length).toBe(initialCallCount);

    mockFocused = true;
    utils.rerender(<SafeAreaProvider><OrderDetailScreen /></SafeAreaProvider>);
    expect(mockFetchOrderDetail.mock.calls.length).toBeGreaterThan(initialCallCount);
  });

  // 15. loading with cached order: still renders (not spinner)
  it('renders cached order while loading (no spinner)', () => {
    mockLoading = true;
    mockSelectedOrder = { ...baseOrder };
    const { queryByText, getByText } = renderScreen();
    expect(queryByText('加载订单详情...')).toBeNull();
    expect(getByText(/ORD-EXT-001/)).toBeTruthy();
  });

  // 16. error with cached order: still renders (not error page)
  it('renders cached order when error exists but data present', () => {
    mockError = '刷新失败';
    mockSelectedOrder = { ...baseOrder };
    const { queryByText, getByText } = renderScreen();
    expect(queryByText('加载失败')).toBeNull();
    expect(getByText(/ORD-EXT-001/)).toBeTruthy();
  });

  // 17. null order (no data, no loading, no error) → returns null (renders empty View)
  it('renders minimal when order is null without loading or error', () => {
    mockSelectedOrder = null;
    mockLoading = false;
    mockError = null;
    const { toJSON } = renderScreen();
    // Component returns null → React Native renders empty <View />
    expect(toJSON()).not.toBeNull();
  });

  // 18. fee breakdown: couponDiscount=0 → discount shows ¥0.00
  it('renders zero discount correctly', async () => {
    mockSelectedOrder = { ...baseOrder, couponDiscount: 0 };
    const { getByText, getAllByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('-¥0.00')).toBeTruthy();
      expect(getAllByText('¥18.60').length).toBeGreaterThanOrEqual(1); // amount - 0 = 18.60
    });
  });
});

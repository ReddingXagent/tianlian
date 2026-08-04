import React from 'react';
import { RefreshControl } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

let mockGetList: jest.Mock;

jest.mock('../../services/api', () => {
  const getList = jest.fn();
  mockGetList = getList;
  const add = jest.fn();
  const remove = jest.fn();
  const setDefault = jest.fn();
  return { vehicleApi: { getList, add, remove, setDefault } };
});

jest.mock('../../components/LoadingSpinner', () => {
  const { Text } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <Text>{text}</Text>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});

jest.mock('../../components/EmptyState', () => {
  const { Text, TouchableOpacity } = require('react-native');
  const Empty = ({ icon, title, message, actionLabel, onAction }: any) => (
    <>
      <Text>{title}</Text>
      <Text>{message}</Text>
      {actionLabel && onAction && (
        <TouchableOpacity onPress={onAction}><Text>{actionLabel}</Text></TouchableOpacity>
      )}
    </>
  );
  Empty.displayName = 'EmptyState';
  return Empty;
});

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

const mockVehicles = [
  { id: 1, userId: 1, plate: '京A12345', brand: 'Tesla', model: 'Model 3',
    color: '白色', vin: 'VIN001', isDefault: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 2, userId: 1, plate: '京B67890', brand: 'BYD', model: '汉EV',
    color: '黑色', vin: 'VIN002', isDefault: false, createdAt: '2026-01-02T00:00:00Z' },
];

describe('VehicleScreen', () => {
  beforeEach(() => { jest.clearAllMocks(); mockFocused = true; });

  const renderScreen = () =>
    render(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);

  it('renders loading state initially', () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockReturnValue(new Promise(() => {}));
    const { getByText } = renderScreen();
    expect(getByText('加载车辆列表...')).toBeTruthy();
  });

  it('renders vehicle list after load', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('京A12345')).toBeTruthy();
      expect(getByText('京B67890')).toBeTruthy();
    });
  });

  it('shows default badge for default vehicle', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('默认')).toBeTruthy();
    });
  });

  it('renders add vehicle button', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('+ 添加车辆')).toBeTruthy();
    });
  });

  it('renders empty state when no vehicles', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: [] });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('暂无车辆')).toBeTruthy();
    });
  });

  it('shows error state on API failure', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockRejectedValue(new Error('Server Error'));
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });
  });

  it('opens add modal when button pressed', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('+ 添加车辆')).toBeTruthy());
    fireEvent.press(getByText('+ 添加车辆'));
    expect(getByText('添加车辆')).toBeTruthy();
  });

  it('renders vehicle brand and model', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });
    const { getByText } = renderScreen();
    await waitFor(() => {
      expect(getByText('Tesla Model 3')).toBeTruthy();
      expect(getByText('BYD 汉EV')).toBeTruthy();
    });
  });

  // --- F215: 回焦静默刷新 + 下拉刷新对齐(F170/F209模式) ---
  it('回焦时重新拉取车辆列表(默认车辆/状态可能已变化)', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(1));

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);
    expect(mockGetList).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
  });

  it('下拉刷新重拉车辆列表(refreshControl onRefresh 并复位 refreshing)', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('京A12345')).toBeTruthy());
    expect(mockGetList).toHaveBeenCalledTimes(1);

    const rc = utils.UNSAFE_getByType(RefreshControl);
    await act(async () => {
      await rc.props.onRefresh();
    });

    expect(mockGetList).toHaveBeenCalledTimes(2);
    const rcAfter = utils.UNSAFE_getByType(RefreshControl);
    expect(rcAfter.props.refreshing).toBe(false);
  });

  it('回焦重拉期间已有列表保持可见(不整屏切spinner)', async () => {
    let call = 0;
    mockGetList.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: mockVehicles });
      // 第二拉挂起: 模拟回焦重拉中, 验证列表不被LoadingSpinner替换
      return new Promise(() => {});
    });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('京A12345')).toBeTruthy());

    mockFocused = false;
    utils.rerender(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);
    mockFocused = true;
    utils.rerender(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);

    // 重拉中: 已有车辆仍可见, 不切整屏spinner
    expect(utils.getByText('京A12345')).toBeTruthy();
    expect(utils.queryByText('加载车辆列表...')).toBeNull();
  });
});

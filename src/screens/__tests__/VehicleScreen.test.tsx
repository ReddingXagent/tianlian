import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

jest.mock('../../services/api', () => {
  const getList = jest.fn();
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

const mockVehicles = [
  { id: 1, userId: 1, plate: '京A12345', brand: 'Tesla', model: 'Model 3',
    color: '白色', vin: 'VIN001', isDefault: true, createdAt: '2026-01-01T00:00:00Z' },
  { id: 2, userId: 1, plate: '京B67890', brand: 'BYD', model: '汉EV',
    color: '黑色', vin: 'VIN002', isDefault: false, createdAt: '2026-01-02T00:00:00Z' },
];

describe('VehicleScreen', () => {
  beforeEach(() => { jest.clearAllMocks(); });

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
});
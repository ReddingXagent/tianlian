import React from 'react';
import { Alert } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

// ─── Mocks ────────────────────────────────────────────────

let mockGetList: jest.Mock;
let mockAdd: jest.Mock;

jest.mock('../../services/api', () => {
  const getList = jest.fn();
  mockGetList = getList;
  const add = jest.fn();
  mockAdd = add;
  return { vehicleApi: { getList, add, remove: jest.fn(), setDefault: jest.fn() } };
});

jest.mock('../../components/LoadingSpinner', () => {
  const { Text } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <Text>{text}</Text>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});

jest.mock('../../components/EmptyState', () => {
  const { Text, TouchableOpacity } = require('react-native');
  const Empty = ({ title, message, actionLabel, onAction }: any) => (
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
];

describe('VehicleScreen.ext2 — final branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });
  afterEach(() => {
    (Alert.alert as jest.Mock).mockRestore();
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><VehicleScreen /></SafeAreaProvider>);

  const renderLoaded = async (vehicles = mockVehicles) => {
    mockGetList.mockResolvedValue({ data: vehicles });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());
    return utils;
  };

  const openModal = async (utils: ReturnType<typeof renderScreen>) => {
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());
  };

  // Line 45: loadVehicles catch → err instanceof Error === false (non-Error throw)
  it('sets generic error message when loadVehicles throws non-Error', async () => {
    mockGetList.mockRejectedValue('network failure');
    const { findByText } = renderScreen();

    await findByText('获取车辆列表失败');
  });

  // Line 90: handleAdd catch → axios error with response.data.message
  it('shows specific axios error message on add failure with response', async () => {
    mockAdd.mockRejectedValue({
      response: { data: { message: '车牌已存在' } },
    });

    const utils = await renderLoaded();
    await openModal(utils);

    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京C99999');
    fireEvent.press(utils.getByText('保存'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('添加失败', '车牌已存在');
    });
  });

  // Line 226: Modal onRequestClose callback — render modal then dismiss
  it('opens and closes modal via cancel button', async () => {
    const utils = await renderLoaded();
    await openModal(utils);

    expect(utils.getByText('添加车辆')).toBeTruthy();

    fireEvent.press(utils.getByText('取消'));
    await waitFor(() => {
      expect(utils.queryByText('添加车辆')).toBeNull();
    });
  });
});

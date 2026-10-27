import React from 'react';
import { Modal } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

jest.mock('../../services/api', () => ({
  vehicleApi: {
    getList: jest.fn(),
    add: jest.fn(),
    remove: jest.fn(),
    setDefault: jest.fn(),
  },
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

const mockVehicles = [
  { id: 1, userId: 1, plate: '京A12345', brand: 'Tesla', model: 'Model 3',
    color: '白色', vin: 'VIN001', isDefault: true, createdAt: '2026-01-01T00:00:00Z' },
];

describe('VehicleScreen.ext3 — Modal onRequestClose 分支', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
  });

  it('Android返回键/系统关闭请求(onRequestClose)关闭添加车辆弹窗', async () => {
    const { vehicleApi } = require('../../services/api');
    vehicleApi.getList.mockResolvedValue({ data: mockVehicles });

    const utils = render(
      <SafeAreaProvider>
        <VehicleScreen />
      </SafeAreaProvider>
    );
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());

    // 打开弹窗
    fireEvent.press(utils.getByText('+ 添加车辆'));
    let modal = utils.UNSAFE_getByType(Modal);
    expect(modal.props.visible).toBe(true);

    // 触发 onRequestClose(Android 物理返回键路径)
    act(() => {
      modal.props.onRequestClose();
    });

    modal = utils.UNSAFE_getByType(Modal);
    expect(modal.props.visible).toBe(false);
  });
});

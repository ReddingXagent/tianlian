/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

// Share the same mock pattern as the base test file
let mockGetList: jest.Mock;
let mockAdd: jest.Mock;
let mockRemove: jest.Mock;
let mockSetDefault: jest.Mock;

jest.mock('../../services/api', () => {
  const getList = jest.fn();
  mockGetList = getList;
  const add = jest.fn();
  mockAdd = add;
  const remove = jest.fn();
  mockRemove = remove;
  const setDefault = jest.fn();
  mockSetDefault = setDefault;
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
  
  const Empty = ({ icon: _icon, title, message, actionLabel, onAction }: { icon?: React.ReactNode; title?: string; message?: string; actionLabel?: string; onAction?: () => void }) => (
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

describe('VehicleScreen — extended coverage', () => {
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

  // Helper: wait for list to load then return utils
  const renderLoaded = async (vehicles = mockVehicles) => {
    mockGetList.mockResolvedValue({ data: vehicles });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());
    return utils;
  };

  // Helper: open add modal
  const openModal = async (utils: ReturnType<typeof renderScreen>) => {
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());
  };

  // --- handleAdd: success path ---
  it('fills form and adds vehicle successfully', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockAdd.mockResolvedValue({});
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());

    // Fill plate (required field)
    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京C99999');
    fireEvent.changeText(utils.getByPlaceholderText('品牌'), 'NIO');
    fireEvent.changeText(utils.getByPlaceholderText('型号'), 'ET7');
    fireEvent.changeText(utils.getByPlaceholderText('颜色'), '蓝色');
    fireEvent.changeText(utils.getByPlaceholderText('VIN码'), 'VIN003');

    fireEvent.press(utils.getByText('保存'));

    await waitFor(() => expect(mockAdd).toHaveBeenCalledWith({
      plate: '京C99999', brand: 'NIO', model: 'ET7', color: '蓝色', vin: 'VIN003', isDefault: false,
    }));
    // After success: modal closes + reload
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
  });

  // --- handleAdd: empty plate validation ---
  it('shows alert when plate is empty on save', async () => {
    const utils = await renderLoaded();
    await openModal(utils);
    fireEvent.press(utils.getByText('保存'));
    expect(Alert.alert).toHaveBeenCalledWith('提示', '请输入车牌号');
    expect(mockAdd).not.toHaveBeenCalled();
  });

  // --- handleAdd: API error with response (axios error) ---
  it('shows axios error message on add failure', async () => {
    const utils = await renderLoaded();
    await openModal(utils);
    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京D88888');
    mockAdd.mockRejectedValue({
      response: { data: { message: '车牌已被绑定' } },
    });
    fireEvent.press(utils.getByText('保存'));
    await waitFor(() => expect(mockAdd).toHaveBeenCalled());
    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('添加失败', '车牌已被绑定');
    });
  });

  // --- handleAdd: network error (non-axios) ---
  it('shows network error on add failure without response', async () => {
    const utils = await renderLoaded();
    await openModal(utils);
    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京E77777');
    mockAdd.mockRejectedValue(new Error('Network'));
    fireEvent.press(utils.getByText('保存'));
    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('添加失败', '网络错误');
    });
  });

  // --- handleAdd: isDefault checkbox toggle ---
  it('toggles default checkbox and includes isDefault=true on submit', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockAdd.mockResolvedValue({});
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());

    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京F66666');
    // Toggle checkbox on
    fireEvent.press(utils.getByText('设为默认车辆'));
    fireEvent.press(utils.getByText('保存'));

    await waitFor(() => {
      expect(mockAdd).toHaveBeenCalledWith(
        expect.objectContaining({ plate: '京F66666', isDefault: true })
      );
    });
  });

  // --- handleRemove: confirm deletion ---
  it('removes vehicle when user confirms deletion', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockRemove.mockResolvedValue({});
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('京A12345')).toBeTruthy());

    // Press delete on first vehicle (id=1, 京A12345)
    const deleteButtons = utils.getAllByText('删除');
    fireEvent.press(deleteButtons[0]);

    // Alert was called with options
    expect(Alert.alert).toHaveBeenCalledWith(
      '删除车辆',
      expect.stringContaining('京A12345'),
      expect.arrayContaining([
        expect.objectContaining({ text: '取消', style: 'cancel' }),
        expect.objectContaining({ text: '删除', style: 'destructive' }),
      ])
    );

    // Extract the onPress callback from the alert call
    const alertCall = (Alert.alert as jest.Mock).mock.calls[0];
    type AlertOption = { text?: string; onPress?: () => Promise<void> | void };
    const deleteOption = alertCall[2].find((o: AlertOption) => o.text === '删除');
    await act(async () => {
      await deleteOption.onPress();
    });

    expect(mockRemove).toHaveBeenCalledWith(1);
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
  });

  // --- handleRemove: deletion fails ---
  it('shows error alert when deletion fails', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockRemove.mockRejectedValue(new Error('fail'));
    const utils = renderScreen();
    await waitFor(() => expect(utils.getAllByText('删除')).toBeTruthy());

    fireEvent.press(utils.getAllByText('删除')[0]);
    const alertCall = (Alert.alert as jest.Mock).mock.calls[0];
    const deleteOpt = alertCall[2].find((o: { text?: string }) => o.text === '删除');

    (Alert.alert as jest.Mock).mockClear();
    await act(async () => {
      await deleteOpt.onPress();
    });

    expect(Alert.alert).toHaveBeenCalledWith('删除失败', '请重试');
  });

  // --- handleSetDefault: success ---
  it('sets non-default vehicle as default', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockSetDefault.mockResolvedValue({});
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('设为默认')).toBeTruthy());

    fireEvent.press(utils.getByText('设为默认'));

    await waitFor(() => expect(mockSetDefault).toHaveBeenCalledWith(2));
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
  });

  // --- handleSetDefault: failure ---
  it('shows error when setDefault fails', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    mockSetDefault.mockRejectedValue(new Error('fail'));
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('设为默认')).toBeTruthy());

    fireEvent.press(utils.getByText('设为默认'));
    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('设置失败', '请重试');
    });
  });

  // --- resetForm: cancel button resets form fields ---
  it('resets form fields when cancel pressed', async () => {
    const utils = await renderLoaded();
    await openModal(utils);

    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京G55555');
    fireEvent.changeText(utils.getByPlaceholderText('品牌'), 'BMW');
    // Cancel
    fireEvent.press(utils.getByText('取消'));

    // Reopen modal — fields should be empty
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());
    expect(utils.getByPlaceholderText('车牌号 *').props.value).toBe('');
    expect(utils.getByPlaceholderText('品牌').props.value).toBe('');
  });

  // --- renderVehicleItem: non-default vehicle shows "设为默认" button ---
  it('shows set-default button only for non-default vehicles', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('设为默认')).toBeTruthy());
    // Default vehicle (京A12345) should not have "设为默认" — only one instance
    expect(utils.getAllByText('设为默认')).toHaveLength(1);
  });

  // --- renderVehicleItem: default vehicle shows default badge ---
  it('renders default badge and hides set-default for default vehicle', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('默认')).toBeTruthy());
    expect(utils.getAllByText('默认')).toHaveLength(1);
  });

  // --- renderVehicleItem: vehicle detail fields ---
  it('renders color and VIN details', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => {
      expect(utils.getByText('颜色: 白色')).toBeTruthy();
      expect(utils.getByText('VIN: VIN001')).toBeTruthy();
      expect(utils.getByText('颜色: 黑色')).toBeTruthy();
      expect(utils.getByText('VIN: VIN002')).toBeTruthy();
    });
  });

  // --- Error state retry via EmptyState action ---
  it('retries loading when error retry button pressed', async () => {
    let call = 0;
    mockGetList.mockImplementation(() => {
      call++;
      if (call === 1) return Promise.reject(new Error('fail'));
      return Promise.resolve({ data: mockVehicles });
    });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('加载失败')).toBeTruthy());

    fireEvent.press(utils.getByText('重试'));
    await waitFor(() => expect(mockGetList).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(utils.getByText('京A12345')).toBeTruthy());
  });

  // --- saving state disables save button ---
  it('shows saving state during add (button disabled)', async () => {
    const utils = await renderLoaded();
    await openModal(utils);
    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京H44444');

    // Make add hang so saving state persists
    mockAdd.mockReturnValue(new Promise(() => {}));
    fireEvent.press(utils.getByText('保存'));

    // mockAdd called = saving started; "保存" text replaced by ActivityIndicator
    await waitFor(() => expect(mockAdd).toHaveBeenCalled());
    // The "保存" text should no longer be visible (ActivityIndicator shown instead)
    expect(utils.queryByText('保存')).toBeNull();
  });

  // --- Multiple vehicles: both delete buttons present ---
  it('renders delete buttons for all vehicles', async () => {
    mockGetList.mockResolvedValue({ data: mockVehicles });
    const utils = renderScreen();
    await waitFor(() => {
      const delBtns = utils.getAllByText('删除');
      expect(delBtns).toHaveLength(2);
    });
  });
});

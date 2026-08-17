/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import VehicleScreen from '../VehicleScreen';

// F1226 coverage: VehicleScreen L60 !cancelled 守卫的 false 臂
// 真缺口: 既有回焦测试(rerender 复用同一组件实例, cancelled 永不生效)未打到
// unmount 后微任务跳过 loadVehicles 的路径 — F1225 ProfileScreen.ext3 同款手法。
// 正确手法: render 后同步 unmount, effect cleanup 置 cancelled=true,
// 再排空微任务队列 → L60 走 false 臂, getList 永不发起。
// fail-fast 锚定: getList 计数恒 0(先证微任务确已排空)

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
  const { Text: T } = require('react-native');
  const Spinner = ({ text }: { text: string }) => <T>{text}</T>;
  Spinner.displayName = 'LoadingSpinner';
  return Spinner;
});

jest.mock('../../components/EmptyState', () => {
  const { Text: T, TouchableOpacity } = require('react-native');
  const Empty = ({ title, actionLabel, onAction }: { title?: string; actionLabel?: string; onAction?: () => void }) => (
    <>
      <T>{title}</T>
      {actionLabel && onAction ? (
        <TouchableOpacity onPress={onAction}><T>{actionLabel}</T></TouchableOpacity>
      ) : null}
    </>
  );
  Empty.displayName = 'EmptyState';
  return Empty;
});

let mockFocused = true;

jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

const flushMicrotasks = () => new Promise(resolve => setImmediate(resolve));

describe('VehicleScreen L60 unmount guard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockFocused = true;
  });

  afterEach(() => {
    (Alert.alert as jest.Mock).mockRestore();
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <VehicleScreen />
      </SafeAreaProvider>
    );

  it('never fetches when unmounted synchronously before microtask runs (卸载守卫 false 臂)', async () => {
    mockGetList.mockResolvedValue({ data: [] });
    const { unmount } = renderScreen();

    // 同步卸载: effect cleanup 置 cancelled=true, 微任务尚未执行
    unmount();

    // 排空微任务队列(多轮保证 Promise.resolve().then 链走完)
    await flushMicrotasks();
    await flushMicrotasks();

    // fail-fast 锚定: 微任务确实排空但守卫拦住了 getList
    expect(mockGetList).not.toHaveBeenCalled();
    expect(mockAdd).not.toHaveBeenCalled();
    expect(mockRemove).not.toHaveBeenCalled();
    expect(mockSetDefault).not.toHaveBeenCalled();
  });

  // F1226 coverage: L94 axios 形状但响应无 message 字段 → || '请重试' 兜底臂
  // 既有测试只测了 message 存在('车牌已被绑定')与纯网络错误两臂, 兜底臂未走过
  it('falls back to 请重试 when axios error has no response message (L94 兜底臂)', async () => {
    mockGetList.mockResolvedValue({ data: [] });
    const utils = renderScreen();
    await waitFor(() => expect(utils.getByText('+ 添加车辆')).toBeTruthy());
    fireEvent.press(utils.getByText('+ 添加车辆'));
    await waitFor(() => expect(utils.getByText('添加车辆')).toBeTruthy());

    fireEvent.changeText(utils.getByPlaceholderText('车牌号 *'), '京G43210');
    mockAdd.mockRejectedValue({
      response: { data: {} }, // axios 形状但无 message → 走 || 兜底
    });
    fireEvent.press(utils.getByText('保存'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('添加失败', '请重试');
    });
  });
});

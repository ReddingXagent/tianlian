import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ProfileScreen from '../ProfileScreen';

// F1225 coverage: L56 !cancelled 守卫的 false 臂
// 真缺口: 既有回焦测试(rerender 复用同一组件实例)与 F1224 中断轮 ext3 首版
// (waitFor 挂载期调用后再 unmount) 都没打到 — 微任务早已执行, cancelled=false。
// 正确手法: render 后同步 unmount, effect cleanup 置 cancelled=true,
// 再排空微任务队列 → L56 走 false 臂, 两个 fetch 永不发起。
// fail-fast 锚定: getUserStats/getProfile 计数恒 0(先证微任务确已排空)

const mockGetUserStats = jest.fn().mockResolvedValue({ data: {} });
const mockGetProfile = jest.fn().mockResolvedValue({ data: {} });

jest.mock('../../services/api', () => ({
  statsApi: {
    getUserStats: (...args: unknown[]) => mockGetUserStats(...args),
  },
  authApi: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
  },
}));

const mockUser = {
  id: 1,
  phone: '13800001111',
  nickname: '测试用户',
  balance: 88.5,
};

const mockLogout = jest.fn().mockResolvedValue(undefined);
const mockSetUser = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: mockUser,
    logout: mockLogout,
    setUser: mockSetUser,
  }),
}));

let mockFocused = true;

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({
    navigate: jest.fn(),
  }),
  useIsFocused: () => mockFocused,
}));

const flushMicrotasks = () => new Promise(resolve => setImmediate(resolve));

describe('ProfileScreen L56 unmount guard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <ProfileScreen />
      </SafeAreaProvider>
    );

  it('never fetches when unmounted synchronously before microtask runs (卸载守卫 false 臂)', async () => {
    const { unmount } = renderScreen();

    // 同步卸载: effect cleanup 置 cancelled=true, 微任务尚未执行
    unmount();

    // 排空微任务队列(多轮保证 Promise.resolve().then 链走完)
    await flushMicrotasks();
    await flushMicrotasks();

    // fail-fast 锚定: 微任务确实排空但守卫拦住了两个 fetch
    expect(mockGetUserStats).not.toHaveBeenCalled();
    expect(mockGetProfile).not.toHaveBeenCalled();
  });
});

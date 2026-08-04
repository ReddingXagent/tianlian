import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import NetInfo from '@react-native-community/netinfo';

// ── Mock auth store (must be self-contained in factory) ──────
const mockAuthState = {
  token: null as string | null,
  user: null as unknown,
  isAuthenticated: false,
  isLoading: false,
  loginByCode: jest.fn().mockResolvedValue(undefined),
  loginByPassword: jest.fn().mockResolvedValue(undefined),
  logout: jest.fn().mockResolvedValue(undefined),
  checkAuth: jest.fn().mockResolvedValue(undefined),
  setUser: jest.fn(),
};

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector?: (s: typeof mockAuthState) => unknown) => {
    if (selector) return selector(mockAuthState);
    return mockAuthState;
  },
}));

// ── Mock navigation: use React.Nested to avoid scope issues ──
jest.mock('@react-navigation/native', () => {
  const React = require('react');
  return {
    NavigationContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    // TabBackHandler 需要: 最小导航对象(无父栈, tab停在 index 0)
    useNavigation: () => ({
      getParent: () => undefined,
      getState: () => ({ index: 0 }),
      navigate: () => {},
    }),
  };
});

jest.mock('@react-navigation/native-stack', () => {
  const React = require('react');
  return {
    createNativeStackNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) =>
        React.createElement(React.Fragment, null, children),
      Screen: ({ name, component: Comp }: { name: string; component: React.FC }) => {
        // Render all named screens — component will be a stub or navigator
        if (Comp) return React.createElement(Comp);
        return null;
      },
    }),
  };
});

jest.mock('@react-navigation/bottom-tabs', () => {
  const React = require('react');
  const { Text, View } = require('react-native');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) =>
        React.createElement(View, { testID: 'tab-navigator' }, children),
      Screen: ({ name }: { name: string }) =>
        React.createElement(Text, null, name),
    }),
  };
});

// ── Mock screens to lightweight stubs ────────────────────────
jest.mock('../../screens/LoginScreen', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const LoginScreenStub = () => React.createElement(Text, null, 'LoginScreen');
  LoginScreenStub.displayName = 'LoginScreen';
  return LoginScreenStub;
});
jest.mock('../../screens/HomeScreen', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const HomeScreenStub = () => React.createElement(Text, null, 'HomeScreen');
  HomeScreenStub.displayName = 'HomeScreen';
  return HomeScreenStub;
});
jest.mock('../../screens/StationDetailScreen', () => () => null);
jest.mock('../../screens/OrderListScreen', () => () => null);
jest.mock('../../screens/ScanScreen', () => () => null);
jest.mock('../../screens/ProfileScreen', () => () => null);
jest.mock('../../screens/ChargingScreen', () => () => null);
jest.mock('../../screens/OrderDetailScreen', () => () => null);
jest.mock('../../screens/PaymentScreen', () => () => null);
jest.mock('../../screens/VehicleScreen', () => () => null);
jest.mock('../../screens/WalletScreen', () => () => null);
jest.mock('../../screens/CouponScreen', () => () => null);

jest.mock('../../components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) =>
    require('react').createElement(require('react').Fragment, null, children),
}));

import { AppNavigator } from '../AppNavigator';

const renderNavigator = () =>
  render(
    <SafeAreaProvider>
      <AppNavigator />
    </SafeAreaProvider>
  );

describe('AppNavigator', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
    mockAuthState.token = null;
    mockAuthState.user = null;
  });

  it('renders loading indicator when isLoading is true', () => {
    mockAuthState.isLoading = true;
    const { getByText } = renderNavigator();
    expect(getByText('加载中...')).toBeTruthy();
  });

  it('renders Login screen when not authenticated', () => {
    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
    const { getByText } = renderNavigator();
    expect(getByText('LoginScreen')).toBeTruthy();
  });

  it('renders tab navigator when authenticated', () => {
    mockAuthState.isAuthenticated = true;
    mockAuthState.isLoading = false;
    const { getByTestId } = renderNavigator();
    expect(getByTestId('tab-navigator')).toBeTruthy();
  });

  it('calls checkAuth on mount', () => {
    renderNavigator();
    expect(mockAuthState.checkAuth).toHaveBeenCalledTimes(1);
  });

  it('shows tab screen names when authenticated', () => {
    mockAuthState.isAuthenticated = true;
    const { getByText } = renderNavigator();
    expect(getByText('Home')).toBeTruthy();
    expect(getByText('Orders')).toBeTruthy();
    expect(getByText('Scan')).toBeTruthy();
    expect(getByText('Profile')).toBeTruthy();
  });
});

// F228: OfflineBanner根级挂载实证 — 组件此前有实现有单测但零挂载(死代码)。
// 挂载守卫: 离线时AppNavigator渲染树必含offline-banner, 在线时零干扰。
// NetInfo走jest.setup.ts全局mock, 此处覆写addEventListener的首帧回值。
type NetInfoCb = (state: { isConnected: boolean; isInternetReachable: boolean }) => void;

function mockNetInfoFirstFrame(firstFrame: { isConnected: boolean; isInternetReachable: boolean } | null) {
  (NetInfo.addEventListener as jest.Mock).mockImplementation((cb: NetInfoCb) => {
    if (firstFrame) cb(firstFrame);
    return () => {};
  });
}

describe('AppNavigator OfflineBanner mount (F228)', () => {
  it('在线时不展示离线横幅(挂载零干扰)', () => {
    mockNetInfoFirstFrame({ isConnected: true, isInternetReachable: true });
    const { queryByTestId } = renderNavigator();
    expect(queryByTestId('offline-banner')).toBeNull();
  });

  it('确认离线时展示离线横幅(Auth态同样覆盖)', () => {
    mockNetInfoFirstFrame({ isConnected: false, isInternetReachable: false });
    const { getByTestId, getByText } = renderNavigator();
    expect(getByTestId('offline-banner')).toBeTruthy();
    expect(getByText('网络已断开 · 显示缓存数据')).toBeTruthy();
  });
});

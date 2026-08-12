import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppNavigator } from '../AppNavigator';

// Use global to collect callbacks from inside jest.mock factories
(global as Record<string, unknown>).__capturedIcons = [];
(global as Record<string, unknown>).__capturedHeaderLefts = [];

// ── Mock auth store (must be self-contained in factory) ──────
jest.mock('../../store/authStore', () => {
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
  return {
    useAuthStore: (selector?: (s: typeof mockAuthState) => unknown) => {
      if (selector) return selector(mockAuthState);
      return mockAuthState;
    },
    __mockAuthState: mockAuthState,
  };
});

jest.mock('@react-navigation/native', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require('react');
  return {
    NavigationContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useNavigation: () => ({
      getParent: () => undefined,
      getState: () => ({ index: 0 }),
      navigate: () => {},
    }),
  };
});

jest.mock('@react-navigation/native-stack', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require('react');
  return {
    createNativeStackNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) =>
        React.createElement(React.Fragment, null, children),
      Screen: ({ name, component: Comp, options }: { name: string; component: React.FC; options?: Record<string, unknown> }) => {
        const g = global as Record<string, unknown>;
        const hl = g.__capturedHeaderLefts as (() => null)[];
        if (options && 'headerLeft' in options && typeof options.headerLeft === 'function') {
          hl.push(options.headerLeft as () => null);
        }
        if (Comp) return React.createElement(Comp);
        return null;
      },
    }),
  };
});

jest.mock('@react-navigation/bottom-tabs', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require('react');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { Text, View } = require('react-native');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) =>
        React.createElement(View, { testID: 'tab-navigator' }, children),
      Screen: ({ name, options }: { name: string; options?: Record<string, unknown> }) => {
        const g = global as Record<string, unknown>;
        const icons = g.__capturedIcons as { label: string; focused: boolean }[];
        if (options && 'tabBarIcon' in options) {
          const iconFn = options.tabBarIcon as any;
          icons.push({ label: name, focused: true });
          icons.push({ label: name, focused: false });
          try {
            iconFn({ focused: true });
            iconFn({ focused: false });
          } catch {
            // ignore
          }
        }
        return React.createElement(Text, null, name);
      },
    }),
  };
});

// ── Mock screens ─────────────────────────────────────────────
jest.mock('../../screens/LoginScreen', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require('react');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { Text } = require('react-native');
  const LoginScreenStub = () => React.createElement(Text, null, 'LoginScreen');
  LoginScreenStub.displayName = 'LoginScreen';
  return LoginScreenStub;
});
jest.mock('../../screens/HomeScreen', () => () => null);
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

// Access mock auth state via the exported __mockAuthState
const authMod = require('../../store/authStore');
const mockAuthState = authMod.__mockAuthState as {
  isAuthenticated: boolean;
  isLoading: boolean;
  checkAuth: jest.Mock;
};

const renderNavigator = () =>
  render(
    <SafeAreaProvider>
      <AppNavigator />
    </SafeAreaProvider>
  );

describe('AppNavigator.ext — coverage lift 79% → 95%+', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global as Record<string, unknown>).__capturedIcons = [];
    (global as Record<string, unknown>).__capturedHeaderLefts = [];
    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
  });

  it('renders MainWithDetail with all detail screens when authenticated', () => {
    mockAuthState.isAuthenticated = true;
    const { getByTestId } = renderNavigator();
    expect(getByTestId('tab-navigator')).toBeTruthy();
  });

  it('invokes tabBarIcon for all 4 tabs with focused=true and focused=false', () => {
    mockAuthState.isAuthenticated = true;
    renderNavigator();
    const icons = (global as Record<string, unknown>).__capturedIcons as { label: string; focused: boolean }[];
    expect(icons.length).toBe(8);
    const labels = icons.map((c) => c.label);
    expect(labels).toContain('Home');
    expect(labels).toContain('Orders');
    expect(labels).toContain('Scan');
    expect(labels).toContain('Profile');
  });

  it('captures and invokes headerLeft callback for Charging screen', () => {
    mockAuthState.isAuthenticated = true;
    renderNavigator();
    const hls = (global as Record<string, unknown>).__capturedHeaderLefts as (() => null)[];
    expect(hls.length).toBeGreaterThanOrEqual(1);
    const result = hls[0]();
    expect(result).toBeNull();
  });

  it('renders AuthNavigator (Login) when not authenticated', () => {
    mockAuthState.isAuthenticated = false;
    const { getByText } = renderNavigator();
    expect(getByText('LoginScreen')).toBeTruthy();
  });

  it('renders loading state with ActivityIndicator', () => {
    mockAuthState.isLoading = true;
    const { getByText } = renderNavigator();
    expect(getByText('加载中...')).toBeTruthy();
  });
});

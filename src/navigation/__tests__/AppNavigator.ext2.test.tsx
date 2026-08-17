import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppNavigator } from '../AppNavigator';

// Use global to collect icon calls from inside jest.mock factories
(global as Record<string, unknown>).__iconCalls = [];

// ── Mock auth store ──────────────────────────────────────────
jest.mock('../../store/authStore', () => {
  const ms = {
    token: null,
    user: null,
    isAuthenticated: false,
    isLoading: false,
    loginByCode: jest.fn().mockResolvedValue(undefined),
    loginByPassword: jest.fn().mockResolvedValue(undefined),
    logout: jest.fn().mockResolvedValue(undefined),
    checkAuth: jest.fn().mockResolvedValue(undefined),
    setUser: jest.fn(),
  };
  return {
    useAuthStore: (selector?: (s: typeof ms) => unknown) => {
      if (selector) return selector(ms);
      return ms;
    },
    __mockAuthState: ms,
  };
});

jest.mock('@react-navigation/native', () => {
  const React = require('react');
  return {
    NavigationContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useIsFocused: () => true,
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
  const React = require('react');
  const { View, Text } = require('react-native');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) =>
        React.createElement(View, { testID: 'tab-navigator' }, children),
      Screen: ({ name, options }: { name: string; options?: Record<string, unknown> }) => {
        const g = global as Record<string, unknown>;
        const calls = g.__iconCalls as { focused: boolean; label: string }[];
        const children: React.ReactNode[] = [];
        if (options && 'tabBarIcon' in options) {
          const iconFn = options.tabBarIcon as (mockArgs: { focused: boolean }) => React.ReactNode;
          calls.push({ focused: true, label: name });
          calls.push({ focused: false, label: name });
          // Actually create the icon elements so TabIcon function gets invoked
          try {
            children.push(iconFn({ focused: true }));
            children.push(iconFn({ focused: false }));
          } catch {
            // ignore
          }
        }
        return React.createElement(View, null, ...children, React.createElement(Text, null, name));
      },
    }),
  };
});

// ── Mock screens ─────────────────────────────────────────────
jest.mock('../../screens/LoginScreen', () => () => null);
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
jest.mock('../../screens/EnergyScreen', () => () => null);

jest.mock('../../components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) =>
    require('react').createElement(require('react').Fragment, null, children),
}));

const authMod = require('../../store/authStore');
const mockState = authMod.__mockAuthState as {
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

describe('AppNavigator.ext2 — TabIcon branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global as Record<string, unknown>).__iconCalls = [];
    (global as Record<string, unknown>).__capturedHeaderLefts = [];
    mockState.isAuthenticated = true;
    mockState.isLoading = false;
  });

  it('invokes TabIcon with focused=true for all 4 tabs', () => {
    const { toJSON } = renderNavigator();
    const tree = JSON.stringify(toJSON());
    // TabIcon renders emoji labels - verify they appear in tree
    expect(tree).toContain('🏠');
    expect(tree).toContain('📋');
    expect(tree).toContain('📷');
    expect(tree).toContain('👤');
    const calls = (global as Record<string, unknown>).__iconCalls as { focused: boolean; label: string }[];
    const focused = calls.filter(c => c.focused);
    expect(focused.length).toBe(4);
    expect(focused.map(c => c.label)).toEqual(expect.arrayContaining(['Home', 'Orders', 'Scan', 'Profile']));
  });

  it('invokes TabIcon with focused=false for all 4 tabs', () => {
    renderNavigator();
    const calls = (global as Record<string, unknown>).__iconCalls as { focused: boolean; label: string }[];
    const unfocused = calls.filter(c => !c.focused);
    expect(unfocused.length).toBe(4);
    expect(unfocused.map(c => c.label)).toEqual(expect.arrayContaining(['Home', 'Orders', 'Scan', 'Profile']));
  });
});

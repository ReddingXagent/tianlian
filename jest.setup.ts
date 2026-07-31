// Jest setup for tianlian-user-app
/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock工厂与setup需CJS require, 有意为之 */

// Global mock for axios to prevent actual HTTP calls in tests
jest.mock('axios', () => {
  const mockAxios = {
    create: jest.fn(() => ({
      get: jest.fn().mockResolvedValue({ data: {} }),
      post: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
      interceptors: {
        request: { use: jest.fn(), eject: jest.fn() },
        response: { use: jest.fn(), eject: jest.fn() },
      },
      defaults: { headers: {} },
    })),
    get: jest.fn().mockResolvedValue({ data: {} }),
    post: jest.fn().mockResolvedValue({ data: {} }),
    put: jest.fn().mockResolvedValue({ data: {} }),
    delete: jest.fn().mockResolvedValue({ data: {} }),
  };
  return mockAxios;
});

// Mock PlatformConstants for TurboModule compatibility
jest.mock('react-native/Libraries/Utilities/NativePlatformConstantsIOS', () => ({
  default: {
    getConstants: () => ({
      forceTouchAvailable: false,
      interfaceIdiom: 'phone',
      osVersion: '16.0',
      systemName: 'iOS',
      reactNativeVersion: { major: 0, minor: 76, patch: 6 },
    }),
  },
}), { virtual: true });

jest.mock('react-native/Libraries/Utilities/NativePlatformConstantsAndroid', () => ({
  default: {
    getConstants: () => ({
      Version: 33,
      Release: '13',
      Serial: 'unknown',
      Model: 'Pixel 6',
    }),
  },
}), { virtual: true });

// Mock react-native-safe-area-context
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  const SafeAreaProvider = ({ children }: { children: React.ReactNode }) =>
    React.createElement(View, null, children);
  const SafeAreaView = ({ children }: { children: React.ReactNode }) =>
    React.createElement(View, null, children);
  const useSafeAreaInsets = () => ({ top: 0, right: 0, bottom: 0, left: 0 });
  return {
    SafeAreaProvider,
    SafeAreaView,
    useSafeAreaInsets,
  };
});

// Mock @react-navigation/native
jest.mock('@react-navigation/native', () => {
  const React = require('react');
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: () => ({
      navigate: jest.fn(),
      goBack: jest.fn(),
      replace: jest.fn(),
      popToTop: jest.fn(),
      dispatch: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }),
    useRoute: () => ({
      params: {},
    }),
    NavigationContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
  };
});

// Mock @react-navigation/native-stack
jest.mock('@react-navigation/native-stack', () => ({
  createNativeStackNavigator: () => ({
    Navigator: ({ children }: { children: React.ReactNode }) => children,
    Screen: ({ children }: { children: React.ReactNode }) => children,
  }),
}));

// Mock @react-navigation/bottom-tabs
jest.mock('@react-navigation/bottom-tabs', () => ({
  createBottomTabNavigator: () => ({
    Navigator: ({ children }: { children: React.ReactNode }) => children,
    Screen: ({ children }: { children: React.ReactNode }) => children,
  }),
}));

// Mock react-native-screens
jest.mock('react-native-screens', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    Screen: ({ children }: { children: React.ReactNode }) =>
      React.createElement(View, null, children),
    ScreenContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(View, null, children),
    NativeScreen: ({ children }: { children: React.ReactNode }) =>
      React.createElement(View, null, children),
    enableScreens: jest.fn(),
    screensEnabled: jest.fn(() => true),
  };
});

// Mock react-native-svg
jest.mock('react-native-svg', () => {
  const React = require('react');
  const { View } = require('react-native');
  const createMock = (name: string) => {
    const Comp = (props: Record<string, unknown>) =>
      React.createElement(View, { ...props, testID: name });
    return Comp;
  };
  return {
    Svg: createMock('Svg'),
    Circle: createMock('Circle'),
    Ellipse: createMock('Ellipse'),
    G: createMock('G'),
    Line: createMock('Line'),
    Path: createMock('Path'),
    Polygon: createMock('Polygon'),
    Polyline: createMock('Polyline'),
    Rect: createMock('Rect'),
    Text: createMock('SvgText'),
    TSpan: createMock('TSpan'),
    Use: createMock('Use'),
    Defs: createMock('Defs'),
    LinearGradient: createMock('LinearGradient'),
    Stop: createMock('Stop'),
    RadialGradient: createMock('RadialGradient'),
    ClipPath: createMock('ClipPath'),
    Mask: createMock('Mask'),
    Image: createMock('Image'),
  };
});
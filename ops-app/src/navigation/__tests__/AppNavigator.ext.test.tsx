/**
 * AppNavigator 扩展测试 — 分支覆盖率提升
 * 目标: 67% → 85%+ branches
 */
import { render } from '@testing-library/react-native';
import React from 'react';

// Must use require to avoid hoisting issues
const mockAuth = {
  isAuthenticated: false,
  isLoading: false,
  checkAuth: jest.fn(),
};

// Mock the store
jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: typeof mockAuth) => unknown) => selector(mockAuth),
}));

// Mock NavigationContainer
jest.mock('@react-navigation/native', () => ({
  NavigationContainer: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock navigators — use require('react') inside factory
jest.mock('@react-navigation/native-stack', () => {
  const R = require('react');
  return {
    createNativeStackNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) => children,
      Screen: ({ component: Comp }: { component: React.FC }) => Comp ? R.createElement(Comp) : null,
      Group: ({ children }: { children: React.ReactNode }) => children,
    }),
  };
});

jest.mock('@react-navigation/bottom-tabs', () => {
  const R = require('react');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) => children,
      Screen: ({ component: Comp }: { component: React.FC }) => Comp ? R.createElement(Comp) : null,
    }),
  };
});

// Mock all screens with simple components
const makeScreen = (name: string) => {
  const R = require('react');
  return function MockScreen() {
    return R.createElement('Text', { testID: name.toLowerCase() }, name);
  };
};

jest.mock('../../screens/LoginScreen', () => makeScreen('Login'));
jest.mock('../../screens/WorkbenchScreen', () => makeScreen('Workbench'));
jest.mock('../../screens/WorkOrderListScreen', () => makeScreen('WOList'));
jest.mock('../../screens/WorkOrderDetailScreen', () => makeScreen('WODetail'));
jest.mock('../../screens/WorkOrderCreateScreen', () => makeScreen('WOCreate'));
jest.mock('../../screens/WorkOrderTransferScreen', () => makeScreen('WOTransfer'));
jest.mock('../../screens/ScanScreen', () => makeScreen('Scan'));
jest.mock('../../screens/MonitorScreen', () => makeScreen('Monitor'));
jest.mock('../../screens/InspectionListScreen', () => makeScreen('InspList'));
jest.mock('../../screens/InspectionDetailScreen', () => makeScreen('InspDetail'));
jest.mock('../../screens/DashboardScreen', () => makeScreen('Dashboard'));
jest.mock('../../screens/ProfileScreen', () => makeScreen('Profile'));
jest.mock('../../screens/DiagnosisScreen', () => makeScreen('Diag'));
jest.mock('../../screens/KnowledgeScreen', () => makeScreen('Knowledge'));
jest.mock('../../screens/KnowledgeDetailScreen', () => makeScreen('KnowDetail'));
jest.mock('../../screens/MerchantAuditListScreen', () => makeScreen('MerchantAuditList'));
jest.mock('../../screens/MerchantAuditDetailScreen', () => makeScreen('MerchantAuditDetail'));

import { AppNavigator } from '../AppNavigator';

describe('AppNavigator.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuth.isAuthenticated = false;
    mockAuth.isLoading = false;
  });

  it('renders loading state when isLoading=true', () => {
    mockAuth.isLoading = true;
    const { getByText } = render(<AppNavigator />);
    expect(getByText('加载中...')).toBeTruthy();
  });

  it('renders Auth (Login) when not authenticated', () => {
    mockAuth.isAuthenticated = false;
    mockAuth.isLoading = false;
    const { getByText } = render(<AppNavigator />);
    expect(getByText('Login')).toBeTruthy();
  });

  it('renders Main when authenticated', () => {
    mockAuth.isAuthenticated = true;
    mockAuth.isLoading = false;
    const { getByText } = render(<AppNavigator />);
    expect(getByText('Workbench')).toBeTruthy();
  });

  it('calls checkAuth on mount', () => {
    render(<AppNavigator />);
    expect(mockAuth.checkAuth).toHaveBeenCalled();
  });

  it('renders all tab screens when authenticated', () => {
    mockAuth.isAuthenticated = true;
    const { getByText } = render(<AppNavigator />);
    expect(getByText('Workbench')).toBeTruthy();
    expect(getByText('WOList')).toBeTruthy();
    expect(getByText('Scan')).toBeTruthy();
    expect(getByText('InspList')).toBeTruthy();
    expect(getByText('Monitor')).toBeTruthy();
    expect(getByText('Dashboard')).toBeTruthy();
    expect(getByText('Profile')).toBeTruthy();
  });
});

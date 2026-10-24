import React from 'react';
import { View, Text } from 'react-native';
import { render, waitFor } from '@testing-library/react-native';

// ── Mock dependencies ──────────────────────────────────────────────
// Capture children from navigation wrappers so mocked screen content bubbles up
const PassChildren = ({ children }: { children: React.ReactNode }) => <>{children}</>;

jest.mock('@react-navigation/native', () => {
  const Real = jest.requireActual('@react-navigation/native');
  return {
    ...Real,
    NavigationContainer: PassChildren,
  };
});

jest.mock('@react-navigation/native-stack', () => ({
  createNativeStackNavigator: () => ({
    Navigator: PassChildren,
    Screen: ({ component: Comp }: { component: React.FC }) => <Comp />,
  }),
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  createBottomTabNavigator: () => ({
    Navigator: PassChildren,
    Screen: ({ component: Comp }: { component: React.FC }) => <Comp />,
  }),
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

// Mock screens with identifiable text
const MockScreen = ({ name }: { name: string }) => (
  <View><Text>{name}</Text></View>
);
jest.mock('../../screens/LoginScreen', () => () => <MockScreen name="LoginScreen" />);
jest.mock('../../screens/WorkbenchScreen', () => () => <MockScreen name="WorkbenchScreen" />);
jest.mock('../../screens/WorkOrderListScreen', () => () => <MockScreen name="WorkOrderListScreen" />);
jest.mock('../../screens/WorkOrderDetailScreen', () => () => <MockScreen name="WorkOrderDetailScreen" />);
jest.mock('../../screens/WorkOrderCreateScreen', () => () => <MockScreen name="WorkOrderCreateScreen" />);
jest.mock('../../screens/WorkOrderTransferScreen', () => () => <MockScreen name="WorkOrderTransferScreen" />);
jest.mock('../../screens/ScanScreen', () => () => <MockScreen name="ScanScreen" />);
jest.mock('../../screens/MonitorScreen', () => () => <MockScreen name="MonitorScreen" />);
jest.mock('../../screens/InspectionListScreen', () => () => <MockScreen name="InspectionListScreen" />);
jest.mock('../../screens/InspectionDetailScreen', () => () => <MockScreen name="InspectionDetailScreen" />);
jest.mock('../../screens/DashboardScreen', () => () => <MockScreen name="DashboardScreen" />);
jest.mock('../../screens/ProfileScreen', () => () => <MockScreen name="ProfileScreen" />);
jest.mock('../../screens/DiagnosisScreen', () => () => <MockScreen name="DiagnosisScreen" />);
jest.mock('../../screens/KnowledgeScreen', () => () => <MockScreen name="KnowledgeScreen" />);
jest.mock('../../screens/KnowledgeDetailScreen', () => () => <MockScreen name="KnowledgeDetailScreen" />);
jest.mock('../../screens/MerchantAuditListScreen', () => () => <MockScreen name="MerchantAuditListScreen" />);
jest.mock('../../screens/MerchantAuditDetailScreen', () => () => <MockScreen name="MerchantAuditDetailScreen" />);

import { AppNavigator } from '../AppNavigator';
import { useAuthStore } from '../../store/authStore';
import type { AuthState } from '../../store/authStore';

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
// F1205: any收窄 — mock态用AuthState本体签名(逆变安全), 实参补齐缺省字段

describe('AppNavigator', () => {
  const mockCheckAuth = jest.fn();

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('renders loading indicator when isLoading is true', () => {
    mockedUseAuthStore.mockImplementation((selector: (state: AuthState) => unknown) => {
      return selector({
        token: null, user: null, isAuthenticated: false, isLoading: true,
        login: jest.fn(), logout: jest.fn(), checkAuth: mockCheckAuth, setUser: jest.fn(),
      });
    });

    const { getByText } = render(<AppNavigator />);
    expect(getByText('加载中...')).toBeTruthy();
  });

  it('renders Auth navigator (Login) when not authenticated', async () => {
    mockedUseAuthStore.mockImplementation((selector: (state: AuthState) => unknown) => {
      return selector({
        token: null, user: null, isAuthenticated: false, isLoading: false,
        login: jest.fn(), logout: jest.fn(), checkAuth: mockCheckAuth, setUser: jest.fn(),
      });
    });

    const { getByText } = render(<AppNavigator />);
    await waitFor(() => {
      expect(getByText('LoginScreen')).toBeTruthy();
    });
  });

  it('renders Main navigator (Workbench) when authenticated', async () => {
    mockedUseAuthStore.mockImplementation((selector: (state: AuthState) => unknown) => {
      return selector({
        token: null, user: null, isAuthenticated: true, isLoading: false,
        login: jest.fn(), logout: jest.fn(), checkAuth: mockCheckAuth, setUser: jest.fn(),
      });
    });

    const { getByText } = render(<AppNavigator />);
    await waitFor(() => {
      expect(getByText('WorkbenchScreen')).toBeTruthy();
    });
  });

  it('calls checkAuth on mount', () => {
    mockedUseAuthStore.mockImplementation((selector: (state: AuthState) => unknown) => {
      return selector({
        token: null, user: null, isAuthenticated: false, isLoading: true,
        login: jest.fn(), logout: jest.fn(), checkAuth: mockCheckAuth, setUser: jest.fn(),
      });
    });

    render(<AppNavigator />);
    expect(mockCheckAuth).toHaveBeenCalled();
  });
});

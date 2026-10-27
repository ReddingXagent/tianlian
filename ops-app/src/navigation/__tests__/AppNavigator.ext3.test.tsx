/**
 * AppNavigator ext3 — TabIcon focused=false branch via actual render
 * Fix: make bottom-tabs mock render tabBarIcon output to hit the opacity ternary
 */
import React from 'react';
import { Text } from 'react-native';
import { render } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  NavigationContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('@react-navigation/native-stack', () => {
  const R = require('react');
  return {
    createNativeStackNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) => R.createElement(R.Fragment, null, children),
      Screen: ({ component: Comp }: { component: React.FC }) => Comp ? R.createElement(Comp) : null,
    }),
  };
});

// Mock bottom-tabs to actually RENDER tabBarIcon output (covers TabIcon branches)
jest.mock('@react-navigation/bottom-tabs', () => {
  const R = require('react');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: { children: React.ReactNode }) => R.createElement(R.Fragment, null, children),
      Screen: ({ component: Comp, options }: { component: React.FC; options?: Record<string, unknown> }) => {
        // Render the icon output so TabIcon's JSX is actually evaluated
        let iconElements: React.ReactNode[] = [];
        if (options?.tabBarIcon) {
          // F1205: any收窄 — tabBarIcon实际类型为React.FC<TabIconProps的focused形态>
          const renderIcon = options.tabBarIcon as ({ focused }: { focused: boolean }) => React.ReactNode;
          try {
            iconElements.push(renderIcon({ focused: true }));
            iconElements.push(renderIcon({ focused: false }));
          } catch {
            // ignore
          }
        }
        return R.createElement(R.Fragment, null,
          ...(Comp ? [R.createElement(Comp)] : []),
          ...iconElements,
        );
      },
    }),
  };
});

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: { isAuthenticated: boolean; isLoading: boolean; checkAuth: jest.Mock }) => unknown) =>
    selector({
      isAuthenticated: true,
      isLoading: false,
      checkAuth: jest.fn(),
    }),
}));

// Mock screens as minimal stubs
const Stub: React.FC<{ name: string }> = ({ name }) => (
  <Text>{name}</Text>
);
jest.mock('../../screens/LoginScreen', () => () => <Stub name="Login" />);
jest.mock('../../screens/WorkbenchScreen', () => () => <Stub name="Workbench" />);
jest.mock('../../screens/WorkOrderListScreen', () => () => <Stub name="WOList" />);
jest.mock('../../screens/WorkOrderDetailScreen', () => () => <Stub name="WODetail" />);
jest.mock('../../screens/WorkOrderCreateScreen', () => () => <Stub name="WOCreate" />);
jest.mock('../../screens/WorkOrderTransferScreen', () => () => <Stub name="WOTransfer" />);
jest.mock('../../screens/ScanScreen', () => () => <Stub name="Scan" />);
jest.mock('../../screens/MonitorScreen', () => () => <Stub name="Monitor" />);
jest.mock('../../screens/InspectionListScreen', () => () => <Stub name="InspList" />);
jest.mock('../../screens/InspectionDetailScreen', () => () => <Stub name="InspDetail" />);
jest.mock('../../screens/DashboardScreen', () => () => <Stub name="Dashboard" />);
jest.mock('../../screens/ProfileScreen', () => () => <Stub name="Profile" />);
jest.mock('../../screens/DiagnosisScreen', () => () => <Stub name="Diag" />);
jest.mock('../../screens/KnowledgeScreen', () => () => <Stub name="Knowledge" />);
jest.mock('../../screens/KnowledgeDetailScreen', () => () => <Stub name="KnowDetail" />);
jest.mock('../../screens/MerchantAuditListScreen', () => () => <Stub name="MerchantAuditList" />);
jest.mock('../../screens/MerchantAuditDetailScreen', () => () => <Stub name="MerchantAuditDetail" />);

import { AppNavigator } from '../AppNavigator';

describe('AppNavigator.ext3 — TabIcon both branches via rendered output', () => {
  it('renders all tab icons covering focused=true AND focused=false', () => {
    const { getAllByText } = render(<AppNavigator />);
    // Tab icons render twice each (focused=true + focused=false)
    // Verify both renders for each emoji
    expect(getAllByText('🔧')).toHaveLength(2);
    expect(getAllByText('📋')).toHaveLength(2);
    expect(getAllByText('📷')).toHaveLength(2);
    expect(getAllByText('🔍')).toHaveLength(2);
    expect(getAllByText('📊')).toHaveLength(2);
    expect(getAllByText('📈')).toHaveLength(2);
    expect(getAllByText('👤')).toHaveLength(2);
  });
});

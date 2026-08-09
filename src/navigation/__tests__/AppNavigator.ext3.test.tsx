/**
 * AppNavigator ext3 — TabIcon focused=false branch via actual render
 * Fix: make bottom-tabs mock render tabBarIcon output to hit the opacity ternary
 */
import React from 'react';
import { Text } from 'react-native';
import { render } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  NavigationContainer: ({ children }: any) => <>{children}</>,
}));

jest.mock('@react-navigation/native-stack', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require('react');
  return {
    createNativeStackNavigator: () => ({
      Navigator: ({ children }: any) => R.createElement(R.Fragment, null, children),
      Screen: ({ component: Comp }: any) => Comp ? R.createElement(Comp) : null,
    }),
  };
});

// Mock bottom-tabs to actually RENDER tabBarIcon output (covers TabIcon branches)
jest.mock('@react-navigation/bottom-tabs', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require('react');
  return {
    createBottomTabNavigator: () => ({
      Navigator: ({ children }: any) => R.createElement(R.Fragment, null, children),
      Screen: ({ component: Comp, options }: any) => {
        // Render the icon output so TabIcon's JSX is actually evaluated
        let iconElements: any[] = [];
        if (options?.tabBarIcon) {
          try {
            iconElements.push(options.tabBarIcon({ focused: true }));
            iconElements.push(options.tabBarIcon({ focused: false }));
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
  useAuthStore: (selector: (s: any) => any) =>
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

/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { render } from '@testing-library/react-native';
import { AppNavigator } from '../AppNavigator';

// ---- authStore mock: 组件用selector调用 useAuthStore((s)=>...), mock需支持selector ----
let mockAuthState = {
  isAuthenticated: false,
  isLoading: false,
};
const mockCheckAuth = jest.fn();
jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: typeof mockAuthState & { checkAuth: jest.Mock }) => unknown) =>
    selector({ ...mockAuthState, checkAuth: mockCheckAuth }),
}));

// ---- 全部屏幕mock为纯文本占位, 避免真实屏幕触发API/导航副作用 ----
// (jest.mock工厂被hoisting, 工厂内require勿引用顶层import)
jest.mock('../../screens/LoginScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'login-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/DashboardScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'dashboard-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/StationListScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'stationlist-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/StationDetailScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'stationdetail-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/RevenueScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'revenue-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/ProfileScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'profile-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/ChargerMonitorScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'chargermonitor-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/AlarmListScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'alarmlist-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/NotificationCenterScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'notificationcenter-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/DeviceListScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'devicelist-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/DeviceDetailScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'devicedetail-screen');
  };
  return { __esModule: true, default: M };
});
jest.mock('../../screens/WorkOrderScreen', () => {
  const M = () => {
    const R = require('react');
    const { Text } = require('react-native');
    return R.createElement(Text, null, 'workorder-screen');
  };
  return { __esModule: true, default: M };
});

describe('AppNavigator', () => {
  beforeEach(() => {
    mockAuthState = { isAuthenticated: false, isLoading: false };
    mockCheckAuth.mockClear();
  });

  it('挂载时调用checkAuth', () => {
    render(<AppNavigator />);
    expect(mockCheckAuth).toHaveBeenCalledTimes(1);
  });

  it('isLoading时渲染加载态而非导航', () => {
    mockAuthState = { isAuthenticated: false, isLoading: true };
    const { getByText, queryByText } = render(<AppNavigator />);
    expect(getByText('加载中...')).toBeTruthy();
    expect(queryByText('login-screen')).toBeNull();
    expect(queryByText('dashboard-screen')).toBeNull();
  });

  it('未认证时进入Auth栈渲染LoginScreen', () => {
    mockAuthState = { isAuthenticated: false, isLoading: false };
    const { getByText, queryByText } = render(<AppNavigator />);
    expect(getByText('login-screen')).toBeTruthy();
    expect(queryByText('dashboard-screen')).toBeNull();
  });

  it('已认证时进入Main栈: 四Tab标签齐备且默认渲染Dashboard', () => {
    mockAuthState = { isAuthenticated: true, isLoading: false };
    const { getByText, getAllByText } = render(<AppNavigator />);
    expect(getByText('dashboard-screen')).toBeTruthy();
    // header title与tabBarLabel同名双匹配, getAllByText容忍
    for (const label of ['首页', '站点', '营收', '我的']) {
      expect(getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
  });
});

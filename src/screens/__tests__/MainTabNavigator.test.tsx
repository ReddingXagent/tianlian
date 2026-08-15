import React from 'react';
import { render } from '@testing-library/react-native';
import { NavigationContainer } from '@react-navigation/native';
import MainTabNavigator from '../MainTabNavigator';

// Mock四个Tab页为纯文本占位, 避免真实屏幕触发API/导航副作用
// (jest.mock工厂被hoisting, 内部用require避免TDZ)
// 注: AI 助手 Tab 已移除(云端 /ai/chat 下线, 2026-08-15), 恢复时需同步加回 mock 与断言
jest.mock('../DashboardScreen', () => {
  const MockDashboard = () => {
  const React = require('react');
  const { Text } = require('react-native');
  return React.createElement(Text, null, 'dashboard-screen');
  };
  return MockDashboard;
});
jest.mock('../StationListScreen', () => {
  const MockStationList = () => {
  const React = require('react');
  const { Text } = require('react-native');
  return React.createElement(Text, null, 'station-screen');
  };
  return MockStationList;
});
jest.mock('../RevenueScreen', () => {
  const MockRevenue = () => {
  const React = require('react');
  const { Text } = require('react-native');
  return React.createElement(Text, null, 'revenue-screen');
  };
  return MockRevenue;
});
jest.mock('../ProfileScreen', () => {
  const MockProfile = () => {
  const React = require('react');
  const { Text } = require('react-native');
  return React.createElement(Text, null, 'profile-screen');
  };
  return MockProfile;
});

describe('MainTabNavigator', () => {
  it('渲染四个Tab且中文标签齐备(AI 助手已暂时移除)', () => {
    const { getAllByText, queryByText } = render(
      <NavigationContainer>
        <MainTabNavigator />
      </NavigationContainer>
    );
    // header title与tabBarLabel同名, 用getAllByText容忍多匹配
    for (const label of ['首页', '站点', '营收', '我的']) {
      expect(getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
    // AI 助手入口已移除, 不应出现
    expect(queryByText('AI 助手')).toBeNull();
  });

  it('默认落在首页Tab(dashboard屏渲染)', () => {
    const { getByText } = render(
      <NavigationContainer>
        <MainTabNavigator />
      </NavigationContainer>
    );
    expect(getByText('dashboard-screen')).toBeTruthy();
  });
});

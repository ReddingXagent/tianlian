import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { MainTabParamList } from '../types';
import DashboardScreen from './DashboardScreen';
import StationListScreen from './StationListScreen';
import RevenueScreen from './RevenueScreen';
// AI 助手 Tab: 云端 /ai/chat 端点已下线, 新 /chat 端点已适配(2026-08-20).
// 当前AI降级模式(answer="对话服务暂时不可用"), 上线后即可正常使用.
import ProfileScreen from './ProfileScreen';
import { useTheme } from '../hooks/useTheme';

const Tab = createBottomTabNavigator<MainTabParamList>();

export default function MainTabNavigator() {
  const { colors } = useTheme();
  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.cardBg },
        headerTintColor: colors.textPrimary,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: { backgroundColor: colors.cardBg, borderTopColor: colors.border },
      }}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{ title: '首页', tabBarLabel: '首页' }}
      />
      <Tab.Screen
        name="Stations"
        component={StationListScreen}
        options={{ title: '站点', tabBarLabel: '站点' }}
      />
      <Tab.Screen
        name="Revenue"
        component={RevenueScreen}
        options={{ title: '营收', tabBarLabel: '营收' }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{ title: '我的', tabBarLabel: '我的' }}
      />
    </Tab.Navigator>
  );
}

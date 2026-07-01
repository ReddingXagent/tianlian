import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { MainTabParamList } from '../types';
import DashboardScreen from './DashboardScreen';
import StationListScreen from './StationListScreen';
import RevenueScreen from './RevenueScreen';
import ProfileScreen from './ProfileScreen';

const Tab = createBottomTabNavigator<MainTabParamList>();

export default function MainTabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#1a1a2e' },
        headerTintColor: '#fff',
        tabBarActiveTintColor: '#4ECDC4',
        tabBarInactiveTintColor: '#666',
        tabBarStyle: { backgroundColor: '#1a1a2e', borderTopColor: '#333' },
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

import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { RootStackParamList, AuthStackParamList, MainTabParamList } from '../types';
import LoginScreen from '../screens/LoginScreen';
import DashboardScreen from '../screens/DashboardScreen';
import StationListScreen from '../screens/StationListScreen';
import StationDetailScreen from '../screens/StationDetailScreen';
import RevenueScreen from '../screens/RevenueScreen';
import ProfileScreen from '../screens/ProfileScreen';
import ChargerMonitorScreen from '../screens/ChargerMonitorScreen';
import AlarmListScreen from '../screens/AlarmListScreen';
import NotificationCenterScreen from '../screens/NotificationCenterScreen';
import DeviceListScreen from '../screens/DeviceListScreen';
import DeviceDetailScreen from '../screens/DeviceDetailScreen';
import WorkOrderScreen from '../screens/WorkOrderScreen';
import MerchantKYCScreen from '../screens/MerchantKYCScreen';
import { useTheme } from '../hooks/useTheme';

const RootStack = createNativeStackNavigator<RootStackParamList>();
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

// Tab 图标组件（纯文字方案，不依赖图标库）
const TabIcon: React.FC<{ label: string; focused: boolean }> = ({ label, focused }) => (
  <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{label}</Text>
);

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
    </AuthStack.Navigator>
  );
}

function MainNavigator() {
  const { colors } = useTheme();
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: {
          height: 56,
          paddingBottom: 6,
          paddingTop: 4,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '500',
        },
        headerStyle: {
          backgroundColor: colors.primary,
        },
        headerTintColor: colors.onPrimary,
        headerTitleStyle: {
          fontWeight: '600',
        },
      }}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          title: '首页',
          tabBarLabel: '首页',
          tabBarIcon: ({ focused }) => <TabIcon label="🏠" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Stations"
        component={StationListScreen}
        options={{
          title: '站点列表',
          tabBarLabel: '站点',
          tabBarIcon: ({ focused }) => <TabIcon label="📡" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Revenue"
        component={RevenueScreen}
        options={{
          title: '营收统计',
          tabBarLabel: '营收',
          tabBarIcon: ({ focused }) => <TabIcon label="💰" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{
          title: '我的',
          tabBarLabel: '我的',
          tabBarIcon: ({ focused }) => <TabIcon label="👤" focused={focused} />,
        }}
      />
    </Tab.Navigator>
  );
}

export const AppNavigator: React.FC = () => {
  const { colors } = useTheme();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const checkAuth = useAuthStore((s) => s.checkAuth);

  React.useEffect(() => {
    checkAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (isLoading) {
    return (
      <View style={[styles.loadingContainer, { backgroundColor: colors.pageBg }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[styles.loadingText, { color: colors.textSecondary }]}>加载中...</Text>
      </View>
    );
  }

  return (
    <NavigationContainer>
      <RootStack.Navigator screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <RootStack.Screen name="Main" component={MainTabNavigatorWithDetail} />
        ) : (
          <RootStack.Screen name="Auth" component={AuthNavigator} />
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
};

// 在 RootStack 中包裹 Main + 详情页面
function MainTabNavigatorWithDetail() {
  const { colors } = useTheme();
  return (
    <RootStack.Navigator>
      <RootStack.Screen name="Main" component={MainNavigator} options={{ headerShown: false }} />
      <RootStack.Screen
        name="StationDetail"
        component={StationDetailScreen}
        options={{
          title: '站点详情',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="ChargerMonitor"
        component={ChargerMonitorScreen}
        options={({ route }) => ({
          title: `充电桩监控`,
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        })}
      />
      <RootStack.Screen
        name="AlarmList"
        component={AlarmListScreen}
        options={{
          title: '告警列表',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="NotificationCenter"
        component={NotificationCenterScreen}
        options={{
          title: '消息中心',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="MerchantKYC"
        component={MerchantKYCScreen}
        options={{
          title: '商户进件',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="DeviceList"
        component={DeviceListScreen}
        options={({ route }) => ({
          title: `${route.params?.stationName || ''} - 设备列表`,
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        })}
      />
      <RootStack.Screen
        name="DeviceDetail"
        component={DeviceDetailScreen}
        options={{
          title: '设备详情',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="WorkOrder"
        component={WorkOrderScreen}
        options={{
          title: '工单管理',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
    </RootStack.Navigator>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
  },
});
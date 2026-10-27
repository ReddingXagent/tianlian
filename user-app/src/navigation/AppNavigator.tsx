import React from 'react';
import { NavigationContainer, useNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { ErrorBoundary } from '../components/ErrorBoundary';
import OfflineBanner from '../components/OfflineBanner';
import { useAndroidBackExit } from '../hooks/useAndroidBackExit';
import { useTheme } from '../hooks/useTheme';
import { RootStackParamList, AuthStackParamList, MainTabParamList } from '../types';
import LoginScreen from '../screens/LoginScreen';
import HomeScreen from '../screens/HomeScreen';
import StationDetailScreen from '../screens/StationDetailScreen';
import OrderListScreen from '../screens/OrderListScreen';
import ScanScreen from '../screens/ScanScreen';
import ProfileScreen from '../screens/ProfileScreen';
import ChargingScreen from '../screens/ChargingScreen';
import OrderDetailScreen from '../screens/OrderDetailScreen';
import PaymentScreen from '../screens/PaymentScreen';
import VehicleScreen from '../screens/VehicleScreen';
import WalletScreen from '../screens/WalletScreen';
import CouponScreen from '../screens/CouponScreen';
import EnergyScreen from '../screens/EnergyScreen';

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

// Android 硬件返回键治理: 非 Home tab 先回 Home, Home 双击退出, 详情页不拦截
function TabBackHandler() {
  const navigation = useNavigation();
  useAndroidBackExit(navigation);
  return null;
}

function MainTabs() {
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
          backgroundColor: colors.cardBg,
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
        name="Home"
        component={HomeScreen}
        options={{
          title: '首页',
          tabBarLabel: '首页',
          tabBarIcon: ({ focused }) => <TabIcon label="🏠" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Orders"
        component={OrderListScreen}
        options={{
          title: '充电记录',
          tabBarLabel: '订单',
          tabBarIcon: ({ focused }) => <TabIcon label="📋" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Scan"
        component={ScanScreen}
        options={{
          title: '扫码充电',
          tabBarLabel: '扫码',
          tabBarIcon: ({ focused }) => <TabIcon label="📷" focused={focused} />,
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
      {/* 非 Screen 子元素, navigator 原样渲染 — 挂硬件返回键监听 */}
      <TabBackHandler />
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
  }, [checkAuth]);

  if (isLoading) {
    return (
      <View style={[styles.loadingContainer, { backgroundColor: colors.pageBg }]}>
        <ActivityIndicator size={"large"} color={colors.primary} />
        <Text style={[styles.loadingText, { color: colors.textSecondary }]}>加载中...</Text>
      </View>
    );
  }

  // F228: OfflineBanner此前有实现有测试但零挂载=死代码, 离线时用户看陈旧数据无视觉告知。
  // 挂根级(flex容器顶部)覆盖Auth(登录需网)与Main全部页面。
  return (
    <ErrorBoundary>
      <View style={styles.appRoot}>
        <OfflineBanner />
        <NavigationContainer>
          <RootStack.Navigator screenOptions={{ headerShown: false }}>
            {isAuthenticated ? (
              <RootStack.Screen name="Main" component={MainWithDetail} />
            ) : (
              <RootStack.Screen name="Auth" component={AuthNavigator} />
            )}
          </RootStack.Navigator>
        </NavigationContainer>
      </View>
    </ErrorBoundary>
  );
};

// 在 RootStack 中包裹 Main + 详情页面
function MainWithDetail() {
  const { colors } = useTheme();
  return (
    <RootStack.Navigator>
      <RootStack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
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
        name="Charging"
        component={ChargingScreen}
        options={{
          title: '充电中',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
          headerLeft: () => null, // 充电中禁止返回
          gestureEnabled: false,
        }}
      />
      <RootStack.Screen
        name="OrderDetail"
        component={OrderDetailScreen}
        options={{
          title: '订单详情',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Payment"
        component={PaymentScreen}
        options={{
          title: '支付',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Vehicle"
        component={VehicleScreen}
        options={{
          title: '车辆管理',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Wallet"
        component={WalletScreen}
        options={{
          title: '我的钱包',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Coupon"
        component={CouponScreen}
        options={{
          title: '我的优惠券',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Energy"
        component={EnergyScreen}
        options={{
          title: '能源概览',
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: colors.onPrimary,
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
    </RootStack.Navigator>
  );
}

const styles = StyleSheet.create({
  appRoot: {
    flex: 1,
  },
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
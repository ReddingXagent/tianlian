import React from 'react';
import { View } from 'react-native';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from './src/store/authStore';
import { RootStackParamList } from './src/types';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import StationDetailScreen from './src/screens/StationDetailScreen';
import DeviceListScreen from './src/screens/DeviceListScreen';
import AlarmListScreen from './src/screens/AlarmListScreen';
import WorkOrderScreen from './src/screens/WorkOrderScreen';
import MainTabNavigator from './src/screens/MainTabNavigator';
import ErrorBoundary from './src/components/ErrorBoundary';
import NetworkStatus from './src/components/NetworkStatus';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  const { isAuthenticated, isLoading, checkAuth } = useAuthStore();

  React.useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (isLoading) {
    // SplashScreen 由 expo 处理
    return null;
  }

  return (
    <SafeAreaProvider>
      <ErrorBoundary>
        <View style={{ flex: 1 }}>
          <NetworkStatus />
          <NavigationContainer theme={DarkTheme}>
            <StatusBar style="light" />
        <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: '#1a1a2e' }, headerTintColor: '#fff' }}>
          {isAuthenticated ? (
            <>
              <Stack.Screen name="Main" component={MainTabNavigator} options={{ headerShown: false }} />
              <Stack.Screen
                name="StationDetail"
                component={StationDetailScreen}
                options={({ route }) => ({ title: `站点详情` })}
              />
              <Stack.Screen
                name="DeviceList"
                component={DeviceListScreen}
                options={({ route }) => ({ title: route.params.stationName || '设备列表' })}
              />
              <Stack.Screen name="AlarmList" component={AlarmListScreen} options={{ title: '告警列表' }} />
              <Stack.Screen name="WorkOrder" component={WorkOrderScreen} options={{ title: '工单管理' }} />
            </>
          ) : (
            <Stack.Screen name="Auth" component={LoginScreen} options={{ headerShown: false }} />
          )}
          </Stack.Navigator>
          </NavigationContainer>
        </View>
      </ErrorBoundary>
    </SafeAreaProvider>
  );
}

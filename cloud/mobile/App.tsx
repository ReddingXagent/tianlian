import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { OfflineProvider } from './src/store/OfflineContext';
import { NetworkStatus } from './src/components/NetworkStatus';
import LoginScreen from './src/screens/LoginScreen';
import HomeScreen from './src/screens/HomeScreen';
import StationsScreen from './src/screens/StationsScreen';
import DevicesScreen from './src/screens/DevicesScreen';
import WorkOrdersScreen from './src/screens/WorkOrdersScreen';
import AlarmsScreen from './src/screens/AlarmsScreen';
import StationDetailScreen from './src/screens/StationDetailScreen';
import DeviceDetailScreen from './src/screens/DeviceDetailScreen';
import WorkOrderDetailScreen from './src/screens/WorkOrderDetailScreen';
import EvaluationScreen from './src/screens/EvaluationScreen';
import ProfileScreen from './src/screens/ProfileScreen';

export type RootStackParamList = {
  Login: undefined;
  Home: undefined;
  Stations: undefined;
  Devices: undefined;
  WorkOrders: { deviceId?: string; deviceName?: string } | undefined;
  Alarms: undefined;
  StationDetail: { stationId: string };
  DeviceDetail: { deviceId: string };
  WorkOrderDetail: { workOrderId: string };
  Evaluation: undefined;
  Profile: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <OfflineProvider>
      <NavigationContainer>
        <NetworkStatus />
        <Stack.Navigator initialRouteName="Login">
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
          <Stack.Screen name="Home" component={HomeScreen} options={{ title: '天链运维' }} />
          <Stack.Screen name="Stations" component={StationsScreen} options={{ title: '站点管理' }} />
          <Stack.Screen name="Devices" component={DevicesScreen} options={{ title: '设备管理' }} />
          <Stack.Screen name="WorkOrders" component={WorkOrdersScreen} options={{ title: '工单管理' }} />
          <Stack.Screen name="Alarms" component={AlarmsScreen} options={{ title: '告警中心' }} />
          <Stack.Screen name="StationDetail" component={StationDetailScreen} options={{ title: '站点详情' }} />
          <Stack.Screen name="DeviceDetail" component={DeviceDetailScreen} options={{ title: '设备详情' }} />
          <Stack.Screen name="WorkOrderDetail" component={WorkOrderDetailScreen} options={{ title: '工单详情' }} />
          <Stack.Screen name="Evaluation" component={EvaluationScreen} options={{ title: '运维评价' }} />
          <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: '我的' }} />
        </Stack.Navigator>
        <StatusBar style="auto" />
      </NavigationContainer>
    </OfflineProvider>
  );
}
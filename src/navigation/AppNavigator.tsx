import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuthStore } from '../store/authStore';
import {
  RootStackParamList,
  AuthStackParamList,
  MainTabParamList,
} from '../types';
import LoginScreen from '../screens/LoginScreen';
import WorkbenchScreen from '../screens/WorkbenchScreen';
import WorkOrderListScreen from '../screens/WorkOrderListScreen';
import WorkOrderDetailScreen from '../screens/WorkOrderDetailScreen';
import WorkOrderCreateScreen from '../screens/WorkOrderCreateScreen';
import WorkOrderTransferScreen from '../screens/WorkOrderTransferScreen';
import ScanScreen from '../screens/ScanScreen';
import MonitorScreen from '../screens/MonitorScreen';
import InspectionListScreen from '../screens/InspectionListScreen';
import InspectionDetailScreen from '../screens/InspectionDetailScreen';
import DashboardScreen from '../screens/DashboardScreen';
import ProfileScreen from '../screens/ProfileScreen';
import DiagnosisScreen from '../screens/DiagnosisScreen';
import KnowledgeScreen from '../screens/KnowledgeScreen';
import KnowledgeDetailScreen from '../screens/KnowledgeDetailScreen';

const RootStack = createNativeStackNavigator<RootStackParamList>();
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

// Tab 图标组件（纯文字方案，不依赖图标库）
const TabIcon: React.FC<{ label: string; focused: boolean }> = ({
  label,
  focused,
}) => (
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
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: '#1a73e8',
        tabBarInactiveTintColor: '#999',
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
          backgroundColor: '#1a73e8',
        },
        headerTintColor: '#fff',
        headerTitleStyle: {
          fontWeight: '600',
        },
      }}
    >
      <Tab.Screen
        name="Workbench"
        component={WorkbenchScreen}
        options={{
          title: '工作台',
          tabBarLabel: '工作台',
          tabBarIcon: ({ focused }) => <TabIcon label="🔧" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="WorkOrders"
        component={WorkOrderListScreen}
        options={{
          title: '工单管理',
          tabBarLabel: '工单',
          tabBarIcon: ({ focused }) => <TabIcon label="📋" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Scan"
        component={ScanScreen}
        options={{
          title: '扫码',
          tabBarLabel: '扫码',
          tabBarIcon: ({ focused }) => <TabIcon label="📷" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Inspection"
        component={InspectionListScreen}
        options={{
          title: '设备巡检',
          tabBarLabel: '巡检',
          tabBarIcon: ({ focused }) => <TabIcon label="🔍" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Monitor"
        component={MonitorScreen}
        options={{
          title: '设备监控',
          tabBarLabel: '监控',
          tabBarIcon: ({ focused }) => <TabIcon label="📊" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          title: '数据看板',
          tabBarLabel: '看板',
          tabBarIcon: ({ focused }) => <TabIcon label="📈" focused={focused} />,
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
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const checkAuth = useAuthStore((s) => s.checkAuth);

  React.useEffect(() => {
    checkAuth();
  }, []);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#1a73e8" />
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  return (
    <NavigationContainer>
      <RootStack.Navigator screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <RootStack.Screen
            name="Main"
            component={MainTabNavigatorWithDetail}
          />
        ) : (
          <RootStack.Screen name="Auth" component={AuthNavigator} />
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
};

// 在 RootStack 中包裹 Main + 详情页
function MainTabNavigatorWithDetail() {
  return (
    <RootStack.Navigator>
      <RootStack.Screen
        name="Main"
        component={MainNavigator}
        options={{ headerShown: false }}
      />
      <RootStack.Screen
        name="WorkOrderDetail"
        component={WorkOrderDetailScreen}
        options={{
          title: '工单详情',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="WorkOrderCreate"
        component={WorkOrderCreateScreen}
        options={{
          title: '创建工单',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="WorkOrderTransfer"
        component={WorkOrderTransferScreen}
        options={{
          title: '工单流转',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="InspectionDetail"
        component={InspectionDetailScreen}
        options={{
          title: '巡检详情',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Diagnosis"
        component={DiagnosisScreen}
        options={{
          title: '故障诊断',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="Knowledge"
        component={KnowledgeScreen}
        options={{
          title: '知识库',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
        }}
      />
      <RootStack.Screen
        name="KnowledgeDetail"
        component={KnowledgeDetailScreen}
        options={{
          title: '文章详情',
          headerStyle: { backgroundColor: '#1a73e8' },
          headerTintColor: '#fff',
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
    backgroundColor: '#fff',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#666',
  },
});
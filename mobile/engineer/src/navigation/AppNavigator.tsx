import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text } from 'react-native';

// 页面导入
import LoginScreen from '../screens/LoginScreen';
import WorkbenchScreen from '../screens/WorkbenchScreen';
import WorkOrderDetailScreen from '../screens/WorkOrderDetailScreen';
import KnowledgeScreen from '../screens/KnowledgeScreen';
import ProfileScreen from '../screens/ProfileScreen';
import V2GDiagnosisScreen from '../screens/V2GDiagnosisScreen';
import V2GDispatchScreen from '../screens/V2GDispatchScreen';
import EfficiencyToolScreen from '../screens/EfficiencyToolScreen';

// 类型定义
export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
  WorkOrderDetail: { workOrderId: string };
  V2GDiagnosis: undefined;
  V2GDispatch: undefined;
  EfficiencyTool: undefined;
};

export type MainTabParamList = {
  Workbench: undefined;
  Knowledge: undefined;
  Profile: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

// 底部导航栏图标组件
const TabBarIcon = ({ name, focused }: { name: string; focused: boolean }) => {
  const icons: Record<string, string> = {
    Workbench: '📋',
    Knowledge: '📚',
    Profile: '👤',
  };
  
  return (
    <Text style={{ fontSize: 20 }}>
      {icons[name] || '📄'}
    </Text>
  );
};

// 主页底部导航
const MainTabs = () => {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused }) => (
          <TabBarIcon name={route.name} focused={focused} />
        ),
        tabBarActiveTintColor: '#1890ff',
        tabBarInactiveTintColor: '#999',
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopWidth: 1,
          borderTopColor: '#f0f0f0',
          height: 60,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: {
          fontSize: 12,
        },
        headerShown: false,
      })}
    >
      <Tab.Screen 
        name="Workbench" 
        component={WorkbenchScreen}
        options={{ tabBarLabel: '工作台' }}
      />
      <Tab.Screen 
        name="Knowledge" 
        component={KnowledgeScreen}
        options={{ tabBarLabel: '知识库' }}
      />
      <Tab.Screen 
        name="Profile" 
        component={ProfileScreen}
        options={{ tabBarLabel: '我的' }}
      />
    </Tab.Navigator>
  );
};

// 根导航
const AppNavigator = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator 
        initialRouteName="Login"
        screenOptions={{
          headerStyle: {
            backgroundColor: '#1a1a2e',
          },
          headerTintColor: '#fff',
          headerTitleStyle: {
            fontWeight: 'bold',
          },
        }}
      >
        <Stack.Screen 
          name="Login" 
          component={LoginScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen 
          name="Main" 
          component={MainTabs}
          options={{ headerShown: false }}
        />
        <Stack.Screen 
          name="WorkOrderDetail" 
          component={WorkOrderDetailScreen}
          options={{ title: '工单详情' }}
        />
        <Stack.Screen 
          name="V2GDiagnosis" 
          component={V2GDiagnosisScreen}
          options={{ title: 'V2G设备诊断' }}
        />
        <Stack.Screen 
          name="V2GDispatch" 
          component={V2GDispatchScreen}
          options={{ title: 'V2G调度响应' }}
        />
        <Stack.Screen 
          name="EfficiencyTool" 
          component={EfficiencyToolScreen}
          options={{ title: '效率检测工具' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default AppNavigator;
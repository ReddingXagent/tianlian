import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Alert,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { CompositeScreenProps } from '@react-navigation/native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { RootStackParamList, MainTabParamList } from '../navigation/AppNavigator';
import { workOrderApi } from '../services/api';
import type { WorkOrder, WorkStats, UrgencyLevel } from '../types';

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, 'Workbench'>,
  NativeStackScreenProps<RootStackParamList>
>;

const WorkbenchScreen: React.FC<Props> = ({ navigation }) => {
  const [stats, setStats] = useState<WorkStats | null>(null);
  const [pendingList, setPendingList] = useState<WorkOrder[]>([]);
  const [processingList, setProcessingList] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'pending' | 'processing'>('pending');

  // 加载数据
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, pendingData, processingData] = await Promise.all([
        workOrderApi.getStats(),
        workOrderApi.getPendingList(),
        workOrderApi.getProcessingList(),
      ]);
      setStats(statsData);
      setPendingList(pendingData);
      setProcessingList(processingData);
    } catch (error: any) {
      console.error('Load data error:', error);
      // 使用模拟数据作为演示
      setStats({
        todayPending: 5,
        todayProcessing: 3,
        todayCompleted: 8,
        monthTotal: 45,
        avgRating: 4.8,
        avgResponseTime: 35,
      });
      setPendingList(getMockPendingData());
      setProcessingList(getMockProcessingData());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 模拟数据
  const getMockPendingData = (): WorkOrder[] => [
    {
      id: '1',
      orderNo: 'WO20260515001',
      status: 'pending',
      urgency: 'high',
      deviceId: 'D001',
      deviceName: '充电桩A03',
      stationId: 'S001',
      stationName: '朝阳充电站',
      stationAddress: '朝阳区朝阳路88号',
      faultDescription: '充电枪无法连接，显示屏无响应',
      createdAt: '2026-05-15 10:30',
      contactPhone: '138****1234',
    },
    {
      id: '2',
      orderNo: 'WO20260515002',
      status: 'pending',
      urgency: 'medium',
      deviceId: 'D002',
      deviceName: '储能柜B05',
      stationId: 'S002',
      stationName: '海淀储能站',
      stationAddress: '海淀区中关村大街66号',
      faultDescription: '储能柜温度异常，显示告警',
      createdAt: '2026-05-15 09:15',
      contactPhone: '139****5678',
    },
  ];

  const getMockProcessingData = (): WorkOrder[] => [
    {
      id: '3',
      orderNo: 'WO20260514003',
      status: 'processing',
      urgency: 'low',
      deviceId: 'D003',
      deviceName: '光伏逆变器C02',
      stationId: 'S003',
      stationName: '昌平光伏站',
      stationAddress: '昌平区科技园区路12号',
      faultDescription: '逆变器效率下降，需检修',
      createdAt: '2026-05-14 14:00',
      acceptedAt: '2026-05-14 14:30',
      arrivedAt: '2026-05-14 16:00',
      engineerId: 'E001',
      engineerName: '张工',
      contactPhone: '137****9012',
    },
  ];

  // 接单
  const handleAccept = async (workOrder: WorkOrder) => {
    Alert.alert(
      '确认接单',
      `确定接受工单 ${workOrder.orderNo} 吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定',
          onPress: async () => {
            try {
              await workOrderApi.accept(workOrder.id);
              Alert.alert('成功', '接单成功');
              loadData();
            } catch (error: any) {
              Alert.alert('接单失败', error.response?.data?.message || '请稍后重试');
            }
          },
        },
      ]
    );
  };

  // 转单
  const handleTransfer = (workOrder: WorkOrder) => {
    Alert.alert(
      '转单申请',
      '请联系客服进行转单操作',
      [
        { text: '取消', style: 'cancel' },
        { text: '拨打客服', onPress: () => {} },
      ]
    );
  };

  // 获取紧急程度标签样式
  const getUrgencyStyle = (urgency: UrgencyLevel) => {
    switch (urgency) {
      case 'high':
        return { color: '#ff4d4f', label: '紧急' };
      case 'medium':
        return { color: '#faad14', label: '一般' };
      case 'low':
        return { color: '#52c41a', label: '低' };
      default:
        return { color: '#999', label: '未知' };
    }
  };

  // 工单卡片
  const WorkOrderCard = ({ item, type }: { item: WorkOrder; type: 'pending' | 'processing' }) => {
    const urgency = getUrgencyStyle(item.urgency);
    
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate('WorkOrderDetail', { workOrderId: item.id })}
      >
        <View style={styles.cardHeader}>
          <View style={[styles.urgencyTag, { backgroundColor: urgency.color }]}>
            <Text style={styles.urgencyText}>{urgency.label}</Text>
          </View>
          <Text style={styles.orderNo}>{item.orderNo}</Text>
        </View>
        
        <View style={styles.cardBody}>
          <Text style={styles.deviceName}>{item.deviceName}</Text>
          <Text style={styles.stationName}>📍 {item.stationName}</Text>
          <Text style={styles.faultDesc}>{item.faultDescription}</Text>
        </View>
        
        <View style={styles.cardFooter}>
          <Text style={styles.timeText}>派单时间: {item.createdAt}</Text>
          {type === 'pending' ? (
            <View style={styles.actionRow}>
              <TouchableOpacity
                style={[styles.actionButton, styles.acceptButton]}
                onPress={() => handleAccept(item)}
              >
                <Text style={styles.actionButtonText}>接单</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.transferButton]}
                onPress={() => handleTransfer(item)}
              >
                <Text style={styles.actionButtonText}>转单</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.actionRow}>
              <TouchableOpacity
                style={[styles.actionButton, styles.progressButton]}
                onPress={() => navigation.navigate('WorkOrderDetail', { workOrderId: item.id })}
              >
                <Text style={styles.actionButtonText}>记录进度</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.completeButton]}
                onPress={() => navigation.navigate('WorkOrderDetail', { workOrderId: item.id })}
              >
                <Text style={styles.actionButtonText}>完成</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={loading} onRefresh={loadData} colors={['#1890ff']} />
      }
    >
      {/* V2G 快捷入口 */}
      <View style={styles.shortcutContainer}>
        <Text style={styles.shortcutTitle}>V2G 设备管理</Text>
        <View style={styles.shortcutGrid}>
          <TouchableOpacity
            style={styles.shortcutItem}
            onPress={() => navigation.navigate('V2GDiagnosis')}
          >
            <Text style={styles.shortcutIcon}>🔍</Text>
            <Text style={styles.shortcutLabel}>设备诊断</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.shortcutItem}
            onPress={() => navigation.navigate('V2GDispatch')}
          >
            <Text style={styles.shortcutIcon}>📡</Text>
            <Text style={styles.shortcutLabel}>调度响应</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.shortcutItem}
            onPress={() => navigation.navigate('EfficiencyTool')}
          >
            <Text style={styles.shortcutIcon}>⚡</Text>
            <Text style={styles.shortcutLabel}>效率检测</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 统计卡片 */}
      <View style={styles.statsContainer}>
        <View style={styles.statsCard}>
          <View style={styles.statItem}>
            <Text style={[styles.statValue, styles.pendingValue]}>
              {stats?.todayPending || 0}
            </Text>
            <Text style={styles.statLabel}>待接单</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, styles.processingValue]}>
              {stats?.todayProcessing || 0}
            </Text>
            <Text style={styles.statLabel}>进行中</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, styles.completedValue]}>
              {stats?.todayCompleted || 0}
            </Text>
            <Text style={styles.statLabel}>已完成</Text>
          </View>
        </View>
      </View>

      {/* Tab切换 */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'pending' && styles.tabActive]}
          onPress={() => setActiveTab('pending')}
        >
          <Text style={[styles.tabText, activeTab === 'pending' && styles.tabTextActive]}>
            待接单 ({pendingList.length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'processing' && styles.tabActive]}
          onPress={() => setActiveTab('processing')}
        >
          <Text style={[styles.tabText, activeTab === 'processing' && styles.tabTextActive]}>
            进行中 ({processingList.length})
          </Text>
        </TouchableOpacity>
      </View>

      {/* 工单列表 */}
      <View style={styles.listContainer}>
        {activeTab === 'pending' && (
          pendingList.length > 0 ? (
            pendingList.map((item) => (
              <WorkOrderCard key={item.id} item={item} type="pending" />
            ))
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>暂无待接单工单</Text>
            </View>
          )
        )}
        
        {activeTab === 'processing' && (
          processingList.length > 0 ? (
            processingList.map((item) => (
              <WorkOrderCard key={item.id} item={item} type="processing" />
            ))
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>暂无进行中工单</Text>
            </View>
          )
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  statsContainer: {
    padding: 16,
  },
  statsCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statDivider: {
    width: 1,
    height: 40,
    backgroundColor: '#e0e0e0',
  },
  statValue: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  pendingValue: {
    color: '#ff4d4f',
  },
  processingValue: {
    color: '#faad14',
  },
  completedValue: {
    color: '#52c41a',
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
  },
  tabContainer: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginBottom: 12,
    backgroundColor: '#e8e8e8',
    borderRadius: 8,
    padding: 4,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 6,
  },
  tabActive: {
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  tabText: {
    fontSize: 14,
    color: '#666',
  },
  tabTextActive: {
    color: '#1890ff',
    fontWeight: '600',
  },
  listContainer: {
    padding: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  urgencyTag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginRight: 12,
  },
  urgencyText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  orderNo: {
    fontSize: 14,
    color: '#999',
  },
  cardBody: {
    padding: 16,
  },
  deviceName: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 8,
  },
  stationName: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  faultDesc: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  timeText: {
    fontSize: 12,
    color: '#999',
  },
  actionRow: {
    flexDirection: 'row',
  },
  actionButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    marginLeft: 8,
  },
  acceptButton: {
    backgroundColor: '#52c41a',
  },
  transferButton: {
    backgroundColor: '#faad14',
  },
  progressButton: {
    backgroundColor: '#1890ff',
  },
  completeButton: {
    backgroundColor: '#52c41a',
  },
  actionButtonText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  emptyContainer: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: '#999',
  },
  shortcutContainer: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  shortcutTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 12,
  },
  shortcutGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  shortcutItem: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  shortcutIcon: {
    fontSize: 28,
    marginBottom: 6,
  },
  shortcutLabel: {
    fontSize: 12,
    color: '#333',
    fontWeight: '500',
  },
});

export default WorkbenchScreen;
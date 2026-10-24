import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  Modal,
  TextInput,
  Image,
  Linking,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/AppNavigator';
import { workOrderApi } from '../services/api';
import type { WorkOrder, ProcessStep, WorkOrderStatus } from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'WorkOrderDetail'>;

type ModalType = 'progress' | 'support' | 'parts' | 'complete' | null;

const WorkOrderDetailScreen: React.FC<Props> = ({ navigation, route }) => {
  const { workOrderId } = route.params;
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalType, setModalType] = useState<ModalType>(null);
  
  // 进度记录表单
  const [progressDesc, setProgressDesc] = useState('');
  const [supportDesc, setSupportDesc] = useState('');
  const [partsName, setPartsName] = useState('');
  const [partsQuantity, setPartsQuantity] = useState('1');
  const [partsReason, setPartsReason] = useState('');
  const [faultReason, setFaultReason] = useState('');
  const [solution, setSolution] = useState('');
  const [replacedParts, setReplacedParts] = useState('');

  // 加载工单详情
  const loadWorkOrder = useCallback(async () => {
    try {
      setLoading(true);
      const data = await workOrderApi.getDetail(workOrderId);
      setWorkOrder(data);
    } catch (error: any) {
      console.error('Load work order error:', error);
      // 使用模拟数据
      setWorkOrder(getMockData());
    } finally {
      setLoading(false);
    }
  }, [workOrderId]);

  useEffect(() => {
    loadWorkOrder();
  }, [loadWorkOrder]);

  // 模拟数据
  const getMockData = (): WorkOrder => ({
    id: workOrderId,
    orderNo: 'WO20260515001',
    status: 'accepted',
    urgency: 'high',
    deviceId: 'D001',
    deviceName: '充电桩A03',
    stationId: 'S001',
    stationName: '朝阳充电站',
    stationAddress: '朝阳区朝阳路88号',
    faultDescription: '充电枪无法连接，显示屏无响应，疑似通信模块故障',
    createdAt: '2026-05-15 10:30',
    acceptedAt: '2026-05-15 11:00',
    contactPhone: '138****1234',
    lat: 39.9289,
    lng: 116.4605,
  });

  // 获取处理流程步骤
  const getProcessSteps = (): ProcessStep[] => {
    const steps: ProcessStep[] = [
      { status: 'pending', label: '待接单', completed: false },
      { status: 'accepted', label: '已接单', completed: false },
      { status: 'arrived', label: '已到场', completed: false },
      { status: 'processing', label: '处理中', completed: false },
      { status: 'completed', label: '已完成', completed: false },
    ];

    const statusOrder: WorkOrderStatus[] = ['pending', 'accepted', 'arrived', 'processing', 'completed'];
    const currentIdx = statusOrder.indexOf(workOrder?.status || 'pending');

    steps.forEach((step, idx) => {
      if (idx < currentIdx) {
        step.completed = true;
      } else if (idx === currentIdx) {
        step.completed = true;
      }
    });

    return steps;
  };

  // 打开导航地图
  const handleNavigate = () => {
    if (!workOrder?.lat || !workOrder?.lng) {
      Alert.alert('提示', '缺少站点坐标信息');
      return;
    }

    // iOS 打开地图
    const url = `http://maps.apple.com/?daddr=${workOrder.lat},${workOrder.lng}&dirflg=d`;
    
    Linking.canOpenURL(url).then((supported) => {
      if (supported) {
        Linking.openURL(url);
      } else {
        Alert.alert('提示', '无法打开地图应用');
      }
    });
  };

  // 拨打电话
  const handleCall = () => {
    if (!workOrder?.contactPhone) {
      Alert.alert('提示', '缺少联系电话');
      return;
    }

    const url = `tel:${workOrder.contactPhone}`;
    Linking.canOpenURL(url).then((supported) => {
      if (supported) {
        Linking.openURL(url);
      } else {
        Alert.alert('提示', '无法拨打电话');
      }
    });
  };

  // 到场确认
  const handleArrive = async () => {
    Alert.alert(
      '到场确认',
      '确认已到达现场？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确认',
          onPress: async () => {
            try {
              await workOrderApi.arrive(workOrderId);
              Alert.alert('成功', '到场确认成功');
              loadWorkOrder();
            } catch (error: any) {
              Alert.alert('失败', error.response?.data?.message || '请稍后重试');
            }
          },
        },
      ]
    );
  };

  // 记录进度
  const handleSaveProgress = async () => {
    if (!progressDesc.trim()) {
      Alert.alert('提示', '请填写进度描述');
      return;
    }

    try {
      await workOrderApi.recordProgress(workOrderId, { description: progressDesc });
      Alert.alert('成功', '进度记录保存成功');
      setModalType(null);
      setProgressDesc('');
    } catch (error: any) {
      Alert.alert('失败', error.response?.data?.message || '请稍后重试');
    }
  };

  // 申请支援
  const handleSubmitSupport = async () => {
    if (!supportDesc.trim()) {
      Alert.alert('提示', '请填写支援说明');
      return;
    }

    try {
      await workOrderApi.requestSupport(workOrderId, supportDesc);
      Alert.alert('成功', '支援申请已提交');
      setModalType(null);
      setSupportDesc('');
    } catch (error: any) {
      Alert.alert('失败', error.response?.data?.message || '请稍后重试');
    }
  };

  // 申请备件
  const handleSubmitParts = async () => {
    if (!partsName.trim()) {
      Alert.alert('提示', '请填写备件名称');
      return;
    }
    if (!partsQuantity.trim() || parseInt(partsQuantity) < 1) {
      Alert.alert('提示', '请填写正确的数量');
      return;
    }
    if (!partsReason.trim()) {
      Alert.alert('提示', '请填写申请原因');
      return;
    }

    try {
      await workOrderApi.requestParts(workOrderId, {
        name: partsName,
        quantity: parseInt(partsQuantity),
        reason: partsReason,
      });
      Alert.alert('成功', '备件申请已提交');
      setModalType(null);
      setPartsName('');
      setPartsQuantity('1');
      setPartsReason('');
    } catch (error: any) {
      Alert.alert('失败', error.response?.data?.message || '请稍后重试');
    }
  };

  // 完成工单
  const handleComplete = async () => {
    if (!faultReason.trim()) {
      Alert.alert('提示', '请填写故障原因');
      return;
    }
    if (!solution.trim()) {
      Alert.alert('提示', '请填写处理方案');
      return;
    }

    Alert.alert(
      '完成确认',
      '确认完成此工单？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确认',
          onPress: async () => {
            try {
              await workOrderApi.complete(workOrderId, {
                faultReason,
                solution,
                replacedParts: replacedParts || undefined,
              });
              Alert.alert('成功', '工单已完成', [
                { text: '确定', onPress: () => navigation.goBack() },
              ]);
              setModalType(null);
            } catch (error: any) {
              Alert.alert('失败', error.response?.data?.message || '请稍后重试');
            }
          },
        },
      ]
    );
  };

  // 获取紧急程度颜色
  const getUrgencyColor = () => {
    switch (workOrder?.urgency) {
      case 'high': return '#ff4d4f';
      case 'medium': return '#faad14';
      case 'low': return '#52c41a';
      default: return '#999';
    }
  };

  if (!workOrder) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  const steps = getProcessSteps();

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* 基本信息 */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>基本信息</Text>
            <View style={[styles.urgencyBadge, { backgroundColor: getUrgencyColor() }]}>
              <Text style={styles.urgencyText}>
                {workOrder.urgency === 'high' ? '紧急' : workOrder.urgency === 'medium' ? '一般' : '低'}
              </Text>
            </View>
          </View>
          
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>工单编号</Text>
            <Text style={styles.infoValue}>{workOrder.orderNo}</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>设备信息</Text>
            <Text style={styles.infoValue}>{workOrder.deviceName}</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>站点信息</Text>
            <Text style={styles.infoValue}>{workOrder.stationName}</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>站点地址</Text>
            <Text style={styles.infoValue}>{workOrder.stationAddress}</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>故障描述</Text>
            <Text style={styles.infoValue}>{workOrder.faultDescription}</Text>
          </View>
        </View>

        {/* 处理流程 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>处理流程</Text>
          <View style={styles.stepsContainer}>
            {steps.map((step, idx) => (
              <View key={step.status} style={styles.stepWrapper}>
                <View style={styles.stepCircle}>
                  {step.completed ? (
                    <View style={[styles.stepCompleted, idx === steps.findIndex(s => s.status === workOrder.status) && styles.stepCurrent]}>
                      <Text style={styles.stepCompletedText}>✓</Text>
                    </View>
                  ) : (
                    <View style={styles.stepPending}>
                      <Text style={styles.stepPendingText}>{idx + 1}</Text>
                    </View>
                  )}
                </View>
                <Text style={[styles.stepLabel, step.completed && styles.stepLabelCompleted]}>
                  {step.label}
                </Text>
                {idx < steps.length - 1 && (
                  <View style={[styles.stepLine, step.completed && styles.stepLineCompleted]} />
                )}
              </View>
            ))}
          </View>
        </View>

        {/* 快捷操作按钮 */}
        <View style={styles.quickActions}>
          <TouchableOpacity style={styles.quickActionButton} onPress={handleNavigate}>
            <Text style={styles.quickActionIcon}>🗺️</Text>
            <Text style={styles.quickActionText}>导航到站</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickActionButton} onPress={handleCall}>
            <Text style={styles.quickActionIcon}>📞</Text>
            <Text style={styles.quickActionText}>联系站长</Text>
          </TouchableOpacity>
        </View>

        {/* 主要操作按钮 */}
        {workOrder.status === 'accepted' && (
          <TouchableOpacity style={styles.primaryButton} onPress={handleArrive}>
            <Text style={styles.primaryButtonText}>开始处理（到场确认）</Text>
          </TouchableOpacity>
        )}

        {workOrder.status === 'arrived' && (
          <View style={styles.actionButtons}>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.progressBtn]} 
              onPress={() => setModalType('progress')}
            >
              <Text style={styles.actionBtnText}>记录进度</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.supportBtn]} 
              onPress={() => setModalType('support')}
            >
              <Text style={styles.actionBtnText}>申请支援</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.partsBtn]} 
              onPress={() => setModalType('parts')}
            >
              <Text style={styles.actionBtnText}>申请备件</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.completeBtn]} 
              onPress={() => setModalType('complete')}
            >
              <Text style={styles.actionBtnText}>完成工单</Text>
            </TouchableOpacity>
          </View>
        )}

        {workOrder.status === 'processing' && (
          <View style={styles.actionButtons}>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.progressBtn]} 
              onPress={() => setModalType('progress')}
            >
              <Text style={styles.actionBtnText}>记录进度</Text>
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.actionBtn, styles.completeBtn]} 
              onPress={() => setModalType('complete')}
            >
              <Text style={styles.actionBtnText}>完成工单</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* 进度记录模态框 */}
      <Modal visible={modalType === 'progress'} transparent animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>记录进度</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="请输入进度描述"
              value={progressDesc}
              onChangeText={setProgressDesc}
              multiline
              numberOfLines={4}
              placeholderTextColor="#999"
            />
            <TouchableOpacity style={styles.modalPhotoButton}>
              <Text style={styles.modalPhotoText}>📷 添加照片</Text>
            </TouchableOpacity>
            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setModalType(null)}>
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={handleSaveProgress}>
                <Text style={styles.modalSaveText}>保存</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 申请支援模态框 */}
      <Modal visible={modalType === 'support'} transparent animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>申请支援</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="请输入支援说明"
              value={supportDesc}
              onChangeText={setSupportDesc}
              multiline
              numberOfLines={4}
              placeholderTextColor="#999"
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setModalType(null)}>
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={handleSubmitSupport}>
                <Text style={styles.modalSaveText}>提交</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 申请备件模态框 */}
      <Modal visible={modalType === 'parts'} transparent animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>申请备件</Text>
            <TextInput
              style={styles.modalInputSmall}
              placeholder="备件名称"
              value={partsName}
              onChangeText={setPartsName}
              placeholderTextColor="#999"
            />
            <TextInput
              style={styles.modalInputSmall}
              placeholder="数量"
              value={partsQuantity}
              onChangeText={setPartsQuantity}
              keyboardType="number-pad"
              placeholderTextColor="#999"
            />
            <TextInput
              style={styles.modalInput}
              placeholder="申请原因"
              value={partsReason}
              onChangeText={setPartsReason}
              multiline
              numberOfLines={3}
              placeholderTextColor="#999"
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setModalType(null)}>
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={handleSubmitParts}>
                <Text style={styles.modalSaveText}>提交</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* 完成工单模态框 */}
      <Modal visible={modalType === 'complete'} transparent animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalContentLarge}>
            <Text style={styles.modalTitle}>完成工单</Text>
            <TextInput
              style={styles.modalInputSmall}
              placeholder="故障原因"
              value={faultReason}
              onChangeText={setFaultReason}
              placeholderTextColor="#999"
            />
            <TextInput
              style={styles.modalInputSmall}
              placeholder="处理方案"
              value={solution}
              onChangeText={setSolution}
              placeholderTextColor="#999"
            />
            <TextInput
              style={styles.modalInputSmall}
              placeholder="更换配件（如有）"
              value={replacedParts}
              onChangeText={setReplacedParts}
              placeholderTextColor="#999"
            />
            <TouchableOpacity style={styles.modalPhotoButton}>
              <Text style={styles.modalPhotoText}>📷 添加照片</Text>
            </TouchableOpacity>
            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setModalType(null)}>
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={handleComplete}>
                <Text style={styles.modalSaveText}>提交</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  scrollView: {
    flex: 1,
    padding: 16,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#999',
  },
  section: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
  },
  urgencyBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  urgencyText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  infoItem: {
    marginBottom: 12,
  },
  infoLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
  },
  stepsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 20,
  },
  stepWrapper: {
    alignItems: 'center',
    width: 60,
  },
  stepCircle: {
    marginBottom: 8,
  },
  stepCompleted: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#52c41a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepCurrent: {
    borderWidth: 2,
    borderColor: '#1890ff',
  },
  stepCompletedText: {
    fontSize: 16,
    color: '#fff',
  },
  stepPending: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#e0e0e0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepPendingText: {
    fontSize: 14,
    color: '#999',
  },
  stepLabel: {
    fontSize: 12,
    color: '#999',
  },
  stepLabelCompleted: {
    color: '#52c41a',
    fontWeight: '600',
  },
  stepLine: {
    position: 'absolute',
    top: 16,
    right: -30,
    width: 60,
    height: 2,
    backgroundColor: '#e0e0e0',
  },
  stepLineCompleted: {
    backgroundColor: '#52c41a',
  },
  quickActions: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  quickActionButton: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 4,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  quickActionIcon: {
    fontSize: 20,
    marginRight: 8,
  },
  quickActionText: {
    fontSize: 14,
    color: '#333',
  },
  primaryButton: {
    backgroundColor: '#1890ff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  primaryButtonText: {
    fontSize: 16,
    color: '#fff',
    fontWeight: 'bold',
  },
  actionButtons: {
    marginBottom: 16,
  },
  actionBtn: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  progressBtn: {
    backgroundColor: '#1890ff',
  },
  supportBtn: {
    backgroundColor: '#faad14',
  },
  partsBtn: {
    backgroundColor: '#722ed1',
  },
  completeBtn: {
    backgroundColor: '#52c41a',
  },
  actionBtnText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  modalContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    width: '80%',
    maxHeight: '70%',
  },
  modalContentLarge: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    width: '85%',
    maxHeight: '80%',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 16,
    textAlign: 'center',
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 12,
    minHeight: 100,
    textAlignVertical: 'top',
  },
  modalInputSmall: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 12,
    height: 44,
  },
  modalPhotoButton: {
    borderWidth: 1,
    borderColor: '#1890ff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
    alignItems: 'center',
    backgroundColor: '#e6f7ff',
  },
  modalPhotoText: {
    fontSize: 14,
    color: '#1890ff',
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  modalCancelBtn: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    marginRight: 8,
    alignItems: 'center',
  },
  modalCancelText: {
    fontSize: 14,
    color: '#666',
  },
  modalSaveBtn: {
    flex: 1,
    backgroundColor: '#1890ff',
    borderRadius: 8,
    padding: 12,
    marginLeft: 8,
    alignItems: 'center',
  },
  modalSaveText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
});

export default WorkOrderDetailScreen;
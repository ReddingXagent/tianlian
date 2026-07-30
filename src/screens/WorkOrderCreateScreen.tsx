import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useWorkOrderEnhancedStore } from '../store/workOrderEnhancedStore';
import { RootStackParamList, WorkOrderType, WorkOrderPriority } from '../types';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ORDER_TYPES: { key: WorkOrderType; label: string }[] = [
  { key: 'repair', label: '维修' },
  { key: 'inspection', label: '巡检' },
  { key: 'installation', label: '安装' },
  { key: 'maintenance', label: '保养' },
  { key: 'other', label: '其他' },
];

const PRIORITIES: { key: WorkOrderPriority; label: string; color: string }[] = [
  { key: 'low', label: '低', color: '#2e7d32' },
  { key: 'normal', label: '中', color: '#1565c0' },
  { key: 'high', label: '高', color: '#c62828' },
  { key: 'urgent', label: '紧急', color: '#b71c1c' },
];

const WorkOrderCreateScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { creating, createError, createOrder } = useWorkOrderEnhancedStore();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [stationId, setStationId] = useState('');
  const [type, setType] = useState<WorkOrderType>('repair');
  const [priority, setPriority] = useState<WorkOrderPriority>('normal');
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setLocalError(null);

    if (!title.trim()) {
      setLocalError('请输入工单标题');
      return;
    }
    if (!description.trim()) {
      setLocalError('请输入工单描述');
      return;
    }
    if (!stationId.trim() || isNaN(Number(stationId))) {
      setLocalError('请输入有效的站点ID');
      return;
    }

    const order = await createOrder({
      title: title.trim(),
      description: description.trim(),
      stationId: Number(stationId),
      type,
      priority,
    });

    if (order) {
      Alert.alert('创建成功', `工单 #${order.id} 已创建`, [
        { text: '查看详情', onPress: () => navigation.replace('WorkOrderDetail', { orderId: order.id }) },
        { text: '继续创建', onPress: () => {
          setTitle('');
          setDescription('');
          setStationId('');
          setType('repair');
          setPriority('normal');
        }},
      ]);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.sectionTitle}>创建工单</Text>

        {(localError || createError) && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>{localError || createError}</Text>
          </View>
        )}

        {/* 工单标题 */}
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>工单标题 *</Text>
          <TextInput
            style={styles.input}
            placeholder="请输入工单标题"
            placeholderTextColor="#999"
            value={title}
            onChangeText={(t) => { setTitle(t); setLocalError(null); }}
            editable={!creating}
            maxLength={100}
          />
        </View>

        {/* 工单描述 */}
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>工单描述 *</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="请详细描述工单内容"
            placeholderTextColor="#999"
            value={description}
            onChangeText={(t) => { setDescription(t); setLocalError(null); }}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
            editable={!creating}
            maxLength={500}
          />
        </View>

        {/* 站点ID */}
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>关联站点ID *</Text>
          <TextInput
            style={styles.input}
            placeholder="请输入站点ID"
            placeholderTextColor="#999"
            value={stationId}
            onChangeText={(t) => { setStationId(t); setLocalError(null); }}
            keyboardType="numeric"
            editable={!creating}
          />
        </View>

        {/* 工单类型 */}
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>工单类型</Text>
          <View style={styles.chipContainer}>
            {ORDER_TYPES.map((ot) => (
              <TouchableOpacity
                key={ot.key}
                style={[styles.chip, type === ot.key && styles.chipActive]}
                onPress={() => setType(ot.key)}
                disabled={creating}
              >
                <Text style={[styles.chipText, type === ot.key && styles.chipTextActive]}>
                  {ot.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* 优先级 */}
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>优先级</Text>
          <View style={styles.chipContainer}>
            {PRIORITIES.map((p) => (
              <TouchableOpacity
                key={p.key}
                style={[
                  styles.chip,
                  priority === p.key && { backgroundColor: p.color },
                ]}
                onPress={() => setPriority(p.key)}
                disabled={creating}
              >
                <Text
                  style={[
                    styles.chipText,
                    priority === p.key && { color: '#fff' },
                  ]}
                >
                  {p.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* 提交按钮 */}
        <TouchableOpacity
          style={[styles.submitBtn, creating && styles.submitBtnDisabled]}
          onPress={handleSubmit}
          disabled={creating}
          activeOpacity={0.7}
        >
          {creating ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.submitBtnText}>提交工单</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    marginBottom: 20,
  },
  errorContainer: {
    backgroundColor: '#fce4ec',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: '#c62828',
    fontSize: 14,
    textAlign: 'center',
  },
  fieldGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#333',
  },
  textArea: {
    height: 100,
    paddingTop: 12,
  },
  chipContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#e8e8e8',
  },
  chipActive: {
    backgroundColor: '#1a73e8',
  },
  chipText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#666',
  },
  chipTextActive: {
    color: '#fff',
  },
  submitBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 10,
  },
  submitBtnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
});

export default WorkOrderCreateScreen;

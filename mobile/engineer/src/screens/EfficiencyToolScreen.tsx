import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TextInput,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/AppNavigator';
import { v2gApi } from '../services/api';
import type { V2GDevice, EfficiencyRecord } from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'EfficiencyTool'>;

type TabType = 'measure' | 'history';

const EfficiencyToolScreen: React.FC<Props> = ({ navigation }) => {
  const [devices, setDevices] = useState<V2GDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [inputEnergy, setInputEnergy] = useState('');
  const [outputEnergy, setOutputEnergy] = useState('');
  const [measurementType, setMeasurementType] = useState<'charge' | 'discharge'>('charge');
  const [calculatedEfficiency, setCalculatedEfficiency] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [records, setRecords] = useState<EfficiencyRecord[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>('measure');

  const loadDevices = useCallback(async () => {
    try {
      setLoading(true);
      const data = await v2gApi.getDevices();
      setDevices(data);
    } catch (error: any) {
      console.error('Load devices error:', error);
      setDevices(getMockDevices());
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRecords = useCallback(async () => {
    if (!selectedDeviceId) return;
    try {
      const data = await v2gApi.getEfficiencyHistory(selectedDeviceId);
      setRecords(data);
    } catch (error: any) {
      console.error('Load records error:', error);
      setRecords(getMockRecords());
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    loadDevices();
  }, [loadDevices]);

  useEffect(() => {
    if (selectedDeviceId) {
      loadRecords();
    }
  }, [selectedDeviceId, loadRecords]);

  const getMockDevices = (): V2GDevice[] => [
    {
      id: 'V2G001',
      name: 'V2G充电桩A01',
      type: 'v2g_charger',
      status: 'online',
      stationId: 'S001',
      stationName: '朝阳充电站',
      ratedPower: 60,
      batteryCapacity: 100,
      currentPower: 0,
      efficiency: 92.5,
      healthScore: 88,
      lastMaintenance: '2026-06-15',
    },
    {
      id: 'V2G002',
      name: 'V2G充电桩A02',
      type: 'v2g_charger',
      status: 'charging',
      stationId: 'S001',
      stationName: '朝阳充电站',
      ratedPower: 60,
      batteryCapacity: 100,
      currentPower: 45,
      efficiency: 78.3,
      healthScore: 65,
      lastMaintenance: '2026-05-20',
    },
  ];

  const getMockRecords = (): EfficiencyRecord[] => [
    {
      id: 'R001',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      inputEnergy: 100,
      outputEnergy: 92.5,
      efficiency: 92.5,
      measurementType: 'charge',
      createdAt: '2026-07-06 14:30',
    },
    {
      id: 'R002',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      inputEnergy: 85,
      outputEnergy: 78.2,
      efficiency: 92.0,
      measurementType: 'discharge',
      createdAt: '2026-07-05 10:15',
    },
    {
      id: 'R003',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      inputEnergy: 120,
      outputEnergy: 111.6,
      efficiency: 93.0,
      measurementType: 'charge',
      createdAt: '2026-07-04 16:00',
    },
  ];

  // 计算效率
  const handleCalculate = () => {
    const input = parseFloat(inputEnergy);
    const output = parseFloat(outputEnergy);

    if (!inputEnergy || !outputEnergy) {
      Alert.alert('提示', '请填写输入和输出电量');
      return;
    }
    if (isNaN(input) || isNaN(output)) {
      Alert.alert('提示', '请输入有效数字');
      return;
    }
    if (input <= 0) {
      Alert.alert('提示', '输入电量必须大于0');
      return;
    }
    if (output < 0) {
      Alert.alert('提示', '输出电量不能为负数');
      return;
    }
    if (output > input) {
      Alert.alert('提示', '输出电量不能大于输入电量');
      return;
    }

    const efficiency = Math.round((output / input) * 100 * 10) / 10;
    setCalculatedEfficiency(efficiency);
  };

  // 保存并上传
  const handleSave = async () => {
    if (!selectedDeviceId) {
      Alert.alert('提示', '请先选择V2G设备');
      return;
    }
    if (calculatedEfficiency === null) {
      Alert.alert('提示', '请先计算效率');
      return;
    }

    try {
      setSaving(true);
      const record = await v2gApi.submitEfficiency(selectedDeviceId, {
        inputEnergy: parseFloat(inputEnergy),
        outputEnergy: parseFloat(outputEnergy),
        measurementType,
      });
      Alert.alert('成功', '效率检测记录已保存');
      // 重置表单
      setInputEnergy('');
      setOutputEnergy('');
      setCalculatedEfficiency(null);
      // 刷新记录
      loadRecords();
    } catch (error: any) {
      console.error('Save efficiency error:', error);
      // 模拟保存
      const newRecord: EfficiencyRecord = {
        id: `R${Date.now()}`,
        deviceId: selectedDeviceId,
        deviceName: devices.find(d => d.id === selectedDeviceId)?.name || '',
        inputEnergy: parseFloat(inputEnergy),
        outputEnergy: parseFloat(outputEnergy),
        efficiency: calculatedEfficiency,
        measurementType,
        createdAt: new Date().toLocaleString('zh-CN'),
      };
      setRecords([newRecord, ...records]);
      Alert.alert('成功', '效率检测记录已保存（本地）');
      setInputEnergy('');
      setOutputEnergy('');
      setCalculatedEfficiency(null);
    } finally {
      setSaving(false);
    }
  };

  const getEfficiencyColor = (val: number) => {
    if (val >= 90) return '#52c41a';
    if (val >= 80) return '#faad14';
    return '#ff4d4f';
  };

  // ========== 测量页 ==========
  const MeasureTab = () => (
    <View>
      {/* 设备选择 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>选择检测设备</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {devices.map((device) => (
            <TouchableOpacity
              key={device.id}
              style={[
                styles.deviceChip,
                selectedDeviceId === device.id && styles.deviceChipActive,
              ]}
              onPress={() => setSelectedDeviceId(device.id)}
            >
              <Text style={[
                styles.deviceChipText,
                selectedDeviceId === device.id && styles.deviceChipTextActive,
              ]}>
                {device.name}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        {devices.length === 0 && (
          <Text style={styles.hint}>正在加载设备列表...</Text>
        )}
      </View>

      {/* 测量类型选择 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>测量类型</Text>
        <View style={styles.typeRow}>
          <TouchableOpacity
            style={[
              styles.typeButton,
              measurementType === 'charge' && styles.typeButtonActive,
            ]}
            onPress={() => setMeasurementType('charge')}
          >
            <Text style={[
              styles.typeButtonText,
              measurementType === 'charge' && styles.typeButtonTextActive,
            ]}>
              ⚡ 充电效率
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.typeButton,
              measurementType === 'discharge' && styles.typeButtonActive,
            ]}
            onPress={() => setMeasurementType('discharge')}
          >
            <Text style={[
              styles.typeButtonText,
              measurementType === 'discharge' && styles.typeButtonTextActive,
            ]}>
              🔋 放电效率
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 输入参数 */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>输入参数</Text>
        <View style={styles.inputGroup}>
          <View style={styles.inputWrapper}>
            <Text style={styles.inputLabel}>充电输入电量 (kWh)</Text>
            <TextInput
              style={styles.input}
              placeholder="请输入输入电量"
              value={inputEnergy}
              onChangeText={setInputEnergy}
              keyboardType="decimal-pad"
              placeholderTextColor="#999"
            />
          </View>
          <View style={styles.inputWrapper}>
            <Text style={styles.inputLabel}>输出电量 (kWh)</Text>
            <TextInput
              style={styles.input}
              placeholder="请输入输出电量"
              value={outputEnergy}
              onChangeText={setOutputEnergy}
              keyboardType="decimal-pad"
              placeholderTextColor="#999"
            />
          </View>
        </View>

        <TouchableOpacity
          style={styles.calcButton}
          onPress={handleCalculate}
          disabled={!inputEnergy || !outputEnergy}
        >
          <Text style={styles.calcButtonText}>计算效率</Text>
        </TouchableOpacity>

        {/* 计算结果 */}
        {calculatedEfficiency !== null && (
          <View style={styles.resultBox}>
            <Text style={styles.resultLabel}>效率计算结果</Text>
            <View style={styles.resultRow}>
              <Text style={[
                styles.resultValue,
                { color: getEfficiencyColor(calculatedEfficiency) },
              ]}>
                {calculatedEfficiency}%
              </Text>
              <Text style={styles.resultFormula}>
                = {outputEnergy} / {inputEnergy} × 100
              </Text>
            </View>
            {calculatedEfficiency < 85 && (
              <View style={styles.warningBanner}>
                <Text style={styles.warningText}>⚠️ 效率偏低，建议进一步检查</Text>
              </View>
            )}

            <TouchableOpacity
              style={[styles.saveButton, saving && styles.saveButtonDisabled]}
              onPress={handleSave}
              disabled={saving}
            >
              <Text style={styles.saveButtonText}>
                {saving ? '保存中...' : '保存并上传'}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </View>
  );

  // ========== 历史记录页 ==========
  const HistoryTab = () => (
    <View>
      {!selectedDeviceId ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>请先在上方选择设备</Text>
        </View>
      ) : records.length > 0 ? (
        records.map((record) => {
          const effColor = getEfficiencyColor(record.efficiency);
          return (
            <View key={record.id} style={styles.recordCard}>
              <View style={styles.recordHeader}>
                <View style={[
                  styles.recordTypeBadge,
                  { backgroundColor: record.measurementType === 'charge' ? '#1890ff' : '#faad14' },
                ]}>
                  <Text style={styles.recordTypeText}>
                    {record.measurementType === 'charge' ? '充电' : '放电'}
                  </Text>
                </View>
                <Text style={styles.recordDate}>{record.createdAt}</Text>
              </View>
              <View style={styles.recordBody}>
                <View style={styles.recordItem}>
                  <Text style={styles.recordLabel}>输入</Text>
                  <Text style={styles.recordValue}>{record.inputEnergy} kWh</Text>
                </View>
                <View style={styles.recordItem}>
                  <Text style={styles.recordLabel}>输出</Text>
                  <Text style={styles.recordValue}>{record.outputEnergy} kWh</Text>
                </View>
                <View style={styles.recordItem}>
                  <Text style={styles.recordLabel}>效率</Text>
                  <Text style={[styles.recordEfficiency, { color: effColor }]}>
                    {record.efficiency}%
                  </Text>
                </View>
              </View>
            </View>
          );
        })
      ) : (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>暂无检测记录</Text>
        </View>
      )}
    </View>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Tab切换 */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'measure' && styles.tabActive]}
          onPress={() => setActiveTab('measure')}
        >
          <Text style={[styles.tabText, activeTab === 'measure' && styles.tabTextActive]}>
            效率检测
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'history' && styles.tabActive]}
          onPress={() => setActiveTab('history')}
        >
          <Text style={[styles.tabText, activeTab === 'history' && styles.tabTextActive]}>
            历史记录 ({records.length})
          </Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={loadDevices} colors={['#1890ff']} />
        }
        keyboardShouldPersistTaps="handled"
      >
        {activeTab === 'measure' ? <MeasureTab /> : <HistoryTab />}
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  tabContainer: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 16,
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
  scrollView: {
    flex: 1,
    paddingHorizontal: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 12,
  },
  hint: {
    fontSize: 13,
    color: '#999',
  },
  deviceChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#f5f5f5',
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  deviceChipActive: {
    backgroundColor: '#e6f7ff',
    borderColor: '#1890ff',
  },
  deviceChipText: {
    fontSize: 13,
    color: '#666',
  },
  deviceChipTextActive: {
    color: '#1890ff',
    fontWeight: '600',
  },
  typeRow: {
    flexDirection: 'row',
    gap: 10,
  },
  typeButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#f5f5f5',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  typeButtonActive: {
    backgroundColor: '#e6f7ff',
    borderColor: '#1890ff',
  },
  typeButtonText: {
    fontSize: 14,
    color: '#666',
  },
  typeButtonTextActive: {
    color: '#1890ff',
    fontWeight: '600',
  },
  inputGroup: {
    gap: 12,
    marginBottom: 16,
  },
  inputWrapper: {
    gap: 4,
  },
  inputLabel: {
    fontSize: 13,
    color: '#666',
  },
  input: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
    backgroundColor: '#fafafa',
  },
  calcButton: {
    backgroundColor: '#1890ff',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
  },
  calcButtonText: {
    fontSize: 15,
    color: '#fff',
    fontWeight: '600',
  },
  resultBox: {
    marginTop: 16,
    backgroundColor: '#f0f5ff',
    borderRadius: 8,
    padding: 16,
  },
  resultLabel: {
    fontSize: 13,
    color: '#666',
    marginBottom: 8,
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginBottom: 8,
  },
  resultValue: {
    fontSize: 36,
    fontWeight: 'bold',
    marginRight: 12,
  },
  resultFormula: {
    fontSize: 13,
    color: '#999',
  },
  warningBanner: {
    backgroundColor: '#fff2f0',
    borderWidth: 1,
    borderColor: '#ffccc7',
    borderRadius: 6,
    padding: 8,
    marginBottom: 12,
  },
  warningText: {
    fontSize: 12,
    color: '#ff4d4f',
  },
  saveButton: {
    backgroundColor: '#52c41a',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  saveButtonDisabled: {
    backgroundColor: '#b7eb8f',
  },
  saveButtonText: {
    fontSize: 15,
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
  recordCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  recordHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  recordTypeBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  recordTypeText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  recordDate: {
    fontSize: 12,
    color: '#999',
  },
  recordBody: {
    flexDirection: 'row',
    padding: 14,
    alignItems: 'center',
  },
  recordItem: {
    flex: 1,
    alignItems: 'center',
  },
  recordLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  recordValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  recordEfficiency: {
    fontSize: 18,
    fontWeight: 'bold',
  },
});

export default EfficiencyToolScreen;
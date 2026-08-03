import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { chargingApi } from '../services/api';
import { useOrderStore } from '../store/orderStore';
import { ScanResult, RootStackParamList } from '../types';
import StatusBadge from '../components/StatusBadge';
import CameraScanner from '../components/CameraScanner';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ScanScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const [codeInput, setCodeInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startCharging = useOrderStore((s) => s.startCharging);
  const [starting, setStarting] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);

  const lookupCode = useCallback(async (code: string) => {
    setLoading(true);
    setError(null);
    setLastResult(null);

    try {
      const response = await chargingApi.scan(code);
      setLastResult(response.data);
      setCodeInput('');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '未找到匹配的充电桩');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleScan = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入充电桩编码');
      return;
    }
    await lookupCode(code);
  }, [codeInput, lookupCode]);

  const handleCameraScan = useCallback(
    (code: string) => {
      setCameraOpen(false);
      setCodeInput(code);
      void lookupCode(code);
    },
    [lookupCode]
  );

  const handleStartCharging = useCallback(async () => {
    if (!lastResult) return;

    if (lastResult.status !== 'idle') {
      Alert.alert('提示', '该充电桩当前不可用');
      return;
    }

    setStarting(true);
    try {
      const status = await startCharging(lastResult.id);
      navigation.replace('Charging', { orderId: status.orderId });
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        Alert.alert('启动失败', axiosErr.response?.data?.message || '启动充电失败');
      } else {
        Alert.alert('启动失败', '网络错误，请检查网络连接');
      }
    } finally {
      setStarting(false);
    }
  }, [lastResult, startCharging, navigation]);

  const handleQuickInput = (code: string) => {
    setCodeInput(code);
    setError(null);
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* 扫码区域: 未开启时为入口, 开启后为相机取景框 */}
      <View style={styles.scannerFrame}>
        {cameraOpen ? (
          <CameraScanner
            onScan={handleCameraScan}
            onClose={() => setCameraOpen(false)}
          />
        ) : (
          <TouchableOpacity
            style={styles.scannerBox}
            onPress={() => setCameraOpen(true)}
            activeOpacity={0.8}
            testID="open-camera-btn"
          >
            <Text style={styles.scannerIcon}>📷</Text>
            <Text style={styles.scannerHint}>扫描充电桩二维码</Text>
            <Text style={styles.scannerSubHint}>点此打开摄像头扫码</Text>
            <Text style={styles.scannerSubHint}>
              也可手动输入充电桩编码进行充电
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {/* 输入区域 */}
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          placeholder="输入充电桩编码"
          placeholderTextColor="#999"
          value={codeInput}
          onChangeText={(text) => {
            setCodeInput(text);
            setError(null);
          }}
          autoCapitalize="characters"
          autoCorrect={false}
          editable={!loading}
          returnKeyType="search"
          onSubmitEditing={handleScan}
        />
        <TouchableOpacity
          style={[styles.scanBtn, loading && styles.scanBtnDisabled]}
          onPress={handleScan}
          disabled={loading}
          activeOpacity={0.7}
        >
          {loading ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.scanBtnText}>查询</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* 快速输入示例 */}
      <View style={styles.quickContainer}>
        <Text style={styles.quickLabel}>快速输入:</Text>
        <View style={styles.quickRow}>
          <TouchableOpacity
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CH-001')}
          >
            <Text style={styles.quickBtnText}>CH-001</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CH-002')}
          >
            <Text style={styles.quickBtnText}>CH-002</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CH-003')}
          >
            <Text style={styles.quickBtnText}>CH-003</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 错误提示 */}
      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* 查询结果 */}
      {lastResult && (
        <View style={styles.resultContainer}>
          <Text style={styles.resultTitle}>充电桩信息</Text>
          <View style={styles.resultCard}>
            <View style={styles.resultInfo}>
              <View style={styles.resultHeader}>
                <Text style={styles.resultName}>{lastResult.name}</Text>
                <StatusBadge status={lastResult.status} />
              </View>
              <Text style={styles.resultStation}>{lastResult.stationName}</Text>
              <View style={styles.resultMeta}>
                <Text style={styles.resultMetaItem}>
                  功率: {lastResult.power}kW
                </Text>
                <Text style={styles.resultMetaItem}>
                  编码: {lastResult.code}
                </Text>
              </View>
              <View style={styles.priceRow}>
                <Text style={styles.resultPrice}>
                  电费 {lastResult.pricePerKwh.toFixed(2)} + 服务费 {lastResult.serviceFee.toFixed(2)}
                </Text>
              </View>
            </View>
          </View>

          {/* 开始充电按钮 */}
          <TouchableOpacity
            style={[
              styles.startBtn,
              (lastResult.status !== 'idle' || starting) && styles.startBtnDisabled,
            ]}
            onPress={handleStartCharging}
            disabled={lastResult.status !== 'idle' || starting}
            activeOpacity={0.7}
          >
            {starting ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.startBtnText}>
                {lastResult.status === 'idle' ? '开始充电' : '当前不可用'}
              </Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  scannerFrame: {
    alignItems: 'center',
    marginTop: 20,
    marginBottom: 24,
  },
  scannerBox: {
    width: 240,
    height: 200,
    borderWidth: 2,
    borderColor: '#1a73e8',
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(26, 115, 232, 0.05)',
  },
  scannerIcon: {
    fontSize: 56,
    marginBottom: 12,
  },
  scannerHint: {
    fontSize: 15,
    fontWeight: '500',
    color: '#333',
  },
  scannerSubHint: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  inputContainer: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  input: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: '#333',
    borderWidth: 1,
    borderColor: '#ddd',
  },
  scanBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanBtnDisabled: {
    opacity: 0.6,
  },
  scanBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  quickContainer: {
    marginBottom: 16,
  },
  quickLabel: {
    fontSize: 13,
    color: '#999',
    marginBottom: 8,
  },
  quickRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  quickBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#e3f2fd',
    borderRadius: 8,
  },
  quickBtnText: {
    fontSize: 13,
    color: '#1565c0',
    fontWeight: '500',
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
  resultContainer: {
    marginTop: 8,
  },
  resultTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  resultCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 16,
  },
  resultInfo: {
    flex: 1,
  },
  resultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  resultName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  resultStation: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  resultMeta: {
    flexDirection: 'row',
    gap: 16,
    marginBottom: 6,
  },
  resultMetaItem: {
    fontSize: 13,
    color: '#999',
  },
  priceRow: {
    marginTop: 4,
  },
  resultPrice: {
    fontSize: 13,
    color: '#e65100',
  },
  startBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
  },
  startBtnDisabled: {
    opacity: 0.6,
  },
  startBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
});

export default ScanScreen;
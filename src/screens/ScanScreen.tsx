import React, { useMemo } from 'react';
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
import { useScan } from '../hooks/useScan';
import { RootStackParamList } from '../types';
import StatusBadge from '../components/StatusBadge';
import CameraScanner from '../components/CameraScanner';
import { formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ScanScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const navigation = useNavigation<NavigationProp>();
  const {
    codeInput,
    setCodeInput,
    loading,
    lastResult,
    error,
    starting,
    cameraOpen,
    setCameraOpen,
    handleScan,
    handleCameraScan,
    handleStartCharging,
  } = useScan();

  const handleStartChargingPress = async () => {
    if (!lastResult || lastResult.status !== 'idle') {
      Alert.alert('提示', '该充电桩当前不可用');
      return;
    }
    try {
      const status = await handleStartCharging();
      if (status) {
        navigation.replace('Charging', { orderId: status.orderId });
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        Alert.alert('启动失败', axiosErr.response?.data?.message || '启动充电失败');
      } else {
        Alert.alert('启动失败', '网络错误，请检查网络连接');
      }
    }
  };

  const handleQuickInput = (code: string) => {
    setCodeInput(code);
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
    >
      {/* 扫码区域: 未开启时为入口, 开启后为相机取景框 */}
      <View style={styles.scannerFrame}>
        {cameraOpen ? (
          <CameraScanner
            onScan={handleCameraScan}
            onClose={() => setCameraOpen(false)}
          />
        ) : (
          <TouchableOpacity accessibilityRole="button"
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
          placeholderTextColor={colors.textSecondary}
          value={codeInput}
          onChangeText={(text) => {
            setCodeInput(text);
          }}
          autoCapitalize="characters"
          autoCorrect={false}
          editable={!loading}
          returnKeyType="search"
          onSubmitEditing={handleScan}
        />
        <TouchableOpacity accessibilityRole="button"
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
          <TouchableOpacity accessibilityRole="button"
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CH-001')}
          >
            <Text style={styles.quickBtnText}>CH-001</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button"
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CH-002')}
          >
            <Text style={styles.quickBtnText}>CH-002</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button"
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
                  电费 {formatMoney(lastResult.pricePerKwh)} + 服务费 {formatMoney(lastResult.serviceFee)}
                </Text>
              </View>
            </View>
          </View>

          {/* 开始充电按钮 */}
          <TouchableOpacity accessibilityRole="button"
            style={[
              styles.startBtn,
              (lastResult.status !== 'idle' || starting) && styles.startBtnDisabled,
            ]}
            onPress={handleStartChargingPress}
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

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'colors.pageBg',
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
    borderColor: colors.primary,
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
    color: 'colors.textPrimary',
  },
  scannerSubHint: {
    fontSize: 12,
    color: 'colors.textSecondary',
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
    color: 'colors.textPrimary',
    borderWidth: 1,
    borderColor: '#ddd',
  },
  scanBtn: {
    backgroundColor: colors.primary,
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
    color: 'colors.textSecondary',
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
    color: 'colors.textPrimary',
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
    color: 'colors.textPrimary',
    flex: 1,
    marginRight: 8,
  },
  resultStation: {
    fontSize: 14,
    color: 'colors.textSecondary',
    marginBottom: 8,
  },
  resultMeta: {
    flexDirection: 'row',
    gap: 16,
    marginBottom: 6,
  },
  resultMetaItem: {
    fontSize: 13,
    color: 'colors.textSecondary',
  },
  priceRow: {
    marginTop: 4,
  },
  resultPrice: {
    fontSize: 13,
    color: '#e65100',
  },
  startBtn: {
    backgroundColor: colors.primary,
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

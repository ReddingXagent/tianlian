import React, { useState, useRef, useCallback } from 'react';
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
import { scanApi } from '../services/api';
import { ScanResult } from '../types';
import StatusBadge from '../components/StatusBadge';

const ScanScreen: React.FC = () => {
  const [codeInput, setCodeInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signInMode, setSignInMode] = useState(false);
  const inputRef = useRef<TextInput>(null);

  const handleScan = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入设备/站点编码');
      return;
    }

    setLoading(true);
    setError(null);
    setLastResult(null);

    try {
      const response = await scanApi.scan(code);
      setLastResult(response.data);
      setCodeInput('');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as {
          response?: { data?: { message?: string } };
        };
        setError(
          axiosErr.response?.data?.message || '未找到匹配的设备或站点'
        );
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, [codeInput]);

  const handleQuickInput = (code: string) => {
    setCodeInput(code);
    setError(null);
  };

  const handleSignIn = useCallback(async () => {
    if (!lastResult) {
      Alert.alert('提示', '请先扫码查询设备信息');
      return;
    }
    setSignInMode(true);
    Alert.alert(
      '扫码签到',
      `确认在 ${lastResult.name || lastResult.code} 处签到？`,
      [
        { text: '取消', style: 'cancel', onPress: () => setSignInMode(false) },
        {
          text: '签到',
          onPress: async () => {
            setLoading(true);
            try {
              await scanApi.checkIn(lastResult.id);
              Alert.alert('签到成功', `已在 ${lastResult.name || lastResult.code} 签到`);
            } catch {
              Alert.alert('签到失败', '请重试或联系管理员');
            } finally {
              setLoading(false);
              setSignInMode(false);
            }
          },
        },
      ]
    );
  }, [lastResult]);

  const handleReportFault = () => {
    if (!lastResult) {
      Alert.alert('提示', '请先扫码查询设备信息');
      return;
    }
    Alert.alert('报修', `是否提交 ${lastResult.name || lastResult.code} 的报修请求？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '提交',
        onPress: () => {
          Alert.alert('提交成功', '报修请求已提交，等待处理');
        },
      },
    ]);
  };

  const resultIcon = (type: string) => {
    switch (type) {
      case 'device':
        return '🔌';
      case 'station':
        return '📡';
      default:
        return '❓';
    }
  };

  const resultTypeLabel = (type: string) => {
    switch (type) {
      case 'device':
        return '设备';
      case 'station':
        return '站点';
      default:
        return '未知';
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* 扫码区域示意 */}
      <View style={styles.scannerFrame}>
        <View style={[styles.scannerBox, signInMode && styles.scannerBoxSignIn]}>
          <Text style={styles.scannerIcon}>{signInMode ? '📌' : '📷'}</Text>
          <Text style={styles.scannerHint}>
            {signInMode ? '签到模式' : '请输入设备或站点编码'}
          </Text>
          <Text style={styles.scannerSubHint}>
            {signInMode ? '请扫描设备二维码进行签到' : '模拟扫码 - 手动输入编码查询'}
          </Text>
        </View>
      </View>

      {/* 输入区域 */}
      <View style={styles.inputContainer}>
        <TextInput
          ref={inputRef}
          style={styles.input}
          placeholder="输入设备/站点编码"
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
            onPress={() => handleQuickInput('DEV-001')}
          >
            <Text style={styles.quickBtnText}>DEV-001</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickBtn}
            onPress={() => handleQuickInput('STATION-A01')}
          >
            <Text style={styles.quickBtnText}>STATION-A01</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickBtn}
            onPress={() => handleQuickInput('CHARGER-005')}
          >
            <Text style={styles.quickBtnText}>CHARGER-005</Text>
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
          <Text style={styles.resultTitle}>扫码结果</Text>
          <View style={styles.resultCard}>
            <Text style={styles.resultIcon}>
              {resultIcon(lastResult.type)}
            </Text>
            <View style={styles.resultInfo}>
              <Text style={styles.resultType}>
                类型: {resultTypeLabel(lastResult.type)}
              </Text>
              <Text style={styles.resultCode}>
                编码: {lastResult.code}
              </Text>
              {lastResult.name && (
                <Text style={styles.resultName}>
                  名称: {lastResult.name}
                </Text>
              )}
              <Text style={styles.resultId}>ID: {lastResult.id}</Text>
              {lastResult.type === 'device' && lastResult.status && (
                <View style={styles.resultStatus}>
                  <StatusBadge status={lastResult.status} />
                </View>
              )}
            </View>
          </View>

          {/* 操作按钮 */}
          <View style={styles.resultActions}>
            <TouchableOpacity
              style={styles.resultActionBtn}
              onPress={handleSignIn}
              activeOpacity={0.7}
            >
              <Text style={styles.resultActionIcon}>📌</Text>
              <Text style={styles.resultActionLabel}>扫码签到</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.resultActionBtn}
              onPress={handleReportFault}
              activeOpacity={0.7}
            >
              <Text style={styles.resultActionIcon}>🔧</Text>
              <Text style={styles.resultActionLabel}>报修</Text>
            </TouchableOpacity>
          </View>
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
  scannerBoxSignIn: {
    borderColor: '#e65100',
    backgroundColor: 'rgba(230, 81, 0, 0.05)',
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
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 12,
  },
  resultIcon: {
    fontSize: 40,
    marginRight: 16,
  },
  resultInfo: {
    flex: 1,
  },
  resultType: {
    fontSize: 14,
    color: '#1a73e8',
    fontWeight: '500',
    marginBottom: 4,
  },
  resultCode: {
    fontSize: 14,
    color: '#333',
    marginBottom: 2,
  },
  resultName: {
    fontSize: 14,
    color: '#333',
    marginBottom: 2,
  },
  resultId: {
    fontSize: 12,
    color: '#999',
  },
  resultStatus: {
    marginTop: 4,
  },
  resultActions: {
    flexDirection: 'row',
    gap: 10,
  },
  resultActionBtn: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  resultActionIcon: {
    fontSize: 28,
    marginBottom: 6,
  },
  resultActionLabel: {
    fontSize: 13,
    color: '#666',
    fontWeight: '500',
  },
});

export default ScanScreen;
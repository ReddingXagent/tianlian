import { useState, useCallback } from 'react';
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
import StatusBadge from '../components/StatusBadge';
import { useScan } from '../hooks/useScan';
import { useTheme } from '../hooks/useTheme';

const ScanScreen: React.FC = () => {
  const {
    codeInput,
    loading,
    lastResult,
    error,
    inputRef,
    setCodeInput,
    setError,
    handleScan,
    handleQuickInput,
    performCheckIn,
  } = useScan();
  const { colors } = useTheme();

  const [signInMode, setSignInMode] = useState(false);

  const handleSignIn = useCallback(async () => {
    setSignInMode(true);
    Alert.alert(
      '扫码签到',
      `确认在 ${lastResult!.name || lastResult!.code} 处签到？`,
      [
        { text: '取消', style: 'cancel', onPress: () => setSignInMode(false) },
        {
          text: '签到',
          onPress: async () => {
            const ok = await performCheckIn();
            if (ok) {
              Alert.alert('签到成功', `已在 ${lastResult!.name || lastResult!.code} 签到`);
            } else {
              Alert.alert('签到失败', '请重试或联系管理员');
            }
            setSignInMode(false);
          },
        },
      ]
    );
  }, [lastResult, performCheckIn]);

  const handleReportFault = () => {
    Alert.alert('报修', `是否提交 ${lastResult!.name || lastResult!.code} 的报修请求？`, [
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
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* 扫码区域示意 */}
      <View style={styles.scannerFrame}>
        <View style={[styles.scannerBox, { borderColor: colors.primary, backgroundColor: colors.infoBg }, signInMode && { borderColor: colors.warning, backgroundColor: colors.warningBg }]}>
          <Text style={styles.scannerIcon}>{signInMode ? '📌' : '📷'}</Text>
          <Text style={[styles.scannerHint, { color: colors.textPrimary }]}>
            {signInMode ? '签到模式' : '请输入设备或站点编码'}
          </Text>
          <Text style={[styles.scannerSubHint, { color: colors.textSecondary }]}>
            {signInMode ? '请扫描设备二维码进行签到' : '模拟扫码 - 手动输入编码查询'}
          </Text>
        </View>
      </View>

      {/* 输入区域 */}
      <View style={styles.inputContainer}>
        <TextInput
          ref={inputRef}
          style={[styles.input, { backgroundColor: colors.cardBg, color: colors.textPrimary, borderColor: colors.border }]}
          placeholder="输入设备/站点编码"
          placeholderTextColor={colors.textSecondary}
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
          style={[styles.scanBtn, { backgroundColor: colors.primary }, loading && styles.scanBtnDisabled]}
          onPress={handleScan}
          disabled={loading}
          activeOpacity={0.7}
          accessibilityRole="button">
          {loading ? (
            <ActivityIndicator color={colors.onPrimary} size="small" />
          ) : (
            <Text style={[styles.scanBtnText, { color: colors.onPrimary }]}>查询</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* 快速输入示例 */}
      <View style={styles.quickContainer}>
        <Text style={[styles.quickLabel, { color: colors.textSecondary }]}>快速输入:</Text>
        <View style={styles.quickRow}>
          <TouchableOpacity
            style={[styles.quickBtn, { backgroundColor: colors.infoBg }]}
            onPress={() => handleQuickInput('DEV-001')}
            accessibilityRole="button">
            <Text style={[styles.quickBtnText, { color: colors.info }]}>DEV-001</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quickBtn, { backgroundColor: colors.infoBg }]}
            onPress={() => handleQuickInput('STATION-A01')}
            accessibilityRole="button">
            <Text style={[styles.quickBtnText, { color: colors.info }]}>STATION-A01</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quickBtn, { backgroundColor: colors.infoBg }]}
            onPress={() => handleQuickInput('CHARGER-005')}
            accessibilityRole="button">
            <Text style={[styles.quickBtnText, { color: colors.info }]}>CHARGER-005</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 错误提示 */}
      {error && (
        <View style={[styles.errorContainer, { backgroundColor: colors.errorBg }]}>
          <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text>
        </View>
      )}

      {/* 查询结果 */}
      {lastResult && (
        <View style={styles.resultContainer}>
          <Text style={[styles.resultTitle, { color: colors.textPrimary }]}>扫码结果</Text>
          <View style={[styles.resultCard, { backgroundColor: colors.cardBg }]}>
            <Text style={styles.resultIcon}>
              {resultIcon(lastResult.type)}
            </Text>
            <View style={styles.resultInfo}>
              <Text style={[styles.resultType, { color: colors.primary }]}>
                类型: {resultTypeLabel(lastResult.type)}
              </Text>
              <Text style={[styles.resultCode, { color: colors.textPrimary }]}>
                编码: {lastResult!.code}
              </Text>
              {lastResult!.name && (
                <Text style={[styles.resultName, { color: colors.textPrimary }]}>
                  名称: {lastResult!.name}
                </Text>
              )}
              <Text style={[styles.resultId, { color: colors.textSecondary }]}>ID: {lastResult.id}</Text>
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
              style={[styles.resultActionBtn, { backgroundColor: colors.cardBg }]}
              onPress={handleSignIn}
              activeOpacity={0.7}
              accessibilityRole="button">
              <Text style={styles.resultActionIcon}>📌</Text>
              <Text style={[styles.resultActionLabel, { color: colors.textSecondary }]}>扫码签到</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.resultActionBtn, { backgroundColor: colors.cardBg }]}
              onPress={handleReportFault}
              activeOpacity={0.7}
              accessibilityRole="button">
              <Text style={styles.resultActionIcon}>🔧</Text>
              <Text style={[styles.resultActionLabel, { color: colors.textSecondary }]}>报修</Text>
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
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scannerIcon: {
    fontSize: 56,
    marginBottom: 12,
  },
  scannerHint: {
    fontSize: 15,
    fontWeight: '500',
  },
  scannerSubHint: {
    fontSize: 12,
    marginTop: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  input: {
    flex: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    borderWidth: 1,
  },
  scanBtn: {
    borderRadius: 8,
    paddingHorizontal: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanBtnDisabled: {
    opacity: 0.6,
  },
  scanBtnText: {
    fontSize: 16,
    fontWeight: '600',
  },
  quickContainer: {
    marginBottom: 16,
  },
  quickLabel: {
    fontSize: 13,
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
    borderRadius: 8,
  },
  quickBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  errorContainer: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    fontSize: 14,
    textAlign: 'center',
  },
  resultContainer: {
    marginTop: 8,
  },
  resultTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  resultCard: {
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
    fontWeight: '500',
    marginBottom: 4,
  },
  resultCode: {
    fontSize: 14,
    marginBottom: 2,
  },
  resultName: {
    fontSize: 14,
    marginBottom: 2,
  },
  resultId: {
    fontSize: 12,
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
    fontWeight: '500',
  },
});

export default ScanScreen;

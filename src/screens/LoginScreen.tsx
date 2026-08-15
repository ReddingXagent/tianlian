import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../services/api';

const LoginScreen: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [loginMode, setLoginMode] = useState<'code' | 'password'>('code');
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const loginByCode = useAuthStore((s) => s.loginByCode);
  const loginByPassword = useAuthStore((s) => s.loginByPassword);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startCountdown = () => {
    setCountdown(60);
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  // 卸载时清理倒计时 interval，防止句柄泄漏逃逸到组件生命周期外
  // (2026-08-16 F1198: --detectOpenHandles 定位泄漏源，与 WalletScreen.ext3 同类)
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const handleSendCode = async () => {
    if (!phone.trim() || phone.trim().length < 11) {
      setError('请输入正确的手机号');
      return;
    }
    setSendingCode(true);
    setError(null);
    try {
      await authApi.sendCode({ phone: phone.trim() });
      startCountdown();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '发送验证码失败');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setSendingCode(false);
    }
  };

  const handleLogin = async () => {
    if (!phone.trim() || phone.trim().length < 11) {
      setError('请输入正确的手机号');
      return;
    }

    if (loginMode === 'code') {
      if (!code.trim()) {
        setError('请输入验证码');
        return;
      }
    } else {
      if (!password.trim()) {
        setError('请输入密码');
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      if (loginMode === 'code') {
        await loginByCode(phone.trim(), code.trim());
      } else {
        await loginByPassword(phone.trim(), password);
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '登录失败');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    // F299: AuthStack为headerShown:false导航器, 无原生header兜顶,
    // iOS刘海屏状态栏会叠在登录表单上方 → 根容器消费顶部安全区
    <SafeAreaView style={styles.safeRoot} edges={['top', 'left', 'right']}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
        <View style={styles.content}>
          <View style={styles.header}>
            <Text style={styles.appName}>天链充电</Text>
            <Text style={styles.subtitle}>新能源充电服务平台</Text>
          </View>

          <View style={styles.form}>
            {error && (
              <View style={styles.errorContainer}>
                <Text style={styles.errorText}>{error}</Text>
              </View>
            )}

            <View style={styles.inputGroup}>
              <Text style={styles.label}>手机号</Text>
              <TextInput
                style={styles.input}
                placeholder="请输入手机号"
                placeholderTextColor="#999"
                value={phone}
                onChangeText={(text) => {
                  setPhone(text);
                  setError(null);
                }}
                keyboardType="phone-pad"
                maxLength={11}
                editable={!loading}
              />
            </View>

            {loginMode === 'code' ? (
              <View style={styles.inputGroup}>
                <Text style={styles.label}>验证码</Text>
                <View style={styles.codeRow}>
                  <TextInput
                    style={[styles.input, styles.codeInput]}
                    placeholder="请输入验证码"
                    placeholderTextColor="#999"
                    value={code}
                    onChangeText={(text) => {
                      setCode(text);
                      setError(null);
                    }}
                    keyboardType="number-pad"
                    maxLength={6}
                    autoComplete="sms-otp"
                    textContentType="oneTimeCode"
                    editable={!loading}
                  />
                  <TouchableOpacity accessibilityRole="button"
                    style={[
                      styles.codeBtn,
                      (countdown > 0 || sendingCode) && styles.codeBtnDisabled,
                    ]}
                    onPress={handleSendCode}
                    disabled={countdown > 0 || sendingCode}
                    activeOpacity={0.7}
                  >
                    {sendingCode ? (
                      <ActivityIndicator color="#fff" size="small" />
                    ) : (
                      <Text style={styles.codeBtnText}>
                        {countdown > 0 ? `${countdown}s` : '获取验证码'}
                      </Text>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            ) : (
              <View style={styles.inputGroup}>
                <Text style={styles.label}>密码</Text>
                <TextInput
                  style={styles.input}
                  placeholder="请输入密码"
                  placeholderTextColor="#999"
                  value={password}
                  onChangeText={(text) => {
                    setPassword(text);
                    setError(null);
                  }}
                  secureTextEntry
                  autoComplete="password"
                  textContentType="password"
                  editable={!loading}
                />
              </View>
            )}

            <TouchableOpacity accessibilityRole="button"
              style={[styles.loginButton, loading && styles.loginButtonDisabled]}
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.7}
            >
              {loading ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.loginButtonText}>登 录</Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity accessibilityRole="button"
              style={styles.modeSwitch}
              onPress={() => {
                setLoginMode(loginMode === 'code' ? 'password' : 'code');
                setError(null);
              }}
            >
              <Text style={styles.modeSwitchText}>
                {loginMode === 'code' ? '使用密码登录' : '使用验证码登录'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeRoot: {
    flex: 1,
    backgroundColor: '#1a73e8',
  },
  container: {
    flex: 1,
    backgroundColor: '#1a73e8',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  header: {
    alignItems: 'center',
    marginBottom: 48,
  },
  appName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: 'rgba(255,255,255,0.8)',
  },
  form: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
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
  inputGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: '#333',
    backgroundColor: '#fafafa',
  },
  codeRow: {
    flexDirection: 'row',
    gap: 10,
  },
  codeInput: {
    flex: 1,
  },
  codeBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  codeBtnDisabled: {
    opacity: 0.6,
  },
  codeBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
  },
  loginButton: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  loginButtonDisabled: {
    opacity: 0.6,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  modeSwitch: {
    alignItems: 'center',
    marginTop: 16,
  },
  modeSwitchText: {
    fontSize: 14,
    color: '#1a73e8',
  },
});

export default LoginScreen;
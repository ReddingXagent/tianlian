import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/AppNavigator';
import { authApi } from '../services/api';

type Props = NativeStackScreenProps<RootStackParamList, 'Login'>;

type LoginMode = 'code' | 'password';

const LoginScreen: React.FC<Props> = ({ navigation }) => {
  const [mode, setMode] = useState<LoginMode>('code');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // 检查登录状态
  useEffect(() => {
    checkLoginStatus();
  }, []);

  // 倒计时
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const checkLoginStatus = async () => {
    try {
      const isLoggedIn = await authApi.isLoggedIn();
      if (isLoggedIn) {
        navigation.replace('Main');
      }
    } catch (error) {
      console.error('Check login status error:', error);
    }
  };

  // 发送验证码
  const handleSendCode = async () => {
    if (!phone || phone.length !== 11) {
      Alert.alert('提示', '请输入正确的手机号');
      return;
    }

    try {
      setLoading(true);
      await authApi.sendCode(phone);
      setCountdown(60);
      Alert.alert('成功', '验证码已发送');
    } catch (error: any) {
      Alert.alert('发送失败', error.response?.data?.message || '请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 登录
  const handleLogin = async () => {
    // 验证输入
    if (mode === 'code') {
      if (!phone || phone.length !== 11) {
        Alert.alert('提示', '请输入正确的手机号');
        return;
      }
      if (!code || code.length < 4) {
        Alert.alert('提示', '请输入验证码');
        return;
      }
    } else {
      if (!username.trim()) {
        Alert.alert('提示', '请输入账号');
        return;
      }
      if (!password.trim()) {
        Alert.alert('提示', '请输入密码');
        return;
      }
    }

    try {
      setLoading(true);
      
      if (mode === 'code') {
        await authApi.loginByCode(phone, code);
      } else {
        await authApi.loginByPassword(username, password);
      }
      
      navigation.replace('Main');
    } catch (error: any) {
      Alert.alert('登录失败', error.response?.data?.message || '请检查输入信息');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Text style={styles.logo}>🔧</Text>
          <Text style={styles.title}>天链工程师</Text>
          <Text style={styles.subtitle}>光储充智能运维平台</Text>
        </View>

        <View style={styles.tabContainer}>
          <TouchableOpacity
            style={[styles.tab, mode === 'code' && styles.tabActive]}
            onPress={() => setMode('code')}
          >
            <Text style={[styles.tabText, mode === 'code' && styles.tabTextActive]}>
              验证码登录
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, mode === 'password' && styles.tabActive]}
            onPress={() => setMode('password')}
          >
            <Text style={[styles.tabText, mode === 'password' && styles.tabTextActive]}>
              账号密码登录
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.form}>
          {mode === 'code' ? (
            <>
              <TextInput
                style={styles.input}
                placeholder="请输入手机号"
                value={phone}
                onChangeText={setPhone}
                keyboardType="phone-pad"
                maxLength={11}
                placeholderTextColor="#999"
              />
              <View style={styles.codeRow}>
                <TextInput
                  style={[styles.input, styles.codeInput]}
                  placeholder="请输入验证码"
                  value={code}
                  onChangeText={setCode}
                  keyboardType="number-pad"
                  maxLength={6}
                  placeholderTextColor="#999"
                />
                <TouchableOpacity
                  style={[styles.codeButton, countdown > 0 && styles.codeButtonDisabled]}
                  onPress={handleSendCode}
                  disabled={countdown > 0 || loading}
                >
                  <Text style={styles.codeButtonText}>
                    {countdown > 0 ? `${countdown}秒` : '获取验证码'}
                  </Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <>
              <TextInput
                style={styles.input}
                placeholder="请输入账号"
                value={username}
                onChangeText={setUsername}
                autoCapitalize="none"
                placeholderTextColor="#999"
              />
              <TextInput
                style={styles.input}
                placeholder="请输入密码"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                placeholderTextColor="#999"
              />
            </>
          )}

          <TouchableOpacity
            style={[styles.loginButton, loading && styles.loginButtonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            <Text style={styles.loginButtonText}>
              {loading ? '登录中...' : '登 录'}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>登录即表示同意</Text>
          <TouchableOpacity>
            <Text style={styles.link}>《用户协议》</Text>
          </TouchableOpacity>
          <Text style={styles.footerText}>和</Text>
          <TouchableOpacity>
            <Text style={styles.link}>《隐私政策》</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 80,
    paddingBottom: 40,
  },
  header: {
    alignItems: 'center',
    marginBottom: 40,
  },
  logo: {
    fontSize: 60,
    marginBottom: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
  },
  tabContainer: {
    flexDirection: 'row',
    marginBottom: 24,
    backgroundColor: '#e8e8e8',
    borderRadius: 8,
    padding: 4,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
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
  form: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  input: {
    height: 50,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    paddingHorizontal: 16,
    fontSize: 16,
    backgroundColor: '#fafafa',
    marginBottom: 16,
  },
  codeRow: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  codeInput: {
    flex: 1,
    marginRight: 12,
  },
  codeButton: {
    width: 120,
    height: 50,
    backgroundColor: '#1890ff',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  codeButtonDisabled: {
    backgroundColor: '#b3d9ff',
  },
  codeButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  loginButton: {
    height: 50,
    backgroundColor: '#1890ff',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
  },
  loginButtonDisabled: {
    backgroundColor: '#b3d9ff',
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  footerText: {
    fontSize: 12,
    color: '#999',
  },
  link: {
    fontSize: 12,
    color: '#1890ff',
  },
});

export default LoginScreen;
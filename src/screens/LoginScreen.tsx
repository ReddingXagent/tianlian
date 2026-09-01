import React from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { useLogin } from '../hooks/useLogin';
import { useTheme } from '../hooks/useTheme';

export default function LoginScreen() {
  const { colors } = useTheme();
  const { username, password, loading, error, setUsername, setPassword, login } = useLogin();

  const handleLogin = async () => {
    const success = await login();
    if (!success && error) {
      Alert.alert('登录失败', error);
    }
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.logoContainer}>
        <Text style={[styles.logoText, { color: colors.primary }]}>天链</Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>站长管理平台</Text>
      </View>

      <View style={styles.form}>
        <TextInput
          style={[styles.input, {
            backgroundColor: colors.inputBg,
            color: colors.textPrimary,
            borderColor: colors.border,
          }]}
          placeholder="用户名"
          placeholderTextColor={colors.textMuted}
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TextInput
          style={[styles.input, {
            backgroundColor: colors.inputBg,
            color: colors.textPrimary,
            borderColor: colors.border,
          }]}
          placeholder="密码"
          placeholderTextColor={colors.textMuted}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
        />

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled, { backgroundColor: colors.primary }]}
          onPress={handleLogin}
          disabled={loading}
         accessibilityRole="button">
          {loading ? (
            <ActivityIndicator color={colors.onPrimary} />
          ) : (
            <Text style={[styles.buttonText, { color: colors.onPrimary }]}>登录</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logoText: {
    fontSize: 48,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 18,
  },
  form: {
    gap: 16,
  },
  input: {
    borderRadius: 12,
    paddingVertical: 16,
    paddingHorizontal: 20,
    fontSize: 16,
    borderWidth: 1,
  },
  button: {
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    fontSize: 18,
    fontWeight: 'bold',
  },
});

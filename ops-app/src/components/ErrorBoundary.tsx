/**
 * ErrorBoundary — 捕获子组件树渲染异常，展示友好降级 UI
 * 生产环境必备：防止 React 渲染崩溃导致整个 APP 白屏/红屏
 * F1366 维度27: 对齐 station-app __DEV__ 错误详情面板
 * 深色模式: 类组件无法用 hook, 降级UI经 getErrorColors() 按系统主题取色
 */
import React, { Component, ErrorInfo, ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Appearance } from 'react-native';
import { colorsLight, colorsDark } from '../theme/colors';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/** 系统主题 → 语义色（类组件渲染时读取一次; 主题切换后重试/重渲染时刷新） */
function getErrorColors() {
  return Appearance.getColorScheme() === 'dark' ? colorsDark : colorsLight;
}

class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      const c = getErrorColors();
      return (
        <View style={[styles.container, { backgroundColor: c.pageBg }]}>
          <Text style={styles.icon}>😵</Text>
          <Text style={[styles.title, { color: c.textPrimary }]}>页面出错了</Text>
          <Text style={[styles.message, { color: c.textSecondary }]}>
            {this.state.error?.message || '发生了未知错误'}
          </Text>
          {__DEV__ && this.state.error && (
            <ScrollView style={[styles.errorDetail, { backgroundColor: c.errorBg }]} contentContainerStyle={styles.errorDetailContent}>
              <Text style={[styles.errorText, { color: c.error }]}>
                {this.state.error.name}: {this.state.error.message}
              </Text>
              <Text style={[styles.errorStack, { color: c.textSecondary }]}>{this.state.error.stack}</Text>
            </ScrollView>
          )}
          <TouchableOpacity style={[styles.button, { backgroundColor: c.primary }]} onPress={this.handleReset} accessibilityRole="button">
            <Text style={[styles.buttonText, { color: c.onPrimary }]}>重试</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  icon: {
    fontSize: 48,
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 8,
  },
  message: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  errorDetail: {
    maxHeight: 200,
    width: '100%',
    borderRadius: 8,
    marginBottom: 24,
  },
  errorDetailContent: {
    padding: 12,
  },
  errorText: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
    fontFamily: 'monospace',
  },
  errorStack: {
    fontSize: 11,
    fontFamily: 'monospace',
    lineHeight: 16,
  },
  button: {
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 32,
  },
  buttonText: {
    fontSize: 15,
    fontWeight: '600',
  },
});

export default ErrorBoundary;

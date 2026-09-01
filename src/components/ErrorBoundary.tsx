/**
 * 全局错误边界 — 捕获子树渲染异常，防止白屏崩溃
 * 生产环境可一键反馈回首页
 */
import React, { Component, ErrorInfo, ReactNode } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Appearance } from 'react-native';
import { colorsLight, colorsDark } from '../theme/colors';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/** 系统主题 → 语义色（类组件渲染时读取一次） */
function getErrorColors() {
  return Appearance.getColorScheme() === 'dark' ? colorsDark : colorsLight;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // 生产环境可接入日志上报
    console.error('[ErrorBoundary]', error, errorInfo.componentStack);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      const c = getErrorColors();
      return (
        <View style={[styles.container, { backgroundColor: c.pageBg }]}>
          <Text style={styles.icon}>😵</Text>
          <Text style={[styles.title, { color: c.textPrimary }]}>应用出现问题</Text>
          <Text style={[styles.message, { color: c.textSecondary }]}>
            抱歉，应用遇到了意外错误。请尝试重启或返回首页。
          </Text>
          {__DEV__ && this.state.error && (
            <ScrollView style={[styles.errorDetail, { backgroundColor: c.errorBg }]} contentContainerStyle={styles.errorDetailContent}>
              <Text style={[styles.errorText, { color: c.error }]}>
                {this.state.error.name}: {this.state.error.message}
              </Text>
              <Text style={[styles.errorStack, { color: c.textSecondary }]}>{this.state.error.stack}</Text>
            </ScrollView>
          )}
          <View style={styles.buttonRow}>
            <TouchableOpacity style={[styles.primaryButton, { backgroundColor: c.primary }]} onPress={this.handleReset} accessibilityRole="button">
              <Text style={[styles.primaryButtonText, { color: c.onPrimary }]}>重试</Text>
            </TouchableOpacity>
          </View>
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
    fontSize: 56,
    marginBottom: 20,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 8,
  },
  message: {
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 24,
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
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  primaryButton: {
    paddingHorizontal: 32,
    paddingVertical: 12,
    borderRadius: 8,
  },
  primaryButtonText: {
    fontSize: 15,
    fontWeight: '600',
  },
});

export default ErrorBoundary;

/**
 * ErrorBoundary — 捕获子组件树渲染异常，展示友好降级 UI
 * 生产环境必备：防止 React 渲染崩溃导致整个 APP 白屏/红屏
 * F1366 维度27: 对齐 station-app __DEV__ 错误详情面板
 */
import React, { Component, ErrorInfo, ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
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
      return (
        <View style={styles.container}>
          <Text style={styles.icon}>😵</Text>
          <Text style={styles.title}>页面出错了</Text>
          <Text style={styles.message}>
            {this.state.error?.message || '发生了未知错误'}
          </Text>
          {__DEV__ && this.state.error && (
            <ScrollView style={styles.errorDetail} contentContainerStyle={styles.errorDetailContent}>
              <Text style={styles.errorText}>
                {this.state.error.name}: {this.state.error.message}
              </Text>
              <Text style={styles.errorStack}>{this.state.error.stack}</Text>
            </ScrollView>
          )}
          <TouchableOpacity style={styles.button} onPress={this.handleReset} accessibilityRole="button">
            <Text style={styles.buttonText}>重试</Text>
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
    backgroundColor: '#f5f6fa',
    padding: 32,
  },
  icon: {
    fontSize: 48,
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  message: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  errorDetail: {
    maxHeight: 200,
    width: '100%',
    backgroundColor: '#fff5f5',
    borderRadius: 8,
    marginBottom: 24,
  },
  errorDetailContent: {
    padding: 12,
  },
  errorText: {
    fontSize: 13,
    color: '#cc3300',
    fontWeight: '600',
    marginBottom: 8,
    fontFamily: 'monospace',
  },
  errorStack: {
    fontSize: 11,
    color: '#999',
    fontFamily: 'monospace',
    lineHeight: 16,
  },
  button: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 32,
  },
  buttonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
});

export default ErrorBoundary;

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { colorsLight } from '../theme/colors';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * 全局错误边界 — 捕获子组件渲染异常，防止白屏崩溃。
 * F1366 维度27: 对齐 station-app __DEV__ 错误详情面板
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo.componentStack);
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
          <Text style={styles.icon}>⚠️</Text>
          <Text style={styles.title}>出错了</Text>
          <Text style={styles.message}>
            {this.state.error?.message || '应用遇到未知错误'}
          </Text>
          {__DEV__ && this.state.error && (
            <ScrollView style={styles.errorDetail} contentContainerStyle={styles.errorDetailContent}>
              <Text style={styles.errorText}>
                {this.state.error.name}: {this.state.error.message}
              </Text>
              <Text style={styles.errorStack}>{this.state.error.stack}</Text>
            </ScrollView>
          )}
          <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={this.handleReset}>
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
    backgroundColor: '#fff',
    padding: 24,
  },
  icon: {
    fontSize: 48,
    marginBottom: 12,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  message: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    marginBottom: 24,
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
    backgroundColor: colorsLight.primary,
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
  },
  buttonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '500',
  },
});

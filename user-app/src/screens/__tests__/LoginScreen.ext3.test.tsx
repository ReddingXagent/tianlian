import React from 'react';
import { KeyboardAvoidingView, Platform } from 'react-native';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import LoginScreen from '../LoginScreen';

// ── Mock auth store ──────────────────────────────────────────
jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      loginByCode: jest.fn().mockResolvedValue(undefined),
      loginByPassword: jest.fn().mockResolvedValue(undefined),
    }),
}));

describe('LoginScreen.ext3 — Android平台KAV分支', () => {
  it('KeyboardAvoidingView behavior 在 Android 上为 height', () => {
    // jest RN preset 默认 Platform.OS=ios(behavior=padding 已被基础用例覆盖),
    // 此处切 android 覆盖三元表达式 false 分支
    const origOS = Platform.OS;
    (Platform as { OS: string }).OS = 'android';
    try {
      const { UNSAFE_getByType } = render(
        <SafeAreaProvider>
          <LoginScreen />
        </SafeAreaProvider>
      );
      const kav = UNSAFE_getByType(KeyboardAvoidingView);
      expect(kav.props.behavior).toBe('height');
    } finally {
      (Platform as { OS: string }).OS = origOS;
    }
  });
});

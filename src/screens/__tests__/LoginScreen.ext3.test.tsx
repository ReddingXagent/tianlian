/**
 * LoginScreen 扩展测试3 — Platform.OS branch闭环
 * 目标: branch 94.73% → 100% (L55 Platform.OS==='ios'?'padding':'height')
 * 实勘: jest RN preset默认Platform.OS='ios'(padding臂已有56次), 真缺的是android臂('height')。
 * 手法: 直接改写react-native导出的Platform.OS为'android'再渲染, finally还原;
 *        不用isolateModules(会重require react造成双React实例hooks崩)。
 *        断言=UNSAFE_getByType直查KeyboardAvoidingView实例读behavior prop(F1223 fail-fast先例)。
 */
import { render } from '@testing-library/react-native';
import type { KeyboardAvoidingViewProps } from 'react-native';

const mockLogin = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: (selector: (s: { login: jest.Mock }) => unknown) => selector({ login: mockLogin }),
}));

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

import LoginScreen from '../LoginScreen';
import { KeyboardAvoidingView, Platform } from 'react-native';

const getBehavior = (): unknown => {
  const { UNSAFE_root } = render(<LoginScreen />);
  const kav = UNSAFE_root.findAllByType(KeyboardAvoidingView);
  // fail-fast直查: 找不到即抛错, 不走if守卫(F1206方法论)
  expect(kav.length).toBeGreaterThan(0);
  return (kav[0].props as KeyboardAvoidingViewProps).behavior;
};

describe('LoginScreen.ext3 — Platform.OS branch', () => {
  const prevOS = Platform.OS;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    Platform.OS = prevOS;
  });

  it('renders behavior="padding" on ios (jest preset default)', () => {
    Platform.OS = 'ios';
    expect(getBehavior()).toBe('padding');
  });

  it('renders behavior="height" on android', () => {
    Platform.OS = 'android';
    expect(getBehavior()).toBe('height');
  });
});

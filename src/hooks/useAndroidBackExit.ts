import { useEffect, useRef } from 'react';
import { BackHandler, ToastAndroid } from 'react-native';

/** Home tab 双击退出的时间窗口(ms) */
export const DOUBLE_BACK_EXIT_MS = 2000;

export const EXIT_TOAST_TEXT = '再按一次退出';

type NavStateLike = { index: number };

/**
 * 结构化最小接口(而非 NavigationProp<ParamListBase>):
 * react-navigation 的 useNavigation() 返回 getState() 可能为 undefined 的类型,
 * 与 NavigationProp 不兼容; 结构化后调用点零 cast 直传。
 */
export interface BackExitNavigation {
  getParent(): { getState(): NavStateLike | undefined } | undefined;
  getState(): NavStateLike | undefined;
  navigate(name: string): void;
}

/**
 * Android 硬件返回键 UX 治理 hook(移动端真缺口补齐)。
 *
 * 此前行为: React Navigation 默认 — 任意 root tab 按硬件返回直接 exitApp,
 * 用户在订单/扫码/我的页随手一按就误退 app(充电中误退尤甚)。
 *
 * 治理策略(标准 tab app 约定):
 * - 有 stack 详情页盖住 tabs(parent stack index > 0): 不拦截, 原生 back 弹栈
 * - 非 Home root tab: back → 先跳 Home, 不退出
 * - Home tab: 首按 toast "再按一次退出", 2s 内再按才 exitApp
 *
 * iOS 无硬件返回键, BackHandler 在 iOS 上为 no-op, 无需平台分支。
 */
export function useAndroidBackExit(navigation: BackExitNavigation): void {
  const lastPressRef = useRef(0);

  useEffect(() => {
    const onBackPress = (): boolean => {
      // 详情页盖住 tabs 时不拦截 — 让原生 back 弹 stack
      const parent = navigation.getParent();
      const parentState = parent?.getState();
      if (parentState && parentState.index > 0) {
        return false;
      }
      // 非 Home root tab → 先回 Home; state 未知时不拦截(退回原生行为)
      const tabState = navigation.getState();
      if (!tabState) {
        return false;
      }
      if (tabState.index !== 0) {
        navigation.navigate('Home');
        return true;
      }
      // Home tab: 双击退出
      const now = Date.now();
      if (now - lastPressRef.current < DOUBLE_BACK_EXIT_MS) {
        BackHandler.exitApp();
        return true;
      }
      lastPressRef.current = now;
      ToastAndroid.show(EXIT_TOAST_TEXT, ToastAndroid.SHORT);
      return true;
    };

    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [navigation]);
}

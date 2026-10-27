import { useColorScheme } from 'react-native';
import { colorsLight, colorsDark, ThemeColors, ColorScheme } from '../theme/colors';

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  colors: ThemeColors;
}

/**
 * useTheme — 深色模式只读提供方 (station-app 深色优先版)
 *
 * 系统主题来自 prefers-color-scheme (useColorScheme)。
 * dark 套=出厂视觉零变化; light 套=新增浅色皮肤。
 */
export function useTheme(): Theme {
  const system = useColorScheme();
  const scheme: ColorScheme = system === 'dark' ? 'dark' : 'light';
  return {
    scheme,
    isDark: scheme === 'dark',
    colors: scheme === 'dark' ? colorsDark : colorsLight,
  };
}

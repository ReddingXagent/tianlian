import { useColorScheme } from 'react-native';
import { colorsLight, colorsDark, ThemeColors, ColorScheme } from '../theme/colors';

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  colors: ThemeColors;
}

/**
 * useTheme — 深色模式只读提供方 (对齐 user-app F2783 模式)
 *
 * 系统主题来自 prefers-color-scheme (useColorScheme)。
 * 管理端暂未引入显式切换开关; 本 hook 仅基于系统主题提供语义色。
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

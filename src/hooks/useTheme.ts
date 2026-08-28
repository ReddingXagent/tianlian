import { useColorScheme } from 'react-native';
import { useBrandingStore } from '../store/brandingStore';
import { colorsLight, colorsDark, ThemeColors, ColorScheme } from '../theme/colors';

const FALLBACK_BRAND = '#00A86B';

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  colors: ThemeColors;
  brand: string;
}

/**
 * useTheme — 深色模式只读提供方 (F2783 Phase 1)
 *
 * 系统主题来自 prefers-color-scheme (useColorScheme), 品牌色来自 brandingStore。
 * 管理端暂未引入显式切换开关; 本 hook 仅基于系统主题 + 品牌色提供语义色。
 * 品牌色多租户机制(brandingStore.themeColor)已兼容, 供后续品牌化组件消费。
 */
export function useTheme(): Theme {
  const system = useColorScheme();
  const brand = useBrandingStore((s) => s.branding?.themeColor) ?? FALLBACK_BRAND;
  const scheme: ColorScheme = system === 'dark' ? 'dark' : 'light';
  return {
    scheme,
    isDark: scheme === 'dark',
    colors: scheme === 'dark' ? colorsDark : colorsLight,
    brand,
  };
}
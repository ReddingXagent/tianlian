/**
 * 主题上下文 - 暗色/亮色模式切换
 * 持久化到 localStorage，通过 CSS 变量驱动主题变化
 */
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';

type ThemeMode = 'light' | 'dark';

interface ThemeContextType {
  mode: ThemeMode;
  isDark: boolean;
  toggleTheme: () => void;
  setTheme: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  mode: 'light',
  isDark: false,
  toggleTheme: () => {},
  setTheme: () => {},
});

const STORAGE_KEY = 'tianlian-theme-mode';

/** 从 localStorage 读取偏好 */
function getInitialTheme(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch {}
  // 遵循系统偏好
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

/** 将 CSS 暗色变量应用到 document */
function applyThemeVars(mode: ThemeMode) {
  const root = document.documentElement;

  if (mode === 'dark') {
    root.setAttribute('data-theme', 'dark');
    // 暗色模式 CSS 变量
    root.style.setProperty('--bg-primary', '#1a1a2e');
    root.style.setProperty('--bg-secondary', '#16162a');
    root.style.setProperty('--bg-card', '#222244');
    root.style.setProperty('--bg-layout', '#0f0f23');
    root.style.setProperty('--text-primary', '#e8e8f0');
    root.style.setProperty('--text-secondary', '#a0a0b8');
    root.style.setProperty('--text-tertiary', '#686890');
    root.style.setProperty('--border-color', '#333355');
    root.style.setProperty('--shadow-sm', '0 1px 3px rgba(0,0,0,0.3)');
    root.style.setProperty('--shadow-md', '0 2px 8px rgba(0,0,0,0.4)');
    root.style.setProperty('--shadow-lg', '0 4px 16px rgba(0,0,0,0.5)');
    root.style.setProperty('--primary-color', '#ff7a5c');
    root.style.setProperty('--primary-hover', '#ff9a7a');
    root.style.setProperty('--primary-active', '#ff5a36');
  } else {
    root.removeAttribute('data-theme');
    // 亮色模式恢复默认
    root.style.setProperty('--bg-primary', '#faf5f4');
    root.style.setProperty('--bg-secondary', '#f5f0ef');
    root.style.setProperty('--bg-card', '#ffffff');
    root.style.setProperty('--bg-layout', '#faf5f4');
    root.style.setProperty('--text-primary', '#1e1918');
    root.style.setProperty('--text-secondary', '#777270');
    root.style.setProperty('--text-tertiary', '#a6a1a0');
    root.style.setProperty('--border-color', '#e6e1e0');
    root.style.setProperty('--shadow-sm', '0 1px 3px rgba(30,25,24,0.04)');
    root.style.setProperty('--shadow-md', '0 2px 8px rgba(30,25,24,0.06)');
    root.style.setProperty('--shadow-lg', '0 4px 16px rgba(30,25,24,0.08)');
    root.style.setProperty('--primary-color', '#ff5a36');
    root.style.setProperty('--primary-hover', '#ff7a5c');
    root.style.setProperty('--primary-active', '#e54d2e');
  }
}

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    applyThemeVars(mode);
    try { localStorage.setItem(STORAGE_KEY, mode); } catch {}
  }, [mode]);

  // 监听系统主题变化
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      // 仅当用户没有手动设置过时跟随系统
      if (!localStorage.getItem(STORAGE_KEY)) {
        setMode(e.matches ? 'dark' : 'light');
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const toggleTheme = useCallback(() => {
    setMode(prev => prev === 'light' ? 'dark' : 'light');
  }, []);

  const setTheme = useCallback((m: ThemeMode) => {
    setMode(m);
  }, []);

  return (
    <ThemeContext.Provider value={{ mode, isDark: mode === 'dark', toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

/** 获取主题上下文 */
export const useTheme = (): ThemeContextType => {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return ctx;
};

export default ThemeContext;

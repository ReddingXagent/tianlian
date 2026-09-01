import { renderHook } from '@testing-library/react-native';
import * as RN from 'react-native';
import { useTheme } from '../useTheme';
import { colorsDark, colorsLight } from '../../theme/colors';

describe('useTheme', () => {
  let colorSchemeSpy: jest.SpyInstance;

  beforeEach(() => {
    colorSchemeSpy = jest.spyOn(RN, 'useColorScheme').mockReturnValue('light');
  });

  afterEach(() => {
    colorSchemeSpy.mockRestore();
  });

  it('exposes light skin when system scheme is light', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.scheme).toBe('light');
    expect(result.current.isDark).toBe(false);
    expect(result.current.colors).toBe(colorsLight);
  });

  it('exposes factory-dark skin when system scheme is dark', () => {
    colorSchemeSpy.mockReturnValue('dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.scheme).toBe('dark');
    expect(result.current.isDark).toBe(true);
    expect(result.current.colors).toBe(colorsDark);
  });

  it('falls back to light when system scheme is null', () => {
    colorSchemeSpy.mockReturnValue(null);
    const { result } = renderHook(() => useTheme());
    expect(result.current.scheme).toBe('light');
  });
});

describe('theme palette integrity', () => {
  it('light and dark expose the same semantic keys', () => {
    expect(Object.keys(colorsLight).sort()).toEqual(Object.keys(colorsDark).sort());
  });

  it('dark skin preserves factory brand teal and navy bg (零变化原则)', () => {
    expect(colorsDark.primary).toBe('#4ECDC4');
    expect(colorsDark.pageBg).toBe('#0f0f23');
    expect(colorsDark.cardBg).toBe('#1a1a2e');
  });

  it('light teal is darkened for contrast on white (#4ECDC4 on white = 1.9:1 unreadable)', () => {
    expect(colorsLight.primary).toBe('#0e8a80');
    expect(colorsLight.pageBg).toBe('#f5f6fa');
  });
});

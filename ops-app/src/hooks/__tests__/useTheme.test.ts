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

  it('defaults to light when system scheme is light', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.scheme).toBe('light');
    expect(result.current.isDark).toBe(false);
    expect(result.current.colors).toBe(colorsLight);
  });

  it('switches to dark when system scheme is dark', () => {
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
    expect(result.current.isDark).toBe(false);
  });
});

describe('theme palette integrity', () => {
  it('light and dark expose the same semantic keys', () => {
    expect(Object.keys(colorsLight).sort()).toEqual(Object.keys(colorsDark).sort());
  });

  it('primary is identical across schemes (brand color)', () => {
    expect(colorsLight.primary).toBe(colorsDark.primary);
  });
});

import { renderHook } from '@testing-library/react-native';
import * as RN from 'react-native';
import { useTheme } from '../useTheme';
import { colorsDark, colorsLight } from '../../theme/colors';
import { useBrandingStore } from '../../store/brandingStore';

describe('useTheme', () => {
  let colorSchemeSpy: jest.SpyInstance;

  beforeEach(() => {
    colorSchemeSpy = jest.spyOn(RN, 'useColorScheme').mockReturnValue('light');
    useBrandingStore.setState({ branding: null, loading: false, error: null });
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

  it('returns fallback brand when branding not loaded', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.brand).toBe('#00A86B');
  });

  it('returns tenant brand color when branding loaded', () => {
    useBrandingStore.setState({
      branding: {
        tenantId: 't1',
        operatorName: 'x',
        themeColor: '#FF5733',
        source: 'operator',
      },
      loading: false,
      error: null,
    });
    const { result } = renderHook(() => useTheme());
    expect(result.current.brand).toBe('#FF5733');
  });
});
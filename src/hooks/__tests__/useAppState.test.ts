import { renderHook, act } from '@testing-library/react-native';
import { AppState, AppStateStatus } from 'react-native';

jest.mock('react-native', () => ({
  AppState: {
    currentState: 'active',
    addEventListener: jest.fn(),
  },
}));

import { useAppState } from '../useAppState';

describe('useAppState', () => {
  let stateHandler: (state: AppStateStatus) => void;

  beforeEach(() => {
    stateHandler = jest.fn();
    (AppState.addEventListener as jest.Mock).mockImplementation((event: string, cb: (s: AppStateStatus) => void) => {
      if (event === 'change') stateHandler = cb;
      return { remove: jest.fn() };
    });
    (AppState as unknown as { currentState: string }).currentState = 'active';
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('returns active state initially', () => {
    const { result } = renderHook(() => useAppState());
    expect(result.current.appState).toBe('active');
    expect(result.current.isForeground()).toBe(true);
  });

  it('calls onForeground when app returns to foreground', () => {
    const onForeground = jest.fn();
    renderHook(() => useAppState({ onForeground }));

    act(() => {
      stateHandler('background');
    });

    act(() => {
      stateHandler('active');
    });

    expect(onForeground).toHaveBeenCalledTimes(1);
  });

  it('calls onBackground when app goes to background', () => {
    const onBackground = jest.fn();
    renderHook(() => useAppState({ onBackground }));

    act(() => {
      stateHandler('background');
    });

    expect(onBackground).toHaveBeenCalledTimes(1);
  });

  it('does not call onForeground on initial mount', () => {
    const onForeground = jest.fn();
    renderHook(() => useAppState({ onForeground }));
    expect(onForeground).not.toHaveBeenCalled();
  });

  it('handles inactive state on iOS (multitask switcher)', () => {
    const onForeground = jest.fn();
    renderHook(() => useAppState({ onForeground }));

    act(() => {
      stateHandler('inactive');
    });

    act(() => {
      stateHandler('active');
    });

    expect(onForeground).toHaveBeenCalledTimes(1);
  });
});

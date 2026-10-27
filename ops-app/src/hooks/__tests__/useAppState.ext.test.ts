/**
 * useAppState 扩展测试 — branch覆盖率提升
 * 目标: 91.66% → 100% branches
 * 覆盖: inactive→background 不触发 callbacks, 无options时默认行为
 */
import { renderHook, act } from '@testing-library/react-native';
import { AppState, AppStateStatus } from 'react-native';

jest.mock('react-native', () => ({
  AppState: {
    currentState: 'active',
    addEventListener: jest.fn(),
  },
}));

import { useAppState } from '../useAppState';

describe('useAppState.ext — branch coverage', () => {
  let stateHandler: (state: AppStateStatus) => void;

  beforeEach(() => {
    stateHandler = jest.fn();
    (AppState.addEventListener as jest.Mock).mockImplementation(
      (event: string, cb: (s: AppStateStatus) => void) => {
        if (event === 'change') stateHandler = cb;
        return { remove: jest.fn() };
      }
    );
    (AppState as unknown as { currentState: string }).currentState = 'active';
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('calls onBackground on active→inactive (iOS multitask)', () => {
    const onBackground = jest.fn();
    renderHook(() => useAppState({ onBackground }));

    // active → inactive triggers onBackground (prev===active, nextState===inactive)
    act(() => stateHandler('inactive'));
    expect(onBackground).toHaveBeenCalledTimes(1);
  });

  it('does not call callbacks on inactive→background transition', () => {
    const onForeground = jest.fn();
    const onBackground = jest.fn();
    // Start from inactive state
    (AppState as unknown as { currentState: string }).currentState = 'inactive';
    renderHook(() => useAppState({ onForeground, onBackground }));

    // inactive → background: prev!==active so onBackground not triggered
    act(() => stateHandler('background'));
    expect(onBackground).not.toHaveBeenCalled();
    expect(onForeground).not.toHaveBeenCalled();
  });

  it('does not call onForeground on active→active (no state change)', () => {
    const onForeground = jest.fn();
    renderHook(() => useAppState({ onForeground }));

    act(() => stateHandler('active'));
    expect(onForeground).not.toHaveBeenCalled();
  });

  it('works with no options (undefined callbacks)', () => {
    const { result } = renderHook(() => useAppState());

    act(() => stateHandler('background'));
    act(() => stateHandler('active'));

    expect(result.current.appState).toBe('active');
    expect(result.current.isForeground()).toBe(true);
  });

  it('isForeground returns false when appState is background', () => {
    const { result } = renderHook(() => useAppState());

    act(() => stateHandler('background'));
    expect(result.current.isForeground()).toBe(false);
  });

  it('isForeground returns false when appState is inactive', () => {
    const { result } = renderHook(() => useAppState());

    act(() => stateHandler('inactive'));
    expect(result.current.isForeground()).toBe(false);
  });
});

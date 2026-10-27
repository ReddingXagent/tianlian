/**
 * useNetworkStatus ext3 — catch block (lines 45-46) in loadNetInfo
 * When require('@react-native-community/netinfo') throws, cachedNetInfo=null is returned.
 * Also: native refresh path with NetInfo=null returns early.
 */
import { renderHook, act } from '@testing-library/react-native';

// Track Platform.OS
const mockPlatformOS = { current: 'ios' as 'ios' | 'web' };

jest.mock('react-native', () => ({
  Platform: {
    get OS() { return mockPlatformOS.current; },
  },
}));

// Make require('@react-native-community/netinfo') throw so loadNetInfo's catch block fires
jest.mock('@react-native-community/netinfo', () => {
  throw new Error('Cannot find module');
});

import { useNetworkStatus } from '../useNetworkStatus';

describe('useNetworkStatus.ext3 — loadNetInfo catch block', () => {
  afterEach(() => {
    mockPlatformOS.current = 'ios';
  });

  it('native: loadNetInfo catch → cachedNetInfo=null, setup returns early (lines 45-46)', async () => {
    mockPlatformOS.current = 'ios';

    const { result, unmount } = renderHook(() => useNetworkStatus());

    // Wait for any async operations to settle
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 200));
    });

    // State remains at initial since NetInfo threw and setup returned early
    expect(result.current.isConnected).toBe(true);
    expect(result.current.isOffline).toBe(false);

    unmount();
  });

  it('native: refresh returns early when NetInfo is null (catch path)', async () => {
    mockPlatformOS.current = 'ios';

    const { result } = renderHook(() => useNetworkStatus());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
    });

    // refresh should not throw and state stays at initial
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.isConnected).toBe(true);
  });
});

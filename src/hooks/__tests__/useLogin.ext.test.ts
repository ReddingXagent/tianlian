import { renderHook, act } from '@testing-library/react-native';
import { authApi } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { useLogin } from '../useLogin';

jest.mock('../../services/api', () => ({
  authApi: {
    sendCode: jest.fn(),
  },
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn((selector) =>
    selector({
      loginByCode: jest.fn(),
      loginByPassword: jest.fn(),
    })
  ),
}));

describe('useLogin countdown completion', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should clear interval and reset countdown to 0 when countdown reaches 1', async () => {
    (authApi.sendCode as jest.Mock).mockResolvedValue({});
    const { result } = renderHook(() => useLogin());

    act(() => result.current.setPhone('13800138000'));
    await act(async () => {
      await result.current.handleSendCode();
    });

    expect(result.current.countdown).toBe(60);

    // Advance 59 intervals to reach countdown=1, then the 60th tick triggers prev<=1 → return 0
    act(() => {
      jest.advanceTimersByTime(59000);
    });

    expect(result.current.countdown).toBe(1);

    // This tick triggers prev<=1 → clearInterval + return 0
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(result.current.countdown).toBe(0);
  });
});

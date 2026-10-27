import { renderHook, act } from '@testing-library/react-native';
import { chargingApi } from '../../services/api';
import { useOrderStore } from '../../store/orderStore';
import { useScan } from '../useScan';
import { ScanResult } from '../../types';

jest.mock('../../services/api', () => ({
  chargingApi: {
    scan: jest.fn(),
  },
}));

jest.mock('../../store/orderStore', () => ({
  useOrderStore: jest.fn((selector) =>
    selector({
      startCharging: jest.fn(),
    })
  ),
}));

const mockScanResult: ScanResult = {
  id: 1,
  code: 'A001',
  name: '充电桩A-01',
  status: 'idle',
  stationName: '中心站',
} as never;

describe('useScan', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should have correct initial state', () => {
    const { result } = renderHook(() => useScan());

    expect(result.current.codeInput).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.lastResult).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.starting).toBe(false);
    expect(result.current.cameraOpen).toBe(false);
  });

  it('should update codeInput and clear error', () => {
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('A001'));
    expect(result.current.codeInput).toBe('A001');
  });

  it('should validate empty code on handleScan', async () => {
    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.handleScan();
    });

    expect(result.current.error).toBe('请输入充电桩编码');
    expect(chargingApi.scan).not.toHaveBeenCalled();
  });

  it('should scan successfully', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('A001'));

    await act(async () => {
      await result.current.handleScan();
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.lastResult).toEqual(mockScanResult);
    expect(result.current.codeInput).toBe(''); // cleared after success
    expect(result.current.error).toBeNull();
  });

  it('should handle scan axios error', async () => {
    (chargingApi.scan as jest.Mock).mockRejectedValue({
      response: { data: { message: '充电桩不存在' } },
    });
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('BAD'));

    await act(async () => {
      await result.current.handleScan();
    });

    expect(result.current.error).toBe('充电桩不存在');
  });

  it('should handle scan network error', async () => {
    (chargingApi.scan as jest.Mock).mockRejectedValue(new Error('Network'));
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('A001'));

    await act(async () => {
      await result.current.handleScan();
    });

    expect(result.current.error).toBe('网络错误，请检查网络连接');
  });

  it('should lookup code directly', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.lookupCode('A001');
    });

    expect(result.current.lastResult).toEqual(mockScanResult);
  });

  it('should handle camera scan', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCameraOpen(true));

    await act(async () => {
      result.current.handleCameraScan('CAM001');
    });

    expect(result.current.cameraOpen).toBe(false);
    expect(result.current.lastResult).toEqual(mockScanResult);
  });

  it('should return undefined when no lastResult on startCharging', async () => {
    const { result } = renderHook(() => useScan());

    let res: unknown;
    await act(async () => {
      res = await result.current.handleStartCharging();
    });

    expect(res).toBeUndefined();
  });

  it('should reject when charger status is not idle', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({
      data: { ...mockScanResult, status: 'charging' } as never,
    });
    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.lookupCode('A001');
    });

    await act(async () => {
      await result.current.handleStartCharging();
    });

    expect(result.current.error).toBe('该充电桩当前不可用');
  });

  it('should start charging successfully', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const mockStartCharging = jest.fn().mockResolvedValue('charging');
    (useOrderStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ startCharging: mockStartCharging })
    );

    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.lookupCode('A001');
    });

    let status: unknown;
    await act(async () => {
      status = await result.current.handleStartCharging();
    });

    expect(mockStartCharging).toHaveBeenCalledWith(1);
    expect(status).toBe('charging');
    expect(result.current.starting).toBe(false);
  });

  it('should handle start charging axios error', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const mockStartCharging = jest.fn().mockRejectedValue({
      response: { data: { message: '充电桩被占用' } },
    });
    (useOrderStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ startCharging: mockStartCharging })
    );

    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.lookupCode('A001');
    });

    await act(async () => {
      try {
        await result.current.handleStartCharging();
      } catch {
        // expected
      }
    });

    expect(result.current.error).toBe('充电桩被占用');
    expect(result.current.starting).toBe(false);
  });

  it('should handle start charging network error', async () => {
    (chargingApi.scan as jest.Mock).mockResolvedValue({ data: mockScanResult });
    const mockStartCharging = jest.fn().mockRejectedValue(new Error('Network'));
    (useOrderStore as unknown as jest.Mock).mockImplementation((selector: (s: unknown) => unknown) =>
      selector({ startCharging: mockStartCharging })
    );

    const { result } = renderHook(() => useScan());

    await act(async () => {
      await result.current.lookupCode('A001');
    });

    await act(async () => {
      try {
        await result.current.handleStartCharging();
      } catch {
        // expected
      }
    });

    expect(result.current.error).toBe('网络错误，请检查网络连接');
  });

  it('should reset error', () => {
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('A001'));
    // trigger an error
    act(() => {
      void result.current.handleScan();
    });
    act(() => result.current.resetError());
    expect(result.current.error).toBeNull();
  });
});

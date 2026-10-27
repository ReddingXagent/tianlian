/**
 * useScan Hook 测试
 */
import { renderHook, act } from '@testing-library/react-native';

jest.mock('../../services/api', () => ({
  scanApi: {
    scan: jest.fn(),
    checkIn: jest.fn(),
  },
}));

import { useScan } from '../useScan';
import { scanApi } from '../../services/api';

const mockScan = scanApi.scan as jest.MockedFunction<typeof scanApi.scan>;
const mockCheckIn = scanApi.checkIn as jest.MockedFunction<typeof scanApi.checkIn>;

const MOCK_SCAN_RESULT = { id: 1, type: 'device', name: '充电桩A' };

describe('useScan', () => {
  beforeEach(() => jest.clearAllMocks());

  it('初始状态', () => {
    const { result } = renderHook(() => useScan());
    expect(result.current.codeInput).toBe('');
    expect(result.current.loading).toBe(false);
    expect(result.current.lastResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('空输入 → 错误"请输入设备/站点编码"', async () => {
    const { result } = renderHook(() => useScan());
    await act(async () => { await result.current.handleScan(); });
    expect(result.current.error).toBe('请输入设备/站点编码');
    expect(mockScan).not.toHaveBeenCalled();
  });

  it('成功扫描: result设置+codeInput清空', async () => {
    mockScan.mockResolvedValueOnce({ data: MOCK_SCAN_RESULT } as never);
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('DEV001'));
    await act(async () => { await result.current.handleScan(); });
    expect(mockScan).toHaveBeenCalledWith('DEV001');
    expect(result.current.lastResult).toEqual(MOCK_SCAN_RESULT);
    expect(result.current.codeInput).toBe('');
    expect(result.current.error).toBeNull();
  });

  it('扫描失败(axios错误): 显示服务端message', async () => {
    mockScan.mockRejectedValueOnce({
      response: { data: { message: '设备不存在' } },
    } as never);
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('BAD'));
    await act(async () => { await result.current.handleScan(); });
    expect(result.current.error).toBe('设备不存在');
  });

  it('扫描失败(网络错误): 显示网络错误', async () => {
    mockScan.mockRejectedValueOnce(new Error('Network') as never);
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('DEV001'));
    await act(async () => { await result.current.handleScan(); });
    expect(result.current.error).toBe('网络错误，请检查网络连接');
  });

  it('handleQuickInput 设置code并清除错误', async () => {
    const { result } = renderHook(() => useScan());
    await act(async () => { await result.current.handleScan(); });
    expect(result.current.error).not.toBeNull();
    act(() => result.current.handleQuickInput('QUICK1'));
    expect(result.current.codeInput).toBe('QUICK1');
    expect(result.current.error).toBeNull();
  });

  it('performCheckIn: 无lastResult时返回false', async () => {
    const { result } = renderHook(() => useScan());
    let success;
    await act(async () => { success = await result.current.performCheckIn(); });
    expect(success).toBe(false);
    expect(mockCheckIn).not.toHaveBeenCalled();
  });

  it('performCheckIn: 有lastResult时成功', async () => {
    mockCheckIn.mockResolvedValueOnce(undefined as never);
    mockScan.mockResolvedValueOnce({ data: MOCK_SCAN_RESULT } as never);
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('DEV001'));
    await act(async () => { await result.current.handleScan(); });
    expect(result.current.lastResult).not.toBeNull();
    let success;
    await act(async () => { success = await result.current.performCheckIn(); });
    expect(success).toBe(true);
    expect(mockCheckIn).toHaveBeenCalledWith(1);
  });

  it('performCheckIn: checkIn失败返回false', async () => {
    mockCheckIn.mockRejectedValueOnce(new Error('Network') as never);
    mockScan.mockResolvedValueOnce({ data: MOCK_SCAN_RESULT } as never);
    const { result } = renderHook(() => useScan());
    act(() => result.current.setCodeInput('DEV001'));
    await act(async () => { await result.current.handleScan(); });
    let success;
    await act(async () => { success = await result.current.performCheckIn(); });
    expect(success).toBe(false);
  });
});

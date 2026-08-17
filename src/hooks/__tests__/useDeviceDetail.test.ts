/**
 * useDeviceDetail Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useDeviceDetail } from '../useDeviceDetail';

jest.mock('../../services/api', () => ({
  deviceApi: {
    getDetail: jest.fn(),
    getTelemetry: jest.fn(),
    controlDevice: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { deviceApi } from '../../services/api';

const mockDevice = { id: 1, name: '充电桩A', status: 'online' };
const mockTelemetry = { temperature: 35, voltage: 220, current: 10 };

describe('useDeviceDetail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (deviceApi.getDetail as jest.Mock).mockResolvedValue({ data: mockDevice });
    (deviceApi.getTelemetry as jest.Mock).mockResolvedValue({ data: mockTelemetry });
    (deviceApi.controlDevice as jest.Mock).mockResolvedValue({ data: { message: 'ok' } });
  });

  it('初始加载: device+telemetry获取成功', async () => {
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 1 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.device).toEqual(mockDevice);
    expect(result.current.telemetry).toEqual(mockTelemetry);
    expect(result.current.error).toBeNull();
  });

  it('telemetry失败 → device仍成功, telemetry=null', async () => {
    (deviceApi.getTelemetry as jest.Mock).mockRejectedValue(new Error('timeout'));
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 1 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.device).toEqual(mockDevice);
    expect(result.current.telemetry).toBeNull();
  });

  it('device失败 → error设置', async () => {
    (deviceApi.getDetail as jest.Mock).mockRejectedValue(new Error('404'));
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 999 }));
    await waitFor(() => expect(result.current.error).toBe('加载设备详情失败'));
    expect(result.current.device).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('refresh → refreshing先true后false', async () => {
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 1 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.fetchData(true); });
    expect(result.current.refreshing).toBe(false);
  });

  it('controlDevice → 成功返回success+message', async () => {
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 1 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    let res: { success: boolean; message?: string } | undefined;
    await act(async () => { res = await result.current.controlDevice('restart'); });
    expect(res?.success).toBe(true);
    expect(res?.message).toBe('ok');
    expect(deviceApi.controlDevice).toHaveBeenCalledWith(1, 'restart');
    expect(result.current.controlling).toBe(false);
  });

  it('controlDevice → 失败返回success=false', async () => {
    (deviceApi.controlDevice as jest.Mock).mockRejectedValue(new Error('denied'));
    const { result } = renderHook(() => useDeviceDetail({ deviceId: 1 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    let res: { success: boolean; message?: string } | undefined;
    await act(async () => { res = await result.current.controlDevice('reboot'); });
    expect(res?.success).toBe(false);
    expect(result.current.controlling).toBe(false);
  });
});

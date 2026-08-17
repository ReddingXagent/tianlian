/**
 * useAlarms Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useAlarms } from '../useAlarms';

jest.mock('../../services/api', () => ({
  alarmApi: {
    getList: jest.fn(),
  },
}));

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { stationId: 1 } }),
}));

// eslint-disable-next-line import/first
import { alarmApi } from '../../services/api';

const mockAlarms = [
  { id: 1, title: '告警1', status: 'active', level: 'critical', deviceId: 1 },
  { id: 2, title: '告警2', status: 'resolved', level: 'warning', deviceId: 2 },
];

describe('useAlarms', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (alarmApi.getList as jest.Mock).mockResolvedValue({ data: { items: mockAlarms, total: 2 } });
  });

  it('初始加载: 告警列表获取成功', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.alarms).toHaveLength(2);
    expect(result.current.filter).toBe('all');
  });

  it('stationId从route.params获取', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(alarmApi.getList).toHaveBeenCalledWith(
      expect.objectContaining({ stationId: 1 })
    );
  });

  it('filter=all → 不传status', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(alarmApi.getList).toHaveBeenCalledWith(
      expect.not.objectContaining({ status: expect.anything() })
    );
  });

  it('filter=active → 传status=active', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setFilter('active'));
    await waitFor(() => {
      expect(alarmApi.getList).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'active' })
      );
    });
  });

  it('filter=resolved → 传status=resolved', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setFilter('resolved'));
    await waitFor(() => {
      expect(alarmApi.getList).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'resolved' })
      );
    });
  });

  it('refresh → 重新加载', async () => {
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const callsBefore = (alarmApi.getList as jest.Mock).mock.calls.length;
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect((alarmApi.getList as jest.Mock).mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it('API失败 → 静默处理, loading=false', async () => {
    (alarmApi.getList as jest.Mock).mockRejectedValue(new Error('500'));
    const { result } = renderHook(() => useAlarms());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.alarms).toEqual([]);
  });
});

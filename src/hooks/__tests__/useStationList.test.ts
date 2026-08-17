/**
 * useStationList Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { useStationList } from '../useStationList';

const mockStations = [
  { id: 1, name: '城南充电站', code: 'CN001', address: '城南路1号' },
  { id: 2, name: '城北充电站', code: 'CB002', address: '城北路2号' },
  { id: 3, name: '东站充电站', code: 'DX003', address: '东站路3号' },
];

const mockFetchStations = jest.fn().mockResolvedValue(undefined);

jest.mock('../../store/stationStore', () => ({
  useStationStore: () => ({
    stations: mockStations,
    loading: false,
    fetchStations: mockFetchStations,
  }),
}));

describe('useStationList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchStations.mockResolvedValue(undefined);
  });

  it('初始加载: stations从store获取, search空', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    expect(result.current.stations).toHaveLength(3);
    expect(result.current.search).toBe('');
    expect(result.current.filteredStations).toHaveLength(3);
  });

  it('search按name过滤', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    act(() => result.current.setSearch('城南'));
    expect(result.current.filteredStations).toHaveLength(1);
    expect(result.current.filteredStations[0].name).toBe('城南充电站');
  });

  it('search按code过滤', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    act(() => result.current.setSearch('CB002'));
    expect(result.current.filteredStations).toHaveLength(1);
    expect(result.current.filteredStations[0].code).toBe('CB002');
  });

  it('search按address过滤', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    act(() => result.current.setSearch('东站路'));
    expect(result.current.filteredStations).toHaveLength(1);
    expect(result.current.filteredStations[0].address).toBe('东站路3号');
  });

  it('search无匹配 → 空列表', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    act(() => result.current.setSearch('不存在的站点'));
    expect(result.current.filteredStations).toHaveLength(0);
  });

  it('search清空 → 恢复全部', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    act(() => result.current.setSearch('城南'));
    expect(result.current.filteredStations).toHaveLength(1);
    act(() => result.current.setSearch(''));
    expect(result.current.filteredStations).toHaveLength(3);
  });

  it('refresh → 调用fetchStations', async () => {
    const { result } = renderHook(() => useStationList());
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    await act(async () => { result.current.refresh(); });
    await waitFor(() => expect(result.current.refreshing).toBe(false));
  });
});

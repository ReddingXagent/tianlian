/**
 * ext3: 覆盖率提升 — useStationList address?.includes(search) ?? false 分支
 * 
 * 覆盖分支:
 * - useStationList line 39: address为undefined时 ?. 链短路 + ?? false 走false分支
 * - useStationList line 39: address有值但不匹配搜索词时 ?? false 走false分支
 * - useStationList line 39: address有值且匹配搜索词时 ?. 走true分支
 */
import React from 'react';
import { render, waitFor } from '@testing-library/react-native';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// eslint-disable-next-line import/first
import { useStationStore } from '../store/stationStore';
// eslint-disable-next-line import/first
import { useStationList } from '../hooks/useStationList';

const renderHook = <T,>(fn: () => T) => {
  const result: { current: T } = { current: null as unknown as T };
  const TestComp = () => {
    result.current = fn();
    return null;
  };
  render(React.createElement(TestComp));
  return result;
};

describe('useStationList ext3: address ?? false分支', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('搜索匹配address: ?? true分支(地址包含搜索词)', async () => {
    useStationStore.setState({
      stations: [
        { id: 1, name: '站点A', code: 'S001', address: '北京市朝阳区' },
        { id: 2, name: '站点B', code: 'S002', address: '上海市浦东新区' },
      ],
      loading: false,
      fetchStations: jest.fn(),
    });

    const result = renderHook(() => useStationList());
    await waitFor(() => {
      expect(result.current.stations.length).toBe(2);
    });

    result.current.setSearch('朝阳');
    expect(result.current.filteredStations.length).toBe(1);
    expect(result.current.filteredStations[0].name).toBe('站点A');
  });

  it('address为undefined: ?? false分支不报错', async () => {
    useStationStore.setState({
      stations: [
        { id: 1, name: '站点A', code: 'S001', address: undefined },
        { id: 2, name: '站点B', code: 'S002', address: '上海市浦东新区' },
      ],
      loading: false,
      fetchStations: jest.fn(),
    });

    const result = renderHook(() => useStationList());
    await waitFor(() => {
      expect(result.current.stations.length).toBe(2);
    });

    result.current.setSearch('浦东');
    expect(result.current.filteredStations.length).toBe(1);
    expect(result.current.filteredStations[0].name).toBe('站点B');
  });

  it('搜索不匹配任何字段: address有值但不匹配, ?? false走false分支', async () => {
    useStationStore.setState({
      stations: [
        { id: 1, name: '站点A', code: 'S001', address: '北京市朝阳区' },
        { id: 2, name: '站点B', code: 'S002', address: '上海市浦东新区' },
      ],
      loading: false,
      fetchStations: jest.fn(),
    });

    const result = renderHook(() => useStationList());
    await waitFor(() => {
      expect(result.current.stations.length).toBe(2);
    });

    result.current.setSearch('广州');
    expect(result.current.filteredStations.length).toBe(0);
  });
});

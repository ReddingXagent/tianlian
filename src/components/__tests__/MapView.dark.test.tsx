import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import * as RN from 'react-native';
import MapView from '../MapView';
import { Station } from '../../types';

/**
 * MapView 深色主题覆盖补测 — useTheme 走 useColorScheme，
 * 既有三套测试全部跑亮色侧，createStyles 内 isDark 三元仅单侧执行；
 * 同轮补 3 列网格 col=2 与多行 row 中段/末段定位分支（需 ≥7 站点触发）。
 */

jest.spyOn(RN, 'useColorScheme').mockReturnValue('dark');

const makeStation = (id: number, overrides: Partial<Station> = {}): Station => ({
  id,
  name: `站点${id}`,
  address: `地址${id}`,
  status: 'online',
  latitude: 39.9,
  longitude: 116.4,
  distance: id * 100,
  pricePerKwh: 0.8,
  serviceFee: 0.5,
  totalConnectors: 10,
  availableConnectors: id % 4,
  chargingConnectors: 2,
  isOpen24h: true,
  rating: 4.5,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  ...overrides,
});

describe('MapView 深色主题', () => {
  it('深色模式下渲染空态', () => {
    const { getByText } = render(<MapView stations={[]} />);
    expect(getByText('暂无站点数据')).toBeTruthy();
  });

  it('深色模式下渲染 7 站点触发 3 列×3 行网格全分支', () => {
    const stations = Array.from({ length: 7 }, (_, i) => makeStation(i + 1));
    const { getByText } = render(<MapView stations={stations} />);
    stations.forEach((s) => {
      expect(getByText(s.name)).toBeTruthy();
    });
    expect(getByText('7 个站点')).toBeTruthy();
  });

  it('深色模式下选中态高亮与 onPress 回调', () => {
    const onPress = jest.fn();
    const stations = [makeStation(1), makeStation(2)];
    const { getByText } = render(
      <MapView stations={stations} selectedStationId={1} onStationPress={onPress} />
    );
    fireEvent.press(getByText('站点1'));
    expect(onPress).toHaveBeenCalledWith(stations[0]);
  });

  it('深色模式下站点无 distance 时不渲染距离标签', () => {
    const stations = [makeStation(1, { distance: undefined })];
    const { getByText, queryByText } = render(<MapView stations={stations} />);
    expect(getByText('站点1')).toBeTruthy();
    expect(queryByText('100米')).toBeNull();
  });
});

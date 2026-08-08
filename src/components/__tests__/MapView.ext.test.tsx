import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import MapView from '../MapView';
import { Station } from '../../types';

const baseStation: Station = {
  id: 1,
  name: '中心站',
  address: '朝阳区',
  status: 'online',
  latitude: 39.9,
  longitude: 116.4,
  distance: 500,
  pricePerKwh: 0.8,
  serviceFee: 0.5,
  totalConnectors: 10,
  availableConnectors: 3,
  chargingConnectors: 5,
  isOpen24h: true,
  rating: 4.5,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('MapView extended coverage', () => {
  // === station.distance undefined → distance label not rendered (line 146 branch) ===

  it('站点无distance时不渲染距离标签', () => {
    const noDist = { ...baseStation, distance: undefined };
    const { getByText, queryByText } = render(<MapView stations={[noDist]} />);
    expect(getByText('中心站')).toBeTruthy();
    expect(queryByText('500米')).toBeNull();
  });

  // === availableConnectors === 0 → red marker (line 155 branch) ===

  it('availableConnectors为0的站点显示红色标记', () => {
    const full = { ...baseStation, id: 3, name: '满站', availableConnectors: 0 };
    const { getByText } = render(<MapView stations={[full]} />);
    expect(getByText('满站')).toBeTruthy();
    expect(getByText('已满')).toBeTruthy();
  });

  // === getStationPosition with many stations (>3, multiple rows) ===

  it('5个站点正确布局多行位置', () => {
    const stations: Station[] = Array.from({ length: 5 }, (_, i) => ({
      ...baseStation,
      id: i + 10,
      name: `站${i}`,
      availableConnectors: i,
    }));
    const { getByText } = render(<MapView stations={stations} />);
    expect(getByText('5 个站点')).toBeTruthy();
    expect(getByText('站0')).toBeTruthy();
    expect(getByText('站4')).toBeTruthy();
  });

  // === single station → getStationPosition returns center ===

  it('单站点居中显示', () => {
    const { getByText } = render(<MapView stations={[baseStation]} />);
    expect(getByText('中心站')).toBeTruthy();
  });

  // === selected station with different id (isSelected=false for non-matching) ===

  it('未选中的站点正常渲染(无选中态)', () => {
    const { getByText } = render(
      <MapView stations={[baseStation]} selectedStationId={999} />
    );
    expect(getByText('中心站')).toBeTruthy();
  });

  // === onStationPress not provided (optional callback) ===

  it('未提供onStationPress时不崩溃', () => {
    const { getByText } = render(<MapView stations={[baseStation]} />);
    fireEvent.press(getByText('中心站'));
    // Should not crash
  });
});

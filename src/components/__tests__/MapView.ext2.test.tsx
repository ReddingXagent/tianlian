import React from 'react';
import { render } from '@testing-library/react-native';
import MapView from '../MapView';
import { Station } from '../../types';

const baseStation: Station = {
  id: 1,
  name: '测试站',
  address: '测试地址',
  latitude: 30,
  longitude: 120,
  pricePerKwh: 1.5,
  serviceFee: 0.5,
  availableConnectors: 2,
  totalConnectors: 4,
  chargingConnectors: 1,
  isOpen24h: true,
  rating: 4.5,
  createdAt: '2025-01-01T00:00:00Z',
  updatedAt: '2025-01-01T00:00:00Z',
  status: 'online',
};

describe('MapView.ext2 — middle row branch coverage', () => {
  // Line 156: yOffset = 0 branch requires row > 0 && row < rows - 1
  // Need ≥7 stations for 3 rows (cols=3, rows=ceil(7/3)=3)
  it('7个站点覆盖中间行yOffset=0分支', () => {
    const stations: Station[] = Array.from({ length: 7 }, (_, i) => ({
      ...baseStation,
      id: i + 100,
      name: `站${i}`,
      availableConnectors: i,
    }));
    const { getByText } = render(<MapView stations={stations} />);
    expect(getByText('7 个站点')).toBeTruthy();
    // Verify all rendered
    expect(getByText('站0')).toBeTruthy();
    expect(getByText('站3')).toBeTruthy();
    expect(getByText('站6')).toBeTruthy();
  });
});

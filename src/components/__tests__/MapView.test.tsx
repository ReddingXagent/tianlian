import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import MapView from '../MapView';
import { Station } from '../../types';

const mockStations: Station[] = [
  {
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
  },
  {
    id: 2,
    name: '南站',
    address: '丰台区',
    status: 'online',
    latitude: 39.86,
    longitude: 116.38,
    distance: 2500,
    pricePerKwh: 0.9,
    serviceFee: 0.4,
    totalConnectors: 8,
    availableConnectors: 0,
    chargingConnectors: 8,
    isOpen24h: true,
    rating: 4.2,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
];

describe('MapView', () => {
  it('renders empty state when no stations', () => {
    const { getByText } = render(<MapView stations={[]} />);
    expect(getByText('暂无站点数据')).toBeTruthy();
  });

  it('renders stations with markers', () => {
    const { getByText } = render(<MapView stations={mockStations} />);
    expect(getByText('中心站')).toBeTruthy();
    expect(getByText('南站')).toBeTruthy();
  });

  it('renders distance labels on markers', () => {
    const { getByText } = render(<MapView stations={mockStations} />);
    expect(getByText('500米')).toBeTruthy();
    expect(getByText('2.5公里')).toBeTruthy();
  });

  it('renders legend with station count', () => {
    const { getByText } = render(<MapView stations={mockStations} />);
    expect(getByText('2 个站点')).toBeTruthy();
    expect(getByText('可用')).toBeTruthy();
    expect(getByText('已满')).toBeTruthy();
  });

  it('calls onStationPress when a marker is pressed', () => {
    const onPress = jest.fn();
    const { getByText } = render(
      <MapView stations={mockStations} onStationPress={onPress} />
    );
    fireEvent.press(getByText('中心站'));
    expect(onPress).toHaveBeenCalledWith(mockStations[0]);
  });

  it('applies selected style to selected station', () => {
    const { getByText } = render(
      <MapView stations={mockStations} selectedStationId={1} />
    );
    // Selected marker should be rendered (we just verify it doesn't crash)
    expect(getByText('中心站')).toBeTruthy();
  });

  it('accepts custom height', () => {
    const { getByText } = render(
      <MapView stations={mockStations} height={400} />
    );
    expect(getByText('中心站')).toBeTruthy();
  });
});
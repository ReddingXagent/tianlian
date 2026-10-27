import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import StationCard from '../StationCard';
import { Station } from '../../types';

const mockStation: Station = {
  id: 1,
  name: '天链充电站-中心站',
  address: '北京市朝阳区建国路88号',
  status: 'online',
  latitude: 39.9042,
  longitude: 116.4074,
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

describe('StationCard', () => {
  it('renders station name and address', () => {
    const { getByText } = render(
      <StationCard station={mockStation} onPress={jest.fn()} />
    );
    expect(getByText('天链充电站-中心站')).toBeTruthy();
    expect(getByText('北京市朝阳区建国路88号')).toBeTruthy();
  });

  it('renders price information', () => {
    const { getByText } = render(
      <StationCard station={mockStation} onPress={jest.fn()} />
    );
    expect(getByText('0.80')).toBeTruthy();
    expect(getByText('0.50')).toBeTruthy();
  });

  it('renders distance in meters when < 1000', () => {
    const { getByText } = render(
      <StationCard station={mockStation} onPress={jest.fn()} />
    );
    expect(getByText('500米')).toBeTruthy();
  });

  it('renders distance in kilometers when >= 1000', () => {
    const farStation = { ...mockStation, distance: 1500 };
    const { getByText } = render(
      <StationCard station={farStation} onPress={jest.fn()} />
    );
    expect(getByText('1.5公里')).toBeTruthy();
  });

  it('shows availability text when available', () => {
    const { getByText } = render(
      <StationCard station={mockStation} onPress={jest.fn()} />
    );
    expect(getByText('可用 3/10')).toBeTruthy();
  });

  it('shows full text when no available connectors', () => {
    const fullStation = { ...mockStation, availableConnectors: 0 };
    const { getByText } = render(
      <StationCard station={fullStation} onPress={jest.fn()} />
    );
    expect(getByText('已满 0/10')).toBeTruthy();
  });

  it('calls onPress when pressed', () => {
    const onPress = jest.fn();
    const { getByText } = render(
      <StationCard station={mockStation} onPress={onPress} />
    );
    fireEvent.press(getByText('天链充电站-中心站'));
    expect(onPress).toHaveBeenCalledWith(mockStation);
  });
});
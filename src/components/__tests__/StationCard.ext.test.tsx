import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import StationCard from '../StationCard';
import { Station } from '../../types';

const baseStation: Station = {
  id: 1,
  name: '测试站',
  address: '测试地址',
  status: 'online',
  latitude: 39.9,
  longitude: 116.4,
  distance: 500,
  pricePerKwh: 0.8,
  serviceFee: 0.4,
  totalConnectors: 10,
  availableConnectors: 3,
  chargingConnectors: 5,
  isOpen24h: true,
  rating: 4.5,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('StationCard.ext — branch coverage', () => {
  // ── distance is 0 (falsy) → distanceText=null, no distance rendered ─
  it('hides distance when station.distance is 0', () => {
    const station = { ...baseStation, distance: 0 };
    const { queryByText } = render(
      <StationCard station={station} onPress={jest.fn()} />,
    );
    // Should not show "0米" — distanceText is null when distance is falsy
    expect(queryByText('0米')).toBeNull();
  });

  // ── distance is undefined → distanceText=null ───────────────
  it('hides distance when station.distance is undefined', () => {
    const station = { ...baseStation, distance: undefined as unknown as number };
    const { queryByText } = render(
      <StationCard station={station} onPress={jest.fn()} />,
    );
    // No distance text at all
    expect(queryByText(/米|公里/)).toBeNull();
  });

  // ── availableConnectors = 0 → 已满 ─────────────────────────
  it('shows 已满 text when no connectors available', () => {
    const station = { ...baseStation, availableConnectors: 0 };
    const { getByText } = render(
      <StationCard station={station} onPress={jest.fn()} />,
    );
    expect(getByText('已满 0/10')).toBeTruthy();
  });

  // ── onPress called with station ────────────────────────────
  it('calls onPress with the full station object on press', () => {
    const onPress = jest.fn();
    const { getByText } = render(
      <StationCard station={baseStation} onPress={onPress} />,
    );
    fireEvent.press(getByText('测试站'));
    expect(onPress).toHaveBeenCalledWith(baseStation);
  });

  // ── renders service fee ────────────────────────────────────
  it('renders both price and service fee', () => {
    const { getByText } = render(
      <StationCard station={baseStation} onPress={jest.fn()} />,
    );
    expect(getByText('0.80')).toBeTruthy();
    expect(getByText('0.40')).toBeTruthy();
  });

  // ── distance in kilometers ─────────────────────────────────
  it('renders distance in km when >= 1000', () => {
    const station = { ...baseStation, distance: 2500 };
    const { getByText } = render(
      <StationCard station={station} onPress={jest.fn()} />,
    );
    expect(getByText('2.5公里')).toBeTruthy();
  });

  // ── total connectors = 0 ───────────────────────────────────
  it('renders 0/0 when total and available are both 0', () => {
    const station = { ...baseStation, totalConnectors: 0, availableConnectors: 0 };
    const { getByText } = render(
      <StationCard station={station} onPress={jest.fn()} />,
    );
    expect(getByText('已满 0/0')).toBeTruthy();
  });

  // ── press on address ───────────────────────────────────────
  it('triggers onPress when pressing on address area', () => {
    const onPress = jest.fn();
    const { getByText } = render(
      <StationCard station={baseStation} onPress={onPress} />,
    );
    fireEvent.press(getByText('测试地址'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

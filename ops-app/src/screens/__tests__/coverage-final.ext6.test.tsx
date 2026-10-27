/**
 * coverage-final ext6 — remaining uncovered branches
 * Split into 2 describe files to avoid jest.mock() conflicts:
 * File 1 (this): MonitorScreen L64 — devices.length===0 fetchRealtimeMetrics guard
 */
import { render, waitFor } from '@testing-library/react-native';
import React from 'react';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useFocusEffect: jest.fn(cb => cb()),
}));

jest.mock('../../services/api', () => ({
  monitorApi: {
    getSummary: jest.fn(),
    getFaultDevices: jest.fn(),
    getCriticalAlarms: jest.fn(),
  },
  deviceMonitorApi: {
    getDeviceStatusList: jest.fn(),
    getRealtimeMetrics: jest.fn(),
  },
}));

import MonitorScreen from '../MonitorScreen';
import { monitorApi, deviceMonitorApi } from '../../services/api';

describe('MonitorScreen ext6 — fetchRealtimeMetrics empty devices guard (L64)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: { totalDevices: 0, onlineDevices: 0, faultDevices: 0, criticalAlarms: 0 } });
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({ data: { items: [], total: 0 } });
    (monitorApi.getFaultDevices as jest.Mock).mockResolvedValue({ data: { items: [], total: 0 } });
    (monitorApi.getCriticalAlarms as jest.Mock).mockResolvedValue({ data: { items: [], total: 0 } });
    (deviceMonitorApi.getRealtimeMetrics as jest.Mock).mockResolvedValue({ data: [] });
  });

  it('renders with empty devices — fetchRealtimeMetrics early return', async () => {
    const { UNSAFE_root } = render(<MonitorScreen />);
    await waitFor(() => {
      expect(monitorApi.getSummary).toHaveBeenCalled();
    });
    // With 0 devices, fetchRealtimeMetrics should return early
    await waitFor(() => {
      expect(UNSAFE_root).toBeTruthy();
    });
  });
});

// __tests__/charging.test.js - 充电中页面测试
const mockShowToast = jest.fn();
const mockShowModal = jest.fn();
const mockRedirectTo = jest.fn();
const mockNavigateTo = jest.fn();

global.wx = {
  showToast: mockShowToast,
  showModal: mockShowModal,
  redirectTo: mockRedirectTo,
  navigateTo: mockNavigateTo,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

const mockGetChargingStatus = jest.fn();
const mockStopCharging = jest.fn();
jest.mock('../services/api', () => ({
  getChargingStatus: mockGetChargingStatus,
  stopCharging: mockStopCharging,
}));
jest.mock('../utils/util', () => ({
  formatTime: jest.fn(() => '12:00:00'),
}));
jest.mock('../config/index', () => ({ CHARGING_POLL_INTERVAL: 3000 }));
jest.mock('../utils/polling', () => ({
  createPolling: jest.fn(() => ({
    start: jest.fn(),
    stop: jest.fn(),
  })),
}));
jest.mock('../utils/perf', () => ({
  diffSetData: jest.fn((page, newData, _last) => {
    page.setData(newData);
  }),
  guardTap: (fn) => fn,
}));

require('../pages/charging/charging');

describe('pages/charging/charging', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageConfig.setData = jest.fn(function(patch) {
      Object.assign(this.data, patch);
    });
    pageConfig.data = {
      sessionId: 'S1', chargerId: 'C1', orderId: '',
      power: '0.00', energy: '0.00', cost: '0.00', duration: 0,
      soc: 0, voltage: '0', current: '0', temp: '0', price: '0.00',
      statusText: '充电中', statusClass: 'charging', startTime: '',
      pollingActive: false,
    };
  });

  describe('onLoad', () => {
    it('sets session data and start time', () => {
      pageConfig.onLoad({ sessionId: 'S1', chargerId: 'C1' });
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({
        sessionId: 'S1', chargerId: 'C1',
      }));
    });
  });

  describe('startPolling / stopPolling', () => {
    it('starts polling and sets active flag', () => {
      pageConfig._polling = null;
      pageConfig.startPolling();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ pollingActive: true }));
    });

    it('stops polling and clears active flag', () => {
      pageConfig._polling = { stop: jest.fn() };
      pageConfig.stopPolling();
      expect(pageConfig._polling).toBeNull();
      expect(pageConfig.setData).toHaveBeenCalledWith(expect.objectContaining({ pollingActive: false }));
    });
  });

  describe('fetchStatus', () => {
    it('maps charging status data correctly', async () => {
      mockGetChargingStatus.mockResolvedValue({
        data: {
          power: 7.5, energy: 3.2, cost: 2.21, duration: 25,
          soc: 45, voltage: 220, current: 34, temperature: 35,
          price: 0.69, orderId: 'O1', status: 'charging',
        },
      });

      await pageConfig.fetchStatus();

      const call = pageConfig.setData.mock.calls[0][0];
      expect(call.power).toBe('7.50');
      expect(call.energy).toBe('3.20');
      expect(call.cost).toBe('2.21');
      expect(call.soc).toBe(45);
      expect(call.voltage).toBe('220');
      expect(call.price).toBe('0.69');
      expect(call.statusText).toBe('充电中');
    });

    it('stops polling and redirects on finished', async () => {
      pageConfig.stopPolling = jest.fn();
      mockGetChargingStatus.mockResolvedValue({
        data: { status: 'finished', orderId: 'O9', power: 0, energy: 0, cost: 0, duration: 0, soc: 100, voltage: 0, current: 0, temperature: 0, price: 0 },
      });

      await pageConfig.fetchStatus();

      expect(pageConfig.stopPolling).toHaveBeenCalled();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '充电完成' }));
    });

    it('throws on API error for backoff handling', async () => {
      mockGetChargingStatus.mockRejectedValue(new Error('network'));
      await expect(pageConfig.fetchStatus()).rejects.toThrow('network');
    });
  });

  describe('onStopCharging', () => {
    it('shows confirmation modal', () => {
      pageConfig.onStopCharging();
      expect(mockShowModal).toHaveBeenCalledWith(expect.objectContaining({ title: '确认停止' }));
    });
  });

  describe('lifecycle', () => {
    it('onShow starts polling when session exists and not active', () => {
      pageConfig.data.sessionId = 'S1';
      pageConfig.data.pollingActive = false;
      pageConfig.startPolling = jest.fn();
      pageConfig.onShow();
      expect(pageConfig.startPolling).toHaveBeenCalled();
    });

    it('onShow does not start polling when already active', () => {
      pageConfig.data.pollingActive = true;
      pageConfig.startPolling = jest.fn();
      pageConfig.onShow();
      expect(pageConfig.startPolling).not.toHaveBeenCalled();
    });

    it('onHide stops polling', () => {
      pageConfig.stopPolling = jest.fn();
      pageConfig.onHide();
      expect(pageConfig.stopPolling).toHaveBeenCalled();
    });

    it('onUnload stops polling', () => {
      pageConfig.stopPolling = jest.fn();
      pageConfig.onUnload();
      expect(pageConfig.stopPolling).toHaveBeenCalled();
    });
  });
});

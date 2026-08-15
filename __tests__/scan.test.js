// __tests__/scan.test.js - 扫码页面测试
const mockShowToast = jest.fn();
const mockScanCode = jest.fn();
const mockNavigateTo = jest.fn();
const mockGetStorageSync = jest.fn();
const mockSetStorageSync = jest.fn();

global.wx = {
  scanCode: mockScanCode,
  showToast: mockShowToast,
  navigateTo: mockNavigateTo,
  getStorageSync: mockGetStorageSync,
  setStorageSync: mockSetStorageSync,
};

let pageConfig = null;
global.Page = (config) => { pageConfig = config; };

jest.mock('../services/api', () => ({
  startCharging: jest.fn(),
}));
jest.mock('../utils/util', () => ({
  formatTime: jest.fn(() => '08-13 12:00'),
}));
jest.mock('../utils/perf', () => ({
  guardTap: (fn) => fn,
}));

require('../pages/scan/scan');

describe('pages/scan/scan', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetStorageSync.mockReturnValue([]);
    mockSetStorageSync.mockImplementation(() => undefined);
  });

  describe('parseChargerId', () => {
    it('parses JSON with chargerId', () => {
      const result = pageConfig.parseChargerId('{"chargerId":"CHG001"}');
      expect(result).toBe('CHG001');
    });

    it('parses JSON with id', () => {
      const result = pageConfig.parseChargerId('{"id":"CHG002"}');
      expect(result).toBe('CHG002');
    });

    it('parses URL format', () => {
      const result = pageConfig.parseChargerId('https://ev.com/charger/CHG003');
      expect(result).toBe('CHG003');
    });

    it('parses pure ID', () => {
      const result = pageConfig.parseChargerId('CHARGER_001');
      expect(result).toBe('CHARGER_001');
    });

    it('returns null for invalid input', () => {
      expect(pageConfig.parseChargerId('')).toBeNull();
      expect(pageConfig.parseChargerId(null)).toBeNull();
      expect(pageConfig.parseChargerId('!!!invalid!!!')).toBeNull();
    });
  });

  describe('onLoad / onShow', () => {
    it('loads history on onLoad', () => {
      pageConfig.onLoad();
      expect(mockGetStorageSync).toHaveBeenCalledWith('scanHistory');
      expect(pageConfig.data.history).toEqual([]);
    });

    it('loads history on onShow', () => {
      pageConfig.onShow();
      expect(mockGetStorageSync).toHaveBeenCalledWith('scanHistory');
    });
  });

  describe('onInputChange', () => {
    it('updates chargerId in data', () => {
      pageConfig.setData = jest.fn();
      pageConfig.onInputChange({ detail: { value: 'CHG123' } });
      expect(pageConfig.setData).toHaveBeenCalledWith({ chargerId: 'CHG123' });
    });
  });

  describe('saveHistory', () => {
    it('saves new entry to storage', () => {
      mockGetStorageSync.mockReturnValue([]);
      pageConfig.setData = jest.fn();
      pageConfig.saveHistory('CHG001', { chargerName: 'Pole 1' });

      expect(mockSetStorageSync).toHaveBeenCalledWith('scanHistory',
        expect.arrayContaining([
          expect.objectContaining({ id: 'CHG001', name: 'Pole 1' })
        ])
      );
    });

    it('deduplicates history entries', () => {
      mockGetStorageSync.mockReturnValue([{ id: 'CHG001', name: 'Old', time: '01-01 00:00' }]);
      pageConfig.setData = jest.fn();
      pageConfig.saveHistory('CHG001', { chargerName: 'New' });

      const saved = mockSetStorageSync.mock.calls[0][1];
      expect(saved).toHaveLength(1);
      expect(saved[0].name).toBe('New');
    });

    it('limits history to 10 entries', () => {
      const existing = Array.from({ length: 10 }, (_, i) => ({ id: `CHG${i}`, name: `Old${i}`, time: '' }));
      mockGetStorageSync.mockReturnValue(existing);
      pageConfig.setData = jest.fn();
      pageConfig.saveHistory('NEW001', null);

      const saved = mockSetStorageSync.mock.calls[0][1];
      expect(saved).toHaveLength(10);
      expect(saved[0].id).toBe('NEW001');
    });
  });

  describe('onManualStart', () => {
    it('shows toast when chargerId is empty', () => {
      pageConfig.data.chargerId = '';
      pageConfig.setData = jest.fn();
      pageConfig.onManualStart();
      expect(mockShowToast).toHaveBeenCalledWith(expect.objectContaining({ title: '请输入充电桩编号' }));
    });
  });

  describe('onScanCode', () => {
    it('calls wx.scanCode', () => {
      pageConfig.onScanCode();
      expect(mockScanCode).toHaveBeenCalled();
    });
  });
});

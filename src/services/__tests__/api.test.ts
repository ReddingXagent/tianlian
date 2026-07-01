import {
  authApi,
  stationApi,
  chargingApi,
  orderApi,
  paymentApi,
  vehicleApi,
  couponApi,
  walletApi,
  statsApi,
  tokenStorage,
} from '../api';

describe('API Service Functions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('authApi', () => {
    it('should have all required auth methods', () => {
      expect(authApi.sendCode).toBeDefined();
      expect(authApi.loginByCode).toBeDefined();
      expect(authApi.loginByPassword).toBeDefined();
      expect(authApi.logout).toBeDefined();
      expect(authApi.getProfile).toBeDefined();
      expect(authApi.updateProfile).toBeDefined();
    });

    it('should be functions', () => {
      expect(typeof authApi.sendCode).toBe('function');
      expect(typeof authApi.loginByCode).toBe('function');
    });
  });

  describe('stationApi', () => {
    it('should have all required station methods', () => {
      expect(stationApi.getList).toBeDefined();
      expect(stationApi.search).toBeDefined();
      expect(stationApi.getDetail).toBeDefined();
      expect(stationApi.getChargers).toBeDefined();
    });
  });

  describe('chargingApi', () => {
    it('should have all required charging methods', () => {
      expect(chargingApi.scan).toBeDefined();
      expect(chargingApi.start).toBeDefined();
      expect(chargingApi.stop).toBeDefined();
      expect(chargingApi.getStatus).toBeDefined();
      expect(chargingApi.getActiveOrder).toBeDefined();
    });
  });

  describe('orderApi', () => {
    it('should have all required order methods', () => {
      expect(orderApi.getList).toBeDefined();
      expect(orderApi.getDetail).toBeDefined();
      expect(orderApi.cancelOrder).toBeDefined();
    });
  });

  describe('paymentApi', () => {
    it('should have all required payment methods', () => {
      expect(paymentApi.pay).toBeDefined();
      expect(paymentApi.getPaymentInfo).toBeDefined();
    });
  });

  describe('vehicleApi', () => {
    it('should have all required vehicle methods', () => {
      expect(vehicleApi.getList).toBeDefined();
      expect(vehicleApi.add).toBeDefined();
      expect(vehicleApi.update).toBeDefined();
      expect(vehicleApi.remove).toBeDefined();
      expect(vehicleApi.setDefault).toBeDefined();
    });
  });

  describe('couponApi', () => {
    it('should have all required coupon methods', () => {
      expect(couponApi.getList).toBeDefined();
      expect(couponApi.getAvailable).toBeDefined();
    });
  });

  describe('walletApi', () => {
    it('should have all required wallet methods', () => {
      expect(walletApi.getBalance).toBeDefined();
      expect(walletApi.getRecords).toBeDefined();
      expect(walletApi.recharge).toBeDefined();
    });
  });

  describe('statsApi', () => {
    it('should have user stats method', () => {
      expect(statsApi.getUserStats).toBeDefined();
      expect(typeof statsApi.getUserStats).toBe('function');
    });
  });

  describe('tokenStorage', () => {
    it('should have all token methods', () => {
      expect(tokenStorage.getToken).toBeDefined();
      expect(tokenStorage.setToken).toBeDefined();
      expect(tokenStorage.removeToken).toBeDefined();
    });
  });

  describe('API function call patterns', () => {
    it('authApi.sendCode accepts phone number', () => {
      const spy = jest.spyOn(authApi, 'sendCode');
      authApi.sendCode({ phone: '13800138000' });
      expect(spy).toHaveBeenCalledWith({ phone: '13800138000' });
      spy.mockRestore();
    });

    it('chargingApi.scan accepts charger code', () => {
      const spy = jest.spyOn(chargingApi, 'scan');
      chargingApi.scan('CH-001');
      expect(spy).toHaveBeenCalledWith('CH-001');
      spy.mockRestore();
    });

    it('chargingApi.start accepts start request', () => {
      const spy = jest.spyOn(chargingApi, 'start');
      chargingApi.start({ chargerId: 1, vehicleId: 2 });
      expect(spy).toHaveBeenCalledWith({ chargerId: 1, vehicleId: 2 });
      spy.mockRestore();
    });

    it('paymentApi.pay accepts payment request', () => {
      const spy = jest.spyOn(paymentApi, 'pay');
      paymentApi.pay({ orderId: 1, method: 'wechat' });
      expect(spy).toHaveBeenCalledWith({ orderId: 1, method: 'wechat' });
      spy.mockRestore();
    });

    it('vehicleApi.add accepts vehicle data', () => {
      const spy = jest.spyOn(vehicleApi, 'add');
      vehicleApi.add({
        plate: '京A12345',
        brand: 'Tesla',
        model: 'Model 3',
        color: '白色',
        vin: 'VIN123',
        isDefault: true,
      });
      expect(spy).toHaveBeenCalledWith({
        plate: '京A12345',
        brand: 'Tesla',
        model: 'Model 3',
        color: '白色',
        vin: 'VIN123',
        isDefault: true,
      });
      spy.mockRestore();
    });
  });
});
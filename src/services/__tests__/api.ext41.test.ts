import { chargingOrderApi } from '../api';

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

// Mock axios
jest.mock('axios', () => {
  const mockAxios: Record<string, any> = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return mockAxios;
});

import axios from 'axios';
const mockAxios = axios as jest.Mocked<typeof axios>;

describe('chargingOrderApi (ext41 — GET /charging-orders, GET /charging-orders/{id})', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    it('maps snake_case to camelCase correctly', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                order_no: 'CO202608130001',
                station_id: 1,
                device_id: 1,
                user_id: 1,
                user_type: 'member',
                vehicle_id: 'V001',
                plate_number: '京A12345',
                start_time: '2026-08-13T10:00:00',
                end_time: '2026-08-13T11:00:00',
                duration_minutes: 60,
                start_soc: 20,
                end_soc: 80,
                start_meter: 1000.0,
                end_meter: 1060.0,
                stop_reason: 'full',
                charged_kwh: 41.2,
                electricity_fee: 28.42,
                service_fee: 4.12,
                parking_fee: 0.0,
                idle_penalty: 0.0,
                reservation_fee: 0.0,
                total_amount: 32.54,
                discount_amount: 0.0,
                paid_amount: 0.0,
                payment_status: 'unpaid',
                order_status: 'completed',
                payment_method: null,
                remark: null,
                created_at: '2026-08-13T10:00:00',
                updated_at: '2026-08-13T11:00:00',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786593390,
        },
      });

      const res = await chargingOrderApi.getList({ page: 1, pageSize: 20 });

      expect(mockAxios.get).toHaveBeenCalledWith('/charging-orders', {
        params: { page: 1, page_size: 20, station_id: undefined, order_status: undefined, payment_status: undefined },
      });
      expect(res.data.items).toHaveLength(1);
      const o = res.data.items[0];
      expect(o.id).toBe(1);
      expect(o.orderNo).toBe('CO202608130001');
      expect(o.stationId).toBe(1);
      expect(o.deviceId).toBe(1);
      expect(o.userId).toBe(1);
      expect(o.userType).toBe('member');
      expect(o.vehicleId).toBe('V001');
      expect(o.plateNumber).toBe('京A12345');
      expect(o.startTime).toBe('2026-08-13T10:00:00');
      expect(o.endTime).toBe('2026-08-13T11:00:00');
      expect(o.durationMinutes).toBe(60);
      expect(o.startSoc).toBe(20);
      expect(o.endSoc).toBe(80);
      expect(o.startMeter).toBe(1000.0);
      expect(o.endMeter).toBe(1060.0);
      expect(o.stopReason).toBe('full');
      expect(o.chargedKwh).toBe(41.2);
      expect(o.electricityFee).toBe(28.42);
      expect(o.serviceFee).toBe(4.12);
      expect(o.totalAmount).toBe(32.54);
      expect(o.paymentStatus).toBe('unpaid');
      expect(o.orderStatus).toBe('completed');
      expect(res.data.total).toBe(1);
    });

    it('handles empty list', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 1786593390,
        },
      });

      const res = await chargingOrderApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('handles null/missing fields with defaults', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 2,
                order_no: 'CO002',
                station_id: 1,
                device_id: 1,
                user_id: 1,
                // all optional fields missing
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
          timestamp: 1786593390,
        },
      });

      const res = await chargingOrderApi.getList();
      const o = res.data.items[0];
      expect(o.userType).toBeNull();
      expect(o.vehicleId).toBeNull();
      expect(o.plateNumber).toBeNull();
      expect(o.endTime).toBeNull();
      expect(o.durationMinutes).toBe(0);
      expect(o.chargedKwh).toBe(0);
      expect(o.totalAmount).toBe(0);
      expect(o.paymentStatus).toBe('unpaid');
      expect(o.orderStatus).toBe('pending');
    });

    it('passes filter params correctly', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0, page: 1, page_size: 20 },
          timestamp: 1786593390,
        },
      });

      await chargingOrderApi.getList({ stationId: 5, orderStatus: 'charging', paymentStatus: 'paid' });

      expect(mockAxios.get).toHaveBeenCalledWith('/charging-orders', {
        params: { page: undefined, page_size: undefined, station_id: 5, order_status: 'charging', payment_status: 'paid' },
      });
    });
  });

  describe('getById', () => {
    it('maps detail response correctly', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 1,
            order_no: 'CO202608130001',
            station_id: 1,
            device_id: 1,
            user_id: 1,
            user_type: null,
            vehicle_id: null,
            plate_number: null,
            start_time: '2026-08-13T10:00:00',
            end_time: null,
            duration_minutes: 0,
            start_soc: null,
            end_soc: null,
            start_meter: null,
            end_meter: null,
            stop_reason: null,
            charged_kwh: 0.0,
            electricity_fee: 0.0,
            service_fee: 0.0,
            parking_fee: 0.0,
            idle_penalty: 0.0,
            reservation_fee: 0.0,
            total_amount: 0.0,
            discount_amount: 0.0,
            paid_amount: 0.0,
            payment_status: 'unpaid',
            order_status: 'pending',
            payment_method: null,
            remark: null,
            created_at: '2026-08-13T11:56:21',
            updated_at: '2026-08-13T11:56:21',
          },
          timestamp: 1786593390,
        },
      });

      const res = await chargingOrderApi.getById(1);

      expect(mockAxios.get).toHaveBeenCalledWith('/charging-orders/1');
      expect(res.data).not.toBeNull();
      expect(res.data!.id).toBe(1);
      expect(res.data!.orderNo).toBe('CO202608130001');
      expect(res.data!.chargedKwh).toBe(0);
      expect(res.data!.paymentStatus).toBe('unpaid');
      expect(res.data!.orderStatus).toBe('pending');
    });

    it('returns null for non-existent order', async () => {
      mockAxios.get.mockResolvedValue({
        data: {
          code: 404,
          message: '充电订单不存在',
          data: null,
          timestamp: 1786593390,
        },
      });

      const res = await chargingOrderApi.getById(999);
      expect(res.data).toBeNull();
    });
  });
});

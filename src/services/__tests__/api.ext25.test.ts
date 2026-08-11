import { securityThreatApi } from '../api';
import type { SecurityThreat } from '../../types';

// Mock axios
jest.mock('axios', () => {
  const mockAxios = {
    create: jest.fn(() => mockAxios),
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return mockAxios;
});

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn().mockResolvedValue('mock-token'),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

describe('securityThreatApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    it('should map snake_case fields to camelCase', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                type: 'brute_force',
                source_ip: '10.0.0.1',
                target: 'admin',
                severity: 'high',
                status: 'blocked',
                timestamp: '2026-08-11T18:55:50Z',
              },
              {
                id: 2,
                type: 'sql_injection',
                source_ip: '10.0.0.2',
                target: '/api/v1/users',
                severity: 'critical',
                status: 'blocked',
                timestamp: '2026-08-11T18:55:50Z',
              },
            ],
            total: 2,
          },
        },
      });

      const res = await securityThreatApi.getList();
      expect(res.data.items).toHaveLength(2);
      expect(res.data.items[0]).toEqual<SecurityThreat>({
        id: 1,
        type: 'brute_force',
        sourceIp: '10.0.0.1',
        target: 'admin',
        severity: 'high',
        status: 'blocked',
        timestamp: '2026-08-11T18:55:50Z',
      });
      expect(res.data.items[1].severity).toBe('critical');
      expect(res.data.total).toBe(2);
    });

    it('should handle empty data', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: { items: [], total: 0 },
        },
      });

      const res = await securityThreatApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('should handle null/missing data gracefully', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: null,
        },
      });

      const res = await securityThreatApi.getList();
      expect(res.data.items).toHaveLength(0);
      expect(res.data.total).toBe(0);
    });

    it('should handle missing fields with defaults', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              { id: 5 },
            ],
            total: 1,
          },
        },
      });

      const res = await securityThreatApi.getList();
      expect(res.data.items[0]).toEqual({
        id: 5,
        type: '',
        sourceIp: '',
        target: '',
        severity: 'low',
        status: 'active',
        timestamp: '',
      });
    });

    it('should call correct endpoint', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: { code: 200, message: 'success', data: { items: [], total: 0 } },
      });

      await securityThreatApi.getList();
      expect(axios.get).toHaveBeenCalledWith('/security/threats');
    });

    it('should handle partial items with null fields', async () => {
      const axios = require('axios');
      axios.get.mockResolvedValueOnce({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 3,
                type: 'ddos',
                source_ip: null,
                target: null,
                severity: null,
                status: null,
                timestamp: null,
              },
            ],
            total: 1,
          },
        },
      });

      const res = await securityThreatApi.getList();
      expect(res.data.items[0].sourceIp).toBe('');
      expect(res.data.items[0].target).toBe('');
      expect(res.data.items[0].severity).toBe('low');
      expect(res.data.items[0].status).toBe('active');
      expect(res.data.items[0].timestamp).toBe('');
    });
  });
});

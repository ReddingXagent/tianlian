import { runbookTemplateApi } from '../api';

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

describe('runbookTemplateApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    it('maps snake_case to camelCase correctly', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [
              {
                id: 1,
                name: '逆变器通讯中断',
                category: 'inverter',
                alarm_type: '逆变器通讯中断',
                description: '逆变器通讯中断自动修复',
                step_count: 4,
                auto_steps: 3,
                manual_steps: 1,
                status: 'active',
                version: 1,
                created_at: '2026-07-25T03:33:51.098116',
                updated_at: '2026-07-25T03:33:51.098116',
              },
              {
                id: 10,
                name: '设备离线',
                category: 'general',
                alarm_type: '设备离线',
                description: '设备离线自动排查',
                step_count: 3,
                auto_steps: 2,
                manual_steps: 1,
                status: 'active',
                version: 1,
                created_at: '2026-07-25T03:33:51.098116',
                updated_at: '2026-07-25T03:33:51.098116',
              },
            ],
            total: 10,
          },
        },
      });

      const result = await runbookTemplateApi.getList();
      expect(result.data.items).toHaveLength(2);
      expect(result.data.items[0]).toEqual({
        id: 1,
        name: '逆变器通讯中断',
        category: 'inverter',
        alarmType: '逆变器通讯中断',
        description: '逆变器通讯中断自动修复',
        stepCount: 4,
        autoSteps: 3,
        manualSteps: 1,
        status: 'active',
        version: 1,
        createdAt: '2026-07-25T03:33:51.098116',
        updatedAt: '2026-07-25T03:33:51.098116',
      });
      expect(result.data.total).toBe(10);
      expect(mockAxios.get).toHaveBeenCalledWith('/runbooks/templates');
    });

    it('handles empty list', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: { code: 200, message: 'success', data: { items: [], total: 0 } },
      });
      const result = await runbookTemplateApi.getList();
      expect(result.data.items).toHaveLength(0);
      expect(result.data.total).toBe(0);
    });

    it('handles null/missing fields with defaults', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            items: [{ id: null, name: null }],
            total: 1,
          },
        },
      });
      const result = await runbookTemplateApi.getList();
      expect(result.data.items[0]).toEqual({
        id: 0,
        name: '',
        category: '',
        alarmType: '',
        description: '',
        stepCount: 0,
        autoSteps: 0,
        manualSteps: 0,
        status: 'active',
        version: 1,
        createdAt: '',
        updatedAt: '',
      });
    });

    it('handles missing data field', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: { code: 200, message: 'success', data: null },
      });
      const result = await runbookTemplateApi.getList();
      expect(result.data.items).toHaveLength(0);
      expect(result.data.total).toBe(0);
    });
  });

  describe('getById', () => {
    it('maps detail with steps correctly', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: {
            id: 1,
            name: '逆变器通讯中断',
            category: 'inverter',
            alarm_type: '逆变器通讯中断',
            description: '逆变器通讯中断自动修复',
            step_count: 4,
            auto_steps: 3,
            manual_steps: 1,
            status: 'active',
            version: 1,
            created_at: '2026-07-25T03:33:51.098116',
            updated_at: '2026-07-25T03:33:51.098116',
            steps: [
              {
                step_id: 1,
                action_type: 'remote_command',
                description: '检查逆变器网络连通性',
                command: 'ping -c 3 {device_ip}',
                params: {},
                risk_level: 'low',
                timeout_sec: 15,
                rollback_command: '',
                pre_check: '',
                post_check: '',
                auto_execute: true,
                status: 'pending',
                result: '',
                duration_ms: 0,
                error_message: '',
              },
              {
                step_id: 4,
                action_type: 'create_workorder',
                description: '通讯仍不通, 派发巡检工单',
                command: '',
                params: { urgency: 'high', type: '巡检' },
                risk_level: 'low',
                timeout_sec: 60,
                rollback_command: '',
                pre_check: '',
                post_check: '',
                auto_execute: false,
                status: 'pending',
                result: '',
                duration_ms: 0,
                error_message: '',
              },
            ],
          },
        },
      });

      const result = await runbookTemplateApi.getById(1);
      expect(result.data.id).toBe(1);
      expect(result.data.name).toBe('逆变器通讯中断');
      expect(result.data.category).toBe('inverter');
      expect(result.data.alarmType).toBe('逆变器通讯中断');
      expect(result.data.stepCount).toBe(4);
      expect(result.data.steps).toHaveLength(2);

      const step0 = result.data.steps[0];
      expect(step0.stepId).toBe(1);
      expect(step0.actionType).toBe('remote_command');
      expect(step0.command).toBe('ping -c 3 {device_ip}');
      expect(step0.autoExecute).toBe(true);
      expect(step0.timeoutSec).toBe(15);

      const step1 = result.data.steps[1];
      expect(step1.stepId).toBe(4);
      expect(step1.actionType).toBe('create_workorder');
      expect(step1.autoExecute).toBe(false);
      expect(step1.params).toEqual({ urgency: 'high', type: '巡检' });

      expect(mockAxios.get).toHaveBeenCalledWith('/runbooks/templates/1');
    });

    it('handles null steps with empty array', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { id: 5, name: 'Test' },
        },
      });
      const result = await runbookTemplateApi.getById(5);
      expect(result.data.steps).toHaveLength(0);
      expect(result.data.id).toBe(5);
    });

    it('handles null/missing fields with defaults', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: {
          code: 200,
          message: 'success',
          data: { id: null, name: null, steps: [{ step_id: null }] },
        },
      });
      const result = await runbookTemplateApi.getById(1);
      expect(result.data.id).toBe(0);
      expect(result.data.name).toBe('');
      expect(result.data.steps[0].stepId).toBe(0);
      expect(result.data.steps[0].actionType).toBe('');
      expect(result.data.steps[0].riskLevel).toBe('low');
    });

    it('calls correct endpoint with id', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: { code: 200, message: 'success', data: { id: 42 } },
      });
      await runbookTemplateApi.getById(42);
      expect(mockAxios.get).toHaveBeenCalledWith('/runbooks/templates/42');
    });

    it('handles missing data field', async () => {
      (mockAxios.get as jest.Mock).mockResolvedValue({
        data: { code: 200, message: 'success', data: null },
      });
      const result = await runbookTemplateApi.getById(1);
      expect(result.data.id).toBe(0);
      expect(result.data.steps).toHaveLength(0);
    });
  });
});

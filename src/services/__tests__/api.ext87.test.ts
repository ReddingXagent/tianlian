/**
 * api ext87 — create-body undefined-spread + raw.data ?? {} falsy side + spare-part create sparse
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api, {
  workOrderActionApi,
  sparePartApi,
  alarmRuleApi,
  notificationRuleApi,
  inspectionTemplateApi,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

describe('api ext87 — undefined-field spread falsy sides', () => {
  it('workOrderActionApi.requestSparePart — minimal body (partModel/quantity undefined)', async () => {
    mockAxios.onPost('/work-orders/wo1/spare-parts').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await workOrderActionApi.requestSparePart('wo1', { partName: 'p', reason: 'r' });
    expect(r.data?.id).toBe(0);
    expect(r.data?.status).toBe('requested');
  });

  it('sparePartApi.getList — sparse item {}', async () => {
    mockAxios.onGet('/spare-parts').reply(200, { code: 200, message: 'ok', data: { items: [{}] } });
    const r = await sparePartApi.getList({ page: 1, pageSize: 10 });
    expect(r.data?.items[0]).toEqual({ id: 0, partName: '', partModel: null, totalQuantity: 0, availableQuantity: 0, warehouse: '', createdAt: '' });
  });

  it('alarmRuleApi.create — minimal body (only required name+metric+threshold)', async () => {
    mockAxios.onPost('/alarm-rules').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await alarmRuleApi.create({ name: 'n', metric: 'm', threshold: 1 });
    expect(r.data).toBeDefined();
  });

  it('notificationRuleApi.create — minimal body (only name+level)', async () => {
    mockAxios.onPost('/notification-rules').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await notificationRuleApi.create({ name: 'n', level: 'info' });
    expect(r.data).toBeDefined();
  });

  it('inspectionTemplateApi.create — minimal body (only name)', async () => {
    mockAxios.onPost('/inspection/templates').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await inspectionTemplateApi.create({ name: 'n' });
    expect(r.data).toBeDefined();
  });
});

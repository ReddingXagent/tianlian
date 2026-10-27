/**
 * api ext86 — cond-expr/if falsy side coverage + getFaqCategories items-wrapper + healing rules wrapper
 */
import MockAdapter from 'axios-mock-adapter';
import api, { knowledgeApi, roleApi, healingRuleApi } from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

describe('api ext86 — remaining cond-expr / if falsy sides', () => {
  it('getFaqCategories — items-wrapper (non-array data)', async () => {
    mockAxios.onGet('/knowledge/faq/categories').reply(200, { code: 200, message: 'ok', data: { items: [{ id: 9 }] } });
    const r = await knowledgeApi.getFaqCategories();
    expect(r.data?.[0]?.id).toBe(9);
  });

  it('getFaqCategories — data null → empty array', async () => {
    mockAxios.onGet('/knowledge/faq/categories').reply(200, { code: 200, message: 'ok', data: null });
    const r = await knowledgeApi.getFaqCategories();
    expect(r.data).toEqual([]);
  });

  it('healingRuleApi.getList — non-array data → []', async () => {
    mockAxios.onGet('/healing/rules').reply(200, { code: 200, message: 'ok', data: { items: [{ id: 3 }] } });
    const r = await healingRuleApi.getList();
    expect(r.data).toEqual([]);
  });

  it('knowledgeApi.updateArticle — empty body (all undefined)', async () => {
    mockAxios.onPut('/knowledge/articles/5').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await knowledgeApi.updateArticle(5, {});
    expect(r.data).toBeDefined();
  });

  it('roleApi.update — empty body (all undefined)', async () => {
    mockAxios.onPut('/roles/5').reply(200, { code: 200, message: 'ok', data: {} });
    const r = await roleApi.update(5, {});
    expect(r.data).toBeDefined();
  });
});

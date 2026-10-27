/**
 * fetchAllPages 分页循环拉全量测试 (卡 971f853e)
 *
 * 背景: 后端 devices/device_library/stations 的 page_size 契约为 Query(20, ge=1, le=100),
 * 前端曾传 200/500 → FastAPI 422, 且调用点 .catch(()=>{}) 静默吞错 → 下拉空。
 * fetchAllPages 固定 page_size=100 循环翻页取尽 total, 从根上规避超限与截断。
 */
import { describe, it, expect, vi } from 'vitest';
import { fetchAllPages } from '../fetchAll';

type Page = { items: any[]; total: number; page: number; page_size: number };

// 构造一个分页 mock: total 条数据, 按 page/page_size 切片返回
function makeListFn(total: number, calls: any[] = []) {
  const all = Array.from({ length: total }, (_, i) => ({ id: i + 1 }));
  return vi.fn((params: Record<string, unknown>) => {
    calls.push(params);
    const page = Number(params.page);
    const pageSize = Number(params.page_size);
    const items = all.slice((page - 1) * pageSize, page * pageSize);
    const payload: Page = { items, total, page, page_size: pageSize };
    return Promise.resolve({ data: payload }); // 拦截器解包后的 axios 形状
  });
}

describe('fetchAllPages', () => {
  it('多页循环: 250 条数据按 page_size=100 翻 3 页取尽', async () => {
    const listFn = makeListFn(250);
    const items = await fetchAllPages<{ id: number }>(listFn);
    expect(items).toHaveLength(250);
    expect(items[0].id).toBe(1);
    expect(items[249].id).toBe(250);
    expect(listFn).toHaveBeenCalledTimes(3);
  });

  it('单页即取尽时不发第二页请求', async () => {
    const listFn = makeListFn(42);
    const items = await fetchAllPages(listFn);
    expect(items).toHaveLength(42);
    expect(listFn).toHaveBeenCalledTimes(1);
  });

  it('恰满一页(100)且有 total 时 1 次即取尽, 不截断也不多发请求', async () => {
    const listFn = makeListFn(100);
    const items = await fetchAllPages(listFn);
    expect(items).toHaveLength(100);
    expect(listFn).toHaveBeenCalledTimes(1); // total=100 已满足, 无需空页确认
  });

  it('空结果返回 []', async () => {
    const listFn = makeListFn(0);
    const items = await fetchAllPages(listFn);
    expect(items).toEqual([]);
    expect(listFn).toHaveBeenCalledTimes(1);
  });

  it('每次请求都带 page_size=100 与透传 extra 参数', async () => {
    const calls: any[] = [];
    const listFn = makeListFn(150, calls);
    await fetchAllPages(listFn, { is_active: true });
    expect(calls[0]).toMatchObject({ page: 1, page_size: 100, is_active: true });
    expect(calls[1]).toMatchObject({ page: 2, page_size: 100, is_active: true });
  });

  it('后端 total 缺失时按"不满页即停"终止, 不死循环', async () => {
    let page = 0;
    const listFn = vi.fn(() => {
      page += 1;
      // 无 total 字段; 第 1 页满 100, 第 2 页只回 3 条 → 停
      const items = page === 1 ? Array.from({ length: 100 }, (_, i) => ({ id: i })) : [{ id: 'x' }, { id: 'y' }, { id: 'z' }];
      return Promise.resolve({ data: { items, page, page_size: 100 } as any });
    });
    const items = await fetchAllPages(listFn);
    expect(items).toHaveLength(103);
    expect(listFn).toHaveBeenCalledTimes(2);
  });

  it('maxPages 熔断: 防后端 total 异常导致的无限翻页', async () => {
    const listFn = vi.fn(() => Promise.resolve({ data: { items: Array.from({ length: 100 }, (_, i) => i), total: 1e9, page: 1, page_size: 100 } as any }));
    const items = await fetchAllPages(listFn, {}, { maxPages: 3 });
    expect(listFn).toHaveBeenCalledTimes(3);
    expect(items).toHaveLength(300);
  });
});

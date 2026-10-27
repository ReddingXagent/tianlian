/**
 * 分页循环拉全量 helper (卡 971f853e)
 *
 * 背景: 后端 devices / device_library / stations 的 page_size 契约为
 * Query(20, ge=1, le=100) —— 前端传 200/500 必 422, 传 100 恰上限则 >100 台静默截断。
 * 此 helper 固定 page_size=100(契约上限)循环翻页直到 total 取尽, 调用点禁止再手拼大 page_size。
 */
import type { PaginatedData } from '../types';

export const FETCH_ALL_PAGE_SIZE = 100; // 后端 le=100 契约上限, 勿调大

type ListFn = (params: Record<string, unknown>) => Promise<any>;

interface FetchAllOptions {
  /** 翔页熔断上限, 防后端 total 异常导致死循环; 默认 50 页(5000 条) */
  maxPages?: number;
}

// 兼容两种返回形状: 拦截器解包后的 axios 响应 ({data: PaginatedData}) / 直接返回 PaginatedData
function extractPayload(res: any): PaginatedData<unknown> | null {
  const payload = res?.data ?? res;
  if (payload && typeof payload === 'object' && Array.isArray(payload.items)) {
    return payload;
  }
  return null;
}

/**
 * 循环调用分页 list 接口直到取尽全量, 返回聚合 items。
 *
 * @param listFn   分页接口函数, 如 `(params) => deviceAPI.list(params)`
 * @param extraParams  透传的过滤参数(不含 page/page_size)
 * @throws 任一页失败即抛出原错误, 由调用方决定降级方式(须 message.error, 禁静默吞)
 */
export async function fetchAllPages<T = unknown>(
  listFn: ListFn,
  extraParams: Record<string, unknown> = {},
  opts: FetchAllOptions = {},
): Promise<T[]> {
  const maxPages = opts.maxPages ?? 50;
  const all: T[] = [];
  let page = 1;

  for (;;) {
    const res = await listFn({ ...extraParams, page, page_size: FETCH_ALL_PAGE_SIZE });
    const payload = extractPayload(res);
    if (!payload) return all; // 形状不符(空/异常体)按已取内容终止, 不抛假错误

    const items = (payload.items as T[]) ?? [];
    all.push(...items);

    const total = Number(payload.total);
    const hasTotal = Number.isFinite(total) && total >= 0;
    if (hasTotal && all.length >= total) return all; // total 取尽
    if (items.length < FETCH_ALL_PAGE_SIZE) return all; // 尾页不满 → 无更多
    if (page >= maxPages) return all; // 熔断
    page += 1;
  }
}

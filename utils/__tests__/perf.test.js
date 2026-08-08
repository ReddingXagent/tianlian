// utils/__tests__/perf.test.js - 性能优化工具测试
const {
  createBatchSetData,
  diffSetData,
  createPagination,
  prepareLazyImages,
  guardTap,
  buildMarkers
} = require('../perf');

// Mock wx
global.wx = {
  showToast: jest.fn()
};

describe('perf utilities', () => {

  // ========== createBatchSetData ==========
  describe('createBatchSetData', () => {
    test('合并多次 set 为一次 setData', async () => {
      const setData = jest.fn((data, cb) => cb && cb());
      const pageInstance = { setData };
      const batch = createBatchSetData(pageInstance);

      batch.set('a', 1);
      batch.set('b', 2);
      batch.set('c', 3);

      expect(setData).not.toHaveBeenCalled();

      await batch.flush();

      expect(setData).toHaveBeenCalledTimes(1);
      expect(setData).toHaveBeenCalledWith({ a: 1, b: 2, c: 3 }, expect.any(Function));
    });

    test('无变更时 flush 不触发 setData', async () => {
      const setData = jest.fn();
      const batch = createBatchSetData({ setData });

      await batch.flush();

      expect(setData).not.toHaveBeenCalled();
    });

    test('flush 后可以再次使用', async () => {
      const setData = jest.fn((data, cb) => cb && cb());
      const batch = createBatchSetData({ setData });

      batch.set('x', 'first');
      await batch.flush();
      expect(setData).toHaveBeenCalledTimes(1);

      batch.set('y', 'second');
      await batch.flush();
      expect(setData).toHaveBeenCalledTimes(2);
      expect(setData).toHaveBeenLastCalledWith({ y: 'second' }, expect.any(Function));
    });

    test('reset 清空待提交数据', async () => {
      const setData = jest.fn();
      const batch = createBatchSetData({ setData });

      batch.set('a', 1);
      batch.reset();
      await batch.flush();

      expect(setData).not.toHaveBeenCalled();
    });
  });

  // ========== diffSetData ==========
  describe('diffSetData', () => {
    test('只更新发生变化的字段', () => {
      const setData = jest.fn();
      const pageInstance = { setData, data: { a: 1, b: 2, c: 3 } };

      const diff = diffSetData(pageInstance, { a: 1, b: 99, c: 3 }, { a: 1, b: 2, c: 3 });

      expect(Object.keys(diff)).toEqual(['b']);
      expect(setData).toHaveBeenCalledWith({ b: 99 });
    });

    test('无变化时不触发 setData', () => {
      const setData = jest.fn();
      const pageInstance = { setData, data: { a: 1 } };

      const diff = diffSetData(pageInstance, { a: 1 }, { a: 1 });

      expect(Object.keys(diff)).toHaveLength(0);
      expect(setData).not.toHaveBeenCalled();
    });

    test('默认使用页面 data 做比较', () => {
      const setData = jest.fn();
      const pageInstance = { setData, data: { x: 10 } };

      const diff = diffSetData(pageInstance, { x: 20 });

      expect(diff).toEqual({ x: 20 });
      expect(setData).toHaveBeenCalledWith({ x: 20 });
    });

    test('处理深层对象引用变化', () => {
      const setData = jest.fn();
      const pageInstance = { setData, data: {} };

      const obj1 = { name: 'test' };
      const obj2 = { name: 'test' };

      // Object.is 对不同引用的对象返回 false
      const diff = diffSetData(pageInstance, { item: obj2 }, { item: obj1 });

      expect(diff).toEqual({ item: obj2 });
    });
  });

  // ========== createPagination ==========
  describe('createPagination', () => {
    test('首次加载获取第一页', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2, 3], total: 25, hasMore: true });

      const pager = createPagination(fetchFn, { pageSize: 10 });

      const result = await pager.loadMore();

      expect(fetchFn).toHaveBeenCalledWith(1, 10);
      expect(result.list).toEqual([1, 2, 3]);
      expect(result.total).toBe(25);
      expect(result.hasMore).toBe(true);
      expect(result.page).toBe(1);
    });

    test('loadMore 累积加载下一页', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2, 3], total: 25 })
        .mockResolvedValueOnce({ list: [4, 5, 6], total: 25 });

      const pager = createPagination(fetchFn, { pageSize: 3 });

      await pager.loadMore();
      const result = await pager.loadMore();

      expect(result.list).toEqual([1, 2, 3, 4, 5, 6]);
      expect(fetchFn).toHaveBeenCalledTimes(2);
      expect(fetchFn).toHaveBeenNthCalledWith(2, 2, 3);
    });

    test('reload=true 重置到第一页', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2], total: 2 })
        .mockResolvedValueOnce({ list: [9, 8], total: 2 });

      const pager = createPagination(fetchFn, { pageSize: 10 });

      await pager.loadMore();
      const result = await pager.loadMore(true);

      expect(result.list).toEqual([9, 8]);
      expect(result.page).toBe(1);
    });

    test('loading 时拒绝重复调用', async () => {
      let resolveFirst;
      const fetchFn = jest.fn()
        .mockReturnValueOnce(new Promise(res => { resolveFirst = res; }));

      const pager = createPagination(fetchFn, { pageSize: 10 });

      const firstCall = pager.loadMore();
      const secondResult = await pager.loadMore(); // 应直接返回

      expect(secondResult.hasMore).toBe(false); // 还没加载完
      expect(fetchFn).toHaveBeenCalledTimes(1);

      resolveFirst({ list: [1], total: 1 });
      await firstCall;
    });

    test('hasMore=false 时不再加载', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2, 3], total: 3 });

      const pager = createPagination(fetchFn, { pageSize: 3 });

      await pager.loadMore();
      expect(pager.getHasMore()).toBe(false);

      const result = await pager.loadMore(); // 不应再调 fetchFn
      expect(fetchFn).toHaveBeenCalledTimes(1);
      expect(result.list).toEqual([1, 2, 3]);
    });

    test('reset 清空状态', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1], total: 10 });

      const pager = createPagination(fetchFn, { pageSize: 10 });
      await pager.loadMore();

      pager.reset();

      expect(pager.getList()).toEqual([]);
      expect(pager.getPage()).toBe(1);
      expect(pager.getHasMore()).toBe(true);
    });

    test('首页缓存命中（cacheKey + cacheTtl）', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2], total: 2 });

      const pager = createPagination(fetchFn, {
        pageSize: 10,
        cacheKey: 'test_cache',
        cacheTtl: 60000
      });

      // 首次加载
      await pager.loadMore();
      expect(fetchFn).toHaveBeenCalledTimes(1);

      // reload 时应命中缓存
      const result = await pager.loadMore(true);
      expect(fetchFn).toHaveBeenCalledTimes(1); // 没有再调
      expect(result.list).toEqual([1, 2]);
    });

    test('clearCache 后 reload 重新请求', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1], total: 1 })
        .mockResolvedValueOnce({ list: [2], total: 1 });

      const pager = createPagination(fetchFn, {
        pageSize: 10,
        cacheKey: 'test_cache2',
        cacheTtl: 60000
      });

      await pager.loadMore();
      pager.clearCache();
      const result = await pager.loadMore(true);

      expect(fetchFn).toHaveBeenCalledTimes(2);
      expect(result.list).toEqual([2]);
    });

    test('isLoading 反映加载状态', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1], total: 1 });
      const pager = createPagination(fetchFn, { pageSize: 10 });

      // 初始状态未加载
      expect(pager.isLoading()).toBe(false);

      // 开始加载
      const p = pager.loadMore();
      expect(pager.isLoading()).toBe(true);

      await p;
      expect(pager.isLoading()).toBe(false);
    });

    test('getLastFetchAt 返回加载时间戳', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1], total: 1 });
      const pager = createPagination(fetchFn, { pageSize: 10 });

      // 初始无时间戳
      expect(pager.getLastFetchAt()).toBe(0);

      await pager.loadMore();
      const ts = pager.getLastFetchAt();
      expect(ts).toBeGreaterThan(0);
    });

    test('createPagination 不传 options 使用默认值', async () => {
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ list: [1, 2, 3], total: 3 });
      // 不传 options 触发 options={} 和解构默认值
      const pager = createPagination(fetchFn);
      const result = await pager.loadMore();
      expect(result.list).toEqual([1, 2, 3]);
      // pageSize 默认 10，3 条数据 < 10 → hasMore=false
      expect(pager.getHasMore()).toBe(false);
    });

    test('fetchFn 返回 res.data.list 格式', async () => {
      // 覆盖 res.list || res.data?.list || [] 的第二分支
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({ data: { list: [10, 20], total: 5 } });
      const pager = createPagination(fetchFn, { pageSize: 10 });
      const result = await pager.loadMore();
      expect(result.list).toEqual([10, 20]);
      expect(pager.getHasMore()).toBe(true);
    });

    test('fetchFn 返回空对象触发 || 后备值', async () => {
      // 覆盖 res.list || res.data?.list || [] 的第三分支 (||[] 和 ||0)
      const fetchFn = jest.fn()
        .mockResolvedValueOnce({}); // 没有 list 也没有 data
      const pager = createPagination(fetchFn, { pageSize: 10 });
      const result = await pager.loadMore();
      expect(result.list).toEqual([]); // || [] 后备
      expect(pager.getHasMore()).toBe(false); // 0 条 < 0 total → false
    });
  });

  // ========== prepareLazyImages ==========
  describe('prepareLazyImages', () => {
    test('使用默认参数生成懒加载属性', () => {
      // 不传 urlKey 和 placeholder 触发默认值
      const items = [{ id: 1, coverUrl: 'https://example.com/1.jpg' }];
      const result = prepareLazyImages(items);
      expect(result[0].lazySrc).toBe('');
      expect(result[0].realSrc).toBe('https://example.com/1.jpg');
    });

    test('生成懒加载属性', () => {
      const items = [
        { id: 1, coverUrl: 'https://example.com/1.jpg' },
        { id: 2, coverUrl: 'https://example.com/2.jpg' }
      ];

      const result = prepareLazyImages(items, 'coverUrl');

      expect(result[0].lazySrc).toBe('');
      expect(result[0].realSrc).toBe('https://example.com/1.jpg');
      expect(result[1].realSrc).toBe('https://example.com/2.jpg');
    });

    test('保持原始属性', () => {
      const items = [{ id: 1, coverUrl: 'url', name: 'Station' }];
      const result = prepareLazyImages(items, 'coverUrl');

      expect(result[0].id).toBe(1);
      expect(result[0].name).toBe('Station');
    });

    test('缺少 urlKey 时 realSrc 为空', () => {
      const items = [{ id: 1, name: 'test' }];
      const result = prepareLazyImages(items, 'coverUrl');

      expect(result[0].realSrc).toBe('');
    });

    test('使用自定义 placeholder', () => {
      const items = [{ id: 1, coverUrl: 'url' }];
      const result = prepareLazyImages(items, 'coverUrl', 'placeholder.png');

      expect(result[0].lazySrc).toBe('placeholder.png');
    });
  });

  // ========== guardTap ==========
  describe('guardTap', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });
    afterEach(() => {
      jest.useRealTimers();
    });

    test('间隔内第二次调用被忽略', () => {
      const fn = jest.fn();
      const guarded = guardTap(fn, 1000);

      guarded();
      guarded();
      guarded();

      expect(fn).toHaveBeenCalledTimes(1);
    });

    test('间隔后可以再次调用', () => {
      const fn = jest.fn();
      const guarded = guardTap(fn, 1000);

      guarded();
      jest.advanceTimersByTime(1001);
      guarded();

      expect(fn).toHaveBeenCalledTimes(2);
    });

    test('默认间隔 800ms', () => {
      const fn = jest.fn();
      const guarded = guardTap(fn);

      guarded();
      jest.advanceTimersByTime(500);
      guarded();

      expect(fn).toHaveBeenCalledTimes(1);

      jest.advanceTimersByTime(400);
      guarded();

      expect(fn).toHaveBeenCalledTimes(2);
    });

    test('传递参数和 this', () => {
      const fn = jest.fn();
      const guarded = guardTap(fn, 100);

      const ctx = { name: 'test' };
      guarded.call(ctx, 'a', 'b');

      expect(fn).toHaveBeenCalledWith('a', 'b');
      expect(fn.mock.instances[0]).toBe(ctx);
    });
  });

  // ========== buildMarkers ==========
  describe('buildMarkers', () => {
    test('为新站点生成 markers', () => {
      const stations = [
        { id: 's1', lat: 30.1, lng: 104.1, name: 'Station A' },
        { id: 's2', lat: 30.2, lng: 104.2, name: 'Station B' }
      ];

      const markers = buildMarkers(stations);

      expect(markers).toHaveLength(2);
      expect(markers[0]).toMatchObject({
        id: 0,
        _stationId: 's1',
        latitude: 30.1,
        longitude: 104.1,
        title: 'Station A',
        iconPath: '/assets/icons/marker.png',
        width: 32,
        height: 32
      });
      expect(markers[0].callout.content).toBe('Station A');
    });

    test('位置不变时复用旧 marker', () => {
      const stations = [
        { id: 's1', lat: 30.1, lng: 104.1, name: 'A' }
      ];
      const prevMarkers = [{
        id: 0,
        _stationId: 's1',
        latitude: 30.1,
        longitude: 104.1,
        title: 'A',
        iconPath: '/assets/icons/marker.png',
        width: 32,
        height: 32,
        callout: { content: 'A' }
      }];

      const markers = buildMarkers(stations, prevMarkers);

      // 应该是同一个对象引用（复用）
      expect(markers[0]).toBe(prevMarkers[0]);
    });

    test('名称变化时不复用', () => {
      const stations = [
        { id: 's1', lat: 30.1, lng: 104.1, name: 'New Name' }
      ];
      const prevMarkers = [{
        id: 0,
        _stationId: 's1',
        latitude: 30.1,
        longitude: 104.1,
        title: 'Old Name'
      }];

      const markers = buildMarkers(stations, prevMarkers);

      expect(markers[0]).not.toBe(prevMarkers[0]);
      expect(markers[0].title).toBe('New Name');
    });

    test('空 stations 返回空数组', () => {
      const markers = buildMarkers([]);
      expect(markers).toEqual([]);
    });

    test('marker id 与索引一致', () => {
      const stations = [
        { id: 'a', lat: 1, lng: 1, name: 'A' },
        { id: 'b', lat: 2, lng: 2, name: 'B' },
        { id: 'c', lat: 3, lng: 3, name: 'C' }
      ];

      const markers = buildMarkers(stations);

      expect(markers.map(m => m.id)).toEqual([0, 1, 2]);
    });
  });
});

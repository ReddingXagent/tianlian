// utils/perf.js - 性能优化工具集
// 批量 setData + 分页缓存 + diff 更新 + 图片懒加载

/**
 * 批量 setData：合并多次 setData 为一次
 * 适用于轮询场景（如充电页 fetchStatus 每次更新10+字段）
 *
 * 用法：
 *   const batch = createBatchSetData(pageInstance);
 *   batch.set('power', '1.5');
 *   batch.set('energy', '2.3');
 *   batch.flush(); // 一次 setData({ power:'1.5', energy:'2.3' })
 *
 * @param {object} pageInstance - Page() 实例
 * @returns {{ set, flush, reset }}
 */
function createBatchSetData(pageInstance) {
  let pending = {};
  let dirty = false;

  return {
    set(key, value) {
      pending[key] = value;
      dirty = true;
    },
    flush() {
      if (!dirty) return Promise.resolve();
      const data = pending;
      pending = {};
      dirty = false;
      return new Promise(resolve => {
        pageInstance.setData(data, resolve);
      });
    },
    reset() {
      pending = {};
      dirty = false;
    }
  };
}

/**
 * Diff SetData：只更新发生变化的字段
 * 减少不必要的渲染压力
 *
 * @param {object} pageInstance - Page() 实例
 * @param {object} newData - 新数据
 * @param {object} [prevData] - 上次数据（默认取页面 data）
 * @returns {object} 实际变更的字段（空对象表示无变化）
 */
function diffSetData(pageInstance, newData, prevData) {
  const prev = prevData || pageInstance.data;
  const diff = {};

  for (const key in newData) {
    if (!Object.is(prev[key], newData[key])) {
      diff[key] = newData[key];
    }
  }

  if (Object.keys(diff).length > 0) {
    pageInstance.setData(diff);
  }
  return diff;
}

/**
 * 创建分页加载器（带缓存）
 * 适用于订单列表、通知列表、交易记录等分页场景
 *
 * @param {Function} fetchFn - (page, pageSize) => Promise<{ list, total, hasMore }>
 * @param {object} [options]
 * @param {number} [options.pageSize=10]
 * @param {number} [options.cacheTtl=10000]
 * @param {string} [options.cacheKey]
 * @returns {object} pagination controller
 */
function createPagination(fetchFn, options = {}) {
  const {
    pageSize = 10,
    cacheTtl = 10000,
    cacheKey = null
  } = options;

  let currentPage = 1;
  let list = [];
  let total = 0;
  let loading = false;
  let hasMore = true;
  let lastFetchAt = 0;

  // 简易内存缓存（首次加载时命中）
  let cachedFirstPage = null;
  let cachedAt = 0;

  return {
    /**
     * 加载下一页（或首次加载）
     * @param {boolean} reload - 强制从第一页开始
     * @returns {Promise<{ list, total, hasMore, page }>}
     */
    async loadMore(reload = false) {
      if (loading) return { list, total, hasMore: false, page: currentPage };

      // 首页缓存命中（仅在 reload 且缓存有效时）
      if (reload && cacheKey && cachedFirstPage && (Date.now() - cachedAt < cacheTtl)) {
        currentPage = 1;
        list = cachedFirstPage.list;
        total = cachedFirstPage.total;
        hasMore = cachedFirstPage.hasMore;
        lastFetchAt = Date.now();
        return { list, total, hasMore, page: currentPage };
      }

      if (reload) {
        currentPage = 1;
        list = [];
        hasMore = true;
        cachedFirstPage = null;
      }

      if (!hasMore) return { list, total, hasMore: false, page: currentPage };

      loading = true;
      try {
        const res = await fetchFn(currentPage, pageSize);
        const newItems = res.list || res.data?.list || [];
        total = res.total || res.data?.total || 0;
        hasMore = list.length + newItems.length < total;

        if (currentPage === 1) {
          list = newItems;
          // 缓存首页
          if (cacheKey) {
            cachedFirstPage = { list: [...newItems], total, hasMore };
            cachedAt = Date.now();
          }
        } else {
          list = list.concat(newItems);
        }

        currentPage++;
        lastFetchAt = Date.now();
        return { list, total, hasMore, page: currentPage - 1 };
      } finally {
        loading = false;
      }
    },

    /** 是否正在加载 */
    isLoading() { return loading; },

    /** 是否还有更多 */
    getHasMore() { return hasMore; },

    /** 当前列表 */
    getList() { return list; },

    /** 当前页码 */
    getPage() { return currentPage; },

    /** 重置（不清缓存） */
    reset() {
      currentPage = 1;
      list = [];
      total = 0;
      loading = false;
      hasMore = true;
    },

    /** 清除首页缓存 */
    clearCache() {
      cachedFirstPage = null;
      cachedAt = 0;
    },

    /** 上次加载时间戳 */
    getLastFetchAt() { return lastFetchAt; }
  };
}

/**
 * 图片懒加载指令
 * 生成 data 属性配合 WXML 的 image 组件使用
 *
 * WXML 用法：
 *   <image src="{{item.lazySrc}}" data-src="{{item.realSrc}}"
 *          bind:load="onLazyLoad" mode="aspectFill" />
 *
 * JS 用法：
 *   const lazyItems = prepareLazyImages(items, 'coverUrl');
 */
function prepareLazyImages(items, urlKey = 'coverUrl', placeholder = '') {
  return items.map(item => ({
    ...item,
    lazySrc: placeholder,
    realSrc: item[urlKey] || ''
  }));
}

/**
 * 节流队列控制
 * 确保同一操作在指定间隔内只执行一次
 * 适用于按钮防连点（定位、刷新、收藏等）
 *
 * @param {Function} fn
 * @param {number} [interval=800] - 默认 800ms 足够防双击
 * @returns {Function}
 */
function guardTap(fn, interval = 800) {
  let lastTap = 0;
  return function (...args) {
    const now = Date.now();
    if (now - lastTap < interval) return;
    lastTap = now;
    return fn.apply(this, args);
  };
}

/**
 * 生成 markers（增量复用）
 * 如果站点数量和 ID 不变，只更新位置变化项
 *
 * @param {Array} stations
 * @param {Array} [prevMarkers=[]]
 * @returns {Array} markers array
 */
function buildMarkers(stations, prevMarkers = []) {
  const markerMap = new Map(prevMarkers.map(m => [m._stationId, m]));
  const result = [];

  for (let i = 0; i < stations.length; i++) {
    const s = stations[i];
    const existing = markerMap.get(s.id);

    // 复用：位置未变
    if (existing &&
        existing.latitude === s.lat &&
        existing.longitude === s.lng &&
        existing.title === s.name) {
      existing.id = i; // 确保 id 与索引一致
      result.push(existing);
    } else {
      result.push({
        id: i,
        _stationId: s.id,
        latitude: s.lat,
        longitude: s.lng,
        title: s.name,
        iconPath: '/assets/icons/marker.png',
        width: 32,
        height: 32,
        callout: {
          content: s.name,
          color: '#333',
          fontSize: 12,
          borderRadius: 8,
          padding: 8,
          display: 'BYCLICK'
        }
      });
    }
  }

  return result;
}

module.exports = {
  createBatchSetData,
  diffSetData,
  createPagination,
  prepareLazyImages,
  guardTap,
  buildMarkers
};

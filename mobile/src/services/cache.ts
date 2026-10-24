import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_PREFIX = '@tianlian_';
const CACHE_EXPIRY = 5 * 60 * 1000; // 5 分钟过期

interface CachedData<T> {
  data: T;
  timestamp: number;
}

export const cache = {
  /**
   * 保存数据到缓存
   * @param key 缓存键
   * @param data 要缓存的数据
   */
  async set<T>(key: string, data: T): Promise<void> {
    try {
      const cached: CachedData<T> = {
        data,
        timestamp: Date.now(),
      };
      await AsyncStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(cached));
      console.log(`[Cache] Saved: ${key}`);
    } catch (error) {
      console.error('[Cache] Save error:', error);
      throw error;
    }
  },

  /**
   * 从缓存获取数据
   * @param key 缓存键
   * @returns 缓存的数据，如果不存在或已过期则返回 null
   */
  async get<T>(key: string): Promise<T | null> {
    try {
      const item = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`);
      if (!item) {
        console.log(`[Cache] Miss: ${key}`);
        return null;
      }

      const cached: CachedData<T> = JSON.parse(item);
      
      // 检查是否过期
      if (Date.now() - cached.timestamp > CACHE_EXPIRY) {
        console.log(`[Cache] Expired: ${key}`);
        await this.remove(key);
        return null;
      }

      console.log(`[Cache] Hit: ${key}`);
      return cached.data;
    } catch (error) {
      console.error('[Cache] Get error:', error);
      return null;
    }
  },

  /**
   * 从缓存删除数据
   * @param key 缓存键
   */
  async remove(key: string): Promise<void> {
    try {
      await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`);
      console.log(`[Cache] Removed: ${key}`);
    } catch (error) {
      console.error('[Cache] Remove error:', error);
    }
  },

  /**
   * 清空所有天链缓存
   */
  async clear(): Promise<void> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      const tianlianKeys = keys.filter(key => key.startsWith(CACHE_PREFIX));
      if (tianlianKeys.length > 0) {
        await AsyncStorage.multiRemove(tianlianKeys);
        console.log(`[Cache] Cleared ${tianlianKeys.length} items`);
      }
    } catch (error) {
      console.error('[Cache] Clear error:', error);
    }
  },

  /**
   * 检查数据是否存在且未过期
   * @param key 缓存键
   * @returns 是否有效
   */
  async isValid(key: string): Promise<boolean> {
    const data = await this.get(key);
    return data !== null;
  },

  /**
   * 获取缓存元数据
   * @param key 缓存键
   * @returns 缓存时间戳，如果不存在则返回 null
   */
  async getTimestamp(key: string): Promise<number | null> {
    try {
      const item = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`);
      if (!item) return null;
      
      const cached: CachedData<any> = JSON.parse(item);
      return cached.timestamp;
    } catch (error) {
      return null;
    }
  },

  /**
   * 获取所有缓存键
   * @returns 缓存键列表
   */
  async getAllKeys(): Promise<string[]> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      return keys
        .filter(key => key.startsWith(CACHE_PREFIX))
        .map(key => key.replace(CACHE_PREFIX, ''));
    } catch (error) {
      console.error('[Cache] Get keys error:', error);
      return [];
    }
  },
};

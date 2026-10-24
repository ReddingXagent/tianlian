import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNetwork } from '../hooks/useNetwork';
import { syncService } from '../services/sync';
import { cache } from '../services/cache';

export interface OfflineContextType {
  isConnected: boolean;
  isSyncing: boolean;
  lastSyncTime: number | null;
  triggerSync: () => Promise<void>;
  getCachedData: <T>(key: string) => Promise<T | null>;
  syncStatus: {
    devices: number;
    stations: number;
    workOrders: number;
    alarms: number;
  } | null;
  syncErrors: string[] | null;
}

const OfflineContext = createContext<OfflineContextType | undefined>(undefined);

/**
 * 离线模式 Provider
 * 为整个应用提供离线数据缓存和同步能力
 */
export const OfflineProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isConnected } = useNetwork();
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<number | null>(null);
  const [syncStatus, setSyncStatus] = useState<OfflineContextType['syncStatus']>(null);
  const [syncErrors, setSyncErrors] = useState<string[] | null>(null);

  /**
   * 触发数据同步
   */
  const triggerSync = useCallback(async () => {
    if (isSyncing || !isConnected) {
      console.log('[Offline] Skip sync: syncing=', isSyncing, 'connected=', isConnected);
      return;
    }
    
    console.log('[Offline] Starting sync...');
    setIsSyncing(true);
    setSyncErrors(null);
    
    try {
      const result = await syncService.fullSync();
      
      if (result.success) {
        setLastSyncTime(result.syncedAt);
        setSyncStatus(result.stats || null);
        console.log('[Offline] Sync success:', result.stats);
      } else {
        setSyncErrors(result.errors || ['同步失败']);
        console.warn('[Offline] Sync completed with errors:', result.errors);
      }
    } catch (error: any) {
      setSyncErrors([error.message || '同步发生错误']);
      console.error('[Offline] Sync error:', error);
    } finally {
      setIsSyncing(false);
    }
  }, [isSyncing, isConnected]);

  /**
   * 获取缓存数据
   */
  const getCachedData = async <T,>(key: string): Promise<T | null> => {
    return cache.get<T>(key);
  };

  // 网络恢复时自动同步
  useEffect(() => {
    if (isConnected) {
      console.log('[Offline] Network connected, triggering sync...');
      triggerSync();
    } else {
      console.log('[Offline] Network disconnected, entering offline mode');
    }
  }, [isConnected]);

  // 应用启动时尝试同步
  useEffect(() => {
    // 延迟一小段时间，等网络状态稳定
    const timer = setTimeout(() => {
      if (isConnected) {
        triggerSync();
      }
    }, 1000);
    
    return () => clearTimeout(timer);
  }, []);

  return (
    <OfflineContext.Provider
      value={{
        isConnected,
        isSyncing,
        lastSyncTime,
        triggerSync,
        getCachedData,
        syncStatus,
        syncErrors,
      }}
    >
      {children}
    </OfflineContext.Provider>
  );
};

/**
 * 离线模式 Hook
 * 在组件中使用离线功能
 */
export const useOffline = () => {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error('useOffline must be used within OfflineProvider');
  }
  return context;
};

import { deviceApi, stationApi, workOrderApi, alarmApi, statsApi } from './api';
import { cache } from './cache';
import { conflictService, ConflictResolutionResult } from './conflict';

export interface SyncResult {
  success: boolean;
  syncedAt: number;
  errors?: string[];
  stats?: {
    devices: number;
    stations: number;
    workOrders: number;
    alarms: number;
  };
}

export interface SyncStatus {
  isSyncing: boolean;
  lastSyncTime: number | null;
  pendingChanges: number;
}

/**
 * 数据同步服务
 * 负责离线数据缓存和网络恢复同步
 */
class SyncService {
  private isSyncing = false;
  private lastSyncTime: number | null = null;
  private pendingChanges: any[] = [];

  /**
   * 全量同步所有数据
   */
  async fullSync(): Promise<SyncResult> {
    if (this.isSyncing) {
      console.log('[Sync] Already syncing, skipping...');
      return {
        success: false,
        syncedAt: 0,
        errors: ['同步进行中']
      };
    }

    console.log('[Sync] Starting full sync...');
    this.isSyncing = true;
    const errors: string[] = [];
    const stats = {
      devices: 0,
      stations: 0,
      workOrders: 0,
      alarms: 0,
    };

    try {
      // 同步设备
      try {
        const devices = await deviceApi.getAll();
        await cache.set('devices', devices.data);
        stats.devices = Array.isArray(devices.data) ? devices.data.length : 0;
        console.log(`[Sync] Devices synced: ${stats.devices}`);
      } catch (e: any) {
        console.error('[Sync] Devices error:', e.message);
        errors.push('设备同步失败');
      }

      // 同步站点
      try {
        const stations = await stationApi.getAll();
        await cache.set('stations', stations.data);
        stats.stations = Array.isArray(stations.data) ? stations.data.length : 0;
        console.log(`[Sync] Stations synced: ${stats.stations}`);
      } catch (e: any) {
        console.error('[Sync] Stations error:', e.message);
        errors.push('站点同步失败');
      }

      // 同步工单
      try {
        const workOrders = await workOrderApi.getAll();
        await cache.set('workOrders', workOrders.data);
        stats.workOrders = Array.isArray(workOrders.data) ? workOrders.data.length : 0;
        console.log(`[Sync] WorkOrders synced: ${stats.workOrders}`);
      } catch (e: any) {
        console.error('[Sync] WorkOrders error:', e.message);
        errors.push('工单同步失败');
      }

      // 同步告警
      try {
        const alarms = await alarmApi.getAll();
        await cache.set('alarms', alarms.data);
        stats.alarms = Array.isArray(alarms.data) ? alarms.data.length : 0;
        console.log(`[Sync] Alarms synced: ${stats.alarms}`);
      } catch (e: any) {
        console.error('[Sync] Alarms error:', e.message);
        errors.push('告警同步失败');
      }

      // 同步统计数据
      try {
        const overview = await statsApi.overview();
        await cache.set('stats_overview', overview.data);
        console.log('[Sync] Stats synced');
      } catch (e: any) {
        console.error('[Sync] Stats error:', e.message);
        // 统计不是关键数据,不加入错误列表
      }

      this.lastSyncTime = Date.now();
      const result: SyncResult = {
        success: errors.length === 0,
        syncedAt: this.lastSyncTime,
        errors: errors.length > 0 ? errors : undefined,
        stats,
      };

      console.log('[Sync] Full sync completed:', result);
      return result;
    } catch (e: any) {
      console.error('[Sync] Critical error:', e.message);
      return {
        success: false,
        syncedAt: 0,
        errors: ['同步发生严重错误'],
      };
    } finally {
      this.isSyncing = false;
    }
  }

  /**
   * 增量同步 (仅同步变化的数据)
   * 基于时间戳的增量同步实现
   */
  async incrementalSync(): Promise<SyncResult> {
    if (this.isSyncing) {
      console.log('[Sync] Already syncing, skipping...');
      return { success: false, syncedAt: 0, errors: ['同步进行中'] };
    }

    console.log('[Sync] Starting incremental sync...');
    this.isSyncing = true;
    const errors: string[] = [];
    const stats = { devices: 0, stations: 0, workOrders: 0, alarms: 0 };

    try {
      // 获取上次同步时间
      const lastSync = await cache.getTimestamp('devices');
      const since = lastSync || 0;
      console.log(`[Sync] Syncing since ${since} (${new Date(since).toLocaleString()})`);

      // 同步设备 (增量)
      try {
        const localDevices = await cache.get<any[]>('devices') || [];
        const serverDevices = await deviceApi.getAll();
        const serverList = Array.isArray(serverDevices.data) ? serverDevices.data : [];
        
        // 检测冲突
        await conflictService.detectConflicts(localDevices, serverList, 'device');
        
        // 合并：服务器新增 + 本地保留 + 冲突解决
        const mergedDevices = this.mergeIncrementalData(localDevices, serverList, since);
        await cache.set('devices', mergedDevices);
        stats.devices = mergedDevices.length;
        console.log(`[Sync] Devices synced: ${stats.devices}`);
      } catch (e: any) {
        console.error('[Sync] Devices error:', e.message);
        errors.push('设备同步失败');
      }

      // 同步站点 (增量)
      try {
        const localStations = await cache.get<any[]>('stations') || [];
        const serverStations = await stationApi.getAll();
        const serverList = Array.isArray(serverStations.data) ? serverStations.data : [];
        
        await conflictService.detectConflicts(localStations, serverList, 'station');
        const mergedStations = this.mergeIncrementalData(localStations, serverList, since);
        await cache.set('stations', mergedStations);
        stats.stations = mergedStations.length;
        console.log(`[Sync] Stations synced: ${stats.stations}`);
      } catch (e: any) {
        console.error('[Sync] Stations error:', e.message);
        errors.push('站点同步失败');
      }

      // 同步工单 (增量 + 离线变更)
      try {
        const localWorkOrders = await cache.get<any[]>('workOrders') || [];
        const serverWorkOrders = await workOrderApi.getAll();
        const serverList = Array.isArray(serverWorkOrders.data) ? serverWorkOrders.data : [];
        
        await conflictService.detectConflicts(localWorkOrders, serverList, 'workorder');
        const mergedWorkOrders = this.mergeIncrementalData(localWorkOrders, serverList, since);
        await cache.set('workOrders', mergedWorkOrders);
        stats.workOrders = mergedWorkOrders.length;
        console.log(`[Sync] WorkOrders synced: ${stats.workOrders}`);
        
        // 同步离线操作
        if (this.pendingChanges.length > 0) {
          const conflictResult = await this.syncPendingChanges();
          if (conflictResult && conflictResult.conflictsResolved > 0) {
            console.log(`[Sync] Resolved ${conflictResult.conflictsResolved} conflicts`);
          }
        }
      } catch (e: any) {
        console.error('[Sync] WorkOrders error:', e.message);
        errors.push('工单同步失败');
      }

      // 同步告警 (增量)
      try {
        const localAlarms = await cache.get<any[]>('alarms') || [];
        const serverAlarms = await alarmApi.getAll();
        const serverList = Array.isArray(serverAlarms.data) ? serverAlarms.data : [];
        
        await conflictService.detectConflicts(localAlarms, serverList, 'alarm');
        const mergedAlarms = this.mergeIncrementalData(localAlarms, serverList, since);
        await cache.set('alarms', mergedAlarms);
        stats.alarms = mergedAlarms.length;
        console.log(`[Sync] Alarms synced: ${stats.alarms}`);
      } catch (e: any) {
        console.error('[Sync] Alarms error:', e.message);
        errors.push('告警同步失败');
      }

      this.lastSyncTime = Date.now();
      return {
        success: errors.length === 0,
        syncedAt: this.lastSyncTime,
        errors: errors.length > 0 ? errors : undefined,
        stats,
      };
    } catch (e: any) {
      console.error('[Sync] Critical error:', e.message);
      return { success: false, syncedAt: 0, errors: ['同步发生严重错误'] };
    } finally {
      this.isSyncing = false;
    }
  }

  /**
   * 合并增量数据
   * 保留本地未同步的数据 + 更新服务器变化的数据
   */
  private mergeIncrementalData(localData: any[], serverData: any[], since: number): any[] {
    const localMap = new Map(localData.map(item => [item.id, item]));
    const serverMap = new Map(serverData.map(item => [item.id, item]));
    
    const merged: any[] = [];
    
    // 服务器数据为基础
    for (const [id, serverItem] of serverMap.entries()) {
      const localItem = localMap.get(id);
      const serverUpdatedAt = serverItem.updatedAt || serverItem.modifiedAt || 0;
      
      // 如果服务器更新时间晚于上次同步，使用服务器数据
      if (serverUpdatedAt > since) {
        merged.push(serverItem);
      } else if (localItem) {
        // 本地有修改（未同步），保留本地数据
        merged.push(localItem);
      } else {
        merged.push(serverItem);
      }
    }
    
    // 添加本地新增的数据（不在服务器中）
    for (const [id, localItem] of localMap.entries()) {
      if (!serverMap.has(id)) {
        merged.push(localItem);
      }
    }
    
    return merged;
  }

  /**
   * 获取同步状态
   */
  getStatus(): SyncStatus {
    return {
      isSyncing: this.isSyncing,
      lastSyncTime: this.lastSyncTime,
      pendingChanges: this.pendingChanges.length,
    };
  }

  /**
   * 获取上次同步时间
   */
  getLastSyncTime(): number | null {
    return this.lastSyncTime;
  }

  /**
   * 添加待同步变更 (用于离线操作)
   */
  addPendingChange(change: any) {
    this.pendingChanges.push({
      ...change,
      createdAt: Date.now(),
    });
    console.log(`[Sync] Pending change added: ${change.type}`);
  }

  /**
   * 获取待同步变更数量
   */
  getPendingChangesCount(): number {
    return this.pendingChanges.length;
  }

  /**
   * 同步待处理变更到服务器
   * 完整实现：包括冲突检测和解决
   */
  async syncPendingChanges(): Promise<ConflictResolutionResult | null> {
    if (this.pendingChanges.length === 0) {
      console.log('[Sync] No pending changes');
      return null;
    }

    console.log(`[Sync] Syncing ${this.pendingChanges.length} pending changes...`);

    // 恢复之前的冲突记录
    await conflictService.restoreFromCache();

    // 1. 按类型分组
    const groupedChanges = this.groupPendingChanges();

    // 2. 逐个类型同步
    const syncResults: any[] = [];
    const failedChanges: any[] = [];

    for (const [type, changes] of Object.entries(groupedChanges)) {
      try {
        const result = await this.syncChangesByType(type, changes as any[]);
        syncResults.push(result);
      } catch (e: any) {
        console.error(`[Sync] Failed to sync ${type}:`, e.message);
        failedChanges.push(...(changes as any[]));
      }
    }

    // 3. 处理冲突
    let conflictResult: ConflictResolutionResult | null = null;
    const pendingConflicts = conflictService.getPendingCount();
    
    if (pendingConflicts > 0) {
      console.log(`[Sync] Resolving ${pendingConflicts} conflicts...`);
      conflictResult = await conflictService.resolveAllConflicts();
      console.log(`[Sync] Conflicts resolved: ${conflictResult.conflictsResolved}`);
    }

    // 4. 更新待处理列表
    this.pendingChanges = failedChanges;
    console.log(`[Sync] Remaining pending changes: ${this.pendingChanges.length}`);

    return conflictResult;
  }

  /**
   * 按类型分组待处理变更
   */
  private groupPendingChanges(): Record<string, any[]> {
    const groups: Record<string, any[]> = {};
    
    for (const change of this.pendingChanges) {
      const type = change.type.split('_')[0]; // workorder, alarm, device, station
      if (!groups[type]) {
        groups[type] = [];
      }
      groups[type].push(change);
    }

    return groups;
  }

  /**
   * 按类型同步变更
   */
  private async syncChangesByType(type: string, changes: any[]): Promise<any> {
    console.log(`[Sync] Syncing ${changes.length} ${type} changes...`);

    switch (type) {
      case 'workorder':
        return await this.syncWorkOrderChanges(changes);
      case 'alarm':
        return await this.syncAlarmChanges(changes);
      case 'device':
        return await this.syncDeviceChanges(changes);
      case 'station':
        return await this.syncStationChanges(changes);
      default:
        console.warn(`[Sync] Unknown type: ${type}`);
        return { success: false, changes: 0 };
    }
  }

  /**
   * 同步工单变更
   */
  private async syncWorkOrderChanges(changes: any[]): Promise<any> {
    let synced = 0;
    let failed = 0;

    for (const change of changes) {
      try {
        if (change.type === 'workorder_create') {
          await workOrderApi.create(change.data);
          synced++;
        } else if (change.type === 'workorder_update') {
          // 先获取服务器版本检测冲突
          const serverData = await workOrderApi.getById(change.id);
          if (serverData.data) {
            await conflictService.detectConflicts(
              [change.data],
              [serverData.data],
              'workorder'
            );
          }
          
          // 应用变更（如果有冲突，冲突服务会处理）
          const pendingConflicts = conflictService.getPendingCount();
          if (pendingConflicts > 0) {
            const resolved = await conflictService.resolveAllConflicts();
            if (resolved.resolvedData.length > 0) {
              await workOrderApi.update(change.id, resolved.resolvedData[0]);
            }
          } else {
            await workOrderApi.update(change.id, change.data);
          }
          synced++;
        }
      } catch (e: any) {
        console.error(`[Sync] WorkOrder sync failed:`, e.message);
        failed++;
      }
    }

    return { type: 'workorder', synced, failed };
  }

  /**
   * 同步告警变更
   */
  private async syncAlarmChanges(changes: any[]): Promise<any> {
    let synced = 0;
    let failed = 0;

    for (const change of changes) {
      try {
        if (change.type === 'alarm_confirm') {
          await alarmApi.update(change.id, { status: 'confirmed', confirmedAt: Date.now() });
          synced++;
        } else if (change.type === 'alarm_update') {
          const serverData = await alarmApi.getById(change.id);
          if (serverData.data) {
            await conflictService.detectConflicts(
              [change.data],
              [serverData.data],
              'alarm'
            );
          }
          await alarmApi.update(change.id, change.data);
          synced++;
        }
      } catch (e: any) {
        console.error(`[Sync] Alarm sync failed:`, e.message);
        failed++;
      }
    }

    return { type: 'alarm', synced, failed };
  }

  /**
   * 同步设备变更
   */
  private async syncDeviceChanges(changes: any[]): Promise<any> {
    let synced = 0;
    let failed = 0;

    for (const change of changes) {
      try {
        if (change.type === 'device_update') {
          await deviceApi.update(change.id, change.data);
          synced++;
        }
      } catch (e: any) {
        console.error(`[Sync] Device sync failed:`, e.message);
        failed++;
      }
    }

    return { type: 'device', synced, failed };
  }

  /**
   * 同步站点变更
   */
  private async syncStationChanges(changes: any[]): Promise<any> {
    let synced = 0;
    let failed = 0;

    for (const change of changes) {
      try {
        if (change.type === 'station_update') {
          await stationApi.update(change.id, change.data);
          synced++;
        }
      } catch (e: any) {
        console.error(`[Sync] Station sync failed:`, e.message);
        failed++;
      }
    }

    return { type: 'station', synced, failed };
  }

  /**
   * 清除待处理变更
   */
  clearPendingChanges() {
    this.pendingChanges = [];
  }
}

// 导出单例
export const syncService = new SyncService();

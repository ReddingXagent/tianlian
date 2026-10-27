/**
 * 冲突解决服务
 * 处理离线操作与服务器数据的冲突
 */

import { cache } from './cache';

export interface ConflictRecord {
  id: string;
  type: 'workorder' | 'alarm' | 'device' | 'station';
  localData: any;
  serverData: any;
  localTimestamp: number;
  serverTimestamp: number;
  status: 'pending' | 'resolved' | 'discarded';
  resolution?: 'server_wins' | 'client_wins' | 'merge';
  resolvedAt?: number;
}

export interface ConflictResolutionResult {
  success: boolean;
  resolvedData: any;
  strategy: 'server_wins' | 'client_wins' | 'merge';
  conflictsResolved: number;
  conflictsDiscarded: number;
}

/**
 * 冲突解决策略
 * 
 * 运维系统采用 Server-Wins 为主策略：
 * - 服务器数据是权威来源
 * - 客户端离线操作作为补充
 * - 关键字段采用合并策略
 */
class ConflictService {
  private conflicts: ConflictRecord[] = [];
  private resolutionStrategies: Record<string, 'server_wins' | 'client_wins' | 'merge'> = {
    // 默认策略：服务器优先
    'default': 'server_wins',
    
    // 工单：合并策略（保留客户端的现场照片和签名）
    'workorder_status': 'merge',
    'workorder_photos': 'client_wins',
    'workorder_signature': 'client_wins',
    'workorder_notes': 'merge',
    
    // 告警：服务器优先（告警状态由系统控制）
    'alarm_status': 'server_wins',
    'alarm_notes': 'merge',
    
    // 设备：服务器优先（设备信息由后台管理）
    'device_info': 'server_wins',
    
    // 站点：服务器优先
    'station_info': 'server_wins',
  };

  /**
   * 检测冲突
   */
  async detectConflicts(
    localData: any[],
    serverData: any[],
    type: 'workorder' | 'alarm' | 'device' | 'station'
  ): Promise<ConflictRecord[]> {
    const conflicts: ConflictRecord[] = [];
    
    // 建立 ID 映射
    const serverMap = new Map(serverData.map(item => [item.id, item]));
    const localMap = new Map(localData.map(item => [item.id, item]));
    
    // 检查本地数据与服务器数据的差异
    for (const [id, localItem] of localMap.entries()) {
      const serverItem = serverMap.get(id);
      
      if (serverItem) {
        // 比较时间戳
        const localTimestamp = localItem.updatedAt || localItem.modifiedAt || 0;
        const serverTimestamp = serverItem.updatedAt || serverItem.modifiedAt || 0;
        
        // 如果本地修改时间晚于服务器，且内容不同，则存在冲突
        if (localTimestamp > serverTimestamp && this.hasDataDiff(localItem, serverItem)) {
          conflicts.push({
            id: id.toString(),
            type,
            localData: localItem,
            serverData: serverItem,
            localTimestamp,
            serverTimestamp,
            status: 'pending',
          });
        }
      }
    }
    
    this.conflicts = conflicts;
    console.log(`[Conflict] Detected ${conflicts.length} conflicts for ${type}`);
    
    return conflicts;
  }

  /**
   * 检查数据是否有差异
   */
  private hasDataDiff(local: any, server: any): boolean {
    const keysToCompare = Object.keys(local).filter(
      key => !['updatedAt', 'modifiedAt', 'syncedAt', '_pending'].includes(key)
    );
    
    for (const key of keysToCompare) {
      if (JSON.stringify(local[key]) !== JSON.stringify(server[key])) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * 解决单个冲突
   */
  resolveConflict(conflict: ConflictRecord): any {
    const strategy = this.getStrategy(conflict.type);
    
    let resolvedData: any;
    
    switch (strategy) {
      case 'server_wins':
        resolvedData = this.applyServerWins(conflict);
        break;
      case 'client_wins':
        resolvedData = this.applyClientWins(conflict);
        break;
      case 'merge':
        resolvedData = this.applyMerge(conflict);
        break;
      default:
        resolvedData = this.applyServerWins(conflict);
    }
    
    // 记录解决结果
    const resolvedConflict: ConflictRecord = {
      ...conflict,
      status: 'resolved',
      resolution: strategy,
      resolvedAt: Date.now(),
    };
    
    this.updateConflictRecord(resolvedConflict);
    
    return resolvedData;
  }

  /**
   * 批量解决冲突
   */
  async resolveAllConflicts(): Promise<ConflictResolutionResult> {
    const pendingConflicts = this.conflicts.filter(c => c.status === 'pending');
    
    let conflictsResolved = 0;
    let conflictsDiscarded = 0;
    const resolvedData: any[] = [];
    
    for (const conflict of pendingConflicts) {
      try {
        const data = this.resolveConflict(conflict);
        resolvedData.push(data);
        conflictsResolved++;
      } catch (error) {
        console.error(`[Conflict] Failed to resolve ${conflict.id}:`, error);
        this.markAsDiscarded(conflict);
        conflictsDiscarded++;
      }
    }
    
    // 保存冲突记录到缓存
    await cache.set('conflict_records', this.conflicts);
    
    return {
      success: conflictsDiscarded === 0,
      resolvedData,
      strategy: 'server_wins',
      conflictsResolved,
      conflictsDiscarded,
    };
  }

  /**
   * Server-Wins 策略
   * 服务器数据覆盖本地数据
   */
  private applyServerWins(conflict: ConflictRecord): any {
    console.log(`[Conflict] Server wins for ${conflict.type}:${conflict.id}`);
    return {
      ...conflict.serverData,
      _resolvedBy: 'server_wins',
      _resolvedAt: Date.now(),
    };
  }

  /**
   * Client-Wins 策略
   * 本地数据覆盖服务器数据
   */
  private applyClientWins(conflict: ConflictRecord): any {
    console.log(`[Conflict] Client wins for ${conflict.type}:${conflict.id}`);
    return {
      ...conflict.localData,
      _resolvedBy: 'client_wins',
      _resolvedAt: Date.now(),
    };
  }

  /**
   * Merge 策略
   * 合并本地和服务器数据
   */
  private applyMerge(conflict: ConflictRecord): any {
    console.log(`[Conflict] Merging ${conflict.type}:${conflict.id}`);
    
    // 根据类型选择合并策略
    if (conflict.type === 'workorder') {
      return this.mergeWorkOrder(conflict);
    } else if (conflict.type === 'alarm') {
      return this.mergeAlarm(conflict);
    }
    
    // 默认：服务器优先，但保留客户端特有字段
    return {
      ...conflict.serverData,
      // 保留客户端的离线操作记录
      offlineOperations: conflict.localData.offlineOperations || [],
      localNotes: conflict.localData.notes,
      _resolvedBy: 'merge',
      _resolvedAt: Date.now(),
    };
  }

  /**
   * 工单合并策略
   * 保留客户端的现场照片、签名和备注
   */
  private mergeWorkOrder(conflict: ConflictRecord): any {
    const merged = {
      ...conflict.serverData,
      // 保留客户端特有字段
      photos: conflict.localData.photos || conflict.serverData.photos || [],
      signature: conflict.localData.signature || conflict.serverData.signature,
      technicianNotes: conflict.localData.technicianNotes || conflict.serverData.technicianNotes,
      completionTime: conflict.localData.completionTime || conflict.serverData.completionTime,
      // 标记合并来源
      _mergedFrom: {
        local: conflict.localTimestamp,
        server: conflict.serverTimestamp,
      },
      _resolvedBy: 'merge',
      _resolvedAt: Date.now(),
    };
    
    return merged;
  }

  /**
   * 告警合并策略
   * 服务器状态优先，合并备注
   */
  private mergeAlarm(conflict: ConflictRecord): any {
    const merged = {
      ...conflict.serverData,
      // 合并备注（服务器 + 客户端）
      notes: this.mergeNotes(conflict.serverData.notes, conflict.localData.notes),
      // 服务器状态优先
      status: conflict.serverData.status,
      // 标记合并来源
      _resolvedBy: 'merge',
      _resolvedAt: Date.now(),
    };
    
    return merged;
  }

  /**
   * 合并备注
   */
  private mergeNotes(serverNotes: string, localNotes: string): string {
    if (!serverNotes && !localNotes) return '';
    if (!serverNotes) return localNotes;
    if (!localNotes) return serverNotes;
    
    // 两者都有，合并并标记来源
    const timestamp = new Date().toLocaleString('zh-CN');
    return `${serverNotes}\n\n[现场备注 @ ${timestamp}]\n${localNotes}`;
  }

  /**
   * 获取冲突解决策略
   */
  private getStrategy(type: string): 'server_wins' | 'client_wins' | 'merge' {
    const key = `${type}_default`;
    return this.resolutionStrategies[key] || this.resolutionStrategies['default'];
  }

  /**
   * 更新冲突记录
   */
  private updateConflictRecord(conflict: ConflictRecord): void {
    const index = this.conflicts.findIndex(c => c.id === conflict.id);
    if (index >= 0) {
      this.conflicts[index] = conflict;
    }
  }

  /**
   * 标记冲突为已丢弃
   */
  private markAsDiscarded(conflict: ConflictRecord): void {
    const discarded: ConflictRecord = {
      ...conflict,
      status: 'discarded',
      resolvedAt: Date.now(),
    };
    this.updateConflictRecord(discarded);
  }

  /**
   * 获取所有冲突
   */
  getConflicts(): ConflictRecord[] {
    return this.conflicts;
  }

  /**
   * 获取待处理冲突数量
   */
  getPendingCount(): number {
    return this.conflicts.filter(c => c.status === 'pending').length;
  }

  /**
   * 清除已解决的冲突
   */
  clearResolved(): void {
    this.conflicts = this.conflicts.filter(c => c.status === 'pending');
    console.log(`[Conflict] Cleared resolved conflicts, ${this.conflicts.length} pending`);
  }

  /**
   * 从缓存恢复冲突记录
   */
  async restoreFromCache(): Promise<void> {
    const cached = await cache.get<ConflictRecord[]>('conflict_records');
    if (cached) {
      this.conflicts = cached.filter(c => c.status === 'pending');
      console.log(`[Conflict] Restored ${this.conflicts.length} pending conflicts`);
    }
  }
}

// 导出单例
export const conflictService = new ConflictService();
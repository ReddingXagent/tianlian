/**
 * types/index.ts — Barrel re-export from domain modules
 *
 * 所有 import 路径 `from '../types'` / `from '../../types'` 保持不变。
 * 重构自原1888行单体文件 (F1364 维度25 types领域拆分)
 */
export * from './modules/common';
export * from './modules/device';
export * from './modules/alarm';
export * from './modules/work-order';
export * from './modules/station';
export * from './modules/user';
export * from './modules/auth';
export * from './modules/knowledge';
export * from './modules/monitor';
export * from './modules/inspection';
export * from './modules/dashboard';
export * from './modules/energy';
export * from './modules/report';
export * from './modules/notification';
export * from './modules/charging';
export * from './modules/infrastructure';
export * from './modules/security';
export * from './modules/ai';
export * from './modules/health';
export * from './modules/merchant-audit';

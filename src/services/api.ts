// Barrel re-export for services — F1363 领域拆分
// 原始 718 行单体 api.ts → 13 模块文件 + barrel

export { default } from './client';
export { tokenStorage } from './client';

// Mappers (公开 API, 测试直接导入)
export {
  mapAlarm,
  mapWorkOrder,
  mapStation,
  mapPagination,
} from './mappers';
export type { Raw } from './mappers';

// 领域 API
export { authApi } from './auth';
export { stationApi } from './station';
export { deviceApi } from './device';
export { alarmApi } from './alarm';
export { workOrderApi } from './work-order';
export { dashboardApi } from './dashboard';
export { revenueApi } from './revenue';
export { chargerApi } from './charger';
export { energyApi } from './energy';
export { notificationApi } from './notification';
export { reportApi } from './report';

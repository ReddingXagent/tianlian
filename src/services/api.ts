// Barrel re-export for services — F1363 领域拆分
// 原始 718 行单体 api.ts → 13 模块文件 + barrel（KYC 轮 433a55b 增 merchant 三件套后 17 模块文件：client + mappers + ai + 11 领域 API + merchant 契约/mock/source）

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
export { merchantApi, mapMerchantApplication, buildMerchantFormData, merchantStatusLabel } from './merchant';

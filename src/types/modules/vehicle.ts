/**
 * types/modules/vehicle.ts — 车辆类型
 */
export interface Vehicle {
  id: number;
  userId: number;
  plate: string;
  brand: string;
  model: string;
  color: string;
  vin: string;
  isDefault: boolean;
  createdAt: string;
}

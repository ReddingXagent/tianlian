/**
 * types/modules/scan.ts — 扫码类型
 */
import type { ConnectorStatus } from './station';

export interface ScanResult {
  id: number;
  type: 'charger';
  code: string;
  name: string;
  stationId: number;
  stationName: string;
  power: number;
  pricePerKwh: number;
  serviceFee: number;
  status: ConnectorStatus;
}

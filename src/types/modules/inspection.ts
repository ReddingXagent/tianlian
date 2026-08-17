/**
 * types/modules/inspection.ts — 巡检相关类型
 */
export type InspectionType = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annual' | 'special';
export type InspectionStatus = 'pending' | 'in_progress' | 'completed' | 'overdue';

export interface InspectionItem {
  id: number;
  name: string;
  expected: string;
  result?: 'pass' | 'fail' | 'na';
  note?: string;
}

export interface InspectionResult {
  overall: 'pass' | 'partial' | 'fail';
  summary: string;
  operatorId: number;
  operatorName: string;
  completedAt: string;
  images?: string[];
}

export interface InspectionTask {
  id: number;
  stationId: number;
  stationName: string;
  deviceId: number;
  deviceName: string;
  type: InspectionType;
  status: InspectionStatus;
  scheduledDate: string;
  completedDate?: string;
  assignedTo?: number;
  assignedName?: string;
  description: string;
  items: InspectionItem[];
  result?: InspectionResult;
  createdAt: string;
  updatedAt: string;
}

// 巡检计划/模板 (Inspection Plans/Templates — /inspection/*)
export interface InspectionPlan {
  id: number;
  name: string;
  stationId: number;
  stationName?: string;
  deviceId?: number;
  deviceName?: string;
  type: InspectionType;
  status: InspectionStatus;
  scheduledDate: string;
  cycle?: string;
  assignedTo?: number;
  assignedName?: string;
  templateId?: number;
  description?: string;
  createdAt: string;
  updatedAt: string;
}

export interface InspectionTemplate {
  id: number;
  name: string;
  type: InspectionType;
  items: InspectionItem[];
  description?: string;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface InspectionTemplateCreate {
  name: string;
  category?: string;
  description?: string;
  items?: { name: string; required?: boolean }[];
}

export interface InspectionTemplateUpdate {
  name?: string;
  category?: string;
  description?: string;
  items?: { name: string; required?: boolean }[];
}

export interface InspectionTemplateCreated {
  id: number;
  name: string;
  description: string | null;
  items: { name: string; required: boolean }[];
  itemCount: number;
  deviceTypes: string[];
  target: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
}

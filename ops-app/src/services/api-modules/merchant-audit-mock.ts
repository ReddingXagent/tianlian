/**
 * api-modules/merchant-audit-mock.ts — 商户进件审核 mock 通道 (卡 a8ca56aa ops-app 审核侧)
 * 云端契约未定前的内存实现: 预置各状态样本申请, approve/reject 推进状态机;
 * 与 MerchantAuditClient 接口同构, merchant-audit-source 按 mode 切换.
 */
import type {
  MerchantApplication,
  MerchantApplicationFormInput,
  MerchantApplicationList,
  MerchantApplicationStatus,
} from '../../types';

/** 模拟网络延迟 (ms) */
const MOCK_LATENCY_MS = 120;

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function buildApplication(
  id: number,
  status: MerchantApplicationStatus,
  form: MerchantApplicationFormInput,
  rejectReason: string | null = null
): MerchantApplication {
  const now = new Date().toISOString();
  return {
    id,
    status,
    submittedAt: now,
    updatedAt: now,
    rejectReason,
    form: { ...form, photos: { ...form.photos } },
  };
}

/** 预置样本: 覆盖四态, 供审核列表演示 (reset 后恢复) */
function seedStore(): MerchantApplication[] {
  const photo = (name: string) => `file://mock-kyc/${name}.jpg`;
  const base = (companyName: string, uscc: string): MerchantApplicationFormInput => ({
    companyName,
    uscc,
    contactName: '王运营',
    contactPhone: '13800000000',
    bankName: '中国工商银行杭州分行',
    bankAccount: '1202020209876543210',
    photos: {
      license: photo('license'),
      idCardFront: photo('id-card-front'),
      idCardBack: photo('id-card-back'),
      bankCard: photo('bank-card'),
    },
  });
  return [
    buildApplication(1001, 'pending', base('杭州星星充电服务有限公司', '91330106MA2H0X9X1A')),
    buildApplication(1002, 'audit', base('宁波未来出行能源有限公司', '91330206MA2H1Y8Y2B')),
    buildApplication(
      1003,
      'rejected',
      base('温州速达充电桩安装有限公司', '91330300MA2H2Z7Z3C'),
      '营业执照照片模糊，请重新上传'
    ),
    buildApplication(1004, 'approved', base('绍兴绿能新能源科技有限公司', '91330600MA2H3A6A4D')),
  ];
}

let store: MerchantApplication[] = seedStore();

function clone(app: MerchantApplication): MerchantApplication {
  return { ...app, form: { ...app.form, photos: { ...app.form.photos } } };
}

/** 测试注入/重置口 (生产代码不得调用) */
export const __mockStore = {
  reset(): void {
    store = seedStore();
  },
  get current(): MerchantApplication[] {
    return store.map(clone);
  },
  seed(apps: MerchantApplication[]): void {
    store = apps.map(clone);
  },
};

export class MerchantAuditNotFoundError extends Error {
  constructor(id: number) {
    super(`进件申请不存在: ${id}`);
    this.name = 'MerchantAuditNotFoundError';
  }
}

export class MerchantAuditInvalidTransitionError extends Error {
  constructor(status: MerchantApplicationStatus) {
    super(`当前状态 ${status} 不可审核`);
    this.name = 'MerchantAuditInvalidTransitionError';
  }
}

/** 审核操作仅对 pending/audit 开放 (approved/rejected 为终态, rejected 由运营商重提产生新单) */
function assertAuditable(app: MerchantApplication): void {
  if (app.status !== 'pending' && app.status !== 'audit') {
    throw new MerchantAuditInvalidTransitionError(app.status);
  }
}

export const merchantAuditMockApi = {
  async listApplications(
    status?: MerchantApplicationStatus
  ): Promise<MerchantApplicationList> {
    await delay(MOCK_LATENCY_MS);
    const items = store.filter((a) => status === undefined || a.status === status);
    return { items: items.map(clone), total: items.length };
  },

  async getApplication(id: number): Promise<MerchantApplication> {
    await delay(MOCK_LATENCY_MS);
    const app = store.find((a) => a.id === id);
    if (!app) throw new MerchantAuditNotFoundError(id);
    return clone(app);
  },

  async approve(id: number): Promise<MerchantApplication> {
    await delay(MOCK_LATENCY_MS);
    const app = store.find((a) => a.id === id);
    if (!app) throw new MerchantAuditNotFoundError(id);
    assertAuditable(app);
    app.status = 'approved';
    app.updatedAt = new Date().toISOString();
    return clone(app);
  },

  async reject(id: number, reason: string): Promise<MerchantApplication> {
    await delay(MOCK_LATENCY_MS);
    const app = store.find((a) => a.id === id);
    if (!app) throw new MerchantAuditNotFoundError(id);
    assertAuditable(app);
    app.status = 'rejected';
    app.rejectReason = reason;
    app.updatedAt = new Date().toISOString();
    return clone(app);
  },
};

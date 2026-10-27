/**
 * MerchantAuditDetailScreen.test.tsx — 审核详情屏测试 (卡 a8ca56aa ops-app 审核侧)
 * 覆盖: 详情字段/证照槽位渲染、pending 操作区、驳回空原因校验、驳回/批准流转后刷新、
 *       rejected 显示驳回原因、approved/rejected 无操作区、null 申请空态
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import MerchantAuditDetailScreen from '../MerchantAuditDetailScreen';
import { merchantAudit } from '../../services/api-modules/merchant-audit-source';
import type { MerchantApplication } from '../../types';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useRoute: () => ({ params: { applicationId: 1001 } }),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('../../services/api-modules/merchant-audit-source', () => {
  const actual = jest.requireActual('../../services/api-modules/merchant-audit-mock');
  return {
    __esModule: true,
    merchantAudit: actual.merchantAuditMockApi,
    resolveMerchantAuditMode: () => 'mock',
    merchantAuditModeLabel: (m: string) => (m === 'real' ? '云端通道' : '模拟通道（契约未定）'),
    createMerchantAuditClient: () => actual.merchantAuditMockApi,
    realMerchantAuditAdapter: actual.merchantAuditMockApi,
    MERCHANT_AUDIT_MODE: 'mock',
  };
});

import { __mockStore as merchantAuditMockStore } from '../../services/api-modules/merchant-audit-mock';

const app = (
  status: MerchantApplication['status'],
  rejectReason: string | null = null
): MerchantApplication => ({
  id: 1001,
  status,
  submittedAt: '2026-10-24T01:00:00Z',
  updatedAt: '2026-10-24T01:00:00Z',
  rejectReason,
  form: {
    companyName: '杭州星星充电服务有限公司',
    uscc: '91330106MA2H0X9X1A',
    contactName: '王运营',
    contactPhone: '13800000000',
    bankName: '工商银行',
    bankAccount: '1202020209876543210',
    photos: {
      license: 'file://mock-kyc/license.jpg',
      idCardFront: 'file://mock-kyc/id-card-front.jpg',
      idCardBack: null,
      bankCard: null,
    },
  },
});

beforeEach(() => {
  jest.clearAllMocks();
  merchantAuditMockStore.reset();
});

describe('MerchantAuditDetailScreen — rendering', () => {
  it('renders application fields and photo slot states', async () => {
    merchantAuditMockStore.seed([app('pending')]);
    const { getByText, getAllByText } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getAllByText('杭州星星充电服务有限公司').length).toBeGreaterThanOrEqual(1);
    });
    expect(getByText('91330106MA2H0X9X1A')).toBeTruthy();
    expect(getByText('工商银行')).toBeTruthy();
    expect(getByText('1202020209876543210')).toBeTruthy();
    expect(getByText('营业执照')).toBeTruthy();
    // 4 槽位: 前 2 已上传(2处), 后 2 缺失(2处)
    expect(getAllByText('已上传 ✓')).toHaveLength(2);
    expect(getAllByText('缺失 ✗')).toHaveLength(2);
    expect(getByText(/申请编号 1001/)).toBeTruthy();
  });

  it('shows audit action panel for pending application', async () => {
    merchantAuditMockStore.seed([app('pending')]);
    const { getByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-approve-btn')).toBeTruthy();
    });
    expect(getByTestId('audit-reject-btn')).toBeTruthy();
    expect(getByTestId('audit-reject-reason')).toBeTruthy();
  });

  it('hides action panel and shows reason for rejected application', async () => {
    merchantAuditMockStore.seed([app('rejected', '营业执照照片模糊')]);
    const { getByText, queryByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByText('驳回原因：营业执照照片模糊')).toBeTruthy();
    });
    expect(queryByTestId('audit-approve-btn')).toBeNull();
    expect(getByText('该申请已驳回，等待运营商修改后重新提交')).toBeTruthy();
  });

  it('hides action panel for approved application', async () => {
    merchantAuditMockStore.seed([app('approved')]);
    const { getByText, queryByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByText('该申请已通过审核，无需操作')).toBeTruthy();
    });
    expect(queryByTestId('audit-approve-btn')).toBeNull();
  });
});

describe('MerchantAuditDetailScreen — actions', () => {
  it('rejects with empty reason shows inline error', async () => {
    merchantAuditMockStore.seed([app('pending')]);
    const { getByTestId, getByText } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-reject-btn')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-reject-btn'));
    await waitFor(() => {
      expect(getByText('请填写驳回原因')).toBeTruthy();
    });
  });

  it('rejects application with reason and refreshes to rejected view', async () => {
    merchantAuditMockStore.seed([app('audit')]);
    const { getByTestId, getByText, queryByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-reject-reason')).toBeTruthy();
    });
    fireEvent.changeText(getByTestId('audit-reject-reason'), '结算账户信息不符');
    fireEvent.press(getByTestId('audit-reject-btn'));
    await waitFor(() => {
      expect(getByText('驳回原因：结算账户信息不符')).toBeTruthy();
    });
    expect(queryByTestId('audit-reject-btn')).toBeNull();
  });

  it('approves application after Alert confirmation', async () => {
    merchantAuditMockStore.seed([app('pending')]);
    const alertSpy = jest
      .spyOn(Alert, 'alert')
      .mockImplementation((_t, _m, buttons) => {
        const confirm = buttons?.find((b) => b.text === '确认批准');
        confirm?.onPress?.();
      });
    const { getByTestId, getByText, queryByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-approve-btn')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-approve-btn'));
    await waitFor(() => {
      expect(getByText('该申请已通过审核，无需操作')).toBeTruthy();
    });
    expect(queryByTestId('audit-approve-btn')).toBeNull();
    alertSpy.mockRestore();
  });

  it('approve does not fire when Alert cancelled', async () => {
    merchantAuditMockStore.seed([app('pending')]);
    const approveSpy = jest.spyOn(merchantAudit, 'approve');
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByTestId } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-approve-btn')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-approve-btn'));
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalled();
    });
    expect(approveSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
    approveSpy.mockRestore();
  });

  it('shows action error when approve fails on terminal state', async () => {
    // 屏内轮询快照为 pending, 但通道操作因后端状态推进而失败
    merchantAuditMockStore.seed([app('pending')]);
    const approveSpy = jest
      .spyOn(merchantAudit, 'approve')
      .mockRejectedValue(new Error('当前状态 approved 不可审核'));
    const alertSpy = jest
      .spyOn(Alert, 'alert')
      .mockImplementation((_t, _m, buttons) => {
        const confirm = buttons?.find((b) => b.text === '确认批准');
        confirm?.onPress?.();
      });
    const { getByTestId, getByText } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByTestId('audit-approve-btn')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-approve-btn'));
    await waitFor(() => {
      expect(getByText('当前状态 approved 不可审核')).toBeTruthy();
    });
    alertSpy.mockRestore();
    approveSpy.mockRestore();
  });
});

describe('MerchantAuditDetailScreen — edge states', () => {
  it('shows not-found empty state when application is null', async () => {
    const spy = jest.spyOn(merchantAudit, 'getApplication').mockResolvedValue(null);
    const { getByText } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByText('申请不存在')).toBeTruthy();
    });
    spy.mockRestore();
  });

  it('shows error state when detail fetch fails', async () => {
    const spy = jest
      .spyOn(merchantAudit, 'getApplication')
      .mockRejectedValue(new Error('服务暂不可用'));
    const { getByText } = render(<MerchantAuditDetailScreen />);
    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });
    expect(getByText('服务暂不可用')).toBeTruthy();
    spy.mockRestore();
  });
});

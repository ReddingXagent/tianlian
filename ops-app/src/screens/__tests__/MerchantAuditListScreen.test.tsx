/**
 * MerchantAuditListScreen.test.tsx — 审核列表屏测试 (卡 a8ca56aa ops-app 审核侧)
 * 覆盖: 加载态、列表渲染+待处理计数、状态过滤、点击导航、错误态、空列表态
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import MerchantAuditListScreen from '../MerchantAuditListScreen';
import { merchantAudit } from '../../services/api-modules/merchant-audit-source';
import type { MerchantApplication } from '../../types';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
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
    // 其余导出供 barrel/其它 import 使用 (本屏只消费 merchantAudit)
    resolveMerchantAuditMode: () => 'mock',
    merchantAuditModeLabel: (m: string) => (m === 'real' ? '云端通道' : '模拟通道（契约未定）'),
    createMerchantAuditClient: () => actual.merchantAuditMockApi,
    realMerchantAuditAdapter: actual.merchantAuditMockApi,
    MERCHANT_AUDIT_MODE: 'mock',
  };
});

import { __mockStore as merchantAuditMockStore } from '../../services/api-modules/merchant-audit-mock';

const baseForm = (companyName: string): MerchantApplication['form'] => ({
  companyName,
  uscc: '91330106MA2H0X9X1A',
  contactName: '王运营',
  contactPhone: '13800000000',
  bankName: '工商银行',
  bankAccount: '1202020209876543210',
  photos: {
    license: 'file://mock-kyc/license.jpg',
    idCardFront: null,
    idCardBack: null,
    bankCard: null,
  },
});

const app = (
  id: number,
  status: MerchantApplication['status'],
  companyName: string
): MerchantApplication => ({
  id,
  status,
  submittedAt: '2026-10-24T01:00:00Z',
  updatedAt: '2026-10-24T01:00:00Z',
  rejectReason: status === 'rejected' ? '照片模糊' : null,
  form: baseForm(companyName),
});

describe('MerchantAuditListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    merchantAuditMockStore.reset();
  });

  it('renders seed list with pending count', async () => {
    merchantAuditMockStore.seed([
      app(1, 'pending', '待审公司A'),
      app(2, 'audit', '在审公司B'),
      app(3, 'approved', '已过公司C'),
    ]);
    const { getByText, getByTestId } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('待审公司A')).toBeTruthy();
    });
    expect(getByText('在审公司B')).toBeTruthy();
    expect(getByText('已过公司C')).toBeTruthy();
    expect(getByText('待处理 2 件')).toBeTruthy();
    expect(getByTestId('audit-item-1')).toBeTruthy();
  });

  it('filters list by status chip', async () => {
    merchantAuditMockStore.seed([
      app(1, 'pending', '待审公司A'),
      app(2, 'approved', '已过公司C'),
    ]);
    const { getByText, queryByText, getByTestId } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('待审公司A')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-filter-approved'));
    await waitFor(() => {
      expect(queryByText('待审公司A')).toBeNull();
    });
    expect(getByText('已过公司C')).toBeTruthy();
  });

  it('shows empty state for filter with no items', async () => {
    merchantAuditMockStore.seed([app(1, 'pending', '待审公司A')]);
    const { getByText, getByTestId } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('待审公司A')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-filter-rejected'));
    await waitFor(() => {
      expect(getByText('该状态下无申请')).toBeTruthy();
    });
  });

  it('navigates to detail on item press', async () => {
    merchantAuditMockStore.seed([app(1001, 'pending', '待审公司A')]);
    const { getByText, getByTestId } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('待审公司A')).toBeTruthy();
    });
    fireEvent.press(getByTestId('audit-item-1001'));
    expect(mockNavigate).toHaveBeenCalledWith('MerchantAuditDetail', { applicationId: 1001 });
  });

  it('shows error state when listing fails', async () => {
    const spy = jest.spyOn(merchantAudit, 'listApplications').mockRejectedValue(new Error('网络异常'));
    const { getByText } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });
    expect(getByText('网络异常')).toBeTruthy();
    spy.mockRestore();
  });

  it('shows empty state when no applications exist', async () => {
    merchantAuditMockStore.seed([]);
    const { getByText } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('暂无进件申请')).toBeTruthy();
    });
  });

  it('shows company placeholder when name missing', async () => {
    merchantAuditMockStore.seed([app(7, 'pending', '')]);
    const { getByText } = render(<MerchantAuditListScreen />);
    await waitFor(() => {
      expect(getByText('申请 #7')).toBeTruthy();
    });
  });
});

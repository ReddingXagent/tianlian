/**
 * WorkOrderDetailScreen 扩展覆盖率
 * 目标: branches 60.86% → 80%+
 * 覆盖: cancelled status, record with note, record unknown action,
 *        handleAction (accept/execute/complete) success+fail,
 *        loadRecords error, null order, type labels, completedAt, description fallback
 */
import { Alert } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import WorkOrderDetailScreen from '../WorkOrderDetailScreen';
import { useWorkOrderStore } from '../../store/workOrderStore';
import { workOrderRecordApi, workOrderActionApi } from '../../services/api';

const mockFetchOrderDetail = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 'WO-1' } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/workOrderStore', () => ({
  useWorkOrderStore: jest.fn(),
}));

jest.mock('../../services/api', () => ({
  workOrderRecordApi: { getRecords: jest.fn() },
  workOrderActionApi: {
    accept: jest.fn(),
    start: jest.fn(),
    complete: jest.fn(),
  },
}));

const BASE_ORDER = {
  id: 'WO-1',
  stationId: 1,
  stationName: '充电站A',
  title: '维修工单',
  description: '设备故障描述',
  type: 'repair',
  priority: 'high',
  status: 'pending',
  creatorId: 1,
  creatorName: '创建人',
  assigneeId: 2,
  assigneeName: '张三',
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

const storeReturn = (overrides: Record<string, unknown> = {}) => ({
  selectedOrder: BASE_ORDER,
  loading: false,
  error: null,
  fetchOrderDetail: mockFetchOrderDetail,
  ...overrides,
});

describe('WorkOrderDetailScreen — 扩展覆盖', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrderDetail.mockResolvedValue(undefined);
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({ data: [] });
    (workOrderActionApi.accept as jest.Mock).mockResolvedValue({});
    (workOrderActionApi.start as jest.Mock).mockResolvedValue({});
    (workOrderActionApi.complete as jest.Mock).mockResolvedValue({});
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(storeReturn());
  });

  // --- cancelled status ---

  it('cancelled status → 显示已取消', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, status: 'cancelled' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('❌ 工单已取消')).toBeTruthy();
  });

  // --- record with note ---

  it('record有note → 渲染备注', async () => {
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({
      data: [
        {
          id: 1, orderId: 'WO-1', action: 'created',
          operatorId: 1, operatorName: '系统',
          note: '工单创建', createdAt: '2024-01-15T10:00:00Z',
        },
      ],
    });
    const { findByText } = render(<WorkOrderDetailScreen />);
    expect(await findByText('工单创建')).toBeTruthy();
  });

  // --- record unknown action fallback ---

  it('record未知action → 显示原始值', async () => {
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({
      data: [
        {
          id: 1, orderId: 'WO-1', action: 'custom_action',
          operatorId: 1, operatorName: '测试',
          note: null, createdAt: '2024-01-15T10:00:00Z',
        },
      ],
    });
    const { findByText } = render(<WorkOrderDetailScreen />);
    expect(await findByText('custom_action')).toBeTruthy();
  });

  // --- multiple records with timeline line ---

  it('多条record → 渲染timeline连线', async () => {
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({
      data: [
        { id: 1, orderId: 'WO-1', action: 'created', operatorId: 1, operatorName: 'A', note: null, createdAt: '2024-01-15T10:00:00Z' },
        { id: 2, orderId: 'WO-1', action: 'accepted', operatorId: 2, operatorName: 'B', note: '接单处理', createdAt: '2024-01-15T11:00:00Z' },
      ],
    });
    const { findByText } = render(<WorkOrderDetailScreen />);
    expect(await findByText('接单')).toBeTruthy();
    expect(await findByText('接单处理')).toBeTruthy();
  });

  // --- handleAction: accept success ---

  it('handleAction accept → 成功 Alert', async () => {
    let capturedButtons: any[] = [];
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_, __, buttons) => {
      capturedButtons = buttons || [];
    });
    const { getByText } = render(<WorkOrderDetailScreen />);
    fireEvent.press(getByText('📋 接单'));
    // Press 确定
    const okBtn = capturedButtons[1];
    await waitFor(() => {
      okBtn?.onPress?.();
    });
    await waitFor(() => {
      expect(workOrderActionApi.accept).toHaveBeenCalledWith('WO-1');
    });
    alertSpy.mockRestore();
  });

  // --- handleAction: execute ---

  it('handleAction execute → start 调用', async () => {
    let capturedButtons: any[] = [];
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_, __, buttons) => {
      capturedButtons = buttons || [];
    });
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, status: 'in_progress' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    fireEvent.press(getByText('🔧 到场并开始执行'));
    const okBtn = capturedButtons[1];
    await waitFor(() => {
      okBtn?.onPress?.();
    });
    await waitFor(() => {
      expect(workOrderActionApi.start).toHaveBeenCalledWith('WO-1');
    });
    alertSpy.mockRestore();
  });

  // --- handleAction: complete ---

  it('handleAction complete → complete 调用', async () => {
    let capturedButtons: any[] = [];
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_, __, buttons) => {
      capturedButtons = buttons || [];
    });
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, status: 'in_progress' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    fireEvent.press(getByText('✅ 标记完成'));
    const okBtn = capturedButtons[1];
    await waitFor(() => {
      okBtn?.onPress?.();
    });
    await waitFor(() => {
      expect(workOrderActionApi.complete).toHaveBeenCalledWith('WO-1');
    });
    alertSpy.mockRestore();
  });

  // --- handleAction: failure ---

  it('handleAction accept fail → Alert 操作失败', async () => {
    (workOrderActionApi.accept as jest.Mock).mockRejectedValue(new Error('fail'));
    let capturedButtons: any[] = [];
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_, __, buttons) => {
      capturedButtons = buttons || [];
    });
    const { getByText } = render(<WorkOrderDetailScreen />);
    fireEvent.press(getByText('📋 接单'));
    const okBtn = capturedButtons[1];
    await waitFor(() => {
      okBtn?.onPress?.();
    });
    await waitFor(() => {
      // After accept fails, should show error alert
      expect(alertSpy).toHaveBeenCalledWith('操作失败', '请重试');
    });
    alertSpy.mockRestore();
  });

  // --- loadRecords error (silent catch) ---

  it('loadRecords reject → 不崩溃', async () => {
    (workOrderRecordApi.getRecords as jest.Mock).mockRejectedValue(new Error('net'));
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('基本信息')).toBeTruthy();
  });

  // --- null order ---

  it('order=null → 渲染不崩溃', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: null })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('基本信息')).toBeTruthy();
  });

  // --- type label fallback ---

  it('unknown type → 显示原始值', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, type: 'custom' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('custom')).toBeTruthy();
  });

  // --- completedAt rendering ---

  it('completedAt存在 → 渲染完成时间', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedOrder: {
          ...BASE_ORDER, status: 'completed',
          completedAt: '2024-01-20T10:00:00Z',
        },
      })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('✅ 工单已完成')).toBeTruthy();
  });

  // --- description fallback ---

  it('description为空 → 显示暂无描述', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, description: '' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('暂无描述')).toBeTruthy();
  });

  // --- error + selectedOrder: show content ---

  it('error但selectedOrder存在 → 显示内容', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ error: 'some err', selectedOrder: BASE_ORDER })
    );
    const { getByText, queryByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('维修工单')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });
});

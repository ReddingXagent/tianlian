import React from 'react';
import { Alert } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
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

const MOCK_RECORDS = [
  {
    id: 1,
    orderId: 'WO-1',
    action: 'created',
    operatorId: 1,
    operatorName: '系统',
    note: '工单创建',
    createdAt: '2024-01-15T10:00:00Z',
  },
];

const storeReturn = (overrides: Record<string, unknown> = {}) => ({
  selectedOrder: BASE_ORDER,
  loading: false,
  error: null,
  fetchOrderDetail: mockFetchOrderDetail,
  ...overrides,
});

describe('WorkOrderDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchOrderDetail.mockResolvedValue(undefined);
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({
      data: MOCK_RECORDS,
    });
    (workOrderActionApi.accept as jest.Mock).mockResolvedValue({});
    (workOrderActionApi.start as jest.Mock).mockResolvedValue({});
    (workOrderActionApi.complete as jest.Mock).mockResolvedValue({});
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(storeReturn());
  });

  it('shows loading spinner initially', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: null, loading: true })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('加载工单详情...')).toBeTruthy();
  });

  it('shows error state when load fails', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: null, error: '加载出错' })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('加载失败')).toBeTruthy();
  });

  it('renders order detail and execution records', async () => {
    const { findByText, getByText } = render(<WorkOrderDetailScreen />);
    expect(await findByText('维修工单')).toBeTruthy();
    expect(getByText('基本信息')).toBeTruthy();
    expect(getByText('设备故障描述')).toBeTruthy();
    expect(await findByText('工单创建')).toBeTruthy();
    expect(await findByText('创建工单')).toBeTruthy();
  });

  it('shows accept button for a pending order and confirms', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText } = render(<WorkOrderDetailScreen />);
    fireEvent.press(getByText('📋 接单'));
    expect(alertSpy).toHaveBeenCalledWith(
      '确认操作',
      expect.any(String),
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });

  it('shows execute and complete buttons for an in-progress order', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, status: 'in_progress' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('🔧 到场并开始执行')).toBeTruthy();
    expect(getByText('✅ 标记完成')).toBeTruthy();
  });

  it('shows completed hint for a completed order', () => {
    (useWorkOrderStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedOrder: { ...BASE_ORDER, status: 'completed' } })
    );
    const { getByText } = render(<WorkOrderDetailScreen />);
    expect(getByText('✅ 工单已完成')).toBeTruthy();
  });

  it('shows empty records placeholder when there are none', async () => {
    (workOrderRecordApi.getRecords as jest.Mock).mockResolvedValue({ data: [] });
    const { findByText } = render(<WorkOrderDetailScreen />);
    expect(await findByText('暂无执行记录')).toBeTruthy();
  });
});

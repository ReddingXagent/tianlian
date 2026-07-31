import React from 'react';
import { Alert } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import WorkOrderCreateScreen from '../WorkOrderCreateScreen';
import { useWorkOrderEnhancedStore } from '../../store/workOrderEnhancedStore';

const mockCreateOrder = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn(), replace: jest.fn() }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../store/workOrderEnhancedStore', () => ({
  useWorkOrderEnhancedStore: jest.fn(),
}));

describe('WorkOrderCreateScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCreateOrder.mockResolvedValue({ id: 'WO-9' });
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: false,
      createError: null,
      createOrder: mockCreateOrder,
    });
  });

  it('renders form fields, type and priority chips', () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    expect(getByText('创建工单')).toBeTruthy();
    expect(getByText('工单标题 *')).toBeTruthy();
    expect(getByText('维修')).toBeTruthy();
    expect(getByText('巡检')).toBeTruthy();
    expect(getByText('紧急')).toBeTruthy();
    expect(getByText('提交工单')).toBeTruthy();
  });

  it('shows error when title is empty', () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.press(getByText('提交工单'));
    expect(getByText('请输入工单标题')).toBeTruthy();
    expect(mockCreateOrder).not.toHaveBeenCalled();
  });

  it('shows error when description is empty', () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '故障');
    fireEvent.press(getByText('提交工单'));
    expect(getByText('请输入工单描述')).toBeTruthy();
  });

  it('shows error when station id is invalid', () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '故障');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '描述');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), 'abc');
    fireEvent.press(getByText('提交工单'));
    expect(getByText('请输入有效的站点ID')).toBeTruthy();
  });

  it('submits with selected type and priority', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '故障');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '描述');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '3');
    fireEvent.press(getByText('安装'));
    fireEvent.press(getByText('紧急'));
    await act(async () => {
      fireEvent.press(getByText('提交工单'));
    });
    expect(mockCreateOrder).toHaveBeenCalledWith({
      title: '故障',
      description: '描述',
      stationId: 3,
      type: 'installation',
      priority: 'urgent',
    });
    expect(alertSpy).toHaveBeenCalledWith(
      '创建成功',
      expect.any(String),
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });

  it('shows store create error', () => {
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: false,
      createError: '创建工单失败',
      createOrder: mockCreateOrder,
    });
    const { getByText } = render(<WorkOrderCreateScreen />);
    expect(getByText('创建工单失败')).toBeTruthy();
  });
});

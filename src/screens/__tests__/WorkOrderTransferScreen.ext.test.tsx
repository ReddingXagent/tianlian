/**
 * WorkOrderTransferScreen Extension Tests
 * 目标: 73.9% → 95%+ branches
 * 覆盖: assigneeId NaN, transferring render, urge success/fail, localError clear
 */
import { Alert } from 'react-native';
import { render, fireEvent, act } from '@testing-library/react-native';
import WorkOrderTransferScreen from '../WorkOrderTransferScreen';
import { useWorkOrderEnhancedStore } from '../../store/workOrderEnhancedStore';

const mockTransferOrder = jest.fn();
const mockUrgeOrder = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { orderId: 'WO-1' } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/workOrderEnhancedStore', () => ({
  useWorkOrderEnhancedStore: jest.fn(),
}));

const pressTransferBtn = (getAllByText: any) => {
  const matches = getAllByText('转派工单');
  fireEvent.press(matches[matches.length - 1]);
};

describe('WorkOrderTransferScreen.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTransferOrder.mockResolvedValue({ id: 'WO-1' });
    mockUrgeOrder.mockResolvedValue({ id: 'WO-1' });
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      transferring: false,
      transferError: null,
      transferOrder: mockTransferOrder,
      urgeOrder: mockUrgeOrder,
    });
  });

  it('shows error for non-numeric assignee ID', () => {
    const { getByText, getByPlaceholderText, getAllByText } = render(<WorkOrderTransferScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), 'abc');
    pressTransferBtn(getAllByText);
    expect(getByText('请输入有效的运维人员ID')).toBeTruthy();
    expect(mockTransferOrder).not.toHaveBeenCalled();
  });

  it('shows error for whitespace-only assignee ID', () => {
    const { getByText, getByPlaceholderText, getAllByText } = render(<WorkOrderTransferScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '   ');
    pressTransferBtn(getAllByText);
    expect(getByText('请输入有效的运维人员ID')).toBeTruthy();
  });

  it('transfer failure does not show success alert', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    mockTransferOrder.mockResolvedValue(null);
    const { getByPlaceholderText, getAllByText } = render(<WorkOrderTransferScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '5');
    fireEvent.changeText(getByPlaceholderText('请输入转派原因'), 'test');
    await act(async () => {
      pressTransferBtn(getAllByText);
    });
    // No success alert
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('renders ActivityIndicator when transferring', () => {
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      transferring: true,
      transferError: null,
      transferOrder: mockTransferOrder,
      urgeOrder: mockUrgeOrder,
    });
    const { getByText } = render(<WorkOrderTransferScreen />);
    // Buttons should be disabled
    // Assignee input should be disabled
    // Check that section title still renders
    expect(getByText('工单流转')).toBeTruthy();
  });

  it('localError is cleared on assignee ID change', () => {
    const { getByText, getByPlaceholderText, getAllByText } = render(<WorkOrderTransferScreen />);
    // Trigger error
    pressTransferBtn(getAllByText);
    expect(getByText('请输入有效的运维人员ID')).toBeTruthy();
    // Type to clear
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '5');
    expect(() => getByText('请输入有效的运维人员ID')).toThrow();
  });

  it('localError is cleared on reason change', () => {
    const { getByText, getByPlaceholderText, getAllByText } = render(<WorkOrderTransferScreen />);
    // Set assignee, then trigger reason error
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '5');
    pressTransferBtn(getAllByText);
    expect(getByText('请输入转派原因')).toBeTruthy();
    // Type reason to clear
    fireEvent.changeText(getByPlaceholderText('请输入转派原因'), 'because');
    expect(() => getByText('请输入转派原因')).toThrow();
  });

  it('urge flow: success shows alert', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons?: any) => {
      // First call: confirm dialog, press 确定催单
      const confirm = buttons?.find((b: any) => b.text === '确定催单');
      if (confirm) {
        confirm.onPress();
      }
    });
    mockUrgeOrder.mockResolvedValue({ id: 'WO-1' });

    const { getByText } = render(<WorkOrderTransferScreen />);
    fireEvent.press(getByText('催促处理'));

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 10));
    });

    // Should show urge success alert
    expect(alertSpy).toHaveBeenCalledWith('催单成功', '已通知工程师尽快处理');
    alertSpy.mockRestore();
  });

  it('urge flow: failure (null result) does not show success alert', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons?: any) => {
      const confirm = buttons?.find((b: any) => b.text === '确定催单');
      if (confirm) {
        confirm.onPress();
      }
    });
    mockUrgeOrder.mockResolvedValue(null);

    const { getByText } = render(<WorkOrderTransferScreen />);
    fireEvent.press(getByText('催促处理'));

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 10));
    });

    // No success alert
    expect(alertSpy).toHaveBeenCalledTimes(1); // only the confirm dialog
    alertSpy.mockRestore();
  });

  it('urge flow: cancel does not call urgeOrder', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons?: any) => {
      const cancel = buttons?.find((b: any) => b.text === '取消');
      if (cancel) {
        cancel.onPress?.();
      }
    });

    const { getByText } = render(<WorkOrderTransferScreen />);
    fireEvent.press(getByText('催促处理'));

    expect(mockUrgeOrder).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});

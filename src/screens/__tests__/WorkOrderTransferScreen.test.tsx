import { Alert, type AlertButton } from 'react-native';
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

const pressTransferButton = (getAllByText: (text: string) => { testID?: string }[]) => {
  const matches = getAllByText('转派工单');
  fireEvent.press(matches[matches.length - 1]);
};

describe('WorkOrderTransferScreen', () => {
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

  it('renders transfer and urge sections', () => {
    const { getByText } = render(<WorkOrderTransferScreen />);
    expect(getByText('工单流转')).toBeTruthy();
    expect(getByText('催促处理')).toBeTruthy();
  });

  it('shows error when assignee id is invalid', () => {
    const { getByText, getAllByText } = render(<WorkOrderTransferScreen />);
    pressTransferButton(getAllByText);
    expect(getByText('请输入有效的运维人员ID')).toBeTruthy();
    expect(mockTransferOrder).not.toHaveBeenCalled();
  });

  it('shows error when reason is empty', () => {
    const { getByText, getByPlaceholderText, getAllByText } = render(
      <WorkOrderTransferScreen />
    );
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '5');
    pressTransferButton(getAllByText);
    expect(getByText('请输入转派原因')).toBeTruthy();
  });

  it('transfers the order successfully', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByPlaceholderText, getAllByText } = render(
      <WorkOrderTransferScreen />
    );
    fireEvent.changeText(getByPlaceholderText('请输入运维人员ID'), '5');
    fireEvent.changeText(getByPlaceholderText('请输入转派原因'), '需要专人处理');
    await act(async () => {
      pressTransferButton(getAllByText);
    });
    expect(mockTransferOrder).toHaveBeenCalledWith('WO-1', 5, '需要专人处理');
    expect(alertSpy).toHaveBeenCalledWith(
      '转派成功',
      expect.any(String),
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });

  it('shows store transfer error', () => {
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      transferring: false,
      transferError: '转派失败',
      transferOrder: mockTransferOrder,
      urgeOrder: mockUrgeOrder,
    });
    const { getByText } = render(<WorkOrderTransferScreen />);
    expect(getByText('转派失败')).toBeTruthy();
  });

  it('urges the order after confirmation', () => {
    let buttons: AlertButton[] = [];
    const alertSpy = jest
      .spyOn(Alert, 'alert')
      .mockImplementation((_t, _m, b) => {
        buttons = b || [];
      });
    const { getByText } = render(<WorkOrderTransferScreen />);
    fireEvent.press(getByText('催促处理'));
    const confirm = buttons.find((b) => b.text === '确定催单');
    act(() => {
      confirm.onPress();
    });
    expect(mockUrgeOrder).toHaveBeenCalledWith('WO-1', '请尽快处理');
    alertSpy.mockRestore();
  });
});

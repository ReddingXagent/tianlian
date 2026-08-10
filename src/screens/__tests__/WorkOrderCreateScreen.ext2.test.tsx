/**
 * WorkOrderCreateScreen ext2 — lines 73-79: order success Alert buttons
 * Cover: "查看详情" (navigation.replace) and "继续创建" (form reset)
 */
import { Alert, type AlertButton } from 'react-native';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import WorkOrderCreateScreen from '../WorkOrderCreateScreen';
import { useWorkOrderEnhancedStore } from '../../store/workOrderEnhancedStore';

const mockNavigate = jest.fn();
const mockReplace = jest.fn();
const mockCreateOrder = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate, replace: mockReplace, goBack: jest.fn() }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../store/workOrderEnhancedStore', () => ({
  useWorkOrderEnhancedStore: jest.fn(),
}));

describe('WorkOrderCreateScreen.ext2 — success alert buttons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCreateOrder.mockResolvedValue({ id: 42, title: 'New Order' });
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: false, createError: null, createOrder: mockCreateOrder,
    });
  });

  // Line 75: "查看详情" button → navigation.replace('WorkOrderDetail', { orderId })
  it('success alert "查看详情" calls navigation.replace', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title: string, _msg: string, buttons?: AlertButton[]) => {
      if (buttons && buttons[0] && buttons[0].onPress) {
        buttons[0].onPress();
      }
    });

    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '测试工单');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '测试描述');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '1');

    await act(async () => {
      fireEvent.press(getByText('提交工单'));
      await new Promise(r => setTimeout(r, 100));
    });

    expect(mockCreateOrder).toHaveBeenCalledWith(expect.objectContaining({
      title: '测试工单',
      description: '测试描述',
      stationId: 1,
    }));
    expect(mockReplace).toHaveBeenCalledWith('WorkOrderDetail', { orderId: 42 });
    alertSpy.mockRestore();
  });

  // Lines 76-79: "继续创建" button → reset form fields
  it('success alert "继续创建" resets form fields', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title: string, _msg: string, buttons?: AlertButton[]) => {
      if (buttons && buttons[1] && buttons[1].onPress) {
        buttons[1].onPress();
      }
    });

    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '测试工单');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '测试描述');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '1');

    await act(async () => {
      fireEvent.press(getByText('提交工单'));
      await new Promise(r => setTimeout(r, 100));
    });

    await waitFor(() => {
      expect(getByPlaceholderText('请输入工单标题').props.value).toBe('');
    });
    expect(getByPlaceholderText('请详细描述工单内容').props.value).toBe('');
    expect(getByPlaceholderText('请输入站点ID').props.value).toBe('');
    alertSpy.mockRestore();
  });

  // createOrder returns null (no order) → no alert
  it('does not show success alert when createOrder returns null', async () => {
    mockCreateOrder.mockResolvedValue(null);
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});

    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), 'T');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), 'D');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '1');

    await act(async () => {
      fireEvent.press(getByText('提交工单'));
      await new Promise(r => setTimeout(r, 100));
    });

    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  // whitespace description triggers validation
  it('whitespace description triggers validation', async () => {
    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), 'Test');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '   ');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '1');
    fireEvent.press(getByText('提交工单'));

    await waitFor(() => {
      expect(getByText('请输入工单描述')).toBeTruthy();
    });
  });

  // whitespace title triggers validation
  it('whitespace title triggers validation', async () => {
    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '   ');
    fireEvent.press(getByText('提交工单'));

    await waitFor(() => {
      expect(getByText('请输入工单标题')).toBeTruthy();
    });
  });

  // whitespace stationId triggers validation
  it('whitespace stationId triggers validation', async () => {
    const { getByPlaceholderText, getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), 'T');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), 'D');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), '   ');
    fireEvent.press(getByText('提交工单'));

    await waitFor(() => {
      expect(getByText('请输入有效的站点ID')).toBeTruthy();
    });
  });
});

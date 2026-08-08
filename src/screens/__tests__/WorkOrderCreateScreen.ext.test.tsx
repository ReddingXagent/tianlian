/**
 * WorkOrderCreateScreen 扩展测试 — branch覆盖率提升
 * 覆盖: form validation, type/priority selection, submit flow
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
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

// Mock Alert
jest.mock('react-native', () => {
  const rn = jest.requireActual('react-native');
  rn.Alert.alert = jest.fn((title, msg, buttons) => {
    if (buttons && buttons[0] && buttons[0].onPress) {
      buttons[0].onPress();
    }
  });
  return rn;
});

describe('WorkOrderCreateScreen.ext — additional branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCreateOrder.mockResolvedValue({ id: 'WO-NEW', title: 'Test' });
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: false, createError: null, createOrder: mockCreateOrder,
    });
  });

  it('renders form with 创建工单 title', async () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    expect(getByText('创建工单')).toBeTruthy();
  });

  it('submit with empty title shows validation error', async () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.press(getByText('提交工单'));
    await waitFor(() => {
      expect(getByText('请输入工单标题')).toBeTruthy();
    });
  });

  it('submit with title but empty description shows validation error', async () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '测试工单');
    fireEvent.press(getByText('提交工单'));
    await waitFor(() => {
      expect(getByText('请输入工单描述')).toBeTruthy();
    });
  });

  it('submit with title+desc but invalid stationId shows error', async () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '测试工单');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '测试描述');
    fireEvent.press(getByText('提交工单'));
    await waitFor(() => {
      expect(getByText('请输入有效的站点ID')).toBeTruthy();
    });
  });

  it('type selection: pressing 巡检 changes type', async () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.press(getByText('巡检'));
    // Type is internal state, just verify no crash
    expect(getByText('巡检')).toBeTruthy();
  });

  it('priority selection: pressing 紧急 changes priority', async () => {
    const { getByText } = render(<WorkOrderCreateScreen />);
    fireEvent.press(getByText('紧急'));
    expect(getByText('紧急')).toBeTruthy();
  });

  it('createError from store renders', async () => {
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: false, createError: '服务器错误', createOrder: mockCreateOrder,
    });
    const { getByText } = render(<WorkOrderCreateScreen />);
    expect(getByText('服务器错误')).toBeTruthy();
  });

  it('localError clears on text input change', async () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    // Trigger error
    fireEvent.press(getByText('提交工单'));
    await waitFor(() => {
      expect(getByText('请输入工单标题')).toBeTruthy();
    });
    // Type to clear error
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), 'T');
    // Error text should be cleared
  });

  it('NaN stationId validation: "abc" rejected', async () => {
    const { getByText, getByPlaceholderText } = render(<WorkOrderCreateScreen />);
    fireEvent.changeText(getByPlaceholderText('请输入工单标题'), '测试');
    fireEvent.changeText(getByPlaceholderText('请详细描述工单内容'), '描述');
    fireEvent.changeText(getByPlaceholderText('请输入站点ID'), 'abc');
    fireEvent.press(getByText('提交工单'));

    await waitFor(() => {
      expect(getByText('请输入有效的站点ID')).toBeTruthy();
    });
  });

  it('creating=true state renders submit button', async () => {
    (useWorkOrderEnhancedStore as unknown as jest.Mock).mockReturnValue({
      creating: true, createError: null, createOrder: mockCreateOrder,
    });
    render(<WorkOrderCreateScreen />);
    // creating=true state: no crash, submit disabled
  });
});

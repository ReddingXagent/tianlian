import { Alert } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import InspectionDetailScreen from '../InspectionDetailScreen';
import { useInspectionStore } from '../../store/inspectionStore';

const mockFetchTaskDetail = jest.fn();
const mockStartTask = jest.fn();
const mockUpdateItem = jest.fn();
const mockCompleteTask = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { taskId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: jest.fn(),
}));

const BASE_TASK = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  deviceId: 1,
  deviceName: '充电桩01',
  type: 'daily',
  status: 'pending',
  scheduledDate: '2024-01-15T00:00:00Z',
  description: '日常巡检任务',
  items: [
    { id: 1, name: '检查项一', expected: '正常' },
    { id: 2, name: '检查项二', expected: '正常' },
  ],
  createdAt: '',
  updatedAt: '',
};

const storeReturn = (overrides: Record<string, unknown> = {}) => ({
  selectedTask: BASE_TASK,
  loading: false,
  error: null,
  submitting: false,
  fetchTaskDetail: mockFetchTaskDetail,
  startTask: mockStartTask,
  updateItem: mockUpdateItem,
  completeTask: mockCompleteTask,
  ...overrides,
});

describe('InspectionDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTaskDetail.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(storeReturn());
  });

  it('shows loading spinner initially', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: null, loading: true })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('加载巡检详情...')).toBeTruthy();
  });

  it('shows error state when load fails', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: null, error: '加载出错' })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('加载出错')).toBeTruthy();
  });

  it('renders task detail and inspection items', () => {
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('日常巡检任务')).toBeTruthy();
    expect(getByText('充电桩01')).toBeTruthy();
    expect(getByText('基本信息')).toBeTruthy();
    expect(getByText('检查项一')).toBeTruthy();
    expect(getByText('检查项二')).toBeTruthy();
  });

  it('shows start button for a pending task and confirms', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getByText('开始巡检'));
    expect(alertSpy).toHaveBeenCalledWith(
      '开始巡检',
      expect.any(String),
      expect.any(Array)
    );
    alertSpy.mockRestore();
  });

  it('shows item actions and complete button for an in-progress task', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getByText, getAllByText } = render(<InspectionDetailScreen />);
    expect(getByText('完成巡检')).toBeTruthy();
    expect(getAllByText('✅ 通过').length).toBe(2);
    expect(getAllByText('❌ 不通过').length).toBe(2);
  });

  it('updates an item result when pressing pass', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getAllByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getAllByText('✅ 通过')[0]);
    expect(mockUpdateItem).toHaveBeenCalledWith(1, 1, 'pass');
  });

  it('shows completed hint and result for a completed task', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'completed',
          result: {
            overall: 'pass',
            summary: '一切正常',
            operatorId: 1,
            operatorName: '王五',
            completedAt: '2024-01-15T12:00:00Z',
          },
        },
      })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('✅ 巡检已完成')).toBeTruthy();
    expect(getByText('一切正常')).toBeTruthy();
  });
});

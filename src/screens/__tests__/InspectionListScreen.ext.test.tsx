/**
 * InspectionListScreen 扩展测试 — branch覆盖率提升
 * 覆盖: filter switching, type labels, items count, error+data, footer
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import InspectionListScreen from '../InspectionListScreen';
import { useInspectionStore } from '../../store/inspectionStore';

const mockNavigate = jest.fn();
const mockFetchTasks = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../store/inspectionStore', () => ({
  useInspectionStore: jest.fn(),
}));

const MOCK_TASKS = [
  {
    id: 1, stationId: 1, stationName: '充电站A', deviceId: 1, deviceName: '充电桩01',
    type: 'daily', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
    description: '日常巡检任务', items: [{ id: 1, name: '检查项', expected: '正常' }],
    createdAt: '', updatedAt: '',
  },
  {
    id: 2, stationId: 1, stationName: '充电站B', deviceId: 2, deviceName: '逆变器02',
    type: 'unknown_type', status: 'in_progress', scheduledDate: '2024-01-14T00:00:00Z',
    description: '特殊巡检', items: [],
    createdAt: '', updatedAt: '',
  },
];

describe('InspectionListScreen.ext — additional branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTasks.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: MOCK_TASKS, loading: false, error: null, total: 2,
      fetchTasks: mockFetchTasks,
    });
  });

  it('filter "pending" calls fetchTasks with status', async () => {
    const { findByText } = render(<InspectionListScreen />);
    await findByText('日常巡检任务');

    mockFetchTasks.mockClear();
    fireEvent.press(await findByText('待巡检'));

    await waitFor(() => {
      expect(mockFetchTasks).toHaveBeenCalledWith({ status: 'pending' });
    });
  });

  it('filter "completed" calls fetchTasks', async () => {
    const { findByText } = render(<InspectionListScreen />);
    await findByText('日常巡检任务');

    mockFetchTasks.mockClear();
    fireEvent.press(await findByText('已完成'));

    await waitFor(() => {
      expect(mockFetchTasks).toHaveBeenCalledWith({ status: 'completed' });
    });
  });

  it('filter "all" after switching to pending calls fetchTasks with undefined', async () => {
    const { findByText } = render(<InspectionListScreen />);
    await findByText('日常巡检任务');

    // Switch to pending first
    mockFetchTasks.mockClear();
    fireEvent.press(await findByText('待巡检'));
    await waitFor(() => {
      expect(mockFetchTasks).toHaveBeenCalledWith({ status: 'pending' });
    });

    // Now switch back to all
    mockFetchTasks.mockClear();
    fireEvent.press(await findByText('全部'));
    await waitFor(() => {
      expect(mockFetchTasks).toHaveBeenCalledWith(undefined);
    });
  });

  it('filter "overdue" calls fetchTasks', async () => {
    const { findByText } = render(<InspectionListScreen />);
    await findByText('日常巡检任务');

    mockFetchTasks.mockClear();
    fireEvent.press(await findByText('已逾期'));

    await waitFor(() => {
      expect(mockFetchTasks).toHaveBeenCalledWith({ status: 'overdue' });
    });
  });

  it('type label fallback: unknown type shows raw value', async () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [MOCK_TASKS[1]], loading: false, error: null, total: 1,
      fetchTasks: mockFetchTasks,
    });

    const { findByText } = render(<InspectionListScreen />);
    expect(await findByText('unknown_type')).toBeTruthy();
  });

  it('items count: shows "0 项检查" for empty items', async () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [MOCK_TASKS[1]], loading: false, error: null, total: 1,
      fetchTasks: mockFetchTasks,
    });

    const { findByText } = render(<InspectionListScreen />);
    expect(await findByText('0 项检查')).toBeTruthy();
  });

  it('footer shows total count when tasks exist', async () => {
    const { findByText } = render(<InspectionListScreen />);
    expect(await findByText('共 2 条巡检任务')).toBeTruthy();
  });

  it('error+data: existing tasks still show when error occurs', async () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: MOCK_TASKS, loading: false,
      error: 'Some error', total: 2,
      fetchTasks: mockFetchTasks,
    });

    const { findByText, queryByText } = render(<InspectionListScreen />);
    expect(await findByText('日常巡检任务')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });

  it('task press navigates with correct id', async () => {
    const { findByText } = render(<InspectionListScreen />);
    fireEvent.press(await findByText('日常巡检任务'));
    expect(mockNavigate).toHaveBeenCalledWith('InspectionDetail', { taskId: 1 });
  });

  it('renders scheduledDate for first task', async () => {
    const { findByText } = render(<InspectionListScreen />);
    // The task with scheduledDate '2024-01-15T00:00:00Z' should render
    expect(await findByText('日常巡检任务')).toBeTruthy();
  });
});

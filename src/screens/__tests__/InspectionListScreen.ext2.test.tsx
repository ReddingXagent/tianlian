/**
 * InspectionListScreen ext2 — lines 122,133: ListFooter + filter variants
 */
import { render } from '@testing-library/react-native';
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
    id: 2, stationId: 2, stationName: '充电站B', deviceId: 2, deviceName: '充电桩02',
    type: 'monthly', status: 'completed', scheduledDate: '2024-01-10T00:00:00Z',
    description: '月度巡检', items: [],
    createdAt: '', updatedAt: '',
  },
];

describe('InspectionListScreen.ext2', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTasks.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: MOCK_TASKS, loading: false, error: null, total: 2,
      fetchTasks: mockFetchTasks,
    });
  });

  // Line 133: ListFooter when tasks.length > 0
  it('renders footer with total count when tasks exist', () => {
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('共 2 条巡检任务')).toBeTruthy();
  });

  // ListFooter null when tasks.length === 0
  it('does not render footer when no tasks', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [], loading: false, error: null, total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { queryByText } = render(<InspectionListScreen />);
    expect(queryByText(/共 \d+ 条巡检任务/)).toBeNull();
  });

  // renders filter buttons
  it('renders filter buttons', () => {
    const { getByText, getAllByText } = render(<InspectionListScreen />);
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('待巡检')).toBeTruthy();
    // '已完成' may appear in both filter and StatusBadge, use getAllByText
    expect(getAllByText('已完成').length).toBeGreaterThanOrEqual(1);
    expect(getByText('已逾期')).toBeTruthy();
  });

  // task items render
  it('renders task items', () => {
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('日常巡检任务')).toBeTruthy();
    expect(getByText('月度巡检')).toBeTruthy();
  });

  // error with tasks (error+data coexist) → FlatList
  it('renders FlatList when error exists but tasks are present', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: MOCK_TASKS, loading: false, error: 'Some error', total: 2,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('日常巡检任务')).toBeTruthy();
  });

  // empty state when no tasks and no error
  it('renders empty state when no tasks and no error', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [], loading: false, error: null, total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('暂无巡检任务')).toBeTruthy();
  });

  // loading state when loading and no tasks
  it('renders loading spinner when loading and no tasks', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [], loading: true, error: null, total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('加载巡检任务...')).toBeTruthy();
  });

  // type label fallback for unknown type
  it('renders unknown type label as raw type', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [{ id: 3, stationId: 1, stationName: '站', deviceId: 1, deviceName: '桩',
        type: 'custom_type', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
        description: '自定义任务', items: [], createdAt: '', updatedAt: '' }],
      loading: false, error: null, total: 1,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('custom_type')).toBeTruthy();
  });

  // items null/undefined → 0 items
  it('renders 0 items count when items is null', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [{ id: 4, stationId: 1, stationName: '站', deviceId: 1, deviceName: '桩',
        type: 'daily', status: 'pending', scheduledDate: '2024-01-15T00:00:00Z',
        description: '无检查项任务', items: null, createdAt: '', updatedAt: '' }],
      loading: false, error: null, total: 1,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('0 项检查')).toBeTruthy();
  });
});

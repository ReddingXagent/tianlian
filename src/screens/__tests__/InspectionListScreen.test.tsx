import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
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
    id: 1,
    stationId: 1,
    stationName: '充电站A',
    deviceId: 1,
    deviceName: '充电桩01',
    type: 'daily',
    status: 'pending',
    scheduledDate: '2024-01-15T00:00:00Z',
    description: '日常巡检任务一',
    items: [{ id: 1, name: '检查项', expected: '正常' }],
    createdAt: '',
    updatedAt: '',
  },
  {
    id: 2,
    stationId: 1,
    stationName: '充电站B',
    deviceId: 2,
    deviceName: '逆变器02',
    type: 'monthly',
    status: 'in_progress',
    scheduledDate: '2024-01-14T00:00:00Z',
    description: '月度巡检任务二',
    items: [],
    createdAt: '',
    updatedAt: '',
  },
];

describe('InspectionListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTasks.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: MOCK_TASKS,
      loading: false,
      error: null,
      total: 2,
      fetchTasks: mockFetchTasks,
    });
  });

  it('shows loading spinner initially', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [],
      loading: true,
      error: null,
      total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('加载巡检任务...')).toBeTruthy();
  });

  it('renders task list after loading', () => {
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('日常巡检任务一')).toBeTruthy();
    expect(getByText('月度巡检任务二')).toBeTruthy();
    expect(getByText('共 2 条巡检任务')).toBeTruthy();
  });

  it('renders status filter chips', () => {
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('待巡检')).toBeTruthy();
    expect(getByText('已逾期')).toBeTruthy();
  });

  it('navigates to detail when a task is pressed', () => {
    const { getByText } = render(<InspectionListScreen />);
    fireEvent.press(getByText('日常巡检任务一'));
    expect(mockNavigate).toHaveBeenCalledWith('InspectionDetail', { taskId: 1 });
  });

  it('shows empty state when no tasks', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [],
      loading: false,
      error: null,
      total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('暂无巡检任务')).toBeTruthy();
  });

  it('shows error state when load fails', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue({
      tasks: [],
      loading: false,
      error: '获取巡检任务失败',
      total: 0,
      fetchTasks: mockFetchTasks,
    });
    const { getByText } = render(<InspectionListScreen />);
    expect(getByText('加载失败')).toBeTruthy();
  });
});

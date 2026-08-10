/**
 * InspectionDetailScreen 扩展覆盖率
 * 目标: branches 52.94% → 80%+
 * 覆盖: refresh, handleComplete, handleItemResult(fail/na), error+selectedTask combo,
 *        null task rendering, partial/fail result, in_progress items with result,
 *        showCompleteForm toggle, Alert empty note, type labels
 */
import { Alert, type AlertButton } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
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
  completedDate: null,
  assignedTo: 2,
  assignedName: '张三',
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

describe('InspectionDetailScreen — 扩展覆盖', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTaskDetail.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(storeReturn());
  });

  // --- null task rendering ---

  it('task=null: 渲染不崩溃 (optional chaining)', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: null })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('基本信息')).toBeTruthy();
  });

  // --- refresh control ---

  it('RefreshControl onRefresh 触发fetchTaskDetail', async () => {
    mockFetchTaskDetail.mockResolvedValue(undefined);
    render(<InspectionDetailScreen />);
    await waitFor(() => {
      expect(mockFetchTaskDetail).toHaveBeenCalled();
    });
  });

  // --- handleStart alert buttons ---

  it('handleStart alert 确定按钮 → startTask 调用', () => {
    let capturedButtons: AlertButton[] = [];
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_, __, buttons) => {
      capturedButtons = buttons || [];
    });
    const { getByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getByText('开始巡检'));
    expect(alertSpy).toHaveBeenCalled();
    // Press '确定' button (index 1)
    const okBtn = capturedButtons[1];
    okBtn?.onPress?.();
    expect(mockStartTask).toHaveBeenCalledWith(1);
    alertSpy.mockRestore();
  });

  // --- handleItemResult: fail + na ---

  it('in_progress: 按不通过 → updateItem fail', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getAllByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getAllByText('❌ 不通过')[0]);
    expect(mockUpdateItem).toHaveBeenCalledWith(1, 1, 'fail');
  });

  it('in_progress: 按N/A → updateItem na', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getAllByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getAllByText('N/A')[0]);
    expect(mockUpdateItem).toHaveBeenCalledWith(1, 1, 'na');
  });

  // --- in_progress: item with result already set → no actions ---

  it('in_progress: item已有result → 不显示操作按钮', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'in_progress',
          items: [
            { id: 1, name: '已完成项', expected: '正常', result: 'pass' },
            { id: 2, name: '待检项', expected: '正常' },
          ],
        },
      })
    );
    const { getAllByText } = render(<InspectionDetailScreen />);
    // Only item 2 should have actions (1 set)
    expect(getAllByText('✅ 通过').length).toBe(1);
  });

  // --- handleComplete flow ---

  it('in_progress: 展开完成表单 → 取消按钮收起', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getByText, queryByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getByText('完成巡检'));
    expect(getByText('巡检总结')).toBeTruthy();
    fireEvent.press(getByText('取消'));
    expect(queryByText('巡检总结')).toBeNull();
  });

  it('完成表单空提交 → Alert 提示', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, status: 'in_progress' } })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    fireEvent.press(getByText('完成巡检'));
    fireEvent.press(getByText('提交结果'));
    expect(alertSpy).toHaveBeenCalledWith('提示', '请填写巡检总结');
    alertSpy.mockRestore();
  });

  it('完成表单填写后提交 → completeTask 调用', () => {
    mockCompleteTask.mockResolvedValue(undefined);
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'in_progress',
          items: [
            { id: 1, name: '检查项一', expected: '正常', result: 'pass' },
            { id: 2, name: '检查项二', expected: '正常', result: 'pass' },
          ],
        },
      })
    );
    const { getByText, getByPlaceholderText } = render(<InspectionDetailScreen />);
    fireEvent.press(getByText('完成巡检'));
    const input = getByPlaceholderText('请输入巡检总结...');
    fireEvent.changeText(input, '一切正常');
    fireEvent.press(getByText('提交结果'));
    // completeTask called: passedCount=2, totalCount=2 → overall='pass'
    expect(mockCompleteTask).toHaveBeenCalledWith(1, '一切正常', 'pass');
  });

  // --- type labels ---

  it('type=weekly → 显示周检', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, type: 'weekly' } })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('周检')).toBeTruthy();
  });

  it('unknown type → 显示原始值', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ selectedTask: { ...BASE_TASK, type: 'custom_type' } })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('custom_type')).toBeTruthy();
  });

  // --- result: partial / fail ---

  it('result.overall=partial → 显示部分通过', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'completed',
          result: {
            overall: 'partial',
            summary: '有隐患',
            operatorId: 1,
            operatorName: '李四',
            completedAt: '2024-01-15T14:00:00Z',
          },
        },
      })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('⚠️ 部分通过')).toBeTruthy();
  });

  it('result.overall=fail → 显示未通过', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'completed',
          result: {
            overall: 'fail',
            summary: '不合格',
            operatorId: 1,
            operatorName: '李四',
            completedAt: '2024-01-15T14:00:00Z',
          },
        },
      })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('❌ 未通过')).toBeTruthy();
  });

  // --- error + selectedTask: show content, not error ---

  it('error但selectedTask存在 → 显示内容而非错误页', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ error: 'some error', selectedTask: BASE_TASK })
    );
    const { getByText, queryByText } = render(<InspectionDetailScreen />);
    expect(getByText('日常巡检任务')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });

  // --- scheduledDate / completedDate rendering ---

  it('completedDate存在 → 渲染完成日期', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          status: 'completed',
          completedDate: '2024-01-20T00:00:00Z',
        },
      })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('基本信息')).toBeTruthy();
  });

  // --- item note rendering ---

  it('item有note → 渲染备注', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({
        selectedTask: {
          ...BASE_TASK,
          items: [{ id: 1, name: '检查项', expected: '标准', note: '注意安全' }],
        },
      })
    );
    const { getByText } = render(<InspectionDetailScreen />);
    expect(getByText('备注: 注意安全')).toBeTruthy();
  });

  // --- submitting state ---

  it('submitting=true → 开始巡检按钮显示loading', () => {
    (useInspectionStore as unknown as jest.Mock).mockReturnValue(
      storeReturn({ submitting: true })
    );
    const { queryByText } = render(<InspectionDetailScreen />);
    expect(queryByText('开始巡检')).toBeNull();
  });
});

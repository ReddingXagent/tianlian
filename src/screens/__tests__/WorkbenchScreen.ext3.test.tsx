/**
 * WorkbenchScreen 扩展测试3 — fn8(L123)覆盖
 * 目标: 待处理工单统计卡片onPress → handleNavigateTab('WorkOrders')
 * 实勘: coverage-final.json fn id8 anonymous L123 count=0,
 *       唯一未覆盖函数(funcs 13/14=92.85%), 双入口均未触发该卡片点击
 */
import { render, fireEvent } from '@testing-library/react-native';
import WorkbenchScreen from '../WorkbenchScreen';
import { usePolling } from '../../hooks/usePolling';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../hooks/usePolling', () => ({
  usePolling: jest.fn(),
}));

jest.mock('../../services/api', () => ({
  workbenchApi: {
    getStats: jest.fn(),
    getPendingOrders: jest.fn(),
    getRecentAlarms: jest.fn(),
  },
}));

const STATS = {
  pendingOrders: 3,
  inProgressOrders: 2,
  todayCompleted: 5,
  unhandledAlarms: 4,
  criticalAlarms: 1,
};

describe('WorkbenchScreen.ext3', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (usePolling as unknown as jest.Mock).mockReturnValue({
      data: { stats: STATS, pendingOrders: [], recentAlarms: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
      tickCount: 1,
    });
  });

  it('navigates to WorkOrders tab when 待处理工单 stat card pressed', () => {
    const { getByText } = render(<WorkbenchScreen />);
    // fail-fast: 卡片标签必须存在, 不存在即红(F1206教训)
    const card = getByText('待处理工单');
    fireEvent.press(card);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('Main', { screen: 'WorkOrders' });
  });
});

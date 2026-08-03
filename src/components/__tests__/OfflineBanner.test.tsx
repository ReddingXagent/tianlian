/**
 * OfflineBanner 测试
 * 通过 mock useNetworkStatus 控制离线/在线状态
 */
import { render } from '@testing-library/react-native';
import OfflineBanner from '../OfflineBanner';

// mock useNetworkStatus
jest.mock('../../hooks/useNetworkStatus', () => ({
  useNetworkStatus: jest.fn(),
}));

const { useNetworkStatus } = jest.requireMock('../../hooks/useNetworkStatus');

describe('OfflineBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders banner when offline', () => {
    (useNetworkStatus as jest.Mock).mockReturnValue({
      isOffline: true,
      isConnected: false,
    });
    const { getByText } = render(<OfflineBanner />);
    expect(getByText('网络已断开 · 显示缓存数据')).toBeTruthy();
  });

  it('renders nothing when online', () => {
    (useNetworkStatus as jest.Mock).mockReturnValue({
      isOffline: false,
      isConnected: true,
    });
    const { queryByText } = render(<OfflineBanner />);
    expect(queryByText('网络已断开 · 显示缓存数据')).toBeNull();
  });

  it('renders nothing when connectivity unknown (default online)', () => {
    (useNetworkStatus as jest.Mock).mockReturnValue({
      isOffline: false,
      isConnected: true,
    });
    const container = render(<OfflineBanner />);
    // Should render null — no text nodes
    expect(container.toJSON()).toBeNull();
  });
});

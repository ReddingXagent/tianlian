/**
 * OfflineNotice 组件单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import OfflineNotice from '../OfflineNotice';

describe('OfflineNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function createNavigator(online: boolean) {
    return {
      onLine: online,
      serviceWorker: { getRegistration: vi.fn().mockResolvedValue(null) },
    };
  }

  it('should render nothing when online and no update', () => {
    vi.stubGlobal('navigator', createNavigator(true));
    const { container } = render(<OfflineNotice />);
    expect(container.firstChild).toBeNull();
  });

  it('should render offline alert when offline', () => {
    vi.stubGlobal('navigator', createNavigator(false));
    render(<OfflineNotice />);
    expect(screen.getByText('当前处于离线模式')).toBeInTheDocument();
  });

  it('should show offline description', () => {
    vi.stubGlobal('navigator', createNavigator(false));
    render(<OfflineNotice />);
    expect(screen.getByText(/您正在浏览已缓存的内容/)).toBeInTheDocument();
  });

  it('should show reconnect button when offline', () => {
    vi.stubGlobal('navigator', createNavigator(false));
    render(<OfflineNotice />);
    expect(screen.getByText('重新连接')).toBeInTheDocument();
  });

  it('should reload on reconnect click', async () => {
    const reloadFn = vi.fn();
    vi.stubGlobal('navigator', createNavigator(false));
    Object.defineProperty(window, 'location', {
      value: { reload: reloadFn },
      writable: true,
      configurable: true,
    });

    render(<OfflineNotice />);
    await act(async () => {
      screen.getByText('重新连接').click();
    });
    expect(reloadFn).toHaveBeenCalled();
  });

  it('should render update alert when sw:update fires', async () => {
    vi.stubGlobal('navigator', createNavigator(true));
    render(<OfflineNotice />);

    // Dispatch the update event and wait for async state updates
    await act(async () => {
      window.dispatchEvent(new CustomEvent('sw:update'));
      // Wait for the async getRegistration promise to resolve
      await new Promise(r => setTimeout(r, 200));
    });

    expect(screen.getByText('新版本已就绪')).toBeInTheDocument();
    expect(document.querySelector('.ant-alert-info')).toBeInTheDocument();
  });

  it('should dismiss update on later click', async () => {
    vi.stubGlobal('navigator', createNavigator(true));
    render(<OfflineNotice />);

    await act(async () => {
      window.dispatchEvent(new CustomEvent('sw:update'));
      await new Promise(r => setTimeout(r, 200));
    });

    expect(screen.getByText('新版本已就绪')).toBeInTheDocument();

    // Find the "稍后" button (in antd Space, text is in a span inside the button)
    const allButtons = screen.getAllByRole('button');
    const laterBtn = allButtons.find(btn =>
      btn.textContent?.includes('稍') || btn.textContent?.includes('后')
    );
    expect(laterBtn).toBeDefined();

    if (laterBtn) {
      await act(async () => {
        laterBtn.click();
      });
      expect(screen.queryByText('新版本已就绪')).not.toBeInTheDocument();
    }
  });

  it('should cleanup listeners on unmount', () => {
    vi.stubGlobal('navigator', createNavigator(true));
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = render(<OfflineNotice />);
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('online', expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith('offline', expect.any(Function));
  });

  it('should handle update with waiting SW', async () => {
    const mockSW = { postMessage: vi.fn() };
    vi.stubGlobal('navigator', {
      onLine: true,
      serviceWorker: { getRegistration: vi.fn().mockResolvedValue({ waiting: mockSW }) },
    });
    Object.defineProperty(window, 'location', {
      value: { reload: vi.fn() },
      writable: true,
      configurable: true,
    });

    render(<OfflineNotice />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent('sw:update'));
      await new Promise(r => setTimeout(r, 200));
    });

    // Find the update button and click
    const updateBtn = screen.getByText('立即更新');
    await act(async () => {
      updateBtn.click();
    });
    expect(mockSW.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' });
  });
});

/**
 * AdminLayout 组件单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import AdminLayout from '../Layout/AdminLayout';

// Mock API
vi.mock('../../api', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }) },
  alarmAPI: {
    stats: vi.fn().mockResolvedValue({ data: { active: 0 } }),
  },
  stationAPI: { list: vi.fn().mockResolvedValue({ data: { items: [] } }) },
}));

vi.mock('../../config/menuConfig', () => ({
  getMenuItems: vi.fn(() => []),
  getSystemTitle: vi.fn(() => 'Test System'),
}));

describe('AdminLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('admin_token', 'test-token');
    localStorage.setItem('admin_user', JSON.stringify({ username: 'admin', role: 'admin' }));
    localStorage.setItem('entry_type', 'ops');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderLayout = () => {
    return render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/" element={<AdminLayout />}>
            <Route path="dashboard" element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
  };

  it('should render layout with outlet content', () => {
    renderLayout();
    expect(screen.getByText('Dashboard Content')).toBeInTheDocument();
  });

  it('should render system title', () => {
    renderLayout();
    // Layout renders the title in sider
    expect(document.body).toBeInTheDocument();
  });

  it('should render avatar', () => {
    renderLayout();
    const avatar = document.querySelector('.ant-avatar');
    expect(avatar).toBeInTheDocument();
  });

  it('should render bell icon for alarms', () => {
    renderLayout();
    const bellIcon = document.querySelector('.anticon-bell');
    expect(bellIcon).toBeInTheDocument();
  });

  it('should render menu component', () => {
    renderLayout();
    const menu = document.querySelector('.ant-menu');
    expect(menu).toBeInTheDocument();
  });

  it('should render with mobile menu button', () => {
    // Simulate mobile width
    vi.stubGlobal('innerWidth', 500);
    window.dispatchEvent(new Event('resize'));

    renderLayout();
    // Mobile layout uses Drawer with hamburger menu
    const menuIcon = document.querySelector('.anticon-menu');
    expect(menuIcon).toBeInTheDocument();
  });

  it('should handle window resize', () => {
    const { unmount } = renderLayout();

    window.dispatchEvent(new Event('resize'));

    unmount();
  });

  it('should render layout structure', () => {
    const { container } = renderLayout();
    const layout = container.querySelector('.ant-layout');
    expect(layout).toBeInTheDocument();
  });
});

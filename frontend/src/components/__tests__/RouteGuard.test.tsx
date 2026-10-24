/**
 * RouteGuard 组件单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import RouteGuard from '../RouteGuard';

describe('RouteGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const createRoutes = (guardedPath: string, children: React.ReactNode) => {
    return (
      <Routes>
        <Route path={guardedPath} element={<RouteGuard>{children}</RouteGuard>} />
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        <Route path="/gateway" element={<div>Gateway Page</div>} />
        <Route path="/protected" element={<div>Default Protected</div>} />
        <Route path="*" element={<div>Fallback</div>} />
      </Routes>
    );
  };

  it('should render children on login page without token', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        {createRoutes('/login', <div>Login Form</div>)}
      </MemoryRouter>
    );
    expect(screen.getByText('Login Form')).toBeInTheDocument();
  });

  it('should render children on scan page without token', () => {
    render(
      <MemoryRouter initialEntries={['/scan']}>
        <Routes>
          <Route path="/scan" element={<RouteGuard><div>Scan Page</div></RouteGuard>} />
          <Route path="*" element={<div>Fallback</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('Scan Page')).toBeInTheDocument();
  });

  it('should redirect to login when not authenticated on protected route', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        {createRoutes('/dashboard', <div>Protected Content</div>)}
      </MemoryRouter>
    );
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  it('should render children when authenticated with ops entry', () => {
    localStorage.setItem('admin_token', 'valid-token');
    localStorage.setItem('admin_user', JSON.stringify({ username: 'admin', role: 'admin' }));
    localStorage.setItem('user_type', 'engineer');

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        {createRoutes('/dashboard', <div>Protected Content</div>)}
      </MemoryRouter>
    );
    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });

  it('should render when no requiredEntryType specified', () => {
    localStorage.setItem('admin_token', 'valid-token');
    localStorage.setItem('admin_user', JSON.stringify({ username: 'admin', role: 'admin' }));
    localStorage.setItem('user_type', 'admin');

    render(
      <MemoryRouter initialEntries={['/protected']}>
        {createRoutes('/protected', <div>Generic Content</div>)}
      </MemoryRouter>
    );
    expect(screen.getByText('Generic Content')).toBeInTheDocument();
  });
});

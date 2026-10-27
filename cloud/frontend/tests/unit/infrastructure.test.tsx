/**
 * 天链V3 - 示例单元测试
 *
 * 验证测试基础设施是否正常工作
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, mockAuthStorage, clearAuthStorage, createMockProps } from '../utils/test-utils';
import { mockUsers, mockStations, mockAPIResponses, createMockData } from '../fixtures/test-data';

// ============ 测试基础设施验证 ============
describe('测试基础设施验证', () => {
  beforeEach(() => {
    clearAuthStorage();
  });

  it('Vitest 应正常运行', () => {
    expect(true).toBe(true);
    expect(1 + 1).toBe(2);
  });

  it('jest-dom 扩展应可用', () => {
    const div = document.createElement('div');
    div.textContent = 'Hello Vitest';
    document.body.appendChild(div);
    
    expect(div).toBeInTheDocument();
    expect(div).toHaveTextContent('Hello Vitest');
  });

  it('localStorage Mock 应正常工作', () => {
    localStorage.setItem('test_key', 'test_value');
    expect(localStorage.getItem('test_key')).toBe('test_value');
    expect(localStorage.setItem).toHaveBeenCalled();
  });

  it('vi.fn Mock 应正常工作', () => {
    const mockFn = vi.fn();
    mockFn('hello');
    
    expect(mockFn).toHaveBeenCalled();
    expect(mockFn).toHaveBeenCalledWith('hello');
  });

  it('renderWithProviders 应正常渲染', () => {
    const TestComponent = () => <div data-testid="test">Test Component</div>;
    const { getByTestId } = renderWithProviders(<TestComponent />);
    
    expect(getByTestId('test')).toBeInTheDocument();
  });
});

// ============ 测试工具函数验证 ============
describe('测试工具函数', () => {
  it('mockAuthStorage 应正常设置 auth storage', () => {
    const { token, user } = mockAuthStorage();
    
    expect(localStorage.getItem('admin_token')).toBe(token);
    expect(localStorage.getItem('admin_user')).toBe(JSON.stringify(user));
  });

  it('createMockProps 应正确合并 props', () => {
    const defaults = { name: 'default', age: 20 };
    const overrides = { age: 25 };
    
    const result = createMockProps(defaults, overrides);
    
    expect(result.name).toBe('default');
    expect(result.age).toBe(25);
  });

  it('createMockData 应正确创建 Mock 数据', () => {
    const template = { name: 'test', value: 1 };
    const overrides = { value: 2 };
    
    const result = createMockData(template, overrides);
    
    expect(result.name).toBe('test');
    expect(result.value).toBe(2);
  });
});

// ============ 测试数据验证 ============
describe('测试数据 Fixtures', () => {
  it('mockUsers 应包含正确的用户数据', () => {
    expect(mockUsers.length).toBe(3);
    expect(mockUsers[0].username).toBe('admin');
    expect(mockUsers[0].role).toBe('admin');
  });

  it('mockStations 应包含正确的站点数据', () => {
    expect(mockStations.length).toBe(3);
    expect(mockStations[0].name).toBe('站点A');
    expect(mockStations[0].status).toBe('active');
  });

  it('mockAPIResponses 应包含正确的响应结构', () => {
    expect(mockAPIResponses.loginSuccess).toHaveProperty('token');
    expect(mockAPIResponses.loginSuccess).toHaveProperty('user');
    
    expect(mockAPIResponses.stationsList).toHaveProperty('data');
    expect(mockAPIResponses.stationsList).toHaveProperty('total');
  });

  it('Dashboard stats 应包含正确的统计数据', () => {
    const stats = mockAPIResponses.dashboardStats;
    
    expect(stats.stationCount).toBe(3);
    expect(stats.deviceCount).toBe(15);
    expect(stats).toHaveProperty('alarmCount');
  });
});
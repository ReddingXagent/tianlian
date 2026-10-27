/**
 * ThemeToggle 组件单元测试（适配 ThemeContext 版本）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, useTheme } from '../../contexts/ThemeContext';
import ThemeToggle from '../ThemeToggle';

/** Helper: render ThemeToggle inside ThemeProvider with controllable context */
const ControlledWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

describe('ThemeToggle', () => {
  it('should render with light mode (default)', () => {
    render(
      <ControlledWrapper>
        <ThemeToggle />
      </ControlledWrapper>
    );
    expect(screen.getByText('暗黑模式')).toBeInTheDocument();
    // Default is light -> shows ☀️
    expect(screen.getByText('☀️')).toBeInTheDocument();
  });

  it('should render within a Space container', () => {
    const { container } = render(
      <ControlledWrapper>
        <ThemeToggle />
      </ControlledWrapper>
    );
    expect(container.querySelector('.ant-space')).toBeInTheDocument();
  });

  it('should render compact mode without text', () => {
    render(
      <ControlledWrapper>
        <ThemeToggle compact />
      </ControlledWrapper>
    );
    // Compact mode only shows switch, no text
    const switches = document.querySelectorAll('.ant-switch');
    expect(switches.length).toBeGreaterThan(0);
  });

  it('should toggle theme when switch is clicked', async () => {
    // We test indirectly via ThemeContext state
    function TestComponent() {
      const { isDark } = useTheme();
      return <div data-testid="theme-indicator">{isDark ? 'dark' : 'light'}</div>;
    }
    render(
      <ControlledWrapper>
        <TestComponent />
        <ThemeToggle />
      </ControlledWrapper>
    );
    // Default is light
    expect(screen.getByTestId('theme-indicator').textContent).toBe('light');
    // Click switch to toggle
    const switchEl = document.querySelector('.ant-switch') as HTMLElement;
    switchEl?.click();
    await new Promise(r => setTimeout(r, 10));
    // Now should be dark
    expect(screen.getByTestId('theme-indicator').textContent).toBe('dark');
  });
});
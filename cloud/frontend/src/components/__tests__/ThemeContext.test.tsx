import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider, useTheme } from '../../contexts/ThemeContext';

const TestConsumer = () => {
  const { isDark, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme-state">{isDark ? 'dark' : 'light'}</span>
      <button data-testid="toggle-btn" onClick={toggleTheme}>Toggle</button>
    </div>
  );
};

describe('ThemeContext', () => {
  it('defaults to light mode', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );
    expect(screen.getByTestId('theme-state').textContent).toBe('light');
  });

  it('toggles between light and dark', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByTestId('toggle-btn'));
    expect(screen.getByTestId('theme-state').textContent).toBe('dark');
    fireEvent.click(screen.getByTestId('toggle-btn'));
    expect(screen.getByTestId('theme-state').textContent).toBe('light');
  });

  it('persists theme preference to localStorage', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByTestId('toggle-btn'));
    expect(localStorage.getItem('tianlian-theme-mode')).toBe('dark');
  });
});

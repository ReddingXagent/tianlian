/**
 * Chart 组件单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Charts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('BarChart', () => {
    it('should export BarChart component', async () => {
      const { BarChart } = await import('../Charts');
      expect(BarChart).toBeDefined();
    });
  });

  describe('LineChart', () => {
    it('should export LineChart component', async () => {
      const { LineChart } = await import('../Charts');
      expect(LineChart).toBeDefined();
    });
  });

  describe('PieChart', () => {
    it('should export PieChart component', async () => {
      const { PieChart } = await import('../Charts');
      expect(PieChart).toBeDefined();
    });
  });

  describe('Charts index', () => {
    it('should export all chart components', async () => {
      const Charts = await import('../Charts');
      expect(Charts.BarChart).toBeDefined();
      expect(Charts.LineChart).toBeDefined();
      expect(Charts.PieChart).toBeDefined();
    });
  });
});

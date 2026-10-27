/**
 * 导出工具测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { exportCSV, exportJSON, printTable } from '../export';

vi.mock('antd', () => ({
  message: {
    warning: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { message } from 'antd';

describe('export utilities', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('exportCSV', () => {
    it('应生成正确的CSV内容并触发下载', () => {
      const data = [
        { id: 1, name: 'Test 1', value: 100 },
        { id: 2, name: 'Test 2', value: 200 },
      ];

      const link = { click: vi.fn(), href: '', download: '' };
      const createObjectURL = vi.fn().mockReturnValue('blob:url');
      const revokeObjectURL = vi.fn();
      const createElementSpy = vi.fn().mockReturnValue(link);

      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', { createElement: createElementSpy });

      exportCSV(data, 'test-export');

      expect(createElementSpy).toHaveBeenCalledWith('a');
      expect(link.download).toBe('test-export.csv');
      expect(link.click).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();

      vi.unstubAllGlobals();
    });

    it('空数据应提示警告', () => {
      vi.stubGlobal('document', { createElement: vi.fn() });

      exportCSV([], 'empty');

      expect(message.warning).toHaveBeenCalledWith('没有数据可导出');

      vi.unstubAllGlobals();
    });

    it('含逗号字符串应加引号', () => {
      const data = [{ name: 'Smith, John', city: 'New York' }];
      const link = { click: vi.fn(), href: '', download: '' };
      const createObjectURL = vi.fn().mockReturnValue('blob:url');
      const revokeObjectURL = vi.fn();

      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', { createElement: () => link });

      exportCSV(data, 'test');

      expect(createObjectURL).toHaveBeenCalled();

      vi.unstubAllGlobals();
    });
  });

  // ============ 公式注入中和 + RFC4180 (card 2aa90b7d) ============

  describe('公式注入中和', () => {
    function stubAndCapture() {
      const link = { click: vi.fn(), href: '', download: '' };
      const createObjectURL = vi.fn().mockReturnValue('blob:url');
      const revokeObjectURL = vi.fn();
      const RealBlob = globalThis.Blob;
      let captured = '';
      class BlobSpy {
        constructor(parts: BlobPart[]) {
          captured = parts.map(String).join('');
          return new RealBlob(parts) as unknown as BlobSpy;
        }
      }
      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', { createElement: () => link });
      vi.stubGlobal('Blob', BlobSpy);
      return { getBody: () => captured.replace(/^﻿/, '') };
    }

    it.each([
      ['=SUM(1,1)', "'\"=SUM(1,1)\""],
      ['+cmd|', "'+cmd|"],
      ['-1+1', "'-1+1"],
      ['@SUM', "'@SUM"],
      ['\t=1+1', "'\t=1+1"],
      ['\r=1+1', "'\"\r=1+1\""],
    ])('公式前缀 %j 被撇号中和', (cell, expectedRow) => {
      const s = stubAndCapture();
      exportCSV([{ v: cell }], 't');
      expect(s.getBody()).toBe(`v\n${expectedRow}`);
    });

    it('逗号+公式前缀组合: RFC4180 包裹后再补撇号', () => {
      const s = stubAndCapture();
      exportCSV([{ v: '=1,2' }], 't');
      expect(s.getBody()).toBe('v\n\'"=1,2"');
    });

    it('双引号转义为两个双引号并包裹(RFC 4180)', () => {
      const s = stubAndCapture();
      exportCSV([{ v: 'say "hi"' }], 't');
      expect(s.getBody()).toBe('v\n"say ""hi"""');
    });

    it('含逗号字段仍加引号包裹', () => {
      const s = stubAndCapture();
      exportCSV([{ v: 'Smith, John' }], 't');
      expect(s.getBody()).toBe('v\n"Smith, John"');
    });

    it('普通文本不受影响', () => {
      const s = stubAndCapture();
      exportCSV([{ a: 1, b: '普通' }], 't');
      expect(s.getBody()).toBe('a,b\n1,普通');
    });
  });

  describe('exportJSON', () => {
    it('应生成JSON文件并触发下载', () => {
      const data = { id: 1, name: 'test' };
      const link = { click: vi.fn(), href: '', download: '' };
      const createObjectURL = vi.fn().mockReturnValue('blob:url');
      const revokeObjectURL = vi.fn();

      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', { createElement: () => link });

      exportJSON(data, 'test-data');

      expect(link.download).toBe('test-data.json');
      expect(link.click).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();

      vi.unstubAllGlobals();
    });

    it('应正确格式化JSON输出', () => {
      const data = { nested: { key: 'value' }, arr: [1, 2, 3] };
      const link = { click: vi.fn(), href: '', download: '' };
      const createObjectURL = vi.fn().mockReturnValue('blob:url');
      const revokeObjectURL = vi.fn();

      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', { createElement: () => link });

      exportJSON(data, 'formatted');

      expect(createObjectURL).toHaveBeenCalled();

      vi.unstubAllGlobals();
    });
  });

  describe('printTable', () => {
    it('元素不存在应提示错误', () => {
      vi.stubGlobal('document', { getElementById: () => null });

      printTable('nonexistent');

      expect(message.error).toHaveBeenCalledWith('未找到打印内容');

      vi.unstubAllGlobals();
    });

    it('元素存在应打开打印窗口', () => {
      const printWindow = {
        document: {
          write: vi.fn(),
          close: vi.fn(),
        },
        print: vi.fn(),
      };
      const element = { innerHTML: '<table><tr><td>test</td></tr></table>' };

      vi.stubGlobal('document', { getElementById: () => element });
      vi.stubGlobal('window', { open: () => printWindow });

      printTable('my-table');

      expect(printWindow.document.write).toHaveBeenCalled();
      expect(printWindow.print).toHaveBeenCalled();

      vi.unstubAllGlobals();
    });
  });
});

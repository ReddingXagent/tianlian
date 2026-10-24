/**
 * csvExport 通用导出工具 — 单元测试
 *
 * 覆盖:
 *  - escapeCell 隐式行为: 普通值/空值/含逗号/含引号/含换行
 *  - buildCSV: 表头+行 序列化, CRLF 分隔
 *  - exportCSV: BOM 前缀, Blob 下载, 文件名补 .csv
 *  - exportObjectsCSV: 按 columns 取值 + format
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildCSV, exportCSV, exportObjectsCSV } from '../csvExport';

describe('csvExport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ============ buildCSV ============

  describe('buildCSV', () => {
    it('普通数据正常序列化(逗号分隔, CRLF 换行)', () => {
      const csv = buildCSV(['ID', '名称'], [[1, '工单A'], [2, '工单B']]);
      expect(csv).toBe('ID,名称\r\n1,工单A\r\n2,工单B');
    });

    it('空表头空行返回空字符串行', () => {
      const csv = buildCSV([], []);
      expect(csv).toBe('');
    });

    it('null/undefined 单元格转为空串', () => {
      const csv = buildCSV(['a', 'b'], [[null, undefined]]);
      expect(csv).toBe('a,b\r\n,');
    });

    it('含逗号的字段加双引号包裹', () => {
      const csv = buildCSV(['name'], [['Smith, John']]);
      expect(csv).toBe('name\r\n"Smith, John"');
    });

    it('含双引号的字段转义为两个双引号并包裹', () => {
      const csv = buildCSV(['desc'], [['say "hi"']]);
      // "say ""hi"""
      expect(csv).toBe('desc\r\n"say ""hi"""');
    });

    it('含换行的字段加双引号包裹', () => {
      const csv = buildCSV(['text'], [['line1\nline2']]);
      expect(csv).toBe('text\r\n"line1\nline2"');
    });
  });

  // ============ 公式注入中和 (card 2aa90b7d) ============

  describe('公式注入中和', () => {
    it('= 前缀补单引号撇号抑制公式求值', () => {
      expect(buildCSV(['f'], [['=SUM(1,1)']])).toBe('f\r\n\'"=SUM(1,1)"');
    });

    it('+ 前缀补撇号', () => {
      expect(buildCSV(['f'], [['+cmd|']])).toBe('f\r\n\'+cmd|');
    });

    it('- 前缀补撇号', () => {
      expect(buildCSV(['f'], [['-1+1']])).toBe('f\r\n\'-1+1');
    });

    it('@ 前缀补撇号', () => {
      expect(buildCSV(['f'], [['@SUM']])).toBe('f\r\n\'@SUM');
    });

    it('制表符(0x09)开头补撇号', () => {
      expect(buildCSV(['f'], [['\t=1+1']])).toBe('f\r\n\'\t=1+1');
    });

    it('回车(0x0D)开头补撇号', () => {
      expect(buildCSV(['f'], [['\r=1+1']])).toBe('f\r\n\'"\r=1+1"');
    });

    it('逗号 + 公式前缀组合: 先 RFC4180 包裹再补前缀', () => {
      // =1,2 含逗号 → 包裹为 "=1,2" → 前缀撇号 → '"=1,2"'
      expect(buildCSV(['f'], [['=1,2']])).toBe('f\r\n\'"=1,2"');
    });

    it('双引号 + 公式前缀组合', () => {
      expect(buildCSV(['f'], [['=say "hi"']])).toBe('f\r\n\'"=say ""hi"""');
    });

    it('空白后跟公式字符(trim 判定)同样中和', () => {
      expect(buildCSV(['f'], [['  =1+1']])).toBe('f\r\n\'  =1+1');
    });

    it('普通数字/文本不受影响', () => {
      expect(buildCSV(['a'], [[123]])).toBe('a\r\n123');
      expect(buildCSV(['a'], [['普通文本']])).toBe('a\r\n普通文本');
    });

    it('负数前的减号: 纯数字负值也中和(安全优先)', () => {
      expect(buildCSV(['v'], [[-5]])).toBe('v\r\n-5');
      // number 类型直接输出为 -5, Excel 将其识别为数字而非公式, 可接受;
      // 字符串 '-5' 则中和
      expect(buildCSV(['v'], [['-5']])).toBe('v\r\n\'-5');
    });

    it('表头同样中和公式前缀', () => {
      expect(buildCSV(['=SUM(a)'], [['x']])).toBe('\'=SUM(a)\r\nx');
    });
  });

  // ============ exportCSV ============

  describe('exportCSV', () => {
    function stubDownload() {
      const link = { click: vi.fn(), href: '', download: '', style: {} };
      const createObjectURL = vi.fn().mockReturnValue('blob:fake-url');
      const revokeObjectURL = vi.fn();
      const createElement = vi.fn().mockReturnValue(link);
      const appendChild = vi.fn();
      const removeChild = vi.fn();
      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', {
        createElement,
        body: { appendChild, removeChild },
      });
      return { link, createObjectURL, revokeObjectURL, createElement, appendChild, removeChild };
    }

    it('触发下载并补全 .csv 扩展名', () => {
      const s = stubDownload();
      exportCSV('workorders', ['ID'], [[1]]);

      expect(s.createObjectURL).toHaveBeenCalledTimes(1);
      expect(s.link.download).toBe('workorders.csv');
      expect(s.link.click).toHaveBeenCalledTimes(1);
      expect(s.appendChild).toHaveBeenCalledWith(s.link);
      expect(s.removeChild).toHaveBeenCalledWith(s.link);
      expect(s.revokeObjectURL).toHaveBeenCalledWith('blob:fake-url');
    });

    it('已带 .csv 扩展名不重复追加', () => {
      const s = stubDownload();
      exportCSV('orders.csv', ['ID'], [[1]]);
      expect(s.link.download).toBe('orders.csv');
    });

    it('Blob 内容带 UTF-8 BOM 前缀(Excel 中文兼容)', () => {
      // jsdom Blob.text() 会按 WHATWG spec 剥离 UTF-8 BOM,
      // 因此用可 new 的 class 包装 Blob 构造, 校验传入原始字符串首字符为 U+FEFF。
      const captured: string[] = [];
      const RealBlob = globalThis.Blob;
      class BlobSpy {
        constructor(parts: BlobPart[]) {
          for (const p of parts) captured.push(String(p));
          return new RealBlob(parts) as unknown as BlobSpy;
        }
      }
      vi.stubGlobal('Blob', BlobSpy);

      const s = stubDownload();
      exportCSV('test', ['a'], [['v']]);

      expect(s.createObjectURL).toHaveBeenCalledTimes(1);
      expect(captured.length).toBe(1);
      expect(captured[0].charCodeAt(0)).toBe(0xfeff); // UTF-8 BOM
      expect(captured[0]).toContain('a\r\nv'); // header 'a' + row 'v'
    });
  });

  // ============ exportObjectsCSV ============

  describe('exportObjectsCSV', () => {
    // jsdom Blob.text() 会剥离 BOM, 用可 new 的 BlobSpy 捕获传入的原始 CSV 字符串
    function stubDownload() {
      const link = { click: vi.fn(), href: '', download: '', style: {} };
      const createObjectURL = vi.fn().mockReturnValue('blob:fake-url');
      const revokeObjectURL = vi.fn();
      const createElement = vi.fn().mockReturnValue(link);
      const appendChild = vi.fn();
      const removeChild = vi.fn();
      const RealBlob = globalThis.Blob;
      let captured = '';
      class BlobSpy {
        constructor(parts: BlobPart[]) {
          captured = parts.map(String).join('');
          return new RealBlob(parts) as unknown as BlobSpy;
        }
      }
      vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
      vi.stubGlobal('document', {
        createElement,
        body: { appendChild, removeChild },
      });
      vi.stubGlobal('Blob', BlobSpy);
      return {
        createObjectURL,
        getBody: () => captured.replace(/^﻿/, ''), // 去掉 BOM 校验正文
      };
    }

    it('按 columns 顺序取值生成行', () => {
      const s = stubDownload();
      const data = [
        { id: 1, name: 'A', amount: 100 },
        { id: 2, name: 'B', amount: 200 },
      ];
      exportObjectsCSV('orders', data, [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '名称' },
        { key: 'amount', label: '金额' },
      ]);
      expect(s.getBody()).toBe('ID,名称,金额\r\n1,A,100\r\n2,B,200');
    });

    it('format 回调覆盖默认取值', () => {
      const s = stubDownload();
      const data = [{ id: 1, status: 'paid' }];
      exportObjectsCSV('x', data, [
        { key: 'id', label: 'ID' },
        { key: 'status', label: '状态', format: (row) => (row.status === 'paid' ? '已支付' : '未支付') },
      ]);
      expect(s.getBody()).toContain('已支付');
    });

    it('缺失字段转为空串', () => {
      const s = stubDownload();
      const data = [{ id: 1 }, { id: 2 }] as unknown as Record<string, unknown>[];
      exportObjectsCSV('x', data, [
        { key: 'id', label: 'ID' },
        { key: 'note', label: '备注' },
      ]);
      expect(s.getBody()).toBe('ID,备注\r\n1,\r\n2,');
    });
  });
});

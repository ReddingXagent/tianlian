/**
 * 通用 CSV 导出工具
 *
 * 特性:
 *  - UTF-8 BOM (﻿) 前缀, Excel 打开中文不乱码
 *  - CRLF 行分隔, Excel 兼容
 *  - 单元格含 逗号/双引号/换行 时自动用双引号包裹, 内部双引号转义为两个双引号 (RFC 4180)
 *  - 公式注入中和: 字符串值以 = + - @ 制表符(0x09) 回车(0x0D) 开头(或 trim 后首字符为公式字符)
 *    时前缀补单引号撇号('), 抑制 Excel/Calc 将其当作公式求值
 *  - 基于 Blob + 临时 <a> 触发浏览器下载
 */

/** 触发公式求值的危险首字符: = + - @ 制表符 回车 */
const FORMULA_PREFIX_RE = /^[=+\-@\t\r]/;

/**
 * 转义单个单元格为 CSV 安全字符串
 *
 * 先做 RFC 4180 包裹(逗号/双引号/换行), 再在包裹结果前补撇号中和公式前缀。
 */
export function escapeCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  let out = /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  if (typeof value === 'string' && (FORMULA_PREFIX_RE.test(s) || FORMULA_PREFIX_RE.test(s.trim()))) {
    out = `'${out}`;
  }
  return out;
}

/**
 * 构建 CSV 文本(不含 BOM)
 *
 * @param headers 表头
 * @param rows    数据行, 每行长度应与 headers 一致
 * @returns CSV 字符串, CRLF 分隔
 */
export function buildCSV(headers: string[], rows: (string | number)[][]): string {
  const line = (cells: (string | number)[]) => cells.map(escapeCell).join(',');
  return [line(headers), ...rows.map(line)].join('\r\n');
}

/**
 * 触发浏览器下载 CSV 文件
 *
 * @param filename 文件名(可不带 .csv 扩展名)
 * @param headers  表头
 * @param rows     数据行
 */
export function exportCSV(
  filename: string,
  headers: string[],
  rows: (string | number)[][],
): void {
  const csv = '﻿' + buildCSV(headers, rows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

export interface CSVColumn<T> {
  /** 取值键 */
  key: string;
  /** 表头显示名 */
  label: string;
  /** 可选自定义取值/格式化 */
  format?: (row: T) => string | number;
}

/**
 * 导出对象数组为 CSV
 *
 * @param filename 文件名
 * @param objects  数据数组
 * @param columns  列定义 (顺序即列顺序)
 */
export function exportObjectsCSV<T extends object>(
  filename: string,
  objects: T[],
  columns: CSVColumn<T>[],
): void {
  const headers = columns.map((c) => c.label);
  const rows = objects.map((obj) =>
    columns.map((c) => {
      if (c.format) return c.format(obj);
      // CSV 按字符串键动态取值，此处将具体行类型放宽为可索引类型
      const v = (obj as Record<string, unknown>)[c.key];
      return v === null || v === undefined ? '' : (v as string | number);
    }),
  );
  exportCSV(filename, headers, rows);
}

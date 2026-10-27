/**
 * 导出工具函数
 */
import { message } from 'antd';
import { escapeCell } from './csvExport';

/**
 * 导出 CSV 文件
 */
export const exportCSV = (data: any[], filename: string) => {
  try {
    if (!data.length) {
      message.warning('没有数据可导出');
      return;
    }

    const headers = Object.keys(data[0]);
    const csvContent = [
      headers.join(','),
      ...data.map(row =>
        headers.map(header => {
          const value = row[header];
          // RFC 4180 转义(逗号/双引号/换行) + 公式注入中和(= + - @ \t \r 前缀补撇号)
          return typeof value === 'string' ? escapeCell(value) : value;
        }).join(',')
      )
    ].join('\n');

    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    message.success('导出成功');
  } catch (error) {
    message.error('导出失败');
  }
};

/**
 * 导出 JSON 文件
 */
export const exportJSON = (data: any, filename: string) => {
  try {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    message.success('导出成功');
  } catch (error) {
    message.error('导出失败');
  }
};

/**
 * 打印表格
 */
export const printTable = (elementId: string) => {
  const printContent = document.getElementById(elementId);
  if (!printContent) {
    message.error('未找到打印内容');
    return;
  }

  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(`
      <html>
        <head>
          <title>打印</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
          </style>
        </head>
        <body>${printContent.innerHTML}</body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  }
};

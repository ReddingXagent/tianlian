/**
 * 浏览器端 blob 文件下载工具 (卡 922b2fba)
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** 按日期生成导出文件名：tianlian_platform_backup_20261008.json */
export function exportFilename(scope: string, mode: string): string {
  const d = new Date();
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  return `tianlian_${scope}_${mode}_${ymd}.json`;
}

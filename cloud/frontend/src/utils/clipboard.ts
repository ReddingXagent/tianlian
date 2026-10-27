/**
 * copyToClipboard - 跨上下文复制（2026-10-09 丁哥: HTTP 站点 navigator.clipboard 为 undefined, 复制点击无反应）
 * 优先 Clipboard API(HTTPS), 回退 execCommand(HTTP/旧浏览器)。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch { /* 回退 */ }
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

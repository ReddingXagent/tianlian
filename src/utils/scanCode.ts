/**
 * 扫码 payload 解析工具。
 *
 * 充电桩二维码 payload 常见形态:
 *  1. 裸编码: "CH-001"
 *  2. URL: "https://charge.tianlian.com/charger/CH-001"
 *  3. URL 带 query/hash: "https://x.com/charger/CH-001?from=qr"
 *
 * 解析优先级:
 *  ① payload 中任意位置命中「字母-数字」编码形态(如 CH-001) → 直接提取;
 *  ② URL → 取最后一个非空路径段(去 query/hash/尾斜杠);
 *  ③ 其余 → 原样返回(trim 后)。
 */

/** 字母-数字编码形态: 至少2字母 + '-' + 至少2位数字 */
const CODE_PATTERN = /[A-Za-z]{2,}-\d{2,}/;

export function parseScanPayload(payload: string): string | null {
  const data = payload.trim();
  if (!data) return null;

  // ① 编码形态优先(兼容 URL/自定义 scheme 包裹)
  const codeMatch = data.match(CODE_PATTERN);
  if (codeMatch) return codeMatch[0].toUpperCase();

  // ② URL: 取最后路径段
  // scheme正则已保证'//'前至少有"scheme:"非空段, 去尾斜杠后末段必非空, 无需空判
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(data)) {
    const path = data.split(/[?#]/)[0];
    const segments = path.replace(/\/+$/, '').split('/');
    const last = segments[segments.length - 1];
    try {
      return decodeURIComponent(last);
    } catch {
      return last;
    }
  }

  // ③ 原样返回
  return data;
}

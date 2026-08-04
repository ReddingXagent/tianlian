import {
  formatDate,
  formatDateTime,
  formatDistance,
  formatMoney,
  formatShortDateTime,
} from '../format';

/**
 * 日期格式单一源守卫(F241): locale 钉 zh-CN + 形态三档 + 无效输入兜底 '-'。
 * 构造日期一律用本地分量 new Date(y, m, d, h, min), 与运行环境 TZ 无关。
 */
const LOCAL_NOON = new Date(2026, 7, 4, 12, 30); // 2026-08-04 12:30 本地

describe('formatDateTime', () => {
  it('完整形态含年含时分(zh-CN)', () => {
    const text = formatDateTime(LOCAL_NOON);
    expect(text).toContain('2026');
    expect(text).toContain('8');
    expect(text).toContain('4');
    expect(text).toContain('12:30');
  });

  it('Date/ISO串/时间戳三形态等价', () => {
    const iso = LOCAL_NOON.toISOString();
    const ts = LOCAL_NOON.getTime();
    expect(formatDateTime(iso)).toBe(formatDateTime(LOCAL_NOON));
    expect(formatDateTime(ts)).toBe(formatDateTime(LOCAL_NOON));
  });
});

describe('formatShortDateTime', () => {
  it('列表紧凑形态: 无年, 月日时分两位补零', () => {
    expect(formatShortDateTime(LOCAL_NOON)).toBe('08/04 12:30');
  });
});

describe('formatDate', () => {
  it('zh-CN 形态(钉 locale, 防设备 locale 漂移回 MM/DD/YYYY)', () => {
    expect(formatDate(LOCAL_NOON)).toBe('2026/8/4');
  });
});

describe('无效输入兜底', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['空串', ''],
    ['垃圾串', 'not-a-date'],
  ])('%s → "-"', (_label, input) => {
    expect(formatDateTime(input as never)).toBe('-');
    expect(formatShortDateTime(input as never)).toBe('-');
    expect(formatDate(input as never)).toBe('-');
  });

  it('NaN 时间戳/无效 Date → "-"', () => {
    expect(formatDateTime(NaN)).toBe('-');
    expect(formatDateTime(new Date('invalid'))).toBe('-');
  });
});

describe('formatDistance(F253距离单一源)', () => {
  it('<1000 米原值直显', () => {
    expect(formatDistance(0)).toBe('0米');
    expect(formatDistance(500)).toBe('500米');
    expect(formatDistance(999)).toBe('999米');
  });

  it('>=1000 公里一位小数', () => {
    expect(formatDistance(1000)).toBe('1.0公里');
    expect(formatDistance(1500)).toBe('1.5公里');
    expect(formatDistance(2500)).toBe('2.5公里');
    expect(formatDistance(9999)).toBe('10.0公里');
  });

  it('边界1000精确切换单位', () => {
    expect(formatDistance(999.9)).toBe('999.9米');
    expect(formatDistance(1000.4)).toBe('1.0公里');
  });
});

describe('formatMoney(F259金额单一源)', () => {
  it('整数补两位小数', () => {
    expect(formatMoney(10)).toBe('10.00');
    expect(formatMoney(0)).toBe('0.00');
  });
  it('小数四舍五入到两位', () => {
    expect(formatMoney(1.005)).toBe('1.00'); // IEEE754: 1.005实际为1.00499...
    expect(formatMoney(2.346)).toBe('2.35');
    expect(formatMoney(0.1 + 0.2)).toBe('0.30');
  });
  it('符号由调用侧处理, 函数只格式化数值', () => {
    expect(formatMoney(-5)).toBe('-5.00');
  });
});

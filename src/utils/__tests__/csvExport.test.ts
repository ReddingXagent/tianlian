import {
  buildRevenueCsv,
  revenueCsvFilename,
  escapeCsv,
  RevenuePeriod,
} from '../csvExport';
import { RevenueRecord, RevenueSummary } from '../../types';

const SUMMARY: RevenueSummary = { today: 100, week: 700, month: 3000, total: 50000 };

const RECORDS: RevenueRecord[] = [
  { date: '2024-01-01', amount: 123.456, orderCount: 10 },
  { date: '2024-01-02', amount: 200, orderCount: 15 },
];

describe('escapeCsv', () => {
  it('should pass through plain numbers and simple strings', () => {
    expect(escapeCsv(123)).toBe('123');
    expect(escapeCsv('2024-01-01')).toBe('2024-01-01');
  });

  it('should wrap fields containing commas in quotes', () => {
    expect(escapeCsv('a,b')).toBe('"a,b"');
  });

  it('should escape double quotes by doubling them', () => {
    expect(escapeCsv('a"b')).toBe('"a""b"');
  });

  it('should wrap fields containing newlines', () => {
    expect(escapeCsv('a\nb')).toBe('"a\nb"');
  });
});

describe('buildRevenueCsv', () => {
  it('should contain header, period, summary and detail sections', () => {
    const csv = buildRevenueCsv(RECORDS, SUMMARY, 'week', { generatedAt: '2024-01-02T00:00:00Z' });

    expect(csv).toContain('天链V3 营收统计');
    expect(csv).toContain('周期,周');
    expect(csv).toContain('生成时间,2024-01-02T00:00:00Z');
    expect(csv).toContain('汇总');
    expect(csv).toContain(`累计,${SUMMARY.total.toFixed(2)}`);
    expect(csv).toContain('明细');
    expect(csv).toContain('日期,营收金额(元),订单数');
  });

  it('should include each record row with 2-decimal amount', () => {
    const csv = buildRevenueCsv(RECORDS, SUMMARY, 'day', { generatedAt: '2024-01-02T00:00:00Z' });

    expect(csv).toContain('2024-01-01,123.46,10');
    expect(csv).toContain('2024-01-02,200.00,15');
  });

  it('should include a 合计 row summing amounts and orders', () => {
    const csv = buildRevenueCsv(RECORDS, SUMMARY, 'month', { generatedAt: '2024-01-02T00:00:00Z' });

    // 123.456 + 200 = 323.456 -> 323.46
    expect(csv).toContain('合计,323.46,25');
  });

  it('should reflect period label in the 周期 line', () => {
    expect(buildRevenueCsv([], SUMMARY, 'day', { generatedAt: 'x' })).toContain('周期,日');
    expect(buildRevenueCsv([], SUMMARY, 'week', { generatedAt: 'x' })).toContain('周期,周');
    expect(buildRevenueCsv([], SUMMARY, 'month', { generatedAt: 'x' })).toContain('周期,月');
  });

  it('should handle empty records gracefully (合计 = 0)', () => {
    const csv = buildRevenueCsv([], SUMMARY, 'week', { generatedAt: 'x' });
    expect(csv).toContain('合计,0.00,0');
    expect(csv).toContain('日期,营收金额(元),订单数');
  });

  it('should produce multi-line CSV string', () => {
    const csv = buildRevenueCsv(RECORDS, SUMMARY, 'week', { generatedAt: 'x' });
    expect(csv.split('\n').length).toBeGreaterThan(10);
  });
});

describe('revenueCsvFilename', () => {
  it('should map each period to the correct filename', () => {
    const cases: { period: RevenuePeriod; expected: string }[] = [
      { period: 'day', expected: 'tianlian-revenue-daily.csv' },
      { period: 'week', expected: 'tianlian-revenue-weekly.csv' },
      { period: 'month', expected: 'tianlian-revenue-monthly.csv' },
    ];
    cases.forEach(({ period, expected }) => {
      expect(revenueCsvFilename(period)).toBe(expected);
    });
  });
});

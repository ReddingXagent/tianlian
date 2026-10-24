/**
 * 大数据集降采样工具
 *
 * 用于 ECharts 图表数据量过大时的降采样（LTTB 算法）
 * 当数据点 > 500 时自动降采样以提升渲染性能
 */

/**
 * LTTB (Largest-Triangle-Three-Buckets) 降采样算法
 * 在保留数据趋势的前提下减少数据点
 *
 * @param data - 原始数据点 [x, y][]
 * @param threshold - 目标采样点数（默认 300）
 * @returns 降采样后的数据 [x, y][]
 */
export function lttbDownsample(
  data: [number, number][],
  threshold: number = 300
): [number, number][] {
  const len = data.length;
  if (threshold >= len || threshold <= 0) {
    return data;
  }

  const result: [number, number][] = [];
  // 始终保留首尾点
  result.push(data[0]);

  // 每桶的数据点数量
  const bucketSize = (len - 2) / (threshold - 2);

  // 上一个选中的点的索引
  let lastSelectedIndex = 0;

  for (let i = 0; i < threshold - 2; i++) {
    // 当前桶的范围
    const bucketStart = Math.floor((i + 0) * bucketSize) + 1;
    const bucketEnd = Math.floor((i + 1) * bucketSize) + 1;

    // 桶内所有点的平均坐标
    let avgX = 0;
    let avgY = 0;
    const avgCount = Math.max(bucketEnd - bucketStart, 1);
    for (let j = bucketStart; j < bucketEnd && j < len - 1; j++) {
      avgX += data[j][0];
      avgY += data[j][1];
    }
    avgX /= avgCount;
    avgY /= avgCount;

    // 上一个选中点
    const px = data[lastSelectedIndex][0];
    const py = data[lastSelectedIndex][1];

    // 下一个桶的平均点（用于计算三角形面积）
    const nextBucketStart = Math.floor((i + 1) * bucketSize) + 1;
    const nextBucketEnd = Math.floor((i + 2) * bucketSize) + 1;
    let nextAvgX = 0;
    let nextAvgY = 0;
    const nextCount = Math.max(nextBucketEnd - nextBucketStart, 1);
    for (let j = nextBucketStart; j < nextBucketEnd && j < len; j++) {
      nextAvgX += data[j][0];
      nextAvgY += data[j][1];
    }
    nextAvgX /= nextCount;
    nextAvgY /= nextCount;

    // 选择三角形面积最大的点
    let maxArea = -1;
    let selectedIndex = bucketStart;
    for (let j = bucketStart; j < bucketEnd && j < len - 1; j++) {
      // 三角形面积 = |(x1-x3)*(y2-y3) - (x2-x3)*(y1-y3)| / 2
      const area = Math.abs(
        (px - nextAvgX) * (data[j][1] - nextAvgY) -
        (data[j][0] - nextAvgX) * (py - nextAvgY)
      );
      if (area > maxArea) {
        maxArea = area;
        selectedIndex = j;
      }
    }

    result.push(data[selectedIndex]);
    lastSelectedIndex = selectedIndex;
  }

  // 添加最后一个点
  result.push(data[len - 1]);
  return result;
}

/**
 * 简单降采样（均匀采样）- 用于不需要保持极值趋势的场景
 */
export function uniformDownsample<T>(data: T[], threshold: number = 300): T[] {
  const len = data.length;
  if (threshold >= len || threshold <= 0) return data;

  const result: T[] = [];
  const step = (len - 1) / (threshold - 1);
  for (let i = 0; i < threshold; i++) {
    const idx = Math.round(i * step);
    result.push(data[Math.min(idx, len - 1)]);
  }
  return result;
}

/**
 * 自动降采样：判断数据量，超过阈值自动应用 LTTB
 */
export function autoDownsample(
  data: [number, number][],
  threshold: number = 500,
  targetPoints: number = 300
): [number, number][] {
  if (data.length <= threshold) return data;
  return lttbDownsample(data, targetPoints);
}

/**
 * ECharts series 数据的降采样包装
 * 将原始 series.data 自动降采样
 */
export function downsampleSeries(
  seriesData: Array<{ value: [number, number] | number; [key: string]: any }>,
  threshold: number = 500,
  targetPoints: number = 300
): Array<{ value: [number, number] | number; [key: string]: any }> {
  if (seriesData.length <= threshold) return seriesData;

  // 只对 [x, y] 格式的数据做降采样
  if (seriesData.length > 0 && Array.isArray(seriesData[0].value)) {
    const numericData = seriesData.map(
      (d) => d.value as [number, number]
    );
    const sampled = lttbDownsample(numericData, targetPoints);
    return sampled.map((v) => ({ value: v }));
  }

  return seriesData;
}
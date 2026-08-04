/**
 * 日期/时间显示格式单一源。
 *
 * 此前各屏 `new Date(x).toLocaleString(...)` 直接内联, 参数双源漂移:
 *  - OrderList: 'zh-CN' + 月日时分短格式
 *  - OrderDetail/Wallet: 'zh-CN' 完整格式
 *  - CouponScreen: toLocaleDateString() **不带 locale 参数**, 跟随设备 locale
 *    (en-US 设备上显示 MM/DD/YYYY, 与中文产品的 zh-CN 形态分叉)
 *
 * 收敛规则: 渲染侧一律走本文件函数; locale 统一钉 'zh-CN'。
 * 新增日期显示点禁止再内联 toLocale*。
 */

const LOCALE = 'zh-CN';

export type DateInput = Date | string | number | null | undefined;

function toDate(input: DateInput): Date | null {
  if (input === null || input === undefined || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 完整日期时间(含年): 订单详情/钱包流水等跨年场景 */
export function formatDateTime(input: DateInput): string {
  const d = toDate(input);
  return d ? d.toLocaleString(LOCALE) : '-';
}

/** 短日期时间(无年): 列表页紧凑形态, 月日时分两位补零 */
export function formatShortDateTime(input: DateInput): string {
  const d = toDate(input);
  return d
    ? d.toLocaleString(LOCALE, {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '-';
}

/** 日期(含年, 无时间): 优惠券有效期等 */
export function formatDate(input: DateInput): string {
  const d = toDate(input);
  return d ? d.toLocaleDateString(LOCALE) : '-';
}

/**
 * 距离显示单一源(F253)。
 *
 * 此前 StationCard 内联 `${distance}米`/`${(distance/1000).toFixed(1)}公里`,
 * MapView marker 内联 `${distance}m`/`${(distance/1000).toFixed(1)}km`——
 * 同一屏幕(Home列表卡片+顶部地图)对同一 station.distance 两种形态分叉。
 * 收敛规则: 渲染侧一律走本函数; 单位跟随 zh-CN 产品口径(米/公里)。
 * 调用侧保留各自的空值守卫(StationCard falsy / MapView undefined)。
 */
export function formatDistance(meters: number): string {
  if (meters < 1000) {
    return `${meters}米`;
  }
  return `${(meters / 1000).toFixed(1)}公里`;
}

/**
 * 金额显示单一源(F259)。
 *
 * 此前 10 文件 21 处内联 `.toFixed(2)`(金额/余额/电费/服务费/面值/优惠, 9屏+StationCard),
 * 形态虽一致但精度口径(两位小数)散布多源——未来任一处单独改成
 * toFixed(1)/toFixed(0) 即静默分叉(资金展示口径漂移)。
 * 收敛规则: 渲染侧一律走本函数; 符号前缀(+/-)由调用侧按业务语义处理,
 * 本函数只负责数值→两位小数字符串。
 */
export function formatMoney(value: number): string {
  return value.toFixed(2);
}

/**
 * 电量显示单一源(F265)。
 *
 * 此前能量精度口径双源散布: OrderList/OrderDetail/Charging 均内联
 * `.toFixed(2)`, 而 ProfileScreen 累计电量内联 `.toFixed(1)`——同一物理量
 * (充电电量 kWh)两种精度口径并存(340.5 在订单显 340.50, 个人页显 340.5),
 * 未来任一处单独再改即静默漂移。
 * 收敛规则: 渲染侧电量数值一律走本函数(两位小数, 与金额同精度口径);
 * 单位(kWh)由调用侧按既有排版附加, 本函数只负责数值→两位小数字符串。
 * 调用侧保留各自的空值守卫(ProfileScreen falsy 三元)。
 */
export function formatEnergy(value: number): string {
  return value.toFixed(2);
}

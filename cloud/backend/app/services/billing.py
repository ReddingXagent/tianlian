"""
计费引擎 - Phase41 运营+车队计费服务

提供5个独立费用计算函数 + 1个综合订单费用计算入口。
所有金额运算均使用 Decimal 保证精度。

安全加固 (卡 b6adf748):
计费核心不得因异常输入导致用户账单错误或结账崩溃。
- 入参先经 _to_decimal 安全转换: None/bool/非法类型 → Decimal("0") (安全默认, 不多收费)。
- 超大数 (>= 10^18) 经 _is_sane_decimal 守卫: 视为非法输入归 0, 防 DoS 与天价账单。
- 独立费用函数: 负数仍 raise ValueError (契约, 调用方需感知非法输入);
  None/非法类型/超大数/运算意外 → 返回 Decimal("0.00")。
- calculate_total_order: 每项费用独立兜底, 单项异常 (含子函数 raise) → 该项归 0,
  订单始终返回完整 dict (宁可少收一项, 不可整个订单崩溃致用户无法结账)。
- 负折扣 (discount_amount < 0): raise ValueError (卡2230298e 缺口1)。旧行为的
  「加价语义」使明细合计 ≠ paid_amount (total_amount / 费用明细均不含加价),
  财务对账不平; 现与独立费用函数的负数契约一致, 拒绝负折扣。
"""
from decimal import Decimal, InvalidOperation

# 数值合理性上限: 10^18 (千万亿级)。充电量/费率/金额远不至于此,
# 超出即视为脏输入 (防恶意超大数撑爆 Decimal 运算或生成天价账单)。
_MAX_ADJUSTED_EXP = 18
_ZERO = Decimal("0")
_TWO_PLACES = Decimal("0.01")


def _to_decimal(value) -> Decimal:
    """入参安全转 Decimal。

    None / bool / dict / list / 无法解析的对象 → Decimal("0")。
    int / float / 数值字符串 → Decimal(str(value)) (str 构造避免 float 二进制误差)。
    Decimal 原样返回。
    """
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    # bool 是 int 子类, 但充电量/费率传 bool 无业务意义 (True==1 会误计), 归 0。
    if isinstance(value, bool):
        return _ZERO
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            d = Decimal(value.strip())
        except (InvalidOperation, ValueError):
            return _ZERO
        return d
    # dict / list / object 等: 无法解释为金额, 归 0。
    return _ZERO


def _is_sane_decimal(d: Decimal) -> bool:
    """数值合理性: Decimal 有限 且 数量级 < 10^18。

    NaN / Infinity / adjusted() >= 18 的超大数 → False。
    """
    if not isinstance(d, Decimal):
        return False
    if not d.is_finite():
        return False
    return d.adjusted() < _MAX_ADJUSTED_EXP


def _quantize_or_zero(d: Decimal) -> Decimal:
    """安全 quantize 到 2 位小数; 异常 (极端精度 InvalidOperation) → 0。"""
    try:
        return d.quantize(_TWO_PLACES)
    except (InvalidOperation, ArithmeticError):
        return _ZERO


def calculate_electricity_fee(
    charged_kwh: Decimal,
    electricity_price: Decimal,
) -> Decimal:
    """计算电费 = 充电电量 × 电价（元/kWh）

    Args:
        charged_kwh: 充电电量 (kWh)
        electricity_price: 电价 (元/kWh)

    Returns:
        电费金额（元），保留2位小数。
        None/非法类型/超大数 → Decimal("0.00"); 负数 → raise ValueError。
    """
    try:
        kwh = _to_decimal(charged_kwh)
        price = _to_decimal(electricity_price)
        if not _is_sane_decimal(kwh) or not _is_sane_decimal(price):
            return _ZERO
        if kwh < _ZERO:
            raise ValueError("充电电量不能为负数")
        if price < _ZERO:
            raise ValueError("电价不能为负数")
        return _quantize_or_zero(kwh * price)
    except ValueError:
        raise
    except (InvalidOperation, ArithmeticError, TypeError):
        return _ZERO


def calculate_service_fee(
    charged_kwh: Decimal,
    service_fee_rate: Decimal,
) -> Decimal:
    """计算服务费 = 充电电量 × 服务费率（元/kWh）

    Args:
        charged_kwh: 充电电量 (kWh)
        service_fee_rate: 服务费率 (元/kWh)

    Returns:
        服务费金额（元），保留2位小数。
        None/非法类型/超大数 → Decimal("0.00"); 负数 → raise ValueError。
    """
    try:
        kwh = _to_decimal(charged_kwh)
        rate = _to_decimal(service_fee_rate)
        if not _is_sane_decimal(kwh) or not _is_sane_decimal(rate):
            return _ZERO
        if kwh < _ZERO:
            raise ValueError("充电电量不能为负数")
        if rate < _ZERO:
            raise ValueError("服务费率不能为负数")
        return _quantize_or_zero(kwh * rate)
    except ValueError:
        raise
    except (InvalidOperation, ArithmeticError, TypeError):
        return _ZERO


def calculate_parking_fee(
    duration_hours: Decimal,
    parking_fee_per_hour: Decimal,
) -> Decimal:
    """计算停车费 = 停车时长(小时) × 停车费率(元/小时)

    Args:
        duration_hours: 停车时长（小时）
        parking_fee_per_hour: 停车费率（元/小时）

    Returns:
        停车费金额（元），保留2位小数。
        None/非法类型/超大数 → Decimal("0.00"); 负数 → raise ValueError。
    """
    try:
        duration = _to_decimal(duration_hours)
        rate = _to_decimal(parking_fee_per_hour)
        if not _is_sane_decimal(duration) or not _is_sane_decimal(rate):
            return _ZERO
        if duration < _ZERO:
            raise ValueError("停车时长不能为负数")
        if rate < _ZERO:
            raise ValueError("停车费率不能为负数")
        return _quantize_or_zero(duration * rate)
    except ValueError:
        raise
    except (InvalidOperation, ArithmeticError, TypeError):
        return _ZERO


def calculate_idle_penalty(
    idle_minutes: int,
    idle_penalty_per_min: Decimal,
) -> Decimal:
    """计算超时占用费 = 超时分钟数 × 占用费率(元/分钟)

    Args:
        idle_minutes: 超时分钟数
        idle_penalty_per_min: 超时时占用费率（元/分钟）

    Returns:
        超时占用费金额（元），保留2位小数。
        None/非法类型/超大数 → Decimal("0.00"); 负数 → raise ValueError。
    """
    try:
        minutes = _to_decimal(idle_minutes)
        rate = _to_decimal(idle_penalty_per_min)
        if not _is_sane_decimal(minutes) or not _is_sane_decimal(rate):
            return _ZERO
        if minutes < _ZERO:
            raise ValueError("超时分钟数不能为负数")
        if rate < _ZERO:
            raise ValueError("占用费率不能为负数")
        return _quantize_or_zero(minutes * rate)
    except ValueError:
        raise
    except (InvalidOperation, ArithmeticError, TypeError):
        return _ZERO


def calculate_reservation_fee(
    reservation_duration_minutes: int,
    base_rate: Decimal = Decimal("1.00"),
) -> Decimal:
    """计算预约费 = 预约时长(分钟) × 基础费率(元/分钟)

    Args:
        reservation_duration_minutes: 预约时长（分钟）
        base_rate: 基础费率（元/分钟），默认1元/分钟

    Returns:
        预约费金额（元），保留2位小数。
        None/非法类型/超大数 → Decimal("0.00"); 负数 → raise ValueError。
    """
    try:
        duration = _to_decimal(reservation_duration_minutes)
        rate = _to_decimal(base_rate)
        if not _is_sane_decimal(duration) or not _is_sane_decimal(rate):
            return _ZERO
        if duration < _ZERO:
            raise ValueError("预约时长不能为负数")
        if rate < _ZERO:
            raise ValueError("基础费率不能为负数")
        return _quantize_or_zero(duration * rate)
    except ValueError:
        raise
    except (InvalidOperation, ArithmeticError, TypeError):
        return _ZERO


def _safe_fee(func, *args) -> Decimal:
    """单项费用兜底: 子函数任意异常 (含 ValueError 负数契约) → 该项归 0。

    用于 calculate_total_order, 保证单项异常不致整个订单崩溃。
    """
    try:
        return func(*args)
    except Exception:
        return _ZERO


def calculate_total_order(
    charged_kwh: Decimal,
    electricity_price: Decimal,
    service_fee_rate: Decimal,
    duration_hours: Decimal = Decimal("0"),
    parking_fee_per_hour: Decimal = Decimal("0"),
    idle_minutes: int = 0,
    idle_penalty_per_min: Decimal = Decimal("0"),
    reservation_duration_minutes: int = 0,
    reservation_fee_rate: Decimal = Decimal("0"),
    discount_amount: Decimal = Decimal("0"),
) -> dict:
    """综合计算充电订单全部费用

    计算顺序:
    1. 电费 = charged_kwh × electricity_price
    2. 服务费 = charged_kwh × service_fee_rate
    3. 停车费 = duration_hours × parking_fee_per_hour
    4. 超时占用费 = idle_minutes × idle_penalty_per_min
    5. 预约费 = reservation_duration_minutes × reservation_fee_rate
    6. 总金额 = 电费 + 服务费 + 停车费 + 占用费 + 预约费
    7. 实付金额 = 总金额 - 折扣金额 (不低于 0)

    安全保证: 任一费用项异常 → 该项归 0, 订单仍返回完整 dict。
              None/非法类型/超大数入参均不崩溃。

    Args:
        charged_kwh: 充电电量 (kWh)
        electricity_price: 电价 (元/kWh)
        service_fee_rate: 服务费率 (元/kWh)
        duration_hours: 停车时长（小时）
        parking_fee_per_hour: 停车费率（元/小时）
        idle_minutes: 超时分钟数
        idle_penalty_per_min: 超时占用费率（元/分钟）
        reservation_duration_minutes: 预约时长（分钟）
        reservation_fee_rate: 预约费率（基础费率，默认0）
        discount_amount: 折扣金额（元），默认0；负数 raise ValueError(与独立费用函数一致)

    Returns:
        dict: { electricity_fee, service_fee, parking_fee, idle_penalty,
                reservation_fee, total_amount, discount_amount, paid_amount }
    """
    electricity_fee = _safe_fee(calculate_electricity_fee, charged_kwh, electricity_price)
    service_fee = _safe_fee(calculate_service_fee, charged_kwh, service_fee_rate)
    parking_fee = _safe_fee(calculate_parking_fee, duration_hours, parking_fee_per_hour)
    idle_penalty = _safe_fee(calculate_idle_penalty, idle_minutes, idle_penalty_per_min)
    reservation_fee = _safe_fee(calculate_reservation_fee, reservation_duration_minutes, reservation_fee_rate)

    total_amount = _quantize_or_zero(
        electricity_fee + service_fee + parking_fee + idle_penalty + reservation_fee
    )

    # 折扣: sanitize (None/非法 → 0); 超大数 → 0; 负数折扣 raise (卡2230298e 缺口1)。
    # 负折扣旧行为是「加价」(paid=total+|d|), 但 total_amount / 费用明细不含加价 →
    # 明细合计 ≠ paid_amount, 财务对账不平; 与独立费用函数负数契约一致, 直接拒绝。
    discount = _to_decimal(discount_amount)
    if not _is_sane_decimal(discount):
        discount = _ZERO
    if discount < _ZERO:
        raise ValueError("折扣不能为负")
    discount = _quantize_or_zero(discount)

    paid_amount = total_amount - discount
    if paid_amount < _ZERO:
        paid_amount = _ZERO
    paid_amount = _quantize_or_zero(paid_amount)

    return {
        "electricity_fee": electricity_fee,
        "service_fee": service_fee,
        "parking_fee": parking_fee,
        "idle_penalty": idle_penalty,
        "reservation_fee": reservation_fee,
        "total_amount": total_amount,
        "discount_amount": discount,
        "paid_amount": paid_amount,
    }

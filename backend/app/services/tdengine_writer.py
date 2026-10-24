"""
TDengine 批量写入适配器
替代 SQLAlchemy 的 telemetry 写入

天链 V2 Phase3 - 时序引擎集成
"""
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from app.core.tdengine import get_tdengine_conn, TDENGINE_AVAILABLE

logger = logging.getLogger(__name__)

# 查询 SQL defense-in-depth 输入校验常量 (卡 26e833c5)
# table_type 白名单: 与 init_tdengine() 建的 3 张超级表一一对应；
# 调用方 (telemetry.py) 对 legacy 旧表走 SQLAlchemy，不会把 legacy 传入 TDengine。
_VALID_TABLE_TYPES = frozenset({"pv", "battery", "charger"})
_QUERY_LIMIT_MIN = 1
_QUERY_LIMIT_MAX = 10000


def _validate_id(value: Any, name: str = "id") -> int:
    """强制转 int 并校验非负，防御 f-string SQL 中的标识符/数值注入。

    Args:
        value: 待校验的 device_id / station_id (int 或可 int() 转换的值)。
        name: 字段名，仅用于错误信息。

    Returns:
        校验后的非负 int。

    Raises:
        ValueError: 无法转为 int 或为负数。
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"非法 {name}: {value!r}")
    if v < 0:
        raise ValueError(f"非法 {name}: {value!r} (必须 >= 0)")
    return v


def _validate_table_type(table_type: str) -> str:
    """表类型白名单校验，仅允许 pv/battery/charger。

    Raises:
        ValueError: 不在白名单内 (含 legacy / 空串 / 注入片段)。
    """
    if table_type not in _VALID_TABLE_TYPES:
        raise ValueError(f"非法 table_type: {table_type!r}")
    return table_type


def _validate_limit(value: Any, lo: int = _QUERY_LIMIT_MIN, hi: int = _QUERY_LIMIT_MAX) -> int:
    """强制转 int 并校验落在 [lo, hi] 范围，防御 LIMIT 子句注入。

    Raises:
        ValueError: 无法转为 int 或越界。
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"非法 limit: {value!r}")
    if v < lo or v > hi:
        raise ValueError(f"非法 limit: {value!r} (允许范围 {lo}~{hi})")
    return v


def _validate_time_range(start: Any, end: Any) -> None:
    """校验时间窗口: 两者必须为 datetime 且 start <= end。

    Raises:
        ValueError: start/end 非 datetime 对象，或 start > end。
    """
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("start/end 必须为 datetime 对象")
    if start > end:
        raise ValueError(f"非法时间区间: start({start}) > end({end})")


# region_id TAG 白名单: telemetry_* TAGS 是 NCHAR(32), 仅允许字母/数字/下划线/连字符。
# 拒单引号 (破坏 TAGS 引号配对)、分号 (SQL 注入)、空格、中文等 (卡 1b312e62 D3)。
_REGION_RE = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")


def _validate_region(value: Any) -> str:
    """region_id TAG 白名单校验, 防 f-string ``TAGS (..., ..., '{region_id}')`` 注入。

    写入侧 region_id 直接拼进单引号 TAG 字面量, 单引号/分号等会破坏 SQL 结构或
    构成注入。仅放行 ``[A-Za-z0-9_-]{1,32}`` (与 NCHAR(32) 列宽对齐); None 兜 "default"。

    Raises:
        ValueError: 不在白名单内 (空串 / 含特殊字符 / 超长)。
    """
    if value is None:
        return "default"
    s = str(value)
    if not _REGION_RE.match(s):
        raise ValueError(f"非法 region_id: {value!r}")
    return s


def _format_ts(ts: Any) -> str:
    """序列化时间戳为 TDengine TIMESTAMP 字面量字符串 (UTC)。

    D4 (时区族, 卡 1b312e62): aware datetime 显式 ``astimezone(UTC)`` 后再 strftime,
    避免 strftime 丢 tzinfo 后依赖 TDengine 服务器时区解释导致 8h 漂移 (上海 aware
    10:00 会被当 UTC 10:00 存, 实际应存 UTC 02:00); naive datetime 无 tzinfo, 按
    表面值直通 (调用方职责); None/缺失默认 ``now(timezone.utc)`` 与查询侧口径一致。

    非 datetime 输入 (字符串等) 原样 str() 直通, 由调用方保证格式。
    """
    if ts is None:
        ts = datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc)
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
    return str(ts)


# 三张超级表的数值列 (ts TIMESTAMP 之后), 顺序与 init_tdengine() 建表一一对应。
# 提取为模块级常量消除 write_pv/battery/charger 的复制粘贴 (卡 1b312e62 D5),
# 也是 D1 缺陷根因 —— 三处曾各自手写 record['device_id'] 下标与 record.get(...,0)
# 不一致; 集中后写入核心只此一份。
_PV_FIELDS: Tuple[str, ...] = (
    "grid_voltage_a", "grid_voltage_b", "grid_voltage_c",
    "grid_current_a", "grid_current_b", "grid_current_c",
    "grid_power_total", "grid_frequency", "grid_power_factor",
    "pv1_voltage", "pv1_current", "pv1_power",
    "pv2_voltage", "pv2_current", "pv2_power",
    "pv_power_total", "bus_voltage_pos", "bus_voltage_neg",
    "internal_temperature", "pv_temperature", "inv_temperature",
    "daily_generation", "total_generation",
    "run_time", "run_mode", "system_status",
)
_BATTERY_FIELDS: Tuple[str, ...] = (
    "grid_voltage_a", "grid_voltage_b", "grid_voltage_c",
    "grid_current_a", "grid_current_b", "grid_current_c",
    "grid_power_total", "grid_frequency", "grid_power_factor",
    "battery_voltage", "battery_current", "battery_power",
    "battery_soc", "battery_soh", "battery_temperature",
    "bms_charge_current_limit", "bms_discharge_current_limit",
    "bms_alarm_word", "bms_alarm_word2", "bms_alarm_word3",
    "daily_charge", "daily_discharge", "total_charge", "total_discharge",
    "internal_temperature", "ambient_temperature",
    "run_time", "run_mode", "system_status",
)
_CHARGER_FIELDS: Tuple[str, ...] = (
    "charger_voltage", "charger_current", "charger_power",
    "charger_soc", "charger_kwh", "gun_status", "gun_temperature",
    "internal_temperature", "ambient_temperature",
    "run_time", "run_mode", "system_status",
)


class TDengineWriter:
    """TDengine 批量写入器
    
    用法:
        writer = TDengineWriter()
        writer.write_pv(records=[...])  # 批量写入PV遥测
        writer.write_battery(records=[...])
        writer.write_charger(records=[...])
    
    特性:
        - 逐条 f-string SQL 自动建子表写入 (INSERT ... USING ... TAGS, 非参数绑定)
        - 毒记录逐条隔离, 返回真实成功条数 (卡 1b312e62 D1)
        - 写入侧标识符/TAG 校验 (_validate_id / _validate_region, D3)
        - aware 时间戳显式转 UTC 写入 (D4)
        - 支持查询最新数据和历史数据
    """
    
    def __init__(self, batch_size: int = 500):
        self.batch_size = batch_size
    
    def _write_records(
        self,
        records: List[Dict[str, Any]],
        stable_name: str,
        fields: Tuple[str, ...],
    ) -> int:
        """三个 write_xxx 共享的批量写入核心 (卡 1b312e62 D1/D3/D4/D5)。

        逐条 f-string SQL 执行 (每条独立 ``INSERT ... USING ... TAGS``), 非参数绑定
        (D5: 修正旧 docstring "使用参数绑定批量插入" 误述 —— TDengine REST 连接器此路径
        无绑定接口; 若改多值单 SQL 需另立工单, 本卡仅修正注释与逐条语义对齐)。

        数据安全:
          - D1: 毒记录 (缺 device_id 键 / None / 校验失败 / execute 异常) 逐条 try
            隔离, 跳过+计数+warning, 健康记录照常写入, 返回真实成功条数 (非 len(batch)),
            不再因单条坏记录静默丢整批, 也消除"已 execute 未计入 total_written"的部分
            写入状态不一致。
          - D3: device_id / station_id 过 _validate_id, region_id 过 _validate_region,
            拒负值/注入片段/单引号; 表名与 TAGS 均来自已校验值。
          - D4: 时间戳经 _format_ts 显式转 UTC 写入, 缺失默认 now(utc)。

        Args:
            records: 遥测记录列表, 每条 {device_id, station_id, region_id, timestamp, ...}。
            stable_name: 超级表名 (telemetry_pv / telemetry_battery / telemetry_charger)。
            fields: 该表数值列名元组 (ts 之后, 顺序与建表一致)。

        Returns:
            真实成功写入的条数 (毒记录/失败条不计入)。
        """
        if not TDENGINE_AVAILABLE:
            logger.warning(f"[TDengineWriter] TDengine 不可用, 跳过 {stable_name} 写入")
            return 0

        conn = get_tdengine_conn()
        if conn is None:
            logger.error(f"[TDengineWriter] 无法获取连接, 跳过 {stable_name} 写入")
            return 0

        if not records:
            return 0

        total_written = 0
        skipped = 0
        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            for record in batch:
                try:
                    # D3: 写入侧校验 (fail-fast, 毒记录在此被隔离)
                    device_id = _validate_id(record.get("device_id"), "device_id")
                    station_id = _validate_id(record.get("station_id", 0), "station_id")
                    region_id = _validate_region(record.get("region_id", "default"))
                    # D4: aware datetime 转 UTC, 缺失默认 now(utc)
                    ts_str = _format_ts(record.get("timestamp"))
                    # D1: 表名用校验后的 device_id (消除 record['device_id'] 下标
                    #     vs record.get('device_id', 0) 的历史不一致)
                    table_name = f"d_{device_id}"

                    # 缺失数值列填 NULL; str() 直通 (TDengine 按列类型解析, 非法值在
                    # execute 阶段被拒, 由逐条 try 兜底隔离)
                    values = f"'{ts_str}', " + ", ".join(
                        str(record.get(f, "NULL")) for f in fields
                    )
                    sql = (
                        f"INSERT INTO {table_name} USING {stable_name} "
                        f"TAGS ({device_id}, {station_id}, '{region_id}') "
                        f"VALUES ({values})"
                    )
                    conn.execute(sql)
                    total_written += 1
                except Exception as e:
                    # D1: 毒记录隔离 — 跳过+计数+warning, 绝不拖垮同批健康记录
                    skipped += 1
                    logger.warning(
                        f"[TDengineWriter] {stable_name} 跳过毒记录: {e} | record={record!r}"
                    )
                    continue

        if skipped:
            logger.warning(
                f"[TDengineWriter] {stable_name} 写入跳过 {skipped}/{len(records)} 条毒记录"
            )
        logger.debug(f"[TDengineWriter] {stable_name} 写入 {total_written} 条")
        return total_written

    def write_pv(self, records: List[Dict[str, Any]]) -> int:
        """批量写入光伏遥测数据

        Args:
            records: [{device_id, station_id, region_id, timestamp, grid_voltage_a, ...}, ...]
            字段集见 telemetry_pv 建表 (app/core/tdengine.py), 缺失数值列填 NULL。

        Returns:
            真实成功写入的条数 (毒记录不计入)。
        """
        return self._write_records(records, "telemetry_pv", _PV_FIELDS)
    
    def write_battery(self, records: List[Dict[str, Any]]) -> int:
        """批量写入电池遥测数据

        Args:
            records: [{device_id, station_id, region_id, timestamp, battery_voltage, ...}, ...]
            字段集见 telemetry_battery 建表 (app/core/tdengine.py), 缺失数值列填 NULL。

        Returns:
            真实成功写入的条数 (毒记录不计入)。
        """
        return self._write_records(records, "telemetry_battery", _BATTERY_FIELDS)
    
    def write_charger(self, records: List[Dict[str, Any]]) -> int:
        """批量写入充电桩遥测数据

        Args:
            records: [{device_id, station_id, region_id, timestamp, charger_voltage, ...}, ...]
            字段集见 telemetry_charger 建表 (app/core/tdengine.py), 缺失数值列填 NULL。

        Returns:
            真实成功写入的条数 (毒记录不计入)。
        """
        return self._write_records(records, "telemetry_charger", _CHARGER_FIELDS)
    
    def query_latest(self, device_id: int, table_type: str) -> Optional[Dict[str, Any]]:
        """查询设备最新一条遥测
        
        Args:
            device_id: 设备ID
            table_type: 表类型 (pv, battery, charger)
            
        Returns:
            最新遥测数据字典，无数据返回 None
        """
        # 输入校验 (fail-fast，先于可用性检查；异常向上抛出，绝不被下方 except 吞掉)
        device_id = _validate_id(device_id, "device_id")
        _validate_table_type(table_type)

        if not TDENGINE_AVAILABLE:
            return None

        conn = get_tdengine_conn()
        if conn is None:
            return None

        try:
            # 查询子表最新数据 (device_id 已 int() 校验，标识符安全)
            table_name = f"d_{device_id}"
            
            # 查询最新一条
            result = conn.query(f"""
                SELECT LAST(*) FROM {table_name}
            """)
            
            if result and len(result) > 0:
                # 转换结果
                row = result[0]
                data = {}
                for i, col in enumerate(result.fields):
                    data[col.name] = row[i]
                return data
            
        except Exception as e:
            logger.warning(f"[TDengineWriter] 查询最新数据失败: {e}")
        
        return None
    
    def query_range(
        self, 
        device_id: int, 
        table_type: str, 
        start: datetime, 
        end: datetime,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """查询设备一段时间的遥测数据
        
        Args:
            device_id: 设备ID
            table_type: 表类型 (pv, battery, charger)
            start: 开始时间
            end: 结束时间
            limit: 返回条数上限
            
        Returns:
            遥测数据列表
        """
        # 输入校验 (fail-fast，先于可用性检查；异常向上抛出，绝不被下方 except 吞掉)
        device_id = _validate_id(device_id, "device_id")
        _validate_table_type(table_type)
        _validate_time_range(start, end)
        limit = _validate_limit(limit)

        if not TDENGINE_AVAILABLE:
            return []

        conn = get_tdengine_conn()
        if conn is None:
            return []

        try:
            table_name = f"d_{device_id}"
            
            start_str = start.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end.strftime("%Y-%m-%d %H:%M:%S")
            
            result = conn.query(f"""
                SELECT * FROM {table_name}
                WHERE ts >= '{start_str}' AND ts <= '{end_str}'
                ORDER BY ts DESC
                LIMIT {limit}
            """)
            
            if result:
                data_list = []
                for row in result:
                    data = {}
                    for i, col in enumerate(result.fields):
                        data[col.name] = row[i]
                    data_list.append(data)
                return data_list
            
        except Exception as e:
            logger.warning(f"[TDengineWriter] 查询历史数据失败: {e}")
        
        return []
    
    def query_station_stats(
        self,
        station_id: int,
        table_type: str,
        start: datetime,
        end: datetime
    ) -> Optional[Dict[str, Any]]:
        """查询场站聚合统计数据

        ⚠️ 电量口径已知缺陷 (累计计数器 SUM 翻倍，卡 eedd9431 调研):
            daily_generation / daily_charge / daily_discharge / charger_kwh 是
            modbus 寄存器直读的 **累计计数器快照** (日内累计/终身累计)，遥测每行重复
            携带当前累计值 → 下方 SUM 会把同一计数器翻 N 倍 (N=窗口行数)，数值虚高数十倍。
            正确口径 = 窗口净增量 LAST−FIRST (且须先 PARTITION BY device_id 求每设备增量
            再跨设备 SUM)。本方法与 pre_aggregation.aggregate_station_hourly /
            core/tdengine._create_continuous_aggregations 三处 SUM 口径完全一致，
            单改此处会制造三方分裂 → 须立独立财务口径工单三处同步改，**禁止单点改**。
            当前 grep 确认零生产调用方 (死方法)，故挂起待工单。
            全局修正方案见 docs/plans/tdengine-cumulative-counter-caliber-fix.md。

        Args:
            station_id: 场站ID
            table_type: 表类型 (pv, battery, charger)
            start: 开始时间
            end: 结束时间

        Returns:
            聚合统计数据字典
        """
        # 输入校验 (fail-fast，先于可用性检查；异常向上抛出，绝不被下方 except 吞掉)
        station_id = _validate_id(station_id, "station_id")
        _validate_table_type(table_type)
        _validate_time_range(start, end)

        if not TDENGINE_AVAILABLE:
            return None

        conn = get_tdengine_conn()
        if conn is None:
            return None

        try:
            stable_name = f"telemetry_{table_type}"
            
            start_str = start.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end.strftime("%Y-%m-%d %H:%M:%S")
            
            # 查询聚合统计
            # ⚠️ daily_generation/daily_charge/daily_discharge/charger_kwh 是累计计数器快照,
            #    SUM 翻 N 倍 (口径缺陷, 见 docstring + docs/plans/tdengine-cumulative-counter-caliber-fix.md).
            #    修正须三处同步 (本处 + pre_aggregation + core/tdengine 流), 禁止单点改.
            if table_type == "pv":
                result = conn.query(f"""
                    SELECT 
                        AVG(grid_power_total) AS avg_power,
                        MAX(grid_power_total) AS max_power,
                        AVG(pv_power_total) AS avg_pv_power,
                        MAX(pv_power_total) AS max_pv_power,
                        SUM(daily_generation) AS pv_generation_kwh,
                        AVG(internal_temperature) AS avg_temp,
                        MAX(internal_temperature) AS max_temp,
                        COUNT(*) AS data_points
                    FROM {stable_name}
                    WHERE station_id = {station_id}
                      AND ts >= '{start_str}' AND ts <= '{end_str}'
                """)
            elif table_type == "battery":
                result = conn.query(f"""
                    SELECT 
                        AVG(battery_soc) AS avg_soc,
                        AVG(battery_power) AS avg_power,
                        SUM(daily_charge) AS charge_kwh,
                        SUM(daily_discharge) AS discharge_kwh,
                        AVG(internal_temperature) AS avg_temp,
                        MAX(internal_temperature) AS max_temp,
                        COUNT(*) AS data_points
                    FROM {stable_name}
                    WHERE station_id = {station_id}
                      AND ts >= '{start_str}' AND ts <= '{end_str}'
                """)
            elif table_type == "charger":
                result = conn.query(f"""
                    SELECT 
                        AVG(charger_power) AS avg_power,
                        MAX(charger_power) AS max_power,
                        SUM(charger_kwh) AS charger_kwh,
                        AVG(internal_temperature) AS avg_temp,
                        MAX(internal_temperature) AS max_temp,
                        COUNT(*) AS data_points
                    FROM {stable_name}
                    WHERE station_id = {station_id}
                      AND ts >= '{start_str}' AND ts <= '{end_str}'
                """)
            else:
                return None
            
            if result and len(result) > 0:
                row = result[0]
                data = {}
                for i, col in enumerate(result.fields):
                    data[col.name] = row[i]
                return data
            
        except Exception as e:
            logger.warning(f"[TDengineWriter] 查询场站统计失败: {e}")
        
        return None
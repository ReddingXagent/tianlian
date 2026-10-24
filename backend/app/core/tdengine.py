"""
TDengine 连接管理器
使用 taosrest (RESTful) 连接器，兼容 TDengine 3.x

天链 V2 Phase3 - 时序引擎集成
"""
import os
import logging
import threading

logger = logging.getLogger(__name__)

# 配置
TDENGINE_URL = os.getenv("TDENGINE_URL", "http://localhost:6041")
TDENGINE_USER = os.getenv("TDENGINE_USER", "root")
TDENGINE_PASS = os.getenv("TDENGINE_PASS", "taosdata")
TDENGINE_DB = os.getenv("TDENGINE_DB", "tianlian")
# 请求级超时 (秒): taosrest TaosRestConnection(timeout=...) 会把该值传给底层
# RestClient → requests，作用于连接上每一次 execute/query 的 HTTP 请求 (卡 2bfe5ffd)。
# 默认 5s: TDengine 半死时避免 DCL 锁内无限挂起拖垮 API 线程池。
TDENGINE_TIMEOUT = float(os.getenv("TDENGINE_TIMEOUT", "5"))

# 检测 taosrest 是否可用
try:
    import taosrest
    TDENGINE_AVAILABLE = True
    logger.info("[TDengine] taosrest 已加载，TDengine 可用")
except ImportError:
    TDENGINE_AVAILABLE = False
    logger.warning("[TDengine] taosrest 未安装，TDengine 不可用，将降级到 SQLAlchemy")

# 类型注解不能引用 taosrest（可能未安装），用 Any 代替
_conn = None  # type: ignore
_lock = threading.Lock()


def get_tdengine_conn():
    """获取 TDengine 连接（单例，线程安全，双重检查锁）

    多线程并发首次调用时，只有一个线程执行 taosrest.connect()，其余在锁上
    等待并通过第二次 None 检查直接返回，避免多余连接被覆盖后泄漏。

    Returns:
        TDengine 连接对象，如果 taosrest 未安装返回 None
    """
    global _conn

    if not TDENGINE_AVAILABLE:
        return None

    if _conn is None:
        with _lock:
            if _conn is None:
                try:
                    _conn = taosrest.connect(
                        url=TDENGINE_URL,
                        user=TDENGINE_USER,
                        password=TDENGINE_PASS,
                        database=TDENGINE_DB,
                        timeout=TDENGINE_TIMEOUT,
                    )
                    logger.info(f"[TDengine] 连接成功: {TDENGINE_URL}")
                except Exception as e:
                    logger.error(f"[TDengine] 连接失败: {e}")
                    _conn = None

    return _conn


def init_tdengine():
    """初始化 TDengine 数据库和超级表
    
    创建:
    - 数据库 tianlian (KEEP 90 DAYS)
    - 超级表 telemetry_pv (光伏逆变器)
    - 超级表 telemetry_battery (储能电池/PCS)
    - 超级表 telemetry_charger (充电桩)
    - 连续聚合流 (预聚合)
    """
    if not TDENGINE_AVAILABLE:
        logger.info("[TDengine] taosrest 未安装，跳过初始化")
        return
    
    conn = get_tdengine_conn()
    if conn is None:
        logger.error("[TDengine] 无法获取连接，初始化失败")
        return
    
    try:
        # 创建数据库（保留90天数据）
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {TDENGINE_DB} KEEP 90 DAYS")
        conn.execute(f"USE {TDENGINE_DB}")
        logger.info(f"[TDengine] 数据库 {TDENGINE_DB} 已创建")
        
        # 创建超级表: telemetry_pv (光伏逆变器)
        conn.execute("""
            CREATE STABLE IF NOT EXISTS telemetry_pv (
                ts TIMESTAMP,
                grid_voltage_a FLOAT,
                grid_voltage_b FLOAT,
                grid_voltage_c FLOAT,
                grid_current_a FLOAT,
                grid_current_b FLOAT,
                grid_current_c FLOAT,
                grid_power_total FLOAT,
                grid_frequency FLOAT,
                grid_power_factor FLOAT,
                pv1_voltage FLOAT,
                pv1_current FLOAT,
                pv1_power FLOAT,
                pv2_voltage FLOAT,
                pv2_current FLOAT,
                pv2_power FLOAT,
                pv_power_total FLOAT,
                bus_voltage_pos FLOAT,
                bus_voltage_neg FLOAT,
                internal_temperature FLOAT,
                pv_temperature FLOAT,
                inv_temperature FLOAT,
                daily_generation FLOAT,
                total_generation FLOAT,
                run_time INT,
                run_mode INT,
                system_status INT
            ) TAGS (device_id BIGINT, station_id BIGINT, region_id NCHAR(32))
        """)
        
        # 创建超级表: telemetry_battery (储能电池/PCS)
        conn.execute("""
            CREATE STABLE IF NOT EXISTS telemetry_battery (
                ts TIMESTAMP,
                grid_voltage_a FLOAT,
                grid_voltage_b FLOAT,
                grid_voltage_c FLOAT,
                grid_current_a FLOAT,
                grid_current_b FLOAT,
                grid_current_c FLOAT,
                grid_power_total FLOAT,
                grid_frequency FLOAT,
                grid_power_factor FLOAT,
                battery_voltage FLOAT,
                battery_current FLOAT,
                battery_power FLOAT,
                battery_soc FLOAT,
                battery_soh FLOAT,
                battery_temperature FLOAT,
                bms_charge_current_limit FLOAT,
                bms_discharge_current_limit FLOAT,
                bms_alarm_word INT,
                bms_alarm_word2 INT,
                bms_alarm_word3 INT,
                daily_charge FLOAT,
                daily_discharge FLOAT,
                total_charge FLOAT,
                total_discharge FLOAT,
                internal_temperature FLOAT,
                ambient_temperature FLOAT,
                run_time INT,
                run_mode INT,
                system_status INT
            ) TAGS (device_id BIGINT, station_id BIGINT, region_id NCHAR(32))
        """)
        
        # 创建超级表: telemetry_charger (充电桩)
        conn.execute("""
            CREATE STABLE IF NOT EXISTS telemetry_charger (
                ts TIMESTAMP,
                charger_voltage FLOAT,
                charger_current FLOAT,
                charger_power FLOAT,
                charger_soc FLOAT,
                charger_kwh FLOAT,
                gun_status INT,
                gun_temperature FLOAT,
                internal_temperature FLOAT,
                ambient_temperature FLOAT,
                run_time INT,
                run_mode INT,
                system_status INT
            ) TAGS (device_id BIGINT, station_id BIGINT, region_id NCHAR(32))
        """)
        
        logger.info("[TDengine] 3 张超级表已创建: telemetry_pv, telemetry_battery, telemetry_charger")
        
        # 创建连续聚合流（预聚合）
        _create_continuous_aggregations(conn)
        
        logger.info("[TDengine] 初始化完成")
        
    except Exception as e:
        logger.error(f"[TDengine] 初始化失败: {e}")
        raise


def _create_continuous_aggregations(conn):
    """创建 TDengine 连续聚合流
    
    相当于自动刷新的物化视图，用于预聚合统计
    """
    try:
        # ⚠️ 电量口径缺陷: daily_generation/daily_charge/daily_discharge/charger_kwh 是 modbus 累计计数器
        #    快照, 下方 SUM 翻 N 倍。与 tdengine_writer.query_station_stats / pre_aggregation 三处 SUM
        #    口径一致 → 须立工单三处同步改 (LAST−FIRST, 先 PARTITION BY device_id 求每设备增量再 SUM),
        #    禁止单点改。注: INTERVAL(1h) 按整点切, daily_* 零点重置落在边界 → 修正后天然无跨零点问题。
        #    详见 docs/plans/tdengine-cumulative-counter-caliber-fix.md (卡 eedd9431)。
        # 场站小时聚合 (光伏)
        conn.execute("""
            CREATE STREAM IF NOT EXISTS station_pv_hourly_stream
            INTO station_pv_hourly_stats AS
            SELECT 
                station_id,
                _wstart AS hour,
                AVG(grid_power_total) AS avg_total_power,
                MAX(grid_power_total) AS max_total_power,
                AVG(pv_power_total) AS avg_pv_power,
                MAX(pv_power_total) AS max_pv_power,
                SUM(daily_generation) AS pv_generation_kwh,
                AVG(internal_temperature) AS avg_temp,
                MAX(internal_temperature) AS max_temp,
                COUNT(*) AS data_points
            FROM telemetry_pv
            INTERVAL(1h)
        """)
        
        # 场站小时聚合 (储能)
        conn.execute("""
            CREATE STREAM IF NOT EXISTS station_battery_hourly_stream 
            INTO station_battery_hourly_stats AS
            SELECT 
                station_id,
                _wstart AS hour,
                AVG(battery_soc) AS avg_battery_soc,
                AVG(battery_power) AS avg_battery_power,
                SUM(daily_charge) AS charge_kwh,
                SUM(daily_discharge) AS discharge_kwh,
                AVG(internal_temperature) AS avg_temp,
                MAX(internal_temperature) AS max_temp,
                COUNT(*) AS data_points
            FROM telemetry_battery
            INTERVAL(1h)
        """)
        
        # 场站小时聚合 (充电桩)
        conn.execute("""
            CREATE STREAM IF NOT EXISTS station_charger_hourly_stream 
            INTO station_charger_hourly_stats AS
            SELECT 
                station_id,
                _wstart AS hour,
                AVG(charger_power) AS avg_charger_power,
                MAX(charger_power) AS max_charger_power,
                SUM(charger_kwh) AS charger_kwh,
                AVG(internal_temperature) AS avg_temp,
                MAX(internal_temperature) AS max_temp,
                COUNT(*) AS data_points
            FROM telemetry_charger
            INTERVAL(1h)
        """)
        
        logger.info("[TDengine] 3 个连续聚合流已创建")
        
    except Exception as e:
        # 连续聚合可能已存在，忽略错误
        logger.warning(f"[TDengine] 创建连续聚合流失败（可能已存在）: {e}")


def close_tdengine():
    """关闭 TDengine 连接"""
    global _conn
    with _lock:
        conn = _conn
        _conn = None
    if conn is not None:
        try:
            conn.close()
            logger.info("[TDengine] 连接已关闭")
        except Exception as e:
            logger.warning(f"[TDengine] 关闭连接失败: {e}")


def is_tdengine_available() -> bool:
    """检查 TDengine 是否可用
    
    Returns:
        True 如果 taosrest 已安装且连接成功
    """
    return TDENGINE_AVAILABLE and get_tdengine_conn() is not None
#!/Users/xxx/.openclaw/workspace/projects/tianlian-v3/backend/venv/bin/python3
"""
设备日志模拟器 - 根据设备类型和故障生成真实的设备日志

模拟各种光储充设备的本地日志输出，包括：
- 逆变器运行日志
- 充电桩运行日志
- 储能PCS日志
- BMS通信日志
- 网关系统日志

当前为模拟器实现，提供测试和开发阶段的数据。
后续可集成真实设备日志采集器替换本模块。
"""
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List

logger = logging.getLogger(__name__)


class _SafeFormatDict(dict):
    """str.format_map 安全字典: 缺失占位符返回空串而非抛 KeyError。"""

    def __missing__(self, key):  # type: ignore[override]
        return ""


class DeviceLogSimulator:
    """设备日志模拟器"""

    # 逆变器日志模板
    INVERTER_NORMAL_LOGS = [
        "[INFO] 系统自检完成，设备状态正常",
        "[INFO] 电网电压: {voltage}V, 频率: {freq}Hz",
        "[INFO] 直流侧电压: {dc_v}V, 直流侧电流: {dc_a}A",
        "[INFO] 当前功率: {power}kW, 发电量累计: {total_kwh}kWh",
        "[INFO] 机内温度: {temp}°C, 散热风扇转速: {fan_rpm}rpm",
        "[INFO] MPPT追踪正常, 光伏阵列电压: {pv_v}V",
        "[INFO] 绝缘阻抗检测正常: {ins}MΩ",
        "[INFO] 并网继电器状态: 闭合",
        "[DEBUG] Modbus轮询周期: {interval}ms, 响应正常",
    ]

    INVERTER_FAULT_LOGS = {
        "0x01": [  # 电网一段过压
            "[WARN] A相电压异常: {voltage}V, 超过阈值{threshold}V",
            "[WARN] 电压THD: {thd}%, 超出正常范围",
            "[ERROR] 电网一段过压保护触发 (A相)",
            "[INFO] 电网电压历史: [{v1}, {v2}, {v3}, {v4}]V",
            "[DEBUG] 保护阈值设置: {threshold}V, 延时: {delay}ms",
        ],
        "0x27": [  # 孤岛故障
            "[WARN] 电网频率异常: {freq}Hz",
            "[ERROR] 检测到电网断开! 频率变化率: {roc}Hz/s",
            "[WARN] 逆变器输出功率与电网功率不匹配: {p_diff}kW",
            "[ERROR] 孤岛保护触发, 逆变器停机",
            "[INFO] 孤岛检测算法: 主动频率偏移法, 判断结果: 孤岛",
        ],
        "0x7E": [  # BMS通信异常
            "[WARN] BMS通信超时, 重试次数: {retry}",
            "[ERROR] CAN总线错误: 接收缓冲区溢出",
            "[WARN] CAN_H电压: {can_h}V, CAN_L电压: {can_l}V (正常: 2.5V/2.5V)",
            "[ERROR] BMS无响应, 通信超时: {timeout}ms",
            "[DEBUG] 终端电阻检测: 开路 (正常: 120Ω)",
        ],
        "0xA0": [  # 机内温度过温
            "[WARN] 机内温度: {temp}°C, 接近阈值{threshold}°C",
            "[WARN] 散热风扇状态: 异常! 转速: {rpm}rpm (正常: >2500rpm)",
            "[WARN] 散热片温度: {heat_sink}°C, IGBT温度: {igbt}°C",
            "[WARN] 进风口温度: {inlet}°C, 出风口温度: {outlet}°C, 温差: {delta}°C",
            "[ERROR] 温度过温保护触发, 降功率运行: {derating}%",
        ],
        "0x3C": [  # 逆变侧过流
            "[WARN] 输出电流异常: {current}A, 额定: {rated}A",
            "[WARN] 电流THD: {thd}%, 谐波超标",
            "[ERROR] 过流保护触发, 逆变器停机",
            "[DEBUG] IGBT模块温度: {igbt_temp}°C, 驱动电压: {drive_v}V",
        ],
        "0x82": [  # 电池过充
            "[WARN] 电池电压: {bat_v}V, 超过充电截止电压{cutoff}V",
            "[WARN] 充电电流: {charge_a}A, SOC: {soc}%",
            "[WARN] 单体最高电压: {cell_max}V, 编号: #{cell_id}",
            "[ERROR] 过充保护触发, 切断充电回路",
        ],
    }

    # 充电桩日志模板
    CHARGER_NORMAL_LOGS = [
        "[INFO] 充电桩自检完成, 状态: 待机",
        "[INFO] 输入电压: {voltage}V, 输入频率: {freq}Hz",
        "[INFO] 枪座温度: {temp}°C, 环境温度: {env_temp}°C",
        "[INFO] 通信模块状态: 正常, 信号强度: {signal}dBm",
        "[DEBUG] 计费模块时钟同步正常",
        "[INFO] 绝缘检测正常: {ins}MΩ",
    ]

    CHARGER_FAULT_LOGS = {
        "0x0101": [  # 急停故障
            "[ERROR] 急停按钮状态: PRESSED!",
            "[WARN] 急停电路状态: 触发, 输出继电器已断开",
            "[ERROR] 充电紧急停止, 输出功率归零",
            "[INFO] 急停时间: {time}, 操作员需现场复位",
        ],
        "0x0601": [  # BMS通信异常(充电桩)
            "[WARN] 车辆BMS通信建立失败, 重试次数: {retry}",
            "[WARN] CAN接口状态: 总线错误, 错误计数器: {err_count}",
            "[ERROR] 车辆BMS无响应, 通信超时",
            "[DEBUG] 充电协议协商失败, 支持的协议: {protocols}",
        ],
        "0x0302": [  # 充电接口过温
            "[WARN] 充电枪温度: {gun_temp}°C, 超过阈值{threshold}°C",
            "[WARN] 枪座温度: {socket_temp}°C",
            "[WARN] 充电电流: {current}A, 已持续: {duration}min",
            "[ERROR] 接口过温保护触发, 降低充电功率至{derating}%",
        ],
    }

    @classmethod
    def _fill(cls, template: str, **kwargs) -> str:
        """填充日志模板"""
        defaults = {
            "voltage": round(random.uniform(215, 245), 1),
            "freq": round(random.uniform(49.8, 50.2), 2),
            "temp": round(random.uniform(25, 85), 1),
            "threshold": 264,
            "power": round(random.uniform(5, 20), 2),
            "total_kwh": round(random.uniform(1000, 10000), 1),
            "dc_v": round(random.uniform(600, 800), 1),
            "dc_a": round(random.uniform(10, 50), 1),
            "fan_rpm": random.randint(2000, 3500),
            "pv_v": round(random.uniform(400, 700), 1),
            "ins": round(random.uniform(1, 50), 1),
            "interval": random.randint(500, 2000),
            "thd": round(random.uniform(0.5, 8.0), 1),
            "v1": random.randint(230, 260),
            "v2": random.randint(230, 260),
            "v3": random.randint(230, 260),
            "v4": random.randint(230, 260),
            "delay": random.randint(100, 1000),
            "roc": round(random.uniform(0.5, 5.0), 2),
            "p_diff": round(random.uniform(-5, 5), 1),
            "retry": random.randint(3, 10),
            "can_h": round(random.uniform(0, 5), 1),
            "can_l": round(random.uniform(0, 5), 1),
            "timeout": random.randint(5000, 30000),
            "rpm": random.randint(0, 1000),
            "heat_sink": round(random.uniform(40, 95), 1),
            "igbt": round(random.uniform(50, 105), 1),
            "inlet": round(random.uniform(20, 35), 1),
            "outlet": round(random.uniform(35, 60), 1),
            "delta": round(random.uniform(5, 30), 1),
            "derating": round(random.uniform(40, 80), 1),
            "current": round(random.uniform(30, 80), 1),
            "rated": 50,
            "igbt_temp": round(random.uniform(60, 110), 1),
            "drive_v": round(random.uniform(12, 16), 1),
            "bat_v": round(random.uniform(52, 60), 1),
            "cutoff": 56.4,
            "charge_a": round(random.uniform(10, 50), 1),
            "soc": random.randint(85, 100),
            "cell_max": round(random.uniform(3.6, 4.3), 3),
            "cell_id": random.randint(1, 16),
            "signal": random.randint(-90, -50),
            "env_temp": round(random.uniform(15, 35), 1),
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "err_count": random.randint(50, 200),
            "protocols": "GB/T 27930-2015, GB/T 18487.1-2015",
            "gun_temp": round(random.uniform(60, 95), 1),
            "socket_temp": round(random.uniform(50, 80), 1),
            "duration": random.randint(10, 120),
            "heat_sink": round(random.uniform(40, 95), 1),
        }
        defaults.update(kwargs)
        try:
            return template.format_map(_SafeFormatDict(defaults))
        except (KeyError, IndexError, ValueError):
            logger.exception("日志模板填充失败, template=%r", template)
            return template

    @classmethod
    def generate_normal_logs(cls, device_type: str = "inverter", count: int = 10) -> List[str]:
        """生成正常运行日志"""
        try:
            if device_type == "charger":
                templates = cls.CHARGER_NORMAL_LOGS
            else:
                # inverter 及未知设备类型均回退到默认的逆变器模板
                templates = cls.INVERTER_NORMAL_LOGS
            logs = []
            now = datetime.now(timezone.utc)
            for i in range(count):
                template = random.choice(templates)
                ts = now - timedelta(seconds=(count - i) * random.randint(5, 60))
                log = f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {cls._fill(template)}"
                logs.append(log)
            return logs
        except Exception:
            logger.exception("生成正常运行日志失败, device_type=%s count=%s", device_type, count)
            return []

    @classmethod
    def generate_fault_logs(cls, fault_code: str, device_type: str = "inverter") -> List[str]:
        """生成故障日志"""
        try:
            if device_type == "charger":
                fault_logs = cls.CHARGER_FAULT_LOGS.get(fault_code)
                normal_logs = cls.CHARGER_NORMAL_LOGS
            else:
                # inverter 及未知设备类型回退到默认的逆变器模板
                fault_logs = cls.INVERTER_FAULT_LOGS.get(fault_code)
                normal_logs = cls.INVERTER_NORMAL_LOGS

            if not fault_logs:
                # 如果不认识的故障码，用普通+随机故障日志
                fault_logs = ["[ERROR] 未知故障码: {fc}"]
                kwargs = {"fc": fault_code}
            else:
                kwargs = {}

            logs = []
            now = datetime.now(timezone.utc)

            # 前几条正常日志
            for i in range(random.randint(3, 8)):
                template = random.choice(normal_logs)
                ts = now - timedelta(seconds=(12 - i) * random.randint(10, 30))
                log = f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {cls._fill(template)}"
                logs.append(log)

            # 异常警告日志
            for i, template in enumerate(fault_logs):
                ts = now - timedelta(seconds=(len(fault_logs) - i) * random.randint(1, 5))
                log = f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {cls._fill(template, **kwargs)}"
                logs.append(log)

            # 故障后的几条日志
            for i in range(random.randint(2, 5)):
                template = random.choice(normal_logs)
                ts = now + timedelta(seconds=(i + 1) * random.randint(1, 3))
                log = f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {cls._fill(template)}"
                logs.append(log)

            return logs
        except Exception:
            logger.exception("生成故障日志失败, fault_code=%s device_type=%s", fault_code, device_type)
            return []

    @classmethod
    def get_logs_for_alarm(cls, device_type: str, fault_code: str = None, fault_name: str = None) -> List[str]:
        """根据告警信息生成设备日志"""
        try:
            return cls.generate_fault_logs(fault_code or "0x01", device_type)
        except Exception:
            logger.exception("获取告警设备日志失败, device_type=%s fault_code=%s", device_type, fault_code)
            return []

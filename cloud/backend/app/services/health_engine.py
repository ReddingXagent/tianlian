"""
健康度评估引擎
5 维度评分模型 + 趋势预测 + 预警生成

安全加固 (卡 a4f06843):
所有评分方法对 None/非法值/异常输入做防御, 异常时返回安全默认分数,
保证设备健康评估链不因单点异常崩溃。
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 安全默认分数 (异常时各维度返回此值)
_SAFE_DEFAULT_SCORE = 80.0


class HealthEngine:
    """
    健康度评估引擎
    
    5 维度权重:
    - 电气安全 (30%): 绝缘电阻、漏电流、接地状态
    - 热稳定性 (25%): 模块温度、温升速率、散热风扇
    - 通信可靠性 (20%): 心跳丢失率、报文响应时延
    - 电能质量 (15%): 电压偏差、电流谐波、功率因数
    - 机械寿命 (10%): 充电枪插拔次数、枪头温度
    """
    
    WEIGHTS = {
        'electrical': 0.30,
        'thermal': 0.25,
        'communication': 0.20,
        'power_quality': 0.15,
        'mechanical': 0.10,
    }
    
    THRESHOLDS = {
        'healthy': 80,    # >80 健康
        'warning': 60,    # 60-80 警告
        'critical': 0,    # <60 严重
    }
    
    # ──────────────────────────────────────────────
    # 设备类型温度阈值表
    # 每个条目: (warning_扣15, critical_扣30, severe_扣50, 温升速率阈值)
    # ──────────────────────────────────────────────
    THERMAL_THRESHOLDS = {
        'pv_inverter':      (60, 70, 80, 5.0),   # 光伏逆变器: IGBT 最高 85°C
        'battery_inverter': (60, 70, 80, 5.0),   # 储能逆变器: 同逆变器
        'pcs':              (55, 65, 75, 5.0),   # 储能变流器: 略保守
        'battery':          (45, 55, 65, 3.0),   # 储能电池柜: ★最严格, 温升更敏感
        'charger_dc':       (65, 80, 90, 5.0),   # 直流充电桩: 功率模块耐受高
        'charger_ac':       (65, 80, 90, 5.0),   # 交流充电桩: 同充电桩
        'meter':            (70, 85, 95, 5.0),   # 电表: 非关键指标
        'gateway':          (70, 85, 95, 5.0),   # 网关: 非关键指标
    }
    
    # 默认温度阈值（不在此表中的设备类型使用）
    DEFAULT_THERMAL_THRESHOLDS = (60, 70, 80, 5.0)
    
    # ──────────────────────────────────────────────
    # 枪头温度阈值（按设备类型）
    # 只有充电桩类设备有枪头温度扣分，其他设备不计
    # ──────────────────────────────────────────────
    GUN_TEMP_THRESHOLDS = {
        'charger_dc': 60,   # 直流充电桩 >60°C 扣分
        'charger_ac': 60,   # 交流充电桩 >60°C 扣分
    }
    
    def __init__(self):
        pass
    
    @staticmethod
    def _get_thermal_thresholds(device_type: Optional[str]) -> Tuple[float, float, float, float]:
        """获取设备类型对应的温度阈值"""
        if device_type is None:
            return HealthEngine.DEFAULT_THERMAL_THRESHOLDS
        dt = device_type.lower() if isinstance(device_type, str) else str(device_type)
        return HealthEngine.THERMAL_THRESHOLDS.get(
            dt, HealthEngine.DEFAULT_THERMAL_THRESHOLDS
        )
    
    @staticmethod
    def _get_gun_temp_threshold(device_type: Optional[str]) -> Optional[float]:
        """获取设备类型对应的枪头温度阈值，非充电桩返回 None"""
        if device_type is None:
            return None
        dt = device_type.lower() if isinstance(device_type, str) else str(device_type)
        return HealthEngine.GUN_TEMP_THRESHOLDS.get(dt)
    
    def calculate_health_score(
        self,
        device_data: Dict,
        historical_data: List[Dict] = None,
        device_type: Optional[str] = None,
    ) -> Tuple[float, Dict]:
        """
        计算健康度分数
        
        Args:
            device_data: 当前设备数据
                - insulation_resistance: 绝缘电阻 (MΩ)
                - leakage_current: 漏电流 (mA)
                - temperature: 温度 (°C)
                - voltage: 电压 (V)
                - current: 电流 (A)
                - comm_success_rate: 通信成功率 (%)
                - plug_count: 插拔次数
            historical_data: 历史数据 (用于趋势分析)
            device_type: 设备类型（如 'pv_inverter', 'charger_dc' 等）
                        用于按设备类型使用不同的温度阈值
        
        Returns:
            (total_score, dimension_scores)
            异常时返回 (安全默认分, 各维度默认分)
        """
        if not isinstance(device_data, dict):
            logger.warning("calculate_health_score: device_data 非字典, 返回安全默认分")
            return (_SAFE_DEFAULT_SCORE, {k: _SAFE_DEFAULT_SCORE for k in self.WEIGHTS})
        
        scores = {}
        
        # 1. 电气安全评分 (30%)
        scores['electrical'] = self._score_electrical_safe(device_data)
        
        # 2. 热稳定性评分 (25%) — 按设备类型
        scores['thermal'] = self._score_thermal(device_data, device_type)
        
        # 3. 通信可靠性评分 (20%)
        scores['communication'] = self._score_communication(device_data)
        
        # 4. 电能质量评分 (15%)
        scores['power_quality'] = self._score_power_quality(device_data)
        
        # 5. 机械寿命评分 (10%) — 按设备类型
        scores['mechanical'] = self._score_mechanical(device_data, device_type)
        
        # 计算总分
        try:
            total = sum(scores[k] * self.WEIGHTS[k] for k in scores)
        except (TypeError, KeyError) as e:
            logger.warning("健康度总分计算异常: %s, 使用加权平均兜底", e)
            total = _SAFE_DEFAULT_SCORE
        
        # 趋势调整 (持续恶化额外扣分)
        if historical_data and len(historical_data) >= 3:
            trend = self._analyze_trend(historical_data)
            if trend < -5:  # 持续恶化
                total += trend  # 负值扣分
        
        return max(0, min(100, total)), scores
    
    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """安全转 float: None/非法类型 → default"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
        
    def _score_electrical_safe(self, data: Dict) -> float:
        """电气安全评分 (0-100)。异常返回安全默认分。"""
        try:
            score = 100
            
            # 绝缘电阻 (标准:>1MΩ)
            insulation = self._safe_float(data.get('insulation_resistance'), 10)
            if insulation < 0.5:
                score -= 50
            elif insulation < 1:
                score -= 30
            elif insulation < 5:
                score -= 10
            
            # 漏电流 (标准:<10mA)
            leakage = self._safe_float(data.get('leakage_current'), 0)
            if leakage > 30:
                score -= 40
            elif leakage > 20:
                score -= 25
            elif leakage > 10:
                score -= 10
            
            # 接地状态
            if data.get('ground_fault', False):
                score -= 50
            
            return max(0, score)
        except Exception as e:
            logger.warning("_score_electrical_safe 异常: %s, 返回默认分", e)
            return _SAFE_DEFAULT_SCORE
    
    def _score_thermal(self, data: Dict, device_type: Optional[str] = None) -> float:
        """热稳定性评分 (0-100)。异常返回安全默认分。"""
        try:
            score = 100
            
            # 获取当前设备类型的温度阈值
            threshold_warn, threshold_crit, threshold_severe, rise_warn = \
                self._get_thermal_thresholds(device_type)
            
            # 温度评分 (按设备类型区分)
            temp = self._safe_float(data.get('temperature'), 40)
            if temp > threshold_severe:
                score -= 50
            elif temp > threshold_crit:
                score -= 30
            elif temp > threshold_warn:
                score -= 15
            
            # 温升速率扣分
            temp_rise = self._safe_float(data.get('temp_rise_rate'), 0)
            if temp_rise > rise_warn:
                score -= 20
            
            return max(0, score)
        except Exception as e:
            logger.warning("_score_thermal 异常: %s, 返回默认分", e)
            return _SAFE_DEFAULT_SCORE
    
    def _score_communication(self, data: Dict) -> float:
        """通信可靠性评分 (0-100)。异常返回安全默认分。"""
        try:
            success_rate = self._safe_float(data.get('comm_success_rate'), 100)
            return max(0, min(100, success_rate))
        except Exception as e:
            logger.warning("_score_communication 异常: %s, 返回默认分", e)
            return _SAFE_DEFAULT_SCORE
    
    def _score_power_quality(self, data: Dict) -> float:
        """电能质量评分 (0-100)。异常返回安全默认分。"""
        try:
            score = 100
            
            # 电压偏差 (标准:±10%)
            voltage = self._safe_float(data.get('voltage'), 220)
            voltage_deviation = abs(voltage - 220) / 220 * 100
            if voltage_deviation > 15:
                score -= 40
            elif voltage_deviation > 10:
                score -= 20
            
            # 电流谐波
            thd = self._safe_float(data.get('current_thd'), 0)
            if thd > 20:
                score -= 30
            elif thd > 10:
                score -= 15
            
            return max(0, score)
        except Exception as e:
            logger.warning("_score_power_quality 异常: %s, 返回默认分", e)
            return _SAFE_DEFAULT_SCORE
    
    def _score_mechanical(self, data: Dict, device_type: Optional[str] = None) -> float:
        """机械寿命评分 (0-100)。异常返回安全默认分。"""
        try:
            score = 100
            
            # 插拔次数 (设计寿命:10000 次)
            plug_count = self._safe_float(data.get('plug_count'), 0)
            wear_rate = plug_count / 10000
            score -= wear_rate * 50
            
            # 枪头温度（仅充电桩相关设备才扣分）
            gun_temp_threshold = self._get_gun_temp_threshold(device_type)
            if gun_temp_threshold is not None:
                gun_temp = self._safe_float(data.get('gun_temperature'), 30)
                if gun_temp > gun_temp_threshold:
                    score -= 20
            
            return max(0, score)
        except Exception as e:
            logger.warning("_score_mechanical 异常: %s, 返回默认分", e)
            return _SAFE_DEFAULT_SCORE
    
    def _analyze_trend(self, historical_data: List[Dict]) -> float:
        """分析健康度趋势。异常或数据不足返回 0 (不扣分)。"""
        try:
            if not historical_data or len(historical_data) < 3:
                return 0
            
            scores = [self._safe_float(h.get('total_score'), 100) for h in historical_data[-7:]]
            if len(scores) < 2:
                return 0
            
            # 计算斜率
            delta = scores[-1] - scores[0]
            days = len(scores)
            if days == 0:
                return 0
            trend_per_day = delta / days
            
            # 持续恶化返回负值
            if trend_per_day < -2:
                return trend_per_day * 2  # 加倍扣分
            
            return 0
        except Exception as e:
            logger.warning("_analyze_trend 异常: %s, 返回 0", e)
            return 0
    
    def generate_alarm(self, device_id: int, score: float, dimensions: Dict) -> Optional[Dict]:
        """生成告警。异常返回 None (不生成告警)。"""
        try:
            if score >= self.THRESHOLDS['healthy']:
                return None
            
            level = 'warning' if score >= self.THRESHOLDS['warning'] else 'critical'
            
            # 找出最差的维度
            if not dimensions:
                return {
                    'device_id': device_id,
                    'alarm_type': '健康度异常',
                    'level': level,
                    'content': f'健康度{score:.1f}分',
                }
            worst_dim = min(dimensions, key=dimensions.get)
            
            alarm_types = {
                'electrical': '电气安全异常',
                'thermal': '温度异常',
                'communication': '通信故障',
                'power_quality': '电能质量异常',
                'mechanical': '机械磨损',
            }
            
            return {
                'device_id': device_id,
                'alarm_type': alarm_types.get(worst_dim, '健康度异常'),
                'level': level,
                'content': f'健康度{score:.1f}分，{alarm_types.get(worst_dim)}得分{dimensions[worst_dim]:.1f}',
            }
        except Exception as e:
            logger.warning("generate_alarm 异常: %s, 返回 None", e)
            return None
    
    def predict_remaining_life(self, device_data: Dict, historical: List[Dict]) -> int:
        """
        预测剩余寿命 (天)
        简化版：基于健康度趋势推算。异常返回 365 (默认安全值)。
        """
        try:
            if not historical or len(historical) < 7:
                return 365  # 默认 1 年
            
            scores = [self._safe_float(h.get('total_score'), 100) for h in historical]
            delta = scores[-1] - scores[0]
            days = len(scores)
            if days == 0:
                return 365
            
            if delta >= 0:
                return 365  # 稳定或改善
            
            # 推算到 0 分的天数
            current_score = scores[-1]
            decline_rate = abs(delta) / days
            if decline_rate == 0:
                return 365
            remaining_days = int(current_score / decline_rate)
            
            return min(365, max(0, remaining_days))
        except Exception as e:
            logger.warning("predict_remaining_life 异常: %s, 返回 365", e)
            return 365


# 单例
health_engine = HealthEngine()
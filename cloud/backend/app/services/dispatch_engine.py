"""
智能派单引擎
多因子加权算法：地理位置 + 技能匹配 + 负载 + 绩效 + 备件
"""
import logging
from typing import Dict, List
import math

logger = logging.getLogger(__name__)


class DispatchEngine:
    """
    智能派单引擎

    评分因子:
    - 地理位置 (30%): 距离越近分数越高
    - 技能匹配 (25%): 擅长修的设备类型
    - 当前负载 (20%): 手头工单越少越好
    - 历史绩效 (15%): 完成率/好评率/平均耗时
    - 备件匹配 (10%): 是否携带所需备件
    """

    WEIGHTS = {
        'distance': 0.30,
        'skill': 0.25,
        'load': 0.20,
        'performance': 0.15,
        'parts': 0.10,
    }

    def __init__(self):
        pass

    def dispatch(self, workorder: Dict, engineers: List[Dict], station_location: Dict) -> Dict:
        """
        派单入口：计算最佳工程师并返回派单结果

        Args:
            workorder: 工单信息
            engineers: 工程师列表
            station_location: 站点位置

        Returns:
            包含派单详细信息的字典
        """
        try:
            result = self.calculate_best_engineer(workorder, engineers, station_location)
            if result is None:
                return {
                    "success": False,
                    "message": "没有可用的工程师",
                    "engineer": None,
                    "score": 0,
                }
            return {
                "success": True,
                "message": "派单成功",
                "engineer": result["engineer"],
                "score": result["total_score"],
                "score_details": result["score_details"],
            }
        except Exception:
            logger.exception(
                "dispatch 派单异常 workorder=%s engineers=%s",
                workorder, engineers,
            )
            return {
                "success": False,
                "message": "派单异常，请稍后重试",
                "engineer": None,
                "score": 0,
            }

    def calculate_best_engineer(
        self,
        workorder: Dict,
        engineers: List[Dict],
        station_location: Dict
    ) -> Dict:
        """
        计算最佳工程师

        Args:
            workorder: 工单信息
                - device_type: 设备类型
                - level: 工单级别
                - required_parts: 所需备件
            engineers: 工程师列表
                - id, name, location, skills, current_load, performance, parts
            station_location: 站点位置
                - lat, lon

        Returns:
            best_engineer with score details
        """
        try:
            scored_engineers = []

            for engineer in (engineers or []):
                # 跳过不可用的工程师 / 非字典脏数据
                if not isinstance(engineer, dict) or engineer.get('status') != 'active':
                    continue

                try:
                    score_details = {}

                    # 1. 地理位置评分 (30%)
                    score_details['distance'] = self._score_distance(
                        engineer.get('location', {}),
                        station_location
                    )

                    # 2. 技能匹配评分 (25%)
                    score_details['skill'] = self._score_skill(
                        engineer.get('skills', []),
                        workorder.get('device_type')
                    )

                    # 3. 当前负载评分 (20%)
                    score_details['load'] = self._score_load(
                        engineer.get('current_load', 0)
                    )

                    # 4. 历史绩效评分 (15%)
                    score_details['performance'] = self._score_performance(
                        engineer.get('performance', {})
                    )

                    # 5. 备件匹配评分 (10%)
                    score_details['parts'] = self._score_parts(
                        engineer.get('parts', []),
                        workorder.get('required_parts', [])
                    )

                    # 计算总分
                    total = sum(
                        score_details[k] * self.WEIGHTS[k]
                        for k in score_details
                    )

                    scored_engineers.append({
                        'engineer': engineer,
                        'total_score': total,
                        'score_details': score_details,
                    })
                except Exception:
                    # 单个工程师评分失败不影响整体派单，跳过该工程师
                    logger.exception(
                        "工程师评分失败，跳过该工程师 engineer=%s",
                        engineer.get('id'),
                    )
                    continue

            # 排序并返回最佳
            if not scored_engineers:
                return None

            scored_engineers.sort(key=lambda x: x['total_score'], reverse=True)
            return scored_engineers[0]
        except Exception:
            logger.exception(
                "calculate_best_engineer 计算异常 workorder=%s",
                workorder,
            )
            return None

    def _score_distance(self, engineer_loc: Dict, station_loc: Dict) -> float:
        """
        地理位置评分 (0-100)
        使用 Haversine 公式计算距离
        """
        if not engineer_loc or not station_loc:
            return 50  # 默认中等分数

        # lat/lon 任一缺失或为 None → 无法定位,返回中性分,避免缺省 0 落到(0,0)几内亚湾
        lat1, lon1 = engineer_loc.get('lat'), engineer_loc.get('lon')
        lat2, lon2 = station_loc.get('lat'), station_loc.get('lon')
        if not all(isinstance(v, (int, float)) for v in (lat1, lon1, lat2, lon2)):
            return 50

        # 计算距离 (km)
        R = 6371  # 地球半径
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat/2) ** 2 +
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
            math.sin(dlon/2) ** 2
        )
        # clamp 到 [0, 1],防止浮点误差令 sqrt(1-a) 取负抛 ValueError
        a = min(1.0, max(0.0, a))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c

        # 距离评分：0km=100 分，50km+=0 分
        score = max(0, 100 - distance * 2)
        return score

    def _score_skill(self, skills: List[str], device_type: str) -> float:
        """技能匹配评分 (0-100)"""
        if not skills or not device_type:
            return 50

        # 技能映射
        skill_map = {
            'charger_dc': ['充电桩', '直流充电', '高压电工'],
            'charger_ac': ['充电桩', '交流充电'],
            'pv_inverter': ['光伏', '逆变器', '高压电工'],
            'battery': ['储能', '电池', 'BMS'],
        }

        required_skills = skill_map.get(device_type, [])
        if not required_skills:
            return 70

        # 计算匹配度
        matched = sum(1 for s in required_skills if s in skills)
        match_rate = matched / len(required_skills) if required_skills else 0.0

        return min(100, match_rate * 80 + 20)

    def _score_load(self, current_load: int) -> float:
        """
        负载评分 (0-100)
        工单越少分数越高
        """
        # 非数值脏数据(None/str)按中性分,避免 None*10 → TypeError
        if not isinstance(current_load, (int, float)) or isinstance(current_load, bool):
            return 50
        # 0 单=100 分，10 单+=0 分
        score = max(0, 100 - current_load * 10)
        return score

    def _score_performance(self, performance: Dict) -> float:
        """
        绩效评分 (0-100)
        完成率 + 好评率 + 平均耗时
        """
        if not performance:
            return 60

        # 数值字段守卫:非数值(含 None/str)按默认值,避免运算崩溃或脏数据放大
        def _num(val, default):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return default
            return val

        completion_rate = _num(performance.get('completion_rate'), 80)  # %
        satisfaction = _num(performance.get('satisfaction'), 4.0)  # 5 分制
        avg_hours = _num(performance.get('avg_hours'), 4)  # 平均耗时

        # 完成率 (40 分)
        score1 = completion_rate * 0.4

        # 好评率 (40 分)
        score2 = (satisfaction / 5) * 40

        # 耗时 (20 分) - 越快越好;avg_hours 为负时 clamp 上限,防止超分
        score3 = max(0, min(20, 20 - avg_hours))

        return min(100, score1 + score2 + score3)

    def _score_parts(self, parts: List[str], required: List[str]) -> float:
        """
        备件匹配评分 (0-100)
        携带所需备件越多分数越高
        """
        if not required:
            return 100  # 不需要备件

        if not parts:
            return 30  # 没带备件

        # 计算匹配度
        matched = sum(1 for p in required if p in parts)
        match_rate = matched / len(required) if required else 0.0

        return 30 + match_rate * 70


# 单例
dispatch_engine = DispatchEngine()

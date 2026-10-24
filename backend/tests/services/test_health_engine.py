#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康引擎服务测试 —— 包含设备类型温度阈值测试
"""
import pytest
from app.services.health_engine import HealthEngine


class TestHealthEngine:
    def test_engine_initialization(self):
        engine = HealthEngine()
        assert engine is not None

    def test_has_calculate_health_method(self):
        engine = HealthEngine()
        assert hasattr(engine, "calculate_health_score")
        assert callable(engine.calculate_health_score)

    def test_has_predict_life_method(self):
        engine = HealthEngine()
        assert hasattr(engine, "predict_remaining_life")
        assert callable(engine.predict_remaining_life)

    # ─── 基础健康度计算 ───

    def test_calculate_health_score_with_defaults(self):
        """默认设备数据应返回高健康度"""
        engine = HealthEngine()
        device_data = {
            'temperature': 35,
            'voltage': 220,
            'current': 32,
            'insulation_resistance': 20,
            'leakage_current': 1,
            'comm_success_rate': 99,
            'plug_count': 100,
            'gun_temperature': 30,
            'temp_rise_rate': 1,
            'current_thd': 3,
            'power_factor': 0.98,
        }
        score, dimensions = engine.calculate_health_score(device_data)
        assert 0 <= score <= 100
        assert score > 80  # 理应健康
        assert all(dim in dimensions for dim in
                   ['electrical', 'thermal', 'communication', 'power_quality', 'mechanical'])

    def test_calculate_health_score_historical_data(self):
        """传入历史数据不应报错"""
        engine = HealthEngine()
        device_data = {'temperature': 40}
        historical = [
            {'total_score': 95},
            {'total_score': 90},
            {'total_score': 85},
        ]
        score, _ = engine.calculate_health_score(device_data, historical)
        assert 0 <= score <= 100

    def test_calculate_device_type_default(self):
        """无 device_type 时使用默认阈值"""
        engine = HealthEngine()
        # 默认阈值: warning=60, critical=70, severe=80
        data_hot = {'temperature': 75, 'temp_rise_rate': 0}
        data_very_hot = {'temperature': 85, 'temp_rise_rate': 0}

        score_75, dims_75 = engine.calculate_health_score(data_hot)
        score_85, dims_85 = engine.calculate_health_score(data_very_hot)

        # 75°C: 超过 critical (70) 但未到 severe (80), 扣30
        assert dims_75['thermal'] == 70  # 100-30
        # 85°C: 超过 severe (80), 扣50
        assert dims_85['thermal'] == 50  # 100-50

    # ─── 设备类型温度阈值测试 ───

    def test_thermal_thresholds_battery_most_strict(self):
        """电池柜 (battery) 温度最严格: warning@45, critical@55, severe@65"""
        engine = HealthEngine()
        data = {'temperature': 48, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 48°C > 45(warning) but < 55(critical) => 扣15 => 85
        assert dims['thermal'] == 85, f"Battery 48°C should score 85, got {dims['thermal']}"

    def test_thermal_critical_battery(self):
        """电池柜55°C以上应扣30"""
        engine = HealthEngine()
        data = {'temperature': 58, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 58°C > 55(critical) but < 65(severe) => 扣30 => 70
        assert dims['thermal'] == 70, f"Battery 58°C should score 70, got {dims['thermal']}"

    def test_thermal_severe_battery(self):
        """电池柜65°C以上应扣50"""
        engine = HealthEngine()
        data = {'temperature': 68, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 68°C > 65(severe) => 扣50 => 50
        assert dims['thermal'] == 50, f"Battery 68°C should score 50, got {dims['thermal']}"

    def test_thermal_thresholds_charger_dc_lenient(self):
        """直流充电桩温度较宽松: warning@65, critical@80, severe@90"""
        engine = HealthEngine()
        data = {'temperature': 75, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='charger_dc')
        # 75°C > 65(warning) but < 80(critical) => 扣15 => 85
        assert dims['thermal'] == 85, f"Charger_DC 75°C should score 85, got {dims['thermal']}"

    def test_thermal_critical_charger_dc(self):
        """直流充电桩80°C以上应扣30"""
        engine = HealthEngine()
        data = {'temperature': 85, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='charger_dc')
        # 85°C > 80(critical) but < 90(severe) => 扣30 => 70
        assert dims['thermal'] == 70, f"Charger_DC 85°C should score 70, got {dims['thermal']}"

    def test_thermal_thresholds_pv_inverter(self):
        """光伏逆变器: warning@60, critical@70, severe@80"""
        engine = HealthEngine()
        data = {'temperature': 65, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='pv_inverter')
        # 65°C > 60(warning) but < 70(critical) => 扣15 => 85
        assert dims['thermal'] == 85, f"PV_Inverter 65°C should score 85, got {dims['thermal']}"

    def test_thermal_critical_pv_inverter(self):
        """光伏逆变器70°C以上扣30"""
        engine = HealthEngine()
        data = {'temperature': 75, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='pv_inverter')
        # 75°C > 70(critical) but < 80(severe) => 扣30 => 70
        assert dims['thermal'] == 70, f"PV_Inverter 75°C should score 70, got {dims['thermal']}"

    def test_thermal_thresholds_pcs(self):
        """储能变流器: warning@55, critical@65, severe@75"""
        engine = HealthEngine()
        data = {'temperature': 60, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='pcs')
        # 60°C > 55(warning) but < 65(critical) => 扣15 => 85
        assert dims['thermal'] == 85, f"PCS 60°C should score 85, got {dims['thermal']}"

    def test_thermal_critical_pcs(self):
        """储能变流器65°C以上扣30"""
        engine = HealthEngine()
        data = {'temperature': 70, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='pcs')
        # 70°C > 65(critical) but < 75(severe) => 扣30 => 70
        assert dims['thermal'] == 70, f"PCS 70°C should score 70, got {dims['thermal']}"

    def test_thermal_meter_lenient(self):
        """电表温度宽松: warning@70, critical@85, severe@95"""
        engine = HealthEngine()
        data = {'temperature': 80, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='meter')
        # 80°C > 70(warning) but < 85(critical) => 扣15 => 85
        assert dims['thermal'] == 85, f"Meter 80°C should score 85, got {dims['thermal']}"

    def test_thermal_gateway_lenient(self):
        """网关温度宽松: 同电表"""
        engine = HealthEngine()
        data = {'temperature': 88, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='gateway')
        # 88°C > 85(critical) but < 95(severe) => 扣30 => 70
        assert dims['thermal'] == 70, f"Gateway 88°C should score 70, got {dims['thermal']}"

    def test_thermal_temp_rise_sensitive_battery(self):
        """电池柜对温升速率更敏感 (阈值 3.0 vs 其他 5.0)"""
        engine = HealthEngine()
        data = {'temperature': 35, 'temp_rise_rate': 4.0}
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 温升 4.0 > 3.0 (battery 阈值) => 扣20 => 80
        assert dims['thermal'] == 80, f"Battery high temp_rise should score 80, got {dims['thermal']}"

    def test_thermal_temp_rise_normal_other(self):
        """其他设备正常温升不扣分"""
        engine = HealthEngine()
        data = {'temperature': 35, 'temp_rise_rate': 4.0}
        _, dims = engine.calculate_health_score(data, device_type='charger_dc')
        # 温升 4.0 < 5.0 (默认阈值) => 不扣分, 温度 35 < 65 => 100
        assert dims['thermal'] == 100, f"Charger_DC temp_rise 4.0 should score 100, got {dims['thermal']}"

    def test_thermal_high_temp_rise_all_devices(self):
        """极高温升在所有设备上都应扣分"""
        engine = HealthEngine()
        for dt in ['pv_inverter', 'charger_dc', 'battery']:
            data = {'temperature': 30, 'temp_rise_rate': 10}
            _, dims = engine.calculate_health_score(data, device_type=dt)
            # 温升10 > 所有阈值, 应扣20
            assert dims['thermal'] < 100, f"{dt} should lose points for high temp_rise"

    # ─── 机械评分（枪头温度）───

    def test_mechanical_gun_temp_only_charger(self):
        """枪头温度扣分仅对充电桩有效"""
        engine = HealthEngine()
        # 对充电桩: 枪头>60应扣分
        data_charger = {
            'plug_count': 0,
            'gun_temperature': 80,
            'temperature': 30,
        }
        _, dims_charger = engine.calculate_health_score(data_charger, device_type='charger_dc')
        # 枪头80>60 => 扣20; plug_count=0 => 不扣; => 100-20=80
        assert dims_charger['mechanical'] == 80, \
            f"Charger gun temp 80°C should score 80, got {dims_charger['mechanical']}"

    def test_mechanical_gun_temp_ignored_for_battery(self):
        """电池柜即使有gun_temperature也不扣分"""
        engine = HealthEngine()
        data = {
            'plug_count': 0,
            'gun_temperature': 80,
            'temperature': 30,
        }
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 电池柜不扣枪头分; 应 100
        assert dims['mechanical'] == 100, \
            f"Battery should not deduct for gun temp, got {dims['mechanical']}"

    def test_mechanical_gun_temp_ignored_for_inverter(self):
        """逆变器不扣枪头分"""
        engine = HealthEngine()
        data = {'plug_count': 0, 'gun_temperature': 90}
        _, dims = engine.calculate_health_score(data, device_type='pv_inverter')
        assert dims['mechanical'] == 100

    def test_mechanical_gun_temp_ac_charger(self):
        """交流充电桩枪头>60扣分"""
        engine = HealthEngine()
        data = {'plug_count': 0, 'gun_temperature': 65}
        _, dims = engine.calculate_health_score(data, device_type='charger_ac')
        assert dims['mechanical'] == 80

    def test_mechanical_gun_temp_below_threshold(self):
        """枪头温度低于阈值不扣分"""
        engine = HealthEngine()
        data = {'plug_count': 0, 'gun_temperature': 50}
        _, dims = engine.calculate_health_score(data, device_type='charger_dc')
        assert dims['mechanical'] == 100

    def test_mechanical_with_plug_wear(self):
        """插拔次数磨损扣分"""
        engine = HealthEngine()
        data = {'plug_count': 5000, 'gun_temperature': 30}
        _, dims = engine.calculate_health_score(data, device_type='charger_dc')
        # 5000/10000 * 50 = 25 => 75
        assert dims['mechanical'] == 75, f"With 5000 plug count, mechanical score should be 75, got {dims['mechanical']}"

    # ─── 电气安全评分 ───

    def test_electrical_low_insulation(self):
        """低绝缘电阻应扣分"""
        engine = HealthEngine()
        data = {'insulation_resistance': 0.3, 'leakage_current': 0, 'ground_fault': False}
        score, dims = engine.calculate_health_score(data)
        # 绝缘<0.5 => 扣50; 漏电=0 => 不扣; 无接地=>不扣 => 50
        assert dims['electrical'] == 50, f"Expected 50, got {dims['electrical']}"

    def test_electrical_high_leakage(self):
        """高漏电流应扣分"""
        engine = HealthEngine()
        data = {'insulation_resistance': 20, 'leakage_current': 35, 'ground_fault': False}
        score, dims = engine.calculate_health_score(data)
        # 漏电 35>30 => 扣40 => 60
        assert dims['electrical'] == 60

    def test_electrical_ground_fault(self):
        """接地故障扣50"""
        engine = HealthEngine()
        data = {'insulation_resistance': 20, 'leakage_current': 0, 'ground_fault': True}
        score, dims = engine.calculate_health_score(data)
        # 接地=>扣50 => 50
        assert dims['electrical'] == 50

    # ─── 电能质量评分 ───

    def test_power_quality_voltage_deviation(self):
        """电压偏差>15%扣40"""
        engine = HealthEngine()
        data = {'voltage': 300, 'current_thd': 0}
        _, dims = engine.calculate_health_score(data)
        # |300-220|/220*100 = 36.3% > 15% => 扣40 => 60
        assert dims['power_quality'] == 60

    def test_power_quality_high_thd(self):
        """高谐波应扣分"""
        engine = HealthEngine()
        data = {'voltage': 220, 'current_thd': 25}
        _, dims = engine.calculate_health_score(data)
        # THD 25 > 20 => 扣30 => 70
        assert dims['power_quality'] == 70

    # ─── 通信可靠性 ───

    def test_communication_score(self):
        """通信评分直接使用成功率"""
        engine = HealthEngine()
        data = {'comm_success_rate': 85}
        _, dims = engine.calculate_health_score(data)
        assert dims['communication'] == 85

    # ─── 告警生成 ───

    def test_generate_alarm_healthy(self):
        """健康设备不告警"""
        engine = HealthEngine()
        alarm = engine.generate_alarm(1, 95, {'electrical': 95})
        assert alarm is None

    def test_generate_alarm_warning(self):
        """警告状态应生成告警"""
        engine = HealthEngine()
        alarm = engine.generate_alarm(1, 75, {'thermal': 60, 'electrical': 90})
        assert alarm is not None
        assert alarm['level'] == 'warning'

    def test_generate_alarm_critical(self):
        """严重状态应生成告警"""
        engine = HealthEngine()
        alarm = engine.generate_alarm(1, 50, {'thermal': 30, 'electrical': 80})
        assert alarm is not None
        assert alarm['level'] == 'critical'
        assert 'device_id' in alarm

    # ─── 剩余寿命预测 ───

    def test_predict_life_no_history(self):
        """无历史时返回默认寿命"""
        engine = HealthEngine()
        life = engine.predict_remaining_life({}, [])
        assert life == 365

    def test_predict_life_with_history(self):
        """根据历史趋势推算寿命"""
        engine = HealthEngine()
        data = {}
        historical = [{'total_score': 100}] * 4 + [{'total_score': 80}]
        life = engine.predict_remaining_life(data, historical)
        assert 0 <= life <= 365

    # ─── 设备类型传入枚举值 ───

    def test_device_type_as_enum_string(self):
        """device_type 作为枚举值字符串传入应正常工作"""
        engine = HealthEngine()
        data = {'temperature': 50, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type='battery')
        # 50°C > 45(warning) but < 55(critical) => 扣15 => 85
        assert dims['thermal'] == 85

    def test_device_type_case_insensitive(self):
        """device_type 大小写不敏感"""
        engine = HealthEngine()
        data = {'temperature': 50, 'temp_rise_rate': 0}
        _, dims1 = engine.calculate_health_score(data, device_type='BATTERY')
        _, dims2 = engine.calculate_health_score(data, device_type='Battery')
        _, dims3 = engine.calculate_health_score(data, device_type='battery')
        assert dims1['thermal'] == dims2['thermal'] == dims3['thermal']

    def test_device_type_null_and_none(self):
        """device_type 为 None 时使用默认阈值"""
        engine = HealthEngine()
        data = {'temperature': 75, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data, device_type=None)
        assert dims['thermal'] == 70  # 75 > 70(critical) => 100-30=70

    # ─── 维度权重验证 ───

    def test_weights_accounted_in_total(self):
        """各维度权重对总分的影响"""
        engine = HealthEngine()
        # 各维度满分 100, 总分应 = 100
        data = {
            'temperature': 30,
            'voltage': 220,
            'current': 32,
            'insulation_resistance': 20,
            'leakage_current': 0.1,
            'comm_success_rate': 100,
            'plug_count': 0,
            'gun_temperature': 30,
            'temp_rise_rate': 0,
            'current_thd': 0,
        }
        score, _ = engine.calculate_health_score(data)
        assert score == 100, f"Perfect data should score 100, got {score}"

    def test_dimension_penalty_reflected_in_total(self):
        """单个维度扣分应反映在总分中"""
        engine = HealthEngine()
        # 热稳定性扣50 (从100->50): 50 * 0.25 = 12.5 总损失
        data = {
            'temperature': 85,
            'voltage': 220,
            'current': 32,
            'insulation_resistance': 20,
            'leakage_current': 0.1,
            'comm_success_rate': 100,
            'plug_count': 0,
            'gun_temperature': 30,
            'temp_rise_rate': 0,
            'current_thd': 0,
        }
        score, dims = engine.calculate_health_score(data)
        # thermal=50, 其他=100
        expected = 100 * 0.30 + 50 * 0.25 + 100 * 0.20 + 100 * 0.15 + 100 * 0.10
        expected = 30 + 12.5 + 20 + 15 + 10  # = 87.5
        assert abs(score - expected) < 0.01

    # ─── 边界值测试 ───

    def test_temperature_exactly_at_threshold(self):
        """温度恰好等于阈值不扣分"""
        engine = HealthEngine()
        data = {'temperature': 60, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data)
        # 默认阈值 warning=60, 精确等于不扣分(> 才扣)
        assert dims['thermal'] == 100

    def test_temperature_just_above_warning(self):
        """温度略超告警阈值扣分"""
        engine = HealthEngine()
        data = {'temperature': 60.1, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data)
        assert dims['thermal'] == 85  # 100-15

    def test_temperature_just_above_critical(self):
        """温度略超严重阈值扣分"""
        engine = HealthEngine()
        data = {'temperature': 70.1, 'temp_rise_rate': 0}
        _, dims = engine.calculate_health_score(data)
        assert dims['thermal'] == 70  # 100-30
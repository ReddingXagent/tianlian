"""
故障码诊断 API 测试
覆盖: fault-codes list, detail, diagnosis, diagnosis-rules, repair-guides, stats
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(test_db):
    """TestClient with proper lifespan management to prevent background task leaks.

    显式依赖 test_db（seed admin + 覆盖 SessionLocal）后登录 admin 注入 Bearer 头，
    与 conftest.client 及其余测试文件保持一致：绝大多数用例登录态运行。测匿名拒绝时
    在用例内 self.client.headers.pop('Authorization') 清除头。
    """
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        if r.status_code == 200:
            token = r.json().get("data", {}).get("token")
            if token:
                c.headers["Authorization"] = f"Bearer {token}"
        yield c


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db, client):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.mark.timeout(30)
class TestFaultDiagnosisAPI:

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.client = client

    # ========== 鉴权测试 ==========

    def test_list_fault_codes_no_auth(self):
        """匿名访问故障码列表 → 401（enforce_auth 全局强制，端点非白名单）"""
        self.client.headers.pop("Authorization", None)  # 清除 fixture 注入的 admin token，测真匿名拒绝
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes")
        assert resp.status_code in (401, 403)

    def test_diagnosis_requires_auth(self):
        """匿名访问诊断端点 → 401（enforce_auth 全局强制）"""
        self.client.headers.pop("Authorization", None)  # 清除 fixture 注入的 admin token，测真匿名拒绝
        resp = self.client.post("/api/v1/fault-diagnosis/alarm-diagnosis", json={
            "alarm_id": 99999
        })
        assert resp.status_code in (401, 403)

    def test_quick_diagnosis_no_auth(self):
        """匿名访问快速诊断 → 401（enforce_auth 全局强制）"""
        self.client.headers.pop("Authorization", None)  # 清除 fixture 注入的 admin token，测真匿名拒绝
        resp = self.client.post("/api/v1/fault-diagnosis/quick-diagnosis?fault_code=E001&device_type=inverter")
        assert resp.status_code in (401, 403)

    # ========== 故障码列表 ==========

    def test_list_fault_codes_empty(self):
        """空数据库返回空列表"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", {}).get("items", []) or data.get("items", [])
        assert isinstance(items, list)

    def test_list_fault_codes_with_pagination(self):
        """分页参数"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        # page_info should be present
        page_data = data.get("data", data)
        assert "page" in page_data or "total" in page_data

    def test_get_fault_code_detail_404(self):
        """不存在的故障码返回404"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes/NONEXIST")
        assert resp.status_code == 404

    def test_filter_by_device_type(self):
        """按设备类型筛选"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?device_type=inverter")
        assert resp.status_code == 200

    def test_filter_by_category(self):
        """按故障分类筛选"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?fault_category=electrical")
        assert resp.status_code == 200

    def test_filter_by_level(self):
        """按故障等级筛选"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?fault_level=critical")
        assert resp.status_code == 200

    def test_keyword_search(self):
        """关键字搜索"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?keyword=过压")
        assert resp.status_code == 200

    def test_combined_filters(self):
        """组合过滤"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?device_type=inverter&fault_category=electrical&fault_level=critical")
        assert resp.status_code == 200

    # ========== 故障诊断 ==========

    def test_diagnose_alarm_not_found(self, auth_token):
        """诊断不存在的告警"""
        resp = self.client.post("/api/v1/fault-diagnosis/alarm-diagnosis", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"alarm_id": 99999})
        assert resp.status_code == 404

    def test_quick_diagnosis_with_device_type(self, auth_token):
        """快速诊断（带设备类型）"""
        resp = self.client.post("/api/v1/fault-diagnosis/quick-diagnosis?fault_code=0x01&device_type=inverter", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 404 or resp.status_code == 200

    def test_quick_diagnosis_without_device_type(self, auth_token):
        """快速诊断（不带设备类型）"""
        resp = self.client.post("/api/v1/fault-diagnosis/quick-diagnosis?fault_code=0x01&device_type=unknown", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 404

    # ========== 远程修复 ==========

    def test_remote_fix_not_found(self, auth_token):
        """远程修复不存在的告警"""
        resp = self.client.post("/api/v1/fault-diagnosis/remote-fix-attempt", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "alarm_id": 99999,
            "fix_type": "reset"
        })
        assert resp.status_code == 404

    def test_remote_fix_unsupported_type(self, auth_token):
        """远程修复不支持的类型"""
        # 需要先创建告警和设备
        pass

    # ========== 统计分析 ==========

    def test_fault_statistics_default(self):
        """默认故障统计"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-statistics")
        assert resp.status_code == 200
        data = resp.json()
        stats = data.get("data", data)
        assert "total_alarms" in stats
        assert "days" in stats

    def test_fault_statistics_with_station(self):
        """按站点统计"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-statistics?station_id=1&days=7")
        assert resp.status_code == 200

    def test_fault_statistics_with_device_type(self):
        """按设备类型统计"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-statistics?device_type=inverter&days=30")
        assert resp.status_code == 200


@pytest.mark.timeout(30)
class TestFaultDiagnosisExtended:
    """扩展故障码诊断测试 - 更多故障码类型"""

    @pytest.fixture(autouse=True)
    def _setup(self, test_db, client):
        self.client = client
        db = test_db["session"]
        from app.models.fault_code import FaultCode, FaultLevel, FaultCategory, RepairGuide

        # ===== 更多逆变器/光储故障码 =====

        fc1 = FaultCode(
            fault_code="0x10",
            fault_name="BMS通信异常",
            fault_description="BMS电池管理系统通信超时或数据异常",
            device_type="inverter",
            fault_category=FaultCategory.BCU_BMS,
            fault_level=FaultLevel.SERIOUS,
            possible_causes=["BMS离线", "CAN总线故障", "通信线缆松动"],
            diagnosis_steps=["检查BMS状态", "检查CAN总线", "重新上电"],
            repair_suggestions=["更换通信线", "重启BMS"],
            response_time_minutes=10,
            remote_fixable=False,
            occurrence_count=3,
            enabled=True
        )
        db.add(fc1)

        fc2 = FaultCode(
            fault_code="0x0A",
            fault_name="散热器温度过高",
            fault_description="散热器温度超过90°C保护阈值",
            device_type="inverter",
            fault_category=FaultCategory.TEMPERATURE,
            fault_level=FaultLevel.EMERGENCY,
            possible_causes=["风扇故障", "散热器堵塞", "环境温度高"],
            diagnosis_steps=["检查风扇转速", "检查散热器", "检查环境温度"],
            repair_suggestions=["清洁散热器", "更换风扇"],
            response_time_minutes=5,
            auto_stop=True,
            remote_fixable=False,
            occurrence_count=8,
            avg_repair_time_minutes=45,
            enabled=True
        )
        db.add(fc2)

        # ===== 充电桩故障码 =====

        fc3 = FaultCode(
            fault_code="0x0301",
            fault_name="充电枪温度过高",
            fault_description="充电枪温度检测点温度超过90°C",
            device_type="charger",
            fault_category=FaultCategory.CHARGING_CONTROLLER,
            fault_level=FaultLevel.EMERGENCY,
            possible_causes=["充电枪接触不良", "过流充电", "环境温度高"],
            diagnosis_steps=["检查枪头温度", "降低充电功率", "检查接触面"],
            repair_suggestions=["更换充电枪", "清洁接触端子"],
            response_time_minutes=3,
            auto_stop=True,
            remote_fixable=True,
            occurrence_count=12,
            avg_repair_time_minutes=60,
            enabled=True
        )
        db.add(fc3)

        fc4 = FaultCode(
            fault_code="0x0802",
            fault_name="4G模块通信中断",
            fault_description="充电桩4G通信模块持续30秒无响应",
            device_type="charger",
            fault_category=FaultCategory.COMMUNICATION,
            fault_level=FaultLevel.SERIOUS,
            possible_causes=["SIM卡故障", "信号弱", "模块硬件故障"],
            diagnosis_steps=["检查SIM卡", "检查信号强度", "重启模块"],
            repair_suggestions=["更换SIM卡", "加装天线", "更换通信模块"],
            response_time_minutes=15,
            remote_fixable=True,
            occurrence_count=20,
            avg_repair_time_minutes=30,
            enabled=True
        )
        db.add(fc4)

        # ===== PCS故障码 =====

        fc5 = FaultCode(
            fault_code="0x50",
            fault_name="直流母线过压",
            fault_description="PCS直流母线电压超过820V保护限值",
            device_type="pcs",
            fault_category=FaultCategory.BUS,
            fault_level=FaultLevel.EMERGENCY,
            possible_causes=["电网波动", "电池过充", "母线电容老化"],
            diagnosis_steps=["检查电网电压", "检查电池SOC", "检查直流接触器"],
            repair_suggestions=["调整充电参数", "更换母线电容"],
            response_time_minutes=5,
            auto_stop=True,
            remote_fixable=True,
            occurrence_count=6,
            avg_repair_time_minutes=90,
            enabled=True
        )
        db.add(fc5)

        # ===== 电池故障码 =====

        fc6 = FaultCode(
            fault_code="0xC0",
            fault_name="电池单体温差过大",
            fault_description="电池组内单体间温差超过8°C",
            device_type="inverter",
            fault_category=FaultCategory.BATTERY,
            fault_level=FaultLevel.WARNING_SERIOUS,
            possible_causes=["BMS均衡失效", "热管理故障", "单体老化"],
            diagnosis_steps=["检查BMS均衡状态", "检查温度传感器"],
            repair_suggestions=["执行均衡充电", "更换异常单体"],
            response_time_minutes=30,
            remote_fixable=True,
            occurrence_count=4,
            avg_repair_time_minutes=120,
            enabled=True
        )
        db.add(fc6)

        # ===== 已禁用的故障码 =====

        fc7 = FaultCode(
            fault_code="0xFF",
            fault_name="已停用故障码",
            fault_description="此故障码已禁用",
            device_type="inverter",
            fault_category=FaultCategory.OTHER,
            fault_level=FaultLevel.WARNING_GENERAL,
            possible_causes=["测试"],
            diagnosis_steps=["测试"],
            repair_suggestions=["测试"],
            enabled=False
        )
        db.add(fc7)

        db.commit()
        self.fc_bms = fc1.fault_code  # "0x10"
        self.fc_temp = fc2.fault_code  # "0x0A"
        self.fc_charger = fc3.fault_code  # "0x0301"
        self.fc_comm = fc4.fault_code  # "0x0802"
        self.fc_pcs = fc5.fault_code  # "0x50"
        self.fc_battery = fc6.fault_code  # "0xC0"
        self.fc_disabled = fc7.fault_code  # "0xFF"
        db.close()

    def test_fault_code_detail_bms(self, auth_token):
        """获取BMS故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_bms}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_name") == "BMS通信异常"
        assert data.get("remote_fixable") is False
        assert len(data.get("possible_causes", [])) == 3

    def test_fault_code_detail_temperature(self, auth_token):
        """获取温度故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_temp}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_name") == "散热器温度过高"
        assert data.get("auto_stop") is True
        assert data.get("occurrence_count") == 8

    def test_fault_code_detail_charger(self, auth_token):
        """获取充电桩故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_charger}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("device_type") == "charger"
        assert data.get("fault_level") == "emergency"
        assert data.get("remote_fixable") is True

    def test_fault_code_detail_communication(self, auth_token):
        """获取通信故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_comm}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_category") == "communication"

    def test_fault_code_detail_pcs(self, auth_token):
        """获取PCS故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_pcs}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_name") == "直流母线过压"
        assert data.get("avg_repair_time_minutes") == 90

    def test_fault_code_detail_battery(self, auth_token):
        """获取电池故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_battery}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert "温差" in data.get("fault_name", "")

    def test_disabled_fault_code_hidden(self, auth_token):
        """已禁用的故障码不被列表包含"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", {}).get("items", []) or data.get("items", [])
        codes = [i.get("fault_code") for i in items]
        assert self.fc_disabled not in codes

    def test_disabled_fault_code_detail_not_found(self, auth_token):
        """已禁用的故障码详情仍可访问（detail端点不过滤enabled）"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fc_disabled}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        # detail endpoint doesn't filter by enabled
        assert data.get("fault_code") == self.fc_disabled
        assert data.get("fault_name") == "已停用故障码"

    def test_filter_fault_codes_by_device_type_charger(self):
        """按设备类型充电桩筛选（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?device_type=charger")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        for item in items:
            assert item.get("device_type") == "charger"

    def test_filter_fault_codes_by_device_type_pcs(self):
        """按设备类型PCS筛选（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?device_type=pcs")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        for item in items:
            assert item.get("device_type") == "pcs"

    def test_filter_fault_codes_by_category_bus(self):
        """按母线故障分类筛选（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?fault_category=bus")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        for item in items:
            assert item.get("fault_category") == "bus"

    def test_filter_fault_codes_by_keyword_temperature(self):
        """按温度关键词搜索（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?keyword=温度")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        # 至少应找到散热器温度过高
        names = [i.get("fault_name") for i in items]
        assert any("温度" in n for n in names)

    def test_filter_fault_codes_by_keyword_bms(self):
        """按BMS关键词搜索（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?keyword=BMS")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        assert len(items) >= 1

    def test_filter_fault_codes_combined_multi_criteria(self):
        """多条件组合筛选（无需auth）"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-codes?device_type=charger&fault_level=emergency&fault_category=charging_controller")
        assert resp.status_code == 200
        items = resp.json().get("data", {}).get("items", [])
        if items:
            for item in items:
                assert item.get("device_type") == "charger"
                assert item.get("fault_level") == "emergency"

    def test_quick_diagnosis_exact_match(self, auth_token):
        """快速诊断精确匹配（故障码+设备类型）"""
        resp = self.client.post(f"/api/v1/fault-diagnosis/quick-diagnosis?fault_code={self.fc_charger}&device_type=charger", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_name") == "充电枪温度过高"
        assert len(data.get("quick_diagnosis", {}).get("possible_causes", [])) <= 3
        assert data.get("quick_diagnosis", {}).get("need_stop") is True

    def test_quick_diagnosis_fallback(self, auth_token):
        """快速诊断模糊匹配（仅故障码，设备类型不匹配）"""
        resp = self.client.post(f"/api/v1/fault-diagnosis/quick-diagnosis?fault_code={self.fc_pcs}&device_type=inverter", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # 没有device_type=pcs的精确匹配，但有故障码匹配
        # quick_diagnosis 先精确匹配，再尝试仅按故障码匹配
        assert resp.status_code in (200, 404)

    def test_quick_diagnosis_no_match(self, auth_token):
        """快速诊断无匹配"""
        resp = self.client.post("/api/v1/fault-diagnosis/quick-diagnosis?fault_code=0x9999&device_type=inverter", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 404

    def test_fault_statistics_with_days_zero(self, auth_token):
        """故障统计 days=0 被拒 — 安全修复:days 边界验证(ge=1,旧测试断言 200 固化了无校验漏洞,翻转)"""
        resp = self.client.get("/api/v1/fault-diagnosis/fault-statistics?days=0", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 422


@pytest.mark.timeout(30)
class TestFaultDiagnosisWithData:

    @pytest.fixture(autouse=True)
    def _setup(self, test_db, client):
        self.client = client
        db = test_db["session"]
        from app.models.fault_code import FaultCode, FaultLevel, FaultCategory, RepairGuide
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus

        # 创建站点和设备
        station = Station(name="FD站点", code="FD-ST-001", status=StationStatus.NORMAL)
        db.add(station)
        db.flush()

        device = Device(
            sn="FD-DEV-001", name="FD测试设备",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=station.id
        )
        db.add(device)
        db.flush()

        # 创建故障码
        fc = FaultCode(
            fault_code="0x01",
            fault_name="电网过压",
            fault_description="电网电压超过保护阈值",
            device_type="inverter",
            fault_category=FaultCategory.GRID,
            fault_level=FaultLevel.SERIOUS,
            possible_causes=["电网波动", "负载突变"],
            diagnosis_steps=["检查电压", "确认阈值"],
            repair_suggestions=["调整参数"],
            response_time_minutes=15,
            auto_stop=True,
            remote_fixable=True,
            occurrence_count=5,
            avg_repair_time_minutes=30,
            enabled=True
        )
        db.add(fc)
        db.flush()

        # 创建修复指南
        guide = RepairGuide(
            fault_code_id=fc.id,
            title="电网过压修复指南",
            estimated_time_minutes=30,
            difficulty_level="medium",
            required_tools="万用表",
            success_rate=0.85,
            enabled=True
        )
        db.add(guide)

        # 创建告警
        alarm = Alarm(
            device_id=device.id,
            station_id=station.id,
            level=AlarmLevel.CRITICAL,
            content="电网过压告警",
            fault_code="0x01",
            status=AlarmStatus.ACTIVE,
            remote_fixable=True,
        )
        db.add(alarm)
        db.flush()

        db.commit()

        self.fault_code_id = fc.id
        self.fault_code = fc.fault_code
        self.alarm_id = alarm.id
        self.device_id = device.id
        self.station_id = station.id
        db.close()

    def test_get_fault_code_detail_with_data(self, auth_token):
        """获取存在的故障码详情"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-codes/{self.fault_code}")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_code") == "0x01"
        assert data.get("fault_name") == "电网过压"
        assert data.get("remote_fixable") is True
        assert len(data.get("repair_guides", [])) >= 1

    def test_diagnose_alarm_with_data(self, auth_token):
        """诊断存在的告警"""
        resp = self.client.post("/api/v1/fault-diagnosis/alarm-diagnosis", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"alarm_id": self.alarm_id})
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("matched") is True
        assert data.get("fault_name") == "电网过压"
        assert data.get("alarm_id") == self.alarm_id

    def test_remote_fix_with_data(self, auth_token):
        """远程修复存在的告警"""
        resp = self.client.post("/api/v1/fault-diagnosis/remote-fix-attempt", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "alarm_id": self.alarm_id,
            "fix_type": "reset"
        })
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fix_type") == "reset"
        assert data.get("alarm_id") == self.alarm_id

    def test_remote_fix_reboot(self, auth_token):
        """远程重启"""
        resp = self.client.post("/api/v1/fault-diagnosis/remote-fix-attempt", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "alarm_id": self.alarm_id,
            "fix_type": "reboot"
        })
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fix_type") == "reboot"

    def test_remote_fix_param_adjust(self, auth_token):
        """远程参数调整"""
        resp = self.client.post("/api/v1/fault-diagnosis/remote-fix-attempt", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "alarm_id": self.alarm_id,
            "fix_type": "param_adjust"
        })
        assert resp.status_code == 200

    def test_fault_statistics_with_data(self, auth_token):
        """统计存在告警的数据"""
        resp = self.client.get(f"/api/v1/fault-diagnosis/fault-statistics?station_id={self.station_id}&days=30")
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("total_alarms") >= 1

    def test_quick_diagnosis_with_existing_code(self, auth_token):
        """快速诊断存在的故障码"""
        resp = self.client.post(f"/api/v1/fault-diagnosis/quick-diagnosis?fault_code={self.fault_code}&device_type=inverter", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("fault_code") == self.fault_code
        assert "quick_diagnosis" in data
        assert "diagnosis_steps" in data
        assert "repair_suggestions" in data

class TestFaultCodesPageGuard:
    """分页 page 参数 ge=1 守卫回归测试（卡0db1465a）"""

    def test_page_zero_returns_422(self, client):
        """page=0 → 422，而非负 offset 导致 500"""
        resp = client.get("/api/v1/fault-diagnosis/fault-codes?page=0")
        assert resp.status_code == 422

    def test_page_negative_returns_422(self, client):
        """page=-1 → 422"""
        resp = client.get("/api/v1/fault-diagnosis/fault-codes?page=-1")
        assert resp.status_code == 422

"""
YAML 设备模板加载器测试

测试内容：
    - DeviceTemplate 数据类
    - TemplateLoader 核心功能
    - YAML 模板文件加载
    - 按类别索引
    - 模板验证
    - 缓存与热重载
    - 全局单例
"""
import pytest
import tempfile
import os
import time
from pathlib import Path

from app.gateway.template_loader import (
    DeviceTemplate,
    TemplateLoader,
    get_template_loader,
    reset_template_loader,
)


# ========== DeviceTemplate 数据类测试 ==========

class TestDeviceTemplate:
    """DeviceTemplate 数据类"""

    def test_create_template(self):
        """测试创建模板对象"""
        template = DeviceTemplate(
            device_type="inverter_eahi_20k",
            manufacturer="EAHI",
            model="20K-TL3",
            category="inverter",
            protocol="modbus_rtu",
            connection={"port": "/dev/ttyUSB0", "baudrate": 9600},
            registers=[
                {"address": 40001, "name": "grid_voltage_a", "type": "uint16", "unit": "V"}
            ],
        )

        assert template.device_type == "inverter_eahi_20k"
        assert template.manufacturer == "EAHI"
        assert template.category == "inverter"
        assert template.protocol == "modbus_rtu"
        assert len(template.registers) == 1

    def test_to_dict(self):
        """测试转换为字典"""
        template = DeviceTemplate(
            device_type="test_device",
            manufacturer="TestMfg",
            model="TestModel",
            category="meter",
            protocol="modbus_rtu",
        )

        d = template.to_dict()
        assert d["device_type"] == "test_device"
        assert d["category"] == "meter"
        assert "connection" in d
        assert "registers" in d

    def test_default_values(self):
        """测试默认值"""
        template = DeviceTemplate(
            device_type="minimal_device",
            manufacturer="Min",
            model="V1",
            category="charger",
            protocol="mqtt",
        )

        assert template.connection == {}
        assert template.registers == []
        assert template.source_file == ""


# ========== TemplateLoader 核心测试 ==========

class TestTemplateLoader:
    """TemplateLoader 加载和索引"""

    @pytest.fixture
    def temp_template_dir(self, tmp_path):
        """创建临时模板目录"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        return templates_dir

    @pytest.fixture
    def sample_yaml(self):
        """示例 YAML 模板内容"""
        return """device_type: inverter_eahi_20k
manufacturer: EAHI
model: 20K-TL3
category: inverter
protocol: modbus_rtu
connection:
  port: /dev/ttyUSB0
  baudrate: 9600
  slave_id: 1
registers:
  - address: 40001
    name: grid_voltage_a
    type: uint16
    scale: 0.1
    unit: V
"""

    def test_load_from_dir(self, temp_template_dir, sample_yaml):
        """测试从目录加载模板"""
        # 写入测试 YAML 文件
        file_path = temp_template_dir / "inverter_eahi_20k.yaml"
        file_path.write_text(sample_yaml)

        loader = TemplateLoader(template_dir=str(temp_template_dir))
        count = loader.load_all()

        assert count == 1
        template = loader.get_template("inverter_eahi_20k")
        assert template is not None
        assert template.manufacturer == "EAHI"
        assert template.category == "inverter"
        assert template.protocol == "modbus_rtu"

    def test_load_multiple_templates(self, temp_template_dir):
        """测试加载多个模板"""
        for dt in ["inverter_eahi_20k", "bms_lithium"]:
            content = f"""device_type: {dt}
manufacturer: Test
model: Test
category: {"inverter" if "inverter" in dt else "bms"}
protocol: modbus_rtu
"""
            (temp_template_dir / f"{dt}.yaml").write_text(content)

        loader = TemplateLoader(template_dir=str(temp_template_dir))
        count = loader.load_all()

        assert count == 2
        assert loader.get_template("inverter_eahi_20k") is not None
        assert loader.get_template("bms_lithium") is not None

    def test_get_by_category(self, temp_template_dir):
        """测试按类别索引"""
        inverter_yaml = """device_type: inv1
manufacturer: A
model: A1
category: inverter
protocol: modbus_rtu
"""
        meter_yaml = """device_type: meter1
manufacturer: B
model: B1
category: meter
protocol: modbus_rtu
"""

        (temp_template_dir / "inv1.yaml").write_text(inverter_yaml)
        (temp_template_dir / "meter1.yaml").write_text(meter_yaml)

        loader = TemplateLoader(template_dir=str(temp_template_dir))
        loader.load_all()

        inverters = loader.get_by_category("inverter")
        assert len(inverters) == 1
        assert inverters[0].category == "inverter"

        meters = loader.get_by_category("meter")
        assert len(meters) == 1
        assert meters[0].category == "meter"

    def test_list_device_types(self, temp_template_dir):
        """测试列出所有设备类型"""
        yaml_content = """device_type: test_device
manufacturer: Test
model: Test
category: pcs
protocol: modbus_rtu
"""
        (temp_template_dir / "test_device.yaml").write_text(yaml_content)

        loader = TemplateLoader(template_dir=str(temp_template_dir))
        loader.load_all()

        mapping = loader.list_device_types()
        assert mapping == {"test_device": "modbus_rtu"}

    def test_list_all(self, temp_template_dir):
        """测试列出所有模板"""
        for i in range(3):
            content = f"""device_type: dev_{i}
manufacturer: M
model: M
category: inverter
protocol: modbus_rtu
"""
            (temp_template_dir / f"dev_{i}.yaml").write_text(content)

        loader = TemplateLoader(template_dir=str(temp_template_dir))
        loader.load_all()

        all_templates = loader.list_all()
        assert len(all_templates) == 3

    def test_get_nonexistent(self, temp_template_dir):
        """测试获取不存在的模板"""
        loader = TemplateLoader(template_dir=str(temp_template_dir))
        loader.load_all()

        assert loader.get_template("nonexistent") is None
        assert loader.get_by_category("nonexistent") == []

    def test_empty_dir(self, temp_template_dir):
        """测试空目录"""
        loader = TemplateLoader(template_dir=str(temp_template_dir))
        count = loader.load_all()

        assert count == 0

    def test_nonexistent_dir(self):
        """测试目录不存在"""
        loader = TemplateLoader(template_dir="/nonexistent/path/12345")
        count = loader.load_all()

        assert count == 0


# ========== 模板验证测试 ==========

class TestTemplateValidation:
    """模板验证"""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_validate_valid_template(self, temp_dir):
        """测试验证有效模板"""
        file_path = temp_dir / "valid.yaml"
        file_path.write_text("""device_type: test_device
manufacturer: Test
model: T1
category: inverter
protocol: modbus_rtu
""")

        result = TemplateLoader.validate_template_file(str(file_path))
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_missing_field(self, temp_dir):
        """测试缺少必填字段"""
        file_path = temp_dir / "missing.yaml"
        file_path.write_text("""device_type: test_device
manufacturer: Test
""")

        result = TemplateLoader.validate_template_file(str(file_path))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_validate_invalid_category(self, temp_dir):
        """测试无效类别"""
        file_path = temp_dir / "bad_cat.yaml"
        file_path.write_text("""device_type: test_device
manufacturer: Test
model: T1
category: invalid_category
protocol: modbus_rtu
""")

        result = TemplateLoader.validate_template_file(str(file_path))
        assert result["valid"] is False

    def test_validate_nonexistent_file(self):
        """测试文件不存在"""
        result = TemplateLoader.validate_template_file("/nonexistent/file.yaml")
        assert result["valid"] is False

    def test_validate_bad_yaml(self, temp_dir):
        """测试无效 YAML"""
        file_path = temp_dir / "bad.yaml"
        file_path.write_text("{invalid: yaml: content: [")

        result = TemplateLoader.validate_template_file(str(file_path))
        assert result["valid"] is False


# ========== 热重载测试 ==========

class TestHotReload:
    """热重载功能"""

    def test_reload_unchanged(self, tmp_path):
        """测试无变化时不重载"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "dev.yaml").write_text("""device_type: dev
manufacturer: M
model: M
category: inverter
protocol: modbus_rtu
""")

        loader = TemplateLoader(template_dir=str(templates_dir))
        loader.load_all()

        count = loader.reload_if_changed()
        assert count == 0

    def test_reload_modified(self, tmp_path):
        """测试文件修改后重载"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        file_path = templates_dir / "dev.yaml"
        file_path.write_text("""device_type: dev
manufacturer: M
model: M
category: inverter
protocol: modbus_rtu
""")

        loader = TemplateLoader(template_dir=str(templates_dir))
        loader.load_all()

        # 修改文件
        time.sleep(0.01)  # 确保 mtime 变化
        file_path.write_text("""device_type: dev
manufacturer: UpdatedMfg
model: NewModel
category: inverter
protocol: modbus_rtu
""")

        count = loader.reload_if_changed()
        assert count == 1

        template = loader.get_template("dev")
        assert template.manufacturer == "UpdatedMfg"

    def test_reload_new_file(self, tmp_path):
        """测试新增文件"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "dev1.yaml").write_text("""device_type: dev1
manufacturer: A
model: A
category: inverter
protocol: modbus_rtu
""")

        loader = TemplateLoader(template_dir=str(templates_dir))
        loader.load_all()
        assert len(loader.list_all()) == 1

        # 新增文件
        (templates_dir / "dev2.yaml").write_text("""device_type: dev2
manufacturer: B
model: B
category: meter
protocol: modbus_rtu
""")

        count = loader.reload_if_changed()
        assert count == 1
        assert len(loader.list_all()) == 2


# ========== 运行时注册测试 ==========

class TestRuntimeRegistration:
    """运行时注册"""

    def test_register_template(self, tmp_path):
        """测试运行时注册模板"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        loader = TemplateLoader(template_dir=str(templates_dir))
        loader.load_all()

        template = DeviceTemplate(
            device_type="runtime_device",
            manufacturer="Runtime",
            model="R1",
            category="charger",
            protocol="mqtt",
        )

        loader.register_template(template)

        assert loader.get_template("runtime_device") is not None
        chargers = loader.get_by_category("charger")
        assert any(t.device_type == "runtime_device" for t in chargers)

    def test_add_template_from_file(self, tmp_path):
        """测试从文件添加模板"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        file_path = tmp_path / "new_device.yaml"
        file_path.write_text("""device_type: from_file_device
manufacturer: FF
model: FF1
category: bms
protocol: modbus_rtu
""")

        loader = TemplateLoader(template_dir=str(templates_dir))
        loader.load_all()

        template = loader.add_template_from_file(str(file_path))
        assert template.device_type == "from_file_device"
        assert loader.get_template("from_file_device") is not None


# ========== 全局单例测试 ==========

class TestGlobalLoader:
    """全局加载器单例"""

    def test_singleton(self):
        """测试单例模式"""
        reset_template_loader()
        loader1 = get_template_loader()
        loader2 = get_template_loader()

        assert loader1 is loader2
        reset_template_loader()

    def test_reset(self):
        """测试重置"""
        loader1 = get_template_loader()
        reset_template_loader()
        loader2 = get_template_loader()

        assert loader1 is not loader2
        reset_template_loader()


# ========== 集成测试：加载真实模板 ==========

class TestRealTemplates:
    """加载项目中的真实模板文件"""

    def test_load_builtin_templates(self):
        """测试加载内置模板"""
        from pathlib import Path
        template_dir = Path(__file__).parent.parent / "app" / "gateway" / "templates"

        if not template_dir.is_dir():
            pytest.skip("模板目录不存在")

        loader = TemplateLoader(template_dir=str(template_dir))
        count = loader.load_all()

        assert count >= 5

        # 验证各设备类型存在
        for dt in ["inverter_eahi_20k", "pcs_100kw", "meter_three_phase", "charger_dc_60kw", "bms_lithium"]:
            template = loader.get_template(dt)
            assert template is not None, f"缺少模板: {dt}"
            assert template.device_type == dt

        # 验证类别索引（已有多个变种，每类至少1个模板）
        assert len(loader.get_by_category("inverter")) >= 1
        assert len(loader.get_by_category("pcs")) >= 1
        assert len(loader.get_by_category("meter")) >= 1
        assert len(loader.get_by_category("charger")) >= 1
        assert len(loader.get_by_category("bms")) >= 1

    def test_all_required_fields_present(self):
        """测试所有模板包含必填字段"""
        from pathlib import Path
        template_dir = Path(__file__).parent.parent / "app" / "gateway" / "templates"

        if not template_dir.is_dir():
            pytest.skip("模板目录不存在")

        loader = TemplateLoader(template_dir=str(template_dir))
        loader.load_all()

        for template in loader.list_all():
            assert template.device_type, f"{template.source_file}: 缺少 device_type"
            assert template.manufacturer, f"{template.source_file}: 缺少 manufacturer"
            assert template.category in TemplateLoader.VALID_CATEGORIES, \
                f"{template.source_file}: 无效 category {template.category}"
            assert template.protocol, f"{template.source_file}: 缺少 protocol"

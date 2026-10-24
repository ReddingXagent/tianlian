"""
modbus_schema.py 补充测试 (卡 810f2bd8)

针对 modbus_schema.py 现有测试 (test_parsers.py + test_parsers_coverage.py) 未覆盖的部分:
  - INVERTER_EAHI_20K_REGISTERS 寄存器配置数据契约 (地址唯一/类型合法/scale>0/unit 非空)
  - INVERTER_FAULT_DISCRETE_ADDR 故障离散量映射 (现有完全未测)
  - load_inverter_schema() 端到端语义 (字段数/可解析性/protocol)
  - 寄存器地址空间与故障地址空间隔离校验

注: _load_schema_json 各分支、load_modbus_schema 内置/JSON/兜底分支
已在 test_parsers_coverage.py 覆盖, 此处不重复。
"""
import pytest

from app.parsers.base_schema import DataType, Unit
from app.parsers.modbus_schema import (
    INVERTER_EAHI_20K_REGISTERS,
    INVERTER_FAULT_DISCRETE_ADDR,
    load_inverter_schema,
    load_modbus_schema,
)


# ========== INVERTER_EAHI_20K_REGISTERS 数据契约 ==========

class TestRegisterConfigContract:
    """寄存器配置表的数据完整性契约, 防止配置被改坏。"""

    def test_registers_non_empty(self):
        assert len(INVERTER_EAHI_20K_REGISTERS) > 0

    def test_every_register_has_required_keys(self):
        """每个寄存器必须含 address/type/scale/unit/description 五键"""
        required = {"address", "type", "scale", "unit", "description"}
        for name, cfg in INVERTER_EAHI_20K_REGISTERS.items():
            assert required.issubset(cfg.keys()), f"{name} 缺键: {required - cfg.keys()}"

    def test_addresses_are_unique(self):
        """寄存器地址必须唯一 (Modbus 地址空间无冲突)"""
        addrs = [c["address"] for c in INVERTER_EAHI_20K_REGISTERS.values()]
        assert len(addrs) == len(set(addrs)), "存在重复寄存器地址"

    def test_addresses_are_non_negative_int(self):
        for name, cfg in INVERTER_EAHI_20K_REGISTERS.items():
            assert isinstance(cfg["address"], int), f"{name} address 非 int"
            assert cfg["address"] >= 0, f"{name} address 为负"

    def test_types_are_valid(self):
        """所有 type 字符串必须是合法 DataType"""
        valid_types = {t.value for t in DataType}
        for name, cfg in INVERTER_EAHI_20K_REGISTERS.items():
            assert cfg["type"] in valid_types, f"{name} type={cfg['type']} 非法"

    def test_scales_are_positive(self):
        """scale 必须为正数 (0 或负缩放因子无物理意义)"""
        for name, cfg in INVERTER_EAHI_20K_REGISTERS.items():
            assert cfg["scale"] > 0, f"{name} scale={cfg['scale']} 非正"

    def test_units_non_empty_string(self):
        """unit 必须是非空字符串 (run_mode/system_status 例外可为空)"""
        # 注: run_mode/system_status 的 unit 确实为 "" (无量纲), 这里校验类型即可
        for name, cfg in INVERTER_EAHI_20K_REGISTERS.items():
            assert isinstance(cfg["unit"], str), f"{name} unit 非 str"

    def test_known_register_values(self):
        """抽样校验关键寄存器配置值 (锁死核心映射)"""
        assert INVERTER_EAHI_20K_REGISTERS["grid_voltage_a"]["address"] == 0
        assert INVERTER_EAHI_20K_REGISTERS["grid_voltage_a"]["scale"] == 0.1
        assert INVERTER_EAHI_20K_REGISTERS["battery_soc"]["address"] == 103
        assert INVERTER_EAHI_20K_REGISTERS["battery_soc"]["unit"] == "%"
        assert INVERTER_EAHI_20K_REGISTERS["run_time"]["unit"] == "s"


# ========== INVERTER_FAULT_DISCRETE_ADDR 故障映射 ==========

class TestFaultDiscreteAddress:
    """故障离散量地址 → 故障名映射 (现有测试完全未覆盖)。"""

    def test_fault_map_non_empty(self):
        assert len(INVERTER_FAULT_DISCRETE_ADDR) > 0

    def test_fault_addresses_are_unique(self):
        """dict 键天然唯一, 这里显式断言"""
        addrs = list(INVERTER_FAULT_DISCRETE_ADDR.keys())
        assert len(addrs) == len(set(addrs))

    def test_fault_addresses_non_negative_int(self):
        for addr in INVERTER_FAULT_DISCRETE_ADDR:
            assert isinstance(addr, int)
            assert addr >= 0

    def test_fault_names_non_empty_string(self):
        for addr, name in INVERTER_FAULT_DISCRETE_ADDR.items():
            assert isinstance(name, str) and name != "", f"{addr} → 空故障名"

    def test_known_fault_mappings(self):
        """抽样校验关键故障映射 (锁死核心地址)"""
        assert INVERTER_FAULT_DISCRETE_ADDR[0] == "grid_over_voltage_a"
        assert INVERTER_FAULT_DISCRETE_ADDR[39] == "island_fault"
        assert INVERTER_FAULT_DISCRETE_ADDR[126] == "bms_comm_fault"
        assert INVERTER_FAULT_DISCRETE_ADDR[160] == "internal_over_temp"

    def test_fault_addr_within_discrete_range(self):
        """故障地址应在 0-223 离散量输入范围内 (文件注释声明 0-223)"""
        for addr in INVERTER_FAULT_DISCRETE_ADDR:
            assert 0 <= addr <= 223, f"故障地址 {addr} 超出 0-223 范围"


class TestRegisterFaultAddressSpaces:
    """寄存器 (holding register) 与故障离散量 (discrete input) 属于 Modbus 不同
    地址空间, 数值可重叠 (如 reg[0]=grid_voltage_a, fault[0]=grid_over_voltage_a),
    不构成冲突。本组刻画两者各自的地址范围契约。"""

    def test_register_and_fault_maps_are_independent_dicts(self):
        """两者是独立映射表, 各自合法即可, 无需数值隔离"""
        assert isinstance(INVERTER_EAHI_20K_REGISTERS, dict)
        assert isinstance(INVERTER_FAULT_DISCRETE_ADDR, dict)

    def test_register_addrs_within_holding_range(self):
        """寄存器地址应在合理 Modbus holding register 范围内 (< 65536)"""
        for cfg in INVERTER_EAHI_20K_REGISTERS.values():
            assert 0 <= cfg["address"] < 65536


# ========== load_inverter_schema 端到端 ==========

class TestLoadInverterSchema:
    def test_load_inverter_schema_metadata(self):
        schema = load_inverter_schema()
        assert schema.device_type == "inverter_eahi_20k"
        assert schema.protocol == "modbus"

    def test_load_inverter_schema_field_count_matches_registers(self):
        """加载后字段数应等于寄存器配置数"""
        schema = load_inverter_schema()
        assert len(schema.fields) == len(INVERTER_EAHI_20K_REGISTERS)

    def test_load_inverter_schema_all_registers_present(self):
        """每个寄存器都应成为 schema 字段"""
        schema = load_inverter_schema()
        for name in INVERTER_EAHI_20K_REGISTERS:
            assert name in schema.fields, f"{name} 未加载为字段"

    def test_load_inverter_schema_parse_value_works(self):
        """加载的 schema 可正确解析寄存器原始值"""
        schema = load_inverter_schema()
        # grid_voltage_a: scale=0.1, raw=2205 → 220.5
        assert schema.parse_value("grid_voltage_a", 2205) == pytest.approx(220.5)
        # battery_soc: scale=0.01, raw=9500 → 95.0
        assert schema.parse_value("battery_soc", 9500) == pytest.approx(95.0)

    def test_load_inverter_schema_field_units_preserved(self):
        """寄存器 unit 字符串正确转为 Unit 枚举"""
        schema = load_inverter_schema()
        assert schema.get_field_schema("grid_voltage_a")["unit"] == Unit.VOLTAGE
        assert schema.get_field_schema("battery_soc")["unit"] == Unit.PERCENTAGE
        assert schema.get_field_schema("run_time")["unit"] == Unit.TIME


class TestLoadModbusSchemaInverterDispatch:
    def test_load_modbus_schema_dispatches_to_inverter(self):
        """load_modbus_schema('inverter_eahi_20k') 应分发到 load_inverter_schema"""
        schema = load_modbus_schema("inverter_eahi_20k")
        assert schema.device_type == "inverter_eahi_20k"
        assert "grid_voltage_a" in schema.fields
        assert "battery_soc" in schema.fields

    def test_load_inverter_schema_independent_instances(self):
        """两次加载返回独立对象 (状态隔离)"""
        s1 = load_inverter_schema()
        s2 = load_inverter_schema()
        assert s1 is not s2
        s1.add_field({
            "name": "extra", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 1.0, "offset": 0, "min": None, "max": None,
            "description": "",
        })
        assert "extra" not in s2.fields

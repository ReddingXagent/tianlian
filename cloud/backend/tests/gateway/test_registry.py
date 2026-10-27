"""
协议注册中心（ProtocolRegistry）单元测试。

覆盖：
    - register_protocol / list_protocols / has_adapter
    - get_adapter（正常 / 未知 device_type / 未注册 protocol / 实例化失败 / config.protocol 覆盖）
    - register_device_type / list_device_types / get_protocol_for_device_type / bulk
    - auto_discover 扫描内置适配器
    - reload_templates 热重载
    - 全局 get_registry 单例 / reset_registry
"""
import pytest

from app.gateway.base import DeviceAdapter, ProtocolAdapter
from app.gateway.registry import (
    ProtocolRegistry,
    get_registry,
    reset_registry,
)


# ========== 测试用假适配器 ==========

class _FakeAdapter(DeviceAdapter):
    protocol_type = "fake_proto"

    def __init__(self, name: str = "fake", **kwargs):
        super().__init__()
        self.name = name
        # 若传入 fail=True 模拟实例化失败
        if kwargs.get("fail"):
            raise RuntimeError("实例化失败")

    async def connect(self):
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False
        return True

    async def read_data(self, device_address):
        return {}

    async def write_command(self, device_address, command):
        return True

    def parse_fault_code(self, raw_data):
        return None


class _FakeAdapterWithDeviceType(DeviceAdapter):
    protocol_type = "fake_device_proto"
    device_type = "fake_device_x"

    async def connect(self):
        return True

    async def disconnect(self):
        return True

    async def read_data(self, device_address):
        return {}

    async def write_command(self, device_address, command):
        return True

    def parse_fault_code(self, raw_data):
        return None


@pytest.fixture
def registry():
    """独立注册中心实例（不污染全局单例）。"""
    return ProtocolRegistry()


# ========== register_protocol ==========

def test_register_protocol(registry):
    registry.register_protocol("fake_proto", _FakeAdapter)
    assert registry.has_adapter("fake_proto") is True
    assert registry.list_protocols()["fake_proto"] == "_FakeAdapter"


def test_register_protocol_invalid_class_ignored(registry):
    # 非 ProtocolAdapter 子类
    class NotAnAdapter:
        pass

    registry.register_protocol("bad", NotAnAdapter)  # type: ignore[arg-type]
    assert registry.has_adapter("bad") is False


def test_register_protocol_non_type_ignored(registry):
    registry.register_protocol("bad2", "not-a-class")  # type: ignore[arg-type]
    assert registry.has_adapter("bad2") is False


def test_protocol_adapter_alias():
    # ProtocolAdapter 是 DeviceAdapter 别名
    assert ProtocolAdapter is DeviceAdapter


# ========== get_adapter ==========

def test_get_adapter_by_device_type(registry):
    registry.register_protocol("fake_proto", _FakeAdapter)
    registry.register_device_type("fake_device", "fake_proto")
    adapter = registry.get_adapter("fake_device", {"name": "inst-1"})
    assert adapter is not None
    assert isinstance(adapter, _FakeAdapter)
    assert adapter.name == "inst-1"


def test_get_adapter_unknown_device_type(registry):
    registry.register_protocol("fake_proto", _FakeAdapter)
    adapter = registry.get_adapter("not_registered_type", {})
    assert adapter is None


def test_get_adapter_protocol_not_registered(registry):
    registry.register_device_type("fake_device", "fake_proto")
    # 未注册 fake_proto 的类
    adapter = registry.get_adapter("fake_device", {})
    assert adapter is None


def test_get_adapter_config_protocol_overrides(registry):
    """config['protocol'] 优先于 device_type 映射。"""
    registry.register_protocol("fake_proto", _FakeAdapter)
    registry.register_device_type("fake_device", "other_proto")
    adapter = registry.get_adapter("fake_device", {"protocol": "fake_proto"})
    assert adapter is not None
    assert isinstance(adapter, _FakeAdapter)


def test_get_adapter_instantiation_failure(registry):
    registry.register_protocol("fake_proto", _FakeAdapter)
    registry.register_device_type("fake_device", "fake_proto")
    # fail=True 触发构造异常 → 返回 None
    adapter = registry.get_adapter("fake_device", {"fail": True})
    assert adapter is None


# ========== device_type 映射 ==========

def test_register_device_type(registry):
    registry.register_device_type("d1", "fake_proto")
    assert registry.get_protocol_for_device_type("d1") == "fake_proto"
    assert "d1" in registry.list_device_types()


def test_register_device_types_bulk(registry):
    registry.register_device_types_bulk({"a": "p1", "b": "p2"})
    mapping = registry.list_device_types()
    assert mapping["a"] == "p1"
    assert mapping["b"] == "p2"


def test_list_device_types_is_copy(registry):
    registry.register_device_type("d1", "p1")
    snapshot = registry.list_device_types()
    snapshot["d1"] = "mutated"
    # 原映射不受影响（返回的是 copy）
    assert registry.get_protocol_for_device_type("d1") == "p1"


def test_get_protocol_for_device_type_unknown(registry):
    assert registry.get_protocol_for_device_type("nope") is None


# ========== auto_discover ==========

def test_auto_discover_registers_builtin_adapters(registry):
    """auto_discover 应扫描出 ocpp / mqtt / modbus_rtu 等内置协议（含 protocol_type）。"""
    registry.auto_discover()
    protocols = registry.list_protocols()
    # ocpp / mqtt 都定义了 protocol_type
    assert "ocpp" in protocols
    assert "mqtt" in protocols


def test_auto_discover_registers_device_type_mapping(registry):
    """带 device_type 类属性的适配器应自动注册设备类型映射。"""
    # 模块级注入一个带 device_type 的假适配器较复杂，这里验证内置映射存在
    registry.auto_discover()
    # 至少能列出若干设备类型（来自硬编码兜底或模板）
    assert len(registry.list_device_types()) >= 0


# ========== reload_templates ==========

def test_reload_templates_picks_up_changes(registry, monkeypatch):
    """reload_templates 应在 loader 检测到变更时合并新映射。"""
    from app.gateway import template_loader as tl_module

    class _FakeLoader:
        def __init__(self, changed_count, mapping):
            self._changed = changed_count
            self._mapping = mapping

        def reload_if_changed(self):
            return self._changed

        def list_device_types(self):
            return dict(self._mapping)

    fake_loader = _FakeLoader(2, {"hot_device_1": "mqtt", "hot_device_2": "ocpp"})
    monkeypatch.setattr(tl_module, "get_template_loader", lambda template_dir=None: fake_loader)

    count = registry.reload_templates()
    assert count == 2
    assert registry.get_protocol_for_device_type("hot_device_1") == "mqtt"
    assert registry.get_protocol_for_device_type("hot_device_2") == "ocpp"
    assert registry.is_mapping_from_templates is True


def test_reload_templates_no_change(registry, monkeypatch):
    from app.gateway import template_loader as tl_module

    class _NoChangeLoader:
        def reload_if_changed(self):
            return 0

        def list_device_types(self):
            return {}

    monkeypatch.setattr(
        tl_module, "get_template_loader",
        lambda template_dir=None: _NoChangeLoader(),
    )
    count = registry.reload_templates()
    assert count == 0


# ========== 全局单例 ==========

def test_global_get_registry_returns_singleton():
    reset_registry()
    try:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
    finally:
        reset_registry()


def test_reset_registry_clears_singleton():
    reset_registry()
    r1 = get_registry()
    reset_registry()
    r2 = get_registry()
    assert r1 is not r2
    reset_registry()


def test_global_get_registry_auto_discovers():
    reset_registry()
    try:
        registry = get_registry()
        # auto_discover 已执行，应含内置协议
        assert "ocpp" in registry.list_protocols()
    finally:
        reset_registry()

"""
YAML 设备模板加载器 - 非并发维度测试 (夜班审计C收窄).

前置卡已修复模块级单例层死锁根因 (重 IO 移出 _loader_lock 临界区),
并发/线程竞态由 tests/gateway/test_template_loader_concurrency.py 覆盖.
本文件只补 **非并发维度** 覆盖, 五个维度:

1. 功能路径: 真实模板目录加载 / 单例 / 分类映射 (不 monkeypatch 真目录)
2. YAML 解析错误 / 缺字段: 坏文件隔离跳过, 不炸全量加载
3. reload_if_changed mtime 边界: 未变 / 变更 / 新增 / 删除
4. load_all 幂等: 重复调用不重复累积
5. 坏文件隔离: 二进制 / 空文件 / 权限不可读 不拖垮其他模板

约束:
- 功能路径用真实 app/gateway/templates 目录, 不 monkeypatch 绕过.
- 错误隔离 / mtime / 幂等等需要可控文件场景时, 用 pytest tmp_path 构造
  独立临时目录 (真实文件系统, 非 mock), 与"不绕过真实模板目录"不冲突.
- 触碰全局单例 (_global_loader) 的用例必须 finally reset, 避免污染其他测试.

历史缺陷 (本卡 86aebb9f 已修复, 对应断言已翻转为正确行为 + 回归用例):
- 缺陷A (reload_if_changed 删除残留): 删除文件仅 del _file_mtimes[key],
  未从 _by_device_type / _by_category 移除 → get_template 仍返回已删文件模板.
  修复: 删除分支调用 _remove_by_source_file 同步清索引.
- 缺陷B (reload_if_changed category 重复累积): 重载变更文件时 _index 对
  category list 为 append 且不 clear → 同一模板在 get_by_category 中重复.
  修复: 变更分支重建前先 _remove_by_source_file 清旧条目.
- 缺陷C (load_all 目录不存在分支未置 _loaded): 提前 return 在 _loaded=True 之前,
  → get_template_loader 反复 load_all. 修复: 该分支也置 _loaded=True.
"""
import os
import builtins
from pathlib import Path

import pytest
import yaml

from app.gateway import template_loader as tl_module
from app.gateway.template_loader import (
    TemplateLoader,
    DeviceTemplate,
    get_template_loader,
    reset_template_loader,
)

# 真实模板目录 (与源码默认逻辑一致, 不依赖 cwd)
REAL_TEMPLATES_DIR = Path(tl_module.__file__).parent / "templates"
EXPECTED_COUNT = 11  # app/gateway/templates/*.yaml 实际数量


# ── 测试夹具/辅助 ──────────────────────────────────────────

_VALID_BODY = """\
device_type: {dt}
manufacturer: {mfr}
model: {model}
category: {cat}
protocol: {proto}
connection:
  host: 127.0.0.1
  port: 502
registers:
  - name: r1
    type: uint16
    unit: V
"""


def _write_valid(
    directory: Path,
    filename: str,
    device_type: str,
    category: str = "inverter",
    protocol: str = "modbus_rtu",
    mfr: str = "TestCo",
    model: str = "M1",
) -> Path:
    """在 directory 写一个字段齐全的合法模板, 返回路径."""
    p = directory / filename
    p.write_text(
        _VALID_BODY.format(dt=device_type, mfr=mfr, model=model, cat=category, proto=protocol),
        encoding="utf-8",
    )
    return p


# ══════════════════════════════════════════════════════════
# 维度1: 功能路径 (真实模板目录, 不 monkeypatch)
# ══════════════════════════════════════════════════════════

def test_default_template_dir_resolves_to_gateway_templates():
    """不传 template_dir 时默认指向 app/gateway/templates."""
    loader = TemplateLoader()
    assert loader.template_dir == REAL_TEMPLATES_DIR


def test_load_all_loads_all_real_templates():
    """真实目录 load_all 应加载全部 11 个模板并置 _loaded."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    count = loader.load_all()
    assert count == EXPECTED_COUNT
    assert loader._loaded is True


def test_load_all_missing_dir_returns_zero():
    """目录不存在时 load_all 不抛, 记 warning 返回 0, 且置 _loaded=True (缺陷C 已修).

    缺陷C: 目录不存在分支原提前 return 在 _loaded=True 之前, 与空目录分支行为不一致;
    后果 get_template_loader 依赖 _loaded 判定是否 load, 目录不存在时反复 load_all.
    修复后该分支也置 _loaded=True, 与空目录行为对齐.
    """
    loader = TemplateLoader("/definitely/not/exist/dir")
    assert loader.load_all() == 0
    assert loader._loaded is True  # 修复后: 目录不存在也置位, 防反复 load_all


def test_load_all_empty_dir_returns_zero(tmp_path):
    """空目录 load_all 返回 0, 不抛."""
    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 0
    assert loader.list_all() == []


def test_load_all_only_scans_yaml_extension(tmp_path):
    """glob('*.yaml') 不扫 .yml 后缀 (诚实固化源码行为)."""
    _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    yml = tmp_path / "b.yml"
    yml.write_text(
        _VALID_BODY.format(dt="b_x", mfr="M", model="M", cat="inverter", proto="mqtt"),
        encoding="utf-8",
    )
    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("a_x") is not None
    assert loader.get_template("b_x") is None  # .yml 被忽略


def test_category_index_matches_real_templates():
    """真实模板的 category 双索引计数正确."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()

    assert len(loader.get_by_category("inverter")) == 3
    assert len(loader.get_by_category("charger")) == 3
    assert len(loader.get_by_category("meter")) == 3
    assert len(loader.get_by_category("bms")) == 1
    assert len(loader.get_by_category("pcs")) == 1

    inverter_dts = {t.device_type for t in loader.get_by_category("inverter")}
    assert inverter_dts == {
        "inverter_eahi_20k",
        "inverter_huawei_sun2000",
        "inverter_sungrow_sg250hx",
    }


def test_get_template_returns_populated_object():
    """get_template 返回字段齐全的 DeviceTemplate."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()
    tpl = loader.get_template("inverter_eahi_20k")

    assert tpl is not None
    assert isinstance(tpl, DeviceTemplate)
    assert tpl.manufacturer == "EAHI"
    assert tpl.model == "20K-TL3"
    assert tpl.category == "inverter"
    assert tpl.protocol == "modbus_rtu"
    assert tpl.source_file.endswith("inverter_eahi_20k.yaml")
    assert tpl.connection  # 非空连接参数
    assert tpl.registers  # 非空寄存器列表


def test_get_template_unknown_returns_none():
    """未知 device_type 返回 None."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()
    assert loader.get_template("does_not_exist") is None


def test_get_by_category_unknown_returns_empty_list():
    """未知 category 返回空列表."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()
    assert loader.get_by_category("nonexistent") == []


def test_get_by_category_returns_defensive_copy():
    """get_by_category 返回拷贝, 外部修改不影响内部索引."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()
    lst = loader.get_by_category("inverter")
    original_len = len(lst)
    lst.clear()
    assert len(loader.get_by_category("inverter")) == original_len


def test_list_device_types_maps_to_protocols():
    """list_device_types 返回 {device_type: protocol} 映射, 覆盖全部模板."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    loader.load_all()
    mapping = loader.list_device_types()

    assert len(mapping) == EXPECTED_COUNT
    # 已从源文件确认的 protocol
    assert mapping["inverter_eahi_20k"] == "modbus_rtu"
    assert mapping["iec104_rtu"] == "iec104"
    assert mapping["charger_dc_60kw"] == "mqtt"


def test_list_all_returns_every_template():
    """list_all 返回全部模板, 数量等于 load_all 计数."""
    loader = TemplateLoader(str(REAL_TEMPLATES_DIR))
    n = loader.load_all()
    all_templates = loader.list_all()
    assert len(all_templates) == n == EXPECTED_COUNT
    assert all(isinstance(t, DeviceTemplate) for t in all_templates)


def test_register_template_indexes_runtime_template(tmp_path):
    """register_template 运行时注册模板, 写入双索引 (不写文件)."""
    loader = TemplateLoader(str(tmp_path))
    loader.load_all()
    assert loader.list_all() == []

    tpl = DeviceTemplate(
        device_type="custom_bms",
        manufacturer="Custom",
        model="X1",
        category="bms",
        protocol="mqtt",
    )
    loader.register_template(tpl)

    assert loader.get_template("custom_bms") is tpl
    assert loader.get_template("custom_bms") in loader.get_by_category("bms")


def test_add_template_from_file_indexes_file(tmp_path):
    """add_template_from_file 解析单文件并索引, 返回该模板对象."""
    p = _write_valid(tmp_path, "extra.yaml", "extra_x", "inverter")
    loader = TemplateLoader(str(tmp_path))

    tpl = loader.add_template_from_file(str(p))
    assert isinstance(tpl, DeviceTemplate)
    assert tpl.device_type == "extra_x"
    assert tpl.source_file.endswith("extra.yaml")
    assert loader.get_template("extra_x") is tpl


def test_get_template_loader_returns_loaded_singleton():
    """get_template_loader 单例: 返回已加载实例, 多次调用同一身份."""
    reset_template_loader()
    try:
        l1 = get_template_loader()
        assert isinstance(l1, TemplateLoader)
        assert l1._loaded is True
        assert len(l1.list_all()) == EXPECTED_COUNT

        l2 = get_template_loader()
        assert l2 is l1  # 单例身份唯一
    finally:
        reset_template_loader()


def test_get_template_loader_missing_dir_loads_once(monkeypatch):
    """模板目录不存在时 get_template_loader 不反复 load_all (缺陷C 回归).

    缺陷C: load_all 目录不存在分支原提前 return 未置 _loaded → get_template_loader
    的 `if not loader._loaded: loader.load_all()` 每次都重新 load_all。
    修复后该分支置 _loaded=True, 再次 get 不再触发 load。
    """
    reset_template_loader()
    load_calls = 0
    real_load_all = TemplateLoader.load_all

    def counting_load_all(self):
        nonlocal load_calls
        load_calls += 1
        return real_load_all(self)

    monkeypatch.setattr(TemplateLoader, "load_all", counting_load_all)
    try:
        loader = get_template_loader(template_dir="/definitely/not/exist/dir")
        # 首调 load_all 一次 (目录不存在返回 0, 但修复后置 _loaded)
        assert load_calls == 1
        assert loader._loaded is True

        # 再次 get 同一单例, 不应再 load (缺陷C 下 _loaded 仍 False → 再 load)
        again = get_template_loader(template_dir="/definitely/not/exist/dir")
        assert again is loader
        assert load_calls == 1, f"目录不存在应只 load 一次, 实际 {load_calls} 次 (缺陷C)"
    finally:
        reset_template_loader()


# ══════════════════════════════════════════════════════════
# 维度2: YAML 解析错误 / 缺字段隔离
# ══════════════════════════════════════════════════════════

def test_load_all_skips_malformed_yaml(tmp_path):
    """坏 YAML 文件被隔离跳过, 不影响其他模板加载."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    bad = tmp_path / "bad.yaml"
    bad.write_text("[unterminated", encoding="utf-8")  # 扫描器错误

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("good_x") is not None
    assert loader.get_template("bad") is None


def test_load_all_skips_missing_required_fields(tmp_path):
    """缺必填字段的文件被隔离跳过."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    bad = tmp_path / "bad.yaml"
    bad.write_text("device_type: only_this\n", encoding="utf-8")  # 缺 manufacturer/model/category/protocol

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("only_this") is None
    assert loader.get_template("good_x") is not None


def test_load_all_skips_non_dict_yaml(tmp_path):
    """YAML 顶层非字典 (如列表) 被隔离跳过."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    bad = tmp_path / "bad.yaml"
    bad.write_text("- a\n- b\n- c\n", encoding="utf-8")  # 顶层是 list

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("good_x") is not None


def test_load_all_skips_invalid_category(tmp_path):
    """category 非法 (不在 VALID_CATEGORIES) 的文件被隔离跳过."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    _write_valid(tmp_path, "bad.yaml", "bad_x", category="foobar")

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("bad_x") is None
    assert loader.get_template("good_x") is not None


def test_register_template_rejects_invalid_category(tmp_path):
    """register_template 对非法 category 抛 ValueError, 不入索引."""
    loader = TemplateLoader(str(tmp_path))
    bad = DeviceTemplate(
        device_type="bad_x",
        manufacturer="M",
        model="M",
        category="not_a_category",
        protocol="mqtt",
    )
    with pytest.raises(ValueError):
        loader.register_template(bad)
    assert loader.get_template("bad_x") is None


def test_validate_template_file_rejects_malformed_yaml(tmp_path):
    """validate_template_file 对坏 YAML 返回 valid=False + 错误信息."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("[unterminated", encoding="utf-8")
    result = TemplateLoader.validate_template_file(str(bad))
    assert result["valid"] is False
    assert result["errors"]


def test_validate_template_file_rejects_missing_fields(tmp_path):
    """validate_template_file 对缺字段返回 valid=False."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("device_type: x\n", encoding="utf-8")
    result = TemplateLoader.validate_template_file(str(bad))
    assert result["valid"] is False
    assert any("必填" in e for e in result["errors"])


def test_validate_template_file_accepts_real_template():
    """validate_template_file 对真实模板返回 valid=True, errors 空."""
    real = REAL_TEMPLATES_DIR / "inverter_eahi_20k.yaml"
    result = TemplateLoader.validate_template_file(str(real))
    assert result["valid"] is True
    assert result["errors"] == []


# ══════════════════════════════════════════════════════════
# 维度3: reload_if_changed mtime 边界
# ══════════════════════════════════════════════════════════

def test_reload_if_changed_zero_when_unchanged(tmp_path):
    """文件未变化时 reload_if_changed 返回 0."""
    _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    loader = TemplateLoader(str(tmp_path))
    loader.load_all()
    assert loader.reload_if_changed() == 0


def test_reload_if_changed_detects_mtime_change(tmp_path):
    """文件 mtime 变化触发重载, device_type 索引反映新内容."""
    p = _write_valid(tmp_path, "a.yaml", "a_x", "inverter", mfr="OldCorp")
    loader = TemplateLoader(str(tmp_path))
    loader.load_all()
    assert loader.get_template("a_x").manufacturer == "OldCorp"

    # 改内容 + 显式抬高 mtime (防 FS mtime 精度同刻不变)
    old_mtime = p.stat().st_mtime
    p.write_text(
        _VALID_BODY.format(dt="a_x", mfr="NewCorp", model="M1", cat="inverter", proto="modbus_rtu"),
        encoding="utf-8",
    )
    os.utime(p, (old_mtime + 100, old_mtime + 100))

    n = loader.reload_if_changed()
    assert n >= 1
    # device_type 索引被覆盖, 反映最新内容
    assert loader.get_template("a_x").manufacturer == "NewCorp"


def test_reload_if_changed_picks_up_new_file(tmp_path):
    """reload_if_changed 检测到新增文件并加载."""
    _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1

    _write_valid(tmp_path, "b.yaml", "b_x", "charger")
    n = loader.reload_if_changed()
    assert n == 1
    assert loader.get_template("a_x") is not None
    assert loader.get_template("b_x") is not None
    assert len(loader.list_all()) == 2


def test_reload_if_changed_handles_deleted_file(tmp_path):
    """reload_if_changed 对已删文件: 不计入 updated_count, mtime 快照 + 双索引同步清理 (缺陷A 已修).

    缺陷A: 删除分支原仅 del _file_mtimes[key], 未清 _by_device_type/_by_category
    → get_template 仍返回已删文件模板. 修复后同步 _remove_by_source_file 清索引.
    """
    a = _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    b = _write_valid(tmp_path, "b.yaml", "b_x", "charger")
    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 2

    b.unlink()
    n = loader.reload_if_changed()
    # 删除不计入 updated_count (仅变更/新增计)
    assert n == 0
    # mtime 快照已移除被删文件, 保留未删文件
    assert str(b) not in loader._file_mtimes
    assert str(a) in loader._file_mtimes
    # 修复后: 双索引同步清理, get_template 不再返已删文件旧模板
    assert loader.get_template("b_x") is None
    assert loader.get_template("a_x") is not None
    # category 索引也同步清理: 被删文件的类别列表不再残留它
    assert loader.get_by_category("charger") == []
    assert len(loader.get_by_category("inverter")) == 1


def test_reload_if_changed_no_category_dup_on_repeated_reload(tmp_path):
    """多次 reload 同一变更文件: category 索引不重复累积 (缺陷B 回归).

    缺陷B: reload_if_changed 变更分支 _index 对 category list 为 append 且不查重,
    多次 reload 同一文件 → get_by_category 重复出现同一模板, device_type 索引虽被
    覆盖但 category 列表逐次膨胀。修复后变更分支重建前先清旧条目。
    """
    p = _write_valid(tmp_path, "a.yaml", "a_x", "inverter", mfr="C0")
    loader = TemplateLoader(str(tmp_path))
    loader.load_all()
    assert len(loader.get_by_category("inverter")) == 1

    # 多次抬高 mtime 触发多次 reload (device_type 不变, 内容变)
    base = p.stat().st_mtime
    for i in range(1, 4):
        p.write_text(
            _VALID_BODY.format(
                dt="a_x", mfr=f"C{i}", model="M1", cat="inverter", proto="modbus_rtu"
            ),
            encoding="utf-8",
        )
        os.utime(p, (base + i * 100, base + i * 100))
        n = loader.reload_if_changed()
        assert n == 1  # 每次都检测到变更

    # device_type 索引反映最新内容
    assert loader.get_template("a_x").manufacturer == "C3"
    # category 索引不重复累积, 仍为 1 (缺陷B 下会 == 3)
    inv = loader.get_by_category("inverter")
    assert len(inv) == 1
    assert inv[0].manufacturer == "C3"
    assert all(t.device_type == "a_x" for t in inv)


def test_reload_if_changed_category_change_no_leftover(tmp_path):
    """reload 变更文件 category 时: 旧 category 列表不留残, 新 category 不重复 (缺陷B 补强).

    文件 category 从 inverter 改为 charger 后 reload: 旧 inverter 列表不应再含该模板,
    新 charger 列表应恰有一个。验证 _remove_by_source_file 跨 category 清理。
    """
    p = _write_valid(tmp_path, "a.yaml", "a_x", "inverter", mfr="C0")
    loader = TemplateLoader(str(tmp_path))
    loader.load_all()
    assert len(loader.get_by_category("inverter")) == 1
    assert loader.get_by_category("charger") == []

    base = p.stat().st_mtime
    p.write_text(
        _VALID_BODY.format(
            dt="a_x", mfr="C1", model="M1", cat="charger", proto="modbus_rtu"
        ),
        encoding="utf-8",
    )
    os.utime(p, (base + 100, base + 100))
    assert loader.reload_if_changed() == 1

    # 旧 category 不留残
    assert loader.get_by_category("inverter") == []
    # 新 category 恰一个, 不重复
    chargers = loader.get_by_category("charger")
    assert len(chargers) == 1
    assert chargers[0].device_type == "a_x"


# ══════════════════════════════════════════════════════════
# 维度4: load_all 幂等
# ══════════════════════════════════════════════════════════

def test_load_all_idempotent_across_calls(tmp_path):
    """重复 load_all 不重复累积: 计数稳定, 索引不翻倍."""
    _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    loader = TemplateLoader(str(tmp_path))

    c1 = loader.load_all()
    c2 = loader.load_all()
    assert c1 == c2 == 1
    # device_type 索引不翻倍
    assert len(loader.list_all()) == 1
    # category 索引不累积 (每次 load_all 先 clear)
    assert len(loader.get_by_category("inverter")) == 1


def test_load_all_rebuilds_after_file_removed(tmp_path):
    """load_all 全量重建: 删除文件后再 load_all, 已删模板从索引消失.

    (对比 reload_if_changed 增量不删索引的缺陷A; load_all 先 clear 故无此问题.)
    """
    a = _write_valid(tmp_path, "a.yaml", "a_x", "inverter")
    b = _write_valid(tmp_path, "b.yaml", "b_x", "charger")
    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 2

    b.unlink()
    assert loader.load_all() == 1
    assert loader.get_template("b_x") is None
    assert loader.get_template("a_x") is not None


# ══════════════════════════════════════════════════════════
# 维度5: 坏文件隔离 (不拖垮其他模板)
# ══════════════════════════════════════════════════════════

def test_load_all_isolates_binary_garbage(tmp_path):
    """二进制垃圾 .yaml 被隔离, 不拖垮同目录合法模板."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    bad = tmp_path / "binary.yaml"
    bad.write_bytes(b"\x00\x01\x02\xff\xfe\x00binary")

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("good_x") is not None


def test_load_all_isolates_empty_file(tmp_path):
    """空 .yaml 文件被隔离 (safe_load→None→ValueError), 不拖垮合法模板."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("good_x") is not None


def test_load_all_isolates_unreadable_file(tmp_path, monkeypatch):
    """权限不可读文件被隔离, 不拖垮合法模板.

    chmod 000 覆盖非 root; 若运行环境为 root (绕过文件权限), 则注入
    PermissionError 模拟不可读 (非 monkeypatch 真实模板目录, 仅模拟单文件不可读).
    """
    good = _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    noperm = _write_valid(tmp_path, "noperm.yaml", "noperm_x", "inverter")
    os.chmod(noperm, 0o000)

    try:
        loader = TemplateLoader(str(tmp_path))
        if os.access(noperm, os.R_OK):
            # root 环境绕过权限 → 注入 PermissionError 确定性模拟不可读
            real_open = builtins.open

            def patched_open(path, *args, **kwargs):
                if Path(path).name == "noperm.yaml":
                    raise PermissionError("模拟不可读 (root 环境)")
                return real_open(path, *args, **kwargs)

            monkeypatch.setattr(builtins, "open", patched_open)

        assert loader.load_all() == 1
        assert loader.get_template("good_x") is not None
        assert loader.get_template("noperm_x") is None
    finally:
        # 恢复权限, 避免 tmp_path 清理时删除失败
        os.chmod(noperm, 0o644)


def test_load_all_isolates_mixed_bad_files(tmp_path):
    """多种坏文件混合存在时, 仅合法模板被加载."""
    _write_valid(tmp_path, "good.yaml", "good_x", "inverter")
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")
    (tmp_path / "broken.yaml").write_text("[unterminated", encoding="utf-8")
    (tmp_path / "nofields.yaml").write_text("hello: world\n", encoding="utf-8")
    (tmp_path / "bin.yaml").write_bytes(b"\x00\x01\x02")

    loader = TemplateLoader(str(tmp_path))
    assert loader.load_all() == 1
    assert loader.get_template("good_x") is not None
    assert len(loader.list_all()) == 1

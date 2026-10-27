"""
设备模板 CLI 工具测试

测试内容：
    - device_template.py list 命令
    - device_template.py add 命令
    - device_template.py validate 命令
    - CLI 参数解析
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch


# ========== CLI list 命令测试 ==========


def test_cli_list_basic():
    """测试基本 list 命令"""
    from app.cli.device_template import main
    import argparse

    ns = argparse.Namespace(
        command="list",
        template_dir="",
        category=None,
        json=False,
    )

    from app.cli.device_template import cmd_list
    result = cmd_list(ns)
    assert result == 0


def test_cli_list_category():
    """测试按类别筛选"""
    from app.cli.device_template import cmd_list
    import argparse

    ns = argparse.Namespace(
        command="list",
        template_dir="",
        category="inverter",
        json=False,
    )

    result = cmd_list(ns)
    assert result == 0


def test_cli_list_json():
    """测试 JSON 输出"""
    from app.cli.device_template import cmd_list
    import argparse

    ns = argparse.Namespace(
        command="list",
        template_dir="",
        category=None,
        json=True,
    )

    result = cmd_list(ns)
    assert result == 0


# ========== CLI add 命令测试 ==========


def test_cli_add_nonexistent_file(tmp_path):
    """测试添加不存在文件"""
    from app.cli.device_template import cmd_add
    import argparse

    ns = argparse.Namespace(
        command="add",
        template_dir=str(tmp_path),
        file="/nonexistent/file.yaml",
    )

    result = cmd_add(ns)
    assert result == 1


def test_cli_add_valid_file(tmp_path):
    """测试添加有效模板文件"""
    file_path = tmp_path / "new_device.yaml"
    file_path.write_text("""device_type: new_test_device
manufacturer: TestCorp
model: TC-100
category: inverter
protocol: modbus_rtu
""")

    from app.cli.device_template import cmd_add
    import argparse

    # 使用临时目录作为模板目录
    templates_dir = tmp_path / "templates_dir"
    templates_dir.mkdir()

    ns = argparse.Namespace(
        command="add",
        template_dir=str(templates_dir),
        file=str(file_path),
    )

    result = cmd_add(ns)
    assert result == 0


def test_cli_add_invalid_yaml(tmp_path):
    """测试添加无效模板"""
    file_path = tmp_path / "invalid.yaml"
    file_path.write_text("""device_type: bad_device
# 缺少 manufacturer, model, category, protocol
""")

    from app.cli.device_template import cmd_add
    import argparse

    templates_dir = tmp_path / "templates_dir"
    templates_dir.mkdir()

    ns = argparse.Namespace(
        command="add",
        template_dir=str(templates_dir),
        file=str(file_path),
    )

    result = cmd_add(ns)
    assert result == 1


# ========== CLI validate 命令测试 ==========


def test_cli_validate_valid_file(tmp_path):
    """测试验证有效文件"""
    file_path = tmp_path / "valid.yaml"
    file_path.write_text("""device_type: test_dev
manufacturer: M
model: M1
category: pcs
protocol: modbus_rtu
""")

    from app.cli.device_template import cmd_validate
    import argparse

    ns = argparse.Namespace(
        command="validate",
        files=[str(file_path)],
    )

    result = cmd_validate(ns)
    assert result == 0


def test_cli_validate_invalid_file(tmp_path):
    """测试验证无效文件"""
    file_path = tmp_path / "invalid.yaml"
    file_path.write_text("""device_type: bad_dev
""")

    from app.cli.device_template import cmd_validate
    import argparse

    ns = argparse.Namespace(
        command="validate",
        files=[str(file_path)],
    )

    result = cmd_validate(ns)
    assert result == 1


def test_cli_validate_multiple_files(tmp_path):
    """测试验证多个文件"""
    (tmp_path / "valid.yaml").write_text("""device_type: d1
manufacturer: M
model: M
category: inverter
protocol: modbus_rtu
""")
    (tmp_path / "also_valid.yaml").write_text("""device_type: d2
manufacturer: N
model: N
category: meter
protocol: modbus_rtu
""")

    from app.cli.device_template import cmd_validate
    import argparse

    ns = argparse.Namespace(
        command="validate",
        files=[
            str(tmp_path / "valid.yaml"),
            str(tmp_path / "also_valid.yaml"),
        ],
    )

    result = cmd_validate(ns)
    assert result == 0


# ========== CLI main 入口测试 ==========


def test_cli_main_no_args():
    """测试无参数时显示帮助"""
    from app.cli.device_template import main
    import argparse

    with patch.object(argparse.ArgumentParser, 'parse_args', return_value=argparse.Namespace(command=None)):
        result = main()
        assert result == 1


def test_cli_main_list():
    """测试 main 调用 list"""
    from app.cli.device_template import main
    import argparse

    ns = argparse.Namespace(
        command="list",
        template_dir="",
        category=None,
        json=False,
    )

    with patch.object(argparse.ArgumentParser, 'parse_args', return_value=ns):
        result = main()
        assert result == 0

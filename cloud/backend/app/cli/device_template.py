#!/usr/bin/env python3
"""
设备模板 CLI 管理工具 (P6 配置驱动设备接入)

命令:
    list      - 列出所有已加载的设备模板
    add       - 新增设备模板（从 YAML 文件导入）
    validate  - 验证 YAML 模板文件格式

用法:
    python -m app.cli.device_template list [--category CATEGORY]
    python -m app.cli.device_template add FILE
    python -m app.cli.device_template validate FILE [FILE ...]
"""
import argparse
import sys
import json
from pathlib import Path


def _get_template_loader(template_dir: str = ""):
    """获取模板加载器（带路径处理）"""
    from app.gateway.template_loader import TemplateLoader, get_template_loader

    if template_dir:
        loader = TemplateLoader(template_dir=template_dir)
        loader.load_all()
        return loader
    return get_template_loader()


def cmd_list(args: argparse.Namespace) -> int:
    """list 命令：列出设备模板"""
    loader = _get_template_loader(args.template_dir)

    if args.category:
        templates = loader.get_by_category(args.category)
        if not templates:
            print(f"类别 '{args.category}' 下无模板")
            return 0
    else:
        templates = loader.list_all()

    if args.json:
        result = [t.to_dict() for t in templates]
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*70}")
        print(f"设备模板列表 ({len(templates)} 个)")
        print(f"{'='*70}")
        for t in templates:
            print(f"\n  device_type  : {t.device_type}")
            print(f"  manufacturer : {t.manufacturer}")
            print(f"  model        : {t.model}")
            print(f"  category     : {t.category}")
            print(f"  protocol     : {t.protocol}")
            print(f"  registers    : {len(t.registers)} 个数据点")
            print(f"  source       : {t.source_file}")
        print(f"\n{'='*70}")

    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """add 命令：新增设备模板"""
    loader = _get_template_loader(args.template_dir)
    file_path = Path(args.file).resolve()

    if not file_path.exists():
        print(f"错误: 文件不存在 - {file_path}", file=sys.stderr)
        return 1

    if not file_path.suffix in (".yaml", ".yml"):
        print(f"错误: 不是 YAML 文件 - {file_path}", file=sys.stderr)
        return 1

    # 先验证
    from app.gateway.template_loader import TemplateLoader
    validation = TemplateLoader.validate_template_file(str(file_path))
    if not validation["valid"]:
        print(f"验证失败:", file=sys.stderr)
        for err in validation["errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if validation["warnings"]:
        print(f"警告:")
        for warn in validation["warnings"]:
            print(f"  - {warn}")

    # 加载并索引
    template = loader.add_template_from_file(str(file_path))
    print(f"\n✓ 模板已添加: {template.device_type}")
    print(f"  制造商: {template.manufacturer}  型号: {template.model}")
    print(f"  类别: {template.category}  协议: {template.protocol}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """validate 命令：验证模板文件"""
    from app.gateway.template_loader import TemplateLoader

    all_valid = True
    for file_path in args.files:
        path = Path(file_path).resolve()
        print(f"\n检查: {path}")

        validation = TemplateLoader.validate_template_file(str(path))

        if validation["valid"]:
            print(f"  结果: ✓ 通过")
        else:
            print(f"  结果: ✗ 失败")
            all_valid = False

        for err in validation["errors"]:
            print(f"  错误: {err}")

        for warn in validation["warnings"]:
            print(f"  警告: {warn}")

    return 0 if all_valid else 1


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="天链V3 设备模板管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s list                          # 列出所有模板
  %(prog)s list --category inverter       # 按类别筛选
  %(prog)s list --json                    # JSON 格式输出
  %(prog)s add templates/new_device.yaml  # 添加模板
  %(prog)s validate templates/*.yaml      # 验证模板文件
        """,
    )

    parser.add_argument(
        "--template-dir", "-d",
        default="",
        help="自定义模板目录路径",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list 子命令
    parser_list = subparsers.add_parser("list", help="列出设备模板")
    parser_list.add_argument("--category", "-c", help="按类别筛选")
    parser_list.add_argument("--json", "-j", action="store_true", help="JSON 格式输出")

    # add 子命令
    parser_add = subparsers.add_parser("add", help="新增设备模板")
    parser_add.add_argument("file", help="YAML 模板文件路径")

    # validate 子命令
    parser_validate = subparsers.add_parser("validate", help="验证模板文件")
    parser_validate.add_argument("files", nargs="+", help="要验证的 YAML 文件")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "list":
        return cmd_list(args)
    elif args.command == "add":
        return cmd_add(args)
    elif args.command == "validate":
        return cmd_validate(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

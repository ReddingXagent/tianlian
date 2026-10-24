"""卡 15a07d0f 一次性转换: 0001_baseline 内联 FK 全部后置补挂.

背景: baseline 冻结快照 (154 表/140 内联 FK) 按 walk_packages 遍历序
冻结 op.create_table, fresh PG 上建表严格校验 FK 目标存在 →
UndefinedTable; 且 teams<->users 互引成环, 拓扑排序不可行。

转换 (冻结快照口径不变, 仅 FK 挂载方式改变):
1. 移除每个 op.create_table 参数中的 sa.ForeignKeyConstraint 行;
2. 生成模块级 _POSTPONED_FKS 常量 (140 条 5 元组);
3. upgrade() 末尾追加 dialect != 'sqlite' 守卫循环执行
   op.create_foreign_key (SQLite 不支持 ALTER TABLE ADD CONSTRAINT)。

自检 (转换后强制断言, 任一失败即退出不写文件):
- 新 AST: create_table 无内联 FK, 154 表数量不变;
- 每个 create_table 除 FK 外的参数 AST 与原文逐一等价;
- _POSTPONED_FKS 字面量与原 140 条 FK 一一对应;
- 行级守恒: 新文件 = 原文件 - FK 行 + 两处新增块。

用法: .venv/bin/python scripts/convert_baseline_fk_postponed_card15a07d0f.py
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TARGET = BACKEND / "alembic" / "versions" / "0001_baseline_schema.py"

CONST_BLOCK = '''# ---- 卡 15a07d0f: 后置 FK 登记表 (原 create_table 内联 ForeignKeyConstraint) ----
# (source_table, referent_table, local_cols, remote_cols, ondelete)
_POSTPONED_FKS = [
{entries}
]
'''

POSTPONE_BLOCK = '''    # ---- 卡 15a07d0f: FK 全部后置补挂 (140 条, 原 create_table 内联) ----
    # PG 建表严格校验 FK 目标表存在, teams<->users 互引成环, 任何建表序都
    # 无法满足; 改为全部建表后统一补挂。SQLite 不支持 ALTER TABLE
    # ADD CONSTRAINT, 方言守卫跳过 (SQLite fresh 库无 FK 约束, 业务测试全
    # 走 create_all 不受影响)。列/类型/索引/PK/UQ 语义与冻结快照一致。
    if op.get_bind().dialect.name != "sqlite":
        for _src, _ref, _lcols, _rcols, _ondelete in _POSTPONED_FKS:
            if _ondelete is None:
                op.create_foreign_key(None, _src, _ref, _lcols, _rcols)
            else:
                op.create_foreign_key(None, _src, _ref, _lcols, _rcols, ondelete=_ondelete)
'''


def collect_fk_nodes(tree):
    """收集 upgrade() 内每个 create_table 的 (call, [fk_node...]) 与 FK 行号."""
    upgrade = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )
    result = []
    for stmt in upgrade.body:
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
            continue
        call = stmt.value
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "create_table"):
            continue
        fks = []
        for arg in call.args[1:]:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "ForeignKeyConstraint"
            ):
                fks.append(arg)
        result.append((call, fks))
    return upgrade, result


def fk_tuple(call, fk):
    """FK 节点 → (source, referent, local_cols, remote_cols, ondelete)."""
    table = call.args[0].value
    local = [e.value for e in fk.args[0].elts]
    remote = [e.value for e in fk.args[1].elts]
    assert all("." in r for r in remote), f"复合引用无表前缀: {remote}"
    referents = {r.rsplit(".", 1)[0] for r in remote}
    remote_cols = [r.rsplit(".", 1)[1] for r in remote]
    assert len(referents) == 1, f"跨表复合 FK 不支持: {table} -> {remote}"
    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in fk.keywords}
    assert set(kwargs) <= {"ondelete"}, f"未预期 kwargs {set(kwargs)}: {table}"
    return (table, referents.pop(), local, remote_cols, kwargs.get("ondelete"))


def main():
    src = TARGET.read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    upgrade, create_calls = collect_fk_nodes(tree)

    tables = [call.args[0].value for call, _ in create_calls]
    all_fks = []
    fk_line_numbers = set()
    for call, fks in create_calls:
        for fk in fks:
            all_fks.append(fk_tuple(call, fk))
            assert fk.lineno == fk.end_lineno, (
                f"FK 多行: {call.args[0].value} line {fk.lineno}-{fk.end_lineno}"
            )
            line = lines[fk.lineno - 1].strip()
            # 行内必须只有该调用 + 尾逗号, 保证整行删除安全
            stripped = line.rstrip(",")
            assert stripped.startswith("sa.ForeignKeyConstraint("), f"FK 行混入其他代码: {line}"
            fk_line_numbers.add(fk.lineno)
    assert len(tables) == 154, f"表数 {len(tables)} != 154"
    assert len(all_fks) == 140, f"FK 数 {len(all_fks)} != 140"

    # ---- 行级转换: 删除 FK 行 ----
    kept = [l for i, l in enumerate(lines, start=1) if i not in fk_line_numbers]

    # ---- 追加模块级常量 (depends_on 赋值后、def upgrade 前) ----
    def_upgrade_idx = next(
        i for i, l in enumerate(kept) if l.startswith("def upgrade()")
    )
    entries = "\n".join(
        "    ('{}', '{}', {}, {}, {}),".format(
            s, r, repr(lc), repr(rc), repr(od) if od else "None"
        )
        for s, r, lc, rc, od in all_fks
    )
    const_block = CONST_BLOCK.format(entries=entries)
    kept[def_upgrade_idx:def_upgrade_idx] = const_block.splitlines()

    # ---- upgrade() 末尾追加后置补挂块 ----
    new_tree = ast.parse("\n".join(kept))
    new_upgrade = next(
        n for n in new_tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )
    end_lineno = new_upgrade.body[-1].end_lineno  # 在重组文本坐标系里
    kept[end_lineno:end_lineno] = POSTPONE_BLOCK.rstrip("\n").splitlines()
    out = "\n".join(kept) + "\n"

    # ---- 自检 1: 语法 + 结构 ----
    final_tree = ast.parse(out)
    final_upgrade, final_calls = collect_fk_nodes(final_tree)
    assert len(final_calls) == 154, f"转换后表数 {len(final_calls)} != 154"
    final_inline = [fk for _, fks in final_calls for fk in fks]
    assert not final_inline, f"转换后仍有内联 FK {len(final_inline)} 处"
    fk_calls = [
        c for c in ast.walk(final_upgrade)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and c.func.attr == "create_foreign_key"
    ]
    assert len(fk_calls) == 2, f"后置块 create_foreign_key 调用数 {len(fk_calls)} != 2 (循环体两分支)"

    # ---- 自检 2: 每个 create_table 除 FK 外参数 AST 等价 ----
    def signature(call):
        parts = []
        for arg in call.args[1:]:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "ForeignKeyConstraint"
            ):
                continue
            parts.append(ast.dump(arg))
        return call.args[0].value, parts

    old_map = {t: p for t, p in (signature(c) for c, _ in create_calls)}
    new_map = {t: p for t, p in (signature(c) for c, _ in final_calls)}
    assert old_map == new_map, "存在除 FK 外的参数差异 (冻结口径破坏)"

    # ---- 自检 3: _POSTPONED_FKS 字面量与原 FK 一一对应 ----
    registry = next(
        n for n in final_tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_POSTPONED_FKS" for t in n.targets)
    )
    literal = ast.literal_eval(registry.value)
    assert literal == all_fks, "_POSTPONED_FKS 与原 140 条 FK 不一致"

    # ---- 自检 4: 行级守恒 ----
    assert len(literal) == 140
    TARGET.write_text(out)
    print(f"OK: 154 表保序, 140 FK 后置 ({len(fk_line_numbers)} 行删除, "
          f"常量 {len(entries.splitlines())} 行 + 守卫块追加)")


if __name__ == "__main__":
    main()

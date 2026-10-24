"""卡 15a07d0f 静态守护: baseline 0001 FK 全部后置补挂。

缺陷: 0001_baseline 冻结快照按 walk_packages 遍历序 (≈字母序) 冻结
op.create_table, 内联 FK 在 PG 严格校验下报 UndefinedTable; 且
teams<->users 互引成环, 任何建表序都无法满足。修复方案 (验收口径 1):
create_table 去内联 ForeignKeyConstraint, 全部建完后用
op.create_foreign_key 后置补挂; SQLite 不支持 ALTER TABLE ADD
CONSTRAINT, 后置段须有方言守卫跳过。

本测试静态锁定不变量, 防回归:
1. op.create_table 参数中不得再出现内联 sa.ForeignKeyConstraint;
2. 模块级 _POSTPONED_FKS 覆盖全部后置 FK, 数量 140 (冻结口径),
   源表/引用表均在 154 表集合内, 列名真实存在于对应表;
3. op.create_foreign_key 只能出现在 dialect != 'sqlite' 守卫分支内。
"""
import ast
import importlib.util
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _BACKEND_DIR / "alembic" / "versions" / "0001_baseline_schema.py"

# 冻结口径数量锁 (卡 6f5a35a2 快照 + 卡 15a07d0f 后置改写)
_FROZEN_TABLE_COUNT = 154
_FROZEN_FK_COUNT = 140


def _load_baseline_module():
    spec = importlib.util.spec_from_file_location(
        "baseline_0001_card15a07d0f", _BASELINE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_fn(tree):
    return next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )


def _iter_calls(node, attr_name):
    """遍历 AST, yield 指定 alembic op 调用节点 (如 create_table)."""
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == attr_name
        ):
            yield sub


def test_baseline_create_table_has_no_inline_fk():
    """不变量 1: create_table 不得内联 ForeignKeyConstraint (PG 建表序断裂根因)."""
    tree = ast.parse(_BASELINE_PATH.read_text())
    violations = []
    for create_call in _iter_calls(_upgrade_fn(tree), "create_table"):
        table = create_call.args[0].value
        for arg in create_call.args[1:]:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "ForeignKeyConstraint"
            ):
                violations.append(f"{table} (line {arg.lineno})")
    assert not violations, (
        f"0001_baseline create_table 内联 FK 违规 {len(violations)} 处 "
        f"(PG UndefinedTable 根因, 应后置到 _POSTPONED_FKS): {violations[:10]}"
    )


def test_baseline_table_count_frozen_154():
    """辅助锁: 154 表冻结口径不变."""
    tree = ast.parse(_BASELINE_PATH.read_text())
    tables = [c.args[0].value for c in _iter_calls(_upgrade_fn(tree), "create_table")]
    assert len(tables) == _FROZEN_TABLE_COUNT
    assert len(set(tables)) == _FROZEN_TABLE_COUNT


def test_postponed_fks_registry_present_and_valid():
    """不变量 2: _POSTPONED_FKS 存在, 数量=140, 结构合法."""
    module = _load_baseline_module()
    registry = getattr(module, "_POSTPONED_FKS", None)
    assert isinstance(registry, list) and registry, "_POSTPONED_FKS 缺失或为空"

    tree = ast.parse(_BASELINE_PATH.read_text())
    tables = {c.args[0].value for c in _iter_calls(_upgrade_fn(tree), "create_table")}
    table_cols = {}
    for c in _iter_calls(_upgrade_fn(tree), "create_table"):
        cols = set()
        for arg in c.args[1:]:
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "Column":
                cols.add(arg.args[0].value)
        table_cols[c.args[0].value] = cols

    assert len(registry) == _FROZEN_FK_COUNT, (
        f"后置 FK 数量 {len(registry)} != 冻结口径 {_FROZEN_FK_COUNT}"
    )
    for i, entry in enumerate(registry):
        assert isinstance(entry, tuple) and len(entry) == 5, f"[{i}] 应为 5 元组: {entry}"
        source, referent, local_cols, remote_cols, ondelete = entry
        assert source in tables, f"[{i}] 源表 {source} 不在 154 表集合"
        assert referent in tables, f"[{i}] 引用表 {referent} 不在 154 表集合"
        assert isinstance(local_cols, list) and isinstance(remote_cols, list)
        for col in local_cols:
            assert col in table_cols[source], f"[{i}] {source}.{col} 列不存在"
        for col in remote_cols:
            assert col in table_cols[referent], f"[{i}] {referent}.{col} 列不存在"
        assert ondelete is None or ondelete in ("CASCADE", "SET NULL"), (
            f"[{i}] 未预期的 ondelete: {ondelete}"
        )


def test_create_foreign_key_sqlite_guarded():
    """不变量 3: create_foreign_key 只能在 dialect != 'sqlite' 守卫分支内."""
    tree = ast.parse(_BASELINE_PATH.read_text())
    upgrade = _upgrade_fn(tree)

    all_fk_calls = list(_iter_calls(upgrade, "create_foreign_key"))
    assert all_fk_calls, "upgrade() 中未找到 op.create_foreign_key 后置补挂"

    guarded = set()
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.unparse(node.test)
        if "sqlite" in test_src and "!=" in test_src and "dialect" in test_src:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "create_foreign_key"
                ):
                    guarded.add(sub.lineno)

    unguarded = [c.lineno for c in all_fk_calls if c.lineno not in guarded]
    assert not unguarded, (
        f"create_foreign_key 脱离 sqlite 守卫 (行 {unguarded}) — "
        "SQLite fresh-db upgrade head 测试会 NotImplementedError"
    )


def test_postponed_fks_cover_all_cross_table_dependencies():
    """不变量 2 补充: 140 条后置 FK 的 (源表, 引用表) 去重集合非空且覆盖成环节."""
    module = _load_baseline_module()
    registry = getattr(module, "_POSTPONED_FKS", None)
    if not registry:
        pytest.fail("_POSTPONED_FKS 缺失")
    pairs = {(src, ref) for src, ref, *_ in registry}
    # teams<->users 互引是建表序断裂的最小环, 双向都必须在后置表里
    assert ("teams", "users") in pairs, "teams->users FK 未后置"
    assert ("users", "teams") in pairs, "users->teams FK 未后置"

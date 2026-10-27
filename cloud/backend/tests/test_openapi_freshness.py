"""openapi.json 新鲜度守卫 (卡 30662646)。

从 app 重新生成 spec，与仓库 backend/openapi.json 做 operations
(METHOD + path) 集合级比对，锁住 spec 与代码的漂移。
新增/删除端点后须重导出 openapi.json（含 root/docs/backend/docs 三副本）。
"""


def _ops(spec: dict) -> set:
    ops = set()
    for path, methods in spec.get("paths", {}).items():
        for method in methods:
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
                ops.add(f"{method.upper()} {path}")
    return ops


def test_openapi_json_matches_app() -> None:
    import json
    from pathlib import Path

    from app.main import app

    repo_spec_path = Path(__file__).resolve().parents[1] / "openapi.json"
    repo_spec = json.loads(repo_spec_path.read_text(encoding="utf-8"))

    fresh_ops = _ops(app.openapi())
    repo_ops = _ops(repo_spec)

    missing = fresh_ops - repo_ops  # 代码有、spec 无 → spec 陈旧
    stale = repo_ops - fresh_ops  # spec 有、代码无 → 端点已删未同步

    assert not missing, (
        f"openapi.json 落后于代码，缺少 {len(missing)} 个端点（重导出后提交）: "
        f"{sorted(missing)[:10]}"
    )
    assert not stale, (
        f"openapi.json 含 {len(stale)} 个代码中已不存在的端点（重导出后提交）: "
        f"{sorted(stale)[:10]}"
    )

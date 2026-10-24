# 0001 Baseline 冻结方案（方案A）— 供文曲审查

> 工作卡 6f5a35a2 · 决策卡 06158913 · 丁哥 2026-08-21 01:4x 批准
> 作者: 石猴 · 分支 feature/frontend-api-integration

## 1. 问题背景

`alembic/versions/0001_baseline_schema.py` 自 2d3092def（2026-07-23）引入起，
`upgrade()` 动态 import 当前 `app.models` 并 `Base.metadata.create_all` 建表。
后果：**baseline 随模型漂移** —— 每次模型变更，"全新库 upgrade head" 链路里
baseline 都会直接建出最新表结构，与后续手写迁移产生重复定义。历史上已炸 6 次
（duplicate column / relation already exists 等），全部靠在迁移里加幂等守卫打补丁
（0c60e5c087e0 / 31cdf3eac / c4b8e2f9a1d0 / f5a6b7c8d9e0 / 9a3c7e1f4d82 等）。

根因：baseline 的语义应该是「baseline 时期 schema 的固定快照」，而不是
「当前模型结构的投影」。

## 2. 方案

1. **冻结基准**：baseline 引入 commit `2d3092def`。该 commit 时刻的
   `app/models/__init__.py` 有坏 import（`ApprovalStatus`/`StationVinWhitelist`），
   3 分钟后的 `c0f535d1d`（同日 22:55:26）修复。故冻结基准取 **c0f535d1d**
   ——包含 baseline 的第一个模型可完整 import 的状态，差异仅限这 3 分钟内的
   fleet 提交，与 baseline 语义等价。
2. **生成方式**：`git archive c0f535d1d` 导出该时期 backend → 用当前 `.venv`
   的 alembic autogenerate 对空 SQLite 库导出静态 DDL。快照口径与旧动态
   baseline 完全等价：`walk_packages` 遍历 `app.models`（含未被 `__init__`
   显式导出的模块，如 `vehicle.py` / `enterprise_recharge.py`），共 154 张表。
3. **重写 0001**：纯静态 `op.create_table`/`op.create_index` 快照，**禁止
   import app.***。revision id `0001_baseline`、`down_revision=None` 不变，
   已 stamp 的库不受影响，生产库永不执行本迁移。
4. **catch-up 迁移**（新文件 `202608210900_baseline_freeze_catchup.py`）：
   旧动态 baseline 曾"顺手"吸收了 6 张后加表 + 9 个自动命名索引
   （模型均在 c0f535d1d 之后新增、从未有专属迁移，历史全靠运行时
   create_all 兜底）。冻结后这些必须由迁移显式补齐，沿 c4b8e2f9a1d0 的
   inspector 幂等守卫风格（生产 PG 已有这些表 → 全部跳过，安全）：
   - 表：`runbooks`、`inspection_templates`、`inspection_results`、
     `fund_pools`、`fund_pool_transactions`、`enterprise_device_grants`
   - 索引：`tenant_brands.ix_tenant_brands_team_id` 等 9 个
     `Column(index=True)` 自动 `ix_*` 索引（对应迁移建表时只建了显式命名索引）

## 3. 冻结纪律（写进 0001 文件头）

- 禁止 import app.* —— baseline 不再随当前模型漂移
- 后续模型变更必须走新增迁移，不得回填 0001
- revision id / down_revision 不变

## 4. 三项验证证据（2026-08-21 真实执行）

### a. 全新 SQLite 临时库 upgrade head

```
$ ALEMBIC_DATABASE_URL="sqlite:////tmp/tl-freeze-verify.db" .venv/bin/python -m alembic upgrade head
... Running upgrade 202608171400 -> 202608201000, fleet_alert_records active 部分唯一索引
... Running upgrade 202608201000 -> 202608210900, baseline 冻结 catch-up
exit=0
$ alembic current → 202608210900 (head)
```

### b. 冻结链最终 schema vs 当前模型（check_schema_drift.py 名称级对比）

```
$ .venv/bin/python scripts/check_schema_drift.py --url sqlite:////tmp/tl-freeze-verify.db
=== Schema Drift Report ===
结论: ✓ 无漂移 (模型与库一致)
汇总: 缺表 0 / 缺列 0 / 缺索引 0 / 孤儿列 0
```

（对照实验：不冻结时的旧动态 baseline 同链路同样零漂移——即冻结后与旧行为
对齐；中间态曾出现缺表 6 / 缺索引 9，即 catch-up 迁移所补内容。）

### c. pytest 迁移链回归

```
$ .venv/bin/python -m pytest tests/test_migration_chain_fresh_db.py -q --timeout=120
1 passed, 5 warnings in 2.01s
```

附加幂等验证：catch-up 在已建表的库上重跑 exit=0（守卫生效）。

## 5. 已知良性差异（未纳入 catch-up，需文曲知悉）

alembic autogenerate 对冻结链库 vs 当前模型还报告了若干 **nullability /
索引冗余 / 方言类型** 级差异（如 `compliance_checks.team_id NOT NULL`、
`devices.provision_status` VARCHAR→Enum、若干 `ix_*` 冗余索引 drop 建议）。
这些差异在旧动态 baseline 链路上同样不存在于 `check_schema_drift` 的名称级
校验范围（名称级零漂移），且 SQLite 修 nullability 需 batch 模式、风险大于
收益，故不纳入本次 catch-up。若文曲认为需要，可另开卡做 batch_alter_table
美化迁移。

## 6. 生产部署步骤（本 commit 只改脚本，未执行）

1. **快照备份**：deploy.sh 自带的 tar 备份（`/opt/tianlian-cloud_backup_*.tar.gz`）
   + 手动 `pg_dump` 数据库快照。
2. **部署**：`bash deploy.sh`（新逻辑：alembic upgrade head 后显式校验
   `alembic current == head`，不等则显式告警——冻结后版本链必须真正走到 head，
   create_all 兜底补不了种子/索引/迁移语义）。
3. **校验**：服务器上 `alembic current` 应为 `202608210900`；
   `venv/bin/python scripts/check_schema_drift.py` 应零漂移；
   `/api/v1/health` 200。
4. 生产库已 stamp 后续版本 → 0001 永不重放；catch-up 的幂等守卫在
   PG 上全部跳过（表已由运行时 create_all 建过）。

## 7. 回滚预案

- 部署层：deploy.sh 原生自动回滚（健康检查超时 → 恢复 tar 备份）。
- 迁移层：`alembic downgrade 202608201000` 只删 catch-up 新建的 9 个索引、
  保留表（与 c4b8e2f9a1d0 同策略，避免误删运行时数据）；0001 本身在
  生产永不执行，无需 downgrade。
- 代码层：revert 本 commit 即回到动态 baseline（版本链兼容：revision id 未变）。

## 8. 变更清单

| 文件 | 变更 |
|------|------|
| `backend/alembic/versions/0001_baseline_schema.py` | 重写为 154 表静态快照（3952 行） |
| `backend/alembic/versions/202608210900_baseline_freeze_catchup.py` | 新增幂等 catch-up |
| `backend/docs/migrations/0001-baseline-freeze-plan.md` | 本文档 |
| `deploy.sh` | alembic upgrade 后新增 current==head 显式校验 |

未动：`app/models/**`、0001 以外的既有迁移、`docs/contracts/`。

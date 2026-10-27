"""alembic 数据库 URL 解析逻辑单元测试 (卡 b60a1d0d)。

背景: commit bacc9ed17 把 alembic.ini 的 sqlalchemy.url 占位化后, 生产
`alembic upgrade head` 报 'could not translate host name "ALEMBIC_HOST"'。
根因是 env.py 只读环境变量、不读 backend/.env 的 DATABASE_URL。解析逻辑抽到
alembic_url_resolver.resolve_alembic_database_url, 这里覆盖三个核心场景 + 优先级。

注意: conftest 会向 os.environ 注入 DATABASE_URL=sqlite, 故每个用例都显式传入
干净的 env dict, 避免测试环境污染解析结果。
"""
from pathlib import Path

import pytest

from alembic_url_resolver import resolve_alembic_database_url

# alembic.ini 里的占位 URL (生产漏配 DATABASE_URL 时的回退值)
PLACEHOLDER_INI_URL = (
    "postgresql://ALEMBIC_USER:ALEMBIC_PASSWORD@ALEMBIC_HOST:5432/ALEMBIC_DB"
)
REAL_PG_URL = "postgresql://tianlian:secret@db.example.com:5432/tianlian_v3"


def _write_env_file(tmp_path: Path, body: str) -> Path:
    dotenv = tmp_path / ".env"
    dotenv.write_text(body, encoding="utf-8")
    return dotenv


# ── 场景 1: .env 有 DATABASE_URL → 用它 ─────────────────────────────────
def test_dotenv_database_url_used_when_present(tmp_path):
    dotenv = _write_env_file(tmp_path, f"DATABASE_URL={REAL_PG_URL}\n")
    url = resolve_alembic_database_url(
        PLACEHOLDER_INI_URL, env={}, dotenv_path=dotenv
    )
    assert url == REAL_PG_URL


def test_dotenv_value_strips_surrounding_quotes(tmp_path):
    # python-dotenv 会剥掉引号; 解析后应是裸 URL
    dotenv = _write_env_file(tmp_path, f'DATABASE_URL="{REAL_PG_URL}"\n')
    url = resolve_alembic_database_url(
        PLACEHOLDER_INI_URL, env={}, dotenv_path=dotenv
    )
    assert url == REAL_PG_URL


def test_dotenv_absent_falls_back_to_real_ini_url(tmp_path):
    # .env 不存在 + ini 是真实 URL → 用 ini
    missing = tmp_path / ".env"
    url = resolve_alembic_database_url(REAL_PG_URL, env={}, dotenv_path=missing)
    assert url == REAL_PG_URL


# ── 场景 2: 优先级 ───────────────────────────────────────────────────────
def test_env_database_url_beats_dotenv(tmp_path):
    dotenv = _write_env_file(tmp_path, f"DATABASE_URL={REAL_PG_URL}\n")
    env_url = "postgresql://env:pw@env-host:5432/envdb"
    url = resolve_alembic_database_url(
        PLACEHOLDER_INI_URL, env={"DATABASE_URL": env_url}, dotenv_path=dotenv
    )
    assert url == env_url


def test_alembic_database_url_beats_database_url_env(tmp_path):
    # ALEMBIC_DATABASE_URL (显式 override, 向后兼容本地 SQLite 验证) 优先于 DATABASE_URL
    env = {
        "ALEMBIC_DATABASE_URL": "sqlite:///./override.db",
        "DATABASE_URL": REAL_PG_URL,
    }
    url = resolve_alembic_database_url(
        PLACEHOLDER_INI_URL, env=env, dotenv_path=tmp_path / ".env"
    )
    assert url == "sqlite:///./override.db"


def test_empty_or_blank_env_values_are_ignored(tmp_path):
    # 空字符串 / 纯空白 env 值不算配置, 继续往下找 .env
    dotenv = _write_env_file(tmp_path, f"DATABASE_URL={REAL_PG_URL}\n")
    url = resolve_alembic_database_url(
        PLACEHOLDER_INI_URL, env={"DATABASE_URL": "   "}, dotenv_path=dotenv
    )
    assert url == REAL_PG_URL


def test_dotenv_without_database_url_key_falls_through_to_ini(tmp_path):
    # .env 存在但无 DATABASE_URL 键 → 落到 ini; ini 是真实 URL → 用 ini
    dotenv = _write_env_file(tmp_path, "OTHER_KEY=foo\nDB_TYPE=postgres\n")
    url = resolve_alembic_database_url(
        REAL_PG_URL, env={}, dotenv_path=dotenv
    )
    assert url == REAL_PG_URL


# ── 场景 3: 占位符 → 明确报错 (核心: 别让 psycopg2 报天书) ────────────────
def test_placeholder_ini_url_raises_clear_error(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        resolve_alembic_database_url(
            PLACEHOLDER_INI_URL, env={}, dotenv_path=tmp_path / ".env"
        )
    msg = str(exc.value)
    assert "ALEMBIC_HOST" in msg          # 指明占位符
    assert "DATABASE_URL" in msg          # 给出修复指引
    # 绝不能是把占位串直接交给驱动后的底层天书
    assert "could not translate host name" not in msg


def test_placeholder_env_value_raises_clear_error(tmp_path):
    # 即便 env 里有值, 若仍是占位符 (deploy 只塞了模板), 也要 fail-fast
    with pytest.raises(RuntimeError) as exc:
        resolve_alembic_database_url(
            REAL_PG_URL,
            env={"DATABASE_URL": PLACEHOLDER_INI_URL},
            dotenv_path=tmp_path / ".env",
        )
    assert "ALEMBIC_HOST" in str(exc.value)


def test_placeholder_dotenv_value_raises_clear_error(tmp_path):
    # .env 里的 DATABASE_URL 若是占位符 (运维复制了 alembic.ini 模板), 也要报错
    dotenv = _write_env_file(tmp_path, f"DATABASE_URL={PLACEHOLDER_INI_URL}\n")
    with pytest.raises(RuntimeError) as exc:
        resolve_alembic_database_url(
            REAL_PG_URL, env={}, dotenv_path=dotenv
        )
    assert "ALEMBIC_HOST" in str(exc.value)


def test_real_url_passes_guard(tmp_path):
    # 真实 URL 不含占位符 → 正常返回, 不报错
    url = resolve_alembic_database_url(
        REAL_PG_URL, env={}, dotenv_path=tmp_path / ".env"
    )
    assert url == REAL_PG_URL

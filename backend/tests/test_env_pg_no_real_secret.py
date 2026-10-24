"""
[卡ad37abf1] docker/.env.pg 真实 JWT SECRET_KEY 泄露 — 安全回归测试

守护契约: docker/.env.pg 是入库的占位符模板, SECRET_KEY 必须是
CHANGE_ME_BEFORE_DEPLOY 占位样式; 真实密钥必须在部署时由服务器生成注入,
严禁真实密钥入库。(历史上曾误提交 63 位真实生成密钥。)
"""
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PG = PROJECT_DIR / "docker" / ".env.pg"
PLACEHOLDER = "CHANGE_ME_BEFORE_DEPLOY"


def _secret_key_value() -> str:
    text = ENV_PG.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("SECRET_KEY="):
            return stripped.split("=", 1)[1].strip()
    raise AssertionError(f"{ENV_PG} 中未找到 SECRET_KEY 行")


def test_env_pg_secret_key_is_placeholder():
    """SECRET_KEY 值必须为占位符, 不含真实密钥。"""
    value = _secret_key_value()
    assert PLACEHOLDER in value, (
        f"docker/.env.pg SECRET_KEY 应为占位符样式 (含 '{PLACEHOLDER}'), "
        f"实际值疑似真实密钥: {value[:8]}...(长度{len(value)})"
    )


def test_env_pg_secret_key_not_real_key_format():
    """占位符之外, 不得是高熵长随机串 (真实生成密钥的格式特征)。"""
    value = _secret_key_value()
    # 真实密钥特征: >=32 位且混合大小写字母/数字/符号的高熵串
    looks_real = (
        len(value) >= 32
        and re.search(r"[a-z]", value)
        and re.search(r"[A-Z]", value)
        and (re.search(r"[0-9_\-+/=]", value) is not None)
    )
    assert not looks_real, (
        f"docker/.env.pg SECRET_KEY 呈真实密钥格式 (长度{len(value)}高熵串), "
        "真实密钥严禁入库, 应改为占位符并在部署时注入"
    )

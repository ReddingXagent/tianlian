#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 模型配置服务测试
"""
import pytest
from app.services.ai_model_config import AIModelManager, TaskType, ENV_API_KEYS, CONFIG_FILE
import os

class TestAIModelConfig:
    def test_task_type_constants(self):
        assert TaskType.LOG_ANALYSIS == "log_analysis"
        assert TaskType.FAULT_CLASSIFY == "fault_classify"
        assert TaskType.ROOT_CAUSE == "root_cause"
        assert TaskType.REPAIR_SUGGEST == "repair_suggest"
        assert TaskType.PREVENTIVE == "preventive"

    def test_env_api_keys_mapping(self):
        assert "cloud_provider-token" in ENV_API_KEYS
        assert ENV_API_KEYS["cloud_provider-token"] == "ALIYUN_TOKEN_API_KEY"

    def test_config_file_path(self):
        assert isinstance(CONFIG_FILE, str)
        assert CONFIG_FILE.endswith("ai_model_config.json")

    def test_ai_model_manager_singleton(self):
        mgr1 = AIModelManager()
        mgr2 = AIModelManager()
        assert mgr1 is mgr2

    def test_get_providers_returns_list(self):
        mgr = AIModelManager()
        providers = mgr.get_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_get_model_by_name(self):
        mgr = AIModelManager()
        # 使用实际存在于配置中的模型名
        model = mgr.get_model_by_name("TP/DS4P")
        assert model is not None
        assert model.get("model_id") == "llm-pro-a"

    def test_get_model_for_task(self):
        mgr = AIModelManager()
        model = mgr.get_model_for_task(TaskType.LOG_ANALYSIS)
        assert model is not None
        assert isinstance(model, dict)

    def test_to_config_dict_hides_api_keys(self):
        mgr = AIModelManager()
        config = mgr.to_config_dict()
        assert "providers" in config
        assert "task_mappings" in config
        for p in config["providers"]:
            if p.get("api_key"):
                assert "***" in p["api_key"]

    def test_get_all_mappings(self):
        mgr = AIModelManager()
        mappings = mgr.get_all_mappings()
        assert isinstance(mappings, dict)
        assert TaskType.LOG_ANALYSIS in mappings


# ─────────────────────────────────────────────────────────────
# 异常处理 + 输入校验补全
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def iso(monkeypatch, tmp_path):
    """隔离全局单例: CONFIG_FILE 指向临时路径 + 备份/恢复内存配置, 不污染真实文件"""
    import copy
    import app.services.ai_model_config as mod
    cfg_path = tmp_path / "ai_model_config.json"
    monkeypatch.setattr(mod, "CONFIG_FILE", str(cfg_path))
    mgr = mod.AIModelManager()
    backup = copy.deepcopy(mgr.config)
    yield mgr, cfg_path
    mgr.config = backup


# ─── 任务1+2: 文件 I/O 容错 + 原子写 ───

class TestConfigIORobustness:
    def test_load_corrupted_json_falls_back_to_default(self, monkeypatch, tmp_path):
        """配置文件 JSON 损坏 → 回退 DEFAULT_CONFIG, 不抛"""
        import app.services.ai_model_config as mod
        bad = tmp_path / "corrupt.json"
        bad.write_text("{ 这是坏掉的 json }}}", encoding="utf-8")
        monkeypatch.setattr(mod, "CONFIG_FILE", str(bad))
        mgr = mod.AIModelManager()
        mgr._load()  # 不应抛
        # 回退默认结构(数量+名称一致; api_key 会被 _apply_env_overrides 填充, 不比较)
        assert [p["name"] for p in mgr.config["providers"]] == \
               [p["name"] for p in mod.DEFAULT_CONFIG["providers"]]
        assert mgr.config["fallback_strategy"] == mod.DEFAULT_CONFIG["fallback_strategy"]

    def test_load_missing_file_falls_back_to_default(self, monkeypatch, tmp_path):
        """配置文件不存在 → 回退默认(回归保护)"""
        import app.services.ai_model_config as mod
        monkeypatch.setattr(mod, "CONFIG_FILE", str(tmp_path / "nope.json"))
        mgr = mod.AIModelManager()
        mgr._load()
        assert [p["name"] for p in mgr.config["providers"]] == \
               [p["name"] for p in mod.DEFAULT_CONFIG["providers"]]

    def test_save_atomic_writes_valid_json_no_temp_residue(self, iso):
        """_save 原子写: 成功后正式文件存在、内容合法、无 .tmp 残留"""
        import json
        mgr, cfg_path = iso
        mgr._save()
        assert cfg_path.exists()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "providers" in data
        assert not [p for p in cfg_path.parent.iterdir() if p.suffix == ".tmp"]

    def test_save_swallows_io_error_without_corrupting(self, monkeypatch, iso):
        """_save 写盘失败被吞: 不向上抛 + 正式文件保持上次合法内容(不被半截写入损坏)"""
        import json as _json
        import app.services.ai_model_config as mod
        mgr, cfg_path = iso
        mgr._save()                       # 先落盘一份合法内容
        good = cfg_path.read_text(encoding="utf-8")

        def _boom(*a, **kw):
            raise OSError("disk full")
        monkeypatch.setattr(mod.json, "dump", _boom)
        mgr._save()                       # 不应抛
        assert cfg_path.read_text(encoding="utf-8") == good      # 未被半截写入
        assert not [p for p in cfg_path.parent.iterdir() if p.suffix == ".tmp"]


# ─── 任务4: add_provider 字段校验 ───

class TestAddProviderValidation:
    def test_add_provider_rejects_empty_base_url(self, iso):
        mgr, _ = iso
        before = len(mgr.config["providers"])
        with pytest.raises(ValueError):
            mgr.add_provider({"provider": "llm_generic", "model_id": "x", "name": "X",
                              "base_url": "", "api_key": "sk-abc"})
        assert len(mgr.config["providers"]) == before

    def test_add_provider_rejects_empty_api_key(self, iso):
        mgr, _ = iso
        before = len(mgr.config["providers"])
        with pytest.raises(ValueError):
            mgr.add_provider({"provider": "llm_generic", "model_id": "x", "name": "X",
                              "base_url": "https://a", "api_key": ""})
        assert len(mgr.config["providers"]) == before

    def test_add_provider_rejects_missing_base_url(self, iso):
        mgr, _ = iso
        with pytest.raises(ValueError):
            mgr.add_provider({"provider": "llm_generic", "model_id": "x", "name": "X",
                              "api_key": "sk-abc"})   # 缺 base_url

    def test_add_provider_accepts_valid(self, iso):
        mgr, _ = iso
        n = len(mgr.config["providers"])
        mgr.add_provider({"provider": "llm_generic", "model_id": "x", "name": "NEW",
                          "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1", "api_key": "sk-abc"})
        assert len(mgr.config["providers"]) == n + 1
        assert mgr.config["providers"][-1]["name"] == "NEW"


# ─── 任务5: API Key 遮罩改进 (短 key 全遮罩) ───

class TestApiKeyMasking:
    def test_short_key_fully_masked(self, iso):
        """<=12 字符的 key 全部遮罩为 ***, 不泄露任何前缀"""
        mgr, _ = iso
        mgr.config["providers"] = [{
            "provider": "llm_generic", "model_id": "x", "name": "SHORT",
            "base_url": "https://a", "api_key": "sk-ab", "enabled": True
        }]
        out = mgr.to_config_dict()
        p = [x for x in out["providers"] if x["name"] == "SHORT"][0]
        assert p["api_key"] == "***"
        assert "sk-ab" not in p["api_key"]

    def test_key_at_12_boundary_fully_masked(self, iso):
        """正好 12 字符 → 全遮罩(临界包含)"""
        mgr, _ = iso
        mgr.config["providers"] = [{
            "provider": "llm_generic", "model_id": "x", "name": "B12",
            "base_url": "https://a", "api_key": "abcdefghij12", "enabled": True
        }]
        out = mgr.to_config_dict()
        p = [x for x in out["providers"] if x["name"] == "B12"][0]
        assert p["api_key"] == "***"

    def test_long_key_keeps_prefix(self, iso):
        """>12 字符的 key 保留前 12 字符 + ***"""
        mgr, _ = iso
        key = "sk-1234567890abcdef"  # 19 字符
        mgr.config["providers"] = [{
            "provider": "llm_generic", "model_id": "x", "name": "LONG",
            "base_url": "https://a", "api_key": key, "enabled": True
        }]
        out = mgr.to_config_dict()
        p = [x for x in out["providers"] if x["name"] == "LONG"][0]
        assert p["api_key"] == "sk-123456789***"   # key[:12]
        assert key not in p["api_key"]


# ─── 任务3: _apply_env_overrides 去冗余 elif (行为不变, 回归覆盖) ───

class TestEnvOverrides:
    def test_cloud_provider_token_env_key_applied(self, monkeypatch, iso):
        """cloud_provider-token provider 在 ALIYUN_TOKEN_KEY 环境变量存在时读到 key"""
        import app.services.ai_model_config as mod
        mgr, _ = iso
        mgr.config["providers"] = [{
            "provider": "cloud_provider-token", "model_id": "x", "name": "ALI",
            "base_url": "https://a", "api_key": "", "enabled": True
        }]
        monkeypatch.setattr(mod.os, "environ", {"ALIYUN_TOKEN_KEY": "env-secret"})
        mgr._apply_env_overrides()
        assert mgr.config["providers"][0]["api_key"] == "env-secret"
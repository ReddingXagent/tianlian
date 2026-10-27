"""
AI 模型配置管理 - 支持多模型、多任务映射

架构：
- 支持多个 AI Provider（cloud_provider-token/CodingPlan等）
- 每个任务类型可分配给不同模型
- 配置可通过API动态修改
- 支持 fallback 降级
- API Key 可从环境变量读取（云端部署优先）
"""
import copy
import json
import logging
import os
import threading
from typing import List, Optional

from app.core.url_safety import UnsafeURLError, validate_external_url

logger = logging.getLogger(__name__)


def validate_provider_urls(providers: List[dict]):
    """校验 provider 列表中每个 base_url 指向公网端点(防 SSRF)。

    复用 url_safety.validate_external_url; 任一不安全即抛 UnsafeURLError(ValueError 子类)。
    """
    for provider in providers:
        base_url = provider.get("base_url", "")
        try:
            validate_external_url(base_url)
        except UnsafeURLError:
            raise UnsafeURLError(
                f"provider '{provider.get('name', provider.get('model_id', '?'))}' 的 base_url 不安全(禁止内网/环回/非 http(s) 地址)"
            )

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "ai_model_config.json")

# 环境变量中 API Key 的映射关系 provider_name => env_var
ENV_API_KEYS = {
    "cloud_provider-token": "ALIYUN_TOKEN_API_KEY",
    "llm_generic": "LLM_GENERIC_API_KEY",
    "model_a": "MODELA_API_KEY",
}


class TaskType:
    """诊断任务类型"""
    LOG_ANALYSIS = "log_analysis"        # 日志分析
    FAULT_CLASSIFY = "fault_classify"    # 故障分类
    ROOT_CAUSE = "root_cause"            # 根因分析
    REPAIR_SUGGEST = "repair_suggest"    # 维修建议
    PREVENTIVE = "preventive"            # 预防措施

    CHAT_GENERAL = "chat_general"        # 通用对话

    ALL = [LOG_ANALYSIS, FAULT_CLASSIFY, ROOT_CAUSE, REPAIR_SUGGEST, PREVENTIVE, CHAT_GENERAL]


DEFAULT_CONFIG = {
    "providers": [
        {
            "provider": "cloud_provider-token",
            "model_id": "llm-pro-a",
            "name": "TP/DS4P",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "context_window": 128000,
            "max_tokens": 16000,
            "enabled": True
        },
        {
            "provider": "cloud_provider-token",
            "model_id": "llm-fast-a",
            "name": "TP/DS4F",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "context_window": 128000,
            "max_tokens": 8000,
            "enabled": True
        },
        {
            "provider": "cloud_provider-token",
            "model_id": "llm-b",
            "name": "TP/ModelB5.1",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "context_window": 128000,
            "max_tokens": 16000,
            "enabled": True
        },
        {
            "provider": "cloud_provider-token",
            "model_id": "model_d-k2.6",
            "name": "TP/ModelD",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "context_window": 128000,
            "max_tokens": 16000,
            "enabled": True
        },
        {
            "provider": "cloud_provider-token",
            "model_id": "llm-pro-c",
            "name": "TP/Q3P",
            "base_url": "https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1",
            "api_key": "",
            "context_window": 1000000,
            "max_tokens": 16000,
            "enabled": True
        }
    ],
    "task_mappings": {
        "log_analysis": "TP/ModelB5.1",
        "fault_classify": "TP/DS4F",
        "root_cause": "TP/DS4P",
        "repair_suggest": "TP/ModelB5.1",
        "preventive": "TP/ModelB5.1"
    },
    "fallback_strategy": "next_available"
}


class AIModelManager:
    """AI模型配置管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._load()
        return cls._instance

    def _load(self):
        """加载配置(容错: 文件损坏或不可读时回退默认, 避免单例初始化崩溃)"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = copy.deepcopy(DEFAULT_CONFIG)
                self._save()
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("AI模型配置文件损坏或不可读, 回退默认配置: %s", e)
            self.config = copy.deepcopy(DEFAULT_CONFIG)
        self._apply_env_overrides()

    def _save(self):
        """原子写保存配置(临时文件 + os.replace, 防止中途崩溃损坏; 失败不向上抛)"""
        tmp = CONFIG_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            os.replace(tmp, CONFIG_FILE)
        except OSError as e:
            logger.warning("AI模型配置保存失败, 已忽略: %s", e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                logger.warning("AI模型配置临时文件清理失败: %s", tmp, exc_info=True)

    def _apply_env_overrides(self):
        """从环境变量覆盖 API Key（云端部署优先）"""
        # 全局 fallback: 任意可用的 key
        global_key = os.environ.get("LLM_GENERIC_API_KEY", "") or os.environ.get("MODELA_API_KEY", "")
        for provider in self.config.get("providers", []):
            env_var = ENV_API_KEYS.get(provider.get("provider", ""))
            if env_var and os.environ.get(env_var):
                provider["api_key"] = os.environ[env_var]
            elif global_key and not provider.get("api_key"):
                provider["api_key"] = global_key
            elif provider.get("provider") == "cloud_provider-token" and not provider.get("api_key"):
                # Fallback: read from local config
                provider["api_key"] = os.environ.get("ALIYUN_TOKEN_KEY", "")

    def get_providers(self) -> List[dict]:
        """获取所有启用的provider"""
        return [p for p in self.config["providers"] if p.get("enabled", True)]

    def get_model_by_name(self, name: str) -> Optional[dict]:
        """通过显示名称获取模型配置"""
        for p in self.config["providers"]:
            if p["name"] == name and p.get("enabled", True):
                return p
        return None

    def get_model_by_id(self, model_id: str) -> Optional[dict]:
        """通过模型ID获取配置"""
        for p in self.config["providers"]:
            if p["model_id"] == model_id and p.get("enabled", True):
                return p
        return None

    def get_model_for_task(self, task_type: str) -> Optional[dict]:
        """获取指定任务类型的模型配置"""
        model_name = self.config["task_mappings"].get(task_type)
        if model_name:
            model = self.get_model_by_name(model_name)
            if model:
                return model
        # fallback: 取第一个启用的
        providers = self.get_providers()
        return providers[0] if providers else None

    def update_providers(self, providers: List[dict]):
        """更新provider列表(base_url 先过 SSRF 校验)"""
        validate_provider_urls(providers)
        self.config["providers"] = providers
        self._save()

    def update_task_mapping(self, task_type: str, model_name: str):
        """更新任务映射"""
        if task_type in TaskType.ALL:
            self.config["task_mappings"][task_type] = model_name
            self._save()

    def add_provider(self, provider: dict):
        """添加provider(base_url / api_key 不能为空)"""
        if not provider.get("base_url"):
            raise ValueError("provider.base_url 不能为空")
        if not provider.get("api_key"):
            raise ValueError("provider.api_key 不能为空")
        validate_provider_urls([provider])
        self.config["providers"].append(provider)
        self._save()

    def get_all_mappings(self) -> dict:
        """获取任务映射表"""
        return self.config["task_mappings"]

    @staticmethod
    def _mask_api_key(key: str) -> str:
        """短 key(<=12 字符)整体遮罩, 避免前缀即泄露全部"""
        return key[:12] + "***" if len(key) > 12 else "***"

    @classmethod
    def _is_masked_api_key(cls, value: str) -> bool:
        """判断入参 api_key 是否为 to_config_dict 掩码产物形态（卡 7ada32c8 哨兵判定，
        与掩码逻辑同源派生）。"""
        return value == "***" or value.endswith("***")

    def _restore_masked_keys(self, incoming: List[dict]) -> List[dict]:
        """掩码哨兵回写守卫 (卡 7ada32c8): 入参 provider.api_key 为掩码形态时,
        按 provider+model_id 身份(索引兜底)从存量配置取真实 api_key 回填,
        防止「GET 回填表单 → 不改密钥 → 保存」把掩码串写回覆盖真实密钥。"""
        existing = self.config.get("providers", [])
        for i, p in enumerate(incoming):
            key = p.get("api_key")
            if not key or not self._is_masked_api_key(key):
                continue
            src = next(
                (e for e in existing
                 if e.get("provider") == p.get("provider")
                 and e.get("model_id") == p.get("model_id")),
                existing[i] if i < len(existing) else None,
            )
            if src is not None:
                p["api_key"] = src.get("api_key", "")
        return incoming

    def to_config_dict(self) -> dict:
        """返回完整配置（隐藏API Key）"""
        config = {
            "providers": [],
            "task_mappings": self.config["task_mappings"],
            "fallback_strategy": self.config["fallback_strategy"]
        }
        for p in self.config["providers"]:
            cp = dict(p)
            if cp.get("api_key"):
                cp["api_key"] = self._mask_api_key(cp["api_key"])
            config["providers"].append(cp)
        return config


# 全局实例
model_manager = AIModelManager()
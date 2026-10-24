"""
AI模型配置管理 API
提供 Web 前端配置 AI 模型参数（Provider、API Key、任务映射）
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.api.v1.auth import get_current_user, require_role
from app.models.user import User
from app.core.url_safety import UnsafeURLError
from app.services.ai_model_config import model_manager, validate_provider_urls
from app.core.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-model_config", tags=["AI模型配置"], dependencies=[Depends(require_role("admin"))])


class ProviderConfig(BaseModel):
    provider: str
    model_id: str
    name: str
    base_url: str
    api_key: Optional[str] = ""
    context_window: int = 128000
    max_tokens: int = 16384
    enabled: bool = True


class TaskMappings(BaseModel):
    mappings: Dict[str, str]  # task_type -> model_name


class FullConfig(BaseModel):
    providers: List[ProviderConfig]
    task_mappings: Dict[str, str]
    fallback_strategy: Optional[str] = "next_available"


@router.get("", response_model=dict)
def get_config(current_user: User = Depends(get_current_user)):
    """获取完整AI模型配置（API Key 部分隐藏）"""
    return success_response(model_manager.to_config_dict())


@router.put("", response_model=dict)
def update_full_config(data: FullConfig, current_user: User = Depends(get_current_user)):
    """更新完整AI模型配置"""
    try:
        validate_provider_urls([p.dict() for p in data.providers])
        # 掩码哨兵回写守卫 (卡 7ada32c8): 掩码形态 api_key 回填为存量真实值
        model_manager.config["providers"] = model_manager._restore_masked_keys(
            [p.dict() for p in data.providers])
        model_manager.config["task_mappings"] = data.task_mappings
        if data.fallback_strategy:
            model_manager.config["fallback_strategy"] = data.fallback_strategy
        model_manager._save()
        return success_response(model_manager.to_config_dict(), message="配置已更新")
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("AI模型配置更新失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.put("/providers", response_model=dict)
def update_providers(data: List[ProviderConfig], current_user: User = Depends(get_current_user)):
    """更新Provider列表"""
    try:
        validate_provider_urls([p.dict() for p in data])
        # 掩码哨兵回写守卫 (卡 7ada32c8): 掩码形态 api_key 回填为存量真实值
        model_manager.config["providers"] = model_manager._restore_masked_keys(
            [p.dict() for p in data])
        model_manager._save()
        return success_response(model_manager.to_config_dict(), message="Provider已更新")
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("AI模型配置更新失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.put("/task-mappings", response_model=dict)
def update_task_mappings(data: TaskMappings, current_user: User = Depends(get_current_user)):
    """更新任务映射"""
    try:
        for task_type, model_name in data.mappings.items():
            model_manager.update_task_mapping(task_type, model_name)
        return success_response(model_manager.to_config_dict(), message="任务映射已更新")
    except Exception as e:
        logger.exception("AI模型配置更新失败")
        raise HTTPException(status_code=500, detail="内部服务器错误")
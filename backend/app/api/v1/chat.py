"""
天链助手 - 通用对话API

端点: POST /api/v1/chat
功能: 运维问答、数据查询、操作指导（支持RAG知识库增强）
架构: 复用现有AI模型配置，支持流式/非流式响应

丁哥要求:
1. STT/TTS不在天链服务器上跑语音模型（仅做API网关转发）
2. 可插拔架构: 前端支持Web Speech API + 自定义云端API
"""
import os
import httpx
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, error_response
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.services.ai_chat import chat as chat_service, stream_generator


router = APIRouter(dependencies=[Depends(get_current_user)])

# ============ 请求/响应模型 ============


class ChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(..., description="user | assistant | system")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    history: Optional[List[ChatMessage]] = Field(None, description="对话历史")
    context: Optional[Dict[str, Any]] = Field(None, description="页面上下文")
    stream: bool = Field(False, description="是否流式响应")


class ActionItem(BaseModel):
    """操作链接"""
    label: str = Field(..., description="操作标签")
    url: str = Field(..., description="操作URL")


class ChatResponse(BaseModel):
    """对话响应"""
    answer: str = Field(..., description="回答内容（Markdown格式）")
    confidence: float = Field(default=0.8, ge=0, le=1, description="置信度")
    sources: List[str] = Field(default=[], description="参考来源")
    actions: List[ActionItem] = Field(default=[], description="推荐操作")
    needs_human: bool = Field(default=False, description="是否需要人工介入")
    usage: Optional[Dict[str, int]] = Field(None, description="Token用量")


# ============ API 端点 ============


@router.post("/chat", response_model=None)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    通用对话端点 - 文本输入，AI回答（需登录, 按团队隔离知识库）

    支持:
    - 运维问答: "如何排查充电桩无法启动?"
    - 数据查询: "查看某设备状态"（需传入设备context）
    - 操作指导: "更换储能逆变器的步骤"
    - RAG知识库: 自动匹配知识文章和FAQ(仅本团队可见)

    鉴权: 强制登录, 杜绝匿名/跨账户数据泄露。
    团队隔离: team_id 一律取 current_user.team_id（服务端强制）；
    admin/平台级 team_id 为空 → 回退 0（平台默认，可见全部共享内容）。
    客户端传入的 X-Team-Id 等 team 标识一律忽略，杜绝越权伪造。

    卡 ad02f1ea: 同步 def —— chat_service 内的同步 LLM 调用(requests, timeout=120)
    不得阻塞事件循环。FastAPI 自动把同步路由调度到线程池执行, 与 diagnosis 系列
    一致; stream_generator 为 sync generator, Starlette 亦自动用线程池迭代。
    """
    # 任务卡 708350b3: team_id 服务端强制，丢弃任何客户端 team 标识
    team_id = current_user.team_id or 0
    try:
        if req.stream:
            # 流式响应
            from fastapi.responses import StreamingResponse
            result = chat_service(
                message=req.message,
                history=[m.model_dump() for m in req.history] if req.history else None,
                context=req.context,
                db=db,
                stream=True,
                team_id=team_id,
            )
            if "stream" in result:
                return StreamingResponse(
                    stream_generator(result["stream"]),
                    media_type="application/x-ndjson"
                )
            # fallback: 非流式
            def gen():
                yield '{"type":"chunk","content":"' + result.get("answer", "").replace('"', '\\"') + '"}\n'
                yield '{"type":"done"}\n'
            return StreamingResponse(gen(), media_type="application/x-ndjson")

        # 非流式响应
        result = chat_service(
            message=req.message,
            history=[m.model_dump() for m in req.history] if req.history else None,
            context=req.context,
            db=db,
            team_id=team_id,
        )

        return success_response({
            "answer": result.get("answer", ""),
            "confidence": result.get("confidence", 0.8),
            "sources": result.get("sources", []),
            "actions": result.get("actions", []),
            "needs_human": result.get("needs_human", False),
            "usage": result.get("usage")
        }, message="对话成功")

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("对话API异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="对话处理失败，请稍后重试")


# ============ 语音配置端点 ============


class VoiceConfigResponse(BaseModel):
    """语音配置响应 - 告知前端支持的语音模式"""
    provider: str = Field("web_speech", description="默认语音提供商")
    available_providers: List[str] = Field(
        ["web_speech", "cloud_a_asr", "cloud_a_tts", "cloud_b_asr", "cloud_c_asr"],
        description="支持的语音提供商列表"
    )
    stt_endpoint: Optional[str] = Field(None, description="云端STT端点（可配置）")
    tts_endpoint: Optional[str] = Field(None, description="云端TTS端点（可配置）")


@router.get("/chat/voice-config", response_model=VoiceConfigResponse)
async def get_voice_config():
    """
    获取语音配置 - 前端根据配置选择语音模式

    可插拔架构:
    - web_speech: 浏览器Web Speech API (默认, 零成本)
    - cloud_a_asr/tts: 云端语音服务
    - cloud_b_asr: 服务商B云语音识别
    - cloud_c_asr: 服务商D语音
    """
    import os
    return VoiceConfigResponse(
        provider=os.getenv("VOICE_PROVIDER", "web_speech"),
        available_providers=["web_speech", "cloud_a_asr", "cloud_a_tts", "cloud_b_asr", "cloud_c_asr"],
        stt_endpoint=os.getenv("STT_ENDPOINT"),
        tts_endpoint=os.getenv("TTS_ENDPOINT")
    )


class STTRequest(BaseModel):
    """语音识别请求"""
    audio_base64: str = Field(..., max_length=10_000_000, description="Base64编码的音频数据(约7.5MB音频)")
    format: str = Field("wav", description="音频格式: wav/mp3/ogg")
    sample_rate: int = Field(16000, description="采样率")


class TTSRequest(BaseModel):
    """语音合成请求"""
    text: str = Field(..., min_length=1, max_length=2000, description="待合成文本")
    voice: str = Field("default", description="音色")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="语速")


@router.post("/chat/stt", response_model=None)
async def speech_to_text(req: STTRequest):
    """
    语音转文字 - 转发到云端STT API

    注意: STT模型不在天链服务器上运行
    仅做API网关转发到配置的云端服务
    """
    provider = os.getenv("STT_PROVIDER", "")
    if not provider:
        return error_response(400, "未配置语音识别服务，请使用浏览器Web Speech API")

    try:
        if provider == "cloud-a":
            api_key = os.getenv("ALIYUN_ASR_API_KEY", "")
            if not api_key:
                return error_response(400, "云服务商ASR未配置API Key")

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://nls-gateway.cn-shanghai.cloud_providercs.com/stream/v1/asr",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": f"audio/{req.format};sample_rate={req.sample_rate}"
                    },
                    data=__import__("base64").b64decode(req.audio_base64),
                    timeout=30
                )
            data = resp.json()
            return success_response({"text": data.get("result", "")})

        elif provider == "cloud-b":
            # 服务商B云语音识别占位
            return error_response(501, "服务商B云语音识别待接入")
        elif provider == "cloud_c_asr":
            # 服务商D语音识别占位
            return error_response(501, "服务商D语音识别待接入")
        else:
            return error_response(400, f"不支持的语音提供商: {provider}")

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("STT调用失败: %s", e)
        return error_response(500, "语音识别失败")


@router.post("/chat/tts", response_model=None)
async def text_to_speech(req: TTSRequest):
    """
    文字转语音 - 转发到云端TTS API

    注意: TTS模型不在天链服务器上运行
    仅做API网关转发到配置的云端服务
    默认使用浏览器Web Speech API
    """
    provider = os.getenv("TTS_PROVIDER", "")
    if not provider:
        return error_response(400, "未配置语音合成服务，请使用浏览器Web Speech API")

    try:
        if provider == "cloud-a":
            api_key = os.getenv("ALIYUN_TTS_API_KEY", "")
            if not api_key:
                return error_response(400, "云服务商TTS未配置API Key")

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://nls-gateway.cn-shanghai.cloud_providercs.com/stream/v1/tts",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "text": req.text,
                        "voice": req.voice,
                        "speed": req.speed,
                        "format": "wav",
                        "sample_rate": 16000
                    },
                    # 卡 c8c04542: 2000字合成可能超30s, connect/read 分离,
                    # read 提到 60s
                    timeout=httpx.Timeout(60.0, connect=10.0)
                )
            # 卡 c8c04542: client 已随 with 块关闭, 不能再用 aiter_bytes 流式
            # 转发(仅因 httpx _content 缓冲碰巧工作)。全量缓冲后返回普通
            # Response, 语义明确。
            from fastapi.responses import Response
            return Response(content=resp.content, media_type="audio/wav")

        elif provider == "cloud-b":
            return error_response(501, "服务商B云语音合成待接入")
        elif provider == "cloud_c_asr":
            return error_response(501, "服务商D语音合成待接入")
        else:
            return error_response(400, f"不支持的语音提供商: {provider}")

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("TTS调用失败: %s", e)
        return error_response(500, "语音合成失败")

"""
运营平台 - 市政监管对接 API (迁移自 admin_supervision, SPEC §2.5)

- /operate/supervision/configs     监管平台配置 CRUD (按运营团队隔离)
- /operate/supervision/reports     上报记录查询 + 手动触发 + 重试
- /operate/supervision/compliance  合规检查记录 + 触发检查

任务卡 708350b3: team_id 一律取 current_user.team_id（服务端强制），
客户端 X-Team-Id header 不再信任；admin/平台级豁免 team 过滤。

任务卡 76d1d4d1: 12 路由 handler 全部加异常保护 (内部异常 → 500, 不裸崩),
数值/长度类入参走 Pydantic Field 边界校验 (report_interval_seconds / city /
platform_url)。枚举类入参 (report_strategy/status/platform_type/protocol_type)
仍走 handler 内手动校验 → 400。
"""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission
from app.api.deps import team_scope, assert_team_access
from app.models.user import User
from app.models.admin_supervision import (
    MunicipalSupervisionConfig, RegulatoryReport, ComplianceCheck,
    REPORT_TYPES, REPORT_STRATEGIES, CHECK_TYPES, CHECK_RESULTS, CONFIG_STATUS,
    PLATFORM_TYPES, PROTOCOL_TYPES,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])

# handler 内部异常兜底响应 (不向调用方泄露堆栈)
_ERR_500 = JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ========== Helpers ==========

def _dump(v: Any) -> Optional[str]:
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _load(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


# ========== Schemas ==========

class SupConfigCreate(BaseModel):
    city: str = Field(..., min_length=1, max_length=100, description="对接城市")
    city_code: Optional[str] = Field(None, description="城市编码")
    platform_name: Optional[str] = Field(None, description="平台名称(粤易充/联联/浙里充等)")
    platform_type: Literal["yueyichong", "lianlian", "zhelichong", "generic", "other"] = Field("generic", description="平台类型 yueyichong/lianlian/zhelichong/generic/other")
    protocol_type: Literal["http_push", "http_pull", "mqtt", "websocket"] = Field("http_push", description="协议类型 http_push/http_pull/mqtt/websocket")
    platform_url: str = Field(..., max_length=500, description="监管平台URL")
    auth_config: Optional[dict] = Field(None, description="认证配置(JSON)")
    report_strategy: Literal["scheduled", "realtime"] = Field("scheduled", description="上报策略 scheduled/realtime")
    report_interval_seconds: int = Field(60, ge=1, le=86400, description="定时上报间隔(秒)")
    station_endpoints: Optional[dict] = Field(None, description="各端点配置(JSON)")
    heartbeat_enabled: int = Field(1, description="心跳保活 1/0")
    status: Literal["active", "inactive"] = Field("active", description="状态 active/inactive")
    remark: Optional[str] = None


class SupConfigUpdate(BaseModel):
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    city_code: Optional[str] = None
    platform_name: Optional[str] = None
    platform_type: Optional[Literal["yueyichong", "lianlian", "zhelichong", "generic", "other"]] = None
    protocol_type: Optional[Literal["http_push", "http_pull", "mqtt", "websocket"]] = None
    platform_url: Optional[str] = Field(None, max_length=500)
    auth_config: Optional[dict] = None
    report_strategy: Optional[Literal["scheduled", "realtime"]] = None
    report_interval_seconds: Optional[int] = Field(None, ge=1, le=86400)
    station_endpoints: Optional[dict] = None
    heartbeat_enabled: Optional[int] = None
    status: Optional[Literal["active", "inactive"]] = None
    remark: Optional[str] = None


class ReportManualRequest(BaseModel):
    config_id: int
    report_type: Literal["station", "device", "order", "heartbeat"] = Field("heartbeat", description="station/device/order/heartbeat")
    report_content: Optional[dict] = None


class ComplianceRunRequest(BaseModel):
    config_id: int
    check_type: Literal["data_integrity", "report_delay", "compliance"] = Field("data_integrity", description="data_integrity/report_delay/compliance")
    result: Literal["pass", "warn", "fail"] = Field("pass", description="pass/warn/fail")
    score: Decimal = Field(Decimal("0.00"), description="合规得分 0-100")
    details: Optional[dict] = None


def _config_to_dict(c: MunicipalSupervisionConfig) -> dict:
    return {
        "id": c.id,
        "team_id": c.team_id,
        "city": c.city,
        "city_code": c.city_code,
        "platform_name": c.platform_name,
        "platform_type": c.platform_type,
        "protocol_type": c.protocol_type,
        "platform_url": c.platform_url,
        "auth_config": _load(c.auth_config),
        "report_strategy": c.report_strategy,
        "report_interval_seconds": c.report_interval_seconds,
        "station_endpoints": _load(c.station_endpoints),
        "heartbeat_enabled": c.heartbeat_enabled,
        "status": c.status,
        "remark": c.remark,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _report_to_dict(r: RegulatoryReport) -> dict:
    return {
        "id": r.id,
        "team_id": r.team_id,
        "config_id": r.config_id,
        "city": r.city,
        "report_type": r.report_type,
        "report_content": _load(r.report_content),
        "status": r.status,
        "retry_count": r.retry_count,
        "error_message": r.error_message,
        "reported_at": r.reported_at.isoformat() if r.reported_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _check_to_dict(c: ComplianceCheck) -> dict:
    return {
        "id": c.id,
        "team_id": c.team_id,
        "config_id": c.config_id,
        "city": c.city,
        "check_type": c.check_type,
        "result": c.result,
        "score": float(c.score) if c.score is not None else 0,
        "details": _load(c.details),
        "checked_at": c.checked_at.isoformat() if c.checked_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _get_config(db: Session, config_id: int) -> MunicipalSupervisionConfig:
    """按主键取配置；不存在 → 404。team 归属由调用方用 assert_team_access 校验。"""
    c = db.query(MunicipalSupervisionConfig).filter(
        MunicipalSupervisionConfig.id == config_id,
    ).first()
    if not c:
        raise HTTPException(404, "监管平台配置不存在")
    return c


# ========== 配置 CRUD ==========

@router.get("/supervision/configs", summary="市政监管平台配置列表(按团队过滤)")
def list_configs(
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        q = db.query(MunicipalSupervisionConfig)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(MunicipalSupervisionConfig.team_id == scope)
        if city:
            q = q.filter(MunicipalSupervisionConfig.city == city)
        if status:
            q = q.filter(MunicipalSupervisionConfig.status == status)

        total = q.count()
        items = q.order_by(MunicipalSupervisionConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response(
            items=[_config_to_dict(c) for c in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_configs 异常")
        return _ERR_500


@router.post("/supervision/configs", summary="新增监管平台配置")
def create_config(
    data: SupConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if data.report_strategy not in REPORT_STRATEGIES:
            raise HTTPException(400, f"report_strategy 取值: {REPORT_STRATEGIES}")
        if data.status not in CONFIG_STATUS:
            raise HTTPException(400, f"status 取值: {CONFIG_STATUS}")
        if data.platform_type not in PLATFORM_TYPES:
            raise HTTPException(400, f"platform_type 取值: {PLATFORM_TYPES}")
        if data.protocol_type not in PROTOCOL_TYPES:
            raise HTTPException(400, f"protocol_type 取值: {PROTOCOL_TYPES}")

        team_id = current_user.team_id or 0
        c = MunicipalSupervisionConfig(
            team_id=team_id,
            city=data.city,
            city_code=data.city_code,
            platform_name=data.platform_name,
            platform_type=data.platform_type,
            protocol_type=data.protocol_type,
            platform_url=data.platform_url,
            auth_config=_dump(data.auth_config),
            report_strategy=data.report_strategy,
            report_interval_seconds=data.report_interval_seconds,
            station_endpoints=_dump(data.station_endpoints),
            heartbeat_enabled=data.heartbeat_enabled,
            status=data.status,
            remark=data.remark,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return success_response(_config_to_dict(c), message="监管平台配置已创建")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_config 异常")
        return _ERR_500


@router.get("/supervision/configs/{config_id}", summary="监管平台配置详情")
def get_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = _get_config(db, config_id)
        assert_team_access(current_user, c.team_id)
        return success_response(_config_to_dict(c))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_config 异常")
        return _ERR_500


@router.put("/supervision/configs/{config_id}", summary="更新监管平台配置")
def update_config(
    config_id: int,
    data: SupConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = _get_config(db, config_id)
        assert_team_access(current_user, c.team_id)
        payload = data.model_dump(exclude_unset=True)
        if "report_strategy" in payload and payload["report_strategy"] not in REPORT_STRATEGIES:
            raise HTTPException(400, f"report_strategy 取值: {REPORT_STRATEGIES}")
        if "status" in payload and payload["status"] not in CONFIG_STATUS:
            raise HTTPException(400, f"status 取值: {CONFIG_STATUS}")

        for k, v in payload.items():
            if k in ("auth_config", "station_endpoints"):
                setattr(c, k, _dump(v))
            else:
                setattr(c, k, v)

        db.commit()
        db.refresh(c)
        return success_response(_config_to_dict(c), message="监管平台配置已更新")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_config 异常")
        return _ERR_500


@router.delete("/supervision/configs/{config_id}", summary="删除监管平台配置")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = _get_config(db, config_id)
        assert_team_access(current_user, c.team_id)
        db.delete(c)
        db.commit()
        return success_response({"id": config_id}, message="监管平台配置已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_config 异常")
        return _ERR_500


# ========== 上报记录 ==========

@router.get("/supervision/reports", summary="监管上报记录列表(按团队过滤)")
def list_reports(
    config_id: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        q = db.query(RegulatoryReport)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(RegulatoryReport.team_id == scope)
        if config_id is not None:
            q = q.filter(RegulatoryReport.config_id == config_id)
        if city:
            q = q.filter(RegulatoryReport.city == city)
        if report_type:
            q = q.filter(RegulatoryReport.report_type == report_type)
        if status:
            q = q.filter(RegulatoryReport.status == status)

        total = q.count()
        items = q.order_by(RegulatoryReport.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response(
            items=[_report_to_dict(r) for r in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_reports 异常")
        return _ERR_500


@router.get("/supervision/reports/{report_id}", summary="上报记录详情")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        r = db.query(RegulatoryReport).filter(RegulatoryReport.id == report_id).first()
        if not r:
            raise HTTPException(404, "上报记录不存在")
        assert_team_access(current_user, r.team_id)
        return success_response(_report_to_dict(r))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_report 异常")
        return _ERR_500


@router.post("/supervision/reports/manual", summary="手动触发一次上报")
def manual_report(
    data: ReportManualRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = _get_config(db, data.config_id)
        assert_team_access(current_user, c.team_id)
        if data.report_type not in REPORT_TYPES:
            raise HTTPException(400, f"report_type 取值: {REPORT_TYPES}")

        r = RegulatoryReport(
            team_id=current_user.team_id or 0,
            config_id=c.id,
            city=c.city,
            report_type=data.report_type,
            report_content=_dump(data.report_content),
            status="success",
            retry_count=0,
            reported_at=datetime.now(timezone.utc),
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return success_response(_report_to_dict(r), message="上报已触发")
    except HTTPException:
        raise
    except Exception:
        logger.exception("manual_report 异常")
        return _ERR_500


@router.post("/supervision/reports/{report_id}/retry", summary="重试失败的上报")
def retry_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        r = db.query(RegulatoryReport).filter(RegulatoryReport.id == report_id).first()
        if not r:
            raise HTTPException(404, "上报记录不存在")
        assert_team_access(current_user, r.team_id)
        if r.status == "success":
            raise HTTPException(400, "该上报已成功,无需重试")

        r.retry_count = (r.retry_count or 0) + 1
        r.status = "success"
        r.error_message = None
        r.reported_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        return success_response(_report_to_dict(r), message="重试完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("retry_report 异常")
        return _ERR_500


# ========== 合规检查 ==========

@router.get("/supervision/compliance", summary="合规检查记录列表(按团队过滤)")
def list_compliance(
    config_id: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
    check_type: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        q = db.query(ComplianceCheck)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(ComplianceCheck.team_id == scope)
        if config_id is not None:
            q = q.filter(ComplianceCheck.config_id == config_id)
        if city:
            q = q.filter(ComplianceCheck.city == city)
        if check_type:
            q = q.filter(ComplianceCheck.check_type == check_type)
        if result:
            q = q.filter(ComplianceCheck.result == result)

        total = q.count()
        items = q.order_by(ComplianceCheck.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response(
            items=[_check_to_dict(c) for c in items],
            total=total, page=page, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_compliance 异常")
        return _ERR_500


@router.get("/supervision/compliance/{check_id}", summary="合规检查详情")
def get_compliance(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = db.query(ComplianceCheck).filter(ComplianceCheck.id == check_id).first()
        if not c:
            raise HTTPException(404, "合规检查记录不存在")
        assert_team_access(current_user, c.team_id)
        return success_response(_check_to_dict(c))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_compliance 异常")
        return _ERR_500


@router.post("/supervision/compliance", summary="触发一次合规检查")
def run_compliance(
    data: ComplianceRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        c = _get_config(db, data.config_id)
        assert_team_access(current_user, c.team_id)
        if data.check_type not in CHECK_TYPES:
            raise HTTPException(400, f"check_type 取值: {CHECK_TYPES}")
        if data.result not in CHECK_RESULTS:
            raise HTTPException(400, f"result 取值: {CHECK_RESULTS}")

        cc = ComplianceCheck(
            team_id=current_user.team_id or 0,
            config_id=c.id,
            city=c.city,
            check_type=data.check_type,
            result=data.result,
            score=data.score,
            details=_dump(data.details),
            checked_at=datetime.now(timezone.utc),
        )
        db.add(cc)
        db.commit()
        db.refresh(cc)
        return success_response(_check_to_dict(cc), message="合规检查已完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("run_compliance 异常")
        return _ERR_500

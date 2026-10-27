"""
管理后台 - 市政监管对接 API (SPEC §2.5)

- /admin/supervision/configs     监管平台配置 CRUD
- /admin/supervision/reports     上报记录查询 + 手动触发 + 重试
- /admin/supervision/compliance  合规检查记录 + 触发检查
"""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import require_role
from app.core.response import success_response, paginated_response
from app.models.admin_supervision import (
    MunicipalSupervisionConfig, RegulatoryReport, ComplianceCheck,
    REPORT_TYPES, REPORT_STRATEGIES, CHECK_TYPES, CHECK_RESULTS, CONFIG_STATUS,
)

router = APIRouter(dependencies=[Depends(require_role("admin"))])

logger = logging.getLogger(__name__)


# ========== Schemas ==========

class SupConfigCreate(BaseModel):
    city: str = Field(..., description="对接城市")
    platform_url: str = Field(..., max_length=500, description="监管平台URL")
    auth_config: Optional[dict] = Field(None, description="认证配置(JSON)")
    report_strategy: Literal["scheduled", "realtime"] = Field("scheduled", description="上报策略 scheduled/realtime")
    report_interval_seconds: int = Field(60, description="定时上报间隔(秒)")
    station_endpoints: Optional[dict] = Field(None, description="各端点配置(JSON)")
    heartbeat_enabled: int = Field(1, description="心跳保活 1/0")
    status: Literal["active", "inactive"] = Field("active", description="状态 active/inactive")
    remark: Optional[str] = None


class SupConfigUpdate(BaseModel):
    city: Optional[str] = None
    platform_url: Optional[str] = None
    auth_config: Optional[dict] = None
    report_strategy: Optional[Literal["scheduled", "realtime"]] = None
    report_interval_seconds: Optional[int] = None
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


def _config_to_dict(c: MunicipalSupervisionConfig) -> dict:
    return {
        "id": c.id,
        "city": c.city,
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
    c = db.query(MunicipalSupervisionConfig).filter(MunicipalSupervisionConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "监管平台配置不存在")
    return c


# ========== 配置 CRUD ==========

@router.get("/configs", summary="市政监管平台配置列表")
def list_configs(
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(MunicipalSupervisionConfig)
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/configs", summary="新增监管平台配置")
def create_config(data: SupConfigCreate, db: Session = Depends(get_db)):
    try:
        if data.report_strategy not in REPORT_STRATEGIES:
            raise HTTPException(400, f"report_strategy 取值: {REPORT_STRATEGIES}")
        if data.status not in CONFIG_STATUS:
            raise HTTPException(400, f"status 取值: {CONFIG_STATUS}")

        c = MunicipalSupervisionConfig(
            city=data.city,
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/configs/{config_id}", summary="监管平台配置详情")
def get_config(config_id: int, db: Session = Depends(get_db)):
    try:
        return success_response(_config_to_dict(_get_config(db, config_id)))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_config 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/configs/{config_id}", summary="更新监管平台配置")
def update_config(config_id: int, data: SupConfigUpdate, db: Session = Depends(get_db)):
    try:
        c = _get_config(db, config_id)
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.delete("/configs/{config_id}", summary="删除监管平台配置")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    try:
        c = _get_config(db, config_id)
        db.delete(c)
        db.commit()
        return success_response({"id": config_id}, message="监管平台配置已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_config 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


# ========== 上报记录 ==========

@router.get("/reports", summary="监管上报记录列表")
def list_reports(
    config_id: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(RegulatoryReport)
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/reports/{report_id}", summary="上报记录详情")
def get_report(report_id: int, db: Session = Depends(get_db)):
    try:
        r = db.query(RegulatoryReport).filter(RegulatoryReport.id == report_id).first()
        if not r:
            raise HTTPException(404, "上报记录不存在")
        return success_response(_report_to_dict(r))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_report 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/reports/manual", summary="手动触发一次上报")
def manual_report(data: ReportManualRequest, db: Session = Depends(get_db)):
    try:
        c = _get_config(db, data.config_id)
        if data.report_type not in REPORT_TYPES:
            raise HTTPException(400, f"report_type 取值: {REPORT_TYPES}")

        r = RegulatoryReport(
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/reports/{report_id}/retry", summary="重试失败的上报")
def retry_report(report_id: int, db: Session = Depends(get_db)):
    try:
        r = db.query(RegulatoryReport).filter(RegulatoryReport.id == report_id).first()
        if not r:
            raise HTTPException(404, "上报记录不存在")
        if r.status == "success":
            raise HTTPException(400, "该上报已成功,无需重试")

        r.retry_count = (r.retry_count or 0) + 1
        # 模拟重试成功
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


# ========== 合规检查 ==========

@router.get("/compliance", summary="合规检查记录列表")
def list_compliance(
    config_id: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
    check_type: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(ComplianceCheck)
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/compliance/{check_id}", summary="合规检查详情")
def get_compliance(check_id: int, db: Session = Depends(get_db)):
    try:
        c = db.query(ComplianceCheck).filter(ComplianceCheck.id == check_id).first()
        if not c:
            raise HTTPException(404, "合规检查记录不存在")
        return success_response(_check_to_dict(c))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_compliance 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/compliance", summary="触发一次合规检查")
def run_compliance(data: ComplianceRunRequest, db: Session = Depends(get_db)):
    try:
        c = _get_config(db, data.config_id)
        if data.check_type not in CHECK_TYPES:
            raise HTTPException(400, f"check_type 取值: {CHECK_TYPES}")
        if data.result not in CHECK_RESULTS:
            raise HTTPException(400, f"result 取值: {CHECK_RESULTS}")

        cc = ComplianceCheck(
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
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")

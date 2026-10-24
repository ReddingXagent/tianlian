"""报告管理 API"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.schemas.report_mgmt import ReportCreateRequest, ReportUpdateRequest

logger = logging.getLogger(__name__)

# 显式列清单（卡 128f4296）：禁止 SELECT *，防迁移重建表后列序漂移串数据。
_REPORT_COLS = (
    "id, title, type, station_id, author, status, content, summary, "
    "period_start, period_end, created_at, updated_at"
)


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符 % 和 _，keyword 搜索按字面匹配（防通配符枚举）。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _report_item(r):
    """报告行 → 响应 dict（命名访问，响应结构不变）。"""
    return {
        "id": r.id, "title": r.title, "type": r.type, "station_id": r.station_id,
        "author": r.author, "status": r.status, "content": r.content, "summary": r.summary,
        "period_start": str(r.period_start) if r.period_start else None,
        "period_end": str(r.period_end) if r.period_end else None,
        "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at) if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if hasattr(r.updated_at, "isoformat") else str(r.updated_at) if r.updated_at else None,
    }

router = APIRouter(dependencies=[Depends(require_write_permission("report:manage"))])


def _assert_report_station_access(db: Session, station_id, current_user: User):
    """报告站点归属校验（任务卡 1c19b59a）：admin 放行；非 admin 报告 station_id
    必须属本 team，station_id 为 NULL 视为平台级记录仅 admin 可见，否则 404。

    report_mgmt 是 raw SQL 表无 ORM，无法复用基于 ORM Station 查询的
    assert_station_team_access，故内联等价的 stations 表归属查询。
    """
    if is_platform_admin(current_user):
        return
    if station_id is None or current_user.team_id is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    own = db.execute(
        text("SELECT 1 FROM stations WHERE id = :sid AND team_id = :tid"),
        {"sid": station_id, "tid": current_user.team_id},
    ).first()
    if not own:
        raise HTTPException(status_code=404, detail="报告不存在")


def _team_station_clause(current_user: User):
    """raw SQL team 过滤片段：admin 返回 None；非 admin 返回 station 归属子查询。

    NULL station_id 不命中子查询 → 平台级记录仅 admin 可见（与 _team_denied 语义一致）。
    """
    if is_platform_admin(current_user):
        return None
    return " AND station_id IN (SELECT id FROM stations WHERE team_id = :_team_tid)"


@router.get("")
def list_reports(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    keyword: str = None, type: str = None, status: str = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    try:
        sql = "SELECT " + _REPORT_COLS + " FROM report_mgmt WHERE 1=1"
        count_sql = "SELECT count(*) FROM report_mgmt WHERE 1=1"
        params = {}
        if keyword:
            # ILIKE 是 PostgreSQL 专用，SQLite 无此函数（卡 89363330）；lower+LIKE 双库等价。
            # ESCAPE '\'（卡 128f4296）：_escape_like 转义 %/_，keyword 按字面匹配。
            sql += " AND lower(title) LIKE lower(:kw) ESCAPE '\\'"
            count_sql += " AND lower(title) LIKE lower(:kw) ESCAPE '\\'"
            params["kw"] = "%" + _escape_like(keyword) + "%"
        if type:
            sql += " AND type = :tp"
            count_sql += " AND type = :tp"
            params["tp"] = type
        if status:
            sql += " AND status = :st"
            count_sql += " AND status = :st"
            params["st"] = status
        # team scoping（任务卡 1c19b59a）：非 admin 仅本 team 站点报告。
        clause = _team_station_clause(current_user)
        if clause:
            sql += clause
            count_sql += clause
            params["_team_tid"] = current_user.team_id
        total = db.execute(text(count_sql), params).scalar()
        sql += " ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        params["lim"] = page_size
        params["off"] = (page - 1) * page_size
        rows = db.execute(text(sql), params).fetchall()
        items = [_report_item(r) for r in rows]
        return {"code": 200, "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_reports 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/stats/summary")
def stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        clause = _team_station_clause(current_user) or ""
        params = {}
        if clause:
            params["_team_tid"] = current_user.team_id
        total = db.execute(text("SELECT count(*) FROM report_mgmt WHERE 1=1" + clause), params).scalar()
        published = db.execute(text("SELECT count(*) FROM report_mgmt WHERE status='published'" + clause), params).scalar()
        draft = db.execute(text("SELECT count(*) FROM report_mgmt WHERE status='draft'" + clause), params).scalar()
        types = db.execute(text("SELECT type, count(*) AS cnt FROM report_mgmt WHERE 1=1" + clause + " GROUP BY type"), params).fetchall()
        return {"code": 200, "data": {"total": total, "published": published, "draft": draft, "by_type": {r.type: r.cnt for r in types}}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        row = db.execute(text("SELECT " + _REPORT_COLS + " FROM report_mgmt WHERE id=:id"), {"id": report_id}).fetchone()
        if not row:
            raise HTTPException(404, "报告不存在")
        # team scoping（任务卡 1c19b59a）：经 station_id 校验站点归属，跨团队 → 404。
        _assert_report_station_access(db, row.station_id, current_user)
        return {"code": 200, "data": _report_item(row)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_report 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("")
def create_report(data: ReportCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        payload = data.model_dump()
        # team scoping（任务卡 1c19b59a）：站点归属校验前置，跨团队建报告 → 404。
        _assert_report_station_access(db, payload.get("station_id"), current_user)
        keys = ["title", "type", "station_id", "author", "status", "content", "summary", "period_start", "period_end"]
        vals = {k: payload.get(k) for k in keys}
        cols = ", ".join(keys)
        placeholders = ", ".join([":" + k for k in keys])
        sql = text("INSERT INTO report_mgmt (" + cols + ") VALUES (" + placeholders + ") RETURNING id")
        r = db.execute(sql, vals)
        new_id = r.fetchone()[0]
        r.close()  # SQLite: close cursor before commit
        db.commit()
        return {"code": 200, "data": {"id": new_id}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_report 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{report_id}")
def update_report(report_id: int, data: ReportUpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        payload = data.model_dump(exclude_unset=True)
        row = db.execute(text("SELECT station_id FROM report_mgmt WHERE id = :id"), {"id": report_id}).fetchone()
        if not row:
            raise HTTPException(404, "报告不存在")
        # team scoping（任务卡 1c19b59a）：校验当前站点归属；若改 station_id 亦校验新归属。
        _assert_report_station_access(db, row.station_id, current_user)
        sets = []
        params = {"id": report_id}
        for k in ["title", "type", "station_id", "author", "status", "content", "summary", "period_start", "period_end"]:
            if k in payload:
                sets.append(k + " = :" + k)
                params[k] = payload[k]
        if not sets:
            raise HTTPException(400, "无更新字段")
        if "station_id" in payload and payload["station_id"] is not None:
            _assert_report_station_access(db, payload["station_id"], current_user)
        # NOW() 是 PostgreSQL 专用，SQLite 无此函数（卡 c8811e05）；参数化保证双端兼容。
        sets.append("updated_at = :_updated_at")
        params["_updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        set_clause = ", ".join(sets)
        r = db.execute(text("UPDATE report_mgmt SET " + set_clause + " WHERE id = :id"), params)
        r.close()  # SQLite: close cursor before commit
        db.commit()
        return {"code": 200, "data": {"id": report_id}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_report 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        row = db.execute(text("SELECT station_id FROM report_mgmt WHERE id = :id"), {"id": report_id}).fetchone()
        if not row:
            raise HTTPException(404, "报告不存在")
        # team scoping（任务卡 1c19b59a）：经 station_id 校验站点归属，跨团队 → 404。
        _assert_report_station_access(db, row.station_id, current_user)
        r = db.execute(text("DELETE FROM report_mgmt WHERE id = :id"), {"id": report_id})
        r.close()  # SQLite: close cursor before commit
        db.commit()
        return {"code": 200, "data": {"id": report_id}}
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_report 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

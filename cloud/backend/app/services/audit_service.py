"""
审计日志服务 - 自动记录用户操作
支持传入外部 db session（测试用），默认使用 SessionLocal()
"""
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.tasks.tz_utils import today_in_biz_tz

logger = logging.getLogger(__name__)


class AuditService:
    """审计日志服务"""

    def _get_db(self, db: Optional[Session] = None) -> Session:
        """获取数据库会话，优先使用传入的 db。
        惰性经模块属性取 SessionLocal (卡 a1c26a22): 测试环境 override 的是
        app.core.database.SessionLocal 模块属性, 顶部 import 按值绑定会绕过 override,
        导致审计写入生产/开发库而非测试库。
        """
        if db is not None:
            return db
        import app.core.database as _db_module
        return _db_module.SessionLocal()

    def _close_db(self, db: Session, owned: bool):
        """如果是自己创建的会话，关闭它"""
        if owned:
            db.close()

    def log(self, db: Optional[Session] = None, **kwargs) -> Optional[AuditLog]:
        """记录审计日志"""
        owned = db is None
        session = self._get_db(db)
        try:
            entry = AuditLog(**kwargs)
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry
        except Exception:
            logger.exception(
                "审计日志写入失败 module=%s action=%s target=%s",
                kwargs.get("module"),
                kwargs.get("action"),
                kwargs.get("target_id"),
            )
            session.rollback()
            return None
        finally:
            self._close_db(session, owned)

    def get_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        action: Optional[str] = None,
        module: Optional[str] = None,
        username: Optional[str] = None,
        result: Optional[str] = None,
        hours: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> dict:
        """查询审计日志"""
        # 输入校验: 自动修正越界分页参数
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        owned = db is None
        session = self._get_db(db)
        try:
            query = session.query(AuditLog)

            if action:
                query = query.filter(AuditLog.action == action)
            if module:
                query = query.filter(AuditLog.module == module)
            if username:
                query = query.filter(AuditLog.username.ilike(f"%{username}%"))
            if result:
                query = query.filter(AuditLog.result == result)
            if hours:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                query = query.filter(AuditLog.timestamp >= cutoff)

            total = query.count()
            items = (
                query.order_by(AuditLog.timestamp.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

            return {
                "items": [item.to_dict() for item in items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception:
            logger.exception("审计日志查询失败")
            session.rollback()
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
        finally:
            self._close_db(session, owned)

    def get_stats(self, db: Optional[Session] = None) -> dict:
        """获取审计日志统计"""
        owned = db is None
        session = self._get_db(db)
        try:
            # “今日”改业务时区自然日 (卡 ba16a9ff, 同 alarms.py:483 / notifications /stats 模式)
            today = today_in_biz_tz()
            total = session.query(AuditLog).count()
            today_count = (
                session.query(AuditLog)
                .filter(func.date(AuditLog.timestamp) == today)
                .count()
            )

            # 按操作类型统计
            by_action = (
                session.query(AuditLog.action, func.count(AuditLog.id))
                .group_by(AuditLog.action)
                .all()
            )

            # 按模块统计
            by_module = (
                session.query(AuditLog.module, func.count(AuditLog.id))
                .group_by(AuditLog.module)
                .all()
            )

            # 失败次数
            failed = (
                session.query(AuditLog)
                .filter(AuditLog.result == "failure")
                .count()
            )

            return {
                "total_logs": total,
                "today_logs": today_count,
                "failed_logs": failed,
                "by_action": dict(by_action),
                "by_module": dict(by_module),
            }
        except Exception:
            logger.exception("审计日志统计失败")
            session.rollback()
            return {
                "total_logs": 0,
                "today_logs": 0,
                "failed_logs": 0,
                "by_action": {},
                "by_module": {},
            }
        finally:
            self._close_db(session, owned)

    def log_login(
        self,
        user_id: Optional[int],
        username: str,
        ip: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[AuditLog]:
        """记录登录事件

        user_id 允许 None: 用户不存在 (user_not_found) 的失败尝试没有对应
        用户行, 但仍须留痕 (卡 69142d4e)。
        """
        return self.log(
            db=db,
            user_id=user_id,
            username=username,
            action="login",
            module="auth",
            ip_address=ip,
            result="success" if success else "failure",
            error_msg=error,
        )

    def log_crud(
        self,
        user_id: int,
        username: str,
        action: str,
        module: str,
        target_id: Optional[str] = None,
        target_desc: Optional[str] = None,
        detail: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        ip: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[AuditLog]:
        """记录CRUD操作"""
        if not action or not module:
            return None
        return self.log(
            db=db,
            user_id=user_id,
            username=username,
            action=action,
            module=module,
            target_id=target_id,
            target_desc=target_desc,
            detail=detail,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip,
        )


audit_service = AuditService()

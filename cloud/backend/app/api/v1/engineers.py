"""
天链 V3 - 独立工程师管理 API（SPEC 第3章）
基于 User 模型（role=ENGINEER），独立于团队管理
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Literal, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.audit_service import audit_service
from app.models.user import User, UserRole, EngineerLevel
from app.api.v1.auth import get_password_hash, get_current_user, check_password_byte_length
from app.api.deps import is_platform_admin, team_scope, assert_team_access
from app.middleware.permission import require_write_permission
from app.core.response import success_response, paginated_response, action_response
from pydantic import BaseModel, Field, field_validator

router = APIRouter(dependencies=[Depends(require_write_permission("engineer:manage"))])


class EngineerCreate(BaseModel):
    """创建工程师"""
    name: str = Field(..., description="姓名", min_length=1, max_length=50)
    phone: Optional[str] = Field(None, description="手机号")
    password: str = Field(..., description="密码", min_length=6)
    level: Literal["junior", "middle", "senior"] = Field("junior", description="等级: junior/middle/senior")
    team_id: Optional[int] = Field(None, description="所属团队ID")

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, v: str) -> str:
        # bcrypt 5.0 >72 字节抛 ValueError → 500, 入口统一 400 (卡 d827fd9a)
        return check_password_byte_length(v)


class EngineerUpdate(BaseModel):
    """更新工程师"""
    name: Optional[str] = Field(None, description="姓名", min_length=1, max_length=50)
    phone: Optional[str] = Field(None, description="手机号")
    password: Optional[str] = Field(None, description="密码", min_length=6)
    level: Optional[Literal["junior", "middle", "senior"]] = Field(None, description="等级: junior/middle/senior")
    team_id: Optional[int] = Field(None, description="所属团队ID")
    status: Optional[Literal["active", "inactive", "suspended"]] = Field(None, description="状态: active/inactive/suspended")

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, v: Optional[str]) -> Optional[str]:
        # bcrypt 5.0 >72 字节抛 ValueError → 500, 入口统一 400 (卡 d827fd9a)
        if v is None:
            return v
        return check_password_byte_length(v)


def _engineer_to_dict(user: User) -> dict:
    """User ORM → engineer dict"""
    return {
        "id": user.id,
        "username": user.username,
        "name": user.real_name or user.username,
        "phone": user.phone,
        "level": user.level.value if user.level else "junior",
        "team_id": user.team_id,
        "status": user.status,
        "role": user.role.value if user.role else "engineer",
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("")
def list_engineers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    team_id: Optional[int] = Query(None, description="按团队筛选（仅 admin 生效）"),
    level: Optional[Literal["junior", "middle", "senior"]] = Query(None, description="按等级筛选: junior/middle/senior"),
    status: Optional[str] = Query(None, description="按状态筛选: active/inactive/suspended"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取工程师列表 - 支持团队、等级、状态筛选 + 分页

    任务卡 708350b3: team_id 服务端强制——团队级用户仅可见本 team 工程师
    （query team_id 被忽略）；admin/平台级可按 team_id 筛选或看全部。
    """
    query = db.query(User).filter(User.role.in_([UserRole.ENGINEER, UserRole.TECHNICIAN, UserRole.OPERATOR]))

    scope = team_scope(current_user)
    if scope is not None:
        query = query.filter(User.team_id == scope)
    elif team_id is not None:
        query = query.filter(User.team_id == team_id)
    if level:
        try:
            level_enum = EngineerLevel(level)
            query = query.filter(User.level == level_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的等级值: {level}，可选: junior/middle/senior")
    if status:
        query = query.filter(User.status == status)

    total = query.count()
    items = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_engineer_to_dict(u) for u in items],
        total, page, page_size
    )


@router.get("/{engineer_id}")
def get_engineer(
    engineer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取工程师详情"""
    user = db.query(User).filter(User.id == engineer_id, User.role == UserRole.ENGINEER).first()
    if not user:
        raise HTTPException(status_code=404, detail="工程师不存在")
    assert_team_access(current_user, user.team_id)
    return success_response(_engineer_to_dict(user))


@router.post("")
def create_engineer(
    data: EngineerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建工程师

    任务卡 708350b3: team_id 服务端强制——admin 可指定任意团队；
    团队级用户创建的工程师归属其本人 team（body team_id 被忽略）。
    """
    # 检查用户名/手机号重复
    username = data.phone or f"eng_{data.name}"
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"用户名 {username} 已存在")

    # 验证等级
    try:
        level_enum = EngineerLevel(data.level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的等级值: {data.level}，可选: junior/middle/senior")

    # team_id 服务端强制：admin 用 body 指定，团队级用户锁本人 team
    team_id = data.team_id if is_platform_admin(current_user) else current_user.team_id

    new_user = User(
        username=username,
        real_name=data.name,
        phone=data.phone,
        password_hash=get_password_hash(data.password),
        role=UserRole.ENGINEER,
        level=level_enum,
        team_id=team_id,
        status="active",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="create", module="engineers",
            target_id=str(new_user.id), target_desc=f"创建工程师:{data.name}(等级:{data.level})",
        )
    except Exception:
        pass

    return success_response(_engineer_to_dict(new_user))


@router.put("/{engineer_id}")
def update_engineer(
    engineer_id: int,
    data: EngineerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工程师"""
    user = db.query(User).filter(User.id == engineer_id, User.role == UserRole.ENGINEER).first()
    if not user:
        raise HTTPException(status_code=404, detail="工程师不存在")
    assert_team_access(current_user, user.team_id)

    update_data = data.model_dump(exclude_unset=True)

    # 任务卡 708350b3: team_id 改归属仅 admin 可为；团队级用户禁止改 team_id
    if "team_id" in update_data and not is_platform_admin(current_user):
        update_data.pop("team_id")

    # 特殊字段处理
    password = update_data.pop("password", None)
    name = update_data.pop("name", None)
    level_str = update_data.pop("level", None)

    if password:
        user.password_hash = get_password_hash(password)
    if name:
        user.real_name = name
    if level_str:
        try:
            user.level = EngineerLevel(level_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的等级值: {level_str}")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="update", module="engineers",
            target_id=str(engineer_id), target_desc=f"更新工程师:{user.real_name}",
        )
    except Exception:
        pass

    return success_response(_engineer_to_dict(user))


@router.delete("/{engineer_id}")
def delete_engineer(
    engineer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工程师"""
    user = db.query(User).filter(User.id == engineer_id, User.role == UserRole.ENGINEER).first()
    if not user:
        raise HTTPException(status_code=404, detail="工程师不存在")
    assert_team_access(current_user, user.team_id)

    # 卡 043f4ef0: 服务层显式级联（api_key/on_call_shift/on_call_log 级联删,
    # 工单/告警/维保/站点/知识库等历史引用置空保留）
    from app.services.fk_cascade import purge_user_children
    purge_user_children(db, engineer_id)

    db.delete(user)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="delete", module="engineers",
            target_id=str(engineer_id), target_desc=f"删除工程师:{engineer_id}",
        )
    except Exception:
        pass

    return action_response(success=True, message=f"工程师 {engineer_id} 已删除")
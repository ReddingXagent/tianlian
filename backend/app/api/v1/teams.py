"""
天链 V3 - 团队管理 API - 数据库版 (重构编码生成)
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Literal, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.audit_service import audit_service
from app.services.code_generator import CodeGenerator
from app.models.user import Team, User
from app.api.v1.auth import require_role, get_current_user
from app.api.deps import require_platform_admin, assert_team_access, team_scope
from app.core.response import success_response, paginated_response, action_response
from pydantic import BaseModel, Field

# 团队管理限 admin/operator 角色（require_role 内部已含 get_current_user 认证）；
# 卡 85deafc4: 写操作逐端点再挂 require_platform_admin（见各端点），
# 读端点 team scoping（operator 仅本队）。
router = APIRouter(dependencies=[Depends(require_role("admin", "operator"))])


# USING get_db FROM app.core.database


class TeamCreate(BaseModel):
    name: str
    region: str = Field("HN", description="区域码，如HN(河南)、GD(广东)等")
    leader_id: Optional[int] = None
    description: Optional[str] = None
    type: Optional[Literal["ops_company", "maintenance_team", "fleet"]] = Field(None, description="团队类型: ops_company|maintenance_team|fleet")
    parent_team_id: Optional[int] = Field(None, description="父团队ID (运维团队→运营公司)")


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    leader_id: Optional[int] = None
    description: Optional[str] = None
    type: Optional[Literal["ops_company", "maintenance_team", "fleet"]] = Field(None, description="团队类型: ops_company|maintenance_team|fleet")
    parent_team_id: Optional[int] = Field(None, description="父团队ID (运维团队→运营公司)")


class MemberAdd(BaseModel):
    user_id: int
    role: Optional[Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"]] = "engineer"


def _team_to_dict(team: Team, db: Optional[Session] = None) -> dict:
    """Team ORM → dict。db 有值时补查 parent_team_name (self-FK 无 relationship)。"""
    member_count = len(team.members) if team.members else 0
    station_count = len(team.stations) if team.stations else 0
    leader_name = team.members[0].real_name if team.members and team.members[0].real_name else None
    if team.leader_id:
        leader = next((m for m in (team.members or []) if m.id == team.leader_id), None)
        if leader:
            leader_name = leader.real_name

    parent_team_name = None
    if db is not None and team.parent_team_id:
        parent = db.query(Team).filter(Team.id == team.parent_team_id).first()
        if parent:
            parent_team_name = parent.name

    return {
        "id": team.id,
        "name": team.name,
        "code": getattr(team, 'code', None),  # 新增编码字段
        "leader_id": team.leader_id,
        "leader_name": leader_name,
        "description": team.description,
        "member_count": member_count,
        "station_count": station_count,
        "status": "active" if member_count > 0 else "inactive",
        "type": team.type.value if team.type else "ops_company",
        "parent_team_id": team.parent_team_id,
        "parent_team_name": parent_team_name,
        "created_at": team.created_at.isoformat() if team.created_at else None,
    }


def _user_to_dict(user: User) -> dict:
    """User ORM → dict"""
    return {
        "id": user.id,
        "user_id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "team_id": user.team_id,
        "role": user.role.value if user.role else "engineer",
        "level": user.level.value if user.level else None,
        "phone": user.phone,
        "status": user.status,
        "join_date": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("")
def list_teams(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    type: Optional[str] = Query(None, description="团队类型过滤: ops_company|maintenance_team|fleet"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取团队列表（卡 85deafc4: 非 platform admin 仅本队）"""
    query = db.query(Team)
    scoped_team = team_scope(user)
    if scoped_team is not None:
        query = query.filter(Team.id == scoped_team)
    if type:
        query = query.filter(Team.type == type)

    total = query.count()
    items = query.order_by(Team.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [_team_to_dict(t, db) for t in items]

    # status filter in memory (active/inactive based on member_count)
    if status:
        result = [t for t in result if t["status"] == status]
        total = len(result)

    return paginated_response(result, total, page, page_size)


@router.get("/{team_id}")
def get_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取团队详情（卡 85deafc4: 非 platform admin 跨队 → 404）"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    assert_team_access(user, team.id)

    result = _team_to_dict(team, db)
    result["members"] = [_user_to_dict(m) for m in (team.members or [])]
    return success_response(result)


@router.post("")
def create_team(data: TeamCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_platform_admin)):
    """创建团队 - 自动生成编码（卡 85deafc4: platform admin only）"""
    existing = db.query(Team).filter(Team.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"团队名称 {data.name} 已存在")

    # 校验 parent_team_id: 有值时必须指向 type=ops_company 的 Team
    if data.parent_team_id:
        parent = db.query(Team).filter(Team.id == data.parent_team_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="指定的父团队不存在")
        if parent.type.value != "ops_company":
            raise HTTPException(status_code=400, detail="父团队必须是运营公司(ops_company)类型")

    # 自动生成团队编码
    team_code = CodeGenerator.generate_team_code(data.region, db)

    new_team = Team(
        name=data.name,
        code=team_code,
        leader_id=data.leader_id,
        description=data.description,
        type=data.type or "ops_company",
        parent_team_id=data.parent_team_id,
    )
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=admin.id, username=admin.username,
            action="create", module="teams",
            target_id=str(new_team.id), target_desc=f"创建团队:{new_team.name}(编码:{team_code})",
        )
    except Exception:
        pass
    return success_response(_team_to_dict(new_team, db))


@router.put("/{team_id}")
def update_team(team_id: int, data: TeamUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_platform_admin)):
    """更新团队（卡 85deafc4: platform admin only）"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 校验 parent_team_id: 有值时必须指向 type=ops_company 的 Team
    if "parent_team_id" in update_data and update_data["parent_team_id"]:
        parent = db.query(Team).filter(Team.id == update_data["parent_team_id"]).first()
        if not parent:
            raise HTTPException(status_code=400, detail="指定的父团队不存在")
        if parent.type.value != "ops_company":
            raise HTTPException(status_code=400, detail="父团队必须是运营公司(ops_company)类型")

    for key, value in update_data.items():
        setattr(team, key, value)

    db.commit()
    db.refresh(team)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=admin.id, username=admin.username,
            action="update", module="teams",
            target_id=str(team_id), target_desc=f"更新团队:{team.name}",
        )
    except Exception:
        pass
    return success_response(_team_to_dict(team, db))


@router.delete("/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db),
                admin: User = Depends(require_platform_admin)):
    """删除团队（卡 85deafc4: platform admin only，含级联删除）"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    # 卡 21205721: 服务层显式级联（16 张子表: on_call/agent_memory 等 NOT NULL
    # 级联删, station/user/enterprise 等可空引用置空保留）
    from app.services.fk_cascade import purge_team_children
    purge_team_children(db, team_id)

    db.delete(team)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=admin.id, username=admin.username,
            action="delete", module="teams",
            target_id=str(team_id), target_desc=f"删除团队:{team_id}",
        )
    except Exception:
        pass
    return action_response(success=True, message=f"团队 {team_id} 已删除")


@router.get("/{team_id}/members")
def get_team_members(
    team_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取团队成员列表（卡 85deafc4: 非 platform admin 跨队 → 404，防 PII 枚举）"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    assert_team_access(user, team.id)

    query = db.query(User).filter(User.team_id == team_id)
    if status:
        query = query.filter(User.status == status)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_user_to_dict(m) for m in items],
        total, page, page_size
    )


@router.post("/{team_id}/members")
def add_team_member(team_id: int, data: MemberAdd, db: Session = Depends(get_db),
                    _admin: User = Depends(require_platform_admin)):
    """添加团队成员（卡 85deafc4: platform admin only，防移动任意用户/提权）"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户 {data.user_id} 不存在")

    user.team_id = team_id
    db.commit()
    db.refresh(user)
    return success_response(_user_to_dict(user))


@router.delete("/{team_id}/members/{member_id}")
def remove_team_member(team_id: int, member_id: int, db: Session = Depends(get_db),
                       _admin: User = Depends(require_platform_admin)):
    """移除团队成员（卡 85deafc4: platform admin only）"""
    user = db.query(User).filter(User.id == member_id, User.team_id == team_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在或不属于该团队")

    user.team_id = None
    db.commit()
    return action_response(success=True, message=f"成员 {member_id} 已从团队 {team_id} 移除")
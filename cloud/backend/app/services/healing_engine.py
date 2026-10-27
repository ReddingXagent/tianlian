"""
告警自愈引擎

核心逻辑：
1. 当告警产生时，评估是否匹配自愈规则
2. 匹配成功后创建自愈执行记录
3. 根据规则配置决定自动执行或等待审批
4. 调用RunbookEngine执行修复步骤
5. 记录执行结果
"""
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.alarm import Alarm
from app.models.device import Device
from app.services.runbook_engine import RunbookEngine

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """统一 naive-UTC 时间戳写入。

    HealingExecution.created_at = server_default func.now() → SQLite 实存 naive UTC。
    approved_at/started_at/completed_at 等应用层写入须与之同形态, 才能与
    _check_cooldown / batch_verify_completed 的 naive cutoff 稳健比较 (缺口5)。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 冷却判定纳入的"活跃"状态集: 处于这些状态的近期执行会阻止同 rule+device 重复触发
_ACTIVE_STATUSES = ["success", "partial_success", "pending_approval", "approved", "running"]


class HealingEngine:
    """告警自愈引擎"""

    def __init__(self):
        self._runbook_engine = RunbookEngine()

    # ========== 告警评估 ==========

    def evaluate_alarm(self, alarm: Alarm, db: Session) -> Optional[Dict]:
        """
        评估告警是否匹配自愈规则

        Args:
            alarm: 告警对象
            db: 数据库会话

        Returns:
            匹配结果（None表示无匹配）
        """
        rules = db.query(HealingRule).filter(
            HealingRule.enabled == True
        ).order_by(desc(HealingRule.priority)).all()

        for rule in rules:
            if self._match_alarm(alarm, rule):
                # 检查冷却时间
                if self._check_cooldown(rule.id, alarm.device_id, db):
                    logger.info(
                        f"自愈规则[{rule.name}]匹配告警#{alarm.id}，但处于冷却期，跳过"
                    )
                    continue

                # 创建执行记录
                execution = self._create_execution(rule, alarm, db)
                if execution is None:
                    # _create_execution 内部异常(已 rollback)返回 None，跳过本规则继续尝试下一条
                    logger.warning(
                        f"自愈规则[{rule.name}]匹配告警#{alarm.id}，但创建执行记录失败，跳过该规则"
                    )
                    continue
                logger.info(
                    f"自愈规则[{rule.name}]匹配告警#{alarm.id}，"
                    f"创建执行记录#{execution.id}"
                )

                # 判断是否需要审批
                if rule.auto_approve:
                    # 自动审批，直接执行
                    return self._execute_auto(execution, alarm, rule, db)
                else:
                    # 等待人工审批
                    return {
                        "execution_id": execution.id,
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "alarm_id": alarm.id,
                        "status": "pending_approval",
                        "message": "等待人工审批",
                    }

        return None

    def _match_alarm(self, alarm: Alarm, rule: HealingRule) -> bool:
        """
        检查告警是否匹配自愈规则的条件

        alarm_pattern 示例:
        {
            "alarm_levels": ["critical", "warning"],
            "alarm_types": ["逆变器通讯中断", "设备离线"],
            "device_types": ["inverter"],
            "device_ids": [1, 2, 3],
            "station_ids": [1],
            "content_keywords": ["过温", "通讯"]
        }
        """
        pattern = rule.alarm_pattern
        if not pattern:
            return False

        # 检查告警级别
        alarm_levels = pattern.get("alarm_levels", [])
        if alarm_levels:
            alarm_level = alarm.level.value if hasattr(alarm.level, 'value') else str(alarm.level)
            if alarm_level not in alarm_levels:
                return False

        # 检查告警类型
        alarm_types = pattern.get("alarm_types", [])
        if alarm_types:
            alarm_type = alarm.alarm_type or ""
            if not any(t in alarm_type for t in alarm_types):
                return False

        # 检查设备类型 - 需要从alarm关联device获取
        device_types = pattern.get("device_types", [])
        if device_types:
            if not alarm.device:
                # 设备已删除/关联断裂: 规则既限定设备类型则判不匹配，避免对错误目标过度匹配
                logger.warning(
                    f"自愈规则[{rule.name}]配置了device_types，但告警#{alarm.id}无关联设备，判不匹配"
                )
                return False
            device_type = alarm.device.device_type.value if hasattr(alarm.device.device_type, 'value') else str(alarm.device.device_type)
            if device_type not in device_types:
                return False

        # 检查设备ID
        device_ids = pattern.get("device_ids", [])
        if device_ids and alarm.device_id not in device_ids:
            return False

        # 检查站点ID
        station_ids = pattern.get("station_ids", [])
        if station_ids and alarm.station_id not in station_ids:
            return False

        # 检查内容关键词
        content_keywords = pattern.get("content_keywords", [])
        if content_keywords:
            if not alarm.content:
                # 规则既限定内容关键词但告警内容为空: 判不匹配，避免静默跳过过滤
                logger.warning(
                    f"自愈规则[{rule.name}]配置了content_keywords，但告警#{alarm.id}内容为空，判不匹配"
                )
                return False
            if not any(kw in alarm.content for kw in content_keywords):
                return False

        return True

    def _check_cooldown(self, rule_id: int, device_id: int, db: Session) -> bool:
        """检查规则是否在冷却期内（同一规则+同一设备）"""
        rule = db.query(HealingRule).filter(HealingRule.id == rule_id).first()
        if not rule or not rule.cooldown_minutes or rule.cooldown_minutes <= 0:
            return False

        cutoff = _utcnow_naive() - timedelta(minutes=rule.cooldown_minutes)
        recent = db.query(HealingExecution).filter(
            HealingExecution.rule_id == rule_id,
            HealingExecution.device_id == device_id,
            HealingExecution.created_at >= cutoff,
            HealingExecution.status.in_(_ACTIVE_STATUSES),
        ).first()

        return recent is not None

    def _detect_duplicate_execution(
        self, rule: HealingRule, execution: HealingExecution, db: Session
    ) -> bool:
        """TOCTOU 自查: commit 后判断是否有更早插入的同 rule+device 近期活跃记录。

        _check_cooldown 与 _create_execution 之间无锁无唯一约束。同设备告警风暴下
        (alarm_rule_service 自动链 + healing 手动 API 双入口并发), 两线程都过冷却检查后
        各自插入 → 双执行记录; auto_approve 时同设备双 runbook 并行(重复重启/重复下发)。

        仲裁: 保留 id 最小(最早插入)的那条。后来者(存在 id < 自身的近期活跃记录)自判
        为重复, 由 _create_execution 删除自身并返回 None, evaluate_alarm 据 None 跳过本规则。
        """
        if not rule.cooldown_minutes or rule.cooldown_minutes <= 0:
            return False
        cutoff = _utcnow_naive() - timedelta(minutes=rule.cooldown_minutes)
        earlier = db.query(HealingExecution).filter(
            HealingExecution.rule_id == rule.id,
            HealingExecution.device_id == execution.device_id,
            HealingExecution.created_at >= cutoff,
            HealingExecution.id < execution.id,
            HealingExecution.status.in_(_ACTIVE_STATUSES),
        ).first()
        return earlier is not None

    def _create_execution(
        self, rule: HealingRule, alarm: Alarm, db: Session
    ) -> Optional[HealingExecution]:
        """创建自愈执行记录

        插入后立即 TOCTOU 自查(缺口1): 若发现更早插入的同 rule+device 近期活跃记录,
        自判为重复者 → 删除自身并返回 None, 调用方(evaluate_alarm)据此跳过本规则,
        避免并发风暴下的双执行记录/双 runbook 并行。
        """
        try:
            execution = HealingExecution(
                rule_id=rule.id,
                rule_name=rule.name,
                alarm_id=alarm.id,
                device_id=alarm.device_id,
                station_id=alarm.station_id,
                runbook_template=rule.runbook_template,
                fault_type=alarm.alarm_type or alarm.fault_code or "未知故障",
                status="pending_approval",
                steps=[],
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)

            if self._detect_duplicate_execution(rule, execution, db):
                logger.info(
                    "自愈规则[%s]告警#%s并发触发, 自身为重复执行#%s, 已撤销",
                    rule.name, alarm.id, execution.id,
                )
                db.delete(execution)
                db.commit()
                return None
            return execution
        except Exception as e:
            db.rollback()
            logger.error("创建自愈执行记录失败(alarm=%s): %s", alarm.id, e)
            return None

    # ========== 执行逻辑 ==========

    def _execute_auto(
        self, execution: HealingExecution, alarm: Alarm, rule: HealingRule, db: Session
    ) -> Dict:
        """自动审批并执行"""
        execution.status = "approved"
        execution.approved_by = "auto"
        execution.approved_at = _utcnow_naive()
        db.commit()

        return self.execute_healing(execution.id, db, alarm, rule)

    def execute_healing(
        self, execution_id: int, db: Session,
        alarm: Optional[Alarm] = None, rule: Optional[HealingRule] = None
    ) -> Dict:
        """
        执行自愈流程

        调用RunbookEngine执行修复步骤
        """
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": f"执行记录#{execution_id}不存在"}

        # 加载关联数据
        if not alarm:
            alarm = db.query(Alarm).filter(Alarm.id == execution.alarm_id).first()
        if not rule:
            rule = db.query(HealingRule).filter(HealingRule.id == execution.rule_id).first()

        if not alarm:
            execution.status = "failed"
            execution.error_message = f"告警#{execution.alarm_id}不存在"
            db.commit()
            return {"error": "告警不存在"}

        # 获取设备信息
        device = db.query(Device).filter(Device.id == alarm.device_id).first()
        if not device:
            execution.status = "failed"
            execution.error_message = f"设备#{alarm.device_id}不存在"
            db.commit()
            return {"error": "设备不存在"}

        device_info = {
            "id": device.id,
            "name": device.name,
            "sn": device.sn,
            "ip": device.ip_address or "",
            "station_id": alarm.station_id or device.station_id or 0,
            "type": device.device_type.value if hasattr(device.device_type, 'value') else str(device.device_type),
        }

        # 构造诊断结果
        diagnosis_result = {}
        if alarm.diagnosis_result:
            try:
                diagnosis_result = json.loads(alarm.diagnosis_result) if isinstance(alarm.diagnosis_result, str) else alarm.diagnosis_result
            except Exception:
                logger.warning("诊断结果JSON解析失败，丢弃损坏数据", exc_info=True)
        if not diagnosis_result.get("fault_type"):
            diagnosis_result["fault_type"] = execution.fault_type

        # 更新状态为执行中
        execution.status = "running"
        execution.started_at = _utcnow_naive()
        db.commit()

        try:
            # 调用RunbookEngine执行
            result = self._runbook_engine.execute(
                alarm_id=alarm.id,
                diagnosis_result=diagnosis_result,
                device_info=device_info,
                db=db,
                auto_trigger=True,
            )

            # 更新执行记录
            execution.runbook_id = result.get("runbook_id")
            execution.steps = result.get("steps", [])
            execution.total_duration_ms = result.get("total_duration_ms", 0)
            execution.success_steps = result.get("success_steps", 0)
            execution.failed_steps = result.get("failed_steps", 0)

            # 确定最终状态 (缺口3): 优先尊重 runbook 的 status==failed 信号。
            # 旧逻辑 `status==failed and success==0 → failed` 会让 status==failed + success>0
            # + failed==0 落入 else → 误记 success。改为: 有失败且有成功步骤才 partial;
            # 否则只要 status==failed 即 failed, 避免 runbook 级失败被记为成功。
            success_steps = result.get("success_steps", 0)
            failed_steps = result.get("failed_steps", 0)
            if failed_steps > 0 and success_steps > 0:
                execution.status = "partial_success"
            elif result.get("status") == "failed":
                execution.status = "failed"
            elif result.get("status") == "pending_approval":
                execution.status = "pending_approval"
            else:
                execution.status = "success"

            execution.result = (
                f"Runbook执行完成: {success_steps}成功/"
                f"{failed_steps}失败/"
                f"{result.get('skipped_steps', 0)}跳过"
            )
            execution.error_message = result.get("error_message", "")
            execution.completed_at = _utcnow_naive()
            db.commit()

            return {
                "execution_id": execution.id,
                "status": execution.status,
                "result": execution.result,
                "runbook_id": execution.runbook_id,
                "total_duration_ms": execution.total_duration_ms,
                "success_steps": execution.success_steps,
                "failed_steps": execution.failed_steps,
            }

        except Exception as e:
            logger.exception(f"自愈执行#{execution_id}失败: {e}")
            execution.status = "failed"
            execution.error_message = str(e)[:500]
            execution.completed_at = _utcnow_naive()
            db.commit()

            return {
                "execution_id": execution.id,
                "status": "failed",
                "error": "服务内部错误，请稍后重试",
            }

    # ========== 审批操作 ==========

    def approve_execution(
        self, execution_id: int, approver: str, db: Session
    ) -> Dict:
        """审批通过自愈执行"""
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": f"执行记录#{execution_id}不存在"}

        if execution.status not in ("pending_approval",):
            return {"error": f"当前状态[{execution.status}]不可审批"}

        try:
            execution.status = "approved"
            execution.approved_by = approver
            execution.approved_at = _utcnow_naive()
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("审批自愈执行#%s失败: %s", execution_id, e)
            return {"error": "服务内部错误，请稍后重试"}

        # 审批通过后自动执行
        result = self.execute_healing(execution.id, db=db)
        return result

    def reject_execution(
        self, execution_id: int, rejector: str, reason: str, db: Session
    ) -> Dict:
        """拒绝自愈执行"""
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": f"执行记录#{execution_id}不存在"}

        if execution.status not in ("pending_approval",):
            return {"error": f"当前状态[{execution.status}]不可拒绝"}

        try:
            execution.status = "rejected"
            execution.approved_by = rejector
            execution.reject_reason = reason
            execution.completed_at = _utcnow_naive()
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("拒绝自愈执行#%s失败: %s", execution_id, e)
            return {"error": "服务内部错误，请稍后重试"}

        return {
            "execution_id": execution.id,
            "status": "rejected",
            "message": "已拒绝执行",
        }

    def retry_execution(self, execution_id: int, db: Session) -> Dict:
        """重试失败的自愈执行"""
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": f"执行记录#{execution_id}不存在"}

        if execution.status not in ("failed", "partial_success"):
            return {"error": f"当前状态[{execution.status}]不可重试"}

        # 检查重试次数
        rule = db.query(HealingRule).filter(
            HealingRule.id == execution.rule_id
        ).first()
        max_retries = rule.max_retries if rule else 1

        if execution.retry_count >= max_retries:
            return {"error": f"已达到最大重试次数({max_retries})"}

        # 缺口2: 重试前必须查冷却。旧逻辑直接 approved+execute 绕过 _check_cooldown,
        # 同 rule+device 若有活跃执行(如已审批在跑), 重试将与之并发 → 重复下发指令/重复重启。
        if self._check_cooldown(execution.rule_id, execution.device_id, db):
            return {"error": "该规则-设备处于冷却期,暂不可重试"}

        try:
            execution.retry_count += 1
            execution.status = "approved"  # 重试视为已审批
            execution.error_message = ""
            execution.completed_at = None
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("重试自愈执行#%s失败: %s", execution_id, e)
            return {"error": "服务内部错误，请稍后重试"}

        result = self.execute_healing(execution.id, db=db)
        return result

    # ========== 规则管理 ==========

    def list_rules(self, db: Session, enabled_only: bool = False) -> List[Dict]:
        """列出自愈规则"""
        query = db.query(HealingRule)
        if enabled_only:
            query = query.filter(HealingRule.enabled == True)
        rules = query.order_by(desc(HealingRule.priority)).all()

        result = []
        for r in rules:
            result.append({
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "alarm_pattern": r.alarm_pattern,
                "runbook_template": r.runbook_template,
                "auto_approve": r.auto_approve,
                "max_retries": r.max_retries,
                "cooldown_minutes": r.cooldown_minutes,
                "priority": r.priority,
                "enabled": r.enabled,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return result

    @staticmethod
    def _validate_rule_data(data: Dict, *, partial: bool) -> Optional[str]:
        """校验规则字段, 返回错误描述或 None。

        partial=False(create): name/alarm_pattern 必填; partial=True(update): 仅校验已提供字段。
        服务层防御性校验——router Pydantic 已约束 HTTP 入口, 但内部直调(如 alarm_rule_service
        自愈链)绕过 Pydantic, 此处兜底返回 {"error":...} 由 router 映射 400, 避免 KeyError→500
        与负数/非数值被直接 setattr。
        """
        # 名称: 非空字符串
        if "name" in data or not partial:
            name = data.get("name")
            if not isinstance(name, str) or not name.strip():
                return "规则名称不能为空"
        # 告警匹配条件: 非空 dict
        if "alarm_pattern" in data or not partial:
            ap = data.get("alarm_pattern")
            if not isinstance(ap, dict) or not ap:
                return "告警匹配条件不能为空"
        # 数值字段: 非负整数 (排除 bool; bool 是 int 子类, 作为次数/优先级语义错误)
        for field in ("max_retries", "cooldown_minutes", "priority"):
            if field in data:
                val = data[field]
                if isinstance(val, bool) or not isinstance(val, int):
                    return f"{field} 必须是整数"
                if val < 0:
                    return f"{field} 不能为负数"
        # 布尔字段
        for field in ("auto_approve", "enabled"):
            if field in data and not isinstance(data[field], bool):
                return f"{field} 必须是布尔值"
        return None

    def create_rule(self, data: Dict, db: Session) -> Dict:
        """创建自愈规则"""
        err = self._validate_rule_data(data, partial=False)
        if err:
            return {"error": err}
        try:
            rule = HealingRule(
                name=data["name"],
                description=data.get("description", ""),
                alarm_pattern=data["alarm_pattern"],
                runbook_template=data.get("runbook_template"),
                auto_approve=data.get("auto_approve", False),
                max_retries=data.get("max_retries", 1),
                cooldown_minutes=data.get("cooldown_minutes", 30),
                priority=data.get("priority", 0),
                enabled=data.get("enabled", True),
            )
            db.add(rule)
            db.commit()
            db.refresh(rule)
            return {"id": rule.id, "name": rule.name, "message": "创建成功"}
        except Exception as e:
            db.rollback()
            logger.error("创建自愈规则失败: %s", e)
            return {"error": "服务内部错误，请稍后重试"}

    def update_rule(self, rule_id: int, data: Dict, db: Session) -> Dict:
        """更新自愈规则"""
        rule = db.query(HealingRule).filter(HealingRule.id == rule_id).first()
        if not rule:
            return {"error": f"规则#{rule_id}不存在"}

        err = self._validate_rule_data(data, partial=True)
        if err:
            return {"error": err}

        try:
            for key in ("name", "description", "alarm_pattern", "runbook_template",
                         "auto_approve", "max_retries", "cooldown_minutes", "priority", "enabled"):
                if key in data:
                    setattr(rule, key, data[key])
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("更新自愈规则#%s失败: %s", rule_id, e)
            return {"error": "服务内部错误，请稍后重试"}
        return {"id": rule.id, "name": rule.name, "message": "更新成功"}

    def delete_rule(self, rule_id: int, db: Session) -> Dict:
        """删除自愈规则"""
        rule = db.query(HealingRule).filter(HealingRule.id == rule_id).first()
        if not rule:
            return {"error": f"规则#{rule_id}不存在"}

        # 检查是否有正在执行的记录
        active = db.query(HealingExecution).filter(
            HealingExecution.rule_id == rule_id,
            HealingExecution.status.in_(["pending_approval", "approved", "running"])
        ).count()
        if active > 0:
            return {"error": f"该规则有{active}条正在执行的记录，请先处理"}

        try:
            db.delete(rule)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("删除自愈规则#%s失败: %s", rule_id, e)
            return {"error": "服务内部错误，请稍后重试"}
        return {"message": "删除成功"}

    # ========== 执行记录 ==========

    def list_executions(
        self, db: Session, status: Optional[str] = None,
        rule_id: Optional[int] = None, device_id: Optional[int] = None,
        page: int = 1, page_size: int = 20,
        station_ids: Optional[list] = None
    ) -> Dict:
        """查询执行记录

        station_ids 用于团队隔离（任务卡 ed509541）：非 None 时仅返回这些站点
        下的执行记录。API 层传入本 team 的 station_ids 实现 team scoping。
        """
        query = db.query(HealingExecution)
        if station_ids is not None:
            query = query.filter(HealingExecution.station_id.in_(station_ids))

        if status:
            query = query.filter(HealingExecution.status == status)
        if rule_id:
            query = query.filter(HealingExecution.rule_id == rule_id)
        if device_id:
            query = query.filter(HealingExecution.device_id == device_id)

        total = query.count()
        executions = query.order_by(desc(HealingExecution.created_at)).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        items = []
        for e in executions:
            items.append({
                "id": e.id,
                "rule_id": e.rule_id,
                "rule_name": e.rule_name,
                "alarm_id": e.alarm_id,
                "device_id": e.device_id,
                "station_id": e.station_id,
                "runbook_id": e.runbook_id,
                "fault_type": e.fault_type,
                "status": e.status,
                "approved_by": e.approved_by,
                "total_duration_ms": e.total_duration_ms,
                "success_steps": e.success_steps,
                "failed_steps": e.failed_steps,
                "retry_count": e.retry_count,
                "result": e.result,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get_execution(self, execution_id: int, db: Session) -> Optional[Dict]:
        """获取执行详情"""
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return None

        return {
            "id": execution.id,
            "rule_id": execution.rule_id,
            "rule_name": execution.rule_name,
            "alarm_id": execution.alarm_id,
            "device_id": execution.device_id,
            "station_id": execution.station_id,
            "runbook_id": execution.runbook_id,
            "runbook_template": execution.runbook_template,
            "fault_type": execution.fault_type,
            "status": execution.status,
            "steps": execution.steps,
            "approved_by": execution.approved_by,
            "approved_at": execution.approved_at.isoformat() if execution.approved_at else None,
            "reject_reason": execution.reject_reason,
            "total_duration_ms": execution.total_duration_ms,
            "success_steps": execution.success_steps,
            "failed_steps": execution.failed_steps,
            "retry_count": execution.retry_count,
            "result": execution.result,
            "error_message": execution.error_message,
            "created_at": execution.created_at.isoformat() if execution.created_at else None,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        }

    # ========== 统计 ==========

    def get_stats(self, db: Session) -> Dict:
        """获取自愈统计"""
        from sqlalchemy import func

        total = db.query(func.count(HealingExecution.id)).scalar() or 0

        # 按状态统计
        status_stats = {}
        for row in db.query(
            HealingExecution.status, func.count(HealingExecution.id)
        ).group_by(HealingExecution.status).all():
            status_stats[row[0]] = row[1]

        # 成功率
        success_count = status_stats.get("success", 0) + status_stats.get("partial_success", 0)
        success_rate = round(success_count / total * 100, 1) if total > 0 else 0

        # 平均耗时
        avg_duration = db.query(
            func.avg(HealingExecution.total_duration_ms)
        ).filter(
            HealingExecution.status.in_(["success", "partial_success", "failed"])
        ).scalar() or 0

        # 自动执行率
        auto_count = db.query(func.count(HealingExecution.id)).filter(
            HealingExecution.approved_by == "auto"
        ).scalar() or 0
        auto_rate = round(auto_count / total * 100, 1) if total > 0 else 0

        # 待审批数
        pending_count = status_stats.get("pending_approval", 0)

        return {
            "total": total,
            "status_breakdown": status_stats,
            "success_rate": success_rate,
            "average_duration_ms": round(avg_duration, 0),
            "auto_approve_rate": auto_rate,
            "pending_approvals": pending_count,
        }


    # ========== 自愈效果验证 ==========

    def verify_healing_result(
        self, execution_id: int, db: Session
    ) -> Dict:
        """
        验证自愈执行后的效果
        
        检查告警是否已清除、设备是否恢复正常
        """
        execution = db.query(HealingExecution).filter(
            HealingExecution.id == execution_id
        ).first()
        if not execution:
            return {"error": f"执行记录#{execution_id}不存在"}

        if execution.status not in ("success", "partial_success"):
            return {"error": f"当前状态[{execution.status}]不可验证"}

        # 检查关联告警是否已清除
        alarm = db.query(Alarm).filter(Alarm.id == execution.alarm_id).first()
        alarm_cleared = False
        if alarm:
            alarm_cleared = alarm.status in ("cleared", "resolved") if hasattr(alarm, 'status') else False

        # 检查设备是否在线
        device = db.query(Device).filter(Device.id == execution.device_id).first()
        device_online = False
        if device:
            device_online = (
                device.status.value in ("online", "normal", "running")
                if hasattr(device.status, 'value')
                else str(device.status) in ("online", "normal", "running")
            )

        # 综合判断
        if alarm_cleared and device_online:
            verification = "healed"
        elif alarm_cleared or device_online:
            verification = "partial"
        else:
            verification = "unhealed"

        # 更新执行记录
        try:
            execution.verified = True
            execution.verified_at = _utcnow_naive()
            execution.verification_result = verification
            execution.alarm_cleared = alarm_cleared
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("验证自愈结果#%s失败: %s", execution_id, e)
            return {"error": "服务内部错误，请稍后重试"}

        logger.info(
            f"自愈验证#{execution_id}: {verification} "
            f"(告警清除={alarm_cleared}, 设备在线={device_online})"
        )

        return {
            "execution_id": execution.id,
            "verification_result": verification,
            "alarm_cleared": alarm_cleared,
            "device_online": device_online,
        }

    def batch_verify_completed(
        self, db: Session, hours: int = 24, limit: int = 200
    ) -> Dict:
        """
        批量验证已成功执行但未验证的记录
        
        Args:
            hours: 检查最近N小时内完成的执行记录
            limit: 单次最大验证条数(防止积压时全量加载拖垮内存)
        """
        cutoff = _utcnow_naive() - timedelta(hours=hours)
        executions = db.query(HealingExecution).filter(
            HealingExecution.status.in_(["success", "partial_success"]),
            HealingExecution.verified == False,
            HealingExecution.completed_at >= cutoff,
        ).limit(limit).all()
        logger.info(
            f"批量验证自愈记录: 命中{len(executions)}条(单次上限{limit})"
        )

        results = {"healed": 0, "partial": 0, "unhealed": 0, "errors": 0}
        for e in executions:
            try:
                r = self.verify_healing_result(e.id, db)
                if "error" in r:
                    results["errors"] += 1
                else:
                    results[r["verification_result"]] = results.get(r["verification_result"], 0) + 1
            except Exception:
                results["errors"] += 1

        return {
            "total_verified": len(executions),
            "results": results,
        }


# ========== 全局引擎实例 ==========
healing_engine = HealingEngine()
